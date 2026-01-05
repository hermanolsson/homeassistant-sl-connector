"""Constants for SL Departures integration."""

DOMAIN = "sl_departures"

API_BASE_URL = "https://transport.integration.sl.se/v1"
API_SITES_URL = f"{API_BASE_URL}/sites"
API_DEPARTURES_URL = f"{API_BASE_URL}/sites/{{site_id}}/departures"

DEFAULT_SCAN_INTERVAL = 60  # seconds
DEFAULT_NUM_DEPARTURES = 3

TRANSPORT_MODES = {
    "TRAIN": "Train (Pendeltåg)",
    "METRO": "Metro (Tunnelbana)",
    "BUS": "Bus",
    "TRAM": "Tram (Spårvagn)",
    "SHIP": "Ship",
    "FERRY": "Ferry",
}
