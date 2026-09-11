import networkx as nx

def solve_dynamic_heuristic(G, instance, method='dijkstra', time_weight=1.0, distance_weight=0.0):
    unvisited = [c.node for c in instance.customers]
    demands = {c.node: c.demand for c in instance.customers}
    routes, paths = [], {}
    total_time, total_dist, total_cost = 0.0, 0.0, 0.0

    def heuristic_func(n1, n2):
        if method == 'astar': 
            return ((G.nodes[n1]['x'] - G.nodes[n2]['x'])**2 + (G.nodes[n1]['y'] - G.nodes[n2]['y'])**2)**0.5
        return 0

    def get_dynamic_path(u, v):
        try:
            if method == 'astar':
                path = nx.astar_path(G, u, v, heuristic=heuristic_func, weight='travel_time_s')
            else:
                path = nx.dijkstra_path(G, u, v, weight='travel_time_s')
                
            t_s, d_m = 0.0, 0.0
            for a, b in zip(path[:-1], path[1:]):
                data = G.get_edge_data(a, b)
                attrs = min(data.values(), key=lambda x: x.get("travel_time_s", float('inf'))) if G.is_multigraph() else data
                t_s += attrs.get("travel_time_s", 0)
                d_m += attrs.get("distance_m", 0)
                
            cost = (t_s * time_weight) + (d_m * distance_weight)
            return path, t_s, d_m, cost
        except nx.NetworkXNoPath:
            return None, float('inf'), float('inf'), float('inf')
    
    while unvisited and len(routes) < instance.num_vehicles:
        route = [instance.depot]
        current_load = 0
        current_node = instance.depot
        
        while unvisited:
            best_next, best_cost, best_path, best_ts, best_dm = None, float('inf'), None, 0, 0
            for candidate in unvisited:
                if current_load + demands[candidate] <= instance.vehicle_capacity:
                    path, t_s, d_m, cost = get_dynamic_path(current_node, candidate)
                    if cost < best_cost:
                        best_cost, best_next, best_path, best_ts, best_dm = cost, candidate, path, t_s, d_m
                        
            if best_next is None: 
                break 
                
            route.append(best_next)
            paths[(current_node, best_next)] = best_path
            current_load += demands[best_next]
            unvisited.remove(best_next)
            total_time += best_ts
            total_dist += best_dm
            total_cost += best_cost
            current_node = best_next
            
        path, t_s, d_m, cost = get_dynamic_path(current_node, instance.depot)
        route.append(instance.depot)
        if path:
            paths[(current_node, instance.depot)] = path
            total_time += t_s
            total_dist += d_m
            total_cost += cost
                
        routes.append(route)

    # Penalty for failing to service customers within capacity/fleet constraints
    if unvisited:
        total_cost += len(unvisited) * 999999.0

    name = "A* Constructive" if method == 'astar' else "Dijkstra Constructive"
    return {
        "algorithm": name, 
        "score": total_cost, 
        "travel_time_s": total_time, 
        "distance_m": total_dist, 
        "routes": routes, 
        "paths": paths, 
        "history": [total_cost] * 100
    }