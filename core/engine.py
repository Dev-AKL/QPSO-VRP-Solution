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

    def evaluate(position):
        # --- DUAL-COMPATIBLE DECODER ---
        # Gracefully supports both continuous random keys (GA) and discrete permutations (QPSO)
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
        # -------------------------------

        routes = split_random_key_solution(order, instance)
        routes = [optimize_route_2opt(r, costs) for r in routes]

        score, metrics = evaluate_routes(
            routes, instance, costs, distances, paths,
            time_weight=time_weight,
            distance_weight=distance_weight,
        )
        return score, {
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

    optimizer = QPSO(
        evaluate=evaluate,
        n_particles=particles,
        iterations=iterations,
        seed=seed,
    )

    best_x, score, history = optimizer.optimize(len(instance.customers))
    _, result = evaluate(best_x)

    return {
        "algorithm": "QPSO",
        "score": score,
        "history": history,
        "routes": result.get("routes", []),
        "travel_time_s": result.get("travel_time_s", float('inf')),
        "distance_m": result.get("distance_m", float('inf')),
        "paths": paths,
    }


def solve_ga_baseline(G, instance, particles=40, iterations=100, seed=42,
                      time_weight=1.0, distance_weight=0.0):
    evaluate, paths = build_optimizer(
        G, instance, time_weight=time_weight,
        distance_weight=distance_weight
    )

    best_x, score, history = run_ga(
        evaluate_fn=evaluate, 
        dimensions=len(instance.customers), 
        population_size=particles, 
        iterations=iterations, 
        seed=seed
    )
    _, result = evaluate(best_x)

    return {
        "algorithm": "Genetic Algorithm",
        "score": score,
        "history": history,
        "routes": result.get("routes", []),
        "travel_time_s": result.get("travel_time_s", float('inf')),
        "distance_m": result.get("distance_m", float('inf')),
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