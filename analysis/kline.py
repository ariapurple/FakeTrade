"""Fetch Longbridge OHLCV and convert it to QuantHarness kline dicts."""

from __future__ import annotations

import json
from typing import Any

from analysis.proc import run_hidden

LONG_BRIDGE_PERIODS: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "1h",
    "1d": "day",
    "day": "day",
    "1w": "week",
    "week": "week",
}


def fetch_klines(symbol: str, period: str = "day", count: int = 60) -> list[dict[str, Any]]:
    """Return recent candles from the Longbridge CLI as a list of row dicts."""
    mapped = LONG_BRIDGE_PERIODS.get(period)
    if mapped is None:
        raise ValueError(
            f"Unsupported period {period!r}. Use one of: {', '.join(sorted(LONG_BRIDGE_PERIODS))}"
        )
    completed = run_hidden(
        [
            "longbridge",
            "kline",
            symbol,
            "--period",
            mapped,
            "--count",
            str(count),
            "--format",
            "json",
        ],
    )
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "unknown error").strip()
        raise RuntimeError(f"longbridge kline failed: {err}")
    payload = json.loads(completed.stdout)
    if not isinstance(payload, list) or not payload:
        raise RuntimeError(f"No kline rows returned for {symbol}")
    return payload


def to_quantharness(rows: list[dict[str, Any]]) -> dict[str, list[Any]]:
    """Map Longbridge rows to the Datetime/Open/High/Low/Close/Volume dict QuantHarness expects."""
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        try:
            cleaned.append(
                {
                    "Datetime": row["time"],
                    "Open": float(row["open"]),
                    "High": float(row["high"]),
                    "Low": float(row["low"]),
                    "Close": float(row["close"]),
                    "Volume": float(row.get("volume") or 0),
                }
            )
        except (TypeError, ValueError, KeyError):
            continue
    if not cleaned:
        raise RuntimeError("No numeric OHLCV rows after cleaning")
    return {
        "Datetime": [row["Datetime"] for row in cleaned],
        "Open": [row["Open"] for row in cleaned],
        "High": [row["High"] for row in cleaned],
        "Low": [row["Low"] for row in cleaned],
        "Close": [row["Close"] for row in cleaned],
        "Volume": [row["Volume"] for row in cleaned],
    }
