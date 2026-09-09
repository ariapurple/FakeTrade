"""US trade-session gate: 盤前 + 盤中 + 盤後 + 夜盤.

Futu US is closed from Saturday 04:00 ET until Sunday 20:00 ET.
All other times (DST-aware America/New_York) are in-session.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Literal
from zoneinfo import ZoneInfo

US_EASTERN = ZoneInfo("America/New_York")
FRIDAY_NIGHT_ENDS_ET = time(4, 0)
SUNDAY_NIGHT_STARTS_ET = time(20, 0)
PREMARKET_START_ET = time(4, 0)
RTH_START_ET = time(9, 30)
RTH_END_ET = time(16, 0)
AFTERHOURS_END_ET = time(20, 0)

QuoteSession = Literal["pre", "rth", "post", "overnight", "closed"]


def _eastern(now: datetime | None = None) -> datetime:
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(US_EASTERN)


def in_us_trade_window(now: datetime | None = None) -> bool:
    eastern = _eastern(now)
    weekday = eastern.weekday()
    clock = eastern.time()
    if weekday == 5:
        return clock < FRIDAY_NIGHT_ENDS_ET
    if weekday == 6:
        return clock >= SUNDAY_NIGHT_STARTS_ET
    return True


def in_us_rth(now: datetime | None = None) -> bool:
    """US regular cash session: Mon-Fri 09:30-16:00 ET.

    That is 13:30-20:00 UTC while the US is on daylight time (as in September),
    and 14:30-21:00 UTC on standard time. Futu Session.NONE orders wait until this window.
    """
    eastern = _eastern(now)
    if eastern.weekday() >= 5:
        return False
    clock = eastern.time()
    return RTH_START_ET <= clock < RTH_END_ET


def should_refresh_signals(now: datetime | None = None) -> bool:
    """Day-bar SMA200 snapshots: 08:00, 09:00, RTH :00/:30, and 16:30 ET. Weekdays only."""
    if not in_us_trade_window(now):
        return False
    eastern = _eastern(now)
    if eastern.weekday() >= 5:
        return False
    if in_us_rth(now):
        return True
    clock = eastern.time()
    if time(8, 0) <= clock < time(8, 30):
        return True
    if time(9, 0) <= clock < time(9, 30):
        return True
    if time(16, 30) <= clock < time(17, 0):
        return True
    return False


def should_place_sim(now: datetime | None = None) -> bool:
    """模拟盘 fills: Mon-Fri 09:30-16:00 ET (scheduled ticks 09:30 through 15:30)."""
    return in_us_rth(now)


def us_quote_session(now: datetime | None = None) -> QuoteSession:
    """Which US tape to read: 盤前 / 盤中 / 盤後 / 夜盤."""
    if not in_us_trade_window(now):
        return "closed"
    clock = _eastern(now).time()
    weekday = _eastern(now).weekday()
    if weekday == 6:
        return "overnight"
    if weekday == 5:
        return "overnight"
    if clock < PREMARKET_START_ET:
        return "overnight"
    if clock < RTH_START_ET:
        return "pre"
    if clock < RTH_END_ET:
        return "rth"
    if clock < AFTERHOURS_END_ET:
        return "post"
    return "overnight"
