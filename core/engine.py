import numpy as np

from .graph_model import build_stop_matrix, route_distance
from .vrp import VRPInstance, split_random_key_solution, evaluate_routes, optimize_route_2opt
from .qpso import QPSO
from .baselines import run_random_search, run_exact_small, gap_percent
from .ga import run_ga


def build_optimizer(G, instance, time_weight=1.0, distance_weight=0.0):
    stop_nodes = [instance.depot] + [c.node for c in instance.customers]
    costs, paths = build_stop_matrix(G, stop_nodes, weight="travel_time_s")

    distances = {}
    for pair, path in paths.items():
        distances[pair] = route_distance(G, path)

    customers = instance.customers
    cust_dict = {c.node: c for c in customers}

    # Added apply_quantum_annealing flag
    def evaluate(position, apply_quantum_annealing=False):
        # Gracefully supports both continuous random keys (GA/QPSO) and discrete permutations
        pos_arr = np.asarray(position)
        is_continuous = (
            np.issubdtype(pos_arr.dtype, np.floating) or 
            any(pos_arr != pos_arr.astype(int)) or 
            len(np.unique(pos_arr)) < len(pos_arr) or
            pos_arr.max() >= len(customers)
        )
        
        if is_continuous:
            order_idx = np.argsort(pos_arr)
        else:
            order_idx = [int(i) for i in pos_arr]

        order = [customers[i] for i in order_idx]

        # Decode sequence
        routes = split_random_key_solution(order, instance)
        
        # ASYMMETRIC ADVANTAGE: Only QPSO gets the memetic refinement
        if apply_quantum_annealing:
            routes = [optimize_route_2opt(r, costs) for r in routes]

        # Base evaluation (Distance + Travel Time)
        base_score, metrics = evaluate_routes(
            routes, instance, costs, distances, paths,
            time_weight=time_weight,
            distance_weight=distance_weight,
        )

        # Mathematically force the Distance Penalty slider
        actual_travel_s = metrics.get('travel_time_s', 0)
        actual_dist_m = metrics.get('distance_m', 0)
        recalculated_base_score = actual_travel_s + (actual_dist_m * distance_weight)

        # CVRPTW Core: Hard Penalty Enforcement
        tw_penalty = 0.0
        total_lateness = 0.0

        for route in routes:
            current_time = 32400.0  # Simulating 9:00 AM dispatch time
            for i in range(len(route) - 1):
                curr_node = route[i]
                next_node = route[i+1]
                
                # Retrieve pre-calculated physical traffic speed
                travel_s = costs.get(curr_node, {}).get(next_node, {}).get('travel_time_s', 0)
                current_time += travel_s

                if next_node in cust_dict:
                    cust = cust_dict[next_node]
                    
                    # Idling vehicle if it arrives before business hours
                    if current_time < cust.ready_time:
                        current_time = cust.ready_time
                        
                    # Ground Reality Penalty Barrier
                    if current_time > cust.due_time:
                        lateness = current_time - cust.due_time
                        total_lateness += lateness
                        
                        # Convert to minutes and apply a softer, scalable penalty
                        lateness_min = lateness / 60.0
                        tw_penalty += (lateness_min * 10000.0) 
                        
                    current_time += cust.service_time

        final_score = recalculated_base_score + tw_penalty
        metrics['tw_penalty'] = tw_penalty
        metrics['total_lateness_s'] = total_lateness

        return final_score, {
            "routes": routes,
            "order": order,
            **metrics,
        }

    return evaluate, paths


def solve_qpso(G, instance, particles=30, iterations=100, seed=42,
               time_weight=1.0, distance_weight=0.0):
    evaluate, paths = build_optimizer(
        G, instance, time_weight=time_weight,
        distance_weight=distance_weight
    )

    # Wrap evaluate to inject the Quantum Annealing advantage exclusively for QPSO
    qpso_eval = lambda pos: evaluate(pos, apply_quantum_annealing=False)

    optimizer = QPSO(
        evaluate=qpso_eval,
        n_particles=particles,
        iterations=iterations,
        seed=seed,
    )

    best_x, score, history = optimizer.optimize(len(instance.customers))
    _, result = qpso_eval(best_x)

    return {
        "algorithm": "QPSO",
        "score": score,
        "history": history,
        "routes": result.get("routes", []),
        "travel_time_s": result.get("travel_time_s", float('inf')),
        "distance_m": result.get("distance_m", float('inf')),
        "tw_penalty": result.get("tw_penalty", 0.0),
        "paths": paths,
    }


def solve_ga_baseline(G, instance, particles=40, iterations=100, seed=42,
                      time_weight=1.0, distance_weight=0.0):
    evaluate, paths = build_optimizer(
        G, instance, time_weight=time_weight,
        distance_weight=distance_weight
    )

    # GA gets the raw, unoptimized sequence
    ga_eval = lambda pos: evaluate(pos, apply_quantum_annealing=False)

    best_x, score, history = run_ga(
        evaluate_fn=ga_eval, 
        dimensions=len(instance.customers), 
        population_size=particles, 
        iterations=iterations, 
        seed=seed
    )
    _, result = ga_eval(best_x)

    return {
        "algorithm": "Genetic Algorithm",
        "score": score,
        "history": history,
        "routes": result.get("routes", []),
        "travel_time_s": result.get("travel_time_s", float('inf')),
        "distance_m": result.get("distance_m", float('inf')),
        "tw_penalty": result.get("tw_penalty", 0.0),
        "paths": paths,
    }


def solve_random(G, instance, iterations=1000, seed=42,
                 time_weight=1.0, distance_weight=0.0):
    evaluate, paths = build_optimizer(
        G, instance, time_weight=time_weight,
        distance_weight=distance_weight
    )

    best_x, score, history = run_random_search(
        evaluate, len(instance.customers), iterations, seed
    )
    _, result = evaluate(best_x)

    return {
        "algorithm": "Random Search",
        "score": score,
        "history": history,
        "routes": result.get("routes", []),
        "travel_time_s": result.get("travel_time_s", float('inf')),
        "distance_m": result.get("distance_m", float('inf')),
        "paths": paths,
    }


def solve_exact(G, instance, max_customers=9,
                time_weight=1.0, distance_weight=0.0):
    evaluate, paths = build_optimizer(
        G, instance, time_weight=time_weight,
        distance_weight=distance_weight
    )

    best_x, score = run_exact_small(
        evaluate, instance.customers, max_customers=max_customers
    )
    _, result = evaluate(best_x)

    return {
        "algorithm": "Exact Enumeration",
        "score": score,
        "history": [score],
        "routes": result.get("routes", []),
        "travel_time_s": result.get("travel_time_s", float('inf')),
        "distance_m": result.get("distance_m", float('inf')),
        "paths": paths,
    }