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
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SL Departures sensor from a config entry."""
    coordinator: SLDeparturesCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SLDeparturesSensor(coordinator, entry)])


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
    """Sensor showing upcoming departures from SL public transit."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SLDeparturesCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry

        site_id = entry.data["site_id"]
        site_name = entry.data["site_name"]
        transport_mode = entry.data.get("transport_mode", "")
        line = entry.data.get("line", "")
        direction_code = entry.data.get("direction_code", "")
        direction_name = entry.data.get("direction_name", "")

        # Build unique_id
        unique_id = f"sl_departures_{site_id}"
        if transport_mode:
            unique_id += f"_{transport_mode}"
        if line:
            unique_id += f"_line{line}"
        if direction_code:
            unique_id += f"_dir{direction_code}"
        self._attr_unique_id = unique_id

        # Entity name - just "Departures" since device name provides context
        self._attr_name = "Departures"

        # Device info for grouping
        device_name = f"SL {site_name}"
        if line:
            device_name += f" {line}"
        if direction_name:
            device_name += f" → {direction_name}"

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

    @property
    def native_value(self) -> str | None:
        """Return the next departure time as the state."""
        if not self.coordinator.data:
            return None
        first = self.coordinator.data[0] if self.coordinator.data else None
        if not first:
            return None
        return first.get("display")

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and bool(self.coordinator.data)

    @property
    def icon(self) -> str:
        """Return icon based on transport mode and delay status."""
        base_icon = TRANSPORT_MODE_ICONS.get(self._transport_mode, "mdi:train")
        if self.coordinator.data:
            first = self.coordinator.data[0]
            delay = self._calculate_delay_minutes(first)
            if delay is not None and delay > 0:
                return "mdi:clock-alert"
        return base_icon

    @property
    def extra_state_attributes(self) -> dict:
        """Return upcoming departures array."""
        if not self.coordinator.data:
            return {"upcoming": []}

        upcoming = []
        for dep in self.coordinator.data:
            scheduled = dep.get("scheduled")
            expected = dep.get("expected")
            delay_minutes = self._calculate_delay_minutes(dep)
            delay = delay_minutes if delay_minutes is not None else 0

            # Check journey.state for cancellation (not top-level state)
            journey_state = dep.get("journey", {}).get("state", "")
            is_canceled = journey_state == "CANCELLED"

            departure = {
                "line": dep.get("line", {}).get("designation"),
                "destination": dep.get("destination"),
                "scheduled_time": scheduled,
                "expected_time": expected,
                "time_formatted": self._format_time(expected) or "",
                "minutes_until": self._calculate_minutes_until(expected),
                "transport_mode": dep.get("line", {}).get("transport_mode"),
                "real_time": dep.get("journey", {}).get("prediction_state") == "NORMAL",
                "delay_minutes": delay,
                "delay": delay,
                "canceled": is_canceled,
                "platform": dep.get("stop_point", {}).get("designation"),
                "agency": "SL",
            }

            # Add deviations if any
            deviations = dep.get("deviations", [])
            if deviations:
                messages = [d.get("message") for d in deviations if d.get("message")]
                if messages:
                    departure["deviations"] = messages

            upcoming.append(departure)

        return {"upcoming": upcoming}

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
            if expected.tzinfo is None:
                now = datetime.now()
            else:
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
            if dt.tzinfo is None:
                return dt.strftime("%H:%M")
            return dt.astimezone().strftime("%H:%M")
        except (ValueError, TypeError):
            return None
