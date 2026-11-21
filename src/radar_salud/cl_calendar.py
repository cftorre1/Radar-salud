"""Chilean business days (Dirección 21-nov-2026: «Los días hábiles debes poder calcularlos»).

A business day («día hábil») is any day that is not a Saturday, a Sunday or a national holiday (Ley 19.880 art. 25).
Holidays are listed per year from the official calendar; a term that reaches a year not listed here is not computed
(``None``) rather than guessed. Regional holidays (Arica 7-jun, Chillán 20-ago) are not national and are not listed.

Sources: 2025–2026, calendario oficial publicado (24horas.cl, «Calendario 2026 oficial»); 2027, calendario proyectado
(calendariochile.com) with the indigenous peoples' day on the winter solstice (21-jun-2027, Chile time). Update the
list when the 2027 decree and the 2028 calendar are published.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

HOLIDAYS: dict[int, frozenset[str]] = {
    2025: frozenset({"2025-01-01", "2025-04-18", "2025-04-19", "2025-05-01", "2025-05-21", "2025-06-20", "2025-06-29",
                     "2025-07-16", "2025-08-15", "2025-09-18", "2025-09-19", "2025-10-12", "2025-10-31", "2025-11-01",
                     "2025-11-16", "2025-12-08", "2025-12-14", "2025-12-25"}),
    2026: frozenset({"2026-01-01", "2026-04-03", "2026-04-04", "2026-05-01", "2026-05-21", "2026-06-21", "2026-06-29",
                     "2026-07-16", "2026-08-15", "2026-09-18", "2026-09-19", "2026-10-12", "2026-10-31", "2026-11-01",
                     "2026-12-08", "2026-12-25"}),
    2027: frozenset({"2027-01-01", "2027-03-26", "2027-03-27", "2027-05-01", "2027-05-21", "2027-06-21", "2027-06-28",
                     "2027-07-16", "2027-08-15", "2027-09-18", "2027-09-19", "2027-10-11", "2027-10-31", "2027-11-01",
                     "2027-12-08", "2027-12-25"}),
}


def is_business_day(d: date) -> bool | None:
    """None when the year's holidays are not known."""
    hol = HOLIDAYS.get(d.year)
    if hol is None:
        return None
    return d.weekday() < 5 and d.isoformat() not in hol


def add_business_days(base: date, n: int) -> date | None:
    """The n-th business day after ``base`` (``base`` itself never counts). None outside the known calendar."""
    d, left = base, n
    while left > 0:
        d += timedelta(days=1)
        ok = is_business_day(d)
        if ok is None:
            return None
        left -= 1 if ok else 0
    return d


def add_months(base: date, months: int) -> date:
    y, mo = divmod(base.month - 1 + months, 12)
    y, mo = base.year + y, mo + 1
    return date(y, mo, min(base.day, calendar.monthrange(y, mo)[1]))


def add_term(base: date, n: int, unit: str, business: bool = False) -> date | None:
    """«n días [hábiles]», «n meses», «n años», «n horas» counted from ``base``. Hours are a per-case term: None."""
    u = unit.lower()
    if u.startswith("d"):
        return add_business_days(base, n) if business else base + timedelta(days=n)
    if u.startswith("m"):
        return add_months(base, n)
    if u.startswith("a"):
        return add_months(base, 12 * n)
    return None
