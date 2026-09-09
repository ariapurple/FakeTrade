"""Donchian signals must not use the same bar's high as the breakout level."""

from __future__ import annotations

import unittest

import pandas as pd

from analysis.theory_backtest import donchian_20_10, simulate, simulate_buy_hold_capital, simulate_capital


class TheoryStrategyTests(unittest.TestCase):
    def test_donchian_uses_prior_window(self) -> None:
        rows = []
        for idx in range(80):
            close = 10.0 if idx < 70 else 20.0
            rows.append(
                {
                    "open": close,
                    "high": close,
                    "low": close - 0.05,
                    "close": close,
                    "volume": 100,
                }
            )
        frame = pd.DataFrame(rows)
        signals = donchian_20_10(frame)
        self.assertEqual(signals[70], "BUY")

    def test_long_only_buy_sell(self) -> None:
        times = [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-02"), pd.Timestamp("2026-01-03")]
        result = simulate(times, [10.0, 11.0, 12.0], [10.0, 11.0, 13.0], ["BUY", "SELL", "HOLD"], "long_only")
        self.assertEqual(result["trades"], 1)
        self.assertGreater(result["pnl"], 0)

    def test_capital_buy_hold_scales_with_price(self) -> None:
        times = [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-02")]
        result = simulate_buy_hold_capital(times, [10.0, 11.0], [10.5, 12.0], 100.0)
        self.assertEqual(result["trades"], 1)
        self.assertAlmostEqual(result["ending_equity"], 120.0, places=4)
        self.assertAlmostEqual(result["pnl"], 20.0, places=4)
        self.assertAlmostEqual(result["return_pct"], 20.0, places=4)

    def test_capital_long_only_spends_full_sleeve(self) -> None:
        times = [
            pd.Timestamp("2026-01-01"),
            pd.Timestamp("2026-01-02"),
            pd.Timestamp("2026-01-03"),
        ]
        result = simulate_capital(
            times, [10.0, 10.0, 12.0], [10.0, 10.0, 12.0], ["BUY", "SELL", "HOLD"], "long_only", 100.0
        )
        self.assertEqual(result["trades"], 1)
        self.assertAlmostEqual(result["ending_equity"], 120.0, places=4)
        self.assertAlmostEqual(result["return_pct"], 20.0, places=4)


if __name__ == "__main__":
    unittest.main()
