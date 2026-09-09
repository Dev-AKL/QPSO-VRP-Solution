import osmnx as ox
import networkx as nx


def load_osm_network(place):
    """Download and project a drivable OSM street network."""
    G = ox.graph_from_place(place, network_type="drive", simplify=True)
    return ox.project_graph(G)


def nearest_node(G, x, y):
    return ox.distance.nearest_nodes(G, X=x, Y=y)


def edge_weighted_subgraph(G, nodes):
    return G.subgraph(nodes).copy()


def build_stop_matrix(G, stops, weight="travel_time_s"):
    """
    Compute shortest-path cost and path between every pair of stops.
    Works with OSMnx MultiDiGraph/MultiGraph.
    """
    costs = {}
    paths = {}

    for source in stops:
        lengths, route_paths = nx.single_source_dijkstra(G, source, weight=weight)
        for target in stops:
            if target == source:
                costs[(source, target)] = 0.0
                paths[(source, target)] = [source]
            elif target in lengths:
                costs[(source, target)] = float(lengths[target])
                paths[(source, target)] = route_paths[target]
            else:
                costs[(source, target)] = float("inf")
                paths[(source, target)] = []

    return costs, paths


def route_distance(G, path):
    total = 0.0
    for u, v in zip(path[:-1], path[1:]):
        data = G.get_edge_data(u, v)
        if not data:
            continue
        # For parallel edges choose the shortest physical distance.
        total += min(float(d.get("distance_m", d.get("length", 0.0))) for d in data.values())
    return total
