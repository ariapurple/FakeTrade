"""News keyword gate and disjoint books."""

from __future__ import annotations

import unittest
from pathlib import Path

from analysis.books import (
    book_signal_path,
    is_signal_index,
    listed_book_signals,
    overlap_errors,
)
from analysis.news_gate import score_headlines


class NewsGateTests(unittest.TestCase):
    def test_hard_negative_sells(self) -> None:
        report = score_headlines(["Acme files Chapter 11 bankruptcy protection"])
        self.assertEqual(report["signal"], "SELL")

    def test_product_news_is_hold(self) -> None:
        report = score_headlines(["Apple will launch its first foldable iPhone Duo"])
        self.assertEqual(report["signal"], "HOLD")


class BooksTests(unittest.TestCase):
    def test_overlap_is_an_error(self) -> None:
        books = [
            {"id": "long", "config": {"symbols": ["NVDA.US"]}},
            {"id": "short", "config": {"symbols": ["NVDA.US", "AMD.US"]}},
        ]
        errors = overlap_errors(books)
        self.assertEqual(len(errors), 1)
        self.assertIn("NVDA.US", errors[0]["error"])

    def test_signal_paths_are_split(self) -> None:
        root = Path("D:/fake-root")
        self.assertEqual(book_signal_path("long", root), root / "trading_signal_long.json")
        self.assertEqual(book_signal_path("short", root), root / "trading_signal_short.json")
        listed = listed_book_signals(
            {"books": [{"id": "long", "signal": "trading_signal_long.json"}]},
            root,
        )
        self.assertEqual(listed[0][0], "long")
        self.assertEqual(listed[0][1], (root / "trading_signal_long.json").resolve())
        self.assertTrue(
            is_signal_index(
                {
                    "books": [{"id": "long", "signal": "trading_signal_long.json"}],
                    "results": [],
                }
            )
        )
        self.assertFalse(is_signal_index({"books": [{"id": "long"}], "results": [{"ticker": "AAPL.US"}]}))


if __name__ == "__main__":
    unittest.main()
