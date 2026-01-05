"""Sensor platform for SL Departures."""
from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SLDeparturesCoordinator
from .const import DEFAULT_NUM_DEPARTURES, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SL Departures sensors from a config entry."""
    coordinator: SLDeparturesCoordinator = hass.data[DOMAIN][entry.entry_id]
    num_departures = entry.data.get("num_departures", DEFAULT_NUM_DEPARTURES)

    # Create one sensor per departure slot
    sensors = [
        SLDeparturesSensor(coordinator, entry, index)
        for index in range(num_departures)
    ]

    async_add_entities(sensors)


# Icons for different transport modes
TRANSPORT_MODE_ICONS = {
    "TRAIN": "mdi:train",
    "METRO": "mdi:subway-variant",
    "BUS": "mdi:bus",
    "TRAM": "mdi:tram",
    "SHIP": "mdi:ship",
    "FERRY": "mdi:ferry",
}


class SLDeparturesSensor(CoordinatorEntity[SLDeparturesCoordinator], SensorEntity):
    """Sensor showing a departure from SL public transit."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SLDeparturesCoordinator,
        entry: ConfigEntry,
        index: int,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._index = index

        site_id = entry.data["site_id"]
        site_name = entry.data["site_name"]
        transport_mode = entry.data.get("transport_mode", "")
        line = entry.data.get("line", "")
        direction_code = entry.data.get("direction_code", "")
        direction_name = entry.data.get("direction_name", "")

        # Build unique_id matching config flow pattern
        unique_id = f"sl_departures_{site_id}"
        if transport_mode:
            unique_id += f"_{transport_mode}"
        if line:
            unique_id += f"_line{line}"
        if direction_code:
            unique_id += f"_dir{direction_code}"
        unique_id += f"_dep{index}"
        self._attr_unique_id = unique_id

        # With has_entity_name=True, entity name is appended to device name
        # So entity name should just be the position (Next, 2nd, 3rd...)
        # Device name provides the full context
        self._attr_name = self._get_position_label(index)

        # Device info for grouping entities
        # This becomes the prefix for all entity names
        device_name = f"SL {site_name}"
        if line:
            device_name += f" {line}"
        if direction_name:
            device_name += f" → {direction_name}"

        # Device identifier includes transport_mode and line for uniqueness
        device_id = site_id
        if transport_mode:
            device_id += f"_{transport_mode}"
        if line:
            device_id += f"_{line}"
        if direction_code:
            device_id += f"_{direction_code}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="Storstockholms Lokaltrafik",
        )

        # Set icon based on transport mode
        self._transport_mode = transport_mode
        self._attr_icon = TRANSPORT_MODE_ICONS.get(transport_mode, "mdi:train")

    @staticmethod
    def _get_position_label(index: int) -> str:
        """Get human-readable position label."""
        if index == 0:
            return "Next"
        elif index == 1:
            return "2nd"
        elif index == 2:
            return "3rd"
        else:
            return f"{index + 1}th"

    @property
    def _departure(self) -> dict | None:
        """Get the departure for this sensor's index."""
        if not self.coordinator.data or len(self.coordinator.data) <= self._index:
            return None
        return self.coordinator.data[self._index]

    @property
    def native_value(self) -> str | None:
        """Return the departure time."""
        dep = self._departure
        if not dep:
            return None
        return dep.get("display")

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self._departure is not None

    @property
    def icon(self) -> str:
        """Return icon based on transport mode and delay status."""
        base_icon = TRANSPORT_MODE_ICONS.get(self._transport_mode, "mdi:train")
        dep = self._departure
        if dep:
            delay = self._calculate_delay_minutes(dep)
            if delay is not None and delay > 0:
                return "mdi:clock-alert"  # Indicate delay
        return base_icon

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional departure information."""
        dep = self._departure
        if not dep:
            return {}

        scheduled = dep.get("scheduled")
        expected = dep.get("expected")
        delay_minutes = self._calculate_delay_minutes(dep)
        minutes_until = self._calculate_minutes_until(expected)
        time_formatted = self._format_time(expected)

        attrs = {
            # Card-compatible attributes (Trafiklab Timetable Card)
            "line": dep.get("line", {}).get("designation"),
            "destination": dep.get("destination"),
            "scheduled_time": scheduled,
            "expected_time": expected,
            "time_formatted": time_formatted,
            "minutes_until": minutes_until,
            "transport_mode": dep.get("line", {}).get("transport_mode"),
            "real_time": dep.get("journey", {}).get("prediction_state") == "NORMAL",
            "delay_minutes": delay_minutes if delay_minutes is not None else 0,
            "canceled": dep.get("state") == "CANCELLED",
            "platform": dep.get("stop_point", {}).get("designation"),
            "agency": "SL",
            # Additional useful attributes
            "direction": dep.get("direction"),
            "state": dep.get("state"),
            "stop_area": dep.get("stop_area", {}).get("name"),
        }

        # Add deviations/messages if any
        deviations = dep.get("deviations", [])
        if deviations:
            messages = [d.get("message") for d in deviations if d.get("message")]
            if messages:
                attrs["deviations"] = messages

        return attrs

    @staticmethod
    def _calculate_delay_minutes(dep: dict) -> int | None:
        """Calculate delay in minutes between scheduled and expected time."""
        scheduled_str = dep.get("scheduled")
        expected_str = dep.get("expected")

        if not scheduled_str or not expected_str:
            return None

        try:
            scheduled = datetime.fromisoformat(scheduled_str.replace("Z", "+00:00"))
            expected = datetime.fromisoformat(expected_str.replace("Z", "+00:00"))
            delay = expected - scheduled
            return int(delay.total_seconds() / 60)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _calculate_minutes_until(expected_str: str | None) -> int:
        """Calculate minutes until departure from expected time."""
        if not expected_str:
            return 0

        try:
            expected = datetime.fromisoformat(expected_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            delta = expected - now
            return max(0, int(delta.total_seconds() / 60))
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _format_time(time_str: str | None) -> str | None:
        """Format ISO timestamp as HH:MM for display."""
        if not time_str:
            return None

        try:
            dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            # Convert to local time for display
            local_dt = dt.astimezone()
            return local_dt.strftime("%H:%M")
        except (ValueError, TypeError):
            return None
