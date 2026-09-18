import math
from pathlib import Path
import unittest
from uuid import uuid4

import networkx as nx
from unittest.mock import patch

from core.time_dependent import (
    TimeIndexedMatrix,
    MatrixCell,
    build_time_indexed_matrix,
    _road_class_factor,
)
from core.vrp import Customer, VRPInstance, evaluate_routes
from core.tomtom_routing import fetch_live_matrix
from core.live_traffic_control import LiveTrafficGovernor, LiveTrafficPolicy, estimate_matrix_transactions


class TimeDependentRoutingTests(unittest.TestCase):
    def make_graph(self):
        graph = nx.MultiDiGraph()
        for node in (0, 1):
            graph.add_node(node, x=float(node), y=0.0)
        graph.add_edge(
            0, 1, distance_m=1000.0, length=1000.0,
            travel_time_s=100.0, highway="primary",
        )
        graph.add_edge(
            1, 0, distance_m=1000.0, length=1000.0,
            travel_time_s=100.0, highway="primary",
        )
        return graph

    def test_matrix_interpolates_travel_time_without_interpolating_geometry(self):
        path = (0, 1)
        matrix = TimeIndexedMatrix(
            {
                0.0: {(0, 1): MatrixCell(10.0, 10.0, 100.0, path)},
                100.0: {(0, 1): MatrixCell(20.0, 20.0, 100.0, path)},
            },
            bin_size_s=100.0,
        )
        cell = matrix.lookup(0, 1, 50.0)
        self.assertAlmostEqual(cell.travel_time_s, 15.0)
        self.assertEqual(cell.distance_m, 100.0)
        self.assertEqual(cell.path, path)

    def test_local_builder_creates_multiple_snapshots(self):
        matrix = build_time_indexed_matrix(
            self.make_graph(), [0, 1], start_s=32400.0,
            horizon_s=3600.0, bin_size_s=1800.0, seed=7,
        )
        self.assertEqual(len(matrix.bins), 3)
        self.assertTrue(all(math.isfinite(matrix.lookup(0, 1, t).travel_time_s) for t in matrix.bins))

    def test_road_factor_accepts_osm_multi_valued_highway_tag(self):
        self.assertEqual(_road_class_factor(["primary", "secondary"]), 1.05)
        self.assertEqual(_road_class_factor([]), 1.12)
        self.assertEqual(_road_class_factor(None), 1.12)

    def test_evaluator_uses_departure_time_for_each_leg(self):
        matrix = TimeIndexedMatrix(
            {
                0.0: {
                    (0, 1): MatrixCell(10.0, 10.0, 100.0, (0, 1)),
                    (1, 0): MatrixCell(10.0, 10.0, 100.0, (1, 0)),
                },
                10.0: {
                    (0, 1): MatrixCell(20.0, 20.0, 100.0, (0, 1)),
                    (1, 0): MatrixCell(30.0, 30.0, 100.0, (1, 0)),
                },
            },
            bin_size_s=10.0,
        )
        instance = VRPInstance(
            depot=0,
            customers=[Customer(1, 1, ready_time=0.0, due_time=1000.0, service_time=0.0)],
            vehicle_capacity=5.0,
            num_vehicles=1,
        )
        score, metrics = evaluate_routes(
            [[0, 1, 0]], instance,
            costs={(0, 1): 10.0, (1, 0): 10.0},
            distances={(0, 1): 100.0, (1, 0): 100.0},
            paths={(0, 1): [0, 1], (1, 0): [1, 0]},
            time_weight=1.0,
            dispatch_start_s=0.0,
            time_matrix=matrix,
        )
        self.assertEqual(score, 40.0)
        self.assertEqual(metrics["travel_time_s"], 40.0)

    def test_tomtom_live_response_is_normalized_for_all_algorithms(self):
        class Response:
            status_code = 200

            def json(self):
                return {
                    "data": [
                        {"originIndex": 0, "destinationIndex": 0,
                         "routeSummary": {"lengthInMeters": 0, "travelTimeInSeconds": 0}},
                        {"originIndex": 0, "destinationIndex": 1,
                         "routeSummary": {"lengthInMeters": 1200, "travelTimeInSeconds": 120,
                                           "trafficDelayInSeconds": 30}},
                        {"originIndex": 1, "destinationIndex": 0,
                         "routeSummary": {"lengthInMeters": 1200, "travelTimeInSeconds": 180,
                                           "trafficDelayInSeconds": 60}},
                        {"originIndex": 1, "destinationIndex": 1,
                         "routeSummary": {"lengthInMeters": 0, "travelTimeInSeconds": 0}},
                    ]
                }

        with patch("core.tomtom_routing.requests.post", return_value=Response()):
            result = fetch_live_matrix(
                self.make_graph(), [0, 1], api_key="test-key", dispatch_start_s=32400
            )

        cell = result.matrix.lookup(0, 1, 32400)
        self.assertEqual(cell.distance_m, 1200.0)
        self.assertEqual(cell.travel_time_s, 120.0)
        self.assertEqual(result.summary.successful_cells, 2)
        self.assertGreater(result.summary.average_congestion_ratio, 0.0)

    def test_live_governor_caches_and_counts_matrix_transactions(self):
        usage_path = Path("cache") / f"test_usage_{uuid4().hex}.json"
        try:
            governor = LiveTrafficGovernor(
                policy=LiveTrafficPolicy(
                    cache_ttl_s=600,
                    minimum_refresh_s=0,
                    max_requests_per_hour=5,
                    max_requests_per_day=20,
                    monthly_transaction_budget=100,
                ),
                usage_path=usage_path,
            )
            calls = []

            def fetch():
                calls.append(True)
                return {"matrix": "live"}

            first, first_decision = governor.get_or_fetch(
                "same-request", "127.0.0.1", 11, 11, fetch
            )
            second, second_decision = governor.get_or_fetch(
                "same-request", "127.0.0.1", 11, 11, fetch
            )
            self.assertEqual(estimate_matrix_transactions(11, 11), 55)
            self.assertEqual(len(calls), 1)
            self.assertFalse(first_decision.cache_hit)
            self.assertTrue(second_decision.cache_hit)
            self.assertEqual(first, second)
        finally:
            usage_path.unlink(missing_ok=True)

    def test_live_governor_falls_back_after_budget_is_exhausted(self):
        usage_path = Path("cache") / f"test_usage_{uuid4().hex}.json"
        try:
            governor = LiveTrafficGovernor(
                policy=LiveTrafficPolicy(monthly_transaction_budget=54),
                usage_path=usage_path,
            )
            value, decision = governor.get_or_fetch(
                "over-budget", "127.0.0.1", 11, 11, lambda: {"live": True}
            )
            self.assertIsNone(value)
            self.assertFalse(decision.allowed)
            self.assertEqual(decision.reason, "monthly_live_transaction_budget_exhausted")
        finally:
            usage_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
