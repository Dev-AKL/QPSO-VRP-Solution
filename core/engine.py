import math

import numpy as np

from .graph_model import add_objective_weights, build_stop_matrix, path_metrics
from .time_dependent import build_time_indexed_matrix
from .vrp import (
    VRPInstance,
    construct_feasible_order,
    evaluate_routes,
    optimize_route_2opt,
    split_random_key_solution,
)
from .qpso import QPSO
from .baselines import run_random_search, run_exact_small
from .ga import run_ga
from .aco import run_aco
from .pso import PSO


def _feasible_random_key(instance):
    order = construct_feasible_order(instance)
    if order is None:
        return None, None
    key = np.empty(len(order), dtype=float)
    denominator = max(1, len(order) - 1)
    for rank, customer_index in enumerate(order):
        key[customer_index] = rank / denominator
    return key, order


def _random_key_for_order(order):
    """Encode an integer customer-index order as stable random keys."""
    key = np.empty(len(order), dtype=float)
    denominator = max(1, len(order) - 1)
    for rank, customer_index in enumerate(order):
        key[int(customer_index)] = rank / denominator
    return key


def _intensify_qpso_solution(best_x, evaluate, max_evaluations=2500):
    """Use bounded swap search to intensify QPSO's discrete random-key result.

    QPSO explores continuous random-key space, while route order is discrete.
    A short deterministic swap neighbourhood closes that representation gap,
    especially when time-window penalties make two nearby permutations differ
    substantially.  The same evaluator and objective are used throughout.
    """
    if best_x is None:
        return best_x, math.inf, {"objective": math.inf}
    order = list(np.argsort(np.asarray(best_x), kind="stable"))
    candidate = _random_key_for_order(order)
    best_score, best_result = evaluate(candidate)
    evaluations = 1

    improved = True
    while improved and evaluations < max_evaluations:
        improved = False
        for left in range(len(order) - 1):
            if evaluations >= max_evaluations:
                break
            for right in range(left + 1, len(order)):
                trial_order = order.copy()
                trial_order[left], trial_order[right] = trial_order[right], trial_order[left]
                trial = _random_key_for_order(trial_order)
                trial_score, trial_result = evaluate(trial)
                evaluations += 1
                if trial_score < best_score:
                    order = trial_order
                    candidate = trial
                    best_score = trial_score
                    best_result = trial_result
                    improved = True
                    break
            if improved:
                break
    return candidate, best_score, best_result


def build_routing_data(G, instance, time_weight=1.0, distance_weight=0.0):
    """Build one request-scoped static stop matrix for all metaheuristics."""
    stop_nodes = [instance.depot] + [c.node for c in instance.customers]
    weighted_graph = add_objective_weights(
        G, time_weight=time_weight, distance_weight=distance_weight
    )
    costs, paths = build_stop_matrix(
        weighted_graph, stop_nodes, weight="_routing_weight"
    )
    distances = {}
    travel_times = {}
    for pair, path in paths.items():
        travel_time, distance = path_metrics(
            weighted_graph, path, weight="_routing_weight"
        )
        travel_times[pair] = travel_time
        distances[pair] = distance
    return costs, paths, distances, travel_times


def build_optimizer(
    G,
    instance,
    time_weight=1.0,
    distance_weight=0.0,
    seed=42,
    time_dependent=False,
    time_matrix=None,
    dispatch_start_s=32400.0,
    routing_data=None,
):
    """Build one route evaluator shared by all algorithms."""
    if time_weight < 0 or distance_weight < 0:
        raise ValueError("Objective weights must be non-negative.")

    stop_nodes = [instance.depot] + [c.node for c in instance.customers]
    if routing_data is None:
        routing_data = build_routing_data(
            G, instance, time_weight=time_weight, distance_weight=distance_weight
        )
    costs, paths, distances, travel_times = routing_data

    customers = instance.customers
    if time_matrix is None and time_dependent:
        time_matrix = build_time_indexed_matrix(
            G,
            stop_nodes,
            time_weight=time_weight,
            distance_weight=distance_weight,
            seed=seed,
            start_s=dispatch_start_s,
        )
    # QPSO's local 2-opt refinement must use the same provider matrix as the
    # final evaluator.  Otherwise live mode would silently refine with local
    # OSM baseline costs before scoring with TomTom costs.
    refinement_costs = costs
    if time_matrix is not None:
        refinement_costs = {
            pair: time_matrix.lookup(pair[0], pair[1], dispatch_start_s).cost
            for pair in costs
        }

    def evaluate(position, apply_quantum_annealing=False):
        if position is None:
            return math.inf, {"objective": math.inf}

        pos_arr = np.asarray(position)
        if pos_arr.ndim != 1 or len(pos_arr) != len(customers):
            return math.inf, {"objective": math.inf}
        try:
            if not np.all(np.isfinite(pos_arr.astype(float, copy=False))):
                return math.inf, {"objective": math.inf}
        except (TypeError, ValueError):
            return math.inf, {"objective": math.inf}

        # The GA and exact solver use integer permutations. QPSO/random search
        # use continuous random keys whose sorted order is the permutation.
        is_integer_permutation = (
            np.issubdtype(pos_arr.dtype, np.integer)
            and len(np.unique(pos_arr)) == len(pos_arr)
            and set(int(value) for value in pos_arr) == set(range(len(customers)))
        )
        if is_integer_permutation:
            order_idx = [int(value) for value in pos_arr]
        else:
            order_idx = np.argsort(pos_arr, kind="stable")

        try:
            order = [customers[int(index)] for index in order_idx]
        except (IndexError, TypeError, ValueError):
            return math.inf, {"objective": math.inf}

        routes = split_random_key_solution(order, instance)
        if apply_quantum_annealing and routes is not None:
            routes = [optimize_route_2opt(route, refinement_costs) for route in routes]

        score, metrics = evaluate_routes(
            routes,
            instance,
            costs,
            distances,
            paths,
            time_weight=time_weight,
            distance_weight=distance_weight,
            travel_times=travel_times,
            time_matrix=time_matrix,
            dispatch_start_s=dispatch_start_s,
        )
        return score, {
            "routes": routes or [],
            "order": order,
            **metrics,
        }

    return evaluate, paths


def _result_payload(algorithm, score, history, result, paths):
    return {
        "algorithm": algorithm,
        "score": score,
        "history": history,
        "routes": result.get("routes", []),
        "travel_time_s": result.get("travel_time_s", float("inf")),
        "distance_m": result.get("distance_m", float("inf")),
        "service_time_s": result.get("service_time_s", 0.0),
        "waiting_time_s": result.get("waiting_time_s", 0.0),
        "total_duration_s": result.get("total_duration_s", float("inf")),
        "tw_penalty": result.get("tw_penalty", 0.0),
        "total_lateness_s": result.get("total_lateness_s", 0.0),
        "leg_metrics": result.get("leg_metrics", []),
        # The evaluator may have selected a different road path for a leg
        # after the vehicle entered a new time bin.  Prefer those paths while
        # retaining the static matrix paths as a safe fallback.
        "paths": result.get("paths") or paths,
    }


def solve_qpso(
    G, instance, particles=30, iterations=100, seed=42,
    time_weight=1.0, distance_weight=0.0, time_matrix=None,
    dispatch_start_s=32400.0, routing_data=None,
):
    evaluate, paths = build_optimizer(
        G, instance, time_weight=time_weight, distance_weight=distance_weight,
        seed=seed,
        time_matrix=time_matrix,
        dispatch_start_s=dispatch_start_s,
        routing_data=routing_data,
    )
    initial_key, _ = _feasible_random_key(instance)
    qpso_eval = lambda pos: evaluate(pos, apply_quantum_annealing=True)
    optimizer = QPSO(
        evaluate=qpso_eval,
        n_particles=particles,
        iterations=iterations,
        seed=seed,
    )
    best_x, score, history = optimizer.optimize(
        len(instance.customers), initial_position=initial_key
    )
    best_x, score, result = _intensify_qpso_solution(
        best_x,
        qpso_eval,
        max_evaluations=min(2500, max(100, len(instance.customers) * 30)),
    )
    history.append(score)
    return _result_payload("QPSO", score, history, result, paths)


def solve_ga_baseline(
    G, instance, particles=40, iterations=100, seed=42,
    time_weight=1.0, distance_weight=0.0, time_matrix=None,
    dispatch_start_s=32400.0, routing_data=None,
):
    evaluate, paths = build_optimizer(
        G, instance, time_weight=time_weight, distance_weight=distance_weight,
        seed=seed,
        time_matrix=time_matrix,
        dispatch_start_s=dispatch_start_s,
        routing_data=routing_data,
    )
    _, initial_permutation = _feasible_random_key(instance)
    ga_eval = lambda pos: evaluate(pos, apply_quantum_annealing=False)
    best_x, score, history = run_ga(
        evaluate_fn=ga_eval,
        dimensions=len(instance.customers),
        population_size=particles,
        iterations=iterations,
        seed=seed,
        initial_permutation=initial_permutation,
    )
    _, result = ga_eval(best_x)
    return _result_payload("Genetic Algorithm", score, history, result, paths)


def solve_aco(
    G, instance, particles=40, iterations=100, seed=42,
    time_weight=1.0, distance_weight=0.0, time_matrix=None,
    dispatch_start_s=32400.0, routing_data=None,
):
    """Run ACO as a fourth benchmark using the shared VRP evaluator."""
    evaluate, paths = build_optimizer(
        G, instance, time_weight=time_weight, distance_weight=distance_weight,
        seed=seed,
        time_matrix=time_matrix,
        dispatch_start_s=dispatch_start_s,
        routing_data=routing_data,
    )
    _, initial_permutation = _feasible_random_key(instance)
    customers = [customer.node for customer in instance.customers]
    costs, _, _, _ = routing_data or build_routing_data(
        G, instance, time_weight=time_weight, distance_weight=distance_weight
    )
    transition_cost = np.asarray([
        [costs.get((customers[left], customers[right]), math.inf)
         for right in range(len(customers))]
        for left in range(len(customers))
    ], dtype=float)
    aco_eval = lambda pos: evaluate(pos, apply_quantum_annealing=False)
    best_x, score, history = run_aco(
        evaluate_fn=aco_eval,
        dimensions=len(customers),
        transition_cost=transition_cost,
        colony_size=particles,
        iterations=iterations,
        seed=seed,
        initial_permutation=initial_permutation,
    )
    _, result = aco_eval(best_x)
    return _result_payload("Ant Colony Optimization", score, history, result, paths)


def solve_pso(
    G, instance, particles=40, iterations=100, seed=42,
    time_weight=1.0, distance_weight=0.0, time_matrix=None,
    dispatch_start_s=32400.0, routing_data=None,
):
    """Run classical PSO as a benchmark using the shared route evaluator."""
    evaluate, paths = build_optimizer(
        G, instance, time_weight=time_weight, distance_weight=distance_weight,
        seed=seed,
        time_matrix=time_matrix,
        dispatch_start_s=dispatch_start_s,
        routing_data=routing_data,
    )
    initial_key, _ = _feasible_random_key(instance)
    pso_eval = lambda pos: evaluate(pos, apply_quantum_annealing=False)
    optimizer = PSO(
        evaluate=pso_eval,
        n_particles=particles,
        iterations=iterations,
        seed=seed,
    )
    best_x, score, history = optimizer.optimize(
        len(instance.customers), initial_position=initial_key
    )
    _, result = pso_eval(best_x)
    return _result_payload("Particle Swarm Optimization", score, history, result, paths)


def solve_random(
    G, instance, iterations=1000, seed=42,
    time_weight=1.0, distance_weight=0.0, time_matrix=None,
    dispatch_start_s=32400.0,
):
    evaluate, paths = build_optimizer(
        G, instance, time_weight=time_weight, distance_weight=distance_weight,
        seed=seed,
        time_matrix=time_matrix,
        dispatch_start_s=dispatch_start_s,
    )
    initial_key, _ = _feasible_random_key(instance)
    best_x, score, history = run_random_search(
        evaluate, len(instance.customers), iterations, seed, initial_x=initial_key
    )
    _, result = evaluate(best_x)
    return _result_payload("Random Search", score, history, result, paths)


def solve_exact(
    G, instance, max_customers=9,
    time_weight=1.0, distance_weight=0.0, time_matrix=None,
    dispatch_start_s=32400.0,
):
    evaluate, paths = build_optimizer(
        G, instance, time_weight=time_weight, distance_weight=distance_weight,
        time_matrix=time_matrix,
        dispatch_start_s=dispatch_start_s,
    )
    best_x, score = run_exact_small(
        evaluate, instance.customers, max_customers=max_customers
    )
    _, result = evaluate(best_x)
    return _result_payload("Exact Enumeration", score, [score], result, paths)
