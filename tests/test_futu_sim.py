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
    pick_simulate_account,
    to_futu_code,
)


class FakeTradeContext:
    def __init__(self) -> None:
        self.place_calls: list[dict[str, Any]] = []
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


class MappingTests(unittest.TestCase):
    def test_longbridge_to_futu(self) -> None:
        self.assertEqual(to_futu_code("AAPL.US"), "US.AAPL")
        self.assertEqual(to_futu_code("nvda.us"), "US.NVDA")
        self.assertEqual(to_futu_code("00700.HK"), "HK.00700")

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
        broker.close()
        self.assertTrue(fake.closed)


class ExecutorModeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
