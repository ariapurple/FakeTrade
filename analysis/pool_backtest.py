"""$2000 start, no notional cap: one shared cash pool vs isolated sleeves.

After a sell, leftover cash (e.g. $2500) can buy more of any name that is BUY.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.book_backtest import _sample_points
from analysis.exit_sweep import hold_plus_exit_signals, load_frames, run_rule

ROOT = Path(__file__).resolve().parents[1]

COMPARE_RULES: list[dict[str, Any]] = [
    {
        "id": "never_sell",
        "below_sma": 0,
        "drawdown_from_high": 0.0,
        "high_lookback": 0,
        "need_both": False,
    },
    {
        "id": "dd40lb252",
        "below_sma": 0,
        "drawdown_from_high": 0.4,
        "high_lookback": 252,
        "need_both": False,
    },
    {
        "id": "dd50lb252",
        "below_sma": 0,
        "drawdown_from_high": 0.5,
        "high_lookback": 252,
        "need_both": False,
    },
    {
        "id": "dd25lb252",
        "below_sma": 0,
        "drawdown_from_high": 0.25,
        "high_lookback": 252,
        "need_both": False,
    },
    {
        "id": "sma200",
        "below_sma": 200,
        "drawdown_from_high": 0.0,
        "high_lookback": 0,
        "need_both": False,
    },
    {
        "id": "old_sma60_or_dd25lb60",
        "below_sma": 60,
        "drawdown_from_high": 0.25,
        "high_lookback": 60,
        "need_both": False,
    },
]


def _day_key(stamp: Any) -> str:
    ts = pd.Timestamp(stamp)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert("UTC").strftime("%Y-%m-%d")


def tapes_from_frames(frames: dict[str, pd.DataFrame], rule: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tapes: dict[str, dict[str, Any]] = {}
    for symbol, frame in frames.items():
        signals = hold_plus_exit_signals(
            frame,
            below_sma=int(rule["below_sma"]),
            drawdown_from_high=float(rule["drawdown_from_high"]),
            high_lookback=int(rule["high_lookback"]),
            need_both=bool(rule["need_both"]),
        )
        opens: dict[str, float] = {}
        closes: dict[str, float] = {}
        sigs: dict[str, str] = {}
        for idx in range(len(frame)):
            key = _day_key(frame["time"].iloc[idx])
            opens[key] = float(frame["open"].iloc[idx])
            closes[key] = float(frame["close"].iloc[idx])
            sigs[key] = signals[idx]
        tapes[symbol] = {"open": opens, "close": closes, "signal": sigs}
    return tapes


def simulate_pool(
    tapes: dict[str, dict[str, Any]],
    capital: float,
    *,
    integer_shares: bool = False,
) -> dict[str, Any]:
    """One cash account. Sells first at the open, then remaining cash splits across new BUYs."""
    all_days = sorted({day for tape in tapes.values() for day in tape["close"]})
    if tapes:
        listed = max(min(tape["close"]) for tape in tapes.values())
        all_days = [day for day in all_days if day >= listed]
    cash = float(capital)
    shares = {symbol: 0.0 for symbol in tapes}
    last_close = {symbol: 0.0 for symbol in tapes}
    pending_sell: set[str] = set()
    pending_buy: set[str] = set()
    peak = float(capital)
    max_dd = 0.0
    equity: list[dict[str, Any]] = []
    buys = 0
    sells = 0

    def mark() -> float:
        total = cash
        for symbol, qty in shares.items():
            if qty > 0 and last_close[symbol] > 0:
                total += qty * last_close[symbol]
        return total

    for day in all_days:
        for symbol, tape in tapes.items():
            if day in tape["close"]:
                last_close[symbol] = float(tape["close"][day])

        for symbol in list(pending_sell):
            tape = tapes[symbol]
            qty = shares[symbol]
            if qty > 0 and day in tape["open"] and float(tape["open"][day]) > 0:
                cash += qty * float(tape["open"][day])
                shares[symbol] = 0.0
                sells += 1
            pending_sell.discard(symbol)

        buyers = [
            symbol
            for symbol in sorted(pending_buy)
            if shares[symbol] <= 0 and day in tapes[symbol]["open"] and float(tapes[symbol]["open"][day]) > 0
        ]
        pending_buy.difference_update(buyers)
        if buyers and cash > 0:
            slice_cash = cash / len(buyers)
            for symbol in buyers:
                price = float(tapes[symbol]["open"][day])
                if integer_shares:
                    qty = int(slice_cash // price)
                    if qty < 1:
                        continue
                    cost = qty * price
                else:
                    qty = slice_cash / price
                    cost = slice_cash
                cash -= cost
                shares[symbol] = qty
                buys += 1

        marked = mark()
        peak = max(peak, marked)
        max_dd = min(max_dd, marked - peak)
        equity.append({"time": day, "equity": round(marked, 4)})

        for symbol, tape in tapes.items():
            if day not in tape["signal"]:
                continue
            signal = tape["signal"][day]
            if signal == "SELL" and shares[symbol] > 0:
                pending_sell.add(symbol)
                pending_buy.discard(symbol)
            elif signal == "BUY" and shares[symbol] <= 0:
                pending_buy.add(symbol)
                pending_sell.discard(symbol)

    for symbol, qty in list(shares.items()):
        if qty > 0 and last_close[symbol] > 0:
            cash += qty * last_close[symbol]
            shares[symbol] = 0.0
            sells += 1
    if equity:
        equity[-1]["equity"] = round(cash, 4)
    pnl = cash - capital
    dd_pct = (max_dd / capital * 100.0) if capital else 0.0
    return {
        "pnl": round(pnl, 4),
        "return_pct": round(pnl / capital * 100.0, 4) if capital else 0.0,
        "ending_equity": round(cash, 4),
        "capital": round(capital, 4),
        "buys": buys,
        "sells": sells,
        "max_drawdown": round(max_dd, 4),
        "max_drawdown_pct": round(dd_pct, 4),
        "equity": _sample_points(equity, 24),
    }


def _sleeve_row(result: dict[str, Any]) -> dict[str, Any]:
    live = result["totals"]["live"]
    return {
        "pnl": live["pnl"],
        "return_pct": live["return_pct"],
        "ending_equity": live["ending_equity"],
        "trades": live["trades"],
        "max_drawdown": live["max_drawdown"],
        "max_drawdown_pct": live["max_drawdown_pct"],
    }


def run_pool_compare(*, capital: float, count: int, adjust: str) -> dict[str, Any]:
    cfg = json.loads((ROOT / "config" / "watchlist.json").read_text(encoding="utf-8"))
    symbols = [str(name) for name in cfg["symbols"]]
    frames, errors = load_frames(symbols, count=count, adjust=adjust)
    ranked: list[dict[str, Any]] = []
    for rule in COMPARE_RULES:
        sleeve = run_rule(frames, rule, capital)
        tapes = tapes_from_frames(frames, rule)
        pooled = simulate_pool(tapes, capital, integer_shares=False)
        pooled_int = simulate_pool(tapes, capital, integer_shares=True)
        ranked.append(
            {
                "id": rule["id"],
                "sleeve": _sleeve_row(sleeve),
                "pool": {key: value for key, value in pooled.items() if key != "equity"},
                "pool_integer": {key: value for key, value in pooled_int.items() if key != "equity"},
                "pool_equity": pooled["equity"],
            }
        )
    return {
        "capital": capital,
        "count": count,
        "adjust": adjust,
        "symbols": list(frames),
        "skipped": errors,
        "notes": [
            f"${capital:.0f} start. No notional cap: NAV can be redeployed after a sell.",
            "Sleeve = each name keeps its own pocket (old 4y test). Pool = one cash pile.",
            "Pool BUY splits free cash equally across names that are flat and BUY.",
            "Integer pool uses whole shares only (closer to Futu 模拟盘).",
        ],
        "ranked": ranked,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare isolated sleeves vs a shared $2000 pool.")
    parser.add_argument("--capital", type=float, default=2000.0)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--adjust", default="forward")
    args = parser.parse_args(argv)
    payload = run_pool_compare(
        capital=float(args.capital),
        count=int(args.count),
        adjust=str(args.adjust),
    )
    out = ROOT / "analysis" / "output" / "pool_backtest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"{'rule':28} {'sleeve%':>10} {'pool%':>10} {'int%':>10} {'pool$':>10}")
    for row in payload["ranked"]:
        print(
            f"{row['id']:28} {row['sleeve']['return_pct']:>10} "
            f"{row['pool']['return_pct']:>10} {row['pool_integer']['return_pct']:>10} "
            f"{row['pool']['ending_equity']:>10}"
        )
    for err in payload.get("skipped") or []:
        print(f"  SKIP {err['ticker']}: {err['error']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
