# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Home Assistant custom integration for Stockholm public transit (SL - Storstockholms Lokaltrafik). The integration connects to the SL Transport API to fetch real-time departure information for trains, metro, buses, trams, and ferries.

## SL Transport API

No API key required - publicly accessible.

- **Sites list**: `https://transport.integration.sl.se/v1/sites?expand=true`
- **Departures**: `https://transport.integration.sl.se/v1/sites/{siteId}/departures`

## Integration Structure

```
custom_components/sl_departures/
├── __init__.py      # Integration setup & data coordinator
├── config_flow.py   # UI configuration flow + options flow
├── const.py         # Constants (domain, API URLs, transport modes)
├── manifest.json    # Integration metadata
├── sensor.py        # Departure sensor entity
├── strings.json     # UI strings
├── icon.png         # Integration icon (256x256)
├── icon@2x.png      # High-res icon (512x512)
└── translations/
    ├── en.json      # English translations
    └── sv.json      # Swedish translations
```

## Config Flow

6-step setup wizard:
1. **Search** - User enters station name
2. **Select** - Pick from matching stations (uses `SelectSelectorMode.LIST`)
3. **Transport Mode** - Select transport type (TRAIN, METRO, BUS, TRAM, SHIP, FERRY)
4. **Line** - Select specific line or "All lines" (auto-skipped if only one line available)
5. **Direction** - Filter by direction (fetches actual destinations from API, e.g., "→ Kungsträdgården")
6. **Count** - Number of departures to show (1-5)

## Options Flow

Configurable after setup via "Configure" button (mainly for legacy entries):
- **scan_interval** - Update frequency (30-300 seconds)
- **transport_modes** - Multi-select: TRAIN, METRO, BUS, TRAM, SHIP, FERRY
- **line_filter** - Comma-separated line numbers

## Sensors

Creates N sensors per config entry (based on num_departures):
- State: Display time from API ("4 min", "Nu", "23:45")
- Icon: Transport mode specific (train, subway, bus, tram, ferry) or clock-alert when delayed
- Attributes (compatible with Trafiklab Timetable Card):
  - Card attrs: line, destination, scheduled_time, expected_time, time_formatted, minutes_until, transport_mode, real_time, delay_minutes, canceled, platform, agency
  - Extra attrs: direction, state, stop_area, deviations

## SL API Data Structure

The `sl-api.json` file contains a sample API response. Key data structures:

- **departures**: Array of upcoming departures with:
  - `destination`, `direction`, `direction_code`: Route information
  - `state`: ATSTOP, EXPECTED, NORMALPROGRESS
  - `display`: Human-readable time ("Nu", "4 min", "23:25")
  - `scheduled`/`expected`: ISO timestamps
  - `journey`: Trip metadata including prediction state
  - `stop_area`/`stop_point`: Station info with IDs and designations
  - `line`: Transport line with mode (BUS, TRAIN, METRO, etc.)
  - `deviations`: Service disruption information

- **stop_deviations**: Station-level service alerts

## Transport Modes

The API supports: BUS, TRAIN (Pendeltåg), METRO, TRAM, SHIP, FERRY
