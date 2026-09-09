"""Futu 模拟盘 mapping and SIMULATE-only guards. No live OpenD required."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

import pandas as pd

from analysis.executor import execute, log_exit_code, mode_from_config
from analysis.futu_sim import (
    FutuSimBroker,
    FutuSimError,
    OpenDDownError,
    book_notional,
    held_qty,
    pick_simulate_account,
    to_futu_code,
)


class FakeTradeContext:
    def __init__(self) -> None:
        self.place_calls: list[dict[str, Any]] = []
        self.cancel_calls: list[dict[str, Any]] = []
        self.closed = False

    def get_acc_list(self) -> tuple[int, pd.DataFrame]:
        return 0, pd.DataFrame(
            [
                {
                    "acc_id": 111,
                    "trd_env": "REAL",
                    "sim_acc_type": "NONE",
                    "trdmarket_auth": ["US"],
                    "acc_status": "ACTIVE",
                    "acc_type": "CASH",
                },
                {
                    "acc_id": 222,
                    "trd_env": "SIMULATE",
                    "sim_acc_type": "STOCK_AND_OPTION",
                    "trdmarket_auth": ["US"],
                    "acc_status": "ACTIVE",
                    "acc_type": "MARGIN",
                },
                {
                    "acc_id": 333,
                    "trd_env": "SIMULATE",
                    "sim_acc_type": "FUTURES",
                    "trdmarket_auth": ["US"],
                    "acc_status": "ACTIVE",
                    "acc_type": "MARGIN",
                },
            ]
        )

    def place_order(self, **kwargs: Any) -> tuple[int, pd.DataFrame]:
        self.place_calls.append(kwargs)
        return 0, pd.DataFrame(
            [
                {
                    "order_id": "sim-1",
                    "order_status": "SUBMITTED",
                    "code": kwargs["code"],
                    "qty": kwargs["qty"],
                    "price": kwargs["price"],
                    "dealt_qty": 0,
                }
            ]
        )

    def accinfo_query(self, **_kwargs: Any) -> tuple[int, pd.DataFrame]:
        return 0, pd.DataFrame([{"cash": 50000.0, "us_cash": 50000.0, "total_assets": 50000.0}])

    def position_list_query(self, **_kwargs: Any) -> tuple[int, pd.DataFrame]:
        return 0, pd.DataFrame([])

    def close(self) -> None:
        self.closed = True

    def order_list_query(self, **_kwargs: Any) -> tuple[int, pd.DataFrame]:
        return 0, pd.DataFrame(
            [
                {
                    "order_id": "9174444",
                    "order_status": "SUBMITTING",
                    "code": "US.AAPL",
                    "qty": 1,
                    "price": 316.22,
                    "trd_side": "BUY",
                }
            ]
        )

    def modify_order(self, *args: Any, **kwargs: Any) -> tuple[int, pd.DataFrame]:
        self.cancel_calls.append({"args": args, "kwargs": kwargs})
        return 0, pd.DataFrame([{"order_id": args[1] if len(args) > 1 else "", "order_status": "CANCELLED_ALL"}])


class MappingTests(unittest.TestCase):
    def test_longbridge_to_futu(self) -> None:
        self.assertEqual(to_futu_code("AAPL.US"), "US.AAPL")
        self.assertEqual(to_futu_code("nvda.us"), "US.NVDA")
        self.assertEqual(to_futu_code("00700.HK"), "HK.00700")

    def test_held_qty_matches_futu_code(self) -> None:
        positions = [{"code": "US.NVDA", "qty": 1}, {"code": "US.AAPL", "qty": 0}]
        self.assertEqual(held_qty(positions, "NVDA.US"), 1)
        self.assertEqual(held_qty(positions, "AAPL.US"), 0)
        self.assertEqual(held_qty(positions, "VOO.US"), 0)

    def test_book_notional_only_counts_that_books_names(self) -> None:
        positions = [
            {"code": "US.AAPL", "qty": 1, "market_val": 316.0},
            {"code": "US.AMD", "qty": 1, "market_val": 500.0},
        ]
        self.assertEqual(book_notional(positions, ["AAPL.US", "NVDA.US"]), 316.0)
        self.assertEqual(book_notional(positions, ["AMD.US"]), 500.0)

    def test_picks_us_stock_simulate_not_real_or_futures(self) -> None:
        rows = FakeTradeContext().get_acc_list()[1].to_dict(orient="records")
        chosen = pick_simulate_account(rows, "US")
        self.assertEqual(int(chosen["acc_id"]), 222)

    def test_refuses_real_account_id(self) -> None:
        rows = FakeTradeContext().get_acc_list()[1].to_dict(orient="records")
        with self.assertRaises(FutuSimError) as ctx:
            pick_simulate_account(rows, "US", acc_id=111)
        self.assertIn("REAL", str(ctx.exception))


class BrokerTests(unittest.TestCase):
    def test_place_order_is_simulate_only(self) -> None:
        fake = FakeTradeContext()

        def factory(_host: str, _port: int, _market: Any, _firm: Any) -> FakeTradeContext:
            return fake

        broker = FutuSimBroker(host="127.0.0.1", port=11111, context_factory=factory)
        with patch("analysis.futu_sim.opend_up", return_value=True):
            info = broker.connect("US")
            fill = broker.place_simulate(symbol="NVDA.US", side="BUY", qty=1, price=225.73)
        self.assertEqual(info["acc_id"], 222)
        self.assertEqual(info["trd_env"], "SIMULATE")
        self.assertEqual(fill["status"], "futu-sim-submitted")
        self.assertEqual(fill["futu_code"], "US.NVDA")
        self.assertEqual(len(fake.place_calls), 1)
        env = fake.place_calls[0]["trd_env"]
        env_name = getattr(env, "name", env)
        self.assertEqual(str(env_name).upper(), "SIMULATE")
        session = fake.place_calls[0].get("session")
        session_name = str(getattr(session, "name", session) or "NONE").upper()
        self.assertIn(session_name, {"RTH", "NONE"})
        broker.close()
        self.assertTrue(fake.closed)

    def test_cancel_open_is_simulate_only(self) -> None:
        fake = FakeTradeContext()

        def factory(_host: str, _port: int, _market: Any, _firm: Any) -> FakeTradeContext:
            return fake

        broker = FutuSimBroker(host="127.0.0.1", port=11111, context_factory=factory)
        with patch("analysis.futu_sim.opend_up", return_value=True):
            broker.connect("US")
            cancelled = broker.cancel_open_orders()
        self.assertEqual(len(cancelled), 1)
        self.assertEqual(cancelled[0]["status"], "cancelled")
        self.assertEqual(cancelled[0]["trd_env"], "SIMULATE")
        self.assertEqual(len(fake.cancel_calls), 1)
        env = fake.cancel_calls[0]["kwargs"]["trd_env"]
        env_name = getattr(env, "name", env)
        self.assertEqual(str(env_name).upper(), "SIMULATE")
        broker.close()


class ExecutorModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._quote = patch("analysis.executor.live_price_for", return_value=None)
        self._quote.start()
        self.addCleanup(self._quote.stop)
        self._rth = patch("analysis.executor.in_us_rth", return_value=True)
        self._rth.start()
        self.addCleanup(self._rth.stop)

    def test_watchlist_aliases(self) -> None:
        self.assertEqual(mode_from_config({"execution": "futu-sim"}, False), "futu-sim")
        self.assertEqual(mode_from_config({"execution": "paper"}, False), "paper")
        self.assertEqual(mode_from_config({}, True), "longbridge-preview")

    def test_futu_sim_uses_broker_not_paper(self) -> None:
        class Stub:
            def __init__(self) -> None:
                self.placed = 0

            def connect(self, market: str = "US") -> dict[str, Any]:
                return {"acc_id": 222, "trd_env": "SIMULATE", "market": market}

            def place_simulate(self, **kwargs: Any) -> dict[str, Any]:
                self.placed += 1
                return {
                    "ticker": kwargs["symbol"],
                    "side": kwargs["side"],
                    "qty": kwargs["qty"],
                    "price": kwargs["price"],
                    "status": "futu-sim-submitted",
                    "trd_env": "SIMULATE",
                    "order_id": "sim-1",
                }

            def funds(self) -> dict[str, Any]:
                return {"us_cash": 1}

            def positions(self) -> list[dict[str, Any]]:
                return []

            def close(self) -> None:
                return None

        stub = Stub()
        payload = {
            "actionable": [
                {"ticker": "NVDA.US", "final_decision": "BUY", "close": 225.73, "buy_votes": 3, "sell_votes": 0}
            ]
        }
        log = execute(payload, "futu-sim", 1, futu_broker=stub)
        self.assertEqual(stub.placed, 1)
        self.assertEqual(log["actions"][0]["status"], "futu-sim-submitted")
        self.assertNotIn("cash", log)

    def test_buy_hold_skips_if_already_long(self) -> None:
        class Stub:
            def __init__(self) -> None:
                self.placed = 0

            def connect(self, market: str = "US") -> dict[str, Any]:
                return {"acc_id": 222, "trd_env": "SIMULATE", "market": market}

            def place_simulate(self, **_kwargs: Any) -> dict[str, Any]:
                self.placed += 1
                raise AssertionError("must not buy again when already long")

            def funds(self) -> dict[str, Any]:
                return {"us_cash": 1}

            def positions(self) -> list[dict[str, Any]]:
                return [{"code": "US.NVDA", "qty": 1}]

            def close(self) -> None:
                return None

        payload = {
            "config": {"strategy": "buy_hold", "execution": "futu-sim", "qty": 1},
            "actionable": [
                {"ticker": "NVDA.US", "final_decision": "BUY", "close": 225.73}
            ],
        }
        log = execute(payload, "futu-sim", 1, futu_broker=Stub())
        self.assertEqual(log["actions"][0]["status"], "skipped-already-long")

    def test_sell_skips_when_flat(self) -> None:
        class Stub:
            def connect(self, market: str = "US") -> dict[str, Any]:
                return {"acc_id": 222, "trd_env": "SIMULATE", "market": market}

            def place_simulate(self, **_kwargs: Any) -> dict[str, Any]:
                raise AssertionError("must not sell when flat")

            def funds(self) -> dict[str, Any]:
                return {"us_cash": 1}

            def positions(self) -> list[dict[str, Any]]:
                return []

            def close(self) -> None:
                return None

        payload = {
            "config": {"strategy": "buy_hold", "execution": "futu-sim", "qty": 1},
            "actionable": [{"ticker": "AAPL.US", "final_decision": "SELL", "close": 180.0}],
        }
        log = execute(payload, "futu-sim", 1, futu_broker=Stub())
        self.assertEqual(log["actions"][0]["status"], "skipped-flat")

    def test_opend_down_does_not_paper_fill(self) -> None:
        class Down:
            def connect(self, market: str = "US") -> dict[str, Any]:
                raise OpenDDownError("OpenD is not listening")

            def place_simulate(self, **_kwargs: Any) -> dict[str, Any]:
                raise AssertionError("must not place when OpenD is down")

            def funds(self) -> dict[str, Any]:
                return {}

            def positions(self) -> list[dict[str, Any]]:
                return []

            def close(self) -> None:
                return None

        payload = {
            "actionable": [
                {"ticker": "AAPL.US", "final_decision": "BUY", "close": 180.0, "buy_votes": 3, "sell_votes": 0}
            ]
        }
        log = execute(payload, "futu-sim", 1, futu_broker=Down())
        self.assertEqual(log["status"], "opend-down")
        self.assertEqual(log["actions"][0]["status"], "skipped-opend-down")
        self.assertEqual(log_exit_code(log), 2)

    def test_budget_skips_buy_that_does_not_fit(self) -> None:
        class Stub:
            def __init__(self) -> None:
                self.placed: list[dict[str, Any]] = []

            def connect(self, market: str = "US") -> dict[str, Any]:
                return {"acc_id": 222, "trd_env": "SIMULATE", "market": market}

            def place_simulate(self, **kwargs: Any) -> dict[str, Any]:
                self.placed.append(kwargs)
                return {
                    "ticker": kwargs["symbol"],
                    "side": kwargs["side"],
                    "qty": kwargs["qty"],
                    "price": kwargs["price"],
                    "status": "futu-sim-submitted",
                    "trd_env": "SIMULATE",
                    "order_id": "sim-1",
                }

            def funds(self) -> dict[str, Any]:
                return {"us_cash": 1_000_000}

            def positions(self) -> list[dict[str, Any]]:
                return []

            def close(self) -> None:
                return None

        stub = Stub()
        payload = {
            "config": {
                "execution": "futu-sim",
                "qty": 1,
                "budget_usd": 500,
                "symbols": ["AAPL.US", "NVDA.US"],
            },
            "actionable": [
                {"ticker": "AAPL.US", "final_decision": "BUY", "close": 300.0, "execution": "futu-sim"},
                {"ticker": "NVDA.US", "final_decision": "BUY", "close": 250.0, "execution": "futu-sim"},
            ],
        }
        log = execute(payload, "futu-sim", 1, futu_broker=stub)
        self.assertEqual(len(stub.placed), 1)
        self.assertEqual(stub.placed[0]["symbol"], "AAPL.US")
        self.assertEqual(log["actions"][1]["status"], "skipped-budget")
        self.assertEqual(log["budget_usd"], 500)
        self.assertEqual(log["book_notional_after"], 300.0)

    def test_existing_book_position_counts_against_budget(self) -> None:
        class Stub:
            def place_simulate(self, **_kwargs: Any) -> dict[str, Any]:
                raise AssertionError("must not buy when the $1000 book cap is already used")

            def connect(self, market: str = "US") -> dict[str, Any]:
                return {"acc_id": 222, "trd_env": "SIMULATE", "market": market}

            def funds(self) -> dict[str, Any]:
                return {"us_cash": 1_000_000}

            def positions(self) -> list[dict[str, Any]]:
                return [{"code": "US.AAPL", "qty": 1, "market_val": 900.0}]

            def close(self) -> None:
                return None

        payload = {
            "config": {
                "execution": "futu-sim",
                "qty": 1,
                "budget_usd": 1000,
                "symbols": ["AAPL.US", "NVDA.US"],
            },
            "actionable": [
                {"ticker": "NVDA.US", "final_decision": "BUY", "close": 225.0, "execution": "futu-sim"}
            ],
        }
        log = execute(payload, "futu-sim", 1, futu_broker=Stub())
        self.assertEqual(log["actions"][0]["status"], "skipped-budget")
        self.assertEqual(log["book_notional_before"], 900.0)

    def test_pending_buy_counts_against_budget_and_held(self) -> None:
        class Stub:
            def place_simulate(self, **_kwargs: Any) -> dict[str, Any]:
                raise AssertionError("must not buy again while a BUY is still submitting")

            def connect(self, market: str = "US") -> dict[str, Any]:
                return {"acc_id": 222, "trd_env": "SIMULATE", "market": market}

            def funds(self) -> dict[str, Any]:
                return {"us_cash": 1_000_000}

            def positions(self) -> list[dict[str, Any]]:
                return []

            def open_orders(self) -> list[dict[str, Any]]:
                return [
                    {
                        "code": "US.AAPL",
                        "trd_side": "BUY",
                        "order_status": "SUBMITTING",
                        "qty": 1,
                        "dealt_qty": 0,
                        "price": 316.22,
                    }
                ]

            def close(self) -> None:
                return None

        payload = {
            "config": {
                "execution": "futu-sim",
                "qty": 1,
                "budget_usd": 1000,
                "symbols": ["AAPL.US"],
            },
            "actionable": [
                {"ticker": "AAPL.US", "final_decision": "BUY", "close": 316.22, "execution": "futu-sim"}
            ],
        }
        log = execute(payload, "futu-sim", 1, futu_broker=Stub())
        self.assertEqual(log["actions"][0]["status"], "skipped-already-long")
        self.assertEqual(log["book_notional_before"], 316.22)

    def test_order_uses_live_premarket_quote(self) -> None:
        class Stub:
            def __init__(self) -> None:
                self.placed: list[dict[str, Any]] = []

            def connect(self, market: str = "US") -> dict[str, Any]:
                return {"acc_id": 222, "trd_env": "SIMULATE", "market": market}

            def place_simulate(self, **kwargs: Any) -> dict[str, Any]:
                self.placed.append(kwargs)
                return {
                    "ticker": kwargs["symbol"],
                    "side": kwargs["side"],
                    "qty": kwargs["qty"],
                    "price": kwargs["price"],
                    "status": "futu-sim-submitted",
                    "trd_env": "SIMULATE",
                    "order_id": "sim-1",
                }

            def funds(self) -> dict[str, Any]:
                return {"us_cash": 1_000_000}

            def positions(self) -> list[dict[str, Any]]:
                return []

            def close(self) -> None:
                return None

        stub = Stub()
        payload = {
            "config": {"execution": "futu-sim", "qty": 1, "budget_usd": 1000, "symbols": ["AAPL.US"]},
            "actionable": [
                {"ticker": "AAPL.US", "final_decision": "BUY", "close": 316.22, "execution": "futu-sim"}
            ],
        }
        with patch(
            "analysis.executor.live_price_for",
            return_value={"price": 315.785, "session": "pre", "source": "pre_market"},
        ):
            log = execute(payload, "futu-sim", 1, futu_broker=stub)
        self.assertEqual(stub.placed[0]["price"], 315.785)
        self.assertEqual(log["actions"][0]["quote_source"], "pre_market")

    def test_skips_orders_outside_regular_hours(self) -> None:
        class Stub:
            def place_simulate(self, **_kwargs: Any) -> dict[str, Any]:
                raise AssertionError("must not place outside US regular hours")

            def connect(self, market: str = "US") -> dict[str, Any]:
                return {"acc_id": 222, "trd_env": "SIMULATE", "market": market}

            def funds(self) -> dict[str, Any]:
                return {}

            def positions(self) -> list[dict[str, Any]]:
                return []

            def close(self) -> None:
                return None

        payload = {
            "config": {"execution": "futu-sim", "qty": 1, "symbols": ["AAPL.US"]},
            "actionable": [
                {"ticker": "AAPL.US", "final_decision": "BUY", "close": 316.22, "execution": "futu-sim"}
            ],
        }
        with patch("analysis.executor.in_us_rth", return_value=False):
            log = execute(payload, "futu-sim", 1, futu_broker=Stub())
        self.assertEqual(log["status"], "skipped-outside-rth")
        self.assertEqual(log["actions"][0]["status"], "skipped-outside-rth")


if __name__ == "__main__":
    unittest.main()
