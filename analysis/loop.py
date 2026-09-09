"""Run the watchlist and write trading_signal.json for Automations / the executor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from analysis.manager import run_watchlist

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WATCHLIST = ROOT / "config" / "watchlist.json"
DEFAULT_OUTPUT = ROOT / "trading_signal.json"


def load_watchlist(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Multi-ticker Quant loop on Longbridge data.")
    parser.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    config = load_watchlist(args.watchlist)
    payload = run_watchlist(config)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"wrote {args.output}  {len(payload['results'])} symbols  {len(payload['actionable'])} actionable")
    for row in payload["results"]:
        print(f"  {row['ticker']:10} {row['final_decision']:4}  close={row['close']}  votes buy={row['buy_votes']} sell={row['sell_votes']}")
    for err in payload["errors"]:
        print(f"  ERROR {err['ticker']}: {err['error']}")
    return 0 if not payload["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
