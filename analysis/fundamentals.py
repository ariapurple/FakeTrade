"""Fetch Longbridge calculated indexes (PE, PB, mktcap)."""

from __future__ import annotations

import json
from typing import Any

from analysis.proc import run_hidden


def fetch_calc_index(symbol: str) -> dict[str, Any] | None:
    completed = run_hidden(["longbridge", "calc-index", symbol, "--format", "json"])
    if completed.returncode != 0:
        return None
    payload = json.loads(completed.stdout)
    if isinstance(payload, list) and payload:
        row = payload[0]
        return row if isinstance(row, dict) else None
    if isinstance(payload, dict):
        return payload
    return None
