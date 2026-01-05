"""Config flow for SL Departures integration."""
from __future__ import annotations

import logging

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    API_DEPARTURES_URL,
    API_SITES_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    TRANSPORT_MODES,
)

_LOGGER = logging.getLogger(__name__)


class SLDeparturesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SL Departures."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._sites: dict[str, str] = {}
        self._matching_sites: dict[str, str] = {}
        self._selected_site_id: str | None = None
        self._selected_site_name: str | None = None
        self._selected_transport_mode: str = "TRAIN"
        self._selected_line: str = ""  # Empty means all lines
        self._available_lines: dict[str, str] = {}  # {designation: designation}
        self._selected_direction: str = ""
        self._available_directions: dict[str, str] = {}  # {direction_code: destination}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return SLDeparturesOptionsFlow()

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Step 1: Ask user to search for a station."""
        errors: dict[str, str] = {}

        if user_input is not None:
            search_term = user_input.get("search", "").strip().lower()

            if len(search_term) < 2:
                errors["search"] = "search_too_short"
            else:
                # Fetch sites if not cached
                if not self._sites:
                    try:
                        self._sites = await self._fetch_sites()
                    except aiohttp.ClientError:
                        errors["base"] = "cannot_connect"

                if not errors:
                    # Filter sites by search term
                    self._matching_sites = {
                        site_id: name
                        for site_id, name in self._sites.items()
                        if search_term in name.lower()
                    }

                    if not self._matching_sites:
                        errors["search"] = "no_matches"
                    else:
                        return await self.async_step_select()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("search"): TextSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_select(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Step 2: Select from matching stations."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._selected_site_id = user_input["site"]
            self._selected_site_name = self._matching_sites.get(
                self._selected_site_id, f"Site {self._selected_site_id}"
            )
            return await self.async_step_transport_mode()

        # Build options with ID to distinguish duplicates
        sorted_sites = sorted(self._matching_sites.items(), key=lambda x: x[1])

        # Check for duplicate names
        name_counts: dict[str, int] = {}
        for _, name in sorted_sites:
            name_counts[name] = name_counts.get(name, 0) + 1

        options = []
        for site_id, name in sorted_sites:
            if name_counts[name] > 1:
                label = f"{name} ({site_id})"
            else:
                label = name
            options.append({"value": site_id, "label": label})

        return self.async_show_form(
            step_id="select",
            data_schema=vol.Schema(
                {
                    vol.Required("site"): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_transport_mode(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Step 3: Select transport mode."""
        if user_input is not None:
            self._selected_transport_mode = user_input["transport_mode"]
            # Fetch available lines for this transport mode
            try:
                self._available_lines = await self._fetch_lines(
                    self._selected_site_id,
                    self._selected_transport_mode,
                )
            except aiohttp.ClientError:
                _LOGGER.warning("Could not fetch lines")
                self._available_lines = {}
            return await self.async_step_line()

        # Build transport mode options
        transport_options = [
            {"value": mode, "label": label}
            for mode, label in TRANSPORT_MODES.items()
        ]

        return self.async_show_form(
            step_id="transport_mode",
            data_schema=vol.Schema(
                {
                    vol.Required("transport_mode", default="TRAIN"): SelectSelector(
                        SelectSelectorConfig(
                            options=transport_options,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    async def async_step_line(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Step 4: Select line (optional)."""
        if user_input is not None:
            selected = user_input["line"]
            self._selected_line = "" if selected == "__all__" else selected
            # Fetch directions filtered by transport mode and line
            try:
                self._available_directions = await self._fetch_directions(
                    self._selected_site_id,
                    self._selected_transport_mode,
                    self._selected_line,
                )
            except aiohttp.ClientError:
                _LOGGER.warning("Could not fetch directions, using defaults")
                self._available_directions = {}
            return await self.async_step_direction()

        # Build line options
        options = [{"value": "__all__", "label": "All lines"}]

        if self._available_lines:
            for designation, name in sorted(
                self._available_lines.items(), key=lambda x: x[0]
            ):
                if name and name != designation:
                    options.append({"value": designation, "label": f"{designation} ({name})"})
                else:
                    options.append({"value": designation, "label": designation})

        # Skip this step if only one line (or no lines)
        if len(options) <= 2:
            self._selected_line = ""
            try:
                self._available_directions = await self._fetch_directions(
                    self._selected_site_id,
                    self._selected_transport_mode,
                    self._selected_line,
                )
            except aiohttp.ClientError:
                self._available_directions = {}
            return await self.async_step_direction()

        return self.async_show_form(
            step_id="line",
            data_schema=vol.Schema(
                {
                    vol.Required("line", default="__all__"): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    async def async_step_direction(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Step 5: Select direction filter."""
        if user_input is not None:
            selected = user_input["direction"]
            if selected == "__all__":
                self._selected_direction = ""
                self._selected_direction_name = ""
            else:
                self._selected_direction = selected
                self._selected_direction_name = self._available_directions.get(
                    selected, ""
                )

            # Build unique_id with transport_mode, line and direction
            unique_id = f"sl_departures_{self._selected_site_id}"
            if self._selected_transport_mode:
                unique_id += f"_{self._selected_transport_mode}"
            if self._selected_line:
                unique_id += f"_line{self._selected_line}"
            if self._selected_direction:
                unique_id += f"_dir{self._selected_direction}"

            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            # Build title
            title = self._selected_site_name
            if self._selected_line:
                title = f"{title} Line {self._selected_line}"
            direction_name = self._selected_direction_name
            if self._selected_direction and direction_name:
                title = f"{title} → {direction_name}"
            elif self._selected_direction:
                title = f"{title} Dir {self._selected_direction}"

            return self.async_create_entry(
                title=title,
                data={
                    "site_id": self._selected_site_id,
                    "site_name": self._selected_site_name,
                    "transport_mode": self._selected_transport_mode,
                    "line": self._selected_line,
                    "direction_code": self._selected_direction,
                    "direction_name": direction_name,
                },
            )

        # Build direction options from fetched data
        options = [{"value": "__all__", "label": "All directions"}]

        if self._available_directions:
            for direction_code, destination in sorted(
                self._available_directions.items()
            ):
                options.append({
                    "value": direction_code,
                    "label": f"→ {destination}",
                })
        else:
            # Fallback if we couldn't fetch directions
            options.extend([
                {"value": "1", "label": "Direction 1"},
                {"value": "2", "label": "Direction 2"},
            ])

        return self.async_show_form(
            step_id="direction",
            data_schema=vol.Schema(
                {
                    vol.Required("direction", default="__all__"): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    async def _fetch_sites(self) -> dict[str, str]:
        """Fetch available sites from SL API."""
        session = async_get_clientsession(self.hass)
        async with session.get(API_SITES_URL) as response:
            response.raise_for_status()
            data = await response.json()

        sites = {}
        for site in data:
            site_id = str(site.get("id"))
            site_name = site.get("name", f"Site {site_id}")
            sites[site_id] = site_name

        return sites

    async def _fetch_lines(
        self, site_id: str, transport_mode: str
    ) -> dict[str, str]:
        """Fetch available lines for a transport mode at a site."""
        session = async_get_clientsession(self.hass)
        url = API_DEPARTURES_URL.format(site_id=site_id)

        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.json()

        departures = data.get("departures", [])
        lines: dict[str, str] = {}

        for dep in departures:
            line_info = dep.get("line", {})
            if line_info.get("transport_mode") != transport_mode:
                continue

            designation = line_info.get("designation", "")
            group_name = line_info.get("group_of_lines", "")

            if designation and designation not in lines:
                lines[designation] = group_name

        return lines

    async def _fetch_directions(
        self, site_id: str, transport_mode: str, line_filter: str = ""
    ) -> dict[str, str]:
        """Fetch available directions from departures at a site."""
        session = async_get_clientsession(self.hass)
        url = API_DEPARTURES_URL.format(site_id=site_id)

        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.json()

        departures = data.get("departures", [])
        directions: dict[str, str] = {}

        for dep in departures:
            line_info = dep.get("line", {})
            # Filter by transport mode
            if line_info.get("transport_mode") != transport_mode:
                continue

            # Filter by line if specified
            if line_filter and line_info.get("designation") != line_filter:
                continue

            direction_code = str(dep.get("direction_code", ""))
            destination = dep.get("destination", "")

            if direction_code and destination and direction_code not in directions:
                directions[direction_code] = destination

        return directions


class SLDeparturesOptionsFlow(OptionsFlow):
    """Handle options flow for SL Departures."""

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            _LOGGER.debug("Options flow saving: %s", user_input)
            return self.async_create_entry(title="", data=user_input)

        # Get current options or defaults
        options = self.config_entry.options
        current_scan_interval = options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        current_transport_modes = options.get("transport_modes", ["TRAIN"])
        current_line_filter = options.get("line_filter", "")

        # Build transport mode options
        transport_options = [
            {"value": mode, "label": label}
            for mode, label in TRANSPORT_MODES.items()
        ]

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "scan_interval",
                        default=current_scan_interval,
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=30,
                            max=300,
                            step=10,
                            unit_of_measurement="seconds",
                            mode=NumberSelectorMode.SLIDER,
                        )
                    ),
                    vol.Required(
                        "transport_modes",
                        default=current_transport_modes,
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=transport_options,
                            multiple=True,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        "line_filter",
                        default=current_line_filter,
                    ): TextSelector(),
                }
            ),
        )
