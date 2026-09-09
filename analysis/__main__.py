"""CLI: Longbridge candles → QuantHarness indicators (and optional 4-agent graph)."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from analysis.indicators import compute_indicators, educational_bias
from analysis.kline import fetch_klines, to_quantharness
from analysis.quantharness import llm_provider, run_trading_graph
from analysis.ticket import build_ticket


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run QuantHarness-style analysis on Longbridge market data."
    )
    parser.add_argument("symbol", nargs="?", default="NVDA.US", help="e.g. NVDA.US or 700.HK")
    parser.add_argument("--period", default="day", help="1m, 5m, 15m, 1h, day, week")
    parser.add_argument("--count", type=int, default=60, help="Number of candles to fetch")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run the four-agent QuantHarness graph (needs a vision LLM API key)",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    return parser.parse_args(argv)


def analyze(symbol: str, period: str, count: int, full: bool) -> dict[str, Any]:
    rows = fetch_klines(symbol, period=period, count=count)
    kline_data = to_quantharness(rows)
    indicators = compute_indicators(kline_data)
    side = educational_bias(indicators)
    result: dict[str, Any] = {
        "symbol": symbol,
        "period": period,
        "bars": indicators["bars"],
        "last_time": kline_data["Datetime"][-1],
        "indicators": indicators,
        "educational_side": side,
        "quantharness": None,
        "ticket": None,
    }

    if full:
        result["quantharness"] = run_trading_graph(kline_data, symbol, period)
        decision = str(result["quantharness"].get("final_trade_decision") or "")
        upper = decision.upper()
        if "LONG" in upper or "BUY" in upper:
            side = "LONG"
        elif "SHORT" in upper or "SELL" in upper:
            side = "SHORT"
        rationale = decision or "; ".join(indicators["notes"])
        source = "QuantHarness TradingGraph"
    else:
        rationale = "; ".join(indicators["notes"])
        source = indicators["source"]

    result["ticket"] = build_ticket(
        symbol,
        side,
        indicators,
        rationale=rationale,
        source=source,
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = analyze(args.symbol, args.period, args.count, args.full)
    except Exception as exc:  # noqa: BLE001 — CLI boundary
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
        return 0

    indicators = payload["indicators"]
    ticket = payload["ticket"]
    print(f"{payload['symbol']}  {payload['period']}  {payload['bars']} bars  last {payload['last_time']}")
    print(
        f"close {indicators['close']}  RSI {indicators['rsi']}  "
        f"MACD hist {indicators['macd_hist']}  bias {indicators['bias']}"
    )
    for note in indicators["notes"]:
        print(f"- {note}")
    print(f"educational side: {payload['educational_side']}")
    if payload["quantharness"]:
        print("--- QuantHarness ---")
        print(payload["quantharness"].get("final_trade_decision"))
    else:
        provider = llm_provider()
        if provider is None:
            print("four-agent graph: skipped (set OPENAI_API_KEY or another vision LLM key, then pass --full)")
        else:
            print(f"four-agent graph: skipped (LLM key for {provider} is set; pass --full to run)")
    print("--- demo ticket (not an order) ---")
    print(f"{ticket['side']} {ticket['symbol']}  via {ticket['broker']}")
    print(ticket["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
