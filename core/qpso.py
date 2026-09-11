import numpy as np

class QPSO:
    def __init__(self, evaluate, n_particles=40, iterations=100, seed=42):
        self.evaluate = evaluate
        self.n_particles = n_particles
        self.iterations = iterations
        self.rng = np.random.default_rng(seed)
        
    def optimize(self, dimensions):
        # Initialize particles in continuous random-key space [0, 1]^N (matching GA)
        particles = self.rng.uniform(0, 1, (self.n_particles, dimensions))
        pbest = particles.copy()
        
        pbest_scores = np.array([self.evaluate(p)[0] for p in particles])
        gbest_idx = np.argmin(pbest_scores)
        gbest = pbest[gbest_idx].copy()
        gbest_score = pbest_scores[gbest_idx]
        
        history = [gbest_score]
        
        for it in range(self.iterations):
            # NON-LINEAR DECAY: Smoothly curves exploration to exploitation, dodging premature local optima
            alpha = 1.0 - 0.5 * (it / self.iterations) ** 2
            
            # Compute Mean Best Position (mbest) of the swarm
            mbest = np.mean(pbest, axis=0)
            
            for i in range(self.n_particles):
                # Quantum attractor: stochastic blend of personal and global best
                phi = self.rng.uniform(0, 1, dimensions)
                p = phi * pbest[i] + (1 - phi) * gbest
                
                # Quantum potential well position update
                u = self.rng.uniform(0, 1, dimensions)
                sign = np.where(self.rng.random(dimensions) > 0.5, 1, -1)
                particles[i] = p + sign * alpha * np.abs(mbest - particles[i]) * np.log(1.0 / u)
                
                # Boundary clamping to [0, 1]
                particles[i] = np.clip(particles[i], 0.0, 1.0)
                
                # Evaluate fitness
                score, _ = self.evaluate(particles[i])
                if score < pbest_scores[i]:
                    pbest[i] = particles[i].copy()
                    pbest_scores[i] = score
                    if score < gbest_score:
                        gbest = particles[i].copy()
                        gbest_score = score
                        
            history.append(gbest_score)
            
        return gbest, gbest_score, history