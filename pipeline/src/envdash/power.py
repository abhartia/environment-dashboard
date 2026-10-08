"""Annual energy as average power: a unit conversion that a transform records as one of its processing steps.

Energy delivered over a span of time, divided by the number of hours in that span, is the constant power that would
deliver the same energy over the same span: its average power. Kilowatt-hours over hours give kilowatts, gigawatt-hours
give gigawatts, terawatt-hours give terawatts. The hours are counted from the span's own dates (8,760 in a common
year, 8,784 in a leap year), never assumed, and the arithmetic is exact decimal arithmetic on the published value.

Primary energy in British thermal units is first turned into terawatt-hours with the International Table Btu, which is
defined as exactly 1,055.05585262 joules; a terawatt-hour is exactly 3.6 x 10^15 joules. EIA's own heat content of a
kilowatt-hour, 3,412.14 Btu, which envdash.transforms.energy.eia_international checks on every build, is this same
definition (3,600,000 / 1,055.05585262 = 3,412.14).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

BTU_JOULES = Decimal("1055.05585262")
"""The International Table British thermal unit, in joules (exact by definition)."""
TWH_JOULES = Decimal("3.6e15")
"""One terawatt-hour, in joules (exact)."""


def hours_between(start: date, end: date) -> int:
    """Hours from the start of `start` to the start of `end` (end exclusive)."""
    if end <= start:
        raise ValueError(f"{end} is not after {start}")
    return (end - start).days * 24


def year_hours(year: int) -> int:
    """Hours in a calendar year: 8,760, or 8,784 in a leap year."""
    return hours_between(date(year, 1, 1), date(year + 1, 1, 1))


def average_power(energy: Decimal, hours: int) -> Decimal:
    """Energy (in X-hours) over the hours of its span: average power in X (kWh -> kW, GWh -> GW, TWh -> TW)."""
    if hours <= 0:
        raise ValueError(f"{hours} hours")
    return energy / Decimal(hours)


def quad_btu_to_twh(quad_btu: Decimal) -> Decimal:
    """Quadrillion (10^15) International Table Btu in terawatt-hours."""
    return quad_btu * Decimal(10) ** 15 * BTU_JOULES / TWH_JOULES


def hours_words(hours: int) -> str:
    """'8,784 hours (366 days)'."""
    return f"{hours:,} hours ({hours // 24} days)"
