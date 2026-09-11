# Quantum-Inspired PSO to solve CVRPTW 

## Quantum-Inspired Particle Swarm Optimiser(QPSO) to solve  Capacitated Vehicle Routing Problem with Time Windows (CVRPTW)


## 1. Pipeline

```text
OpenStreetMap
     |
     v
Directed road graph
     |
     v
Traffic scenario
     |
     v
Shortest-path matrix between depot/customers
     |
     v
VRP random-key encoding
     |
     +------------------+
     |                  |
     v                  v
    QPSO          Classical baseline
     |                  |
     +---------+--------+
               |
               v
        Route evaluation
               |
               v
        Benchmark metrics
```

## 2. Mathematical model

Let:

- `V` = depot + customers
- `K` = vehicles
- `d_i` = demand of customer i
- `Q` = vehicle capacity
- `t_ij` = shortest-path travel time from stop i to j under current traffic
- `x_ijk` = 1 if vehicle k travels from i to j

The primary objective is:

```text
minimize  sum_k sum_i sum_j t_ij x_ijk
```

Capacity constraint:

```text
sum_i d_i y_ik <= Q       for every vehicle k
```

Every customer is served once:

```text
sum_k y_ik = 1            for every customer i
```

Each active vehicle starts and ends at the depot.

The implementation uses a permutation decoder rather than directly optimizing binary `x_ijk` variables. This is deliberate: QPSO operates in continuous space, so random-key encoding provides a clean bridge to the discrete VRP.

## 3. QPSO representation

A particle is:

```text
X = [0.71, 0.13, 0.94, 0.31, ...]
```

Sorting the values gives a customer permutation:

```text
[customer 2, customer 4, customer 1, customer 3, ...]
```

The permutation is then split into vehicle routes using the capacity constraint.

The QPSO update is based on:

```text
mbest = mean(personal_best_positions)

P = phi * pbest + (1 - phi) * gbest

X_new = P +/- beta * |mbest - X| * ln(1/u)
```

where `u` is uniformly sampled in `(0,1)`.

## 4. Traffic model

For every road edge:

```text
free_flow_time = length / speed
travel_time = free_flow_time * congestion_multiplier
```

The congestion multiplier is generated from a seeded stochastic scenario.

This gives reproducible simulated traffic. Later, `apply_traffic_scenario()` can be replaced with live traffic data without changing the optimizer
