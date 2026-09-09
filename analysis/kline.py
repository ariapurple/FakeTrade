"""Fetch Longbridge OHLCV and convert it to QuantHarness kline dicts."""

from __future__ import annotations

import json
import subprocess
from typing import Any

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
    completed = subprocess.run(
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
        check=False,
        capture_output=True,
        text=True,
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
    return {
        "Datetime": [row["time"] for row in rows],
        "Open": [float(row["open"]) for row in rows],
        "High": [float(row["high"]) for row in rows],
        "Low": [float(row["low"]) for row in rows],
        "Close": [float(row["close"]) for row in rows],
        "Volume": [float(row.get("volume") or 0) for row in rows],
    }
