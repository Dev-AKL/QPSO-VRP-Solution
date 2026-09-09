## Randomness Documentation

They all originate from a **single master seed** (the `traffic_seed` in the UI), but they absolutely

Using a single master seed is standard scientific practice for Operations Research. It ensures "Global Reproducibility"—if a judge runs your app with Seed 42, they will see the exact same customers, the exact same traffic jams, and the exact same QPSO convergence curve you saw.

Here is how the randomness is partitioned under the hood, and how you can swap the distributions to model different real-world scenarios.

**1. Customer & Depot Locations**

* **Current Distribution:** Uniform Random Choice without replacement.
* **Mechanism:** `rng.choice(nodes, size=n+1, replace=False)`. Every intersection in the city has an equal $1/N$ probability of being picked.
* **How to Change It:** If you want to model a dense downtown delivery zone with a few sparse suburban outliers, you would cluster them using a 2D Gaussian (Normal) distribution around a specific coordinate, snapping the results to the nearest OSM graph nodes using `ox.distance.nearest_nodes()`.

**2. Customer Demand**

* **Current Distribution:** Discrete Uniform Distribution.
* **Mechanism:** `rng.integers(1, 8, size=N)`. A customer is equally likely to order 1, 2, 3, 4, 5, 6, or 7 items.
* **How to Change It:** Real-world logistics rarely follow a uniform distribution. Most people order small packages, and a few order massive freight. You should change this to a **Poisson Distribution** (standard for arrival/demand modeling):
```python
# lambda (lam) is the average demand.
demands = rng.poisson(lam=3.0, size=len(customer_nodes))
# Ensure no zero-demand customers
demands = np.clip(demands, 1, capacity) 

```



**3. Traffic Congestion Multipliers**

* **Current Distribution:** Continuous Uniform Distribution.
* **Mechanism:** Typically `rng.uniform(1.0, 3.0)`. A road is equally likely to be empty (1.0x time) or gridlocked (3.0x time).
* **How to Change It:** Real traffic follows a **Lognormal** or **Gaussian** distribution with a long tail (most roads are fine, a few are completely jammed). Inside your `apply_traffic_scenario` function, swap it to:
```python
# Mean congestion of 1.2x, with some variance. Clipped to ensure it never goes below 1.0 (speed of light).
raw_congestion = rng.normal(loc=1.2, scale=0.4)
multiplier = max(1.0, raw_congestion)

```



**4. QPSO Wavefunction (Algorithm Randomness)**

* **Current Distribution:** Continuous Uniform $U(0,1)$.
* **Mechanism:** `u = rng.uniform(0.0, 1.0)` and `phi = rng.uniform(0.0, 1.0)`.
* **How to Change It:** **Do not change this.** The mathematical proof for QPSO's global convergence relies entirely on uniformly sampling the inverse cumulative distribution function of the Laplace distribution. Changing `u` or `phi` to a Gaussian will break the quantum delta-potential well mechanics and destroy the algorithm's ability to search the space properly.