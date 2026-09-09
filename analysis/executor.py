"""Turn trading_signal.json into dry-run, paper, Futu 模拟盘, or Longbridge preview.

Never TrdEnv.REAL. Never `longbridge order --execute`.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol, assert_never

from analysis.books import any_futu_sim, is_signal_index
from analysis.futu_sim import (
    FutuSimBroker,
    FutuSimError,
    OpenDDownError,
    book_notional,
    held_qty,
    opend_up,
    pending_buy_notional,
    pending_buy_qty,
)
from analysis.manager import strategy_from_config
from analysis.quote import live_price_for
from analysis.session import in_us_rth
from analysis.paper_broker import (
    DEFAULT_LEDGER,
    apply_fill,
    load_account,
    load_ledger,
    save_ledger,
)
from analysis.proc import run_hidden

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SIGNAL = ROOT / "trading_signal.json"
DEFAULT_LOG = ROOT / "analysis" / "output" / "execution_log.json"

Mode = Literal["dry-run", "paper", "futu-sim", "longbridge-preview"]
DEFAULT_BOOK_BUDGET_USD = 1000.0


def book_budget_usd(config: dict[str, Any]) -> float:
    """Per-book notional cap. Defaults to $1000 so the $1M 模拟盘 cash is not used."""
    raw = config.get("budget_usd")
    if raw is None or raw == "":
        return DEFAULT_BOOK_BUDGET_USD
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_BOOK_BUDGET_USD
    return max(0.0, value)


class SimBroker(Protocol):
    def connect(self, market: str = "US") -> dict[str, Any]: ...
    def place_simulate(
        self,
        *,
        symbol: str,
        side: Literal["BUY", "SELL"],
        qty: int,
        price: float,
        remark: str = "QUANTSIM",
    ) -> dict[str, Any]: ...
    def funds(self) -> dict[str, Any]: ...
    def positions(self) -> list[dict[str, Any]]: ...
    def close(self) -> None: ...


def mode_from_config(config: dict[str, Any], preview_flag: bool) -> Mode:
    if preview_flag:
        return "longbridge-preview"
    raw = str(config.get("execution", "futu-sim")).strip().lower()
    if raw in {"futu-sim", "futu", "simulate", "sim", "opend"}:
        return "futu-sim"
    if raw in {"paper", "paper-trade", "fake"}:
        return "paper"
    if raw in {"longbridge-preview", "preview"}:
        return "longbridge-preview"
    if raw in {"dry-run", "dry", "none"}:
        return "dry-run"
    return "dry-run"


def _empty_action(row: dict[str, Any], qty: int, price: float) -> dict[str, Any]:
    return {
        "ticker": row["ticker"],
        "decision": row["final_decision"],
        "qty": qty,
        "price": price,
        "status": "skipped",
    }


def _row_qty(row: dict[str, Any], default_qty: int) -> int:
    try:
        return int(row.get("qty") or default_qty)
    except (TypeError, ValueError):
        return default_qty


def _order_price(row: dict[str, Any]) -> tuple[float, dict[str, Any] | None]:
    """Prefer the live 盤前/盤中/盤後/夜盤 quote; fall back to the signal's kline close."""
    ticker = str(row.get("ticker") or "")
    live = live_price_for(ticker) if ticker else None
    if live and live.get("price"):
        try:
            price = float(live["price"])
        except (TypeError, ValueError):
            price = 0.0
        if price > 0:
            return price, live
    try:
        fallback = float(row.get("close") or 0)
    except (TypeError, ValueError):
        fallback = 0.0
    return fallback, None


def _row_mode(row: dict[str, Any], fallback: Mode, preview_flag: bool) -> Mode:
    if preview_flag:
        return "longbridge-preview"
    if row.get("execution"):
        return mode_from_config({"execution": row.get("execution")}, False)
    return fallback


def execute(
    payload: dict[str, Any],
    mode: Mode,
    qty: int,
    *,
    futu_broker: SimBroker | None = None,
) -> dict[str, Any]:
    log: dict[str, Any] = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "futu_opend": opend_up(),
        "actions": [],
    }
    strategy = strategy_from_config(payload.get("config") or {})
    log["strategy"] = strategy
    actionable = [
        row
        for row in payload.get("actionable", [])
        if row.get("final_decision") in {"BUY", "SELL"}
    ]

    dry_rows: list[dict[str, Any]] = []
    futu_rows: list[dict[str, Any]] = []
    paper_rows: list[dict[str, Any]] = []
    preview_rows: list[dict[str, Any]] = []
    for row in actionable:
        row_mode = _row_mode(row, mode, mode == "longbridge-preview")
        if row_mode == "dry-run":
            dry_rows.append(row)
        elif row_mode == "futu-sim":
            futu_rows.append(row)
        elif row_mode == "paper":
            paper_rows.append(row)
        elif row_mode == "longbridge-preview":
            preview_rows.append(row)
        else:
            assert_never(row_mode)

    if mode == "dry-run":
        dry_rows, futu_rows, paper_rows, preview_rows = actionable, [], [], []
    elif mode == "paper":
        dry_rows, futu_rows, paper_rows, preview_rows = [], [], actionable, []
    elif mode == "longbridge-preview":
        dry_rows, futu_rows, paper_rows, preview_rows = [], [], [], actionable

    if mode == "futu-sim" and futu_rows and not in_us_rth():
        log["status"] = "skipped-outside-rth"
        log["futu_note"] = (
            "Futu 模拟盘 only during US regular hours (09:30-16:00 ET). "
            "That is 13:30-20:00 UTC on US daylight time. Signal kept, no order."
        )
        for row in futu_rows:
            row_qty = _row_qty(row, qty)
            price = float(row.get("close") or 0)
            action = _empty_action(row, row_qty, price)
            action["status"] = "skipped-outside-rth"
            action["note"] = log["futu_note"]
            log["actions"].append(action)
        futu_rows = []

    for row in dry_rows:
        row_qty = _row_qty(row, qty)
        price = float(row.get("close") or 0)
        action = _empty_action(row, row_qty, price)
        action["status"] = "dry-run"
        action["book"] = row.get("book")
        action["strategy"] = row.get("strategy") or strategy
        if (row.get("strategy") or strategy) == "buy_hold":
            action["note"] = (
                "Long book (dry-run). No fill. "
                "Sells only on SMA/drawdown/news. Set execution=futu-sim for 模拟盘."
            )
        else:
            action["note"] = "No fill. Set this book's execution=futu-sim for Futu 模拟盘."
        log["actions"].append(action)
    if dry_rows and mode == "dry-run":
        log["futu_note"] = "Dry-run. No Futu order was sent."

    if paper_rows:
        log["ledger_path"] = str(DEFAULT_LEDGER)
        ledger = load_ledger()
        for row in paper_rows:
            row_qty = _row_qty(row, qty)
            price = float(row.get("close") or 0)
            fill = apply_fill(
                ledger,
                symbol=row["ticker"],
                side=row["final_decision"],
                qty=row_qty,
                price=price,
                reason=f"{row.get('book') or 'book'} {row.get('strategy') or strategy}",
            )
            action = _empty_action(row, row_qty, price)
            action.update(fill)
            log["actions"].append(action)
        save_ledger(ledger)
        log["cash"] = ledger["cash"]
        log["positions"] = ledger.get("positions", {})
        log["fills_count"] = len(ledger.get("fills", []))
        log["account"] = load_account()
        log["futu_note"] = "Internal paper ledger. Futu OpenD was not called."

    if mode == "futu-sim" and futu_rows:
        extra = _execute_futu_sim(futu_rows, qty, futu_broker, payload.get("config") or {})
        log["actions"].extend(extra.pop("actions", []))
        log.update(extra)
    elif mode == "futu-sim" and dry_rows and not futu_rows:
        log["futu_note"] = "No futu-sim rows this run. Dry-run books were logged only."

    if mode == "longbridge-preview" or preview_rows:
        for row in preview_rows or (actionable if mode == "longbridge-preview" else []):
            row_qty = _row_qty(row, qty)
            price = float(row.get("close") or 0)
            action = _empty_action(row, row_qty, price)
            side = "buy" if row["final_decision"] == "BUY" else "sell"
            cmd = [
                "longbridge",
                "order",
                side,
                row["ticker"],
                str(row_qty),
                "--order-type",
                "MO",
                "--format",
                "json",
            ]
            completed = run_hidden(cmd)
            action["command"] = cmd
            action["returncode"] = completed.returncode
            action["stdout"] = (completed.stdout or "")[-4000:]
            action["stderr"] = (completed.stderr or "")[-2000:]
            action["status"] = "previewed" if completed.returncode == 0 else "preview-failed"
            action["note"] = "Preview only. Never pass --execute unless you intend a live Longbridge order."
            log["actions"].append(action)
        log["futu_note"] = "Longbridge preview only. Futu was not called."

    if not log["actions"] and not log.get("note"):
        log["note"] = "No BUY/SELL to execute this run."
    return log


def _execute_futu_sim(
    actionable: list[dict[str, Any]],
    qty: int,
    futu_broker: SimBroker | None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    budget = book_budget_usd(config)
    symbols = [str(item) for item in (config.get("symbols") or [])]
    if not symbols:
        symbols = [str(row.get("ticker") or "") for row in actionable if row.get("ticker")]
    extra: dict[str, Any] = {
        "actions": [],
        "futu_note": "Futu 模拟盘 via OpenD. TrdEnv.REAL is never used.",
        "budget_usd": budget,
        "budget_symbols": symbols,
    }
    broker = futu_broker or FutuSimBroker()
    owns_broker = futu_broker is None
    try:
        extra["futu"] = broker.connect("US")
        extra["futu_opend"] = True
        snapshot = list(broker.positions())
        extra["futu_positions_before"] = snapshot
        fetch_orders = getattr(broker, "open_orders", None)
        orders = list(fetch_orders()) if callable(fetch_orders) else []
        extra["futu_open_orders"] = orders
        used = book_notional(snapshot, symbols) + pending_buy_notional(orders, symbols)
        remaining = max(0.0, budget - used)
        extra["book_notional_before"] = round(used, 2)
        extra["budget_remaining_before"] = round(remaining, 2)
        bought_this_run: dict[str, float] = {}
        sold_this_run: dict[str, float] = {}
        for row in actionable:
            want_qty = _row_qty(row, qty)
            price, live = _order_price(row)
            ticker = str(row["ticker"])
            if price <= 0:
                action = _empty_action(row, want_qty, price)
                action["status"] = "skipped-no-price"
                action["note"] = "No live Longbridge quote or kline close; refused to guess a Futu price."
                extra["actions"].append(action)
                continue
            held = (
                held_qty(snapshot, ticker)
                + pending_buy_qty(orders, ticker)
                + bought_this_run.get(ticker, 0.0)
                - sold_this_run.get(ticker, 0.0)
            )
            if row.get("final_decision") == "BUY" and held >= want_qty:
                action = _empty_action(row, want_qty, price)
                action["status"] = "skipped-already-long"
                action["note"] = f"Already long {held:g} {ticker}; will not add."
                extra["actions"].append(action)
                continue
            if row.get("final_decision") == "SELL" and held <= 0:
                action = _empty_action(row, want_qty, price)
                action["status"] = "skipped-flat"
                action["note"] = f"No long position in {ticker}; nothing to sell."
                extra["actions"].append(action)
                continue
            if row.get("final_decision") == "SELL":
                order_qty = int(held) if held >= 1 else want_qty
            else:
                affordable = int(remaining // price)
                order_qty = min(want_qty, affordable)
                if order_qty < 1:
                    action = _empty_action(row, want_qty, price)
                    action["status"] = "skipped-budget"
                    action["note"] = (
                        f"Book cap ${budget:.0f}; ${remaining:.2f} left after "
                        f"${used:.2f} already in this book's names. {ticker} is ${price:.2f}."
                    )
                    extra["actions"].append(action)
                    continue
            fill = broker.place_simulate(
                symbol=ticker,
                side=row["final_decision"],
                qty=order_qty,
                price=price,
                remark="QUANTSIM",
            )
            extra["actions"].append(fill)
            if live:
                fill["quote_session"] = live.get("session")
                fill["quote_source"] = live.get("source")
            if str(fill.get("status")) == "futu-sim-submitted":
                if row.get("final_decision") == "BUY":
                    bought_this_run[ticker] = bought_this_run.get(ticker, 0.0) + order_qty
                    cost = order_qty * price
                    remaining -= cost
                    used += cost
                elif row.get("final_decision") == "SELL":
                    sold_this_run[ticker] = sold_this_run.get(ticker, 0.0) + order_qty
                    remaining += order_qty * price
                    used = max(0.0, used - order_qty * price)
        extra["book_notional_after"] = round(used, 2)
        extra["budget_remaining_after"] = round(max(0.0, remaining), 2)
        extra["futu_funds"] = broker.funds()
        extra["futu_positions"] = broker.positions()
    except OpenDDownError as exc:
        extra["futu_opend"] = False
        extra["status"] = "opend-down"
        extra["error"] = str(exc)
        extra["futu_note"] = str(exc)
        for row in actionable:
            price = float(row.get("close") or 0)
            action = _empty_action(row, qty, price)
            action["status"] = "skipped-opend-down"
            action["note"] = str(exc)
            extra["actions"].append(action)
        if not extra["actions"]:
            extra["note"] = (
                "No BUY/SELL this hour, and OpenD is down. "
                "Unattended Futu fake trades need OpenD on this machine."
            )
    except FutuSimError as exc:
        extra["status"] = "futu-sim-error"
        extra["error"] = str(exc)
        extra["futu_note"] = str(exc)
        if not extra["actions"] and actionable:
            for row in actionable:
                price = float(row.get("close") or 0)
                action = _empty_action(row, qty, price)
                action["status"] = "skipped-futu-error"
                action["note"] = str(exc)
                extra["actions"].append(action)
    finally:
        if owns_broker:
            broker.close()
    return extra


def log_exit_code(log: dict[str, Any]) -> int:
    status = str(log.get("status") or "")
    if status == "opend-down":
        return 2
    if status == "futu-sim-error":
        return 1
    if any(str(action.get("status", "")).endswith("failed") for action in log.get("actions", [])):
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Executor for Quant watchlist signals. Futu = SIMULATE only.")
    parser.add_argument("--signal", type=Path, default=DEFAULT_SIGNAL)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument(
        "--longbridge-preview",
        action="store_true",
        help="Call `longbridge order buy/sell` WITHOUT --execute (preview only).",
    )
    args = parser.parse_args(argv)

    if not args.signal.exists():
        print(f"missing {args.signal}; run python -m analysis.loop first")
        return 1

    payload = json.loads(args.signal.read_text(encoding="utf-8"))
    if is_signal_index(payload):
        print(f"{args.signal.name} is an index; per-book files are listed in it. Skipping.")
        return 0
    config = payload.get("config", {})
    qty = int(config.get("qty", 1))
    mode = mode_from_config(config, args.longbridge_preview)
    if not args.longbridge_preview and any_futu_sim(payload):
        mode = "futu-sim"
    log = execute(payload, mode, qty)
    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.log.write_text(json.dumps(log, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"mode={log['mode']}  futu_opend={log.get('futu_opend')}  actions={len(log['actions'])}")
    if log.get("budget_usd") is not None:
        print(
            f"budget=${log.get('budget_usd')}  "
            f"book_notional {log.get('book_notional_before')} -> {log.get('book_notional_after')}  "
            f"left={log.get('budget_remaining_after')}"
        )
    if log.get("futu"):
        print(f"futu acc_id={log['futu'].get('acc_id')} trd_env={log['futu'].get('trd_env')}")
    if log.get("positions") is not None:
        print(f"positions {log['positions']}")
    for action in log["actions"]:
        print(f"  {action.get('decision', action.get('side'))} {action['ticker']:10} {action['status']}")
    if log.get("error"):
        print(log["error"])
    if log.get("note"):
        print(log["note"])
    print(f"wrote {args.log}")
    return log_exit_code(log)


if __name__ == "__main__":
    raise SystemExit(main())
