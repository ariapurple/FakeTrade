"""Backtest the grouped hold book: configured rules vs pure hold.

News is not replayed (no historical headline tape without lookahead).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.backtest import rows_to_frame
from analysis.books import load_books
from analysis.kline import fetch_klines
from analysis.manager import _sell_cfg, strategy_from_config
from analysis.session import in_us_rth
from analysis.theory_backtest import (
    CAPITAL,
    TEST_BARS,
    WARMUP,
    _portfolio_max_dd,
    _without_equity,
    simulate_buy_hold_capital,
    simulate_capital,
)

ROOT = Path(__file__).resolve().parents[1]
PRIOR_LONG = ["AAPL.US", "NVDA.US", "DRAM.US", "VOO.US"]
Signal = str


def buy_hold_exit_signals(
    frame: pd.DataFrame,
    *,
    below_sma: int = 60,
    drawdown_from_high: float = 0.25,
    high_lookback: int = 60,
) -> list[Signal]:
    """Match live manager: SELL on SMA/drawdown, otherwise BUY. No news.

    ``below_sma`` 0 and ``drawdown_from_high`` 0 means never-sell (always BUY).
    """
    close = frame["close"].astype(float)
    if not below_sma and float(drawdown_from_high) <= 0:
        return ["BUY"] * len(frame)
    sma = close.rolling(int(below_sma)).mean() if below_sma else None
    peak = close.rolling(int(high_lookback)).max() if high_lookback else None
    out: list[Signal] = []
    for idx in range(len(frame)):
        if idx < WARMUP:
            out.append("HOLD")
            continue
        last = float(close.iloc[idx])
        sell = False
        if sma is not None and pd.notna(sma.iloc[idx]) and last < float(sma.iloc[idx]):
            sell = True
        if (
            peak is not None
            and drawdown_from_high > 0
            and pd.notna(peak.iloc[idx])
            and last <= float(peak.iloc[idx]) * (1.0 - float(drawdown_from_high))
        ):
            sell = True
        out.append("SELL" if sell else "BUY")
    return out


def swing_signals(frame: pd.DataFrame, *, fast: int = 10, slow: int = 20) -> list[Signal]:
    close = frame["close"].astype(float)
    fast_ma = close.rolling(int(fast)).mean()
    slow_ma = close.rolling(int(slow)).mean()
    out: list[Signal] = []
    for idx in range(len(frame)):
        if idx < max(WARMUP, slow):
            out.append("HOLD")
            continue
        f_val = fast_ma.iloc[idx]
        s_val = slow_ma.iloc[idx]
        if pd.isna(f_val) or pd.isna(s_val):
            out.append("HOLD")
        elif float(f_val) > float(s_val):
            out.append("BUY")
        elif float(f_val) < float(s_val):
            out.append("SELL")
        else:
            out.append("HOLD")
    return out


def fill_is_rth(stamp: Any, period: str) -> bool:
    """Daily bars are cash-session closes. Intraday bars must sit in 09:30-16:00 ET."""
    if period in {"day", "1d", "1w", "week"}:
        return True
    ts = pd.Timestamp(stamp)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return in_us_rth(ts.to_pydatetime())


def rth_mask(times: list[Any], period: str) -> list[bool]:
    return [fill_is_rth(stamp, period) for stamp in times]


def _sample_points(points: list[dict[str, Any]], count: int = 24) -> list[dict[str, Any]]:
    if len(points) <= count:
        return points
    last = len(points) - 1
    indexes = [round(idx * last / (count - 1)) for idx in range(count)]
    return [points[idx] for idx in indexes]


def _combined_equity(named: dict[str, Any], which: str, count: int = 24) -> list[dict[str, Any]]:
    curves = [list(row[which].get("equity") or []) for row in named.values()]
    curves = [curve for curve in curves if curve]
    if not curves:
        return []
    master = max(curves, key=len)
    times = [str(point["time"]) for point in master]
    combined: list[dict[str, Any]] = []
    for time in times:
        total = 0.0
        for curve in curves:
            last = float(curve[0]["equity"])
            for point in curve:
                if str(point["time"]) <= time:
                    last = float(point["equity"])
                else:
                    break
            total += last
        combined.append({"time": time, "equity": round(total, 2)})
    return _sample_points(combined, count)


def _slice_test(frame: pd.DataFrame, test_bars: int | None) -> tuple[pd.DataFrame, int]:
    if test_bars and len(frame) > test_bars:
        test = frame.iloc[-test_bars:].reset_index(drop=True)
        start_idx = len(frame) - len(test)
        return test, start_idx
    return frame.reset_index(drop=True), 0


def backtest_symbol(
    frame: pd.DataFrame,
    capital: float,
    signals: list[Signal],
    *,
    test_bars: int | None,
    period: str,
) -> dict[str, Any]:
    test, start_idx = _slice_test(frame, test_bars)
    times = test["time"].tolist()
    opens = test["open"].astype(float).tolist()
    closes = test["close"].astype(float).tolist()
    sliced = signals[start_idx : start_idx + len(test)]
    if len(sliced) != len(test):
        sliced = signals[-len(test) :]
    mask = rth_mask(times, period)
    hold = simulate_buy_hold_capital(times, opens, closes, capital)
    live = simulate_capital(times, opens, closes, sliced, "long_only", capital, rth_fill=mask)
    live["buy_hold_pnl"] = hold["pnl"]
    live["buy_hold_return_pct"] = hold["return_pct"]
    return {
        "buy_hold": hold,
        "live": live,
        "bars": len(test),
        "range": {"start": str(times[0]), "end": str(times[-1])},
    }


def _totals(per_symbol: dict[str, Any], capital: float, sleeve: float) -> dict[str, Any]:
    names = ["buy_hold", "live"]
    totals = {name: {"pnl": 0.0, "ending_equity": 0.0, "trades": 0, "wins": 0} for name in names}
    curves: dict[str, list[tuple[float, list[dict[str, Any]]]]] = {name: [] for name in names}
    for row in per_symbol.values():
        for name in names:
            block = row[name]
            totals[name]["pnl"] += float(block["pnl"])
            totals[name]["ending_equity"] += float(block["ending_equity"])
            totals[name]["trades"] += int(block.get("trades") or 0)
            totals[name]["wins"] += int(block.get("wins") or 0)
            curves[name].append((sleeve, list(block.get("equity") or [])))
    out: dict[str, Any] = {}
    for name, block in totals.items():
        trades = int(block["trades"])
        pnl = round(float(block["pnl"]), 4)
        ending = round(float(block["ending_equity"]), 4)
        max_dd, dd_pct = _portfolio_max_dd(curves[name])
        out[name] = {
            "pnl": pnl,
            "ending_equity": ending,
            "capital": round(capital, 4),
            "return_pct": round(pnl / capital * 100.0, 4) if capital else 0.0,
            "max_drawdown": max_dd,
            "max_drawdown_pct": dd_pct,
            "trades": trades,
            "wins": int(block["wins"]),
            "win_rate": round(block["wins"] / trades, 4) if trades else None,
            "sleeve_capital": round(sleeve, 4),
            "sleeves": len(per_symbol),
        }
    return out


def run_symbols(
    symbols: list[str],
    *,
    period: str,
    count: int,
    capital: float,
    signal_kind: str,
    sell: dict[str, Any] | None,
    test_bars: int | None,
) -> dict[str, Any]:
    frames: dict[str, pd.DataFrame] = {}
    errors: list[dict[str, str]] = []
    for symbol in symbols:
        try:
            frame = rows_to_frame(fetch_klines(symbol, period=period, count=count))
            min_bars = WARMUP + 20
            if len(frame) <= min_bars:
                raise RuntimeError(f"not enough {period} bars ({len(frame)})")
            frames[symbol] = frame
        except Exception as exc:  # noqa: BLE001
            errors.append({"ticker": symbol, "error": str(exc)})
    n_sleeves = len(frames)
    sleeve = (capital / n_sleeves) if n_sleeves else 0.0
    named: dict[str, Any] = {}
    for symbol, frame in frames.items():
        if signal_kind == "buy_hold":
            cfg = sell or {}
            signals = buy_hold_exit_signals(
                frame,
                below_sma=int(cfg.get("below_sma") or 0),
                drawdown_from_high=float(cfg.get("drawdown_from_high") or 0),
                high_lookback=int(cfg.get("high_lookback") or 0),
            )
        elif signal_kind == "swing":
            signals = swing_signals(frame)
        else:
            raise ValueError(f"unknown signal_kind {signal_kind}")
        named[symbol] = backtest_symbol(frame, sleeve, signals, test_bars=test_bars, period=period)
    published = {
        symbol: {
            "bars": row["bars"],
            "range": row["range"],
            "sleeve_capital": round(sleeve, 4),
            "buy_hold": _without_equity(row["buy_hold"]),
            "live": _without_equity(row["live"]),
        }
        for symbol, row in named.items()
    }
    totals = _totals(named, capital, sleeve)
    return {
        "period": period,
        "count": count,
        "test_bars": test_bars,
        "signal_kind": signal_kind,
        "capital": capital,
        "notes": [
            f"${capital:.0f} equal sleeves, fractional shares, next-bar open, no commission.",
            "Signals refresh every bar; fills only on US regular hours (09:30-16:00 ET).",
            "News gate is omitted in this replay (would look ahead or miss headlines).",
        ],
        "equity": {
            "buy_hold": _combined_equity(named, "buy_hold"),
            "live": _combined_equity(named, "live"),
        },
        "totals": totals,
        "symbols": published,
        "errors": errors,
    }


def run_all(capital: float = CAPITAL) -> dict[str, Any]:
    cfg = json.loads((ROOT / "config" / "watchlist.json").read_text(encoding="utf-8"))
    sell = _sell_cfg(cfg)
    kind = "swing" if strategy_from_config(cfg) == "swing" else "buy_hold"
    hold_capital = float(cfg.get("starting_usd") or cfg.get("budget_usd") or capital)
    prior = run_symbols(
        PRIOR_LONG,
        period="day",
        count=400,
        capital=capital,
        signal_kind="buy_hold",
        sell=sell,
        test_bars=TEST_BARS,
    )
    hold_book = run_symbols(
        list(cfg["symbols"]),
        period=str(cfg.get("period", "day")),
        count=400,
        capital=hold_capital,
        signal_kind=kind,
        sell=sell if kind == "buy_hold" else None,
        test_bars=TEST_BARS,
    )
    return {
        "capital": hold_capital,
        "prior_four_name_hold": {
            "symbols": PRIOR_LONG,
            "note": "Same four names as the earlier $1000 hold backtest.",
            **prior,
        },
        "hold": {
            "strategy": strategy_from_config(cfg),
            "sell": sell if kind == "buy_hold" else None,
            **hold_book,
        },
        "books_loaded": [book["id"] for book in load_books(ROOT)],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest the grouped hold book vs buy-and-hold.")
    parser.add_argument("--capital", type=float, default=CAPITAL)
    args = parser.parse_args(argv)
    payload = run_all(capital=float(args.capital))
    out = ROOT / "analysis" / "output" / "book_backtest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    def _print_book(title: str, block: dict[str, Any]) -> None:
        print(title)
        totals = block.get("totals") or {}
        for name, row in totals.items():
            print(
                f"  {name:12} pnl={row['pnl']:>10} ret={row['return_pct']:>8}% "
                f"end={row['ending_equity']:>10} trades={row['trades']:>3}"
            )
        for err in block.get("errors") or []:
            print(f"  ERROR {err['ticker']}: {err['error']}")

    _print_book("prior four (AAPL NVDA DRAM VOO)", payload["prior_four_name_hold"])
    _print_book("hold book", payload["hold"])
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
