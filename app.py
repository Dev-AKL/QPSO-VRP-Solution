import time
import traceback
import networkx as nx
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

from core.baselines import gap_percent
from core.engine import solve_exact, solve_qpso, solve_random
from core.graph_model import load_osm_network
from core.traffic import apply_traffic_scenario
from core.vrp import Customer, VRPInstance

# UI logic modules
from core.heuristics import solve_dynamic_heuristic
from core.visualization import plot_map_view, plot_graph_view

# -----------------------------------------------------------------------------
# Configuration & Styling
# -----------------------------------------------------------------------------
st.set_page_config(page_title="QPSO Urban Routing Framework", page_icon="🗺️", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
    <style>
        .block-container { padding-top: 1.5rem; padding-bottom: 2rem; max-width: 95%; }
        .hero { padding-bottom: 1rem; border-bottom: 1px solid #e5e7eb; margin-bottom: 1.5rem; }
        .hero h1 { font-size: 2.2rem; margin-bottom: 0.2rem; letter-spacing: -0.02em; color: #111827; }
        .hero p { color: #4b5563; margin: 0; font-size: 1.05rem; }
        .metric-card { border: 1px solid #e5e7eb; border-radius: 6px; padding: 1.2rem; background: #ffffff; min-height: 95px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
        .metric-label { color: #6b7280; font-size: 0.75rem; text-transform: uppercase; font-weight: 600; letter-spacing: 0.05em; }
        .metric-value { font-size: 1.6rem; font-weight: 700; margin-top: 0.3rem; color: #111827; }
        .section-title { font-size: 1.25rem; font-weight: 600; margin: 1.5rem 0 1rem 0; color: #111827; }
        [data-testid="stSidebar"] .block-container { padding-top: 1.5rem; }
        div[role="radiogroup"] { gap: 15px; padding: 5px 0 10px 0; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
        <h1>Quantum-Inspired Urban Routing Framework</h1>
        <p>Dynamic modeling for large-scale CVRP (with varying demands) and Shortest-Path optimization.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# Core Helpers
# -----------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_network(place_name):
    return load_osm_network(place_name)

def choose_stops(G, n, seed=42, manual_depot=None, manual_customers=None):
    if manual_depot and manual_customers:
        all_nodes = set(G.nodes)
        depot = int(manual_depot)
        cust_list = [int(x.strip()) for x in manual_customers.split(",") if x.strip()]
        if depot not in all_nodes or any(c not in all_nodes for c in cust_list):
            st.warning("Manual Node IDs missing from graph. Falling back to random generation.")
        else:
            return depot, cust_list

    rng = np.random.default_rng(seed)
    components = nx.weakly_connected_components(G) if G.is_directed() else nx.connected_components(G)
    largest = max(components, key=len)
    nodes = np.asarray(list(largest))
    if len(nodes) < n + 1:
        raise ValueError(f"Network requires {n + 1} connected nodes. Found {len(nodes)}.")
    chosen = rng.choice(nodes, size=n + 1, replace=False)
    return int(chosen[0]), [int(x) for x in chosen[1:]]

# -----------------------------------------------------------------------------
# Sidebar Configuration
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("Routing Problem Type")
    mode = st.radio("Select Problem Model:", ["Fleet VRP (Capacity, Round-trip)", "Shortest Path (Point-to-Point)"])
    is_sp = "Shortest Path" in mode

    st.header("Graph Environment")
    place = st.text_input("OSM Location", "Manhattan, New York, USA")
    customers_n = st.slider("Number of Destinations", 1 if is_sp else 4, 30, 2 if is_sp else 10)
    
    if not is_sp:
        vehicles = st.slider("Fleet Vehicles", 1, 10, 3)
        capacity = st.number_input("Vehicle Capacity (Total Units)", min_value=1.0, value=25.0, step=1.0)
        time_windows = st.checkbox("Enforce Time-Window Constraints (VRPTW)", value=True)
    else:
        vehicles, capacity, time_windows = 1, 9999, False

    with st.expander("🛠 Advanced: Manual Node Mapping"):
        st.caption("Leave blank to randomly generate based on seed.")
        manual_depot = st.text_input("Origin/Depot Node ID", "")
        manual_customers = st.text_input("Destination Node IDs (Comma Separated)", "")

    traffic_seed = st.number_input("Traffic Scenario Seed", 0, 9999, 42)
    objective_distance = st.slider("Distance Objective Weight", 0.0, 1.0, 0.2)
    
    st.header("Algorithm Selection")
    run_qpso = st.checkbox("QPSO (Quantum-Inspired)", value=True)
    run_astar = st.checkbox("A* Heuristic", value=True)
    run_dijkstra = st.checkbox("Dijkstra Heuristic", value=True)
    run_nn = st.checkbox("Nearest Neighbor", value=not is_sp)
    run_exact = st.checkbox("Exact Enumeration (≤ 9)", value=(customers_n <= 9))

    st.header("QPSO Hyperparameters")
    particles = st.slider("Swarm Particles", 10, 100, 40)
    iterations = st.slider("Max Iterations", 20, 500, 100)

    run_btn = st.button("Execute Routing Experiment", type="primary", use_container_width=True)

# -----------------------------------------------------------------------------
# Execution Engine
# -----------------------------------------------------------------------------
if 'results' not in st.session_state and not run_btn:
    st.markdown("### Experiment Initialized")
    sc1, sc2, sc3, sc4 = st.columns(4)
    with sc1: st.markdown(f'<div class="metric-card"><div class="metric-label">Target Network</div><div class="metric-value">{place}</div></div>', unsafe_allow_html=True)
    with sc2: st.markdown(f'<div class="metric-card"><div class="metric-label">Mode Selected</div><div class="metric-value">{mode}</div></div>', unsafe_allow_html=True)
    with sc3: st.markdown(f'<div class="metric-card"><div class="metric-label">Time-Windows</div><div class="metric-value">{"Active" if time_windows else "Inactive"}</div></div>', unsafe_allow_html=True)
    with sc4: st.markdown(f'<div class="metric-card"><div class="metric-label">QPSO Evaluations</div><div class="metric-value">{particles * iterations}</div></div>', unsafe_allow_html=True)
    st.info("👈 **Configure parameters in the sidebar and click 'Execute Routing Experiment'.**")
    st.stop()

if run_btn:
    if customers_n > 9 and run_exact:
        st.sidebar.warning("Exact enumeration disabled (> 9 nodes).")
        run_exact = False

    results = {}
    start_total = time.perf_counter()

    try:
        with st.spinner("Initializing OSM Network & Traffic Metrics..."):
            G0 = get_network(place)
            G = apply_traffic_scenario(G0, seed=int(traffic_seed))
            
            for u, v, k, data in G.edges(keys=True, data=True):
                if 'distance_m' not in data: data['distance_m'] = float(data.get('length', 10.0))
                if 'travel_time_s' not in data: data['travel_time_s'] = data['distance_m'] / 8.33

            depot, customer_nodes = choose_stops(G, customers_n, seed=int(traffic_seed), manual_depot=manual_depot, manual_customers=manual_customers)

        rng = np.random.default_rng(int(traffic_seed))
        demands = rng.integers(1, 8, size=len(customer_nodes)) if not is_sp else np.ones(len(customer_nodes))
        customers_obj = [Customer(node=n, demand=float(d)) for n, d in zip(customer_nodes, demands)]
        instance = VRPInstance(depot=depot, customers=customers_obj, vehicle_capacity=float(capacity), num_vehicles=int(vehicles))

        if run_qpso:
            with st.spinner("Computing QPSO Global Topology..."):
                results['QPSO'] = solve_qpso(G, instance, particles=particles, iterations=iterations, seed=int(traffic_seed), distance_weight=objective_distance)
        if run_nn and not is_sp:
            with st.spinner("Computing Nearest Neighbor Baseline..."):
                results['NN'] = solve_dynamic_heuristic(G, instance, method='dijkstra', distance_weight=objective_distance, is_shortest_path_mode=is_sp)
                results['NN']['algorithm'] = "Nearest Neighbor"
        if run_astar:
            with st.spinner("Computing A* Heuristic Baseline..."):
                results['A*'] = solve_dynamic_heuristic(G, instance, method='astar', distance_weight=objective_distance, is_shortest_path_mode=is_sp)
        if run_dijkstra:
            with st.spinner("Computing Dijkstra Baseline..."):
                results['Dijkstra'] = solve_dynamic_heuristic(G, instance, method='dijkstra', distance_weight=objective_distance, is_shortest_path_mode=is_sp)
        if run_exact:
            with st.spinner("Solving Exact Exhaustive..."):
                results['Exact'] = solve_exact(G, instance, max_customers=9, distance_weight=objective_distance)

    except Exception as exc:
        st.error(f"🚨 Execution Error: `{type(exc).__name__}: {exc}`")
        with st.expander("🔍 View Detailed Error Traceback"): st.code(traceback.format_exc(), language="python")
        st.stop()

    st.session_state.update({'results': results, 'G': G, 'instance': instance, 'elapsed': time.perf_counter() - start_total, 'is_sp': is_sp})

# -----------------------------------------------------------------------------
# Results Dashboard
# -----------------------------------------------------------------------------
results = st.session_state['results']
G = st.session_state['G']
instance = st.session_state['instance']
elapsed = st.session_state['elapsed']
is_sp = st.session_state['is_sp']

st.markdown('<div class="section-title" style="margin-top:0;">Visualize Algorithm Output</div>', unsafe_allow_html=True)

c_toggle_1, c_toggle_2 = st.columns(2)
with c_toggle_1: selected_algo = st.radio("Selected Algorithm:", list(results.keys()), horizontal=True)
with c_toggle_2: view_mode = st.radio("Visualization Mode:", ["🗺️ Map View", "⏺️ Graph View"], horizontal=True)

primary_res = results[selected_algo]

c1, c2, c3, c4 = st.columns(4)
with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">{primary_res["algorithm"]} Score</div><div class="metric-value">{primary_res["score"]:.2f}</div></div>', unsafe_allow_html=True)
with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">{"Paths Computed" if is_sp else "Vehicles Utilized"}</div><div class="metric-value">{len([r for r in primary_res["routes"] if len(r)>2])} / {st.session_state.get("vehicles", vehicles)}</div></div>', unsafe_allow_html=True)
with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">Total Traversed Dist.</div><div class="metric-value">{primary_res["distance_m"]/1000:.2f} km</div></div>', unsafe_allow_html=True)
with c4: st.markdown(f'<div class="metric-card"><div class="metric-label">Total Execution Time</div><div class="metric-value">{elapsed:.2f} s</div></div>', unsafe_allow_html=True)

if "Map View" in view_mode:
    fig = plot_map_view(G, primary_res, instance, is_shortest_path=is_sp)
else:
    fig = plot_graph_view(G, primary_res, instance, is_shortest_path=is_sp)
    
st.pyplot(fig, use_container_width=True)
plt.close(fig)

col_a, col_b = st.columns([1, 1.2])
with col_a:
    st.markdown('<div class="section-title">Algorithmic Benchmarking</div>', unsafe_allow_html=True)
    comp_data = []
    exact_score = results.get('Exact', {}).get('score', None)
    
    for key, res in results.items():
        gap = gap_percent(res['score'], exact_score) if exact_score and key != 'Exact' else 0.0
        comp_data.append({"Methodology": res['algorithm'], "Cost": res['score'], "Time (min)": res['travel_time_s'] / 60, "Gap %": f"{gap:.1f}%" if exact_score and key != 'Exact' else ("-" if key == 'Exact' else "N/A")})
    st.dataframe(pd.DataFrame(comp_data).sort_values("Cost").style.format({"Cost": "{:.2f}", "Time (min)": "{:.1f}"}), use_container_width=True, hide_index=True)

with col_b:
    st.markdown('<div class="section-title">Optimization Convergence</div>', unsafe_allow_html=True)
    fig_conv, ax = plt.subplots(figsize=(8, 3.8))
    colors = {'QPSO': '#D90429', 'Random': '#F4A261', 'NN': '#2A9D8F', 'A*': '#0077B6', 'Dijkstra': '#7209B7', 'Exact': '#111827'}
    
    for key, res in results.items():
        color = colors.get(key, '#888888')
        if 'history' in res and key in ['QPSO', 'Random']:
            ax.plot(res["history"], color=color, linewidth=2.5, label=res['algorithm'])
        else:
            ax.axhline(y=res["score"], color=color, linestyle='--', linewidth=1.8, label=res['algorithm'])
            
    ax.set_xlabel("Iteration Step")
    ax.set_ylabel("Global Best Cost")
    ax.grid(True, alpha=0.3)
    ax.legend(bbox_to_anchor=(1.04, 1), loc="upper left", frameon=False, fontsize=9)
    fig_conv.tight_layout()
    st.pyplot(fig_conv)