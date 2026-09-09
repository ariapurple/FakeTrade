"""Optional internal ledger. Unattended fake trades use Futu 模拟盘 (`execution=futu-sim`)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, assert_never

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ACCOUNT = ROOT / "config" / "paper_account.json"
DEFAULT_LEDGER = ROOT / "analysis" / "output" / "paper_ledger.json"

Side = Literal["BUY", "SELL"]


def load_account(path: Path = DEFAULT_ACCOUNT) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def empty_ledger(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "cash": float(account.get("starting_cash", 100_000)),
        "currency": account.get("currency", "USD"),
        "positions": {},
        "fills": [],
    }


def load_ledger(path: Path = DEFAULT_LEDGER, account: dict[str, Any] | None = None) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return empty_ledger(account or load_account())


def save_ledger(ledger: dict[str, Any], path: Path = DEFAULT_LEDGER) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8")


def apply_fill(
    ledger: dict[str, Any],
    *,
    symbol: str,
    side: Side,
    qty: int,
    price: float,
    reason: str,
) -> dict[str, Any]:
    """Mutate ledger. Skip duplicate BUY (already long) or SELL (flat)."""
    positions: dict[str, Any] = ledger.setdefault("positions", {})
    held = int(positions.get(symbol, {}).get("qty", 0))
    cash = float(ledger.get("cash", 0))
    result: dict[str, Any] = {
        "ticker": symbol,
        "side": side,
        "qty": qty,
        "price": price,
        "status": "skipped",
    }

    if side == "BUY":
        if held > 0:
            result["status"] = "skipped-already-long"
            result["note"] = f"Already long {held} {symbol}."
            return result
        cost = price * qty
        if cost > cash:
            result["status"] = "skipped-insufficient-cash"
            result["note"] = f"Need {cost:.2f}, cash {cash:.2f}."
            return result
        ledger["cash"] = round(cash - cost, 2)
        positions[symbol] = {"qty": qty, "avg_price": price}
    elif side == "SELL":
        if held <= 0:
            result["status"] = "skipped-flat"
            result["note"] = f"No long position in {symbol}."
            return result
        sell_qty = min(qty, held)
        proceeds = price * sell_qty
        ledger["cash"] = round(cash + proceeds, 2)
        remaining = held - sell_qty
        if remaining <= 0:
            positions.pop(symbol, None)
        else:
            positions[symbol]["qty"] = remaining
        result["qty"] = sell_qty
    else:
        assert_never(side)

    fill = {
        "time": datetime.now(timezone.utc).isoformat(),
        "ticker": symbol,
        "side": side,
        "qty": result["qty"],
        "price": price,
        "reason": reason,
        "cash_after": ledger["cash"],
    }
    ledger.setdefault("fills", []).append(fill)
    result["status"] = "paper-filled"
    result["cash_after"] = ledger["cash"]
    result["positions"] = dict(ledger["positions"])
    return result
