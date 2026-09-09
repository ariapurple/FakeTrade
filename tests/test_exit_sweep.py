"""Hold-plus-exit signal helper."""

from __future__ import annotations

import unittest

import pandas as pd

from analysis.exit_sweep import hold_plus_exit_signals, pick_candidate, rule_grid


def _frame(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1] * len(closes),
        }
    )


class HoldPlusExitTests(unittest.TestCase):
    def test_never_sell_is_all_buy(self) -> None:
        flags = hold_plus_exit_signals(_frame([100.0] * 30 + [40.0] * 10))
        self.assertTrue(all(flag == "BUY" for flag in flags))

    def test_sma_sells_after_window(self) -> None:
        closes = [100.0] * 120 + [50.0] * 10
        flags = hold_plus_exit_signals(_frame(closes), below_sma=100)
        self.assertEqual(flags[50], "BUY")
        self.assertEqual(flags[-1], "SELL")

    def test_need_both_waits_for_drawdown(self) -> None:
        closes = [100.0] * 100 + [80.0] * 20
        or_flags = hold_plus_exit_signals(_frame(closes), below_sma=50, drawdown_from_high=0.5, high_lookback=60)
        and_flags = hold_plus_exit_signals(
            _frame(closes),
            below_sma=50,
            drawdown_from_high=0.5,
            high_lookback=60,
            need_both=True,
        )
        self.assertEqual(or_flags[-1], "SELL")
        self.assertEqual(and_flags[-1], "BUY")

    def test_grid_includes_never_sell_once(self) -> None:
        ids = [row["id"] for row in rule_grid()]
        self.assertEqual(ids.count("never_sell"), 1)

    def test_pick_prefers_plus_30_and_milder_dd(self) -> None:
        picked = pick_candidate(
            [
                {"id": "never_sell", "return_pct": 80.0, "max_drawdown_pct": -40.0, "trades": 11},
                {"id": "sma200", "return_pct": 35.0, "max_drawdown_pct": -18.0, "trades": 20},
                {"id": "clone_hold", "return_pct": 80.0, "max_drawdown_pct": -18.0, "trades": 11},
                {"id": "sma100", "return_pct": 12.0, "max_drawdown_pct": -10.0, "trades": 40},
            ],
            -40.0,
            80.0,
            11,
        )
        self.assertEqual(picked["id"], "sma200")


if __name__ == "__main__":
    unittest.main()
