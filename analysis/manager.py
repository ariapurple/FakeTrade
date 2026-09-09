"""Watchlist manager: run four sub-agents on each Longbridge symbol and vote."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from analysis.agents import (
    Signal,
    mean_reversion,
    trend_following,
    value_investing,
    volume_spread,
    vote_weight,
)
from analysis.fundamentals import fetch_calc_index
from analysis.kline import fetch_klines, to_quantharness


def _final_decision(
    reports: dict[str, dict[str, Any]],
    buy_votes_needed: int,
    sell_votes_needed: int,
) -> Signal:
    buy_votes = 0
    sell_votes = 0
    for report in reports.values():
        signal: Signal = report["signal"]
        weight = vote_weight(signal)
        if weight == 1:
            buy_votes += 1
        elif weight == -1:
            sell_votes += 1
    if buy_votes >= buy_votes_needed:
        return "BUY"
    if sell_votes >= sell_votes_needed:
        return "SELL"
    return "HOLD"


def run_symbol(
    symbol: str,
    *,
    period: str,
    count: int,
    buy_votes_needed: int,
    sell_votes_needed: int,
) -> dict[str, Any]:
    rows = fetch_klines(symbol, period=period, count=count)
    kline_data = to_quantharness(rows)
    calc = fetch_calc_index(symbol)
    reports = {
        "trend": trend_following(kline_data),
        "reversion": mean_reversion(kline_data),
        "vsa": volume_spread(kline_data),
        "value": value_investing(calc),
    }
    decision = _final_decision(reports, buy_votes_needed, sell_votes_needed)
    close = kline_data["Close"][-1]
    return {
        "ticker": symbol,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "period": period,
        "close": close,
        "final_decision": decision,
        "buy_votes": sum(1 for r in reports.values() if r["signal"] == "BUY"),
        "sell_votes": sum(1 for r in reports.values() if r["signal"] == "SELL"),
        "detailed_reports": reports,
    }


def run_watchlist(config: dict[str, Any]) -> dict[str, Any]:
    symbols = list(config["symbols"])
    period = str(config.get("period", "day"))
    count = int(config.get("count", 80))
    buy_needed = int(config.get("buy_votes_needed", 3))
    sell_needed = int(config.get("sell_votes_needed", 3))
    results = []
    errors = []
    for symbol in symbols:
        try:
            results.append(
                run_symbol(
                    symbol,
                    period=period,
                    count=count,
                    buy_votes_needed=buy_needed,
                    sell_votes_needed=sell_needed,
                )
            )
        except Exception as exc:  # noqa: BLE001 — one symbol must not abort the book
            errors.append({"ticker": symbol, "error": str(exc)})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_source": "Longbridge",
        "config": {
            "symbols": symbols,
            "period": period,
            "count": count,
            "buy_votes_needed": buy_needed,
            "sell_votes_needed": sell_needed,
            "qty": int(config.get("qty", 1)),
            "execution": str(config.get("execution", "paper")),
        },
        "results": results,
        "errors": errors,
        "actionable": [
            row
            for row in results
            if row["final_decision"] in ("BUY", "SELL")
        ],
    }
