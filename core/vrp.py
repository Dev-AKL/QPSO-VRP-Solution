from dataclasses import dataclass
from typing import List, Dict, Any
import math


@dataclass
class Customer:
    node: int
    demand: float = 1.0
    service_time_s: float = 0.0


@dataclass
class VRPInstance:
    depot: int
    customers: List[Customer]
    vehicle_capacity: float
    num_vehicles: int
    time_limit_s: float | None = None


def split_random_key_solution(order, instance: VRPInstance):
    """
    Decode a customer permutation into <= num_vehicles capacity-feasible routes.
    Each route starts and ends at the depot.
    """
    routes = []
    current = [instance.depot]
    load = 0.0

    for customer in order:
        if load + customer.demand <= instance.vehicle_capacity:
            current.append(customer.node)
            load += customer.demand
        else:
            current.append(instance.depot)
            routes.append(current)
            current = [instance.depot, customer.node]
            load = customer.demand

    current.append(instance.depot)
    routes.append(current)

    if len(routes) > instance.num_vehicles:
        return None

    while len(routes) < instance.num_vehicles:
        routes.append([instance.depot, instance.depot])

    return routes


def evaluate_routes(routes, instance, costs, distances, paths, 
                    time_weight=1.0, distance_weight=0.0,
                    congestion_weight=0.0):
    """
    Objective = weighted travel time + distance.
    Congestion is already reflected in travel_time_s; congestion_weight is
    retained as a hook for a separate congestion penalty.
    """
    if routes is None:
        return math.inf, {}

    total_time = 0.0
    total_distance = 0.0

    for route in routes:
        for u, v in zip(route[:-1], route[1:]):
            c = costs.get((u, v), math.inf)
            d = distances.get((u, v), math.inf)
            if not math.isfinite(c):
                return math.inf, {}

            total_time += c
            total_distance += d

    objective = (
        time_weight * total_time +
        distance_weight * total_distance +
        congestion_weight * 0.0
    )

    return objective, {
        "travel_time_s": total_time,
        "distance_m": total_distance,
        "objective": objective,
    }

# Append this function to the bottom of core/vrp.py

def optimize_route_2opt(route, costs):
    """
    Applies 2-opt local search to a single vehicle route to eliminate 
    overlapping edges and minimize local transit cost.
    """
    if len(route) < 4:
        return route
        
    best_route = list(route)
    improved = True
    
    while improved:
        improved = False
        for i in range(1, len(best_route) - 2):
            for j in range(i + 1, len(best_route)):
                if j - i == 1: continue 
                
                # Reverse sub-segment between i and j
                new_route = best_route[:i] + list(reversed(best_route[i:j])) + best_route[j:]
                
                # Quick cost evaluation of the sub-segments
                old_cost = sum(costs.get((best_route[k], best_route[k+1]), 0) for k in range(len(best_route)-1))
                new_cost = sum(costs.get((new_route[k], new_route[k+1]), 0) for k in range(len(new_route)-1))
                
                if new_cost < old_cost:
                    best_route = new_route
                    improved = True
                    break
            if improved:
                break
                
    return best_route
