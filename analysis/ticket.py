"""Turn analysis into a paper-trade ticket for Futu 牛牛 (or any broker) to execute."""

from __future__ import annotations

from typing import Any, Literal

Side = Literal["LONG", "SHORT", "WAIT"]


def build_ticket(
    symbol: str,
    side: Side,
    indicators: dict[str, Any],
    *,
    rationale: str,
    source: str,
) -> dict[str, Any]:
    """Structured ticket an automation can read. This does not place an order."""
    return {
        "symbol": symbol,
        "side": side,
        "action": "none" if side == "WAIT" else "demo-trade",
        "close": indicators.get("close"),
        "rationale": rationale,
        "indicators": {
            "rsi": indicators.get("rsi"),
            "macd_hist": indicators.get("macd_hist"),
            "bias": indicators.get("bias"),
        },
        "source": source,
        "broker": "futu-sim",
        "note": (
            "Ticket only. Unattended fills go through OpenD TrdEnv.SIMULATE "
            "when config execution=futu-sim. Never REAL."
        ),
    }
