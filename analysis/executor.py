"""Turn trading_signal.json into dry-run, paper, Futu 模拟盘, or Longbridge preview.

Never TrdEnv.REAL. Never `longbridge order --execute`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol, assert_never

from analysis.futu_sim import FutuSimBroker, FutuSimError, OpenDDownError, opend_up
from analysis.paper_broker import (
    DEFAULT_LEDGER,
    apply_fill,
    load_account,
    load_ledger,
    save_ledger,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SIGNAL = ROOT / "trading_signal.json"
DEFAULT_LOG = ROOT / "analysis" / "output" / "execution_log.json"

Mode = Literal["dry-run", "paper", "futu-sim", "longbridge-preview"]


class SimBroker(Protocol):
    def connect(self, market: str = "US") -> dict[str, Any]: ...
    def place_simulate(
        self,
        *,
        symbol: str,
        side: Literal["BUY", "SELL"],
        qty: int,
        price: float,
        remark: str = "QUANTSIM",
    ) -> dict[str, Any]: ...
    def funds(self) -> dict[str, Any]: ...
    def positions(self) -> list[dict[str, Any]]: ...
    def close(self) -> None: ...


def mode_from_config(config: dict[str, Any], preview_flag: bool) -> Mode:
    if preview_flag:
        return "longbridge-preview"
    raw = str(config.get("execution", "futu-sim")).strip().lower()
    if raw in {"futu-sim", "futu", "simulate", "sim", "opend"}:
        return "futu-sim"
    if raw in {"paper", "paper-trade", "fake"}:
        return "paper"
    if raw in {"longbridge-preview", "preview"}:
        return "longbridge-preview"
    if raw in {"dry-run", "dry", "none"}:
        return "dry-run"
    return "dry-run"


def _empty_action(row: dict[str, Any], qty: int, price: float) -> dict[str, Any]:
    return {
        "ticker": row["ticker"],
        "decision": row["final_decision"],
        "qty": qty,
        "price": price,
        "status": "skipped",
    }


def execute(
    payload: dict[str, Any],
    mode: Mode,
    qty: int,
    *,
    futu_broker: SimBroker | None = None,
) -> dict[str, Any]:
    log: dict[str, Any] = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "futu_opend": opend_up(),
        "actions": [],
    }
    actionable = [
        row
        for row in payload.get("actionable", [])
        if row.get("final_decision") in {"BUY", "SELL"}
    ]

    if mode == "dry-run":
        for row in actionable:
            price = float(row.get("close") or 0)
            action = _empty_action(row, qty, price)
            action["status"] = "dry-run"
            action["note"] = "No fill. Set config execution=futu-sim for Futu 模拟盘."
            log["actions"].append(action)
        log["futu_note"] = "Dry-run. No Futu order was sent."
    elif mode == "paper":
        log["ledger_path"] = str(DEFAULT_LEDGER)
        ledger = load_ledger()
        for row in actionable:
            price = float(row.get("close") or 0)
            fill = apply_fill(
                ledger,
                symbol=row["ticker"],
                side=row["final_decision"],
                qty=qty,
                price=price,
                reason=f"watchlist vote {row.get('buy_votes')}/{row.get('sell_votes')}",
            )
            action = _empty_action(row, qty, price)
            action.update(fill)
            log["actions"].append(action)
        save_ledger(ledger)
        log["cash"] = ledger["cash"]
        log["positions"] = ledger.get("positions", {})
        log["fills_count"] = len(ledger.get("fills", []))
        log["account"] = load_account()
        log["futu_note"] = "Internal paper ledger. Futu OpenD was not called."
    elif mode == "futu-sim":
        log.update(_execute_futu_sim(actionable, qty, futu_broker))
    elif mode == "longbridge-preview":
        for row in actionable:
            price = float(row.get("close") or 0)
            action = _empty_action(row, qty, price)
            side = "buy" if row["final_decision"] == "BUY" else "sell"
            cmd = [
                "longbridge",
                "order",
                side,
                row["ticker"],
                str(qty),
                "--order-type",
                "MO",
                "--format",
                "json",
            ]
            completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
            action["command"] = cmd
            action["returncode"] = completed.returncode
            action["stdout"] = (completed.stdout or "")[-4000:]
            action["stderr"] = (completed.stderr or "")[-2000:]
            action["status"] = "previewed" if completed.returncode == 0 else "preview-failed"
            action["note"] = "Preview only. Never pass --execute unless you intend a live Longbridge order."
            log["actions"].append(action)
        log["futu_note"] = "Longbridge preview only. Futu was not called."
    else:
        assert_never(mode)

    if not log["actions"] and not log.get("note"):
        log["note"] = "No BUY/SELL votes reached the threshold. Nothing to execute."
    return log


def _execute_futu_sim(
    actionable: list[dict[str, Any]],
    qty: int,
    futu_broker: SimBroker | None,
) -> dict[str, Any]:
    extra: dict[str, Any] = {
        "actions": [],
        "futu_note": "Futu 模拟盘 via OpenD. TrdEnv.REAL is never used.",
    }
    broker = futu_broker or FutuSimBroker()
    owns_broker = futu_broker is None
    try:
        extra["futu"] = broker.connect("US")
        extra["futu_opend"] = True
        for row in actionable:
            price = float(row.get("close") or 0)
            if price <= 0:
                action = _empty_action(row, qty, price)
                action["status"] = "skipped-no-price"
                action["note"] = "No last close from Longbridge; refused to guess a Futu price."
                extra["actions"].append(action)
                continue
            fill = broker.place_simulate(
                symbol=row["ticker"],
                side=row["final_decision"],
                qty=qty,
                price=price,
                remark="QUANTSIM",
            )
            extra["actions"].append(fill)
        extra["futu_funds"] = broker.funds()
        extra["futu_positions"] = broker.positions()
    except OpenDDownError as exc:
        extra["futu_opend"] = False
        extra["status"] = "opend-down"
        extra["error"] = str(exc)
        extra["futu_note"] = str(exc)
        for row in actionable:
            price = float(row.get("close") or 0)
            action = _empty_action(row, qty, price)
            action["status"] = "skipped-opend-down"
            action["note"] = str(exc)
            extra["actions"].append(action)
        if not extra["actions"]:
            extra["note"] = (
                "No BUY/SELL this hour, and OpenD is down. "
                "Unattended Futu fake trades need OpenD on this machine."
            )
    except FutuSimError as exc:
        extra["status"] = "futu-sim-error"
        extra["error"] = str(exc)
        extra["futu_note"] = str(exc)
        if not extra["actions"] and actionable:
            for row in actionable:
                price = float(row.get("close") or 0)
                action = _empty_action(row, qty, price)
                action["status"] = "skipped-futu-error"
                action["note"] = str(exc)
                extra["actions"].append(action)
    finally:
        if owns_broker:
            broker.close()
    return extra


def log_exit_code(log: dict[str, Any]) -> int:
    status = str(log.get("status") or "")
    if status == "opend-down":
        return 2
    if status == "futu-sim-error":
        return 1
    if any(str(action.get("status", "")).endswith("failed") for action in log.get("actions", [])):
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Executor for Quant watchlist signals. Futu = SIMULATE only.")
    parser.add_argument("--signal", type=Path, default=DEFAULT_SIGNAL)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument(
        "--longbridge-preview",
        action="store_true",
        help="Call `longbridge order buy/sell` WITHOUT --execute (preview only).",
    )
    args = parser.parse_args(argv)

    if not args.signal.exists():
        print(f"missing {args.signal}; run python -m analysis.loop first")
        return 1

    payload = json.loads(args.signal.read_text(encoding="utf-8"))
    config = payload.get("config", {})
    qty = int(config.get("qty", 1))
    mode = mode_from_config(config, args.longbridge_preview)
    log = execute(payload, mode, qty)
    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.log.write_text(json.dumps(log, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"mode={log['mode']}  futu_opend={log.get('futu_opend')}  actions={len(log['actions'])}")
    if log.get("futu"):
        print(f"futu acc_id={log['futu'].get('acc_id')} trd_env={log['futu'].get('trd_env')}")
    if log.get("positions") is not None:
        print(f"positions {log['positions']}")
    for action in log["actions"]:
        print(f"  {action.get('decision', action.get('side'))} {action['ticker']:10} {action['status']}")
    if log.get("error"):
        print(log["error"])
    if log.get("note"):
        print(log["note"])
    print(f"wrote {args.log}")
    return log_exit_code(log)


if __name__ == "__main__":
    raise SystemExit(main())
