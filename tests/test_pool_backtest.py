"""Shared-pool cash can buy more after a profitable exit."""

from __future__ import annotations

import unittest

from analysis.pool_backtest import simulate_pool


class PoolBacktestTests(unittest.TestCase):
    def test_exit_cash_buys_a_larger_second_name(self) -> None:
        tapes = {
            "WIN.US": {
                "open": {"2026-01-01": 10.0, "2026-01-02": 10.0, "2026-01-03": 20.0, "2026-01-04": 20.0},
                "close": {"2026-01-01": 10.0, "2026-01-02": 20.0, "2026-01-03": 20.0, "2026-01-04": 20.0},
                "signal": {"2026-01-01": "BUY", "2026-01-02": "SELL", "2026-01-03": "SELL", "2026-01-04": "SELL"},
            },
            "NEXT.US": {
                "open": {"2026-01-01": 10.0, "2026-01-02": 10.0, "2026-01-03": 10.0, "2026-01-04": 10.0},
                "close": {"2026-01-01": 10.0, "2026-01-02": 10.0, "2026-01-03": 10.0, "2026-01-04": 12.0},
                "signal": {"2026-01-01": "SELL", "2026-01-02": "SELL", "2026-01-03": "BUY", "2026-01-04": "BUY"},
            },
        }
        result = simulate_pool(tapes, 2000.0, integer_shares=False)
        self.assertGreater(result["ending_equity"], 2000.0)
        self.assertGreaterEqual(result["buys"], 2)

    def test_pool_waits_until_every_name_is_listed(self) -> None:
        tapes = {
            "EARLY.US": {
                "open": {"2026-01-01": 10.0, "2026-01-02": 10.0, "2026-01-03": 10.0},
                "close": {"2026-01-01": 10.0, "2026-01-02": 10.0, "2026-01-03": 10.0},
                "signal": {"2026-01-01": "BUY", "2026-01-02": "BUY", "2026-01-03": "BUY"},
            },
            "LATE.US": {
                "open": {"2026-01-02": 10.0, "2026-01-03": 10.0},
                "close": {"2026-01-02": 10.0, "2026-01-03": 10.0},
                "signal": {"2026-01-02": "BUY", "2026-01-03": "BUY"},
            },
        }
        result = simulate_pool(tapes, 200.0, integer_shares=False)
        self.assertAlmostEqual(result["ending_equity"], 200.0, delta=0.01)

    def test_integer_skips_unaffordable_slice(self) -> None:
        tapes = {
            "RICH.US": {
                "open": {"2026-01-01": 3000.0, "2026-01-02": 3000.0},
                "close": {"2026-01-01": 3000.0, "2026-01-02": 3000.0},
                "signal": {"2026-01-01": "BUY", "2026-01-02": "BUY"},
            }
        }
        result = simulate_pool(tapes, 2000.0, integer_shares=True)
        self.assertEqual(result["ending_equity"], 2000.0)
        self.assertEqual(result["buys"], 0)


if __name__ == "__main__":
    unittest.main()
