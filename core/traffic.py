import pandas as pd
import networkx as nx
import os

# Global cache for O(1) hash map lookup
TRAFFIC_DATA_MAP = None

def load_traffic_data():
    global TRAFFIC_DATA_MAP
    if TRAFFIC_DATA_MAP is None:
        csv_path = os.path.join(os.path.dirname(__file__), "traffic_dataset.csv")
        if not os.path.exists(csv_path):
            raise FileNotFoundError("traffic_dataset.csv not found. Run generate_traffic_data.py first.")
        
        df = pd.read_csv(csv_path)
        
        # Build an O(1) lookup dictionary keyed by exact (u, v) node ID pairs
        TRAFFIC_DATA_MAP = {}
        for _, row in df.iterrows():
            u, v = int(row['u']), int(row['v'])
            TRAFFIC_DATA_MAP[(u, v)] = {
                'travel_time_offpeak_s': row['travel_time_offpeak_s'],
                'travel_time_rush_s': row['travel_time_rush_s'],
                'speed_offpeak_kph': row['speed_offpeak_kph'],
                'speed_rush_kph': row['speed_rush_kph']
            }

def apply_traffic_scenario(G, mode='off_peak'):
    """
    Maps the exact pre-calculated BPR traffic kinematics onto the live routing graph.
    """
    load_traffic_data()
    G_live = G.copy()
    
    is_multi = isinstance(G_live, (nx.MultiGraph, nx.MultiDiGraph))
    edge_iter = G_live.edges(keys=True, data=True) if is_multi else G_live.edges(data=True)
    
    for edge in edge_iter:
        if is_multi:
            u, v, k, data = edge
        else:
            u, v, data = edge
            
        length_m = float(data.get('length', 10.0))
        data['distance_m'] = length_m
        
        # Exact edge lookup from the BPR dataset
        traffic_attrs = TRAFFIC_DATA_MAP.get((u, v))
        
        if traffic_attrs:
            if mode == 'rush_hour':
                data['travel_time_s'] = traffic_attrs['travel_time_rush_s']
                data['speed_kmh'] = traffic_attrs['speed_rush_kph']
            else:
                data['travel_time_s'] = traffic_attrs['travel_time_offpeak_s']
                data['speed_kmh'] = traffic_attrs['speed_offpeak_kph']
        else:
            # Fallback for dynamic graph anomalies: Assume 25 km/h urban crawl
            speed_ms = 25.0 * (5.0 / 18.0)
            data['travel_time_s'] = length_m / speed_ms
            data['speed_kmh'] = 25.0
                
    return G_live