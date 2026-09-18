"""Deterministic, local time-dependent routing primitives.

This module deliberately does not call a third-party routing API.  It builds a
small set of traffic snapshots from the project's OSM graph, caches the
shortest-path matrix for each snapshot, and interpolates travel time between
neighbouring snapshots during route evaluation.

TomTom can later be used to calibrate the profile factors, but the optimizer
never needs to make a network request while evaluating a particle or genome.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import networkx as nx
import numpy as np

from .graph_model import add_objective_weights, build_stop_matrix, path_metrics


DEFAULT_DISPATCH_START_S = 9 * 60 * 60
DEFAULT_BIN_SIZE_S = 30 * 60
DEFAULT_HORIZON_S = 24 * 60 * 60


@dataclass(frozen=True)
class MatrixCell:
    cost: float
    travel_time_s: float
    distance_m: float
    path: tuple[int, ...]


def _highway_class(value) -> str:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else "unknown"
    return str(value or "unknown").lower()


def _time_profile_factor(seconds_from_midnight: float) -> float:
    """Return a smooth weekday-like congestion profile.

    The profile is intentionally deterministic and conservative.  It models
    two commuting peaks and a smaller midday increase.  Values are factors on
    free-flow travel time, not on physical distance.
    """
    hour = (seconds_from_midnight % (24 * 3600)) / 3600.0
    morning = math.exp(-0.5 * ((hour - 8.0) / 1.35) ** 2)
    evening = math.exp(-0.5 * ((hour - 18.0) / 1.65) ** 2)
    midday = math.exp(-0.5 * ((hour - 13.0) / 2.5) ** 2)
    return 1.0 + 0.55 * morning + 0.70 * evening + 0.10 * midday


def _road_class_factor(highway) -> float:
    """Return a road factor for OSM's scalar or multi-valued highway tag.

    OSMnx commonly represents tags such as ``highway=primary`` as a string,
    but some edges contain a list of classifications.  Normalize that value
    before using it as a dictionary key; otherwise a valid OSM edge raises
    ``TypeError: unhashable type: 'list'`` during matrix construction.
    """
    highway = _highway_class(highway)
    return {
        "motorway": 0.90,
        "motorway_link": 0.96,
        "trunk": 0.96,
        "trunk_link": 1.00,
        "primary": 1.05,
        "primary_link": 1.08,
        "secondary": 1.12,
        "secondary_link": 1.15,
        "tertiary": 1.18,
        "tertiary_link": 1.20,
        "residential": 1.10,
        "living_street": 1.18,
        "service": 1.25,
    }.get(highway, 1.12)


class TimeIndexedMatrix:
    """A collection of stop matrices indexed by departure time."""

    def __init__(self, snapshots: dict[float, dict], bin_size_s: float):
        if not snapshots:
            raise ValueError("At least one time-dependent matrix snapshot is required")
        self.snapshots = dict(sorted(snapshots.items()))
        self.bin_size_s = float(bin_size_s)
        self.bins = tuple(self.snapshots)

    def _bracket(self, departure_s: float) -> tuple[float, float, float]:
        value = float(departure_s)
        if value <= self.bins[0]:
            return self.bins[0], self.bins[0], 0.0
        if value >= self.bins[-1]:
            return self.bins[-1], self.bins[-1], 0.0

        right_index = int(np.searchsorted(self.bins, value, side="right"))
        left = self.bins[right_index - 1]
        right = self.bins[right_index]
        fraction = (value - left) / max(1.0, right - left)
        return left, right, fraction

    def lookup(self, origin, destination, departure_s: float) -> MatrixCell:
        left, right, fraction = self._bracket(departure_s)
        left_cell = self.snapshots[left].get((origin, destination))
        right_cell = self.snapshots[right].get((origin, destination))
        if left_cell is None or right_cell is None:
            return MatrixCell(math.inf, math.inf, math.inf, tuple())

        if not all(
            math.isfinite(float(value))
            for value in (left_cell.cost, left_cell.travel_time_s, left_cell.distance_m,
                          right_cell.cost, right_cell.travel_time_s, right_cell.distance_m)
        ):
            return MatrixCell(math.inf, math.inf, math.inf, tuple())

        travel_time = left_cell.travel_time_s + fraction * (
            right_cell.travel_time_s - left_cell.travel_time_s
        )
        distance = left_cell.distance_m + fraction * (
            right_cell.distance_m - left_cell.distance_m
        )
        cost = left_cell.cost + fraction * (right_cell.cost - left_cell.cost)
        # Geometry cannot be interpolated.  Use the snapshot at the actual
        # departure side of the interval, which keeps it road-following.
        path = left_cell.path if fraction < 0.5 else right_cell.path
        return MatrixCell(float(cost), float(travel_time), float(distance), path)

    def snapshot(self, departure_s: float) -> dict:
        left, right, fraction = self._bracket(departure_s)
        return self.snapshots[left if fraction < 0.5 else right]


def build_time_indexed_matrix(
    graph,
    stops: Iterable,
    time_weight: float = 1.0,
    distance_weight: float = 0.0,
    start_s: float = DEFAULT_DISPATCH_START_S,
    horizon_s: float = DEFAULT_HORIZON_S,
    bin_size_s: float = DEFAULT_BIN_SIZE_S,
    seed: int = 42,
) -> TimeIndexedMatrix:
    """Build local matrices for a deterministic sequence of traffic periods.

    Edge distance never changes.  Each snapshot changes edge travel time,
    after which NetworkX recomputes shortest paths.  A stable per-edge factor
    prevents random noise from changing between optimizer evaluations.
    """
    if time_weight < 0 or distance_weight < 0:
        raise ValueError("Objective weights must be non-negative")
    if bin_size_s <= 0 or horizon_s < 0:
        raise ValueError("Time-bin size must be positive and horizon must be non-negative")

    stop_list = list(stops)
    rng = np.random.default_rng(seed)
    edge_noise = {}
    is_multi = graph.is_multigraph()
    edge_iter = graph.edges(keys=True) if is_multi else graph.edges()
    for edge in edge_iter:
        edge_noise[edge] = float(np.clip(rng.normal(1.0, 0.035), 0.92, 1.10))

    snapshots = {}
    count = int(math.floor(horizon_s / bin_size_s)) + 1
    for index in range(count):
        departure_s = float(start_s + index * bin_size_s)
        factor_at_time = _time_profile_factor(departure_s)
        weighted = graph.copy()

        edges = (
            weighted.edges(keys=True, data=True)
            if is_multi else weighted.edges(data=True)
        )
        for edge in edges:
            if is_multi:
                u, v, key, data = edge
                noise = edge_noise.get((u, v, key), 1.0)
            else:
                u, v, data = edge
                noise = edge_noise.get((u, v), 1.0)

            distance_m = float(data.get("distance_m", data.get("length", 0.0)))
            existing_time = float(data.get("travel_time_s", 0.0))
            if distance_m <= 0 or existing_time <= 0 or not math.isfinite(existing_time):
                existing_time = distance_m / 8.33 if distance_m > 0 else math.inf
            road_factor = _road_class_factor(data.get("highway"))
            # The reference graph is the local traffic snapshot supplied by
            # the API. Normalize the class factors around 1.0 so the profile
            # changes travel time without changing the road distance.
            data["distance_m"] = distance_m
            data["travel_time_s"] = existing_time * factor_at_time * road_factor * noise / 1.12
            data["speed_kmh"] = (
                distance_m / data["travel_time_s"] * 3.6
                if data["travel_time_s"] > 0 and math.isfinite(data["travel_time_s"])
                else 0.0
            )

        weighted = add_objective_weights(
            weighted,
            time_weight=time_weight,
            distance_weight=distance_weight,
        )
        costs, paths = build_stop_matrix(weighted, stop_list, weight="_routing_weight")
        cells = {}
        for pair, path in paths.items():
            travel_time, distance = path_metrics(weighted, path, weight="_routing_weight")
            cells[pair] = MatrixCell(
                cost=float(costs.get(pair, math.inf)),
                travel_time_s=float(travel_time),
                distance_m=float(distance),
                path=tuple(path),
            )
        snapshots[departure_s] = cells

    return TimeIndexedMatrix(snapshots, bin_size_s=bin_size_s)
