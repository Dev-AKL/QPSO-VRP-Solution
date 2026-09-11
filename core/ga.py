import numpy as np

def run_ga(evaluate_fn, dimensions, population_size=40, iterations=100, mutation_rate=0.1, seed=42):
    """
    Continuous Genetic Algorithm using Arithmetic Crossover and Gaussian Mutation.
    Designed to operate in R^N to provide a mathematically fair baseline against QPSO.
    """
    rng = np.random.default_rng(seed)
    
    # Initialize continuous population in [0, 1]^N
    population = rng.uniform(0, 1, (population_size, dimensions))
    fitness_scores = np.full(population_size, np.inf)
    
    global_best_cost = np.inf
    global_best_position = None
    history = []
    
    for it in range(iterations):
        # 1. Evaluate Population
        for i in range(population_size):
            cost, _ = evaluate_fn(population[i])
            fitness_scores[i] = cost
            
            if cost < global_best_cost:
                global_best_cost = cost
                global_best_position = np.copy(population[i])
                
        history.append(global_best_cost)
        
        # 2. Tournament Selection
        new_population = np.zeros_like(population)
        for i in range(population_size):
            # Select 3 random individuals, pick the best
            competitors = rng.choice(population_size, 3, replace=False)
            winner = competitors[np.argmin(fitness_scores[competitors])]
            new_population[i] = population[winner]
            
        # 3. Arithmetic Crossover (Affine combination of pairs)
        for i in range(0, population_size, 2):
            if i + 1 < population_size:
                alpha = rng.uniform(0, 1, dimensions)
                parent1, parent2 = new_population[i], new_population[i+1]
                
                child1 = alpha * parent1 + (1 - alpha) * parent2
                child2 = (1 - alpha) * parent1 + alpha * parent2
                
                new_population[i] = child1
                new_population[i+1] = child2
                
        # 4. Gaussian Mutation
        mutation_mask = rng.random(new_population.shape) < mutation_rate
        gaussian_noise = rng.normal(0, 0.1, new_population.shape)
        new_population += mutation_mask * gaussian_noise
        
        # 5. Bound constraints and Elitism
        population = np.clip(new_population, 0, 1)
        population[0] = global_best_position # Inject the best known solution (Elitism)
        
    return global_best_position, global_best_cost, history