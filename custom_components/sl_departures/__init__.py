"""SL Departures integration for Home Assistant."""
from __future__ import annotations

from datetime import timedelta
import logging
import time

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    MAX_STALE_SECONDS,
    backoff_seconds,
    is_backoff_status,
    parse_retry_after,
    with_jitter,
)
from .const import (
    API_DEPARTURES_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


def _sites(hass: HomeAssistant) -> dict[str, SLSiteCoordinator]:
    """Return the site_id -> shared coordinator registry."""
    return hass.data.setdefault(DOMAIN, {}).setdefault("sites", {})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SL Departures from a config entry."""
    _LOGGER.debug("Setting up entry %s with data: %s", entry.entry_id, dict(entry.data))
    site_id = entry.data["site_id"]
    sites = _sites(hass)

    coordinator = sites.get(site_id)
    is_new = coordinator is None
    if is_new:
        coordinator = SLSiteCoordinator(hass, site_id)
        sites[site_id] = coordinator
    coordinator.register_entry(entry)

    if is_new:
        # Never fail setup on a bad first fetch: a ConfigEntryNotReady makes HA
        # retry every few seconds, which is exactly what a rate-limited API
        # doesn't need. The coordinator retries on its own back-off schedule and
        # the sensors are unavailable until the first success.
        await coordinator.async_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener for options changes
    entry.async_on_unload(entry.add_update_listener(async_options_updated))

    return True


async def async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update - reload the integration."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        sites = _sites(hass)
        coordinator = sites.get(entry.data["site_id"])
        if coordinator is not None and coordinator.unregister_entry(entry) == 0:
            sites.pop(entry.data["site_id"])
            await coordinator.async_shutdown()

    return unload_ok


class SLSiteCoordinator(DataUpdateCoordinator[list[dict]]):
    """Fetches the departures of one SL site, shared by all entries using it.

    Holds the unfiltered departures; each sensor applies its own filter. Backs
    off on 429/5xx and serves the last good data for a while when the API fails.
    """

    def __init__(self, hass: HomeAssistant, site_id: str) -> None:
        """Initialize the coordinator."""
        self.site_id = site_id
        self._scan_intervals: dict[str, int] = {}
        self._base_seconds = DEFAULT_SCAN_INTERVAL
        self._failures = 0
        self._last_success: float | None = None

        # config_entry=None: the coordinator outlives any single entry, so it
        # must not be shut down when the entry that created it unloads.
        super().__init__(
            hass,
            _LOGGER,
            name=f"SL Departures {site_id}",
            config_entry=None,
            update_interval=timedelta(seconds=self._base_seconds),
        )
        self._session = async_get_clientsession(hass)

    def register_entry(self, entry: ConfigEntry) -> None:
        """Attach an entry; poll as often as the most demanding entry wants."""
        self._scan_intervals[entry.entry_id] = entry.options.get(
            "scan_interval", DEFAULT_SCAN_INTERVAL
        )
        self._update_base_interval()

    def unregister_entry(self, entry: ConfigEntry) -> int:
        """Detach an entry and return how many entries remain."""
        self._scan_intervals.pop(entry.entry_id, None)
        if self._scan_intervals:
            self._update_base_interval()
        return len(self._scan_intervals)

    def _update_base_interval(self) -> None:
        self._base_seconds = min(self._scan_intervals.values())
        if self._failures == 0:
            self.update_interval = timedelta(seconds=self._base_seconds)

    async def _async_update_data(self) -> list[dict]:
        """Fetch departure data from SL API."""
        url = API_DEPARTURES_URL.format(site_id=self.site_id)

        try:
            async with self._session.get(url, timeout=REQUEST_TIMEOUT) as response:
                if is_backoff_status(response.status):
                    retry_after = parse_retry_after(response.headers.get("Retry-After"))
                    return self._handle_failure(
                        f"HTTP {response.status} {response.reason}", retry_after
                    )
                response.raise_for_status()
                data = await response.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            return self._handle_failure(str(err) or type(err).__name__, None)

        if self._failures:
            _LOGGER.warning(
                "Site %s: API recovered after %d failed attempts", self.site_id, self._failures
            )
        self._failures = 0
        self._last_success = time.monotonic()
        self.update_interval = timedelta(seconds=self._base_seconds)

        departures = data.get("departures", [])
        _LOGGER.debug("Site %s: Got %d departures", self.site_id, len(departures))
        return departures

    def _handle_failure(self, reason: str, retry_after: int | None) -> list[dict]:
        """Back off, and keep serving recent data if we have it."""
        self._failures += 1
        delay = round(
            with_jitter(backoff_seconds(self._base_seconds, self._failures, retry_after))
        )
        self.update_interval = timedelta(seconds=delay)

        stale_for = (
            time.monotonic() - self._last_success
            if self._last_success is not None
            else None
        )
        if self.data is not None and stale_for is not None and stale_for <= MAX_STALE_SECONDS:
            log = _LOGGER.warning if self._failures == 1 else _LOGGER.debug
            log(
                "Site %s: %s; serving departures from %ds ago, retrying in %ds",
                self.site_id, reason, stale_for, delay,
            )
            return self.data

        raise UpdateFailed(f"Error fetching data: {reason} (retrying in {delay}s)")
