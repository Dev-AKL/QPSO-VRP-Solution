import numpy as np
import networkx as nx


def apply_traffic_scenario(G, seed=42, congestion_min=1.0, congestion_max=3.0):
    """Assign reproducible traffic multipliers and derived travel-time weights."""
    rng = np.random.default_rng(seed)
    H = G.copy()

    for u, v, k, data in H.edges(keys=True, data=True):
        length = float(data.get("length", 100.0))
        speed_kph = float(data.get("maxspeed", 30.0)) if isinstance(data.get("maxspeed"), (int, float)) else 30.0
        speed_mps = max(speed_kph / 3.6, 1.0)

        free_flow_seconds = length / speed_mps
        congestion = float(rng.uniform(congestion_min, congestion_max))

        data["distance_m"] = length
        data["free_flow_time_s"] = free_flow_seconds
        data["congestion"] = congestion
        data["travel_time_s"] = free_flow_seconds * congestion

    return H


def update_traffic(G, seed=None, low=1.0, high=3.0):
    """Update congestion while preserving the physical road network."""
    rng = np.random.default_rng(seed)

    for _, _, _, data in G.edges(keys=True, data=True):
        data["congestion"] = float(rng.uniform(low, high))
        data["travel_time_s"] = data.get("free_flow_time_s", 1.0) * data["congestion"]

    return G
