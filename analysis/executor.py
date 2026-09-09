"""Turn trading_signal.json into a dry-run (default) or Longbridge preview. Never live Futu."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, assert_never

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SIGNAL = ROOT / "trading_signal.json"
DEFAULT_LOG = ROOT / "analysis" / "output" / "execution_log.json"

Mode = Literal["dry-run", "longbridge-preview"]


def _futu_opend_up(host: str, port: int) -> bool:
    try:
        import socket

        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


def execute(payload: dict[str, Any], mode: Mode, qty: int) -> dict[str, Any]:
    log: dict[str, Any] = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "futu_opend": _futu_opend_up("127.0.0.1", 11111),
        "actions": [],
    }
    for row in payload.get("actionable", []):
        decision = row["final_decision"]
        symbol = row["ticker"]
        if decision not in ("BUY", "SELL"):
            continue
        action: dict[str, Any] = {
            "ticker": symbol,
            "decision": decision,
            "qty": qty,
            "status": "skipped",
        }
        if mode == "dry-run":
            action["status"] = "dry-run"
            action["note"] = "No order sent. Re-run with --longbridge-preview to preview a Longbridge ticket."
        elif mode == "longbridge-preview":
            side = "buy" if decision == "BUY" else "sell"
            cmd = ["longbridge", "order", side, symbol, str(qty), "--format", "json"]
            completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
            action["command"] = cmd
            action["returncode"] = completed.returncode
            action["stdout"] = (completed.stdout or "")[-4000:]
            action["stderr"] = (completed.stderr or "")[-2000:]
            action["status"] = "previewed" if completed.returncode == 0 else "preview-failed"
            action["note"] = "Preview only. longbridge order does not send unless you pass --execute CODE."
        else:
            assert_never(mode)
        log["actions"].append(action)

    if not log["actions"]:
        log["note"] = "No BUY/SELL votes reached the threshold. Nothing to execute."
    if log["futu_opend"]:
        log["futu_note"] = (
            "Futu OpenD is listening on 127.0.0.1:11111 on THIS machine. "
            "Cloud Automations are a different VM — your home-PC OpenD is not this port."
        )
    else:
        log["futu_note"] = (
            "Futu OpenD is not reachable at 127.0.0.1:11111. "
            "Install OpenD on the same computer that runs this script (or a Cursor self-hosted worker)."
        )
    return log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Demo executor for Quant watchlist signals.")
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
    qty = int(payload.get("config", {}).get("qty", 1))
    mode: Mode = "longbridge-preview" if args.longbridge_preview else "dry-run"
    log = execute(payload, mode, qty)
    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.log.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"mode={log['mode']}  futu_opend={log['futu_opend']}  actions={len(log['actions'])}")
    print(log.get("futu_note"))
    for action in log["actions"]:
        print(f"  {action['decision']:4} {action['ticker']:10} {action['status']}")
    print(f"wrote {args.log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
