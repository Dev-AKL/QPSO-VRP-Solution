"""Cost and safety controls around live TomTom matrix requests.

The controls are deliberately provider-agnostic at the API boundary:

* identical live requests are served from a short-lived in-memory cache;
* monthly transactions are counted conservatively in a small JSON ledger;
* each client has hourly and daily request limits;
* a cooldown prevents accidental refresh loops;
* callers receive an explicit reason when local fallback is required.

The usage ledger is an operational estimate/reservation. It intentionally
counts a request before sending it so a timeout cannot make the application
underestimate possible provider usage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from typing import Callable, Generic, TypeVar


T = TypeVar("T")


class LiveTrafficControlError(RuntimeError):
    """Raised when a live request is not allowed by local policy."""


@dataclass(frozen=True)
class LiveTrafficPolicy:
    cache_ttl_s: float = 600.0
    minimum_refresh_s: float = 60.0
    max_requests_per_hour: int = 5
    max_requests_per_day: int = 20
    monthly_transaction_budget: int = 2000

    @classmethod
    def from_environment(cls) -> "LiveTrafficPolicy":
        def number(name, default, cast):
            try:
                value = cast(os.getenv(name, str(default)))
                if value < 0:
                    raise ValueError
                return value
            except (TypeError, ValueError):
                return default

        return cls(
            cache_ttl_s=number("TOMTOM_LIVE_CACHE_TTL_SECONDS", 600.0, float),
            minimum_refresh_s=number("TOMTOM_MIN_REFRESH_SECONDS", 60.0, float),
            max_requests_per_hour=number("TOMTOM_MAX_LIVE_REQUESTS_PER_HOUR", 5, int),
            max_requests_per_day=number("TOMTOM_MAX_LIVE_REQUESTS_PER_DAY", 20, int),
            # Leave headroom below the currently displayed free allowance.
            monthly_transaction_budget=number(
                "TOMTOM_MONTHLY_TRANSACTION_BUDGET", 2000, int
            ),
        )


@dataclass(frozen=True)
class LiveTrafficDecision:
    allowed: bool
    reason: str | None
    transaction_estimate: int
    month_transactions: int
    monthly_budget: int
    user_hour_requests: int
    user_day_requests: int
    cache_hit: bool = False


@dataclass
class _CacheEntry(Generic[T]):
    value: T
    created_at: float


def estimate_matrix_transactions(origins: int, destinations: int) -> int:
    """Estimate Matrix Routing v2 billable transactions.

    TomTom's discounted matrix billing uses origins × destinations for small
    dimensions and max(origins, destinations) × 5 otherwise.
    """
    if origins < 1 or destinations < 1:
        raise ValueError("Matrix dimensions must be positive")
    if origins <= 5 and destinations <= 5:
        return origins * destinations
    return max(origins, destinations) * 5


class LiveTrafficGovernor:
    def __init__(
        self,
        policy: LiveTrafficPolicy | None = None,
        usage_path: str | os.PathLike | None = None,
    ):
        self.policy = policy or LiveTrafficPolicy.from_environment()
        self.usage_path = Path(
            usage_path
            or os.getenv(
                "TOMTOM_USAGE_LEDGER_PATH",
                str(Path(__file__).parent / "cache" / "tomtom_usage.json"),
            )
        )
        self._cache: dict[str, _CacheEntry] = {}
        self._last_request_by_user: dict[str, float] = {}
        self._user_requests: dict[str, list[float]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def cache_key(payload: dict) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _month_key(now: datetime | None = None) -> str:
        current = now or datetime.now(timezone.utc)
        return current.strftime("%Y-%m")

    def _read_usage(self) -> dict:
        try:
            with self.usage_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                return payload
        except (FileNotFoundError, OSError, ValueError, TypeError):
            pass
        return {"months": {}}

    def _write_usage(self, payload: dict) -> None:
        self.usage_path.parent.mkdir(parents=True, exist_ok=True)
        # Calls are serialized by ``self._lock``. A direct write avoids
        # Windows file-replacement/antivirus races in development while still
        # keeping the ledger consistent within this process.
        with self.usage_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def _month_transactions(self, now: datetime | None = None) -> int:
        month = self._month_key(now)
        usage = self._read_usage()
        return int(usage.get("months", {}).get(month, {}).get("transactions", 0))

    def _user_counts(self, user_id: str, now: float) -> tuple[int, int]:
        timestamps = self._user_requests.setdefault(user_id, [])
        timestamps[:] = [stamp for stamp in timestamps if now - stamp < 86400]
        hour_count = sum(now - stamp < 3600 for stamp in timestamps)
        return hour_count, len(timestamps)

    def get_cached(self, key: str, now: float | None = None) -> T | None:
        current = time.monotonic() if now is None else now
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if current - entry.created_at > self.policy.cache_ttl_s:
                self._cache.pop(key, None)
                return None
            return entry.value

    def _store_cache(self, key: str, value: T, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        with self._lock:
            self._cache[key] = _CacheEntry(value=value, created_at=current)

    def decide(self, user_id: str, origins: int, destinations: int) -> LiveTrafficDecision:
        transactions = estimate_matrix_transactions(origins, destinations)
        now = time.monotonic()
        with self._lock:
            month_used = self._month_transactions()
            hour_count, day_count = self._user_counts(user_id, now)
            last_request = self._last_request_by_user.get(user_id)

            reason = None
            if month_used + transactions > self.policy.monthly_transaction_budget:
                reason = "monthly_live_transaction_budget_exhausted"
            elif hour_count >= self.policy.max_requests_per_hour:
                reason = "per_user_hourly_live_limit_exhausted"
            elif day_count >= self.policy.max_requests_per_day:
                reason = "per_user_daily_live_limit_exhausted"
            elif (
                last_request is not None
                and now - last_request < self.policy.minimum_refresh_s
            ):
                reason = "minimum_live_refresh_interval_not_elapsed"

            return LiveTrafficDecision(
                allowed=reason is None,
                reason=reason,
                transaction_estimate=transactions,
                month_transactions=month_used,
                monthly_budget=self.policy.monthly_transaction_budget,
                user_hour_requests=hour_count,
                user_day_requests=day_count,
            )

    def reserve(self, user_id: str, transactions: int) -> None:
        now = time.monotonic()
        month = self._month_key()
        with self._lock:
            usage = self._read_usage()
            months = usage.setdefault("months", {})
            record = months.setdefault(month, {"transactions": 0, "requests": 0})
            record["transactions"] = int(record.get("transactions", 0)) + int(transactions)
            record["requests"] = int(record.get("requests", 0)) + 1
            self._write_usage(usage)
            self._last_request_by_user[user_id] = now
            self._user_requests.setdefault(user_id, []).append(now)

    def get_or_fetch(
        self,
        key: str,
        user_id: str,
        origins: int,
        destinations: int,
        fetch: Callable[[], T],
    ) -> tuple[T | None, LiveTrafficDecision]:
        cached = self.get_cached(key)
        if cached is not None:
            decision = self.decide(user_id, origins, destinations)
            return cached, LiveTrafficDecision(
                allowed=True,
                reason=None,
                transaction_estimate=decision.transaction_estimate,
                month_transactions=decision.month_transactions,
                monthly_budget=decision.monthly_budget,
                user_hour_requests=decision.user_hour_requests,
                user_day_requests=decision.user_day_requests,
                cache_hit=True,
            )

        decision = self.decide(user_id, origins, destinations)
        if not decision.allowed:
            return None, decision

        self.reserve(user_id, decision.transaction_estimate)
        value = fetch()
        self._store_cache(key, value)
        return value, decision
