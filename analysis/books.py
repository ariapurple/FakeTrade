"""Load one or more strategy books from config/books.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOOKS = ROOT / "config" / "books.json"
DEFAULT_WATCHLIST = ROOT / "config" / "watchlist.json"


def load_books(root: Path | None = None) -> list[dict[str, Any]]:
    base = root or ROOT
    index_path = base / "config" / "books.json"
    if not index_path.exists():
        watchlist = base / "config" / "watchlist.json"
        config = json.loads(watchlist.read_text(encoding="utf-8"))
        return [{"id": "default", "path": str(watchlist), "config": config}]
    index = json.loads(index_path.read_text(encoding="utf-8"))
    books: list[dict[str, Any]] = []
    for entry in index.get("books") or []:
        rel = str(entry["file"]).replace("\\", "/")
        path = base / rel
        config = json.loads(path.read_text(encoding="utf-8"))
        books.append({"id": str(entry["id"]), "path": str(path), "config": config})
    if not books:
        raise RuntimeError(f"No books listed in {index_path}")
    return books


def book_signal_path(book_id: str, root: Path | None = None) -> Path:
    """Repo-root JSON for one book, e.g. trading_signal_hold.json."""
    base = root or ROOT
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(book_id))
    return base / f"trading_signal_{safe}.json"


def book_log_path(book_id: str, root: Path | None = None) -> Path:
    base = root or ROOT
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(book_id))
    return base / "analysis" / "output" / f"execution_log_{safe}.json"


def listed_book_signals(index: dict[str, Any], root: Path | None = None) -> list[tuple[str, Path, Path]]:
    """Map an index payload to (book_id, signal_path, log_path)."""
    base = root or ROOT
    out: list[tuple[str, Path, Path]] = []
    books = index.get("books")
    if not isinstance(books, list):
        return out
    for book in books:
        if not isinstance(book, dict):
            continue
        book_id = str(book.get("id") or "book")
        raw = book.get("signal")
        signal = (base / str(raw)).resolve() if raw else book_signal_path(book_id, base)
        out.append((book_id, signal, book_log_path(book_id, base)))
    return out


def is_signal_index(payload: dict[str, Any]) -> bool:
    books = payload.get("books")
    if not isinstance(books, list) or not books:
        return False
    if payload.get("results"):
        return False
    return any(isinstance(book, dict) and book.get("signal") for book in books)


def overlap_errors(books: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen: dict[str, str] = {}
    errors: list[dict[str, str]] = []
    for book in books:
        book_id = str(book["id"])
        for symbol in book["config"].get("symbols") or []:
            ticker = str(symbol)
            if ticker in seen:
                errors.append(
                    {
                        "ticker": ticker,
                        "error": (
                            f"{ticker} is in both '{seen[ticker]}' and '{book_id}'. "
                            "Futu 模拟盘 is one net position; keep books disjoint."
                        ),
                    }
                )
            else:
                seen[ticker] = book_id
    return errors


def any_futu_sim(payload: dict[str, Any]) -> bool:
    aliases = {"futu-sim", "futu", "simulate", "sim", "opend"}
    configs = [payload.get("config") or {}]
    for book in payload.get("books") or []:
        if isinstance(book, dict):
            configs.append(book.get("config") or {})
    for row in payload.get("results") or []:
        if isinstance(row, dict):
            configs.append({"execution": row.get("execution")})
    for config in configs:
        raw = str(config.get("execution") or "").strip().lower()
        if raw in aliases:
            return True
    return False
