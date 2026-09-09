"""Turn trading_signal.json into dry-run, paper fills, or Longbridge preview. Never live Futu."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, assert_never

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

Mode = Literal["dry-run", "paper", "longbridge-preview"]


def _futu_opend_up(host: str, port: int) -> bool:
    try:
        import socket

        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


def mode_from_config(config: dict[str, Any], preview_flag: bool) -> Mode:
    if preview_flag:
        return "longbridge-preview"
    raw = str(config.get("execution", "paper")).strip().lower()
    if raw in {"paper", "paper-trade", "fake"}:
        return "paper"
    if raw in {"longbridge-preview", "preview"}:
        return "longbridge-preview"
    return "dry-run"


def execute(payload: dict[str, Any], mode: Mode, qty: int) -> dict[str, Any]:
    log: dict[str, Any] = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "futu_opend": _futu_opend_up("127.0.0.1", 11111),
        "actions": [],
        "ledger_path": str(DEFAULT_LEDGER),
    }
    ledger = load_ledger()
    for row in payload.get("actionable", []):
        decision = row["final_decision"]
        symbol = row["ticker"]
        if decision not in ("BUY", "SELL"):
            continue
        price = float(row.get("close") or 0)
        action: dict[str, Any] = {
            "ticker": symbol,
            "decision": decision,
            "qty": qty,
            "price": price,
            "status": "skipped",
        }
        if mode == "dry-run":
            action["status"] = "dry-run"
            action["note"] = "No fill. Set config execution=paper for unattended fake trades."
        elif mode == "paper":
            fill = apply_fill(
                ledger,
                symbol=symbol,
                side=decision,
                qty=qty,
                price=price,
                reason=f"watchlist vote {row.get('buy_votes')}/{row.get('sell_votes')}",
            )
            action.update(fill)
        elif mode == "longbridge-preview":
            side = "buy" if decision == "BUY" else "sell"
            cmd = [
                "longbridge",
                "order",
                side,
                symbol,
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
        else:
            assert_never(mode)
        log["actions"].append(action)

    if mode == "paper":
        save_ledger(ledger)
        log["cash"] = ledger["cash"]
        log["positions"] = ledger.get("positions", {})
        log["fills_count"] = len(ledger.get("fills", []))

    if not log["actions"]:
        log["note"] = "No BUY/SELL votes reached the threshold. Nothing to execute."
    log["futu_note"] = (
        "Futu OpenD is not used. Unattended fake trades are the paper ledger. "
        "Cloud Automations cannot reach OpenD on your laptop."
    )
    log["account"] = load_account()
    return log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Demo/paper executor for Quant watchlist signals.")
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
    args.log.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"mode={log['mode']}  cash={log.get('cash')}  actions={len(log['actions'])}")
    if log.get("positions") is not None:
        print(f"positions {log['positions']}")
    for action in log["actions"]:
        print(f"  {action.get('decision', action.get('side'))} {action['ticker']:10} {action['status']}")
    if log.get("note"):
        print(log["note"])
    print(f"wrote {args.log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
