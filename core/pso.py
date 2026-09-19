"""Standard Particle Swarm Optimization in random-key permutation space."""

import numpy as np


class PSO:
    """Classical PSO with inertia, cognitive, and social components.

    Each continuous position is decoded by the shared VRP evaluator through
    its sorted random keys. This keeps PSO comparable with QPSO while making
    the update rule conventional rather than quantum-inspired.
    """

    def __init__(
        self,
        evaluate,
        n_particles=40,
        iterations=100,
        seed=42,
        inertia_start=0.90,
        inertia_end=0.40,
        cognitive=1.7,
        social=1.7,
    ):
        if n_particles < 3 or iterations < 1:
            raise ValueError("PSO requires at least three particles and one iteration.")
        if inertia_start < 0 or inertia_end < 0 or cognitive < 0 or social < 0:
            raise ValueError("PSO coefficients must be non-negative.")
        self.evaluate = evaluate
        self.n_particles = n_particles
        self.iterations = iterations
        self.rng = np.random.default_rng(seed)
        self.inertia_start = inertia_start
        self.inertia_end = inertia_end
        self.cognitive = cognitive
        self.social = social

    def optimize(self, dimensions, initial_position=None):
        if dimensions < 1:
            raise ValueError("PSO requires at least one dimension.")
        positions = self.rng.uniform(0.0, 1.0, (self.n_particles, dimensions))
        velocities = self.rng.uniform(-0.2, 0.2, (self.n_particles, dimensions))
        if initial_position is not None:
            initial_position = np.asarray(initial_position, dtype=float)
            if initial_position.shape != (dimensions,):
                raise ValueError("initial_position has the wrong dimension.")
            positions[0] = np.clip(initial_position, 0.0, 1.0)

        scores = np.asarray([self.evaluate(position)[0] for position in positions])
        personal_best_positions = positions.copy()
        personal_best_scores = scores.copy()
        global_index = int(np.argmin(personal_best_scores))
        global_best_position = personal_best_positions[global_index].copy()
        global_best_score = float(personal_best_scores[global_index])
        history = [global_best_score]

        for iteration in range(self.iterations):
            progress = iteration / max(1, self.iterations - 1)
            inertia = self.inertia_start + (self.inertia_end - self.inertia_start) * progress
            r1 = self.rng.random((self.n_particles, dimensions))
            r2 = self.rng.random((self.n_particles, dimensions))
            velocities = (
                inertia * velocities
                + self.cognitive * r1 * (personal_best_positions - positions)
                + self.social * r2 * (global_best_position - positions)
            )
            positions = np.clip(positions + velocities, 0.0, 1.0)

            scores = np.asarray([self.evaluate(position)[0] for position in positions])
            improved = scores < personal_best_scores
            personal_best_positions[improved] = positions[improved]
            personal_best_scores[improved] = scores[improved]
            iteration_best = int(np.argmin(personal_best_scores))
            if personal_best_scores[iteration_best] < global_best_score:
                global_best_position = personal_best_positions[iteration_best].copy()
                global_best_score = float(personal_best_scores[iteration_best])
            history.append(global_best_score)

        return global_best_position, global_best_score, history
