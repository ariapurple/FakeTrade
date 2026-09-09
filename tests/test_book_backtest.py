"""Live book-signal helpers match agent last-bar decisions."""

from __future__ import annotations

import unittest

import pandas as pd

from analysis.agents import buy_hold_exits, ma_swing
from analysis.book_backtest import buy_hold_exit_signals, rth_mask, swing_signals


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


def _qh(frame: pd.DataFrame) -> dict[str, list[float]]:
    return {
        "Open": frame["open"].astype(float).tolist(),
        "High": frame["high"].astype(float).tolist(),
        "Low": frame["low"].astype(float).tolist(),
        "Close": frame["close"].astype(float).tolist(),
        "Volume": frame["volume"].astype(float).tolist(),
    }


class BookSignalTests(unittest.TestCase):
    def test_crash_matches_agent_sell(self) -> None:
        frame = _frame([100.0] * 70 + [70.0] * 10)
        flags = buy_hold_exit_signals(frame)
        plan = buy_hold_exits(_qh(frame))
        self.assertEqual(flags[-1], "SELL")
        self.assertEqual(plan["signal"], "SELL")

    def test_never_sell_signals_are_all_buy(self) -> None:
        frame = _frame([100.0] * 70 + [40.0] * 10)
        flags = buy_hold_exit_signals(frame, below_sma=0, drawdown_from_high=0.0)
        self.assertTrue(all(flag == "BUY" for flag in flags))

    def test_uptrend_swing_matches_agent(self) -> None:
        frame = _frame(list(range(1, 80)))
        flags = swing_signals(frame)
        agent = ma_swing(_qh(frame))
        self.assertEqual(flags[-1], "BUY")
        self.assertEqual(agent["signal"], "BUY")

    def test_rth_mask_skips_intraday_outside_cash_hours(self) -> None:
        times = [
            pd.Timestamp("2026-09-09T09:31:00Z"),
            pd.Timestamp("2026-09-09T14:00:00Z"),
        ]
        mask = rth_mask(times, "1h")
        self.assertEqual(mask, [False, True])
        self.assertTrue(all(rth_mask(times, "day")))


if __name__ == "__main__":
    unittest.main()
