"""Tests for the dependency-free helpers in sl_departures.api."""
import importlib.util
import pathlib
import sys
import unittest

_PATH = pathlib.Path(__file__).parent.parent / "custom_components" / "sl_departures" / "api.py"
_spec = importlib.util.spec_from_file_location("sl_api_helpers", _PATH)
api = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = api
_spec.loader.exec_module(api)


def dep(mode="METRO", line="14", direction_code=1):
    return {
        "line": {"transport_mode": mode, "designation": line},
        "direction_code": direction_code,
    }


class ParseRetryAfterTest(unittest.TestCase):
    def test_seconds(self):
        self.assertEqual(api.parse_retry_after("30"), 30)

    def test_missing_or_garbage(self):
        self.assertIsNone(api.parse_retry_after(None))
        self.assertIsNone(api.parse_retry_after("soon"))
        self.assertIsNone(api.parse_retry_after("-5"))


class BackoffSecondsTest(unittest.TestCase):
    def test_doubles_per_failure(self):
        self.assertEqual(api.backoff_seconds(60, 1), 120)
        self.assertEqual(api.backoff_seconds(60, 2), 240)

    def test_capped(self):
        self.assertEqual(api.backoff_seconds(60, 10), api.MAX_BACKOFF)

    def test_retry_after_wins_when_larger(self):
        self.assertEqual(api.backoff_seconds(60, 1, retry_after=300), 300)

    def test_retry_after_does_not_shorten_backoff(self):
        self.assertEqual(api.backoff_seconds(60, 2, retry_after=5), 240)

    def test_retry_after_capped(self):
        self.assertEqual(api.backoff_seconds(60, 1, retry_after=99999), api.MAX_BACKOFF)


class IsRetryableStatusTest(unittest.TestCase):
    def test_statuses(self):
        for status in (429, 500, 502, 503):
            self.assertTrue(api.is_backoff_status(status), status)
        for status in (200, 400, 404):
            self.assertFalse(api.is_backoff_status(status), status)


class DepartureFilterTest(unittest.TestCase):
    def test_mode_direction_and_line(self):
        deps = [dep("METRO", "14", 1), dep("METRO", "14", 2), dep("BUS", "4", 1), dep("METRO", "13", 1)]
        f = api.DepartureFilter(["METRO"], "1", "14")
        self.assertEqual(f.apply(deps), [deps[0]])

    def test_multiple_lines(self):
        deps = [dep("BUS", "4"), dep("BUS", "1"), dep("BUS", "2")]
        f = api.DepartureFilter(["BUS"], "", "4, 2")
        self.assertEqual(f.apply(deps), [deps[0], deps[2]])

    def test_from_entry_new_style(self):
        f = api.DepartureFilter.from_entry(
            {"transport_mode": "TRAIN", "line": "40", "direction_code": "2"}, {}
        )
        self.assertEqual((f.transport_modes, f.line_filter, f.direction_code), (["TRAIN"], "40", "2"))

    def test_from_entry_legacy_options(self):
        f = api.DepartureFilter.from_entry(
            {}, {"transport_modes": ["BUS", "TRAM"], "line_filter": "1"}
        )
        self.assertEqual((f.transport_modes, f.line_filter), (["BUS", "TRAM"], "1"))

    def test_from_entry_defaults_to_train(self):
        self.assertEqual(api.DepartureFilter.from_entry({}, {}).transport_modes, ["TRAIN"])


if __name__ == "__main__":
    unittest.main()
