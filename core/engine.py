import numpy as np

from .graph_model import build_stop_matrix, route_distance
from .vrp import VRPInstance, split_random_key_solution, evaluate_routes
from .qpso import QPSO
from .baselines import run_random_search, run_exact_small, gap_percent


def build_optimizer(G, instance, time_weight=1.0, distance_weight=0.0):
    stop_nodes = [instance.depot] + [c.node for c in instance.customers]

    costs, paths = build_stop_matrix(G, stop_nodes, weight="travel_time_s")

    distances = {}
    for pair, path in paths.items():
        distances[pair] = route_distance(G, path)

    customers = instance.customers

    def evaluate(position):
        order_idx = np.argsort(position)
        order = [customers[i] for i in order_idx]

        routes = split_random_key_solution(order, instance)
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
        "routes": result["routes"],
        "travel_time_s": result["travel_time_s"],
        "distance_m": result["distance_m"],
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
        "routes": result["routes"],
        "travel_time_s": result["travel_time_s"],
        "distance_m": result["distance_m"],
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
        "routes": result["routes"],
        "travel_time_s": result["travel_time_s"],
        "distance_m": result["distance_m"],
        "paths": paths,
    }
