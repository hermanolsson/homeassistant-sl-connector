"""Home Assistant-independent helpers: back-off maths and departure filtering."""
from __future__ import annotations

from dataclasses import dataclass, field

MAX_BACKOFF = 600  # seconds
MAX_STALE_SECONDS = 600  # serve cached departures for at most this long


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
    """Return the next polling interval after `failures` consecutive failures."""
    delay = base * 2**failures
    if retry_after is not None:
        delay = max(delay, retry_after)
    return min(delay, maximum)


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
