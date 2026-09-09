"""Integer 1-share vs cheap 3-share top-up on SMA200-style tapes."""

from __future__ import annotations

import unittest

import pandas as pd

from analysis.qty_backtest import cheap_flags, simulate_qty_book


class CheapFlagTests(unittest.TestCase):
    def test_unique_low_close_is_cheap_after_min_bars(self) -> None:
        close = pd.Series([100.0] * 259 + [40.0])
        flags = cheap_flags(close, lookback=1000, min_bars=252, percentile=0.2)
        self.assertFalse(flags[250])
        self.assertTrue(flags[-1])

    def test_flat_tape_is_not_cheap(self) -> None:
        close = pd.Series([100.0] * 260)
        flags = cheap_flags(close, lookback=1000, min_bars=252, percentile=0.2)
        self.assertFalse(any(flags))


class QtyBookTests(unittest.TestCase):
    def test_cheap_flag_tops_up_from_1_to_3(self) -> None:
        tapes = {
            "CHEAP.US": {
                "open": {
                    "2026-01-01": 10.0,
                    "2026-01-02": 10.0,
                    "2026-01-03": 10.0,
                    "2026-01-04": 12.0,
                },
                "close": {
                    "2026-01-01": 10.0,
                    "2026-01-02": 10.0,
                    "2026-01-03": 10.0,
                    "2026-01-04": 12.0,
                },
                "signal": {
                    "2026-01-01": "BUY",
                    "2026-01-02": "BUY",
                    "2026-01-03": "BUY",
                    "2026-01-04": "BUY",
                },
                "cheap": {
                    "2026-01-01": False,
                    "2026-01-02": True,
                    "2026-01-03": True,
                    "2026-01-04": True,
                },
            }
        }
        one = simulate_qty_book(tapes, 1000.0, qty=1, qty_cheap=1)
        three = simulate_qty_book(tapes, 1000.0, qty=1, qty_cheap=3)
        self.assertEqual(one["shares_bought"], 1)
        self.assertEqual(three["shares_bought"], 3)
        self.assertEqual(three["top_ups"], 1)
        self.assertGreater(three["pnl"], one["pnl"])

    def test_scale_in_adds_one_share_per_buy_day(self) -> None:
        tapes = {
            "ADD.US": {
                "open": {
                    "2026-01-01": 10.0,
                    "2026-01-02": 10.0,
                    "2026-01-03": 10.0,
                    "2026-01-04": 12.0,
                },
                "close": {
                    "2026-01-01": 10.0,
                    "2026-01-02": 10.0,
                    "2026-01-03": 10.0,
                    "2026-01-04": 12.0,
                },
                "signal": {
                    "2026-01-01": "BUY",
                    "2026-01-02": "BUY",
                    "2026-01-03": "BUY",
                    "2026-01-04": "BUY",
                },
                "cheap": {
                    "2026-01-01": False,
                    "2026-01-02": False,
                    "2026-01-03": False,
                    "2026-01-04": False,
                },
            }
        }
        hold = simulate_qty_book(tapes, 1000.0, qty=1, qty_cheap=1, scale_in=False)
        add = simulate_qty_book(tapes, 1000.0, qty=1, qty_cheap=1, scale_in=True)
        self.assertEqual(hold["shares_bought"], 1)
        self.assertEqual(add["shares_bought"], 3)
        self.assertEqual(add["top_ups"], 2)
        self.assertEqual(add["max_held"]["ADD.US"], 3)
        self.assertGreater(add["pnl"], hold["pnl"])

    def test_scale_in_skips_hold_days(self) -> None:
        tapes = {
            "DIP.US": {
                "open": {
                    "2026-01-01": 10.0,
                    "2026-01-02": 10.0,
                    "2026-01-03": 10.0,
                    "2026-01-04": 12.0,
                },
                "close": {
                    "2026-01-01": 10.0,
                    "2026-01-02": 10.0,
                    "2026-01-03": 10.0,
                    "2026-01-04": 12.0,
                },
                "signal": {
                    "2026-01-01": "BUY",
                    "2026-01-02": "HOLD",
                    "2026-01-03": "HOLD",
                    "2026-01-04": "BUY",
                },
                "cheap": {
                    "2026-01-01": False,
                    "2026-01-02": False,
                    "2026-01-03": False,
                    "2026-01-04": False,
                },
            }
        }
        dip = simulate_qty_book(tapes, 1000.0, qty=1, qty_cheap=1, scale_in=True)
        self.assertEqual(dip["shares_bought"], 1)
        self.assertEqual(dip["top_ups"], 0)
        self.assertEqual(dip["max_held"]["DIP.US"], 1)


if __name__ == "__main__":
    unittest.main()
