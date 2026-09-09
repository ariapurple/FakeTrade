"""Sweep hold-plus-exit rules on ~4 years of daily Longbridge bars.

``kline history`` is not available on this account (quota 0). ``--count 1000``
is the longest daily window the quote API accepts (~4 years).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.backtest import rows_to_frame
from analysis.book_backtest import _totals, backtest_symbol
from analysis.kline import fetch_klines

ROOT = Path(__file__).resolve().parents[1]
Signal = str


def hold_plus_exit_signals(
    frame: pd.DataFrame,
    *,
    below_sma: int = 0,
    drawdown_from_high: float = 0.0,
    high_lookback: int = 0,
    need_both: bool = False,
) -> list[Signal]:
    """Stay long by default. Sell only after the indicator window is ready."""
    close = frame["close"].astype(float)
    n_bars = len(frame)
    if not below_sma and float(drawdown_from_high) <= 0:
        return ["BUY"] * n_bars
    sma = close.rolling(int(below_sma)).mean() if below_sma else None
    peak = (
        close.rolling(int(high_lookback)).max()
        if high_lookback and float(drawdown_from_high) > 0
        else None
    )
    ready = max(int(below_sma or 0), int(high_lookback or 0) if float(drawdown_from_high) > 0 else 0, 1)
    out: list[Signal] = []
    for idx in range(n_bars):
        if idx + 1 < ready:
            out.append("BUY")
            continue
        last = float(close.iloc[idx])
        sma_hit = bool(sma is not None and pd.notna(sma.iloc[idx]) and last < float(sma.iloc[idx]))
        dd_hit = bool(
            peak is not None
            and pd.notna(peak.iloc[idx])
            and last <= float(peak.iloc[idx]) * (1.0 - float(drawdown_from_high))
        )
        if need_both and below_sma and float(drawdown_from_high) > 0:
            sell = sma_hit and dd_hit
        else:
            sell = sma_hit or dd_hit
        out.append("SELL" if sell else "BUY")
    return out


def rule_grid() -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = [
        {
            "id": "never_sell",
            "below_sma": 0,
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
    for sma in (0, 100, 200):
        for drawdown in (0.0, 0.20, 0.25, 0.30, 0.40, 0.50):
            lookbacks = (60, 252) if drawdown > 0 else (0,)
            for lookback in lookbacks:
                if sma == 0 and drawdown <= 0:
                    continue
                ident = _rule_id(sma, drawdown, lookback, False)
                rules.append(
                    {
                        "id": ident,
                        "below_sma": sma,
                        "drawdown_from_high": drawdown,
                        "high_lookback": lookback,
                        "need_both": False,
                    }
                )
                if sma and drawdown > 0:
                    rules.append(
                        {
                            "id": _rule_id(sma, drawdown, lookback, True),
                            "below_sma": sma,
                            "drawdown_from_high": drawdown,
                            "high_lookback": lookback,
                            "need_both": True,
                        }
                    )
    return rules


def _rule_id(sma: int, drawdown: float, lookback: int, need_both: bool) -> str:
    parts: list[str] = []
    if sma:
        parts.append(f"sma{sma}")
    if drawdown > 0:
        parts.append(f"dd{int(round(drawdown * 100))}lb{lookback}")
    joiner = "_and_" if need_both else "_or_" if sma and drawdown > 0 else "_"
    if not parts:
        return "never_sell"
    if len(parts) == 1:
        return parts[0]
    return parts[0] + joiner + parts[1]


def load_frames(
    symbols: list[str],
    *,
    count: int,
    adjust: str,
) -> tuple[dict[str, pd.DataFrame], list[dict[str, str]]]:
    frames: dict[str, pd.DataFrame] = {}
    errors: list[dict[str, str]] = []
    for idx, symbol in enumerate(symbols):
        if idx:
            time.sleep(0.25)
        try:
            frame = rows_to_frame(fetch_klines(symbol, period="day", count=count, adjust=adjust))
            if len(frame) < 220:
                raise RuntimeError(f"not enough daily bars ({len(frame)})")
            frames[symbol] = frame
        except Exception as exc:  # noqa: BLE001 — one name must not abort the book
            errors.append({"ticker": symbol, "error": str(exc)})
    return frames, errors


def run_rule(
    frames: dict[str, pd.DataFrame],
    rule: dict[str, Any],
    capital: float,
) -> dict[str, Any]:
    n_sleeves = len(frames)
    sleeve = (capital / n_sleeves) if n_sleeves else 0.0
    named: dict[str, Any] = {}
    for symbol, frame in frames.items():
        signals = hold_plus_exit_signals(
            frame,
            below_sma=int(rule["below_sma"]),
            drawdown_from_high=float(rule["drawdown_from_high"]),
            high_lookback=int(rule["high_lookback"]),
            need_both=bool(rule["need_both"]),
        )
        row = backtest_symbol(frame, sleeve, signals, test_bars=None, period="day")
        named[symbol] = {
            "bars": row["bars"],
            "range": row["range"],
            "buy_hold": row["buy_hold"],
            "live": row["live"],
        }
    totals = _totals(named, capital, sleeve)
    published = {}
    for symbol, row in named.items():
        published[symbol] = {
            "bars": row["bars"],
            "range": row["range"],
            "buy_hold": {
                "pnl": row["buy_hold"]["pnl"],
                "return_pct": row["buy_hold"]["return_pct"],
                "ending_equity": row["buy_hold"]["ending_equity"],
            },
            "live": {
                "pnl": row["live"]["pnl"],
                "return_pct": row["live"]["return_pct"],
                "ending_equity": row["live"]["ending_equity"],
                "trades": row["live"]["trades"],
                "max_drawdown_pct": row["live"]["max_drawdown_pct"],
            },
        }
    return {"totals": totals, "symbols": published, "sleeve_capital": round(sleeve, 4)}


def pick_candidate(rows: list[dict[str, Any]], hold_dd: float, hold_ret: float, hold_trades: int) -> dict[str, Any] | None:
    """Prefer +30% or more, milder drawdown than never-sell, and a rule that actually sold."""
    eligible: list[dict[str, Any]] = []
    for row in rows:
        if row["id"] == "never_sell":
            continue
        if float(row["return_pct"]) < 30.0:
            continue
        if float(row["max_drawdown_pct"]) <= float(hold_dd):
            continue
        sold = int(row["trades"]) > int(hold_trades) or float(row["return_pct"]) < float(hold_ret) - 0.5
        if not sold:
            continue
        eligible.append(row)
    if not eligible:
        return None
    eligible.sort(
        key=lambda row: (
            -float(row["return_pct"]),
            -float(row["max_drawdown_pct"]),
            int(row["trades"]),
        )
    )
    return eligible[0]


def run_sweep(
    *,
    capital: float,
    count: int,
    adjust: str,
) -> dict[str, Any]:
    cfg = json.loads((ROOT / "config" / "watchlist.json").read_text(encoding="utf-8"))
    symbols = [str(name) for name in cfg["symbols"]]
    frames, errors = load_frames(symbols, count=count, adjust=adjust)
    rules = rule_grid()
    ranked: list[dict[str, Any]] = []
    for rule in rules:
        result = run_rule(frames, rule, capital)
        live = result["totals"]["live"]
        hold = result["totals"]["buy_hold"]
        ranked.append(
            {
                "id": rule["id"],
                "below_sma": rule["below_sma"],
                "drawdown_from_high": rule["drawdown_from_high"],
                "high_lookback": rule["high_lookback"],
                "need_both": rule["need_both"],
                "pnl": live["pnl"],
                "return_pct": live["return_pct"],
                "ending_equity": live["ending_equity"],
                "trades": live["trades"],
                "max_drawdown": live["max_drawdown"],
                "max_drawdown_pct": live["max_drawdown_pct"],
                "hold_return_pct": hold["return_pct"],
                "hold_max_drawdown_pct": hold["max_drawdown_pct"],
            }
        )
    never = next(row for row in ranked if row["id"] == "never_sell")
    candidate = pick_candidate(
        ranked,
        float(never["max_drawdown_pct"]),
        float(never["return_pct"]),
        int(never["trades"]),
    )
    ranges = {
        symbol: frames[symbol]["time"].iloc[0].isoformat() + " -> " + frames[symbol]["time"].iloc[-1].isoformat()
        if hasattr(frames[symbol]["time"].iloc[0], "isoformat")
        else f"{frames[symbol]['time'].iloc[0]} -> {frames[symbol]['time'].iloc[-1]}"
        for symbol in frames
    }
    return {
        "capital": capital,
        "count": count,
        "adjust": adjust,
        "symbols": list(frames),
        "skipped": errors,
        "range_by_symbol": ranges,
        "notes": [
            f"${capital:.0f} equal sleeves, fractional shares, next-bar open, no commission, no news.",
            "Default is buy-and-hold; SMA/drawdown only sell after the window is ready.",
            "Longbridge kline history quota is 0; daily --count 1000 is ~4 years.",
            "Prices are forward-adjusted so NVDA/AAPL splits do not fake the 4y tape.",
        ],
        "never_sell": never,
        "candidate": candidate,
        "ranked": sorted(ranked, key=lambda row: float(row["return_pct"]), reverse=True),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sweep hold-plus-exit rules on ~4y daily bars.")
    parser.add_argument("--capital", type=float, default=2000.0)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--adjust", default="forward")
    args = parser.parse_args(argv)
    payload = run_sweep(capital=float(args.capital), count=int(args.count), adjust=str(args.adjust))
    out = ROOT / "analysis" / "output" / "exit_sweep.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    never = payload["never_sell"]
    print(
        f"never_sell  ret={never['return_pct']}%  end={never['ending_equity']}  "
        f"dd={never['max_drawdown_pct']}%"
    )
    for row in payload["ranked"][:12]:
        print(
            f"  {row['id']:28} ret={row['return_pct']:>8}%  "
            f"dd={row['max_drawdown_pct']:>8}%  trades={row['trades']:>4}"
        )
    picked = payload.get("candidate")
    if picked:
        print(f"candidate {picked['id']} ret={picked['return_pct']}% dd={picked['max_drawdown_pct']}%")
    for err in payload.get("skipped") or []:
        print(f"  SKIP {err['ticker']}: {err['error']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
