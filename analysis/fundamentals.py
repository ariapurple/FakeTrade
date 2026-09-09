"""Fetch Longbridge calculated indexes (PE, PB, mktcap)."""

from __future__ import annotations

import json
import subprocess
from typing import Any


def fetch_calc_index(symbol: str) -> dict[str, Any] | None:
    completed = subprocess.run(
        ["longbridge", "calc-index", symbol, "--format", "json"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    payload = json.loads(completed.stdout)
    if isinstance(payload, list) and payload:
        row = payload[0]
        return row if isinstance(row, dict) else None
    if isinstance(payload, dict):
        return payload
    return None
