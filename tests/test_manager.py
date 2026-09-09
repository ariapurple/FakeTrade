"""Buy-and-hold exits, swing regime, and strategy aliases."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from analysis.agents import buy_hold_exits, ma_swing, multi_year_cheap
from analysis.manager import add_style_from_raw, live_extension_pct, run_watchlist, strategy_from_config, _buy_cfg


def _bars(closes: list[float]) -> list[dict[str, float | str]]:
    rows = []
    for idx, close in enumerate(closes):
        rows.append(
            {
                "time": f"2026-01-01T00:00:00Z",
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 100,
            }
        )
        del idx
    return rows


class StrategyConfigTests(unittest.TestCase):
    def test_aliases(self) -> None:
        self.assertEqual(strategy_from_config({"strategy": "buy_hold"}), "buy_hold")
        self.assertEqual(strategy_from_config({"strategy": "buy-and-hold"}), "buy_hold")
        self.assertEqual(strategy_from_config({"strategy": "swing"}), "swing")
        self.assertEqual(strategy_from_config({}), "vote")
        self.assertEqual(strategy_from_config({"strategy": "vote"}), "vote")

    def test_buy_add_switch(self) -> None:
        self.assertEqual(add_style_from_raw("always_add"), "always_add")
        self.assertEqual(add_style_from_raw("dip-add"), "dip_add")
        always = _buy_cfg({"buy": {"add": "always_add", "max_extension_pct": 0.08}})
        dip = _buy_cfg({"buy": {"add": "dip_add", "max_extension_pct": 0.08}})
        inferred = _buy_cfg({"buy": {"max_extension_pct": 0.08}})
        self.assertEqual(always["add"], "always_add")
        self.assertEqual(live_extension_pct(always), 0.0)
        self.assertEqual(dip["add"], "dip_add")
        self.assertEqual(live_extension_pct(dip), 0.08)
        self.assertEqual(inferred["add"], "dip_add")
        with self.assertRaises(ValueError):
            add_style_from_raw("swing")


class BuyHoldWatchlistTests(unittest.TestCase):
    @patch("analysis.manager.fetch_quotes", return_value={})
    @patch("analysis.manager.news_gate", return_value={"signal": "HOLD", "reason": "quiet", "hits": []})
    @patch("analysis.manager.fetch_klines")
    @patch("analysis.manager.fetch_calc_index")
    def test_stays_buy_when_price_holds(self, calc_index, fetch_klines, _news, _quotes) -> None:
        fetch_klines.return_value = _bars([10.0] * 80)
        payload = run_watchlist(
            {
                "symbols": ["AAPL.US"],
                "strategy": "buy_hold",
                "period": "day",
                "count": 80,
                "qty": 1,
                "execution": "dry-run",
                "news": False,
            }
        )
        calc_index.assert_not_called()
        row = payload["results"][0]
        self.assertEqual(payload["config"]["strategy"], "buy_hold")
        self.assertEqual(row["final_decision"], "BUY")
        self.assertEqual(row["detailed_reports"]["buy_hold"]["signal"], "BUY")

    @patch("analysis.manager.fetch_quotes", return_value={})
    @patch("analysis.manager.news_gate", return_value={"signal": "HOLD", "reason": "off", "hits": []})
    @patch("analysis.manager.fetch_klines")
    @patch("analysis.manager.fetch_calc_index")
    def test_never_sells_without_sell_block(self, calc_index, fetch_klines, _news, _quotes) -> None:
        fetch_klines.return_value = _bars([100.0] * 70 + [40.0] * 10)
        payload = run_watchlist(
            {
                "symbols": ["AAPL.US"],
                "strategy": "buy_hold",
                "period": "day",
                "count": 80,
                "qty": 1,
                "execution": "dry-run",
                "news": False,
            }
        )
        calc_index.assert_not_called()
        row = payload["results"][0]
        self.assertEqual(row["final_decision"], "BUY")
        self.assertEqual(payload["config"]["sell"]["below_sma"], 0)

    @patch("analysis.manager.fetch_quotes", return_value={})
    @patch("analysis.manager.news_gate", return_value={"signal": "HOLD", "reason": "quiet", "hits": []})
    @patch("analysis.manager.fetch_klines")
    @patch("analysis.manager.fetch_calc_index")
    def test_sell_block_still_exits(self, calc_index, fetch_klines, _news, _quotes) -> None:
        fetch_klines.return_value = _bars([100.0] * 70 + [40.0] * 10)
        payload = run_watchlist(
            {
                "symbols": ["AAPL.US"],
                "strategy": "buy_hold",
                "period": "day",
                "count": 80,
                "qty": 1,
                "execution": "dry-run",
                "news": False,
                "sell": {"below_sma": 60, "drawdown_from_high": 0.25, "high_lookback": 60},
            }
        )
        calc_index.assert_not_called()
        self.assertEqual(payload["results"][0]["final_decision"], "SELL")

    @patch("analysis.quote.us_quote_session", return_value="rth")
    @patch("analysis.manager.fetch_quotes")
    @patch("analysis.manager.news_gate", return_value={"signal": "HOLD", "reason": "off", "hits": []})
    @patch("analysis.manager.fetch_klines")
    @patch("analysis.manager.fetch_calc_index")
    def test_sim_sma200_exit(self, calc_index, fetch_klines, _news, fetch_quotes, _session) -> None:
        fetch_klines.return_value = _bars([100.0] * 220)
        fetch_quotes.return_value = {"AAPL.US": {"symbol": "AAPL.US", "last": "90"}}
        payload = run_watchlist(
            {
                "symbols": ["AAPL.US"],
                "strategy": "buy_hold",
                "period": "day",
                "count": 300,
                "qty": 1,
                "execution": "futu-sim",
                "news": False,
                "sell": {
                    "below_sma": 200,
                    "drawdown_from_high": 0,
                    "high_lookback": 0,
                    "news": False,
                },
            }
        )
        calc_index.assert_not_called()
        self.assertEqual(payload["results"][0]["final_decision"], "SELL")
        fetch_quotes.return_value = {"AAPL.US": {"symbol": "AAPL.US", "last": "110"}}
        stay = run_watchlist(
            {
                "symbols": ["AAPL.US"],
                "strategy": "buy_hold",
                "period": "day",
                "count": 300,
                "qty": 1,
                "execution": "futu-sim",
                "news": False,
                "sell": {
                    "below_sma": 200,
                    "drawdown_from_high": 0,
                    "high_lookback": 0,
                    "news": False,
                },
            }
        )
        self.assertEqual(stay["results"][0]["final_decision"], "BUY")

    @patch("analysis.quote.us_quote_session", return_value="rth")
    @patch("analysis.manager.fetch_quotes")
    @patch("analysis.manager.news_gate", return_value={"signal": "HOLD", "reason": "off", "hits": []})
    @patch("analysis.manager.fetch_klines")
    @patch("analysis.manager.fetch_calc_index")
    def test_dip_in_expansion_hold_is_not_remapped_to_buy(
        self, calc_index, fetch_klines, _news, fetch_quotes, _session
    ) -> None:
        fetch_klines.return_value = _bars([100.0] * 220)
        fetch_quotes.return_value = {"AAPL.US": {"symbol": "AAPL.US", "last": "110"}}
        book = {
            "symbols": ["AAPL.US"],
            "strategy": "buy_hold",
            "period": "day",
            "count": 300,
            "qty": 1,
            "execution": "futu-sim",
            "news": False,
            "buy": {"max_extension_pct": 0.08},
            "sell": {
                "below_sma": 200,
                "drawdown_from_high": 0,
                "high_lookback": 0,
                "news": False,
            },
        }
        stretched = run_watchlist(book)
        calc_index.assert_not_called()
        self.assertEqual(stretched["results"][0]["final_decision"], "HOLD")
        self.assertEqual(stretched["actionable"], [])
        self.assertEqual(stretched["config"]["buy"]["max_extension_pct"], 0.08)
        fetch_quotes.return_value = {"AAPL.US": {"symbol": "AAPL.US", "last": "105"}}
        near = run_watchlist(book)
        self.assertEqual(near["results"][0]["final_decision"], "BUY")

        book["buy"] = {"add": "always_add", "max_extension_pct": 0.08}
        fetch_quotes.return_value = {"AAPL.US": {"symbol": "AAPL.US", "last": "110"}}
        always = run_watchlist(book)
        self.assertEqual(always["results"][0]["final_decision"], "BUY")
        self.assertEqual(always["config"]["buy"]["add"], "always_add")
        self.assertEqual(live_extension_pct(always["config"]["buy"]), 0.0)

    @patch("analysis.manager.fetch_quotes", return_value={})
    @patch("analysis.manager.news_gate", return_value={"signal": "HOLD", "reason": "off", "hits": []})
    @patch("analysis.manager.fetch_klines")
    @patch("analysis.manager.fetch_calc_index")
    def test_buy_qty_stays_one(self, calc_index, fetch_klines, _news, _quotes) -> None:
        fetch_klines.return_value = _bars([100.0] * 259 + [40.0])
        payload = run_watchlist(
            {
                "symbols": ["AAPL.US"],
                "strategy": "buy_hold",
                "period": "day",
                "count": 300,
                "qty": 1,
                "execution": "dry-run",
                "news": False,
                "sell": {"below_sma": 0, "drawdown_from_high": 0, "high_lookback": 0},
            }
        )
        calc_index.assert_not_called()
        row = payload["results"][0]
        self.assertEqual(row["final_decision"], "BUY")
        self.assertEqual(row["qty"], 1)
        self.assertNotIn("qty_cheap", payload["config"])

    def test_exits_below_sma(self) -> None:
        closes = [100.0] * 70 + [70.0] * 10
        kline = {
            "Close": closes,
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Volume": [1] * 80,
        }
        plan = buy_hold_exits(kline, below_sma=60, drawdown_from_high=0.9, high_lookback=60)
        self.assertEqual(plan["signal"], "SELL")

    def test_exits_on_drawdown(self) -> None:
        closes = [100.0] * 50 + [70.0] * 10
        kline = {
            "Close": closes,
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Volume": [1] * 60,
        }
        plan = buy_hold_exits(kline, below_sma=200, drawdown_from_high=0.25, high_lookback=60)
        self.assertEqual(plan["signal"], "SELL")

    def test_live_premarket_below_sma_exits(self) -> None:
        closes = [100.0] * 80
        kline = {
            "Close": closes,
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Volume": [1] * 80,
        }
        plan = buy_hold_exits(kline, below_sma=60, last_price=50.0)
        self.assertEqual(plan["signal"], "SELL")
        self.assertEqual(plan["close"], 50.0)

    def test_dip_in_expansion_holds_when_stretched(self) -> None:
        kline = {
            "Close": [100.0] * 80,
            "Open": [100.0] * 80,
            "High": [100.0] * 80,
            "Low": [100.0] * 80,
            "Volume": [1] * 80,
        }
        stretched = buy_hold_exits(
            kline,
            below_sma=60,
            drawdown_from_high=0.0,
            high_lookback=0,
            last_price=109.0,
            max_extension_pct=0.08,
        )
        near = buy_hold_exits(
            kline,
            below_sma=60,
            drawdown_from_high=0.0,
            high_lookback=0,
            last_price=105.0,
            max_extension_pct=0.08,
        )
        self.assertEqual(stretched["signal"], "HOLD")
        self.assertEqual(near["signal"], "BUY")

    def test_dip_in_expansion_still_sells_below_sma(self) -> None:
        kline = {
            "Close": [100.0] * 80,
            "Open": [100.0] * 80,
            "High": [100.0] * 80,
            "Low": [100.0] * 80,
            "Volume": [1] * 80,
        }
        plan = buy_hold_exits(
            kline,
            below_sma=60,
            drawdown_from_high=0.0,
            high_lookback=0,
            last_price=90.0,
            max_extension_pct=0.08,
        )
        self.assertEqual(plan["signal"], "SELL")

    def test_news_sell_overrides(self) -> None:
        kline = {"Close": [100.0] * 80, "Open": [100.0] * 80, "High": [100.0] * 80, "Low": [100.0] * 80, "Volume": [1] * 80}
        plan = buy_hold_exits(
            kline,
            news_report={"signal": "SELL", "reason": "bankruptcy headline"},
        )
        self.assertEqual(plan["signal"], "SELL")


class MultiYearCheapTests(unittest.TestCase):
    def test_bottom_print_is_cheap(self) -> None:
        closes = [100.0] * 259 + [40.0]
        kline = {
            "Close": closes,
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Volume": [1] * len(closes),
        }
        report = multi_year_cheap(kline, min_bars=252, percentile=0.2)
        self.assertTrue(report["cheap"])

    def test_flat_history_is_not_cheap(self) -> None:
        closes = [100.0] * 260
        kline = {
            "Close": closes,
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Volume": [1] * 260,
        }
        report = multi_year_cheap(kline, min_bars=252, percentile=0.2)
        self.assertFalse(report["cheap"])

    def test_short_listing_is_not_cheap(self) -> None:
        closes = [10.0] * 80
        kline = {
            "Close": closes,
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Volume": [1] * 80,
        }
        report = multi_year_cheap(kline, min_bars=252, percentile=0.2)
        self.assertFalse(report["cheap"])


class SwingTests(unittest.TestCase):
    def test_fast_above_slow_is_buy(self) -> None:
        closes = list(range(1, 40))
        kline = {
            "Close": closes,
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Volume": [1] * len(closes),
        }
        self.assertEqual(ma_swing(kline)["signal"], "BUY")

    def test_fast_below_slow_is_sell(self) -> None:
        closes = list(range(40, 0, -1))
        kline = {
            "Close": closes,
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Volume": [1] * len(closes),
        }
        self.assertEqual(ma_swing(kline)["signal"], "SELL")


if __name__ == "__main__":
    unittest.main()
