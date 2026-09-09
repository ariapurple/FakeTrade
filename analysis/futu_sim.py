"""Futu OpenD 模拟盘 fills. Always TrdEnv.SIMULATE. Never REAL. Never unlock_trade."""

from __future__ import annotations

import argparse
import json
import os
import socket
from typing import Any, Callable, Literal, assert_never

try:
    from futu import (  # type: ignore[import-untyped]
        RET_OK,
        OpenSecTradeContext,
        OrderType,
        SecurityFirm,
        Session,
        TimeInForce,
        TrdEnv,
        TrdMarket,
        TrdSide,
        ModifyOrderOp,
    )
except ImportError:  # pragma: no cover — tests inject a context factory
    RET_OK = 0
    OpenSecTradeContext = None
    OrderType = None
    SecurityFirm = None
    Session = None
    TimeInForce = None
    TrdEnv = None
    TrdMarket = None
    TrdSide = None
    ModifyOrderOp = None

Side = Literal["BUY", "SELL"]
ContextFactory = Callable[[str, int, Any, Any], Any]


class FutuSimError(RuntimeError):
    """OpenD / 模拟盘 error that is safe to show in logs."""


class OpenDDownError(FutuSimError):
    """Nothing is listening on the OpenD host:port."""


def opend_host_port() -> tuple[str, int]:
    host = os.getenv("FUTU_OPEND_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.getenv("FUTU_OPEND_PORT", "11111"))
    return host, port


def opend_up(host: str | None = None, port: int | None = None, timeout: float = 1.5) -> bool:
    resolved_host, resolved_port = opend_host_port()
    host = host or resolved_host
    port = resolved_port if port is None else port
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def to_futu_code(longbridge_symbol: str) -> str:
    """Longbridge `AAPL.US` → Futu `US.AAPL`."""
    raw = str(longbridge_symbol).strip().upper()
    if "." not in raw:
        raise FutuSimError(f"Symbol {longbridge_symbol!r} is missing a market suffix (e.g. AAPL.US).")
    ticker, market = raw.rsplit(".", 1)
    if not ticker or not market:
        raise FutuSimError(f"Cannot map {longbridge_symbol!r} to a Futu code.")
    if market in {"US", "HK", "SH", "SZ", "SG", "JP", "MY"}:
        return f"{market}.{ticker}"
    raise FutuSimError(f"Unsupported market {market} in {longbridge_symbol!r}.")


def position_notional(row: dict[str, Any]) -> float:
    """USD market value of one Futu position row."""
    for key in ("market_val", "market_value"):
        raw = row.get(key)
        if raw is None or raw == "":
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    try:
        qty = float(row.get("qty") or row.get("qty_pos") or 0)
    except (TypeError, ValueError):
        qty = 0.0
    price = 0.0
    for key in ("nominal_price", "price", "cost_price", "average_cost"):
        raw = row.get(key)
        if raw is None or raw == "":
            continue
        try:
            price = float(raw)
        except (TypeError, ValueError):
            continue
        if price > 0:
            break
    return max(0.0, qty * price)


def book_notional(positions: list[dict[str, Any]], symbols: list[str]) -> float:
    """Market value of Futu positions that belong to this book's tickers."""
    wanted: set[str] = set()
    for symbol in symbols:
        try:
            wanted.add(to_futu_code(str(symbol)).upper())
        except FutuSimError:
            continue
    if not wanted:
        return 0.0
    total = 0.0
    for row in positions:
        code = str(row.get("code") or row.get("stock_code") or "").strip().upper()
        if code in wanted:
            total += position_notional(row)
    return total


def held_qty(positions: list[dict[str, Any]], symbol: str) -> float:
    """Long qty for a Longbridge symbol in a Futu position_list_query snapshot."""
    code = to_futu_code(symbol).upper()
    total = 0.0
    for row in positions:
        row_code = str(row.get("code") or row.get("stock_code") or "").strip().upper()
        if row_code != code:
            continue
        qty_raw = row.get("qty", row.get("qty_pos", row.get("can_sell_qty")))
        try:
            qty = float(qty_raw)
        except (TypeError, ValueError):
            continue
        if qty > 0:
            total += qty
    return total


PENDING_ORDER_STATUSES = {
    "UNSUBMITTED",
    "WAITING_SUBMIT",
    "SUBMITTING",
    "SUBMITTED",
    "FILLING",
    "FILLED_PART",
    "PARTIAL",
    "CANCELLING",
    "CANCELING",
    "TIMEOUT",
}


def _order_code(row: dict[str, Any]) -> str:
    return str(row.get("code") or row.get("stock_code") or "").strip().upper()


def _order_is_open_buy(row: dict[str, Any]) -> bool:
    side = enum_name(row.get("trd_side") or row.get("side"))
    if side not in {"BUY", "BUY_BACK"}:
        return False
    status = enum_name(row.get("order_status") or row.get("status"))
    return status in PENDING_ORDER_STATUSES


def pending_buy_qty(orders: list[dict[str, Any]], symbol: str) -> float:
    """Unfilled BUY qty for a Longbridge symbol in order_list_query."""
    code = to_futu_code(symbol).upper()
    total = 0.0
    for row in orders:
        if _order_code(row) != code or not _order_is_open_buy(row):
            continue
        try:
            qty = float(row.get("qty") or 0)
            dealt = float(row.get("dealt_qty") or 0)
        except (TypeError, ValueError):
            continue
        leftover = qty - dealt
        if leftover > 0:
            total += leftover
    return total


def pending_buy_notional(orders: list[dict[str, Any]], symbols: list[str]) -> float:
    wanted: set[str] = set()
    for symbol in symbols:
        try:
            wanted.add(to_futu_code(str(symbol)).upper())
        except FutuSimError:
            continue
    total = 0.0
    for row in orders:
        if _order_code(row) not in wanted or not _order_is_open_buy(row):
            continue
        try:
            qty = float(row.get("qty") or 0)
            dealt = float(row.get("dealt_qty") or 0)
            price = float(row.get("price") or row.get("order_price") or 0)
        except (TypeError, ValueError):
            continue
        leftover = max(0.0, qty - dealt)
        if leftover > 0 and price > 0:
            total += leftover * price
    return total


def enum_name(value: Any) -> str:
    if value is None:
        return ""
    name = getattr(value, "name", None)
    if name:
        return str(name).upper()
    text = str(value).upper()
    for prefix in ("TRDENV.", "TRDMARKET.", "TRDSIDE.", "SIMACCTTYPE.", "TRDACCTYPE."):
        text = text.replace(prefix, "")
    return text.strip()


def _auth_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        cleaned = raw.strip().strip("[]")
        return [enum_name(part.strip()) for part in cleaned.split(",") if part.strip()]
    if isinstance(raw, (list, tuple)):
        return [enum_name(item) for item in raw if item is not None and str(item).strip()]
    return [enum_name(raw)]


def _rows_from_table(data: Any) -> list[dict[str, Any]]:
    if data is None:
        return []
    if hasattr(data, "to_dict"):
        records = data.to_dict(orient="records")
        return [dict(row) for row in records]
    if isinstance(data, list):
        out: list[dict[str, Any]] = []
        for item in data:
            out.append(dict(item) if not isinstance(item, dict) else item)
        return out
    if isinstance(data, dict):
        return [data]
    return []


def _is_simulate(value: Any) -> bool:
    return enum_name(value) == "SIMULATE"


def pick_simulate_account(
    accounts: list[dict[str, Any]],
    market: str,
    acc_id: int | None = None,
) -> dict[str, Any]:
    """Choose a SIMULATE stock account. Refuse REAL even if the id is explicit."""
    wanted = int(acc_id) if acc_id else 0
    if wanted:
        matches = [row for row in accounts if int(row.get("acc_id") or 0) == wanted]
        if not matches:
            raise FutuSimError(f"FUTU_SIM_ACC_ID={wanted} is not in OpenD get_acc_list.")
        chosen = matches[0]
        if not _is_simulate(chosen.get("trd_env")):
            raise FutuSimError("Refusing a REAL Futu account. This broker is SIMULATE-only.")
        return chosen

    market_key = enum_name(market)
    simulate: list[dict[str, Any]] = []
    for row in accounts:
        if not _is_simulate(row.get("trd_env")):
            continue
        if enum_name(row.get("acc_status")) in {"DISABLED", "DISABLE"}:
            continue
        simulate.append(row)
    if not simulate:
        raise FutuSimError("OpenD has no SIMULATE account. Log into 牛牛 模拟交易, then OpenD.")

    def score(row: dict[str, Any]) -> int:
        auth = _auth_list(row.get("trdmarket_auth"))
        sim_type = enum_name(row.get("sim_acc_type"))
        points = 0
        if market_key in auth or not auth:
            points += 10
        if sim_type in {"STOCK_AND_OPTION", "STOCK"}:
            points += 5
        if sim_type == "FUTURES":
            points -= 20
        if sim_type == "OPTION":
            points -= 10
        return points

    return max(simulate, key=score)


def _resolve_trd_market(market: str) -> Any:
    key = enum_name(market)
    if TrdMarket is None:
        return key
    mapping = {
        "US": TrdMarket.US,
        "HK": TrdMarket.HK,
        "SH": getattr(TrdMarket, "CN", TrdMarket.US),
        "SZ": getattr(TrdMarket, "CN", TrdMarket.US),
        "CN": getattr(TrdMarket, "CN", TrdMarket.US),
        "SG": getattr(TrdMarket, "SG", TrdMarket.US),
        "JP": getattr(TrdMarket, "JP", TrdMarket.US),
        "MY": getattr(TrdMarket, "MY", TrdMarket.US),
    }
    return mapping.get(key, TrdMarket.US)


def _resolve_firm(name: str) -> Any:
    key = enum_name(name) or "FUTUINC"
    if SecurityFirm is None:
        return key
    return getattr(SecurityFirm, key, SecurityFirm.FUTUINC)


def _firm_candidates() -> list[Any]:
    preferred = os.getenv("FUTU_SECURITY_FIRM", "FUTUINC").strip() or "FUTUINC"
    names: list[str] = []
    for name in (preferred, "FUTUINC", "FUTUSECURITIES", "NONE"):
        upper = name.upper()
        if upper not in names:
            names.append(upper)
    return [_resolve_firm(name) for name in names]


def _trd_side(side: Side) -> Any:
    if side == "BUY":
        return TrdSide.BUY if TrdSide is not None else "BUY"
    if side == "SELL":
        return TrdSide.SELL if TrdSide is not None else "SELL"
    assert_never(side)


def _simulate_env() -> Any:
    if TrdEnv is None:
        return "SIMULATE"
    env = TrdEnv.SIMULATE
    if not _is_simulate(env):
        raise FutuSimError("futu-api TrdEnv.SIMULATE is missing; refusing to place an order.")
    return env


def default_context_factory(host: str, port: int, market: Any, firm: Any) -> Any:
    if OpenSecTradeContext is None:
        raise FutuSimError("futu-api is not installed. pip install futu-api")
    return OpenSecTradeContext(
        filter_trdmarket=market,
        host=host,
        port=port,
        security_firm=firm,
    )


class FutuSimBroker:
    """One OpenD connection. place_order is hard-wired to SIMULATE."""

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        context_factory: ContextFactory | None = None,
    ) -> None:
        resolved_host, resolved_port = opend_host_port()
        self.host = host or resolved_host
        self.port = resolved_port if port is None else port
        self._factory = context_factory or default_context_factory
        self._ctx: Any = None
        self._account: dict[str, Any] | None = None
        self._firm: Any = None
        self._market: Any = None

    def connect(self, market: str = "US") -> dict[str, Any]:
        if not opend_up(self.host, self.port):
            raise OpenDDownError(
                f"OpenD is not listening on {self.host}:{self.port}. "
                "Start 富途 OpenD on this same machine (Cloud Automations cannot see your laptop)."
            )
        last_error = "no security firm returned a SIMULATE account"
        trd_market = _resolve_trd_market(market)
        for firm in _firm_candidates():
            ctx = None
            try:
                ctx = self._factory(self.host, self.port, trd_market, firm)
                ret, data = ctx.get_acc_list()
                if ret != RET_OK:
                    last_error = str(data)
                    if ctx is not None:
                        ctx.close()
                    continue
                accounts = _rows_from_table(data)
                env_acc = os.getenv("FUTU_SIM_ACC_ID", "").strip()
                acc_id = int(env_acc) if env_acc else None
                account = pick_simulate_account(accounts, market, acc_id)
                self._ctx = ctx
                self._account = account
                self._firm = firm
                self._market = trd_market
                return {
                    "host": self.host,
                    "port": self.port,
                    "security_firm": enum_name(firm) or str(firm),
                    "acc_id": int(account.get("acc_id") or 0),
                    "trd_env": "SIMULATE",
                    "sim_acc_type": enum_name(account.get("sim_acc_type")),
                    "acc_type": enum_name(account.get("acc_type")),
                    "trdmarket_auth": _auth_list(account.get("trdmarket_auth")),
                    "accounts_seen": len(accounts),
                }
            except OpenDDownError:
                raise
            except FutuSimError as exc:
                last_error = str(exc)
                if ctx is not None:
                    ctx.close()
            except Exception as exc:  # noqa: BLE001 — OpenD SDK raises mixed types
                last_error = str(exc)
                if ctx is not None:
                    try:
                        ctx.close()
                    except Exception:
                        pass
        raise FutuSimError(f"Could not open a Futu SIMULATE account via OpenD: {last_error}")

    def place_simulate(
        self,
        *,
        symbol: str,
        side: Side,
        qty: int,
        price: float,
        remark: str = "QUANTSIM",
    ) -> dict[str, Any]:
        code = to_futu_code(symbol)
        market = code.split(".", 1)[0]
        if self._ctx is None or self._account is None:
            self.connect(market)
        assert self._ctx is not None
        assert self._account is not None

        env = _simulate_env()
        payload: dict[str, Any] = {
            "price": float(price),
            "qty": int(qty),
            "code": code,
            "trd_side": _trd_side(side),
            "order_type": OrderType.NORMAL if OrderType is not None else "NORMAL",
            "adjust_limit": 0.02,
            "trd_env": env,
            "acc_id": int(self._account.get("acc_id") or 0),
            "remark": (remark or "QUANTSIM")[:64],
        }
        if TimeInForce is not None:
            payload["time_in_force"] = TimeInForce.DAY
        if Session is not None:
            payload["session"] = getattr(Session, "RTH", None) or Session.NONE
        if not _is_simulate(payload["trd_env"]):
            raise FutuSimError("Blocked a non-SIMULATE place_order.")

        ret, data = self._ctx.place_order(**payload)
        result: dict[str, Any] = {
            "ticker": symbol,
            "futu_code": code,
            "side": side,
            "qty": qty,
            "price": price,
            "trd_env": "SIMULATE",
            "acc_id": payload["acc_id"],
        }
        if ret != RET_OK:
            result["status"] = "futu-sim-failed"
            result["note"] = str(data)
            return result
        rows = _rows_from_table(data)
        first = rows[0] if rows else {}
        result["status"] = "futu-sim-submitted"
        result["order_id"] = str(first.get("order_id") or "")
        result["order_status"] = enum_name(first.get("order_status")) or str(first.get("order_status") or "")
        result["session"] = enum_name(payload.get("session")) or "NONE"
        result["dealt_qty"] = first.get("dealt_qty")
        result["note"] = "Submitted to Futu 模拟盘 (TrdEnv.SIMULATE). Not a live order."
        return result

    def funds(self) -> dict[str, Any]:
        if self._ctx is None or self._account is None:
            return {}
        ret, data = self._ctx.accinfo_query(
            trd_env=_simulate_env(),
            acc_id=int(self._account.get("acc_id") or 0),
            refresh_cache=True,
        )
        if ret != RET_OK:
            return {"error": str(data)}
        rows = _rows_from_table(data)
        return rows[0] if rows else {}

    def positions(self) -> list[dict[str, Any]]:
        if self._ctx is None or self._account is None:
            return []
        ret, data = self._ctx.position_list_query(
            trd_env=_simulate_env(),
            acc_id=int(self._account.get("acc_id") or 0),
            refresh_cache=True,
        )
        if ret != RET_OK:
            return [{"error": str(data)}]
        return _rows_from_table(data)

    def open_orders(self) -> list[dict[str, Any]]:
        if self._ctx is None or self._account is None:
            return []
        ret, data = self._ctx.order_list_query(
            trd_env=_simulate_env(),
            acc_id=int(self._account.get("acc_id") or 0),
            refresh_cache=True,
        )
        if ret != RET_OK:
            return []
        return _rows_from_table(data)

    def cancel_open_orders(self) -> list[dict[str, Any]]:
        """Cancel unfilled SIMULATE orders only. Never touches REAL."""
        if self._ctx is None or self._account is None:
            self.connect("US")
        assert self._ctx is not None
        assert self._account is not None
        env = _simulate_env()
        if not _is_simulate(env):
            raise FutuSimError("Refusing to cancel orders on a non-SIMULATE account.")
        acc_id = int(self._account.get("acc_id") or 0)
        if ModifyOrderOp is None:
            raise FutuSimError("futu-api ModifyOrderOp is missing; cannot cancel.")
        results: list[dict[str, Any]] = []
        for row in self.open_orders():
            status = enum_name(row.get("order_status") or row.get("status"))
            if status not in PENDING_ORDER_STATUSES:
                continue
            order_id = str(row.get("order_id") or "")
            if not order_id:
                continue
            ret, data = self._ctx.modify_order(
                ModifyOrderOp.CANCEL,
                order_id,
                0,
                0,
                trd_env=env,
                acc_id=acc_id,
            )
            item: dict[str, Any] = {
                "order_id": order_id,
                "code": row.get("code") or row.get("stock_code"),
                "qty": row.get("qty"),
                "price": row.get("price"),
                "trd_env": "SIMULATE",
                "acc_id": acc_id,
                "prior_status": status,
            }
            if ret != RET_OK:
                item["status"] = "cancel-failed"
                item["note"] = str(data)
            else:
                item["status"] = "cancelled"
            results.append(item)
        return results

    def close(self) -> None:
        ctx = self._ctx
        self._ctx = None
        if ctx is None:
            return
        try:
            ctx.close()
        except Exception:
            pass

    def __enter__(self) -> FutuSimBroker:
        return self

    def __exit__(self, *_exc: object) -> Literal[False]:
        self.close()
        return False


def probe() -> dict[str, Any]:
    host, port = opend_host_port()
    report: dict[str, Any] = {
        "host": host,
        "port": port,
        "opend_up": opend_up(host, port),
        "futu_api": OpenSecTradeContext is not None,
        "trd_env": "SIMULATE",
    }
    if not report["opend_up"]:
        report["ok"] = False
        report["error"] = (
            f"OpenD is down at {host}:{port}. Fake Futu fills need 牛牛 + OpenD on this machine."
        )
        return report
    broker = FutuSimBroker(host=host, port=port)
    try:
        report["account"] = broker.connect()
        report["funds"] = _public_funds(broker.funds())
        report["positions"] = broker.positions()
        report["ok"] = True
    except FutuSimError as exc:
        report["ok"] = False
        report["error"] = str(exc)
    finally:
        broker.close()
    return report


def _public_funds(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "total_assets",
        "cash",
        "us_cash",
        "hk_cash",
        "market_val",
        "currency",
        "error",
    )
    return {key: row[key] for key in keys if key in row}


def cancel_open() -> dict[str, Any]:
    host, port = opend_host_port()
    report: dict[str, Any] = {
        "host": host,
        "port": port,
        "opend_up": opend_up(host, port),
        "trd_env": "SIMULATE",
        "cancelled": [],
    }
    if not report["opend_up"]:
        report["ok"] = False
        report["error"] = f"OpenD is down at {host}:{port}."
        return report
    broker = FutuSimBroker(host=host, port=port)
    try:
        report["account"] = broker.connect()
        if str(report["account"].get("trd_env")) != "SIMULATE":
            raise FutuSimError("Refusing cancel: account is not SIMULATE.")
        report["cancelled"] = broker.cancel_open_orders()
        report["ok"] = not any(row.get("status") == "cancel-failed" for row in report["cancelled"])
    except FutuSimError as exc:
        report["ok"] = False
        report["error"] = str(exc)
    finally:
        broker.close()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe Futu OpenD 模拟盘. Never places REAL orders.")
    parser.add_argument("--check", action="store_true", help="Connect and list the SIMULATE account.")
    parser.add_argument(
        "--cancel-open",
        action="store_true",
        help="Cancel unfilled SIMULATE orders only (等待成交). Never REAL.",
    )
    args = parser.parse_args(argv)
    if args.cancel_open:
        report = cancel_open()
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return 0 if report.get("ok") else 2
    if not args.check:
        parser.print_help()
        return 2
    report = probe()
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
