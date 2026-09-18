import math
import os
from dataclasses import asdict
from datetime import datetime
import networkx as nx
import numpy as np
import osmnx as ox
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from typing import Literal

from core.graph_model import add_objective_weights, path_metrics
from core.stop_selection import choose_spread_stops
from core.vrp import Customer, VRPInstance, capacity_feasible
from core.engine import build_routing_data, solve_qpso, solve_ga_baseline
from core.heuristics import solve_dynamic_heuristic
from core.traffic import apply_traffic_scenario
from core.time_dependent import build_time_indexed_matrix
from core.tomtom_routing import TomTomRoutingError, fetch_live_matrix
from core.live_traffic_control import LiveTrafficGovernor

load_dotenv()

app = FastAPI(title="Quantum VRP Dispatch Engine")

def get_allowed_origins() -> list[str]:
    configured_origins = os.getenv("ALLOWED_ORIGINS", "")

    if configured_origins.strip():
        return [
            origin.strip().rstrip("/")
            for origin in configured_origins.split(",")
            if origin.strip()
        ]

    # Safe local-development fallback
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8501",
        "http://127.0.0.1:8501",
    ]

# for checking the allowed CORS origins
# print("Allowed CORS origins:", get_allowed_origins())

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),  # parentheses are required
    allow_credentials=False,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

GRAPH_CACHE = {}
LIVE_TRAFFIC_GOVERNOR = LiveTrafficGovernor()

class OptimizationRequest(BaseModel):
    place_name: str = Field("Salt Lake, Kolkata, India", min_length=1)
    customers_n: int = Field(10, ge=1, le=500)
    num_vehicles: int = Field(4, ge=1, le=100)
    vehicle_capacity: float = Field(25.0, gt=0)
    distance_weight: float = Field(0.2, ge=0)
    particles: int = Field(40, ge=3, le=1000)
    iterations: int = Field(100, ge=1, le=5000)
    traffic_mode: Literal["simulated", "live"] = "simulated"
    traffic_seed: int = 42
    sla_strictness_hours: float = Field(4.0, gt=0, le=24)

def prepare_osm_graph(place_name: str):
    """Download a WGS84 road graph, keep its strongly connected core, and patch edge metrics."""
    if place_name in GRAPH_CACHE:
        return GRAPH_CACHE[place_name]

    # Load unprojected graph (WGS84 EPSG:4326) for GeoJSON GPS coordinates
    G_raw = ox.graph_from_place(place_name, network_type="drive", simplify=True)
    
    # Guarantee legal bidirectional driving paths exist between all node pairs
    if G_raw.is_directed():
        scc = max(nx.strongly_connected_components(G_raw), key=len)
        G = G_raw.subgraph(scc).copy()
    else:
        cc = max(nx.connected_components(G_raw), key=len)
        G = G_raw.subgraph(cc).copy()

    # Pre-calculate fallback edge metrics
    for u, v, k, data in G.edges(keys=True, data=True):
        if 'distance_m' not in data:
            data['distance_m'] = float(data.get('length', 10.0))
        if 'travel_time_s' not in data:
            data['travel_time_s'] = data['distance_m'] / 8.33  # ~30 km/h baseline

    GRAPH_CACHE[place_name] = G
    return G

@app.post("/api/optimize")
def run_optimization(req: OptimizationRequest, request: Request):
    try:
        G_base = prepare_osm_graph(req.place_name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to load map network: {str(e)}")

    # Simulated mode uses the local seeded traffic model. Live mode keeps the
    # OSM graph for stop selection and geometry, while all optimization costs
    # come from the live TomTom matrix below.
    if req.traffic_mode == "live":
        G = G_base.copy()
        local_now = datetime.now().astimezone()
        dispatch_start_s = (
            local_now.hour * 3600.0
            + local_now.minute * 60.0
            + local_now.second
            + local_now.microsecond / 1_000_000.0
        )
    else:
        G = apply_traffic_scenario(
            G_base,
            mode="off_peak",
            seed=req.traffic_seed,
        )
        dispatch_start_s = 32400.0

    # Dynamically select nodes directly from the graph
    try:
        depot_node, customer_nodes = choose_spread_stops(
            G, req.customers_n, seed=req.traffic_seed
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    rng = np.random.default_rng(req.traffic_seed)
    demands = rng.integers(1, 8, size=len(customer_nodes))
    
    # Check both aggregate capacity and the actual bin-packing feasibility of
    # the generated demands. Aggregate capacity alone is insufficient.
    total_demand = sum(demands)
    total_fleet_capacity = int(req.num_vehicles) * float(req.vehicle_capacity)

    if not capacity_feasible(demands, req.vehicle_capacity, req.num_vehicles):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Infeasible fleet: demand is {total_demand} items and total capacity is "
                f"{total_fleet_capacity}, but the individual demands cannot be packed "
                "into the requested vehicles. Increase fleet size or capacity."
            ),
        )

    # Convert UI slider (hours) directly into seconds
    strictness_seconds = req.sla_strictness_hours * 3600.0
    start_of_day = dispatch_start_s
    
    customer_objs = []
    node_to_id = {depot_node: "Depot"}
    frontend_customers = []
    
    for i, (node, demand) in enumerate(zip(customer_nodes, demands)):
        window_duration = strictness_seconds
        offset = rng.uniform(0, 7200)
        
        c_ready_time = start_of_day + offset
        c_due_time = c_ready_time + window_duration
        
        customer_objs.append(Customer(
            node=node, 
            demand=float(demand),
            ready_time=c_ready_time,
            due_time=c_due_time,
            service_time=300.0
        ))
        
        c_id = f"C{i+1}"
        node_to_id[node] = c_id
        frontend_customers.append({
            "id": c_id,
            "lat": G.nodes[node]['y'],
            "lng": G.nodes[node]['x'],
            "demand": float(demand),
            "ready_time": c_ready_time,
            "due_time": c_due_time
        })

    frontend_depot = {
        "id": "Depot",
        "lat": G.nodes[depot_node]['y'],
        "lng": G.nodes[depot_node]['x']
    }

    instance = VRPInstance(
        depot=depot_node,
        customers=customer_objs,
        vehicle_capacity=float(req.vehicle_capacity),
        num_vehicles=int(req.num_vehicles),
        dispatch_start_s=dispatch_start_s,
    )

    # Build one shared matrix and pass it to every algorithm.  Simulated mode
    # generates it locally; live mode obtains it once from TomTom.  In both
    # cases no provider request occurs during particle/genome evaluation.
    stop_nodes = [depot_node] + customer_nodes
    traffic_summary = None
    if req.traffic_mode == "live":
        user_id = (
            request.client.host
            if request is not None and request.client is not None
            else "local-client"
        )
        cache_payload = {
            "place_name": req.place_name.strip().lower(),
            "stops": [
                {
                    "node": str(node),
                    "lat": round(float(G.nodes[node]["y"]), 7),
                    "lng": round(float(G.nodes[node]["x"]), 7),
                }
                for node in stop_nodes
            ],
            "distance_weight": float(req.distance_weight),
            "travel_mode": "truck",
            "traffic": "live",
        }
        live_cache_key = LIVE_TRAFFIC_GOVERNOR.cache_key(cache_payload)

        try:
            live_result, decision = LIVE_TRAFFIC_GOVERNOR.get_or_fetch(
                live_cache_key,
                user_id,
                origins=len(stop_nodes),
                destinations=len(stop_nodes),
                fetch=lambda: fetch_live_matrix(
                    G,
                    stop_nodes,
                    time_weight=1.0,
                    distance_weight=req.distance_weight,
                    dispatch_start_s=dispatch_start_s,
                    departure_time="now",
                ),
            )
        except TomTomRoutingError as exc:
            # The local model remains available if the provider is unavailable,
            # the key is missing, or the request exceeds provider limits.
            live_result = None
            decision = LIVE_TRAFFIC_GOVERNOR.decide(
                user_id, len(stop_nodes), len(stop_nodes)
            )
            decision_reason = f"tomtom_request_failed: {exc}"
        else:
            decision_reason = decision.reason

        if live_result is not None:
            time_matrix = live_result.matrix
            traffic_summary = asdict(live_result.summary)
            traffic_summary.update(asdict(decision))
            traffic_summary.update({
                "requested_mode": "live",
                "fallback": False,
            })
        else:
            # Preserve the requested live mode in telemetry, but make the
            # route usable with a deterministic local rush-hour fallback.
            G = apply_traffic_scenario(
                G_base,
                mode="rush_hour",
                seed=req.traffic_seed,
            )
            time_matrix = build_time_indexed_matrix(
                G,
                stop_nodes,
                time_weight=1.0,
                distance_weight=req.distance_weight,
                seed=req.traffic_seed,
                start_s=dispatch_start_s,
            )
            traffic_summary = {
                "provider": "local_fallback",
                "requested_mode": "live",
                "fallback": True,
                "fallback_reason": decision_reason,
                **asdict(decision),
            }
    else:
        # The seeded dataset is a deterministic off-peak scenario. Use its
        # traffic-adjusted graph directly as one shared static matrix. A full
        # time-indexed matrix would copy the entire OSM graph dozens of times
        # and provide no additional information for this selected scenario.
        # Live mode retains time-dependent provider/fallback behavior below.
        time_matrix = None

    # Build the static stop matrix once per request. GA and QPSO use the same
    # request-scoped data instead of repeating identical Dijkstra searches.
    routing_data = build_routing_data(
        G,
        instance,
        time_weight=1.0,
        distance_weight=req.distance_weight,
    )

    # 1. Benchmark Execution: A* Baseline, GA, and QPSO
    results = {}
    
    # A* Greedy Constructive Baseline
    results['A*'] = solve_dynamic_heuristic(
        G,
        instance,
        method='astar',
        distance_weight=req.distance_weight,
        time_matrix=time_matrix,
        dispatch_start_s=dispatch_start_s,
    )
    
    # Genetic Algorithm
    results['GA'] = solve_ga_baseline(
        G, instance, particles=req.particles, iterations=req.iterations,
        seed=req.traffic_seed, distance_weight=req.distance_weight,
        time_matrix=time_matrix,
        dispatch_start_s=dispatch_start_s,
        routing_data=routing_data,
    )
    
    # Quantum PSO
    results['QPSO'] = solve_qpso(
        G, instance, particles=req.particles, iterations=req.iterations,
        seed=req.traffic_seed, distance_weight=req.distance_weight,
        time_matrix=time_matrix,
        dispatch_start_s=dispatch_start_s,
        routing_data=routing_data,
    )

    def first_nonfinite(value, path="result"):
        if isinstance(value, (float, np.floating)) and not math.isfinite(float(value)):
            return path
        if isinstance(value, dict):
            for key, child in value.items():
                found = first_nonfinite(child, f"{path}.{key}")
                if found:
                    return found
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                found = first_nonfinite(child, f"{path}[{index}]")
                if found:
                    return found
        return None

    for algorithm, solution in results.items():
        nonfinite_path = first_nonfinite(solution, algorithm)
        if nonfinite_path:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{algorithm} could not produce a finite route for this instance "
                    f"({nonfinite_path}). Increase fleet capacity, check graph connectivity, "
                    "or increase the optimizer budget."
                ),
            )

    # Every algorithm is evaluated on the same customer set.  Reject a
    # malformed/partial solver result instead of allowing the dashboard to
    # silently show a different number of stops for GA or A*.
    expected_customer_nodes = {customer.node for customer in customer_objs}
    for algorithm, solution in results.items():
        served_nodes = [
            node
            for route in solution.get("routes", [])
            for node in route
            if node != depot_node
        ]
        served_set = set(served_nodes)
        if served_set != expected_customer_nodes or len(served_nodes) != len(expected_customer_nodes):
            missing = expected_customer_nodes - served_set
            duplicate_count = len(served_nodes) - len(served_set)
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{algorithm} returned an incomplete customer set: "
                    f"expected {len(expected_customer_nodes)} stops, got "
                    f"{len(served_nodes)} ({len(missing)} missing, "
                    f"{duplicate_count} duplicates). Check the solver's route decoder."
                ),
            )

    # 2. Compute logistics impact. Keep negative savings visible when QPSO is
    # worse than the baseline instead of masking the regression with max(0, x).
    qpso_dist_km = results['QPSO'].get('distance_m', 0) / 1000.0
    astar_dist_km = results['A*'].get('distance_m', 0) / 1000.0
    dist_saved_km = astar_dist_km - qpso_dist_km
    
    # Logistics constant standards: 8 km/L fuel efficiency, ₹100/L diesel, 2.68 kg CO2/L
    liters_saved = dist_saved_km / 8.0
    rupees_saved = liters_saved * 100.0
    co2_saved_kg = liters_saved * 2.68

    # 3. Serialize every solution so the dashboard can inspect the selected
    # algorithm without silently continuing to display QPSO routes.
    palette = ["#D90429", "#0077B6", "#2A9D8F", "#F4A261", "#7209B7", "#FFB703"]
    cust_dict = {c.node: c for c in customer_objs}

    display_graph = add_objective_weights(
        G, time_weight=1.0, distance_weight=req.distance_weight
    )

    def serialize_solution(solution):
        routes_geojson = {"type": "FeatureCollection", "features": []}
        schedule_data = []
        for v_idx, route in enumerate(solution.get("routes", [])):
            color = palette[v_idx % len(palette)]
            coords = []
            stops_labels = [node_to_id.get(n, str(n)) for n in route]
            current_time = dispatch_start_s
            route_start = current_time
            stops_timeline = []

            for leg_index, (a, b) in enumerate(zip(route[:-1], route[1:])):
                dynamic_leg = next(
                    (
                        leg
                        for leg in solution.get("leg_metrics", [])
                        if leg.get("route_index") == v_idx
                        and leg.get("leg_index") == leg_index
                    ),
                    None,
                )
                if a == b:
                    path = [a]
                    segment_time = 0.0
                elif dynamic_leg is not None:
                    path = dynamic_leg.get("path") or solution.get("paths", {}).get((a, b))
                    if not path:
                        path = [a, b]
                    segment_time = float(dynamic_leg.get("travel_time_s", math.inf))
                else:
                    path = solution.get("paths", {}).get((a, b))
                    if not path:
                        path = [a, b]
                    segment_time, _ = path_metrics(
                        display_graph, path, weight="_routing_weight"
                    )
                if not math.isfinite(segment_time):
                    raise HTTPException(
                        status_code=422,
                        detail=f"{solution.get('algorithm', 'A route')} contains an unreachable leg {a}->{b}.",
                    )
                current_time += segment_time

                if b in cust_dict:
                    current_time = max(current_time, cust_dict[b].ready_time)
                stops_timeline.append({
                    "stopId": node_to_id.get(b, str(b)),
                    "arrivalTime_s": round(current_time, 1),
                    "isDepot": b == instance.depot,
                })

                if b in cust_dict:
                    current_time += cust_dict[b].service_time

                for node in path:
                    if node in G.nodes:
                        coords.append([G.nodes[node]["x"], G.nodes[node]["y"]])

            if len(coords) > 1:
                routes_geojson["features"].append({
                    "type": "Feature",
                    "properties": {
                        "vehicle": v_idx + 1,
                        "color": color,
                        "stops": stops_labels,
                    },
                    "geometry": {"type": "LineString", "coordinates": coords},
                })
            schedule_data.append({
                "vehicle": v_idx + 1,
                "color": color,
                "stops": stops_labels,
                "timeline": stops_timeline,
                "totalTime_min": round((current_time - route_start) / 60.0, 1),
            })
        return routes_geojson, schedule_data

    routes_by_algorithm = {}
    schedules_by_algorithm = {}
    for algorithm, solution in results.items():
        routes_by_algorithm[algorithm], schedules_by_algorithm[algorithm] = serialize_solution(solution)

    return {
        "locations": {
            "depot": frontend_depot,
            "customers": frontend_customers
        },
        "traffic": traffic_summary or {
            "provider": "local_seeded",
            "mode": "simulated",
            "seed": req.traffic_seed,
        },
        "business_impact": {
            "distance_saved_km": round(dist_saved_km, 2),
            "rupees_saved": round(rupees_saved, 0),
            "liters_saved": round(liters_saved, 1),
            "co2_saved_kg": round(co2_saved_kg, 1),
            "qpso_dist_km": round(qpso_dist_km, 2),
            "astar_dist_km": round(astar_dist_km, 2)
        },
        "algorithms": {
            algorithm: {
                "score": round(solution["score"], 2),
                "distance_km": round(solution["distance_m"] / 1000.0, 2),
                "travel_time_min": round(solution["travel_time_s"] / 60.0, 1),
                "total_duration_min": round(solution["total_duration_s"] / 60.0, 1),
                "tw_penalty": round(solution.get("tw_penalty", 0.0), 2),
                "total_lateness_s": round(solution.get("total_lateness_s", 0.0), 1),
                "history": solution["history"],
            }
            for algorithm, solution in results.items()
        },
        "routes": routes_by_algorithm["QPSO"],
        "schedules": schedules_by_algorithm["QPSO"],
        "routes_by_algorithm": routes_by_algorithm,
        "schedules_by_algorithm": schedules_by_algorithm,
    }
