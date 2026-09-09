"""Unattended 30-minute job: session gate, analysis loop, optional Futu SIMULATE executor.

Run with pythonw.exe so Task Scheduler does not flash a console or steal focus.
"""

from __future__ import annotations

import json
from pathlib import Path

from analysis.books import any_futu_sim, listed_book_signals
from analysis.executor import main as executor_main
from analysis.loop import main as loop_main
from analysis.session import in_us_rth, in_us_trade_window

ROOT = Path(__file__).resolve().parents[1]
SIGNAL_INDEX = ROOT / "trading_signal.json"


def run_book_executors(index_path: Path = SIGNAL_INDEX) -> int:
    """Place 模拟盘 fills only for books whose own file has execution=futu-sim."""
    if not index_path.exists():
        return 0
    index = json.loads(index_path.read_text(encoding="utf-8"))
    listed = listed_book_signals(index, ROOT)
    if not listed:
        if any_futu_sim(index) and index.get("results"):
            return executor_main([])
        return 0
    worst = 0
    ran = False
    for _book_id, signal, log_path in listed:
        if not signal.exists():
            continue
        payload = json.loads(signal.read_text(encoding="utf-8"))
        if not any_futu_sim(payload):
            continue
        ran = True
        code = executor_main(["--signal", str(signal), "--log", str(log_path)])
        if code:
            worst = code
    if not ran:
        return 0
    return worst


def main(argv: list[str] | None = None) -> int:
    del argv
    if not in_us_trade_window():
        return 0
    loop_code = loop_main([])
    if not in_us_rth():
        return loop_code
    exec_code = run_book_executors()
    if loop_code != 0:
        return loop_code
    return exec_code


if __name__ == "__main__":
    raise SystemExit(main())
