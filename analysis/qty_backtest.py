"""SMA200 live book: 1 share vs 1/3-share cheap sizing on ~4y daily bars."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.backtest import rows_to_frame
from analysis.book_backtest import _sample_points, buy_hold_exit_signals
from analysis.exit_sweep import hold_plus_exit_signals, run_rule
from analysis.kline import fetch_klines
from analysis.manager import _buy_cfg, _sell_cfg

ROOT = Path(__file__).resolve().parents[1]
SMA200_RULE = {
    "id": "sma200",
    "below_sma": 200,
    "drawdown_from_high": 0.0,
    "high_lookback": 0,
    "need_both": False,
}


def _day_key(stamp: Any) -> str:
    ts = pd.Timestamp(stamp)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert("UTC").strftime("%Y-%m-%d")


def cheap_flags(
    close: pd.Series,
    *,
    lookback: int = 1000,
    min_bars: int = 252,
    percentile: float = 0.20,
) -> list[bool]:
    """Same rule as live ``multi_year_cheap``: no future bars in the window."""
    flags: list[bool] = []
    values = close.astype(float)
    for idx in range(len(values)):
        start = max(0, idx + 1 - int(lookback))
        window = values.iloc[start : idx + 1]
        last = float(values.iloc[idx])
        if len(window) < int(min_bars):
            flags.append(False)
            continue
        threshold = float(window.quantile(float(percentile)))
        rank = float((window <= last).mean())
        flags.append(bool(last <= threshold and rank <= float(percentile) + 1e-9))
    return flags


def tapes_live_qty(
    frames: dict[str, pd.DataFrame],
    *,
    lookback: int,
    min_bars: int,
    percentile: float,
) -> dict[str, dict[str, Any]]:
    tapes: dict[str, dict[str, Any]] = {}
    for symbol, frame in frames.items():
        signals = hold_plus_exit_signals(
            frame,
            below_sma=int(SMA200_RULE["below_sma"]),
            drawdown_from_high=0.0,
            high_lookback=0,
            need_both=False,
        )
        cheap = cheap_flags(
            frame["close"],
            lookback=lookback,
            min_bars=min_bars,
            percentile=percentile,
        )
        opens: dict[str, float] = {}
        closes: dict[str, float] = {}
        sigs: dict[str, str] = {}
        cheap_days: dict[str, bool] = {}
        for idx in range(len(frame)):
            key = _day_key(frame["time"].iloc[idx])
            opens[key] = float(frame["open"].iloc[idx])
            closes[key] = float(frame["close"].iloc[idx])
            sigs[key] = signals[idx]
            cheap_days[key] = bool(cheap[idx])
        tapes[symbol] = {
            "open": opens,
            "close": closes,
            "signal": sigs,
            "cheap": cheap_days,
        }
    return tapes


def tapes_buy_hold(
    frames: dict[str, pd.DataFrame],
    *,
    below_sma: int,
    drawdown_from_high: float,
    high_lookback: int,
    max_extension_pct: float,
) -> dict[str, dict[str, Any]]:
    """Daily tapes using the live buy_hold SELL / HOLD / BUY rules."""
    tapes: dict[str, dict[str, Any]] = {}
    for symbol, frame in frames.items():
        signals = buy_hold_exit_signals(
            frame,
            below_sma=int(below_sma),
            drawdown_from_high=float(drawdown_from_high),
            high_lookback=int(high_lookback),
            max_extension_pct=float(max_extension_pct),
        )
        opens: dict[str, float] = {}
        closes: dict[str, float] = {}
        sigs: dict[str, str] = {}
        for idx in range(len(frame)):
            key = _day_key(frame["time"].iloc[idx])
            opens[key] = float(frame["open"].iloc[idx])
            closes[key] = float(frame["close"].iloc[idx])
            sigs[key] = signals[idx]
        tapes[symbol] = {
            "open": opens,
            "close": closes,
            "signal": sigs,
            "cheap": {key: False for key in closes},
        }
    return tapes


def simulate_qty_book(
    tapes: dict[str, dict[str, Any]],
    capital: float,
    *,
    qty: int = 1,
    qty_cheap: int = 1,
    scale_in: bool = False,
) -> dict[str, Any]:
    """Integer shares, next-bar open. Target 1 or 3; never trim extras until SMA200 SELL.

    ``scale_in`` matches live add-1: each BUY queues one more share (qty) for the
    next open even if already long. At most one working add; SELL still exits all.
    """
    all_days = sorted({day for tape in tapes.values() for day in tape["close"]})
    cash = float(capital)
    shares = {symbol: 0 for symbol in tapes}
    last_close = {symbol: 0.0 for symbol in tapes}
    pending_sell: set[str] = set()
    pending_target: dict[str, int] = {}
    peak = float(capital)
    max_dd = 0.0
    equity: list[dict[str, Any]] = []
    buys = 0
    sells = 0
    top_ups = 0
    cheap_fills = 0
    shares_bought = 0
    cheap_days = 0
    bought_by = {symbol: 0 for symbol in tapes}
    max_held = {symbol: 0 for symbol in tapes}

    def mark() -> float:
        total = cash
        for symbol, held in shares.items():
            if held > 0 and last_close[symbol] > 0:
                total += held * last_close[symbol]
        return total

    for day in all_days:
        for symbol, tape in tapes.items():
            if day in tape["close"]:
                last_close[symbol] = float(tape["close"][day])
            if tape.get("cheap", {}).get(day):
                cheap_days += 1

        for symbol in list(pending_sell):
            tape = tapes[symbol]
            held = shares[symbol]
            if held > 0 and day in tape["open"] and float(tape["open"][day]) > 0:
                cash += held * float(tape["open"][day])
                shares[symbol] = 0
                sells += 1
            pending_sell.discard(symbol)
            pending_target.pop(symbol, None)

        for symbol in list(pending_target):
            tape = tapes[symbol]
            target = int(pending_target[symbol])
            price = float(tape["open"][day]) if day in tape["open"] else 0.0
            held = shares[symbol]
            need = target - held
            if need < 1 or price <= 0:
                pending_target.pop(symbol, None)
                continue
            affordable = int(cash // price)
            fill = min(need, affordable)
            if fill < 1:
                continue
            cash -= fill * price
            shares[symbol] = held + fill
            buys += 1
            shares_bought += fill
            bought_by[symbol] += fill
            max_held[symbol] = max(max_held[symbol], shares[symbol])
            if held > 0:
                top_ups += 1
            if not scale_in and target > qty:
                cheap_fills += 1
            if shares[symbol] >= target:
                pending_target.pop(symbol, None)

        marked = mark()
        peak = max(peak, marked)
        max_dd = min(max_dd, marked - peak)
        equity.append({"time": day, "equity": round(marked, 4), "pnl": round(marked - capital, 4)})

        for symbol, tape in tapes.items():
            if day not in tape["signal"]:
                continue
            signal = tape["signal"][day]
            if signal == "SELL" and shares[symbol] > 0:
                pending_sell.add(symbol)
                pending_target.pop(symbol, None)
            elif signal == "BUY":
                if scale_in:
                    pending_target[symbol] = shares[symbol] + int(qty)
                    pending_sell.discard(symbol)
                else:
                    target = int(qty_cheap) if tape.get("cheap", {}).get(day) else int(qty)
                    if shares[symbol] < target:
                        pending_target[symbol] = target
                        pending_sell.discard(symbol)

    for symbol, held in list(shares.items()):
        if held > 0 and last_close[symbol] > 0:
            cash += held * last_close[symbol]
            shares[symbol] = 0
            sells += 1
    if equity:
        equity[-1]["equity"] = round(cash, 4)
        equity[-1]["pnl"] = round(cash - capital, 4)
    pnl = cash - capital
    dd_pct = (max_dd / capital * 100.0) if capital else 0.0
    return {
        "pnl": round(pnl, 4),
        "return_pct": round(pnl / capital * 100.0, 4) if capital else 0.0,
        "ending_equity": round(cash, 4),
        "capital": round(capital, 4),
        "buys": buys,
        "sells": sells,
        "top_ups": top_ups,
        "cheap_fills": cheap_fills,
        "shares_bought": shares_bought,
        "cheap_day_marks": cheap_days,
        "max_drawdown": round(max_dd, 4),
        "max_drawdown_pct": round(dd_pct, 4),
        "scale_in": scale_in,
        "max_held": max_held,
        "shares_bought_by": bought_by,
        "equity": _sample_points(equity, 24),
    }


LAST_TEN_QTY1 = {
    "pnl": 2937.6,
    "buys": 97,
    "shares_bought": 97,
    "note": "Last published: 10 names + TSM, qty 1, no add, $1M, ~4y daily next-open.",
}


def _tape_span(frames: dict[str, pd.DataFrame]) -> tuple[str | None, str | None]:
    first: str | None = None
    last: str | None = None
    for frame in frames.values():
        if frame.empty:
            continue
        start = _day_key(frame["time"].iloc[0])
        end = _day_key(frame["time"].iloc[-1])
        first = start if first is None or start < first else first
        last = end if last is None or end > last else last
    return first, last


def _without_equity(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "equity"}


def run_add_compare(
    *,
    capital: float,
    count: int,
    adjust: str,
) -> dict[str, Any]:
    """Current add-1-on-BUY vs last hold-1-until-SELL, same daily tape."""
    cfg = json.loads((ROOT / "config" / "watchlist.json").read_text(encoding="utf-8"))
    symbols = [str(name) for name in cfg["symbols"]]
    sell = _sell_cfg(cfg)
    buy = _buy_cfg(cfg)
    frames, errors = load_watchlist_frames(symbols, count=count, adjust=adjust)
    tapes = tapes_live_qty(frames, lookback=1000, min_bars=252, percentile=0.2)
    ten_frames = {sym: frame for sym, frame in frames.items() if len(frame) >= 220}
    ten_tapes = tapes_live_qty(ten_frames, lookback=1000, min_bars=252, percentile=0.2)
    dip_tapes = tapes_buy_hold(
        frames,
        below_sma=int(sell["below_sma"]),
        drawdown_from_high=float(sell["drawdown_from_high"]),
        high_lookback=int(sell["high_lookback"]),
        max_extension_pct=float(buy["max_extension_pct"]),
    )
    dip_ten_tapes = tapes_buy_hold(
        ten_frames,
        below_sma=int(sell["below_sma"]),
        drawdown_from_high=float(sell["drawdown_from_high"]),
        high_lookback=int(sell["high_lookback"]),
        max_extension_pct=float(buy["max_extension_pct"]),
    )
    last_all = simulate_qty_book(tapes, capital, qty=1, qty_cheap=1, scale_in=False)
    add_all = simulate_qty_book(tapes, capital, qty=1, qty_cheap=1, scale_in=True)
    last_ten = simulate_qty_book(ten_tapes, capital, qty=1, qty_cheap=1, scale_in=False)
    add_ten = simulate_qty_book(ten_tapes, capital, qty=1, qty_cheap=1, scale_in=True)
    dip_all = simulate_qty_book(dip_tapes, capital, qty=1, qty_cheap=1, scale_in=True)
    dip_ten = simulate_qty_book(dip_ten_tapes, capital, qty=1, qty_cheap=1, scale_in=True)
    start, end = _tape_span(ten_frames or frames)
    per_symbol = []
    for symbol in list(ten_tapes) or list(tapes):
        tape = (ten_tapes or tapes)[symbol]
        per_symbol.append(
            {
                "ticker": symbol,
                "bars": len(tape["close"]),
                "last_shares_bought": last_ten["shares_bought_by"].get(symbol, 0)
                if symbol in last_ten["shares_bought_by"]
                else last_all["shares_bought_by"].get(symbol, 0),
                "add_shares_bought": add_ten["shares_bought_by"].get(symbol, 0)
                if symbol in add_ten["shares_bought_by"]
                else add_all["shares_bought_by"].get(symbol, 0),
                "last_max_held": last_ten["max_held"].get(symbol, 0)
                if symbol in last_ten["max_held"]
                else last_all["max_held"].get(symbol, 0),
                "add_max_held": add_ten["max_held"].get(symbol, 0)
                if symbol in add_ten["max_held"]
                else add_all["max_held"].get(symbol, 0),
                "dip_shares_bought": dip_ten["shares_bought_by"].get(symbol, 0)
                if symbol in dip_ten["shares_bought_by"]
                else dip_all["shares_bought_by"].get(symbol, 0),
                "dip_max_held": dip_ten["max_held"].get(symbol, 0)
                if symbol in dip_ten["max_held"]
                else dip_all["max_held"].get(symbol, 0),
            }
        )
    return {
        "capital": capital,
        "count": count,
        "adjust": adjust,
        "qty": 1,
        "start": start,
        "end": end,
        "max_extension_pct": float(buy["max_extension_pct"]),
        "symbols": list(frames),
        "ten_symbols": list(ten_frames),
        "skipped": errors,
        "last_published_ten_qty_1": LAST_TEN_QTY1,
        "this_run_ten_hold_1": _without_equity(last_ten),
        "this_run_ten_add_1": _without_equity(add_ten),
        "this_run_ten_dip_add_1": _without_equity(dip_ten),
        "this_run_all_hold_1": _without_equity(last_all),
        "this_run_all_add_1": _without_equity(add_all),
        "this_run_all_dip_add_1": _without_equity(dip_all),
        "ten_hold_1_equity": last_ten["equity"],
        "ten_add_1_equity": add_ten["equity"],
        "ten_dip_add_1_equity": dip_ten["equity"],
        "per_symbol": per_symbol,
        "notes": [
            "Hold-1 = BUY until 1 share, skip until SMA200 SELL.",
            "Add-1 = each BUY day queues 1 more share at next open (old live rule).",
            "Dip-add-1 = 8% add band (buy.max_extension_pct), even if live buy.add is always_add.",
            "Daily bars only. Live RTH ticks every 30 minutes would add faster on BUY days.",
        ],
    }


def load_watchlist_frames(
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
            if len(frame) < 40:
                raise RuntimeError(f"not enough daily bars ({len(frame)})")
            frames[symbol] = frame
        except Exception as exc:  # noqa: BLE001 — one name must not abort the book
            errors.append({"ticker": symbol, "error": str(exc)})
    return frames, errors


def run_qty_compare(
    *,
    capital: float,
    count: int,
    adjust: str,
    qty: int,
    qty_cheap: int,
    lookback: int,
    min_bars: int,
    percentile: float,
) -> dict[str, Any]:
    cfg = json.loads((ROOT / "config" / "watchlist.json").read_text(encoding="utf-8"))
    symbols = [str(name) for name in cfg["symbols"]]
    frames, errors = load_watchlist_frames(symbols, count=count, adjust=adjust)
    sleeve_frames = {sym: frame for sym, frame in frames.items() if len(frame) >= 220}
    sleeve = run_rule(sleeve_frames, SMA200_RULE, 2000.0) if sleeve_frames else {}
    tapes = tapes_live_qty(
        frames,
        lookback=lookback,
        min_bars=min_bars,
        percentile=percentile,
    )
    always_one = simulate_qty_book(tapes, capital, qty=qty, qty_cheap=qty)
    cheap_three = simulate_qty_book(tapes, capital, qty=qty, qty_cheap=qty_cheap)
    ten_frames = {sym: frame for sym, frame in frames.items() if len(frame) >= 220}
    ten_tapes = tapes_live_qty(
        ten_frames,
        lookback=lookback,
        min_bars=min_bars,
        percentile=percentile,
    )
    ten_one = simulate_qty_book(ten_tapes, capital, qty=1, qty_cheap=1)
    ten_three = simulate_qty_book(ten_tapes, capital, qty=1, qty_cheap=3)
    cheap_buy = 0
    cheap_sell = 0
    for tape in ten_tapes.values():
        for day, is_cheap in tape["cheap"].items():
            if not is_cheap:
                continue
            if tape["signal"].get(day) == "BUY":
                cheap_buy += 1
            else:
                cheap_sell += 1
    nine_frames = {sym: frame for sym, frame in ten_frames.items() if sym != "TSM.US"}
    nine_sleeve = run_rule(nine_frames, SMA200_RULE, 2000.0) if nine_frames else {}
    nine_tapes = tapes_live_qty(
        nine_frames,
        lookback=lookback,
        min_bars=min_bars,
        percentile=percentile,
    )
    nine_one = simulate_qty_book(nine_tapes, capital, qty=1, qty_cheap=1)
    per_symbol = []
    for symbol, tape in tapes.items():
        n_cheap = sum(1 for flag in tape["cheap"].values() if flag)
        per_symbol.append(
            {
                "ticker": symbol,
                "bars": len(tape["close"]),
                "cheap_days": n_cheap,
                "cheap_pct": round(100.0 * n_cheap / len(tape["close"]), 2) if tape["close"] else 0.0,
            }
        )
    live = sleeve.get("totals", {}).get("live", {}) if sleeve else {}
    nine_live = nine_sleeve.get("totals", {}).get("live", {}) if nine_sleeve else {}
    return {
        "capital": capital,
        "count": count,
        "adjust": adjust,
        "qty": qty,
        "qty_cheap": qty_cheap,
        "lookback": lookback,
        "min_bars": min_bars,
        "percentile": percentile,
        "symbols": list(frames),
        "skipped": errors,
        "prior_sma200_sleeve_2000": {
            "pnl": 7908.095,
            "return_pct": 395.4048,
            "ending_equity": 9908.0949,
            "trades": 89,
            "note": "Last published SMA200: $2000 equal sleeves, fractional, 9 names, no TSM.",
        },
        "sma200_sleeve_2000_this_run": {
            "pnl": live.get("pnl"),
            "return_pct": live.get("return_pct"),
            "ending_equity": live.get("ending_equity"),
            "trades": live.get("trades"),
            "symbols": list(sleeve_frames),
        },
        "nine_names_sleeve_2000": {
            "pnl": nine_live.get("pnl"),
            "return_pct": nine_live.get("return_pct"),
            "ending_equity": nine_live.get("ending_equity"),
            "trades": nine_live.get("trades"),
            "symbols": list(nine_frames),
        },
        "always_1": {key: value for key, value in always_one.items() if key != "equity"},
        "cheap_1_or_3": {key: value for key, value in cheap_three.items() if key != "equity"},
        "ten_names_qty_1": {
            "symbols": list(ten_frames),
            **{key: value for key, value in ten_one.items() if key != "equity"},
        },
        "ten_names_qty_1_or_3": {
            "symbols": list(ten_frames),
            "cheap_days_with_buy": cheap_buy,
            "cheap_days_with_sell": cheap_sell,
            **{key: value for key, value in ten_three.items() if key != "equity"},
        },
        "nine_names_qty_1": {
            "symbols": list(nine_frames),
            **{key: value for key, value in nine_one.items() if key != "equity"},
        },
        "always_1_equity": always_one["equity"],
        "cheap_1_or_3_equity": cheap_three["equity"],
        "ten_names_qty_1_equity": ten_one["equity"],
        "ten_names_qty_1_or_3_equity": ten_three["equity"],
        "per_symbol": per_symbol,
        "notes": [
            "Signals = live SMA200 (sell if close < SMA200, else BUY).",
            "Cheap = close in the cheapest 20% of the lookback window so far (min 252 bars).",
            "Fills = next-bar open, integer shares, $1M sim cash, never trim extras until SELL.",
            "Last SMA200 $2000 sleeve is fractional equal-weight; 1/3-share book is not that test.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SMA200 1-share vs 1/3 cheap sizing backtest.")
    parser.add_argument("--capital", type=float, default=1_000_000.0)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--adjust", default="forward")
    parser.add_argument(
        "--compare-add",
        action="store_true",
        help="Compare last hold-1 book vs current add-1-on-BUY on the same tape.",
    )
    args = parser.parse_args(argv)
    if args.compare_add:
        payload = run_add_compare(
            capital=float(args.capital),
            count=int(args.count),
            adjust=str(args.adjust),
        )
        out = ROOT / "analysis" / "output" / "add_backtest.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        prior = payload["last_published_ten_qty_1"]
        hold = payload["this_run_ten_hold_1"]
        add = payload["this_run_ten_add_1"]
        dip = payload["this_run_ten_dip_add_1"]
        hold_all = payload["this_run_all_hold_1"]
        add_all = payload["this_run_all_add_1"]
        dip_all = payload["this_run_all_dip_add_1"]
        print(
            f"window {payload.get('start')} → {payload.get('end')}  "
            f"ten={len(payload.get('ten_symbols') or [])}  all={len(payload.get('symbols') or [])}  "
            f"max_extension={payload.get('max_extension_pct')}"
        )
        print(
            f"last published 10 names qty 1   pnl ${prior['pnl']}  buys={prior['buys']}"
        )
        print(
            f"this tape 10 names hold-1       pnl ${hold['pnl']}  buys={hold['buys']}  "
            f"shares={hold['shares_bought']}"
        )
        print(
            f"this tape 10 names add-1        pnl ${add['pnl']}  buys={add['buys']}  "
            f"shares={add['shares_bought']}  top_ups={add['top_ups']}"
        )
        print(
            f"this tape 10 names dip-add-1    pnl ${dip['pnl']}  buys={dip['buys']}  "
            f"shares={dip['shares_bought']}  top_ups={dip['top_ups']}"
        )
        print(
            f"this tape all names hold-1      pnl ${hold_all['pnl']}  buys={hold_all['buys']}  "
            f"shares={hold_all['shares_bought']}"
        )
        print(
            f"this tape all names add-1       pnl ${add_all['pnl']}  buys={add_all['buys']}  "
            f"shares={add_all['shares_bought']}  top_ups={add_all['top_ups']}"
        )
        print(
            f"this tape all names dip-add-1   pnl ${dip_all['pnl']}  buys={dip_all['buys']}  "
            f"shares={dip_all['shares_bought']}  top_ups={dip_all['top_ups']}"
        )
        print(f"wrote {out}")
        return 0
    cfg = json.loads((ROOT / "config" / "watchlist.json").read_text(encoding="utf-8"))
    cheap = cfg.get("cheap") if isinstance(cfg.get("cheap"), dict) else {}
    payload = run_qty_compare(
        capital=float(args.capital),
        count=int(args.count),
        adjust=str(args.adjust),
        qty=max(1, int(cfg.get("qty") or 1)),
        qty_cheap=max(1, int(cfg.get("qty_cheap") or 3)),
        lookback=int(cheap.get("lookback") or 1000),
        min_bars=int(cheap.get("min_bars") or 252),
        percentile=float(cheap.get("percentile") or 0.2),
    )
    out = ROOT / "analysis" / "output" / "qty_backtest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    one = payload["always_1"]
    three = payload["cheap_1_or_3"]
    ten = payload["ten_names_qty_1"]
    ten3 = payload["ten_names_qty_1_or_3"]
    nine = payload["nine_names_qty_1"]
    nine_sleeve_row = payload["nine_names_sleeve_2000"]
    prior = payload["prior_sma200_sleeve_2000"]
    sleeve = payload["sma200_sleeve_2000_this_run"]
    print(f"prior SMA200 $2000 sleeve  {prior['return_pct']}%  end ${prior['ending_equity']}")
    print(
        f"this run $2000 sleeve      {sleeve.get('return_pct')}%  end ${sleeve.get('ending_equity')}  "
        f"names={len(sleeve.get('symbols') or [])}"
    )
    print(
        f"live 1-share $1M           pnl ${one['pnl']}  buys={one['buys']}  shares={one['shares_bought']}"
    )
    print(
        f"live 1/3 cheap $1M         pnl ${three['pnl']}  buys={three['buys']}  "
        f"shares={three['shares_bought']}  cheap_fills={three['cheap_fills']}  top_ups={three['top_ups']}"
    )
    print(
        f"9 names $2000 sleeve       {nine_sleeve_row.get('return_pct')}%  end ${nine_sleeve_row.get('ending_equity')}"
    )
    print(
        f"10 names qty 1 $1M         pnl ${ten['pnl']}  buys={ten['buys']}  shares={ten['shares_bought']}"
    )
    print(
        f"10 names 1/3 cheap $1M     pnl ${ten3['pnl']}  buys={ten3['buys']}  "
        f"shares={ten3['shares_bought']}  cheap_fills={ten3['cheap_fills']}  "
        f"cheap_buy_days={ten3.get('cheap_days_with_buy')}  cheap_sell_days={ten3.get('cheap_days_with_sell')}"
    )
    print(
        f"9 names qty 1 $1M          pnl ${nine['pnl']}  buys={nine['buys']}  shares={nine['shares_bought']}"
    )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
