import numpy as np
import networkx as nx

def fetch_live_traffic_api(G, seed=42):
    """
    STUB: For SIH Finale. 
    Simulates live unpredictable real-world bottlenecks 
    by heavily penalizing central nodes to mimic rush hour.
    """
    rng = np.random.default_rng(seed)
    G_live = G.copy()
    nodes = list(G_live.nodes)
    central_nodes = set(nodes[:len(nodes)//4]) # Simulate downtown
    
    # Safe handling for both MultiDiGraph and standard DiGraph
    is_multi = isinstance(G_live, (nx.MultiGraph, nx.MultiDiGraph))
    edge_iter = G_live.edges(keys=True, data=True) if is_multi else G_live.edges(data=True)
    
    for edge in edge_iter:
        if is_multi:
            u, v, k, data = edge
        else:
            u, v, data = edge
            
        if 'travel_time_s' not in data:
            data['travel_time_s'] = data.get('length', 10.0) / 8.33
            
        # Heavy congestion if passing through "downtown" nodes
        if u in central_nodes or v in central_nodes:
            data['travel_time_s'] *= rng.uniform(2.5, 5.0) 
        else:
            data['travel_time_s'] *= rng.uniform(1.0, 1.5)
            
    return G_live

def apply_traffic_scenario(G, seed=42, mode='simulated'):
    """
    Applies either reproducible seeded stochastic noise or live API data.
    """
    if mode == 'live':
        return fetch_live_traffic_api(G, seed=seed)
        
    G_sim = G.copy()
    rng = np.random.default_rng(seed)
    
    is_multi = isinstance(G_sim, (nx.MultiGraph, nx.MultiDiGraph))
    edge_iter = G_sim.edges(keys=True, data=True) if is_multi else G_sim.edges(data=True)
    
    for edge in edge_iter:
        if is_multi:
            u, v, k, data = edge
        else:
            u, v, data = edge
            
        base_time = data.get('length', 10.0) / 8.33
        multiplier = max(1.0, rng.normal(loc=1.2, scale=0.4))
        data['travel_time_s'] = base_time * multiplier
        
    return G_sim