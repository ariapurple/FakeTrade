"""Session-aware Longbridge last: 盤前 uses pre_market, not the RTH close."""

from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from analysis.quote import parse_live_price

ET = ZoneInfo("America/New_York")

AAPL_QUOTE = {
    "symbol": "AAPL.US",
    "last": "316.220",
    "pre_market": {"last": "315.785"},
    "post_market": {"last": "316.340"},
    "overnight": {"last": "316.930"},
}


class LiveQuoteTests(unittest.TestCase):
    def test_premarket_ignores_stale_rth_last(self) -> None:
        live = parse_live_price(AAPL_QUOTE, datetime(2026, 9, 9, 5, 31, tzinfo=ET))
        assert live is not None
        self.assertEqual(live["price"], 315.785)
        self.assertEqual(live["source"], "pre_market")
        self.assertEqual(live["session"], "pre")

    def test_regular_hours_uses_last(self) -> None:
        live = parse_live_price(AAPL_QUOTE, datetime(2026, 9, 9, 10, 0, tzinfo=ET))
        assert live is not None
        self.assertEqual(live["price"], 316.220)
        self.assertEqual(live["source"], "last")

    def test_overnight_uses_overnight_tape(self) -> None:
        live = parse_live_price(AAPL_QUOTE, datetime(2026, 9, 9, 21, 0, tzinfo=ET))
        assert live is not None
        self.assertEqual(live["price"], 316.930)
        self.assertEqual(live["source"], "overnight")


if __name__ == "__main__":
    unittest.main()
