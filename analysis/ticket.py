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
        "broker": "futu-niuniu-demo",
        "note": (
            "Not an order. Log into Futu 牛牛 (模拟交易) on the Cloud Agent desktop "
            "or connect OpenD, then place this ticket by hand or via futu-api."
        ),
    }
