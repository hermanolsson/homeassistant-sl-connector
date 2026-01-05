# SL Departures for Home Assistant

A Home Assistant custom integration for real-time public transit departures from SL (Storstockholms Lokaltrafik) in Stockholm, Sweden.

## Features

- Real-time departure information from any SL station
- Filter by transport mode (train, metro, bus, tram, ferry)
- Filter by specific line
- Filter by direction (shows actual destinations)
- Single sensor with `upcoming` array of all departures
- Compatible with [Trafiklab Timetable Card](https://github.com/MrSjodin/HomeAssistant_Trafiklab_Timetable_Card)
- Transport mode specific icons
- Delay detection with automatic calculation
- Service disruption/deviation alerts

## Installation

### Manual Installation

1. Copy the `custom_components/sl_departures` folder to your Home Assistant's `config/custom_components/` directory
2. Restart Home Assistant
3. Go to **Settings → Devices & Services → Add Integration**
4. Search for "SL Departures"

### HACS Installation

1. Open HACS in Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add `https://github.com/hermanolsson/homeassistant-sl-connector` as an **Integration**
4. Click **+ Explore & Download Repositories**
5. Search for "SL Departures" and install it
6. Restart Home Assistant

## Configuration

The integration uses a UI-based configuration flow:

1. **Search** - Enter your station name (e.g., "Barkarby")
2. **Select** - Choose your station from the search results
3. **Transport mode** - Select type: Train, Metro, Bus, Tram, Ship, or Ferry
4. **Line** - Select a specific line or "All lines" (auto-skipped if only one line)
5. **Direction** - Filter by direction showing actual destinations (e.g., "→ Kungsträdgården")

## Options

After setup, click **Configure** on the integration to adjust:

| Option | Description | Default |
|--------|-------------|---------|
| Update interval | How often to fetch new data (30-300 seconds) | 60 seconds |
| Transport modes | Override transport modes (for legacy entries) | From setup |
| Line filter | Override line filter (comma-separated) | From setup |

## Sensors

Each config entry creates one sensor with:

**State:** Next departure display time (e.g., "4 min", "Nu", "23:45")

**Attributes** (compatible with [Trafiklab Timetable Card](https://github.com/MrSjodin/HomeAssistant_Trafiklab_Timetable_Card)):

| Attribute | Description |
|-----------|-------------|
| `upcoming` | Array of departure objects (see below) |

Each item in the `upcoming` array contains:

| Field | Description |
|-------|-------------|
| `line` | Line number/designation |
| `destination` | Final destination |
| `scheduled_time` | Scheduled departure (ISO timestamp) |
| `expected_time` | Expected departure (ISO timestamp) |
| `time_formatted` | Clock time (e.g., "14:35") |
| `minutes_until` | Minutes until departure (integer, 0 = now) |
| `transport_mode` | TRAIN, METRO, BUS, TRAM, SHIP, FERRY |
| `real_time` | True if real-time data available |
| `delay_minutes` | Delay in minutes (0 = on time) |
| `delay` | Alias for delay_minutes |
| `canceled` | True if departure is cancelled |
| `platform` | Platform/track number |
| `agency` | "SL" |
| `deviations` | List of service alerts (if any) |

## Example Dashboard Cards

### Trafiklab Timetable Card (Recommended)
```yaml
type: custom:trafiklab-timetable-card
entity: sensor.sl_barkarby_43_nynashamn_departures
title: Pendeltåg från Barkarby
```

### Markdown Card
```yaml
type: markdown
title: Pendeltåg från Barkarby
content: |
  {% set deps = state_attr('sensor.sl_barkarby_43_nynashamn_departures', 'upcoming') %}
  {% for dep in deps[:3] %}
  **{{ dep.time_formatted }}** → {{ dep.destination }} · Spår {{ dep.platform }}
  {% endfor %}
```

## API

This integration uses the public SL Transport API:
- No API key required
- Sites: `https://transport.integration.sl.se/v1/sites`
- Departures: `https://transport.integration.sl.se/v1/sites/{siteId}/departures`

## License

MIT
