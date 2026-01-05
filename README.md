# SL Departures for Home Assistant

A Home Assistant custom integration for real-time public transit departures from SL (Storstockholms Lokaltrafik) in Stockholm, Sweden.

## Features

- Real-time departure information from any SL station
- Filter by transport mode (train, metro, bus, tram, ferry)
- Filter by specific line
- Filter by direction (shows actual destinations)
- Multiple departure sensors per station
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
6. **Count** - Number of departures to track (1-5)

## Options

After setup, click **Configure** on the integration to adjust:

| Option | Description | Default |
|--------|-------------|---------|
| Update interval | How often to fetch new data (30-300 seconds) | 60 seconds |
| Transport modes | Override transport modes (for legacy entries) | From setup |
| Line filter | Override line filter (comma-separated) | From setup |

## Sensors

Each departure creates a sensor with:

**State:** Display time (e.g., "4 min", "Nu", "23:45")

**Attributes:**
- `destination` - Final destination
- `direction` - Direction name
- `line` - Line number
- `platform` - Platform/track number
- `scheduled` - Scheduled departure time
- `expected` - Expected departure time (real-time)
- `delay_minutes` - Delay in minutes (0 = on time)
- `is_delayed` - Boolean delay indicator
- `delay_message` - Human-readable delay status
- `deviations` - List of service alerts (if any)

## Example Dashboard Cards

### Markdown Card
```yaml
type: markdown
title: Pendeltåg från Barkarby
content: |
  {% set s = 'sensor.barkarby_southbound_next' %}
  **{{ states(s) }}** → {{ state_attr(s, 'destination') }}
  Spår {{ state_attr(s, 'platform') }} · {{ state_attr(s, 'delay_message') }}
```

### Entities Card
```yaml
type: entities
title: Nästa tåg
entities:
  - entity: sensor.barkarby_southbound_next
  - type: attribute
    entity: sensor.barkarby_southbound_next
    attribute: destination
    name: Destination
  - type: attribute
    entity: sensor.barkarby_southbound_next
    attribute: delay_message
    name: Status
```

## API

This integration uses the public SL Transport API:
- No API key required
- Sites: `https://transport.integration.sl.se/v1/sites`
- Departures: `https://transport.integration.sl.se/v1/sites/{siteId}/departures`

## License

MIT
