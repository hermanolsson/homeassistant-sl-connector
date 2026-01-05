"""SL Departures integration for Home Assistant."""
from __future__ import annotations

from datetime import timedelta
import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_DEPARTURES_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SL Departures from a config entry."""
    _LOGGER.debug("Setting up entry %s with data: %s", entry.entry_id, dict(entry.data))
    coordinator = SLDeparturesCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener for options changes
    entry.async_on_unload(entry.add_update_listener(async_options_updated))

    return True


async def async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update - reload the integration."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class SLDeparturesCoordinator(DataUpdateCoordinator[list[dict]]):
    """Coordinator to fetch departure data from SL API."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry

        # Get config data
        self.site_id = entry.data["site_id"]
        self.direction_code = entry.data.get("direction_code", "")
        # Transport mode from config data (new entries) or options (legacy)
        self.transport_mode = entry.data.get("transport_mode")
        # Line filter from config data (new entries) or options (legacy)
        self.line_from_config = entry.data.get("line", "")

        # Get options (with defaults)
        options = entry.options
        scan_interval = options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        # Legacy: transport_modes from options (for old entries without transport_mode in data)
        if self.transport_mode:
            self.transport_modes = [self.transport_mode]
        else:
            self.transport_modes = options.get("transport_modes", ["TRAIN"])
        # Line filter: prefer config data, fall back to options
        if self.line_from_config:
            self.line_filter = self.line_from_config
        else:
            self.line_filter = options.get("line_filter", "")

        _LOGGER.debug(
            "Coordinator init for site %s: transport_modes=%s, line=%s, direction=%s",
            self.site_id,
            self.transport_modes,
            self.line_filter,
            self.direction_code,
        )

        super().__init__(
            hass,
            _LOGGER,
            name=f"SL Departures {self.site_id}",
            update_interval=timedelta(seconds=scan_interval),
        )

        self._session = async_get_clientsession(hass)

    async def _async_update_data(self) -> list[dict]:
        """Fetch departure data from SL API."""
        url = API_DEPARTURES_URL.format(site_id=self.site_id)

        try:
            async with self._session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err

        departures = data.get("departures", [])

        _LOGGER.debug(
            "Site %s: Got %d departures, filtering by modes=%s",
            self.site_id,
            len(departures),
            self.transport_modes,
        )

        # Filter by transport modes
        filtered = [
            dep for dep in departures
            if dep.get("line", {}).get("transport_mode") in self.transport_modes
        ]

        _LOGGER.debug(
            "Site %s: After transport mode filter: %d departures",
            self.site_id,
            len(filtered),
        )

        # Filter by direction if specified
        if self.direction_code:
            filtered = [
                dep for dep in filtered
                if str(dep.get("direction_code")) == self.direction_code
            ]
            _LOGGER.debug(
                "Site %s: After direction filter (code=%s): %d departures",
                self.site_id,
                self.direction_code,
                len(filtered),
            )

        # Filter by line if specified
        if self.line_filter:
            line_numbers = [ln.strip() for ln in self.line_filter.split(",")]
            filtered = [
                dep for dep in filtered
                if dep.get("line", {}).get("designation") in line_numbers
            ]

        return filtered
