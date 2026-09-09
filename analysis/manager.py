"""Watchlist manager: buy-and-hold (optional exits), MA swing, or four-agent vote."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal, assert_never

from analysis.agents import (
    Signal,
    buy_and_hold,
    buy_hold_exits,
    ma_swing,
    mean_reversion,
    trend_following,
    value_investing,
    volume_spread,
    vote_weight,
)
from analysis.books import book_budget_usd, book_starting_usd
from analysis.fundamentals import fetch_calc_index
from analysis.kline import fetch_klines, to_quantharness
from analysis.news_gate import news_gate
from analysis.quote import fetch_quotes, parse_live_price

HK_TZ = timezone(timedelta(hours=8))
StrategyName = Literal["vote", "buy_hold", "swing"]
AddStyle = Literal["always_add", "dip_add"]


def now_hk_iso() -> str:
    return datetime.now(HK_TZ).isoformat()


def strategy_from_config(config: dict[str, Any]) -> StrategyName:
    raw = str(config.get("strategy", "vote")).strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"buy_hold", "buy_and_hold", "buyandhold", "hold"}:
        return "buy_hold"
    if raw in {"swing", "ma_swing", "short", "short_term"}:
        return "swing"
    return "vote"


def _final_decision(
    reports: dict[str, dict[str, Any]],
    buy_votes_needed: int,
    sell_votes_needed: int,
) -> Signal:
    buy_votes = 0
    sell_votes = 0
    for report in reports.values():
        signal: Signal = report["signal"]
        weight = vote_weight(signal)
        if weight == 1:
            buy_votes += 1
        elif weight == -1:
            sell_votes += 1
    if buy_votes >= buy_votes_needed:
        return "BUY"
    if sell_votes >= sell_votes_needed:
        return "SELL"
    return "HOLD"


def _sell_cfg(config: dict[str, Any]) -> dict[str, Any]:
    """Missing or empty ``sell`` means never-sell buy-and-hold."""
    block = config.get("sell") if isinstance(config.get("sell"), dict) else None
    if not block:
        return {
            "below_sma": 0,
            "drawdown_from_high": 0.0,
            "high_lookback": 0,
            "news": False,
        }
    return {
        "below_sma": int(block.get("below_sma") or 0),
        "drawdown_from_high": float(block.get("drawdown_from_high") or 0),
        "high_lookback": int(block.get("high_lookback") or 0),
        "news": bool(block.get("news", False)),
    }


def add_style_from_raw(raw: str) -> AddStyle:
    key = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
    if key in {"always_add", "always", "always_add_1", "add_1"}:
        return "always_add"
    if key in {"dip_add", "dip", "dip_add_1", "dip_in_expansion"}:
        return "dip_add"
    raise ValueError(f"Unknown buy.add {raw!r}; use always_add or dip_add.")


def live_extension_pct(buy: dict[str, Any]) -> float:
    """Band used for live BUY/HOLD. always_add ignores max_extension_pct."""
    style: AddStyle = buy["add"]
    if style == "always_add":
        return 0.0
    if style == "dip_add":
        return float(buy["max_extension_pct"])
    assert_never(style)


def _buy_cfg(config: dict[str, Any]) -> dict[str, Any]:
    """Missing ``buy`` means always-add. Dip band is kept so the switch is one field."""
    block = config.get("buy") if isinstance(config.get("buy"), dict) else None
    if not block:
        return {"add": "always_add", "max_extension_pct": 0.0}
    pct = float(block.get("max_extension_pct") or 0)
    raw_add = block.get("add")
    if raw_add is None or str(raw_add).strip() == "":
        style: AddStyle = "dip_add" if pct > 0 else "always_add"
    else:
        style = add_style_from_raw(str(raw_add))
    if style == "dip_add" and pct <= 0:
        pct = 0.08
    return {"add": style, "max_extension_pct": pct}


def _exits_enabled(sell: dict[str, Any]) -> bool:
    return bool(
        sell.get("below_sma")
        or float(sell.get("drawdown_from_high") or 0) > 0
        or sell.get("news")
    )


def _news_enabled(config: dict[str, Any], strategy: StrategyName) -> bool:
    if "news" in config:
        return bool(config.get("news"))
    if strategy == "buy_hold":
        return bool(_sell_cfg(config)["news"])
    if strategy == "swing":
        return True
    return False


def run_symbol(
    symbol: str,
    *,
    period: str,
    count: int,
    buy_votes_needed: int,
    sell_votes_needed: int,
    strategy: StrategyName = "vote",
    config: dict[str, Any] | None = None,
    live: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    rows = fetch_klines(symbol, period=period, count=count)
    kline_data = to_quantharness(rows)
    news_report = news_gate(symbol, enabled=_news_enabled(cfg, strategy))
    live_px = float(live["price"]) if live and live.get("price") else None
    qty = max(1, int(cfg.get("qty") or 1))
    if strategy == "buy_hold":
        sell = _sell_cfg(cfg)
        buy = _buy_cfg(cfg)
        extension = live_extension_pct(buy)
        if _exits_enabled(sell) or extension > 0:
            plan = buy_hold_exits(
                kline_data,
                below_sma=int(sell["below_sma"]),
                drawdown_from_high=float(sell["drawdown_from_high"]),
                high_lookback=int(sell["high_lookback"]),
                news_report=news_report,
                last_price=live_px,
                max_extension_pct=extension,
            )
        else:
            plan = buy_and_hold()
        reports = {"buy_hold": plan, "news": news_report}
        decision: Signal = plan["signal"]
        buy_votes = 1 if decision == "BUY" else 0
        sell_votes = 1 if decision == "SELL" else 0
    elif strategy == "swing":
        swing = ma_swing(kline_data)
        decision = swing["signal"]
        if news_report.get("signal") == "SELL":
            decision = "SELL"
            swing = dict(swing)
            swing["reason"] = f"{swing.get('reason')} News veto: {news_report.get('reason')}"
        reports = {"swing": swing, "news": news_report}
        buy_votes = 1 if decision == "BUY" else 0
        sell_votes = 1 if decision == "SELL" else 0
    elif strategy == "vote":
        calc = fetch_calc_index(symbol)
        reports = {
            "trend": trend_following(kline_data),
            "reversion": mean_reversion(kline_data),
            "vsa": volume_spread(kline_data),
            "value": value_investing(calc),
        }
        if _news_enabled(cfg, strategy):
            reports["news"] = news_report
        decision = _final_decision(reports, buy_votes_needed, sell_votes_needed)
        buy_votes = sum(1 for r in reports.values() if r["signal"] == "BUY")
        sell_votes = sum(1 for r in reports.values() if r["signal"] == "SELL")
    else:
        assert_never(strategy)
    kline_close = kline_data["Close"][-1]
    close = live_px if live_px is not None else kline_close
    return {
        "ticker": symbol,
        "timestamp": now_hk_iso(),
        "period": period,
        "close": close,
        "kline_close": kline_close,
        "quote_session": None if not live else live.get("session"),
        "quote_source": None if not live else live.get("source"),
        "final_decision": decision,
        "qty": qty,
        "buy_votes": buy_votes,
        "sell_votes": sell_votes,
        "detailed_reports": reports,
    }


def run_watchlist(config: dict[str, Any]) -> dict[str, Any]:
    symbols = list(config["symbols"])
    period = str(config.get("period", "day"))
    count = int(config.get("count", 80))
    buy_needed = int(config.get("buy_votes_needed", 3))
    sell_needed = int(config.get("sell_votes_needed", 3))
    strategy = strategy_from_config(config)
    quotes: dict[str, dict[str, Any]] = {}
    try:
        quotes = fetch_quotes(symbols)
    except (RuntimeError, ValueError, OSError):
        quotes = {}
    results = []
    errors = []
    for symbol in symbols:
        try:
            raw_quote = quotes.get(str(symbol).upper())
            live = parse_live_price(raw_quote) if raw_quote else None
            results.append(
                run_symbol(
                    symbol,
                    period=period,
                    count=count,
                    buy_votes_needed=buy_needed,
                    sell_votes_needed=sell_needed,
                    strategy=strategy,
                    config=config,
                    live=live,
                )
            )
        except Exception as exc:  # noqa: BLE001 — one symbol must not abort the book
            errors.append({"ticker": symbol, "error": str(exc)})
    return {
        "generated_at": now_hk_iso(),
        "data_source": "Longbridge",
        "config": {
            "symbols": symbols,
            "period": period,
            "count": count,
            "strategy": strategy,
            "buy_votes_needed": buy_needed,
            "sell_votes_needed": sell_needed,
            "qty": max(1, int(config.get("qty") or 1)),
            "budget_usd": book_budget_usd(config),
            "starting_usd": book_starting_usd(config),
            "execution": str(config.get("execution", "paper")),
            "news": _news_enabled(config, strategy),
            "sell": _sell_cfg(config) if strategy == "buy_hold" else None,
            "buy": _buy_cfg(config) if strategy == "buy_hold" else None,
        },
        "results": results,
        "errors": errors,
        "actionable": [
            row
            for row in results
            if row["final_decision"] in ("BUY", "SELL")
        ],
    }
