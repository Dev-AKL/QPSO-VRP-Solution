"""Permutation-aware Ant Colony Optimization for benchmark comparisons.

The route evaluator remains the source of truth for feasibility and cost.  ACO
only proposes customer permutations, so it is directly comparable with GA and
QPSO on the same instance and shared routing matrix.
"""

import math

import numpy as np


def run_aco(
    evaluate_fn,
    dimensions,
    transition_cost=None,
    colony_size=40,
    iterations=100,
    evaporation_rate=0.25,
    alpha=1.0,
    beta=2.0,
    seed=42,
    initial_permutation=None,
):
    """Optimize a customer permutation with pheromone-guided construction."""
    if dimensions < 1:
        raise ValueError("ACO requires at least one dimension.")
    if colony_size < 3 or iterations < 1:
        raise ValueError("ACO requires at least three ants and one iteration.")
    if not 0 < evaporation_rate <= 1:
        raise ValueError("evaporation_rate must be in (0, 1].")
    if alpha < 0 or beta < 0:
        raise ValueError("ACO alpha and beta must be non-negative.")

    rng = np.random.default_rng(seed)
    pheromone = np.ones((dimensions, dimensions), dtype=float)
    costs = None
    if transition_cost is not None:
        costs = np.asarray(transition_cost, dtype=float)
        if costs.shape != (dimensions, dimensions):
            raise ValueError("transition_cost must be a square customer matrix.")
        costs = np.where(np.isfinite(costs) & (costs >= 0), costs, np.nan)

    initial = None
    if initial_permutation is not None:
        initial = np.asarray(initial_permutation, dtype=int)
        if sorted(initial.tolist()) != list(range(dimensions)):
            raise ValueError("initial_permutation must be a valid permutation.")

    global_best = None
    global_best_cost = math.inf
    history = []

    def construct_ant():
        remaining = list(range(dimensions))
        route = []
        current = None
        while remaining:
            if current is None or (costs is None and len(remaining) == dimensions):
                selected = int(rng.choice(remaining))
            else:
                candidate_indices = np.asarray(remaining, dtype=int)
                pheromone_weight = np.power(
                    np.maximum(pheromone[current, candidate_indices], 1e-12), alpha
                )
                if costs is None:
                    heuristic = np.ones(len(candidate_indices), dtype=float)
                else:
                    edge_cost = costs[current, candidate_indices]
                    heuristic = np.where(
                        np.isfinite(edge_cost), 1.0 / np.maximum(edge_cost, 1e-6), 0.0
                    )
                    heuristic = np.power(heuristic, beta)
                weights = pheromone_weight * heuristic
                if not np.all(np.isfinite(weights)) or weights.sum() <= 0:
                    selected = int(rng.choice(remaining))
                else:
                    selected = int(rng.choice(candidate_indices, p=weights / weights.sum()))
            route.append(selected)
            remaining.remove(selected)
            current = selected
        return np.asarray(route, dtype=int)

    for _ in range(iterations):
        ants = [initial.copy()] if initial is not None else []
        ants.extend(construct_ant() for _ in range(colony_size - len(ants)))
        scores = np.asarray([evaluate_fn(ant)[0] for ant in ants], dtype=float)
        best_index = int(np.argmin(scores))
        if global_best is None or scores[best_index] < global_best_cost:
            global_best = ants[best_index].copy()
            global_best_cost = float(scores[best_index])
        history.append(global_best_cost)

        pheromone *= 1.0 - evaporation_rate
        finite_scores = np.isfinite(scores)
        for ant, score in zip(ants, scores):
            if not finite_scores.any() or not math.isfinite(float(score)):
                continue
            deposit = 1.0 / (1.0 + max(float(score), 0.0))
            for left, right in zip(ant[:-1], ant[1:]):
                pheromone[left, right] += deposit
                pheromone[right, left] += deposit
        pheromone = np.clip(pheromone, 1e-6, 1e6)

    return global_best, global_best_cost, history
