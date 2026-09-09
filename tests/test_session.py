"""Futu US sessions: 盤前 + 盤中 + 盤後 + 夜盤; closed Sat 04:00-Sun 20:00 ET."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from analysis.session import in_us_rth, in_us_trade_window, us_quote_session

ET = ZoneInfo("America/New_York")


def _et(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=ET)


class SessionWindowTests(unittest.TestCase):
    def test_premarket_included(self) -> None:
        self.assertTrue(in_us_trade_window(_et(2026, 9, 9, 4, 0)))

    def test_regular_included(self) -> None:
        self.assertTrue(in_us_trade_window(_et(2026, 9, 9, 9, 30)))

    def test_afterhours_included(self) -> None:
        self.assertTrue(in_us_trade_window(_et(2026, 9, 9, 20, 0)))

    def test_overnight_before_premarket_included(self) -> None:
        self.assertTrue(in_us_trade_window(_et(2026, 9, 9, 3, 59)))

    def test_overnight_after_afterhours_included(self) -> None:
        self.assertTrue(in_us_trade_window(_et(2026, 9, 9, 20, 1)))

    def test_friday_night_session_into_saturday_included(self) -> None:
        self.assertTrue(in_us_trade_window(_et(2026, 9, 12, 3, 59)))

    def test_saturday_after_overnight_skipped(self) -> None:
        self.assertFalse(in_us_trade_window(_et(2026, 9, 12, 4, 0)))

    def test_saturday_afternoon_skipped(self) -> None:
        self.assertFalse(in_us_trade_window(_et(2026, 9, 12, 12, 0)))

    def test_sunday_before_night_session_skipped(self) -> None:
        self.assertFalse(in_us_trade_window(_et(2026, 9, 13, 19, 59)))

    def test_sunday_night_session_included(self) -> None:
        self.assertTrue(in_us_trade_window(_et(2026, 9, 13, 20, 0)))

    def test_quote_session_names(self) -> None:
        self.assertEqual(us_quote_session(_et(2026, 9, 9, 5, 31)), "pre")
        self.assertEqual(us_quote_session(_et(2026, 9, 9, 10, 0)), "rth")
        self.assertEqual(us_quote_session(_et(2026, 9, 9, 17, 0)), "post")
        self.assertEqual(us_quote_session(_et(2026, 9, 9, 21, 0)), "overnight")
        self.assertEqual(us_quote_session(_et(2026, 9, 12, 12, 0)), "closed")

    def test_rth_is_cash_session_only(self) -> None:
        self.assertFalse(in_us_rth(_et(2026, 9, 9, 5, 31)))
        self.assertTrue(in_us_rth(_et(2026, 9, 9, 9, 30)))
        self.assertTrue(in_us_rth(_et(2026, 9, 9, 15, 59)))
        self.assertFalse(in_us_rth(_et(2026, 9, 9, 16, 0)))
        self.assertFalse(in_us_rth(_et(2026, 9, 12, 12, 0)))

    def test_rth_matches_1330_2000_utc_in_september(self) -> None:
        start = datetime(2026, 9, 9, 13, 30, tzinfo=timezone.utc)
        too_early = datetime(2026, 9, 9, 13, 29, tzinfo=timezone.utc)
        end = datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc)
        self.assertTrue(in_us_rth(start))
        self.assertFalse(in_us_rth(too_early))
        self.assertFalse(in_us_rth(end))

    def test_naive_datetime_treated_as_utc(self) -> None:
        now = datetime(2026, 9, 9, 16, 0)
        self.assertTrue(in_us_trade_window(now))


class HkDisplayTimeTests(unittest.TestCase):
    def test_signal_timestamp_uses_utc_plus_8(self) -> None:
        from analysis.manager import now_hk_iso

        self.assertTrue(now_hk_iso().endswith("+08:00"))


class HiddenCliTests(unittest.TestCase):
    def test_windows_hides_console(self) -> None:
        import subprocess
        import sys
        from unittest.mock import patch

        from analysis.proc import run_hidden

        if sys.platform != "win32":
            self.skipTest("Windows only")
        with patch("analysis.proc.subprocess.run") as mocked:
            mocked.return_value = subprocess.CompletedProcess(["longbridge"], 0, "", "")
            run_hidden(["longbridge", "check"])
            kwargs = mocked.call_args.kwargs
            self.assertEqual(kwargs["creationflags"], subprocess.CREATE_NO_WINDOW)


if __name__ == "__main__":
    unittest.main()
