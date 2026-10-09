"""Pakistan business calendar (public holidays for the data window, Eid periods)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

PKT_OFFSET = timedelta(hours=5)

# Federal public holidays, Oct 2025 - Dec 2026 (Islamic dates are the announced/expected ones).
PUBLIC_HOLIDAYS: dict[date, str] = {
    date(2025, 11, 9): "Iqbal Day",
    date(2025, 12, 25): "Quaid-e-Azam Day",
    date(2026, 2, 5): "Kashmir Solidarity Day",
    date(2026, 3, 20): "Eid ul Fitr",
    date(2026, 3, 21): "Eid ul Fitr",
    date(2026, 3, 22): "Eid ul Fitr",
    date(2026, 3, 23): "Pakistan Day",
    date(2026, 5, 1): "Labour Day",
    date(2026, 5, 27): "Eid ul Adha",
    date(2026, 5, 28): "Eid ul Adha",
    date(2026, 5, 29): "Eid ul Adha",
    date(2026, 6, 25): "Ashura",
    date(2026, 6, 26): "Ashura",
    date(2026, 8, 14): "Independence Day",
    date(2026, 8, 26): "Eid Milad-un-Nabi",
    date(2026, 11, 9): "Iqbal Day",
    date(2026, 12, 25): "Quaid-e-Azam Day",
}

EID_DAYS = [date(2026, 3, 20), date(2026, 5, 27)]


def is_holiday(d: date) -> bool:
    return d in PUBLIC_HOLIDAYS


def is_off_day(d: date) -> bool:
    """Sunday or a public holiday."""
    return d.weekday() == 6 or d in PUBLIC_HOLIDAYS


def near_eid(d: date, before: int = 14, after: int = 10) -> bool:
    return any(-before <= (d - e).days <= after for e in EID_DAYS)


def next_business_day(d: date) -> date:
    while is_off_day(d):
        d += timedelta(days=1)
    return d


def to_pkt(dt_utc: datetime) -> datetime:
    return dt_utc + PKT_OFFSET


def to_utc(dt_pkt: datetime) -> datetime:
    return dt_pkt - PKT_OFFSET
