"""TomTom live traffic matrix adapter.

The optimizer remains provider-independent.  This adapter only translates the
TomTom Matrix Routing v2 response into the same ``TimeIndexedMatrix`` format
used by the local simulator, so QPSO, GA, and A* consume identical live data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import os
from typing import Sequence

import requests

from .graph_model import add_objective_weights, build_stop_matrix
from .time_dependent import MatrixCell, TimeIndexedMatrix


TOMTOM_MATRIX_URL = "https://api.tomtom.com/routing/matrix/2"
DEFAULT_DISPATCH_START_S = 9 * 60 * 60


class TomTomRoutingError(RuntimeError):
    """Raised when a live TomTom matrix cannot be used safely."""


@dataclass(frozen=True)
class LiveTrafficSummary:
    provider: str
    requested_at: str
    departure_time: str
    successful_cells: int
    failed_cells: int
    total_cells: int
    average_speed_kmh: float | None
    average_traffic_delay_s: float | None
    average_congestion_ratio: float | None


@dataclass(frozen=True)
class LiveMatrixResult:
    matrix: TimeIndexedMatrix
    summary: LiveTrafficSummary


def _point(latitude: float, longitude: float) -> dict:
    if not -90 <= float(latitude) <= 90:
        raise ValueError("Latitude must be between -90 and 90")
    if not -180 <= float(longitude) <= 180:
        raise ValueError("Longitude must be between -180 and 180")
    return {"point": {"latitude": float(latitude), "longitude": float(longitude)}}


def _parse_datetime(value: datetime | str | None) -> str:
    if value is None:
        return "now"
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def fetch_live_matrix(
    graph,
    stop_nodes: Sequence,
    time_weight: float = 1.0,
    distance_weight: float = 0.0,
    dispatch_start_s: float = DEFAULT_DISPATCH_START_S,
    api_key: str | None = None,
    departure_time: datetime | str | None = None,
    timeout_s: float = 30.0,
    max_locations: int | None = None,
) -> LiveMatrixResult:
    """Fetch one live traffic matrix and normalize it for the optimizer.

    TomTom supplies traffic-aware travel time, distance, and delay.  Speed is
    derived as distance / travel time and congestion is represented by the
    delay ratio.  Local OSM shortest paths provide road-following geometry for
    the map; they are not used to replace TomTom's live optimization costs.
    """
    key = (api_key or os.getenv("TOMTOM_API_KEY", "")).strip()
    if not key:
        raise TomTomRoutingError(
            "TOMTOM_API_KEY is required when traffic_mode='live'."
        )
    if len(stop_nodes) < 2:
        raise ValueError("At least a depot and one delivery stop are required")
    if max_locations is None:
        max_locations = int(os.getenv("TOMTOM_MAX_LOCATIONS", "100"))
    if len(stop_nodes) > max_locations:
        raise TomTomRoutingError(
            f"Live TomTom mode supports at most {max_locations} selected locations "
            f"for this deployment; received {len(stop_nodes)}."
        )
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")

    locations = []
    for node in stop_nodes:
        try:
            locations.append(_point(graph.nodes[node]["y"], graph.nodes[node]["x"]))
        except KeyError as exc:
            raise TomTomRoutingError(
                f"Stop node {node} has no WGS84 coordinates"
            ) from exc

    depart_at = _parse_datetime(departure_time)
    payload = {
        "origins": locations,
        "destinations": locations,
        "options": {
            "departAt": depart_at,
            "traffic": "live",
            "travelMode": "truck",
            "routeType": "fastest",
        },
    }

    try:
        response = requests.post(
            TOMTOM_MATRIX_URL,
            params={"key": key},
            json=payload,
            timeout=float(timeout_s),
        )
    except requests.RequestException as exc:
        raise TomTomRoutingError(f"TomTom live matrix request failed: {exc}") from exc

    if response.status_code >= 400:
        # Never include the request URL because it contains the API key.
        raise TomTomRoutingError(
            f"TomTom live matrix returned HTTP {response.status_code}"
        )
    try:
        body = response.json()
        data = body["data"]
    except (ValueError, KeyError, TypeError) as exc:
        raise TomTomRoutingError("TomTom returned an invalid matrix response") from exc

    weighted_graph = add_objective_weights(
        graph,
        time_weight=time_weight,
        distance_weight=distance_weight,
    )
    _, geometry_paths = build_stop_matrix(
        weighted_graph,
        list(stop_nodes),
        weight="_routing_weight",
    )

    cells = {}
    speeds = []
    delays = []
    congestion_ratios = []
    successes = 0
    failures = 0
    for item in data:
        try:
            origin_index = int(item["originIndex"])
            destination_index = int(item["destinationIndex"])
        except (KeyError, TypeError, ValueError):
            failures += 1
            continue
        if not (0 <= origin_index < len(stop_nodes) and 0 <= destination_index < len(stop_nodes)):
            failures += 1
            continue

        summary = item.get("routeSummary")
        path = geometry_paths.get((stop_nodes[origin_index], stop_nodes[destination_index]), [])
        if not summary:
            failures += 1
            cells[(stop_nodes[origin_index], stop_nodes[destination_index])] = MatrixCell(
                math.inf, math.inf, math.inf, tuple(path)
            )
            continue

        try:
            distance_m = float(summary["lengthInMeters"])
            travel_time_s = float(summary["travelTimeInSeconds"])
            delay_s = float(summary.get("trafficDelayInSeconds", 0.0))
        except (KeyError, TypeError, ValueError):
            failures += 1
            continue
        if distance_m < 0 or travel_time_s <= 0 or not math.isfinite(travel_time_s):
            failures += 1
            continue

        cost = time_weight * travel_time_s + distance_weight * distance_m
        pair = (stop_nodes[origin_index], stop_nodes[destination_index])
        cells[pair] = MatrixCell(float(cost), travel_time_s, distance_m, tuple(path))
        successes += 1
        speed = distance_m / travel_time_s * 3.6
        speeds.append(speed)
        delays.append(max(0.0, delay_s))
        congestion_ratios.append(max(0.0, delay_s) / travel_time_s)

    expected_cells = len(stop_nodes) * len(stop_nodes)
    for index, origin in enumerate(stop_nodes):
        for destination_index, destination in enumerate(stop_nodes):
            pair = (origin, destination)
            if pair not in cells:
                if origin == destination:
                    cells[pair] = MatrixCell(0.0, 0.0, 0.0, (origin,))
                else:
                    cells[pair] = MatrixCell(math.inf, math.inf, math.inf, tuple())

    if successes == 0:
        raise TomTomRoutingError("TomTom returned no usable live matrix cells")

    matrix = TimeIndexedMatrix(
        {float(dispatch_start_s): cells},
        bin_size_s=1.0,
    )
    requested_at = datetime.now(timezone.utc).isoformat()
    summary = LiveTrafficSummary(
        provider="tomtom_live",
        requested_at=requested_at,
        departure_time=depart_at,
        successful_cells=successes,
        failed_cells=max(failures, expected_cells - successes),
        total_cells=expected_cells,
        average_speed_kmh=float(sum(speeds) / len(speeds)) if speeds else None,
        average_traffic_delay_s=float(sum(delays) / len(delays)) if delays else None,
        average_congestion_ratio=(
            float(sum(congestion_ratios) / len(congestion_ratios))
            if congestion_ratios else None
        ),
    )
    return LiveMatrixResult(matrix=matrix, summary=summary)
