"""Live Longbridge quotes. Pick 盤前 / 盤中 / 盤後 / 夜盤 last, not a stale daily close."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from analysis.proc import run_hidden
from analysis.session import QuoteSession, us_quote_session


def _as_float(raw: Any) -> float | None:
    if raw is None or raw == "" or raw == "-":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value


def _nested_last(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        block = row.get(key)
        if not isinstance(block, dict):
            continue
        value = _as_float(block.get("last") or block.get("last_done"))
        if value is not None:
            return value
    return None


def parse_live_price(row: dict[str, Any], now: datetime | None = None) -> dict[str, Any] | None:
    """Choose the tape that is actually trading right now.

    During 盤前, top-level ``last`` is still yesterday's regular close.
    """
    session: QuoteSession = us_quote_session(now)
    rth_last = _as_float(row.get("last") or row.get("last_done"))
    pre = _nested_last(row, "pre_market", "pre_market_quote")
    post = _nested_last(row, "post_market", "post_market_quote")
    overnight = _nested_last(row, "overnight", "overnight_quote")
    chosen: float | None = None
    source = "last"
    if session == "pre":
        chosen, source = (pre, "pre_market") if pre is not None else (rth_last, "last")
    elif session == "post":
        chosen, source = (post, "post_market") if post is not None else (rth_last, "last")
    elif session == "overnight":
        chosen, source = (overnight, "overnight") if overnight is not None else (rth_last, "last")
    elif session == "rth":
        chosen, source = rth_last, "last"
    else:
        chosen = pre or post or overnight or rth_last
        source = "last"
    if chosen is None:
        return None
    return {
        "price": chosen,
        "session": session,
        "source": source,
        "rth_last": rth_last,
        "symbol": row.get("symbol"),
    }


def fetch_quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    tickers = [str(symbol) for symbol in symbols if str(symbol).strip()]
    if not tickers:
        return {}
    completed = run_hidden(["longbridge", "quote", *tickers, "--format", "json"])
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "unknown error").strip()
        raise RuntimeError(f"longbridge quote failed: {err}")
    payload = json.loads(completed.stdout or "[]")
    if not isinstance(payload, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in payload:
        if isinstance(row, dict) and row.get("symbol"):
            out[str(row["symbol"]).upper()] = row
    return out


def live_price_for(symbol: str, now: datetime | None = None) -> dict[str, Any] | None:
    try:
        rows = fetch_quotes([symbol])
    except (RuntimeError, ValueError, OSError, json.JSONDecodeError):
        return None
    row = rows.get(str(symbol).upper())
    if not row:
        return None
    return parse_live_price(row, now)
