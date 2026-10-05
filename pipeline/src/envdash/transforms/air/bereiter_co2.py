"""Antarctic ice-core CO2 composite, 805,669 years ago to 2001 (Bereiter et al. 2015): reader only, no indicator yet.

Input: antarctica2015co2composite-noaa.txt (NOAA template v4; '#' header, then tab-separated, CRLF lines):
age_gas_calBP (gas age in calendar years before 1950, printed with two decimals, from -51.03 to 805668.87), co2_ppm
and co2_1s_ppm (one standard deviation; the header says "Where no individual sigma is given we use average for
system/record"). 1,901 samples, ages strictly increasing, i.e. the file runs backwards in time.

Why there is no indicator. The data contract's Period is an ISO calendar year, month or date with four-digit years
(0001-9999). These ages cannot be written as such without changing them:
- 1,648 of the 1,901 samples are older than 1 CE (age above 1949), down to 805,669 years ago;
- ages are fractional (e.g. -33.08 and -33.03, two samples in 1983), so even the 253 Common Era samples would have to
  be rounded to years, giving 59 duplicate years that the contract rejects; dropping or averaging them would be our
  own reduction of the producer's data;
- a fixed sentinel period with the age in a dimension would publish a false date on every value.
So `transforms()` returns nothing until the contract can carry a gas age as published (the proposed model change is
recorded with the work order that asked for co2.bereiter-2015.800k). `read_composite` is the reader that indicator
will use; its header checks are the conditions for reading the file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from envdash.paths import Paths
from envdash.transform import Input, Transform

SOURCE = "bereiter-2015-co2"
COMPOSITE = Input(SOURCE, "composite")
COLUMNS = ["age_gas_calBP", "co2_ppm", "co2_1s_ppm"]
REQUIRED = (
    "Age unit is in years before present (yr BP) where present refers to 1950 AD",
    "## co2_1s_ppm\tcarbon dioxide,bulk atmosphere,one standard deviation,parts per million",
    "## co2_ppm\tcarbon dioxide,bulk atmosphere,,parts per million",
    "Time_Unit: cal yr BP",
)


class BereiterFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Sample:
    age_bp: Decimal
    """Gas age in years before 1950, as printed."""
    co2_ppm: Decimal
    sigma_ppm: Decimal
    """One standard deviation."""


def read_composite(raw: str) -> list[Sample]:
    lines = raw.splitlines()
    header = "\n".join(ln for ln in lines if ln.startswith("#"))
    for s in REQUIRED:
        if s not in header:
            raise BereiterFormatError(f"header no longer says {s!r}; re-read the file before trusting these rules")
    body = [ln for ln in lines if ln and not ln.startswith("#")]
    if not body or body[0].split("\t") != COLUMNS:
        raise BereiterFormatError(f"column header {body[0] if body else None!r} != {COLUMNS}")
    out: list[Sample] = []
    for n, ln in enumerate(body[1:], start=1):
        cells = ln.split("\t")
        if len(cells) != 3 or not all(re.fullmatch(r"-?\d+\.\d+", c) for c in cells):
            raise BereiterFormatError(f"data row {n}: {ln!r} is not three decimal numbers")
        s = Sample(Decimal(cells[0]), Decimal(cells[1]), Decimal(cells[2]))
        if out and s.age_bp <= out[-1].age_bp:
            raise BereiterFormatError(f"data row {n}: age {s.age_bp} does not follow {out[-1].age_bp}")
        out.append(s)
    return out


def transforms(paths: Paths) -> list[Transform]:
    return []
