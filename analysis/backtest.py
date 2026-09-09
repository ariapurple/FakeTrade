"""Compare daily 3/4 voting vs daily-trend + 5m trigger on Longbridge history."""

from __future__ import annotations

import argparse
import json
import time as pytime
from calendar import monthrange
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import pandas as pd
import talib

from analysis.agents import (
    Signal,
    mean_reversion,
    trend_following,
    value_investing,
    volume_spread,
)
from analysis.fundamentals import fetch_calc_index
from analysis.kline import fetch_klines
from analysis.manager import _final_decision
from analysis.proc import run_hidden

ET = ZoneInfo("America/New_York")
DAILY_WINDOW = 60
FAST_WINDOW = 80
StrategyName = Literal["daily_vote", "dual_tf"]
OHLC_SCRIPT = 'indicator("ohlc"); plot(close, "C");'
MAX_STORED_FILLS = 8


def _month_windows(start: date, end: date) -> list[tuple[date, date]]:
    windows: list[tuple[date, date]] = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        last_day = monthrange(cursor.year, cursor.month)[1]
        chunk_start = max(cursor, start)
        chunk_end = min(date(cursor.year, cursor.month, last_day), end)
        windows.append((chunk_start, chunk_end))
        cursor = date(cursor.year + (1 if cursor.month == 12 else 0), 1 if cursor.month == 12 else cursor.month + 1, 1)
    return windows


def parse_quant_ohlcv(payload: dict[str, Any]) -> list[dict[str, Any]]:
    events = payload.get("events_json")
    if isinstance(events, str):
        events = json.loads(events)
    rows: list[dict[str, Any]] = []
    if not isinstance(events, list):
        return rows
    for event in events:
        if not isinstance(event, dict) or "barStart" not in event:
            continue
        candle = event["barStart"].get("candlestick") or {}
        millis = candle.get("time")
        if millis is None:
            continue
        rows.append(
            {
                "time": datetime.fromtimestamp(int(millis) / 1000, tz=timezone.utc).isoformat(),
                "open": candle.get("open"),
                "high": candle.get("high"),
                "low": candle.get("low"),
                "close": candle.get("close"),
                "volume": candle.get("volume") or 0,
            }
        )
    return rows


def fetch_quant_ohlcv(symbol: str, period: str, start: date, end: date) -> list[dict[str, Any]]:
    last_error = "unknown error"
    for attempt in range(6):
        completed = run_hidden(
            [
                "longbridge",
                "quant",
                "run",
                symbol,
                "--period",
                period,
                "--start",
                start.isoformat(),
                "--end",
                end.isoformat(),
                "--script",
                OHLC_SCRIPT,
                "--format",
                "json",
            ]
        )
        if completed.returncode == 0:
            payload = json.loads(completed.stdout)
            return parse_quant_ohlcv(payload)
        last_error = (completed.stderr or completed.stdout or "unknown error").strip()
        if "429" not in last_error and "rate limit" not in last_error.lower():
            break
        pytime.sleep(1.2 + attempt)
    raise RuntimeError(f"quant run {symbol} {period} {start}..{end} failed: {last_error}")


def fetch_5m_range(symbol: str, start: date, end: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk_start, chunk_end in _month_windows(start, end):
        for row in fetch_quant_ohlcv(symbol, "5m", chunk_start, chunk_end):
            key = str(row["time"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
        pytime.sleep(1.1)
    if not rows:
        raise RuntimeError(f"no 5m bars for {symbol} {start}..{end}")
    return rows


def last_completed_daily_indices(daily: pd.DataFrame, times: pd.Series) -> list[int]:
    available = pd.DatetimeIndex([session_close_utc(_et_date(stamp)) for stamp in daily["time"]])
    positions = available.searchsorted(pd.DatetimeIndex(times), side="right") - 1
    return [int(pos) for pos in positions]


def dual_tf_signals(daily: pd.DataFrame, fast: pd.DataFrame) -> list[Signal]:
    dclose = daily["close"].to_numpy(dtype="float64")
    sma20 = talib.SMA(dclose, 20)
    sma50 = talib.SMA(dclose, 50)
    trend: list[Signal] = []
    for idx, close in enumerate(dclose):
        s20 = sma20[idx]
        s50 = sma50[idx]
        if s20 != s20 or s50 != s50:
            trend.append("HOLD")
        elif close > s20 > s50:
            trend.append("BUY")
        elif close < s20 < s50:
            trend.append("SELL")
        else:
            trend.append("HOLD")
    fclose = fast["close"].to_numpy(dtype="float64")
    fopen = fast["open"].to_numpy(dtype="float64")
    fvol = fast["volume"].fillna(0).to_numpy(dtype="float64")
    rsi = talib.RSI(fclose, 14)
    daily_pos = last_completed_daily_indices(daily, fast["time"])
    out: list[Signal] = []
    for idx, di in enumerate(daily_pos):
        if di < DAILY_WINDOW - 1 or idx < FAST_WINDOW - 1:
            out.append("HOLD")
            continue
        value = rsi[idx]
        if value != value:
            reversion: Signal = "HOLD"
        elif value <= 30:
            reversion = "BUY"
        elif value >= 70:
            reversion = "SELL"
        else:
            reversion = "HOLD"
        vsa: Signal = "HOLD"
        if idx >= 20:
            avg = float(fvol[idx - 20 : idx].mean())
            ratio = float(fvol[idx]) / avg if avg else 0.0
            up = bool(fclose[idx] > fopen[idx])
            if ratio >= 1.5 and up:
                vsa = "BUY"
            elif ratio >= 1.5 and not up:
                vsa = "SELL"
        mapped = trend[di]
        if mapped == "BUY" and (reversion == "BUY" or vsa == "BUY"):
            out.append("BUY")
        elif mapped == "SELL" and (reversion == "SELL" or vsa == "SELL"):
            out.append("SELL")
        else:
            out.append("HOLD")
    return out


def _trim_fills(result: dict[str, Any]) -> dict[str, Any]:
    fills = list(result.get("fills") or [])
    if len(fills) <= MAX_STORED_FILLS:
        return result
    trimmed = dict(result)
    trimmed["fills"] = fills[:4] + fills[-4:]
    trimmed["fills_truncated"] = True
    return trimmed


def rows_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["time", "open", "close"]).sort_values("time")
    return frame.reset_index(drop=True)


def to_qh(frame: pd.DataFrame) -> dict[str, list[Any]]:
    return {
        "Datetime": [str(value) for value in frame["time"].tolist()],
        "Open": frame["open"].astype(float).tolist(),
        "High": frame["high"].astype(float).tolist(),
        "Low": frame["low"].astype(float).tolist(),
        "Close": frame["close"].astype(float).tolist(),
        "Volume": frame["volume"].fillna(0).astype(float).tolist(),
    }


def _et_date(stamp: pd.Timestamp) -> date:
    return stamp.tz_convert(ET).date()


def session_close_utc(session_day: date) -> pd.Timestamp:
    close_et = datetime.combine(session_day, time(16, 0), tzinfo=ET)
    return pd.Timestamp(close_et).tz_convert("UTC")


def last_completed_daily_idx(daily: pd.DataFrame, at: pd.Timestamp) -> int | None:
    for idx in range(len(daily) - 1, -1, -1):
        bar_day = _et_date(daily.at[idx, "time"])
        if session_close_utc(bar_day) <= at:
            return int(idx)
    return None


def daily_vote_decision(
    daily: pd.DataFrame,
    idx: int,
    value_report: dict[str, Any],
    buy_votes_needed: int,
    sell_votes_needed: int,
) -> Signal:
    start = max(0, idx + 1 - DAILY_WINDOW)
    qh = to_qh(daily.iloc[start : idx + 1])
    reports = {
        "trend": trend_following(qh),
        "reversion": mean_reversion(qh),
        "vsa": volume_spread(qh),
        "value": value_report,
    }
    return _final_decision(reports, buy_votes_needed, sell_votes_needed)


def dual_tf_decision(daily: pd.DataFrame, daily_idx: int, fast: pd.DataFrame, fast_idx: int) -> Signal:
    daily_start = max(0, daily_idx + 1 - DAILY_WINDOW)
    fast_start = max(0, fast_idx + 1 - FAST_WINDOW)
    trend = trend_following(to_qh(daily.iloc[daily_start : daily_idx + 1]))["signal"]
    reversion = mean_reversion(to_qh(fast.iloc[fast_start : fast_idx + 1]))["signal"]
    vsa = volume_spread(to_qh(fast.iloc[fast_start : fast_idx + 1]))["signal"]
    if trend == "BUY" and (reversion == "BUY" or vsa == "BUY"):
        return "BUY"
    if trend == "SELL" and (reversion == "SELL" or vsa == "SELL"):
        return "SELL"
    return "HOLD"


def simulate_long_only(
    times: list[pd.Timestamp],
    opens: list[float],
    closes: list[float],
    decisions: list[Signal],
) -> dict[str, Any]:
    cash = 0.0
    shares = 0
    entry: float | None = None
    trades: list[dict[str, Any]] = []
    equity: list[float] = []
    peak = 0.0
    max_dd = 0.0
    for idx in range(len(decisions) - 1):
        decision = decisions[idx]
        fill = float(opens[idx + 1])
        fill_time = times[idx + 1]
        if decision == "BUY" and shares == 0 and fill > 0:
            shares = 1
            cash -= fill
            entry = fill
            trades.append({"side": "BUY", "time": str(fill_time), "price": fill})
        elif decision == "SELL" and shares == 1 and fill > 0:
            shares = 0
            cash += fill
            pnl = fill - float(entry or fill)
            trades.append({"side": "SELL", "time": str(fill_time), "price": fill, "pnl": round(pnl, 4)})
            entry = None
        mark = cash + shares * float(closes[idx])
        equity.append(mark)
        peak = max(peak, mark)
        if peak:
            max_dd = min(max_dd, mark - peak)
    if shares == 1:
        last = float(closes[-1])
        cash += last
        trades.append(
            {
                "side": "SELL",
                "time": str(times[-1]),
                "price": last,
                "pnl": round(last - float(entry or last), 4),
                "note": "mark-to-last-close",
            }
        )
        shares = 0
    closed = [row for row in trades if "pnl" in row]
    wins = [row for row in closed if float(row["pnl"]) > 0]
    start_price = float(opens[1]) if len(opens) > 1 else float(closes[0])
    end_price = float(closes[-1])
    return {
        "pnl": round(cash, 4),
        "trades": len(closed),
        "wins": len(wins),
        "win_rate": round(len(wins) / len(closed), 4) if closed else None,
        "max_drawdown": round(max_dd, 4),
        "buy_hold_pnl": round(end_price - start_price, 4),
        "fills": trades,
    }


def backtest_symbol(
    daily: pd.DataFrame,
    fast: pd.DataFrame,
    value_report: dict[str, Any],
    buy_votes_needed: int,
    sell_votes_needed: int,
) -> dict[str, Any]:
    compare_start = fast["time"].iloc[0]
    daily_decisions: list[Signal] = []
    daily_times: list[pd.Timestamp] = []
    daily_opens: list[float] = []
    daily_closes: list[float] = []
    for idx in range(DAILY_WINDOW - 1, len(daily)):
        stamp = daily.at[idx, "time"]
        if stamp < compare_start:
            continue
        daily_times.append(stamp)
        daily_opens.append(float(daily.at[idx, "open"]))
        daily_closes.append(float(daily.at[idx, "close"]))
        daily_decisions.append(
            daily_vote_decision(daily, idx, value_report, buy_votes_needed, sell_votes_needed)
        )

    fast_decisions = dual_tf_signals(daily, fast)
    fast_times = [stamp for stamp in fast["time"].tolist()]
    fast_opens = fast["open"].astype(float).tolist()
    fast_closes = fast["close"].astype(float).tolist()
    buy_hold = round(float(fast_closes[-1]) - float(fast_opens[0]), 4) if fast_opens else 0.0
    dual = (
        simulate_long_only(fast_times, fast_opens, fast_closes, fast_decisions)
        if len(fast_decisions) > 1
        else {"pnl": 0.0, "trades": 0, "wins": 0, "win_rate": None, "max_drawdown": 0.0, "buy_hold_pnl": 0.0, "fills": []}
    )
    dual["buy_hold_pnl"] = buy_hold
    daily_result = (
        simulate_long_only(daily_times, daily_opens, daily_closes, daily_decisions)
        if len(daily_decisions) > 1
        else {"pnl": 0.0, "trades": 0, "wins": 0, "win_rate": None, "max_drawdown": 0.0, "buy_hold_pnl": 0.0, "fills": []}
    )

    return {
        "daily_vote": _trim_fills(daily_result),
        "dual_tf": _trim_fills(dual),
        "bars": {"daily": len(daily_decisions), "m5": len(fast_decisions)},
        "range": {
            "fast_start": str(fast["time"].iloc[0]),
            "fast_end": str(fast["time"].iloc[-1]),
        },
    }


def load_symbol(
    symbol: str,
    *,
    fast_start: date | None = None,
    fast_end: date | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    daily = rows_to_frame(fetch_klines(symbol, period="day", count=400))
    if fast_start and fast_end:
        fast = rows_to_frame(fetch_5m_range(symbol, fast_start, fast_end))
    else:
        fast = rows_to_frame(fetch_klines(symbol, period="5m", count=1000))
    value_report = value_investing(fetch_calc_index(symbol))
    return daily, fast, value_report


def run_watchlist_backtest(
    symbols: list[str],
    buy_votes_needed: int = 3,
    sell_votes_needed: int = 3,
    *,
    fast_start: date | None = None,
    fast_end: date | None = None,
) -> dict[str, Any]:
    per_symbol: dict[str, Any] = {}
    errors: list[dict[str, str]] = []
    for symbol in symbols:
        try:
            daily, fast, value_report = load_symbol(symbol, fast_start=fast_start, fast_end=fast_end)
            per_symbol[symbol] = backtest_symbol(
                daily, fast, value_report, buy_votes_needed, sell_votes_needed
            )
            per_symbol[symbol]["value_signal"] = value_report.get("signal")
            per_symbol[symbol]["pe"] = value_report.get("pe")
        except Exception as exc:  # noqa: BLE001
            errors.append({"ticker": symbol, "error": str(exc)})
    totals = {
        "daily_vote": {"pnl": 0.0, "trades": 0, "wins": 0},
        "dual_tf": {"pnl": 0.0, "trades": 0, "wins": 0},
        "buy_hold": 0.0,
    }
    for row in per_symbol.values():
        for name in ("daily_vote", "dual_tf"):
            totals[name]["pnl"] += float(row[name]["pnl"])
            totals[name]["trades"] += int(row[name]["trades"])
            totals[name]["wins"] += int(row[name]["wins"])
        totals["buy_hold"] += float(row["dual_tf"]["buy_hold_pnl"])
    for name in ("daily_vote", "dual_tf"):
        trades = int(totals[name]["trades"])
        totals[name]["pnl"] = round(float(totals[name]["pnl"]), 4)
        totals[name]["win_rate"] = round(totals[name]["wins"] / trades, 4) if trades else None
    totals["buy_hold"] = round(float(totals["buy_hold"]), 4)
    winner = "buy_hold"
    if totals["dual_tf"]["pnl"] > totals["buy_hold"]:
        winner = "dual_tf"
    elif totals["dual_tf"]["pnl"] == totals["buy_hold"]:
        winner = "tie"
    horizon = "count-1000-5m"
    if fast_start and fast_end:
        horizon = f"{fast_start.isoformat()}..{fast_end.isoformat()}"
    return {
        "generated_at": datetime.now(ET).isoformat(),
        "horizon": horizon,
        "notes": [
            "Long-only 1 share, fill next bar open, no commission.",
            "Dual TF: previous completed daily SMA trend must agree; 5m RSI or VSA triggers.",
            "Buy-hold is 1 share from first 5m open to last 5m close in the same window.",
            "5m bars from Longbridge quant run monthly chunks (RTH). kline history quota is 0 on this account.",
        ],
        "totals": totals,
        "winner": winner,
        "symbols": per_symbol,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest daily+5m trigger vs buy-and-hold.")
    parser.add_argument("--start", default="", help="YYYY-MM-DD start for 5m window")
    parser.add_argument("--end", default="", help="YYYY-MM-DD end for 5m window")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    watchlist = json.loads((root / "config" / "watchlist.json").read_text(encoding="utf-8"))
    fast_start = date.fromisoformat(args.start) if args.start else None
    fast_end = date.fromisoformat(args.end) if args.end else None
    payload = run_watchlist_backtest(
        list(watchlist["symbols"]),
        fast_start=fast_start,
        fast_end=fast_end,
    )
    out = root / "analysis" / "output" / "backtest_compare.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"winner={payload['winner']}  horizon={payload.get('horizon')}")
    print(
        "dual_tf "
        f"pnl={payload['totals']['dual_tf']['pnl']} "
        f"trades={payload['totals']['dual_tf']['trades']} "
        f"win={payload['totals']['dual_tf']['win_rate']}"
    )
    print(f"buy_hold pnl={payload['totals']['buy_hold']}")
    for symbol, row in payload["symbols"].items():
        print(
            f"  {symbol:10} dual={row['dual_tf']['pnl']:>8} "
            f"hold={row['dual_tf']['buy_hold_pnl']:>8} "
            f"trades={row['dual_tf']['trades']} bars={row['bars']['m5']}"
        )
    for err in payload["errors"]:
        print(f"  ERROR {err['ticker']}: {err['error']}")
    print(f"wrote {out}")
    return 0 if not payload["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
