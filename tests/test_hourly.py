"""Hidden hourly job skips the loop when the US session gate is closed."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from analysis.hourly import main, run_book_executors


class HourlyJobTests(unittest.TestCase):
    @patch("analysis.hourly.executor_main")
    @patch("analysis.hourly.loop_main")
    @patch("analysis.hourly.should_refresh_signals", return_value=False)
    def test_skip_does_not_run_loop(self, _signals, loop_main, executor_main) -> None:
        self.assertEqual(main([]), 0)
        loop_main.assert_not_called()
        executor_main.assert_not_called()

    @patch("analysis.hourly.executor_main")
    @patch("analysis.hourly.loop_main", return_value=0)
    @patch("analysis.hourly.should_place_sim", return_value=False)
    @patch("analysis.hourly.should_refresh_signals", return_value=True)
    def test_outside_rth_signals_only(self, _signals, _sim, loop_main, executor_main) -> None:
        self.assertEqual(main([]), 0)
        loop_main.assert_called_once()
        executor_main.assert_not_called()

    @patch("analysis.hourly.executor_main")
    @patch("analysis.hourly.loop_main", return_value=0)
    @patch("analysis.hourly.should_place_sim", return_value=True)
    @patch("analysis.hourly.should_refresh_signals", return_value=True)
    def test_dry_run_skips_executor(self, _signals, _sim, loop_main, executor_main) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            long_file = root / "trading_signal_long.json"
            long_file.write_text(
                json.dumps({"config": {"execution": "dry-run"}, "results": [{"execution": "dry-run"}]}),
                encoding="utf-8",
            )
            index = root / "trading_signal.json"
            index.write_text(
                json.dumps(
                    {
                        "books": [
                            {"id": "long", "signal": "trading_signal_long.json", "execution": "dry-run"}
                        ],
                        "results": [],
                    }
                ),
                encoding="utf-8",
            )
            with patch("analysis.hourly.ROOT", root), patch("analysis.hourly.SIGNAL_INDEX", index):
                self.assertEqual(main([]), 0)
        loop_main.assert_called_once()
        executor_main.assert_not_called()

    @patch("analysis.hourly.executor_main", return_value=0)
    def test_futu_sim_only_on_that_book(self, executor_main) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "trading_signal_long.json").write_text(
                json.dumps({"config": {"execution": "dry-run"}, "results": [{"execution": "dry-run"}]}),
                encoding="utf-8",
            )
            short_file = root / "trading_signal_short.json"
            short_file.write_text(
                json.dumps({"config": {"execution": "futu-sim"}, "results": [{"execution": "futu-sim"}]}),
                encoding="utf-8",
            )
            index = root / "trading_signal.json"
            index.write_text(
                json.dumps(
                    {
                        "books": [
                            {"id": "long", "signal": "trading_signal_long.json", "execution": "dry-run"},
                            {"id": "short", "signal": "trading_signal_short.json", "execution": "futu-sim"},
                        ],
                        "results": [],
                    }
                ),
                encoding="utf-8",
            )
            with patch("analysis.hourly.ROOT", root):
                self.assertEqual(run_book_executors(index), 0)
        executor_main.assert_called_once()
        args = executor_main.call_args[0][0]
        self.assertEqual(args[1], str(short_file.resolve()))
        self.assertIn("execution_log_short.json", args[3])


if __name__ == "__main__":
    unittest.main()
