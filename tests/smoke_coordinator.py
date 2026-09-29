"""Smoke test for SLSiteCoordinator against a fake HTTP session (needs homeassistant)."""
import asyncio
from datetime import datetime, timedelta, timezone
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, ".")
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
import aiohttp

import custom_components.sl_departures as sl

DEPS = {"departures": [{"line": {"transport_mode": "TRAIN", "designation": "40"}}]}


class FakeResponse:
    def __init__(self, status, headers=None, body=None):
        self.status, self.headers, self.reason = status, headers or {}, "x"
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise aiohttp.ClientResponseError(MagicMock(), (), status=self.status)

    async def json(self):
        return self._body


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)

    def get(self, url, **kw):
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def near(interval, expected):
    """Intervals after a failure carry up to 10% jitter."""
    seconds = interval.total_seconds()
    return expected <= seconds <= expected * 1.1 + 1


def entry(eid, options=None):
    e = MagicMock()
    e.entry_id, e.options = eid, options or {}
    return e


async def main():
    hass = HomeAssistant(tempfile.mkdtemp())
    session = FakeSession([
        FakeResponse(200, body=DEPS),
        FakeResponse(429, {"Retry-After": "300"}),
        FakeResponse(500),
        aiohttp.ServerTimeoutError(),
        FakeResponse(200, body=DEPS),
    ])
    with patch.object(sl, "async_get_clientsession", return_value=session):
        c = sl.SLSiteCoordinator(hass, "1080")
    c.register_entry(entry("a"))
    c.register_entry(entry("b", {"scan_interval": 30}))
    assert c.update_interval.total_seconds() == 30, "min interval of entries"

    await c.async_refresh()
    assert c.last_update_success and c.data == DEPS["departures"]
    await c.async_refresh()  # 429 + Retry-After 300
    assert c.last_update_success and c.data == DEPS["departures"], "stale served"
    assert near(c.update_interval, 300), c.update_interval  # Retry-After honoured
    await c.async_refresh()  # 500
    assert near(c.update_interval, 60), c.update_interval  # 2x base, capped
    await c.async_refresh()  # timeout
    assert near(c.update_interval, 60), c.update_interval  # still capped at 2x
    await c.async_refresh()  # recovery
    assert c.update_interval.total_seconds() == 30, c.update_interval
    assert c._failures == 0

    # Failure with nothing cached -> UpdateFailed / last_update_success False
    with patch.object(sl, "async_get_clientsession", return_value=FakeSession([FakeResponse(429)])):
        c2 = sl.SLSiteCoordinator(hass, "9703")
    c2.register_entry(entry("c"))
    await c2.async_refresh()
    assert not c2.last_update_success
    assert isinstance(c2.last_exception, UpdateFailed), c2.last_exception

    # Stale data expires
    c._failures = 0
    c._last_success -= 10_000
    c._session = FakeSession([FakeResponse(500)])
    await c.async_refresh()
    assert not c.last_update_success, "stale data too old must fail"

    # Unregister bookkeeping
    assert c.unregister_entry(entry("a")) == 1
    assert c.unregister_entry(entry("b")) == 0
    # Setup with a failing first fetch must not raise (no HA-level retry storm);
    # the coordinator keeps the site and retries on its own back-off schedule.
    hass2 = HomeAssistant(tempfile.mkdtemp())
    hass2.config_entries = MagicMock()
    hass2.config_entries.async_forward_entry_setups = AsyncMock()
    e = entry("s1")
    e.data = {"site_id": "1080"}
    calls = []
    fail = FakeSession([FakeResponse(429), FakeResponse(429)])
    with patch.object(sl, "async_get_clientsession", return_value=fail):
        assert await sl.async_setup_entry(hass2, e) is True
    coord = hass2.data[sl.DOMAIN]["sites"]["1080"]
    assert not coord.last_update_success and coord.data is None
    assert near(coord.update_interval, sl.DEFAULT_SCAN_INTERVAL), coord.update_interval  # first failure: base
    coord.async_add_listener(lambda: None)  # what the sensor does
    assert coord._unsub_refresh is not None, "retry must be scheduled once a sensor listens"
    coord._unschedule_refresh()

    # Second entry on the same site reuses the coordinator; unloading one keeps it.
    e2 = entry("s2")
    e2.data = {"site_id": "1080"}
    assert await sl.async_setup_entry(hass2, e2) is True
    assert hass2.data[sl.DOMAIN]["sites"]["1080"] is coord
    hass2.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    assert await sl.async_unload_entry(hass2, e) is True
    assert "1080" in hass2.data[sl.DOMAIN]["sites"]
    assert await sl.async_unload_entry(hass2, e2) is True
    assert "1080" not in hass2.data[sl.DOMAIN]["sites"]

    # Sensor: departed trains are not shown, even when serving cached data.
    from custom_components.sl_departures.sensor import SLDeparturesSensor

    now = datetime.now(timezone.utc)

    def stamp(minutes):
        return (now + timedelta(minutes=minutes)).isoformat()

    def train(minutes):
        return {
            "line": {"transport_mode": "TRAIN", "designation": "40"},
            "direction_code": 1,
            "expected": stamp(minutes),
            "scheduled": stamp(minutes),
        }

    se = entry("sensor")
    se.data = {"site_id": "1080", "site_name": "Test", "transport_mode": "TRAIN"}
    coord.data = [train(-5), train(5)]
    sensor = SLDeparturesSensor(coord, se)
    assert len(sensor.extra_state_attributes["upcoming"]) == 1, sensor.extra_state_attributes
    assert sensor.native_value in ("4 min", "5 min"), sensor.native_value

    print("SMOKE OK")


asyncio.run(main())
