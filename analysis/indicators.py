"""QuantHarness-style TA-Lib indicators without calling an LLM."""

from __future__ import annotations

from typing import Any

import pandas as pd
import talib


def _last(values: Any) -> float | None:
    series = pd.Series(values, dtype="float64").dropna()
    if series.empty:
        return None
    return round(float(series.iloc[-1]), 4)


def compute_indicators(kline_data: dict[str, list[Any]]) -> dict[str, Any]:
    """Return the same RSI/MACD/Stoch/ROC/Williams %R set QuantHarness's Indicator Agent uses."""
    frame = pd.DataFrame(kline_data)
    close = frame["Close"].astype(float)
    high = frame["High"].astype(float)
    low = frame["Low"].astype(float)

    rsi = _last(talib.RSI(close, timeperiod=14))
    macd, macd_signal, macd_hist = talib.MACD(
        close, fastperiod=12, slowperiod=26, signalperiod=9
    )
    stoch_k, stoch_d = talib.STOCH(
        high, low, close, fastk_period=14, slowk_period=3, slowd_period=3
    )
    roc = _last(talib.ROC(close, timeperiod=10))
    willr = _last(talib.WILLR(high, low, close, timeperiod=14))
    last_macd = _last(macd)
    last_signal = _last(macd_signal)
    last_hist = _last(macd_hist)
    last_k = _last(stoch_k)
    last_d = _last(stoch_d)
    last_close = _last(close)

    notes: list[str] = []
    bias = "neutral"
    if rsi is not None and rsi >= 70:
        bias = "overbought"
        notes.append(f"RSI {rsi:.1f} is overbought (≥70).")
    elif rsi is not None and rsi <= 30:
        bias = "oversold"
        notes.append(f"RSI {rsi:.1f} is oversold (≤30).")
    elif rsi is not None:
        notes.append(f"RSI {rsi:.1f} is mid-range.")
    else:
        notes.append("RSI unavailable (not enough bars).")

    if last_hist is not None and last_hist > 0:
        notes.append(f"MACD histogram {last_hist:.2f} is positive (bullish momentum).")
    elif last_hist is not None:
        notes.append(f"MACD histogram {last_hist:.2f} is negative (bearish momentum).")

    return {
        "close": last_close,
        "rsi": rsi,
        "macd": last_macd,
        "macd_signal": last_signal,
        "macd_hist": last_hist,
        "stoch_k": last_k,
        "stoch_d": last_d,
        "roc": roc,
        "willr": willr,
        "bias": bias,
        "notes": notes,
        "bars": int(len(frame)),
        "source": "TA-Lib via QuantHarness indicator set",
    }


def educational_bias(indicators: dict[str, Any]) -> str:
    """Map indicator extremes to LONG/SHORT/WAIT for learning. Not an order."""
    rsi = indicators.get("rsi")
    hist = indicators.get("macd_hist")
    if isinstance(rsi, (int, float)) and rsi <= 30 and isinstance(hist, (int, float)) and hist > 0:
        return "LONG"
    if isinstance(rsi, (int, float)) and rsi >= 70 and isinstance(hist, (int, float)) and hist < 0:
        return "SHORT"
    return "WAIT"
