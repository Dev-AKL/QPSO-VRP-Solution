import numpy as np


class QPSO:
    """
    Quantum-behaved Particle Swarm Optimization using random-key encoding.

    A particle is a real-valued vector. Sorting its values produces a
    permutation of customer indices. The permutation is decoded into VRP
    routes by the problem-specific decoder.
    """

    def __init__(self, evaluate, n_particles=30, iterations=100,
                 beta_max=1.0, beta_min=0.5, seed=42):
        self.evaluate = evaluate
        self.n_particles = n_particles
        self.iterations = iterations
        self.beta_max = beta_max
        self.beta_min = beta_min
        self.rng = np.random.default_rng(seed)

    def optimize(self, dimension):
        X = self.rng.uniform(0.0, 1.0, (self.n_particles, dimension))

        pbest = X.copy()
        pbest_score = np.array([self.evaluate(x)[0] for x in X])

        g_idx = int(np.argmin(pbest_score))
        gbest = pbest[g_idx].copy()
        gbest_score = float(pbest_score[g_idx])

        history = [gbest_score]

        for t in range(self.iterations):
            beta = self.beta_max - (
                self.beta_max - self.beta_min
            ) * (t / max(1, self.iterations - 1))

            mbest = np.mean(pbest, axis=0)

            for i in range(self.n_particles):
                phi = self.rng.random(dimension)
                attractor = phi * pbest[i] + (1.0 - phi) * gbest

                u = np.clip(self.rng.random(dimension), 1e-12, 1.0)
                direction = np.where(
                    self.rng.random(dimension) < 0.5, -1.0, 1.0
                )

                step = beta * np.abs(mbest - X[i]) * np.log(1.0 / u)
                X[i] = attractor + direction * step

                score, _ = self.evaluate(X[i])

                if score < pbest_score[i]:
                    pbest[i] = X[i].copy()
                    pbest_score[i] = score

                    if score < gbest_score:
                        gbest = X[i].copy()
                        gbest_score = float(score)

            history.append(gbest_score)

        return gbest, gbest_score, history
