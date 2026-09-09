"""1-year daily backtests of strategy_theory.md rules vs buy-and-hold.

Elliott wave counting is not encoded: it is too subjective to replay without lookahead.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable, Literal, assert_never

import numpy as np
import pandas as pd

from analysis.backtest import rows_to_frame
from analysis.kline import fetch_klines

Signal = Literal["BUY", "SELL", "HOLD"]
StrategyFn = Callable[[pd.DataFrame], list[Signal]]
Mode = Literal["long_only", "always_in"]
TEST_BARS = 252
WARMUP = 60
CAPITAL = 1000.0


def _cross_up(fast: pd.Series, slow: pd.Series) -> pd.Series:
    return (fast.shift(1) <= slow.shift(1)) & (fast > slow)


def _cross_down(fast: pd.Series, slow: pd.Series) -> pd.Series:
    return (fast.shift(1) >= slow.shift(1)) & (fast < slow)


def ma20_granville(frame: pd.DataFrame) -> list[Signal]:
    close = frame["close"]
    ma = close.rolling(20).mean()
    rising = ma > ma.shift(1)
    falling = ma < ma.shift(1)
    buy = _cross_up(close, ma) & rising
    sell = _cross_down(close, ma) & falling
    return _from_flags(buy, sell, len(frame))


def gold_10_20(frame: pd.DataFrame) -> list[Signal]:
    close = frame["close"]
    fast = close.rolling(10).mean()
    slow = close.rolling(20).mean()
    return _from_flags(_cross_up(fast, slow), _cross_down(fast, slow), len(frame))


def gold_20_60(frame: pd.DataFrame) -> list[Signal]:
    close = frame["close"]
    fast = close.rolling(20).mean()
    slow = close.rolling(60).mean()
    return _from_flags(_cross_up(fast, slow), _cross_down(fast, slow), len(frame))


def volume_breakout(frame: pd.DataFrame) -> list[Signal]:
    high20 = frame["high"].rolling(20).max().shift(1)
    low10 = frame["low"].rolling(10).min().shift(1)
    vol_avg = frame["volume"].rolling(20).mean().shift(1)
    buy = (frame["close"] > high20) & (frame["volume"] > 1.5 * vol_avg)
    sell = frame["close"] < low10
    return _from_flags(buy, sell, len(frame))


def donchian_20_10(frame: pd.DataFrame) -> list[Signal]:
    high20 = frame["high"].rolling(20).max().shift(1)
    low10 = frame["low"].rolling(10).min().shift(1)
    return _from_flags(frame["close"] > high20, frame["close"] < low10, len(frame))


def donchian_10_5(frame: pd.DataFrame) -> list[Signal]:
    high10 = frame["high"].rolling(10).max().shift(1)
    low5 = frame["low"].rolling(5).min().shift(1)
    return _from_flags(frame["close"] > high10, frame["close"] < low5, len(frame))


def hammer_support(frame: pd.DataFrame) -> list[Signal]:
    body = (frame["close"] - frame["open"]).abs().clip(lower=1e-6)
    lower = np.minimum(frame["open"], frame["close"]) - frame["low"]
    upper = frame["high"] - np.maximum(frame["open"], frame["close"])
    support = frame["low"].rolling(20).min().shift(1)
    ma20 = frame["close"].rolling(20).mean()
    buy = (lower > 2 * body) & (lower > upper) & (frame["low"] <= support * 1.01)
    sell = frame["close"] < ma20
    return _from_flags(buy, sell, len(frame))


def wyckoff_spring(frame: pd.DataFrame) -> list[Signal]:
    rng_low = frame["low"].rolling(20).min().shift(1)
    rng_high = frame["high"].rolling(20).max().shift(1)
    vol_avg = frame["volume"].rolling(20).mean().shift(1)
    spring = (
        (frame["low"] < rng_low)
        & (frame["close"] > rng_low)
        & (frame["close"] < rng_high)
        & (frame["volume"] > vol_avg)
    )
    sell = frame["close"] < rng_low
    return _from_flags(spring, sell, len(frame))


def combo_ma_vol(frame: pd.DataFrame) -> list[Signal]:
    """Guidebook combo: 20/60 MA uptrend + volume-confirmed 20-day breakout."""
    ma20 = frame["close"].rolling(20).mean()
    ma60 = frame["close"].rolling(60).mean()
    uptrend = (frame["close"] > ma20) & (ma20 > ma60)
    high20 = frame["high"].rolling(20).max().shift(1)
    low10 = frame["low"].rolling(10).min().shift(1)
    vol_avg = frame["volume"].rolling(20).mean().shift(1)
    buy = uptrend & (frame["close"] > high20) & (frame["volume"] > 1.5 * vol_avg)
    sell = frame["close"] < low10
    return _from_flags(buy, sell, len(frame))


def _from_flags(buy: pd.Series, sell: pd.Series, n: int) -> list[Signal]:
    out: list[Signal] = []
    for idx in range(n):
        if idx < WARMUP:
            out.append("HOLD")
        elif bool(buy.iloc[idx]):
            out.append("BUY")
        elif bool(sell.iloc[idx]):
            out.append("SELL")
        else:
            out.append("HOLD")
    return out


def simulate(
    times: list[pd.Timestamp],
    opens: list[float],
    closes: list[float],
    decisions: list[Signal],
    mode: Mode,
) -> dict[str, Any]:
    cash = 0.0
    shares = 0
    entry: float | None = None
    trades: list[dict[str, Any]] = []
    peak = 0.0
    max_dd = 0.0

    def close_position(fill: float, fill_time: pd.Timestamp, note: str | None = None) -> None:
        nonlocal cash, shares, entry
        if shares == 0 or fill <= 0:
            return
        if shares == 1:
            cash += fill
            pnl = fill - float(entry or fill)
            row: dict[str, Any] = {"side": "SELL", "time": str(fill_time), "price": fill, "pnl": round(pnl, 4)}
        else:
            cash -= fill
            pnl = float(entry or fill) - fill
            row = {"side": "COVER", "time": str(fill_time), "price": fill, "pnl": round(pnl, 4)}
        if note:
            row["note"] = note
        trades.append(row)
        shares = 0
        entry = None

    def open_long(fill: float, fill_time: pd.Timestamp) -> None:
        nonlocal cash, shares, entry
        cash -= fill
        shares = 1
        entry = fill
        trades.append({"side": "BUY", "time": str(fill_time), "price": fill})

    def open_short(fill: float, fill_time: pd.Timestamp) -> None:
        nonlocal cash, shares, entry
        cash += fill
        shares = -1
        entry = fill
        trades.append({"side": "SHORT", "time": str(fill_time), "price": fill})

    for idx in range(len(decisions) - 1):
        decision = decisions[idx]
        fill = float(opens[idx + 1])
        fill_time = times[idx + 1]
        if mode == "long_only":
            if decision == "BUY" and shares == 0 and fill > 0:
                open_long(fill, fill_time)
            elif decision == "SELL" and shares == 1 and fill > 0:
                close_position(fill, fill_time)
        elif mode == "always_in":
            if decision == "BUY" and shares != 1 and fill > 0:
                close_position(fill, fill_time)
                open_long(fill, fill_time)
            elif decision == "SELL" and shares != -1 and fill > 0:
                close_position(fill, fill_time)
                open_short(fill, fill_time)
        else:
            assert_never(mode)
        mark = cash + shares * float(closes[idx])
        peak = max(peak, mark)
        if peak:
            max_dd = min(max_dd, mark - peak)
    if shares != 0:
        close_position(float(closes[-1]), times[-1], "mark-to-last-close")
    closed = [row for row in trades if "pnl" in row]
    wins = [row for row in closed if float(row["pnl"]) > 0]
    start_price = float(opens[0])
    end_price = float(closes[-1])
    return {
        "pnl": round(cash, 4),
        "trades": len(closed),
        "wins": len(wins),
        "win_rate": round(len(wins) / len(closed), 4) if closed else None,
        "max_drawdown": round(max_dd, 4),
        "buy_hold_pnl": round(end_price - start_price, 4),
        "fills": closed[:6],
    }


def _empty_capital_result(capital: float) -> dict[str, Any]:
    return {
        "pnl": 0.0,
        "return_pct": 0.0,
        "ending_equity": round(capital, 4),
        "capital": round(capital, 4),
        "trades": 0,
        "wins": 0,
        "win_rate": None,
        "max_drawdown": 0.0,
        "max_drawdown_pct": 0.0,
        "fills": [],
        "equity": [],
    }


def _summarize_capital(
    capital: float,
    cash: float,
    trades: list[dict[str, Any]],
    max_dd: float,
    equity: list[dict[str, Any]],
) -> dict[str, Any]:
    closed = [row for row in trades if "pnl" in row]
    wins = [row for row in closed if float(row["pnl"]) > 0]
    ending = cash
    pnl = ending - capital
    dd_pct = (max_dd / capital * 100.0) if capital else 0.0
    return {
        "pnl": round(pnl, 4),
        "return_pct": round(pnl / capital * 100.0, 4) if capital else 0.0,
        "ending_equity": round(ending, 4),
        "capital": round(capital, 4),
        "trades": len(closed),
        "wins": len(wins),
        "win_rate": round(len(wins) / len(closed), 4) if closed else None,
        "max_drawdown": round(max_dd, 4),
        "max_drawdown_pct": round(dd_pct, 4),
        "fills": closed[:6],
        "equity": equity,
    }


def simulate_buy_hold_capital(
    times: list[pd.Timestamp],
    opens: list[float],
    closes: list[float],
    capital: float,
) -> dict[str, Any]:
    """Fully invest ``capital`` at the first open; mark to each close. Fractional shares."""
    if capital <= 0 or not opens or float(opens[0]) <= 0:
        return _empty_capital_result(capital)
    fill = float(opens[0])
    shares = capital / fill
    cash = 0.0
    peak = capital
    max_dd = 0.0
    equity: list[dict[str, Any]] = []
    for idx, close in enumerate(closes):
        mark = shares * float(close)
        peak = max(peak, mark)
        max_dd = min(max_dd, mark - peak)
        equity.append({"time": str(times[idx]), "equity": round(mark, 4)})
    cash = shares * float(closes[-1])
    result = _summarize_capital(capital, cash, [], max_dd, equity)
    result["trades"] = 1
    result["wins"] = 1 if cash > capital else 0
    result["win_rate"] = 1.0 if cash > capital else 0.0
    result["fills"] = [
        {
            "side": "BUY",
            "time": str(times[0]),
            "price": fill,
            "qty": round(shares, 6),
        },
        {
            "side": "SELL",
            "time": str(times[-1]),
            "price": float(closes[-1]),
            "qty": round(shares, 6),
            "pnl": round(cash - capital, 4),
            "note": "mark-to-last-close",
        },
    ]
    return result


def simulate_capital(
    times: list[pd.Timestamp],
    opens: list[float],
    closes: list[float],
    decisions: list[Signal],
    mode: Mode,
    capital: float,
    rth_fill: list[bool] | None = None,
) -> dict[str, Any]:
    """Trade fractional shares with a cash account. BUY spends all cash; SELL sells all shares.

    Signals may update on every bar. Fills happen only on bars where ``rth_fill`` is true
    (US regular hours). If omitted, every bar is fillable.
    """
    cash = float(capital)
    shares = 0.0
    entry: float | None = None
    trades: list[dict[str, Any]] = []
    peak = capital
    max_dd = 0.0
    equity: list[dict[str, Any]] = []
    can_fill = rth_fill if rth_fill is not None else [True] * len(times)

    def mark_to(idx: int) -> None:
        nonlocal peak, max_dd
        price = float(closes[idx])
        marked = cash + shares * price
        peak = max(peak, marked)
        max_dd = min(max_dd, marked - peak)
        equity.append({"time": str(times[idx]), "equity": round(marked, 4)})

    def close_position(fill: float, fill_time: pd.Timestamp, note: str | None = None) -> None:
        nonlocal cash, shares, entry
        if shares == 0 or fill <= 0:
            return
        qty = abs(shares)
        pnl = shares * (fill - float(entry or fill))
        cash += shares * fill
        side = "SELL" if shares > 0 else "COVER"
        row: dict[str, Any] = {
            "side": side,
            "time": str(fill_time),
            "price": fill,
            "qty": round(qty, 6),
            "pnl": round(pnl, 4),
        }
        if note:
            row["note"] = note
        trades.append(row)
        shares = 0.0
        entry = None

    def open_long(fill: float, fill_time: pd.Timestamp) -> None:
        nonlocal cash, shares, entry
        if cash <= 0 or fill <= 0:
            return
        qty = cash / fill
        cash -= qty * fill
        shares = qty
        entry = fill
        trades.append({"side": "BUY", "time": str(fill_time), "price": fill, "qty": round(qty, 6)})

    def open_short(fill: float, fill_time: pd.Timestamp) -> None:
        nonlocal cash, shares, entry
        if cash <= 0 or fill <= 0:
            return
        qty = cash / fill
        cash += qty * fill
        shares = -qty
        entry = fill
        trades.append({"side": "SHORT", "time": str(fill_time), "price": fill, "qty": round(qty, 6)})

    if times:
        mark_to(0)
    for idx in range(len(decisions) - 1):
        decision = decisions[idx]
        fill = float(opens[idx + 1])
        fill_time = times[idx + 1]
        allowed = True if idx + 1 >= len(can_fill) else bool(can_fill[idx + 1])
        if allowed:
            if mode == "long_only":
                if decision == "BUY" and shares == 0 and fill > 0:
                    open_long(fill, fill_time)
                elif decision == "SELL" and shares > 0 and fill > 0:
                    close_position(fill, fill_time)
            elif mode == "always_in":
                if decision == "BUY" and shares <= 0 and fill > 0:
                    close_position(fill, fill_time)
                    open_long(fill, fill_time)
                elif decision == "SELL" and shares >= 0 and fill > 0:
                    close_position(fill, fill_time)
                    open_short(fill, fill_time)
            else:
                assert_never(mode)
        mark_to(idx + 1)
    if shares != 0:
        close_position(float(closes[-1]), times[-1], "mark-to-last-close")
        if equity:
            equity[-1]["equity"] = round(cash, 4)
    return _summarize_capital(capital, cash, trades, max_dd, equity)


def _sleeve_equity_on(day: str, start_capital: float, curve: list[dict[str, Any]]) -> float:
    """Cash until the first bar, then last known mark (forward-filled)."""
    if not curve:
        return start_capital
    first = str(curve[0]["time"])[:10]
    if day < first:
        return start_capital
    last_eq = start_capital
    for point in curve:
        point_day = str(point["time"])[:10]
        if point_day > day:
            break
        last_eq = float(point["equity"])
        if point_day == day:
            return last_eq
    return last_eq


def _portfolio_max_dd(
    sleeve_curves: list[tuple[float, list[dict[str, Any]]]],
) -> tuple[float, float]:
    """Sum sleeve equity on the union calendar. Idle sleeves stay in cash until listed."""
    days = sorted({str(point["time"])[:10] for _cap, curve in sleeve_curves for point in curve})
    initials = sum(start_capital for start_capital, _curve in sleeve_curves)
    if not days:
        return 0.0, 0.0
    peak = initials
    max_dd = 0.0
    for day in days:
        marked = sum(
            _sleeve_equity_on(day, start_capital, curve) for start_capital, curve in sleeve_curves
        )
        peak = max(peak, marked)
        max_dd = min(max_dd, marked - peak)
    dd_pct = (max_dd / initials * 100.0) if initials else 0.0
    return round(max_dd, 4), round(dd_pct, 4)


STRATEGIES: dict[str, tuple[StrategyFn, Mode, str]] = {
    "ma20_granville": (ma20_granville, "long_only", "Granville: close crosses rising/falling 20MA"),
    "gold_10_20": (gold_10_20, "long_only", "10MA / 20MA golden and death cross"),
    "gold_20_60": (gold_20_60, "long_only", "20MA / 60MA golden and death cross"),
    "volume_breakout": (volume_breakout, "long_only", "Close > 20d high and 1.5x volume; exit 10d low"),
    "donchian_20_10": (donchian_20_10, "long_only", "Dow/Turtle: 20d breakout, 10d exit"),
    "donchian_10_5_ai": (donchian_10_5, "always_in", "Aggressive always-in 10d/5d Donchian (long or short)"),
    "hammer_support": (hammer_support, "long_only", "Long lower wick at 20d support; exit below 20MA"),
    "wyckoff_spring": (wyckoff_spring, "long_only", "Spring: false break of 20d low then reclaim, with volume"),
    "combo_ma_vol": (combo_ma_vol, "long_only", "20>60 MA uptrend + volume-confirmed 20d breakout"),
}


def _without_equity(block: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in block.items() if key != "equity"}


def backtest_frame(frame: pd.DataFrame, capital: float) -> dict[str, Any]:
    if len(frame) <= WARMUP + 20:
        raise RuntimeError("not enough daily bars")
    test = frame.iloc[-TEST_BARS:].reset_index(drop=True) if len(frame) > TEST_BARS else frame
    times = test["time"].tolist()
    opens = test["open"].astype(float).tolist()
    closes = test["close"].astype(float).tolist()
    hold = simulate_buy_hold_capital(times, opens, closes, capital)
    results: dict[str, Any] = {"buy_hold": hold}
    aligned_start = test["time"].iloc[0]
    matches = frame.index[frame["time"] == aligned_start].tolist()
    start_idx = int(matches[0]) if matches else max(0, len(frame) - len(test))
    for name, (fn, mode, _blurb) in STRATEGIES.items():
        signals = fn(frame)
        sliced = signals[start_idx : start_idx + len(test)]
        if len(sliced) != len(test):
            sliced = signals[-len(test) :]
        results[name] = simulate_capital(times, opens, closes, sliced, mode, capital)
        results[name]["buy_hold_pnl"] = hold["pnl"]
        results[name]["buy_hold_return_pct"] = hold["return_pct"]
    results["bars"] = len(test)
    results["range"] = {"start": str(times[0]), "end": str(times[-1])}
    return results


def run(symbols: list[str], capital: float = CAPITAL) -> dict[str, Any]:
    frames: dict[str, pd.DataFrame] = {}
    errors: list[dict[str, str]] = []
    for symbol in symbols:
        try:
            frame = rows_to_frame(fetch_klines(symbol, period="day", count=400))
            if len(frame) <= WARMUP + 20:
                raise RuntimeError("not enough daily bars")
            frames[symbol] = frame
        except Exception as exc:  # noqa: BLE001
            errors.append({"ticker": symbol, "error": str(exc)})
    names = ["buy_hold", *STRATEGIES.keys()]
    n_sleeves = len(frames)
    sleeve = (capital / n_sleeves) if n_sleeves else 0.0
    totals = {
        name: {
            "pnl": 0.0,
            "ending_equity": 0.0,
            "trades": 0,
            "wins": 0,
        }
        for name in names
    }
    curves: dict[str, list[tuple[float, list[dict[str, Any]]]]] = {name: [] for name in names}
    per_symbol: dict[str, Any] = {}
    for symbol, frame in frames.items():
        row = backtest_frame(frame, sleeve)
        published: dict[str, Any] = {
            "bars": row["bars"],
            "range": row["range"],
            "sleeve_capital": round(sleeve, 4),
        }
        for name in names:
            block = row[name]
            curves[name].append((sleeve, list(block.get("equity") or [])))
            published[name] = _without_equity(block)
            totals[name]["pnl"] += float(block["pnl"])
            totals[name]["ending_equity"] += float(block["ending_equity"])
            totals[name]["trades"] += int(block.get("trades") or 0)
            totals[name]["wins"] += int(block.get("wins") or 0)
        per_symbol[symbol] = published
    for name, block in totals.items():
        trades = int(block["trades"])
        pnl = round(float(block["pnl"]), 4)
        ending = round(float(block["ending_equity"]), 4)
        max_dd, dd_pct = _portfolio_max_dd(curves[name])
        block["pnl"] = pnl
        block["ending_equity"] = ending
        block["capital"] = round(capital, 4)
        block["return_pct"] = round(pnl / capital * 100.0, 4) if capital else 0.0
        block["max_drawdown"] = max_dd
        block["max_drawdown_pct"] = dd_pct
        block["win_rate"] = round(block["wins"] / trades, 4) if trades else None
        block["sleeve_capital"] = round(sleeve, 4)
        block["sleeves"] = n_sleeves
    ranked = sorted(totals.items(), key=lambda item: float(item[1]["pnl"]), reverse=True)
    return {
        "horizon": "last 252 US daily bars (~1y)",
        "capital": capital,
        "allocation": (
            f"Equal sleeves of ${sleeve:.2f} across {n_sleeves} names with enough daily bars. "
            "Fractional shares. DRAM sleeve stays cash until its first bar."
        ),
        "notes": [
            f"${capital:.0f} starting cash, split equally across names that have enough daily bars.",
            "Fractional shares so VOO can be held in a $1000 book. Futu sim is still integer qty.",
            "Timing rules fill next open. Buy-and-hold buys the first open and marks the last close.",
            "No commission. Elliott Wave is omitted (not a unique mechanical count).",
            "donchian_10_5_ai is always-in (can short the sleeve). Other rules are long-only.",
        ],
        "totals": totals,
        "ranked": [name for name, _ in ranked],
        "winner": ranked[0][0] if ranked else "buy_hold",
        "symbols": per_symbol,
        "errors": errors,
        "strategy_notes": {name: blurb for name, (_fn, _mode, blurb) in STRATEGIES.items()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest strategy_theory.md rules vs buy-and-hold.")
    parser.add_argument("--capital", type=float, default=CAPITAL, help="Starting USD cash (default 1000)")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    watchlist = json.loads((root / "config" / "watchlist.json").read_text(encoding="utf-8"))
    payload = run(list(watchlist["symbols"]), capital=float(args.capital))
    out = root / "analysis" / "output" / "theory_backtest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"winner={payload['winner']}")
    for name in payload["ranked"]:
        block = payload["totals"][name]
        print(
            f"  {name:22} pnl={block['pnl']:>9} ret={block['return_pct']:>7}% "
            f"end={block['ending_equity']:>9} trades={block['trades']:>3} win={block['win_rate']}"
        )
    for err in payload["errors"]:
        print(f"  ERROR {err['ticker']}: {err['error']}")
    print(f"wrote {out}")
    return 0 if not payload["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
