"""Hard-negative Longbridge news gate. Never emits BUY; fail-open on fetch errors."""

from __future__ import annotations

import json
from typing import Any, Literal

from analysis.proc import run_hidden

NewsSignal = Literal["SELL", "HOLD"]

HARD_NEGATIVE = (
    "bankrupt",
    "chapter 11",
    "going concern",
    "delist",
    "accounting fraud",
    "securities fraud",
    "restatement",
    "trading halt",
    "stock halt",
    "auditor resign",
    "profit warning",
    "slashes guidance",
    "cuts guidance",
    "full-year cut",
    "债务违约",
    "破产",
    "退市",
    "造假",
    "盈警",
    "停牌",
)


def score_headlines(titles: list[str]) -> dict[str, Any]:
    hits: list[str] = []
    for title in titles:
        text = str(title or "")
        lowered = text.lower()
        for needle in HARD_NEGATIVE:
            if needle.lower() in lowered:
                hits.append(text)
                break
    if hits:
        return {
            "signal": "SELL",
            "confidence": 0.8,
            "reason": f"Hard-negative Longbridge headline: {hits[0][:160]}",
            "hits": hits[:4],
        }
    return {
        "signal": "HOLD",
        "confidence": 0.4,
        "reason": "No hard-negative headlines in recent Longbridge news.",
        "hits": [],
    }


def fetch_news_titles(symbol: str, count: int = 8) -> list[str]:
    completed = run_hidden(
        ["longbridge", "news", symbol, "--count", str(count), "--format", "json", "--lang", "en"]
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "news failed").strip())
    payload = json.loads(completed.stdout or "[]")
    if not isinstance(payload, list):
        return []
    titles: list[str] = []
    for row in payload:
        if isinstance(row, dict) and row.get("title"):
            titles.append(str(row["title"]))
    return titles


def news_gate(symbol: str, *, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {
            "signal": "HOLD",
            "confidence": 0.0,
            "reason": "News gate off for this book.",
            "hits": [],
        }
    try:
        titles = fetch_news_titles(symbol)
    except Exception as exc:  # noqa: BLE001 — missing news must not force a sell
        return {
            "signal": "HOLD",
            "confidence": 0.2,
            "reason": f"News fetch failed; not selling on headlines ({exc}).",
            "hits": [],
        }
    report = score_headlines(titles)
    report["count"] = len(titles)
    return report
