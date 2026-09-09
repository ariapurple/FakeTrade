"""Signal agents: 3/4 vote (SMA, RSI, VSA, PE) or buy-and-hold."""

from __future__ import annotations

from typing import Any, Literal, assert_never

import pandas as pd
import talib

Signal = Literal["BUY", "SELL", "HOLD"]


def vote_weight(signal: Signal) -> int:
    if signal == "BUY":
        return 1
    if signal == "SELL":
        return -1
    if signal == "HOLD":
        return 0
    assert_never(signal)


def _last(values: Any) -> float | None:
    series = pd.Series(values, dtype="float64").dropna()
    if series.empty:
        return None
    return float(series.iloc[-1])


def _frame(kline_data: dict[str, list[Any]]) -> pd.DataFrame:
    return pd.DataFrame(kline_data)


def trend_following(kline_data: dict[str, list[Any]]) -> dict[str, Any]:
    """Close vs SMA20 / SMA50. Needs enough bars; otherwise HOLD."""
    frame = _frame(kline_data)
    close = frame["Close"].astype(float)
    sma20 = _last(talib.SMA(close, timeperiod=20))
    sma50 = _last(talib.SMA(close, timeperiod=50))
    last = _last(close)
    if last is None or sma20 is None or sma50 is None:
        return {
            "signal": "HOLD",
            "confidence": 0.3,
            "reason": "Not enough bars for SMA20/SMA50 trend.",
            "sma20": sma20,
            "sma50": sma50,
            "close": last,
        }
    if last > sma20 > sma50:
        return {
            "signal": "BUY",
            "confidence": 0.7,
            "reason": f"Close {last:.2f} is above SMA20 {sma20:.2f} and SMA50 {sma50:.2f} (uptrend).",
            "sma20": round(sma20, 2),
            "sma50": round(sma50, 2),
            "close": round(last, 2),
        }
    if last < sma20 < sma50:
        return {
            "signal": "SELL",
            "confidence": 0.7,
            "reason": f"Close {last:.2f} is below SMA20 {sma20:.2f} and SMA50 {sma50:.2f} (downtrend).",
            "sma20": round(sma20, 2),
            "sma50": round(sma50, 2),
            "close": round(last, 2),
        }
    return {
        "signal": "HOLD",
        "confidence": 0.45,
        "reason": f"Close {last:.2f} vs SMA20 {sma20:.2f} / SMA50 {sma50:.2f} is mixed.",
        "sma20": round(sma20, 2),
        "sma50": round(sma50, 2),
        "close": round(last, 2),
    }


def mean_reversion(kline_data: dict[str, list[Any]]) -> dict[str, Any]:
    """RSI extremes only. Mid-range is HOLD — this is the opposite of trend-following."""
    frame = _frame(kline_data)
    rsi = _last(talib.RSI(frame["Close"].astype(float), timeperiod=14))
    if rsi is None:
        return {"signal": "HOLD", "confidence": 0.3, "reason": "RSI unavailable.", "rsi": None}
    if rsi <= 30:
        return {
            "signal": "BUY",
            "confidence": 0.65,
            "reason": f"RSI {rsi:.1f} is oversold (≤30); mean-reversion long.",
            "rsi": round(rsi, 2),
        }
    if rsi >= 70:
        return {
            "signal": "SELL",
            "confidence": 0.65,
            "reason": f"RSI {rsi:.1f} is overbought (≥70); mean-reversion short/exit.",
            "rsi": round(rsi, 2),
        }
    return {
        "signal": "HOLD",
        "confidence": 0.5,
        "reason": f"RSI {rsi:.1f} is mid-range; no mean-reversion edge.",
        "rsi": round(rsi, 2),
    }


def volume_spread(kline_data: dict[str, list[Any]]) -> dict[str, Any]:
    """Lightweight VSA: last bar volume vs 20-bar average, with candle direction."""
    frame = _frame(kline_data)
    if len(frame) < 21:
        return {"signal": "HOLD", "confidence": 0.3, "reason": "Not enough bars for volume average."}
    volume = frame["Volume"].astype(float)
    close = frame["Close"].astype(float)
    open_ = frame["Open"].astype(float)
    avg_vol = float(volume.iloc[-21:-1].mean())
    last_vol = float(volume.iloc[-1])
    last_close = float(close.iloc[-1])
    last_open = float(open_.iloc[-1])
    ratio = last_vol / avg_vol if avg_vol else 0.0
    up = last_close > last_open
    if ratio >= 1.5 and up:
        return {
            "signal": "BUY",
            "confidence": 0.6,
            "reason": f"Up bar on {ratio:.1f}x average volume (effort with result).",
            "volume_ratio": round(ratio, 2),
        }
    if ratio >= 1.5 and not up:
        return {
            "signal": "SELL",
            "confidence": 0.6,
            "reason": f"Down bar on {ratio:.1f}x average volume (supply showing).",
            "volume_ratio": round(ratio, 2),
        }
    return {
        "signal": "HOLD",
        "confidence": 0.4,
        "reason": f"Last bar volume is {ratio:.1f}x average; no VSA extreme.",
        "volume_ratio": round(ratio, 2),
    }


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in {"", "-", "N/A", "na", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def value_investing(calc: dict[str, Any] | None) -> dict[str, Any]:
    """Very coarse PE screen from Longbridge calc-index. Not a DCF."""
    pe = _optional_float((calc or {}).get("pe"))
    if pe is None:
        return {"signal": "HOLD", "confidence": 0.3, "reason": "No PE from Longbridge calc-index.", "pe": None}
    if pe <= 0:
        return {"signal": "HOLD", "confidence": 0.3, "reason": f"PE {pe} is not meaningful.", "pe": pe}
    if pe < 18:
        return {
            "signal": "BUY",
            "confidence": 0.55,
            "reason": f"PE {pe:.1f} is below 18 (cheap vs a simple screen, not 5y history).",
            "pe": pe,
        }
    if pe > 40:
        return {
            "signal": "SELL",
            "confidence": 0.5,
            "reason": f"PE {pe:.1f} is above 40 (expensive vs a simple screen).",
            "pe": pe,
        }
    return {
        "signal": "HOLD",
        "confidence": 0.45,
        "reason": f"PE {pe:.1f} is in a normal band (18–40).",
        "pe": pe,
    }


def buy_and_hold() -> dict[str, Any]:
    """Stay long. Optional SMA/drawdown/news exits live in buy_hold_exits when enabled."""
    return {
        "signal": "BUY",
        "confidence": 0.7,
        "reason": "Buy-and-hold: stay long; no SMA, drawdown, or news exit.",
    }


def multi_year_cheap(
    kline_data: dict[str, list[Any]],
    last_price: float | None = None,
    *,
    lookback: int = 1000,
    min_bars: int = 252,
    percentile: float = 0.20,
) -> dict[str, Any]:
    """True when live/last close is in the cheapest band of the lookback window.

    Needs ``min_bars`` (default 1 year). Names with a short listing stay not-cheap.
    All-equal history is not cheap.
    """
    frame = _frame(kline_data)
    close = frame["Close"].astype(float).dropna()
    last = float(last_price) if last_price is not None else _last(close)
    window = close.iloc[-int(lookback) :] if lookback else close
    bars = int(len(window))
    if last is None or bars < int(min_bars):
        return {
            "cheap": False,
            "reason": f"Need {int(min_bars)} daily bars for multi-year cheap; have {bars}.",
            "percentile_rank": None,
            "threshold": None,
            "close": None if last is None else round(last, 2),
            "bars": bars,
        }
    threshold = float(window.quantile(float(percentile)))
    rank = float((window <= last).mean())
    cheap = bool(last <= threshold and rank <= float(percentile) + 1e-9)
    band = int(round(float(percentile) * 100))
    return {
        "cheap": cheap,
        "reason": (
            f"Price {last:.2f} is at the {rank * 100:.0f}th percentile of {bars}d closes "
            f"(3-share size if at or below the {band}th / {threshold:.2f})."
        ),
        "percentile_rank": round(rank, 4),
        "threshold": round(threshold, 2),
        "close": round(last, 2),
        "bars": bars,
    }


def buy_hold_exits(
    kline_data: dict[str, list[Any]],
    *,
    below_sma: int = 60,
    drawdown_from_high: float = 0.25,
    high_lookback: int = 60,
    news_report: dict[str, Any] | None = None,
    last_price: float | None = None,
    max_extension_pct: float = 0.0,
) -> dict[str, Any]:
    """SMA/drawdown/news exits, plus optional add-only-near-SMA (dip-in-expansion)."""
    frame = _frame(kline_data)
    close = frame["Close"].astype(float)
    last = float(last_price) if last_price is not None else _last(close)
    reasons: list[str] = []
    if last is None:
        return {
            "signal": "HOLD",
            "confidence": 0.3,
            "reason": "No close for buy-and-hold exit check.",
            "close": None,
            "extension_pct": None,
        }
    news_signal = (news_report or {}).get("signal")
    sma_len = int(below_sma) if below_sma else 0
    ext_len = sma_len or (200 if float(max_extension_pct) > 0 else 0)
    if not sma_len and drawdown_from_high <= 0 and news_signal != "SELL" and float(max_extension_pct) <= 0:
        return {
            **buy_and_hold(),
            "close": round(last, 2),
            "sma": None,
            "high": None,
            "extension_pct": None,
        }
    sma = _last(talib.SMA(close, timeperiod=int(ext_len))) if ext_len else None
    extension_pct = None if sma is None or float(sma) <= 0 else (last - float(sma)) / float(sma)
    sma_label = sma_len or ext_len
    if sma_len and sma is not None and last < sma:
        reasons.append(f"price {last:.2f} is below SMA{sma_len} {sma:.2f}")
    window = close.iloc[-int(high_lookback) :] if high_lookback else close
    peak = float(window.max()) if not window.empty else None
    if last_price is not None and peak is not None:
        peak = max(peak, float(last_price))
    if peak and drawdown_from_high > 0 and last <= peak * (1.0 - float(drawdown_from_high)):
        pct = (peak - last) / peak * 100.0
        reasons.append(f"price {last:.2f} is {pct:.1f}% below {high_lookback}d high {peak:.2f}")
    if news_signal == "SELL":
        reasons.append(str((news_report or {}).get("reason") or "hard-negative news"))
    if reasons:
        return {
            "signal": "SELL",
            "confidence": 0.75,
            "reason": "Buy-and-hold exit: " + "; ".join(reasons),
            "close": round(last, 2),
            "sma": None if sma is None else round(float(sma), 2),
            "high": None if peak is None else round(peak, 2),
            "extension_pct": None if extension_pct is None else round(float(extension_pct), 4),
        }
    if float(max_extension_pct) > 0:
        band = float(max_extension_pct)
        if sma is None or extension_pct is None:
            return {
                "signal": "HOLD",
                "confidence": 0.4,
                "reason": (
                    f"Dip-in-expansion: not enough bars for SMA{sma_label}; "
                    "will not add until the trend line exists."
                ),
                "close": round(last, 2),
                "sma": None,
                "high": None if peak is None else round(peak, 2),
                "extension_pct": None,
            }
        if extension_pct > band:
            return {
                "signal": "HOLD",
                "confidence": 0.65,
                "reason": (
                    f"Dip-in-expansion: price {last:.2f} is {extension_pct * 100:.1f}% above "
                    f"SMA{sma_label} {sma:.2f}; stop adding (band {band * 100:.0f}%)."
                ),
                "close": round(last, 2),
                "sma": round(float(sma), 2),
                "high": None if peak is None else round(peak, 2),
                "extension_pct": round(float(extension_pct), 4),
            }
    return {
        "signal": "BUY",
        "confidence": 0.7,
        "reason": (
            f"Buy-and-hold: price {last:.2f} still inside the exit rules"
            + (f" (SMA{sma_label} {sma:.2f})" if sma is not None else "")
            + (
                f", {extension_pct * 100:.1f}% above SMA (add band {float(max_extension_pct) * 100:.0f}%)"
                if extension_pct is not None and float(max_extension_pct) > 0
                else ""
            )
            + (
                f", {int(drawdown_from_high * 100)}% off {high_lookback}d high"
                if drawdown_from_high > 0 and high_lookback
                else ""
            )
            + "."
        ),
        "close": round(last, 2),
        "sma": None if sma is None else round(float(sma), 2),
        "high": None if peak is None else round(peak, 2),
        "extension_pct": None if extension_pct is None else round(float(extension_pct), 4),
    }


def ma_swing(kline_data: dict[str, list[Any]], *, fast: int = 10, slow: int = 20) -> dict[str, Any]:
    """Short-term regime: long while fast SMA > slow SMA; sell when it drops back under."""
    frame = _frame(kline_data)
    close = frame["Close"].astype(float)
    last = _last(close)
    fast_ma = _last(talib.SMA(close, timeperiod=int(fast)))
    slow_ma = _last(talib.SMA(close, timeperiod=int(slow)))
    if last is None or fast_ma is None or slow_ma is None:
        return {
            "signal": "HOLD",
            "confidence": 0.3,
            "reason": f"Not enough bars for SMA{fast}/SMA{slow} swing.",
            "close": last,
            "sma_fast": fast_ma,
            "sma_slow": slow_ma,
        }
    if fast_ma > slow_ma:
        return {
            "signal": "BUY",
            "confidence": 0.65,
            "reason": f"SMA{fast} {fast_ma:.2f} is above SMA{slow} {slow_ma:.2f} (swing long).",
            "close": round(last, 2),
            "sma_fast": round(fast_ma, 2),
            "sma_slow": round(slow_ma, 2),
        }
    if fast_ma < slow_ma:
        return {
            "signal": "SELL",
            "confidence": 0.65,
            "reason": f"SMA{fast} {fast_ma:.2f} is below SMA{slow} {slow_ma:.2f} (swing exit).",
            "close": round(last, 2),
            "sma_fast": round(fast_ma, 2),
            "sma_slow": round(slow_ma, 2),
        }
    return {
        "signal": "HOLD",
        "confidence": 0.45,
        "reason": f"SMA{fast} and SMA{slow} are tied.",
        "close": round(last, 2),
        "sma_fast": round(fast_ma, 2),
        "sma_slow": round(slow_ma, 2),
    }
