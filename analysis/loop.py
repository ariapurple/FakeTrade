"""Run one watchlist or all books; write trading_signal_long.json / trading_signal_short.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from analysis.books import book_signal_path, load_books, overlap_errors
from analysis.manager import now_hk_iso, run_watchlist

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "trading_signal.json"


def load_watchlist(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _tag_rows(payload: dict[str, Any], book_id: str, book_path: str) -> dict[str, Any]:
    qty = int(payload.get("config", {}).get("qty", 1))
    strategy = str(payload.get("config", {}).get("strategy", "vote"))
    execution = str(payload.get("config", {}).get("execution", "dry-run"))
    for row in payload.get("results") or []:
        row["book"] = book_id
        row["book_path"] = book_path
        row["strategy"] = strategy
        row["qty"] = qty
        row["execution"] = execution
    for row in payload.get("actionable") or []:
        row["book"] = book_id
        row["strategy"] = strategy
        row["qty"] = qty
        row["execution"] = execution
    for err in payload.get("errors") or []:
        err["book"] = book_id
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Multi-ticker Quant loop on Longbridge data.")
    parser.add_argument("--watchlist", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    output_path = args.output.resolve()
    if args.watchlist is not None:
        watchlist_path = args.watchlist.resolve()
        config = load_watchlist(watchlist_path)
        print(f"watchlist {watchlist_path}")
        print(f"symbols   {', '.join(str(s) for s in config.get('symbols', []))}")
        payload = run_watchlist(config)
        payload["watchlist_path"] = str(watchlist_path)
        payload = _tag_rows(payload, "single", str(watchlist_path))
    else:
        books = load_books(ROOT)
        errors = overlap_errors(books)
        if errors:
            for err in errors:
                print(f"  ERROR {err['ticker']}: {err['error']}")
            return 1
        index_books: list[dict[str, Any]] = []
        had_errors = False
        for book in books:
            config = book["config"]
            print(f"book {book['id']}  {book['path']}")
            print(f"  strategy={config.get('strategy')}  symbols={', '.join(str(s) for s in config.get('symbols', []))}")
            book_payload = run_watchlist(config)
            book_payload["book_id"] = book["id"]
            book_payload["watchlist_path"] = book["path"]
            book_payload = _tag_rows(book_payload, book["id"], book["path"])
            signal_path = book_signal_path(str(book["id"]), ROOT)
            signal_path.write_text(json.dumps(book_payload, indent=2, ensure_ascii=False), encoding="utf-8")
            print(
                f"  wrote {signal_path}  {len(book_payload['results'])} symbols  "
                f"{len(book_payload['actionable'])} actionable"
            )
            for row in book_payload["results"]:
                print(
                    f"    {row['ticker']:10} {row['final_decision']:4}  "
                    f"close={row['close']}  votes buy={row['buy_votes']} sell={row['sell_votes']}"
                )
            for err in book_payload["errors"]:
                had_errors = True
                print(f"    ERROR {err['ticker']}: {err['error']}")
            index_books.append(
                {
                    "id": book["id"],
                    "watchlist": book["path"],
                    "signal": signal_path.name,
                    "execution": str(config.get("execution", "dry-run")),
                    "budget_usd": float(config.get("budget_usd") or 1000),
                    "strategy": str(config.get("strategy", "")),
                    "symbols": list(config.get("symbols") or []),
                    "actionable": len(book_payload.get("actionable") or []),
                }
            )
        payload = {
            "generated_at": now_hk_iso(),
            "data_source": "Longbridge",
            "_comment": "Index only. Open trading_signal_long.json and trading_signal_short.json for decisions.",
            "books": index_books,
            "config": {
                "books": [row["id"] for row in index_books],
                "execution": index_books[0]["execution"] if index_books else "dry-run",
            },
            "results": [],
            "errors": [],
            "actionable": [],
        }
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote index {output_path}")
        return 1 if had_errors else 0

    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {output_path}  {len(payload['results'])} symbols  {len(payload['actionable'])} actionable")
    for row in payload["results"]:
        book = row.get("book", "")
        print(
            f"  {str(book):6} {row['ticker']:10} {row['final_decision']:4}  "
            f"close={row['close']}  votes buy={row['buy_votes']} sell={row['sell_votes']}"
        )
    for err in payload["errors"]:
        print(f"  ERROR {err.get('book', '')} {err['ticker']}: {err['error']}")
    return 0 if not payload["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
