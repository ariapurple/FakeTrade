"""News keyword gate and disjoint books."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis.books import (
    ROOT,
    book_budget_usd,
    book_signal_path,
    book_starting_usd,
    is_signal_index,
    listed_book_signals,
    load_book_cash,
    load_books,
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

    def test_repo_is_one_grouped_hold_book(self) -> None:
        books = load_books(ROOT)
        self.assertEqual([book["id"] for book in books], ["hold"])
        self.assertEqual(books[0]["config"]["strategy"], "buy_hold")
        self.assertNotIn("starting_usd", books[0]["config"])
        self.assertEqual(books[0]["config"]["budget_usd"], "unlimited")
        self.assertIsNone(book_budget_usd(books[0]["config"]))
        self.assertEqual(books[0]["config"]["qty"], 1)
        self.assertNotIn("qty_cheap", books[0]["config"])
        self.assertEqual(books[0]["config"]["count"], 300)
        sell = books[0]["config"]["sell"]
        self.assertEqual(sell["below_sma"], 200)
        self.assertEqual(sell["drawdown_from_high"], 0)
        self.assertEqual(books[0]["config"]["buy"]["add"], "always_add")
        self.assertEqual(books[0]["config"]["buy"]["max_extension_pct"], 0.08)
        self.assertFalse(overlap_errors(books))
        symbols = list(books[0]["config"]["symbols"])
        self.assertIn("AAPL.US", symbols)
        self.assertIn("AMD.US", symbols)


class BookCashTests(unittest.TestCase):
    def test_starting_usd_means_no_cap(self) -> None:
        self.assertIsNone(book_budget_usd({"starting_usd": 2000}))
        self.assertEqual(book_starting_usd({"starting_usd": 2000}), 2000)
        self.assertEqual(book_budget_usd({"budget_usd": 500}), 500)
        self.assertIsNone(book_budget_usd({"budget_usd": "unlimited"}))

    def test_missing_cash_file_seeds_leftover_of_start(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cash.json"
            self.assertEqual(load_book_cash(path, starting_usd=2000, book_used=0), 2000)
            self.assertEqual(load_book_cash(path, starting_usd=2000, book_used=800), 1200)
            self.assertEqual(load_book_cash(path, starting_usd=2000, book_used=2500), 0)

    def test_neither_starting_nor_budget_defaults_to_1000_cap(self) -> None:
        self.assertEqual(book_budget_usd({}), 1000.0)
        self.assertIsNone(book_starting_usd({}))


if __name__ == "__main__":
    unittest.main()
