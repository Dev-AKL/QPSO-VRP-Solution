"""Optional TomTom route sampling for calibration and validation.

This module is intentionally outside the optimization loop.  The local
time-dependent matrix remains the source used by QPSO, GA, and A*.  TomTom is
queried only when an operator explicitly requests a validation sample or a
calibration observation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from statistics import median
from typing import Iterable, Sequence

import requests


TOMTOM_ROUTE_URL = "https://api.tomtom.com/routing/1/calculateRoute"


@dataclass(frozen=True)
class RouteObservation:
    distance_m: float
    travel_time_s: float
    traffic_delay_s: float
    departure_time: str | None


@dataclass(frozen=True)
class CalibrationResult:
    multiplier: float
    samples: int
    median_absolute_error_s: float


class TomTomValidationError(RuntimeError):
    """Raised when a validation request cannot be completed safely."""


def _format_location(latitude: float, longitude: float) -> str:
    if not -90 <= float(latitude) <= 90:
        raise ValueError("Latitude must be between -90 and 90")
    if not -180 <= float(longitude) <= 180:
        raise ValueError("Longitude must be between -180 and 180")
    return f"{float(latitude):.7f},{float(longitude):.7f}"


class TomTomValidator:
    """Small server-side client for explicit route validation samples."""

    def __init__(self, api_key: str | None = None, timeout_s: float = 15.0):
        self.api_key = api_key or os.getenv("TOMTOM_API_KEY", "").strip()
        self.timeout_s = float(timeout_s)
        if not self.api_key:
            raise TomTomValidationError(
                "TOMTOM_API_KEY is not configured; validation is optional and remains disabled."
            )
        if self.timeout_s <= 0:
            raise ValueError("timeout_s must be positive")

    def calculate_route(
        self,
        locations: Sequence[tuple[float, float]],
        departure_time: datetime | str | None = None,
        traffic: bool = True,
        travel_mode: str = "truck",
    ) -> RouteObservation:
        if len(locations) < 2:
            raise ValueError("At least an origin and destination are required")

        route_locations = ":".join(
            _format_location(latitude, longitude)
            for latitude, longitude in locations
        )
        params = {
            "key": self.api_key,
            "traffic": str(bool(traffic)).lower(),
            "travelMode": travel_mode,
            "routeType": "fastest",
            "computeTravelTimeFor": "all",
        }
        if departure_time is not None:
            value = departure_time.isoformat() if isinstance(departure_time, datetime) else str(departure_time)
            params["departAt"] = value

        try:
            response = requests.get(
                f"{TOMTOM_ROUTE_URL}/{route_locations}/json",
                params=params,
                timeout=self.timeout_s,
            )
        except requests.RequestException as exc:
            raise TomTomValidationError(f"TomTom validation request failed: {exc}") from exc

        if response.status_code >= 400:
            raise TomTomValidationError(
                f"TomTom validation returned HTTP {response.status_code}"
            )
        try:
            payload = response.json()
            summary = payload["routes"][0]["summary"]
            return RouteObservation(
                distance_m=float(summary["lengthInMeters"]),
                travel_time_s=float(summary["travelTimeInSeconds"]),
                traffic_delay_s=float(summary.get("trafficDelayInSeconds", 0.0)),
                departure_time=summary.get("departureTime"),
            )
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise TomTomValidationError(
                "TomTom returned an unexpected route response"
            ) from exc


def compare_prediction(
    predicted_time_s: float,
    observed: RouteObservation,
) -> dict[str, float]:
    """Return transparent error metrics for one local-vs-TomTom comparison."""
    predicted = float(predicted_time_s)
    observed_time = float(observed.travel_time_s)
    if predicted <= 0 or observed_time <= 0:
        raise ValueError("Predicted and observed travel times must be positive")
    absolute_error = observed_time - predicted
    return {
        "predicted_time_s": predicted,
        "observed_time_s": observed_time,
        "absolute_error_s": absolute_error,
        "absolute_error_pct": absolute_error / predicted * 100.0,
        "correction_multiplier": observed_time / predicted,
    }


def calibrate_multiplier(
    predicted_times_s: Iterable[float],
    observations: Iterable[RouteObservation],
) -> CalibrationResult:
    """Calculate a robust correction factor from sampled route observations.

    The median ratio is used instead of the mean so one incident or failed
    prediction does not distort the whole synthetic traffic profile.
    """
    ratios = []
    errors = []
    for predicted, observed in zip(predicted_times_s, observations):
        metrics = compare_prediction(predicted, observed)
        ratios.append(metrics["correction_multiplier"])
        errors.append(abs(metrics["absolute_error_s"]))
    if not ratios:
        raise ValueError("At least one calibration sample is required")
    return CalibrationResult(
        multiplier=float(median(ratios)),
        samples=len(ratios),
        median_absolute_error_s=float(median(errors)),
    )
