"""Home Assistant-independent helpers: back-off maths and departure filtering."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import random

MAX_BACKOFF = 600  # seconds
MAX_STALE_SECONDS = 600  # serve cached departures for at most this long
DEPARTED_GRACE_SECONDS = 60  # keep a just-left departure so it can show "Nu"


def is_backoff_status(status: int) -> bool:
    """Return True for HTTP statuses that mean "slow down / try later"."""
    return status == 429 or status >= 500


def parse_retry_after(value: str | None) -> int | None:
    """Parse a Retry-After header given in seconds (HTTP-date form is ignored)."""
    if value is None:
        return None
    try:
        seconds = int(value.strip())
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def backoff_seconds(
    base: int,
    failures: int,
    retry_after: int | None = None,
    maximum: int = MAX_BACKOFF,
) -> int:
    """Return the next polling interval after `failures` consecutive failures.

    SL's 429s come from a quota shared by all anonymous callers, so our own rate
    is not the cause and long back-offs only waste chances to get through: retry
    at the normal interval once, then at twice that. A server-sent Retry-After
    is always honoured (up to `maximum`).
    """
    delay = base if failures <= 1 else base * 2
    if retry_after is not None:
        delay = max(delay, retry_after)
    return min(delay, maximum)


def with_jitter(
    seconds: float,
    fraction: float = 0.1,
    rand: Callable[[], float] = random.random,
) -> float:
    """Add up to `fraction` of random extra delay so entries don't retry in lockstep."""
    return seconds * (1 + fraction * rand())


def _departure_time(dep: dict) -> datetime | None:
    """Return the departure's expected (else scheduled) time as an aware datetime."""
    value = dep.get("expected") or dep.get("scheduled")
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None
    # Naive timestamps are local time, matching how the sensor reads them.
    return parsed.astimezone() if parsed.tzinfo is None else parsed


def drop_departed(departures: list[dict], now: datetime) -> list[dict]:
    """Remove departures that left more than the grace period ago.

    Keeps departures with no usable timestamp. Matters when serving cached data.
    """
    cutoff = now - timedelta(seconds=DEPARTED_GRACE_SECONDS)
    kept = []
    for dep in departures:
        when = _departure_time(dep)
        if when is None or when >= cutoff:
            kept.append(dep)
    return kept


@dataclass(frozen=True)
class DepartureFilter:
    """Per-entry filter applied to a site's raw departures."""

    transport_modes: list[str] = field(default_factory=lambda: ["TRAIN"])
    direction_code: str = ""
    line_filter: str = ""

    @classmethod
    def from_entry(cls, data: dict, options: dict) -> DepartureFilter:
        """Build a filter from config entry data, falling back to legacy options."""
        transport_mode = data.get("transport_mode")
        if transport_mode:
            modes = [transport_mode]
        else:
            modes = options.get("transport_modes", ["TRAIN"])
        line = data.get("line", "") or options.get("line_filter", "")
        return cls(modes, data.get("direction_code", ""), line)

    def apply(self, departures: list[dict]) -> list[dict]:
        """Return the departures matching this filter."""
        result = [
            dep
            for dep in departures
            if dep.get("line", {}).get("transport_mode") in self.transport_modes
        ]
        if self.direction_code:
            result = [
                dep for dep in result
                if str(dep.get("direction_code")) == self.direction_code
            ]
        if self.line_filter:
            numbers = [ln.strip() for ln in self.line_filter.split(",")]
            result = [
                dep for dep in result
                if dep.get("line", {}).get("designation") in numbers
            ]
        return result
