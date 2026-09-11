import time
import networkx as nx
import numpy as np
import osmnx as ox
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

from core.graph_model import build_stop_matrix, nearest_node
from core.vrp import Customer, VRPInstance
from core.engine import solve_qpso, solve_ga_baseline
from core.heuristics import solve_dynamic_heuristic
from core.traffic import apply_traffic_scenario

app = FastAPI(title="Quantum VRP Dispatch Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GRAPH_CACHE = {}

class OptimizationRequest(BaseModel):
    place_name: str = "Salt Lake, Kolkata, India"
    customers_n: int = 10
    num_vehicles: int = 4
    vehicle_capacity: float = 25.0
    distance_weight: float = 0.2
    particles: int = 40
    iterations: int = 100
    traffic_mode: str = "simulated"  # "simulated" | "live"
    traffic_seed: int = 42
    sla_strictness_hours: float = 4.0 # NEW: Dynamic SLA Slider

def prepare_osm_graph(place_name: str):
    """Downloads, projects to WGS84, extracts strongly connected subgraph, and patches edge attributes."""
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

def choose_stops(G, n, seed):
    """Selects a connected depot and n customers deterministically."""
    rng = np.random.default_rng(seed)
    components = nx.strongly_connected_components(G) if G.is_directed() else nx.connected_components(G)
    nodes = np.asarray(list(max(components, key=len)))
    
    if len(nodes) < n + 1:
        raise ValueError(f"Network requires {n + 1} connected nodes. Graph is too small.")
    
    chosen = rng.choice(nodes, size=n + 1, replace=False)
    return int(chosen[0]), [int(x) for x in chosen[1:]]

@app.post("/api/optimize")
def run_optimization(req: OptimizationRequest):
    try:
        G_base = prepare_osm_graph(req.place_name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to load map network: {str(e)}")

    # Bridge frontend terminology to backend telemetry models
    historical_mode = 'rush_hour' if req.traffic_mode == 'live' else 'off_peak'
    
    # Applies exact traversal speeds via cKDTree spatial joining
    G = apply_traffic_scenario(G_base, mode=historical_mode)

    # Dynamically select nodes directly from the graph
    try:
        depot_node, customer_nodes = choose_stops(G, req.customers_n, seed=req.traffic_seed)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    rng = np.random.default_rng(req.traffic_seed)
    demands = rng.integers(1, 8, size=len(customer_nodes))
    
    # 1. ENTERPRISE GUARDRAIL: Check if the problem is physically possible
    total_demand = sum(demands)
    total_fleet_capacity = int(req.num_vehicles) * float(req.vehicle_capacity)
    
    if total_demand > total_fleet_capacity:
        raise HTTPException(
            status_code=400, 
            detail=f"Infeasible Physics: Total customer demand is {total_demand} items, but your fleet can only carry {total_fleet_capacity}. Increase Fleet Size or Capacity."
        )

    # Convert UI slider (hours) directly into seconds
    strictness_seconds = req.sla_strictness_hours * 3600.0
    start_of_day = 32400.0 
    
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
        num_vehicles=int(req.num_vehicles)
    )

    # 1. Benchmark Execution: A* Baseline, GA, and QPSO
    results = {}
    
    # A* Greedy Constructive Baseline
    results['A*'] = solve_dynamic_heuristic(
        G, instance, method='astar', distance_weight=req.distance_weight
    )
    
    # Genetic Algorithm
    results['GA'] = solve_ga_baseline(
        G, instance, particles=req.particles, iterations=req.iterations,
        seed=req.traffic_seed, distance_weight=req.distance_weight
    )
    
    # Quantum PSO
    results['QPSO'] = solve_qpso(
        G, instance, particles=req.particles, iterations=req.iterations,
        seed=req.traffic_seed, distance_weight=req.distance_weight
    )

    # 2. Compute Indian Logistics Business ROI Impact
    qpso_dist_km = results['QPSO'].get('distance_m', 0) / 1000.0
    astar_dist_km = results['A*'].get('distance_m', 0) / 1000.0
    dist_saved_km = max(0.0, astar_dist_km - qpso_dist_km)
    
    # Logistics constant standards: 8 km/L fuel efficiency, ₹100/L diesel, 2.68 kg CO2/L
    liters_saved = dist_saved_km / 8.0
    rupees_saved = liters_saved * 100.0
    co2_saved_kg = liters_saved * 2.68

    # 3. GeoJSON Construction (Defaulting to QPSO optimal routes)
    primary_solution = results['QPSO']
    routes_geojson = {"type": "FeatureCollection", "features": []}
    palette = ["#D90429", "#0077B6", "#2A9D8F", "#F4A261", "#7209B7", "#FFB703"]
    schedule_data = []
    
    # Map nodes to customer objects for quick lookup
    cust_dict = {c.node: c for c in customer_objs}

    for v_idx, route in enumerate(primary_solution["routes"]):
        if len(route) <= 2 and route[0] == route[-1]:
            continue
            
        coords = []
        stops_labels = [node_to_id.get(n, str(n)) for n in route]
        current_time = 32400.0  # 9:00 AM
        stops_timeline = []

        for a, b in zip(route[:-1], route[1:]):
            path = primary_solution["paths"].get((a, b)) or primary_solution["paths"].get((b, a), [])
            if not path:
                path = [a, b] 
                
            seg_time = 0.0
            for u, v in zip(path[:-1], path[1:]):
                edge_data = G.get_edge_data(u, v)
                if edge_data is None:
                    continue
                attrs = min(edge_data.values(), key=lambda x: x.get("travel_time_s", float('inf'))) if G.is_multigraph() else edge_data
                seg_time += attrs.get("travel_time_s", 0)

            current_time += seg_time
            
            # FIX 2: Engine Synchronization (Idling)
            # If the truck arrives early, it MUST wait until the customer is ready
            if b in cust_dict:
                if current_time < cust_dict[b].ready_time:
                    current_time = cust_dict[b].ready_time

            stops_timeline.append({
                "stopId": node_to_id.get(b, str(b)),
                "arrivalTime_s": round(current_time, 1),
                "isDepot": b == instance.depot
            })
            
            # Add unloading service time
            if b in cust_dict:
                current_time += cust_dict[b].service_time
            else:
                current_time += 300.0  # Depot service time

            for n in path:
                coords.append([G.nodes[n]['x'], G.nodes[n]['y']])

        color = palette[v_idx % len(palette)]
        if len(coords) > 1:
            routes_geojson["features"].append({
                "type": "Feature",
                "properties": {
                    "vehicle": v_idx + 1,
                    "color": color,
                    "stops": stops_labels
                },
                "geometry": {"type": "LineString", "coordinates": coords}
            })

        schedule_data.append({
            "vehicle": v_idx + 1,
            "color": color,
            "stops": stops_labels,
            "timeline": stops_timeline,
            "totalTime_min": round(current_time / 60.0, 1)
        })

    return {
        "locations": {
            "depot": frontend_depot,
            "customers": frontend_customers
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
            "QPSO": {
                "score": round(results['QPSO']['score'], 2),
                "distance_km": round(qpso_dist_km, 2),
                "travel_time_min": round(results['QPSO']['travel_time_s'] / 60.0, 1),
                "history": results['QPSO']['history']
            },
            "GA": {
                "score": round(results['GA']['score'], 2),
                "distance_km": round(results['GA']['distance_m'] / 1000.0, 2),
                "travel_time_min": round(results['GA']['travel_time_s'] / 60.0, 1),
                "history": results['GA']['history']
            },
            "A*": {
                "score": round(results['A*']['score'], 2),
                "distance_km": round(astar_dist_km, 2),
                "travel_time_min": round(results['A*']['travel_time_s'] / 60.0, 1),
                "history": results['A*']['history']
            }
        },
        "routes": routes_geojson,
        "schedules": schedule_data
    }