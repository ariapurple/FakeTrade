"""Synthetic-bar checks for daily vs dual-timeframe backtest helpers."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import pandas as pd

from analysis.agents import value_investing
from analysis.backtest import dual_tf_decision, last_completed_daily_idx, rows_to_frame, simulate_long_only


def _iso(stamp: datetime) -> str:
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


class BacktestHelperTests(unittest.TestCase):
    def test_long_only_buy_then_sell(self) -> None:
        times = [
            pd.Timestamp("2026-09-01T13:30:00Z"),
            pd.Timestamp("2026-09-01T13:35:00Z"),
            pd.Timestamp("2026-09-01T13:40:00Z"),
        ]
        result = simulate_long_only(times, [10.0, 11.0, 12.0], [10.5, 11.5, 13.0], ["BUY", "HOLD", "HOLD"])
        self.assertEqual(result["trades"], 1)
        self.assertGreater(result["pnl"], 0)

    def test_no_lookahead_on_same_day_daily_bar(self) -> None:
        start = datetime(2026, 9, 1, 4, 0, tzinfo=timezone.utc)
        rows = []
        for day in range(3):
            stamp = start + timedelta(days=day)
            rows.append(
                {
                    "time": _iso(stamp),
                    "open": 100,
                    "high": 101,
                    "low": 99,
                    "close": 100,
                    "volume": 1,
                }
            )
        daily = rows_to_frame(rows)
        during_rth = pd.Timestamp("2026-09-03T15:00:00Z")
        idx = last_completed_daily_idx(daily, during_rth)
        self.assertIsNotNone(idx)
        self.assertEqual(daily.at[idx, "time"], pd.Timestamp("2026-09-02T04:00:00Z"))

    def test_dual_requires_daily_trend(self) -> None:
        daily_rows = []
        price = 50.0
        start = datetime(2026, 6, 1, 4, 0, tzinfo=timezone.utc)
        for i in range(60):
            price += 0.4
            stamp = start + timedelta(days=i)
            daily_rows.append(
                {
                    "time": _iso(stamp),
                    "open": price - 0.2,
                    "high": price + 0.3,
                    "low": price - 0.3,
                    "close": price,
                    "volume": 1000,
                }
            )
        fast_rows = []
        fast_start = datetime(2026, 8, 1, 13, 30, tzinfo=timezone.utc)
        fast_price = 40.0
        for i in range(80):
            fast_price -= 0.5 if i < 70 else 0.05
            stamp = fast_start + timedelta(minutes=5 * i)
            vol = 5000 if i == 79 else 100
            o = fast_price + 0.4
            c = fast_price
            fast_rows.append(
                {
                    "time": _iso(stamp),
                    "open": o,
                    "high": max(o, c),
                    "low": min(o, c),
                    "close": c,
                    "volume": vol,
                }
            )
        daily = rows_to_frame(daily_rows)
        fast = rows_to_frame(fast_rows)
        signal = dual_tf_decision(daily, 59, fast, 79)
        self.assertIn(signal, {"BUY", "HOLD"})
        value_investing({"pe": 25})


class QuantParseTests(unittest.TestCase):
    def test_parse_bar_start_events(self) -> None:
        from analysis.backtest import parse_quant_ohlcv

        payload = {
            "events_json": [
                {"sessionInfo": {}},
                {
                    "barStart": {
                        "candlestick": {
                            "time": 1788278400000,
                            "open": 1,
                            "high": 2,
                            "low": 0.5,
                            "close": 1.5,
                            "volume": 10,
                        }
                    }
                },
                "barEnd",
            ]
        }
        rows = parse_quant_ohlcv(payload)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["close"], 1.5)


if __name__ == "__main__":
    unittest.main()
