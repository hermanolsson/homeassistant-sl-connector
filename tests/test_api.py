"""Tests for the dependency-free helpers in sl_departures.api."""
from datetime import datetime, timedelta, timezone
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
    def test_first_failure_retries_at_normal_interval(self):
        self.assertEqual(api.backoff_seconds(120, 1), 120)

    def test_later_failures_capped_at_twice_the_interval(self):
        self.assertEqual(api.backoff_seconds(120, 2), 240)
        self.assertEqual(api.backoff_seconds(120, 10), 240)

    def test_retry_after_wins_when_larger(self):
        self.assertEqual(api.backoff_seconds(60, 1, retry_after=300), 300)

    def test_retry_after_does_not_shorten_backoff(self):
        self.assertEqual(api.backoff_seconds(60, 3, retry_after=5), 120)

    def test_retry_after_capped(self):
        self.assertEqual(api.backoff_seconds(60, 1, retry_after=99999), api.MAX_BACKOFF)


class WithJitterTest(unittest.TestCase):
    def test_bounds(self):
        self.assertEqual(api.with_jitter(100, 0.1, rand=lambda: 0.0), 100)
        self.assertAlmostEqual(api.with_jitter(100, 0.1, rand=lambda: 1.0), 110)

    def test_default_random_stays_in_range(self):
        for _ in range(100):
            self.assertTrue(100 <= api.with_jitter(100, 0.1) <= 110)


class DropDepartedTest(unittest.TestCase):
    NOW = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)

    @staticmethod
    def d(expected=None, scheduled=None):
        out = {}
        if expected:
            out["expected"] = expected
        if scheduled:
            out["scheduled"] = scheduled
        return out

    def test_drops_departed_keeps_upcoming_and_grace(self):
        gone = self.d("2026-09-29T09:58:00Z")
        just_left = self.d("2026-09-29T09:59:30Z")  # inside 60s grace: shows "Nu"
        later = self.d("2026-09-29T10:05:00Z")
        self.assertEqual(api.drop_departed([gone, just_left, later], self.NOW), [just_left, later])

    def test_falls_back_to_scheduled_then_keeps_unknown(self):
        old_sched = self.d(scheduled="2026-09-29T09:00:00Z")
        unknown = self.d()
        self.assertEqual(api.drop_departed([old_sched, unknown], self.NOW), [unknown])

    def test_expected_beats_scheduled(self):
        delayed = self.d(expected="2026-09-29T10:10:00Z", scheduled="2026-09-29T09:00:00Z")
        self.assertEqual(api.drop_departed([delayed], self.NOW), [delayed])

    def test_naive_timestamps_are_local_time(self):
        five_min_ago = (self.NOW - timedelta(minutes=5)).astimezone().replace(tzinfo=None)
        in_five = (self.NOW + timedelta(minutes=5)).astimezone().replace(tzinfo=None)
        gone, coming = self.d(five_min_ago.isoformat()), self.d(in_five.isoformat())
        self.assertEqual(api.drop_departed([gone, coming], self.NOW), [coming])

    def test_garbage_timestamp_is_kept(self):
        junk = self.d("not-a-time")
        self.assertEqual(api.drop_departed([junk], self.NOW), [junk])


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
