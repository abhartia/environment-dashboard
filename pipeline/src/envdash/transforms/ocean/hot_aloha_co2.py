"""Hawaii Ocean Time-series (HOT), Station ALOHA: surface seawater pH and CO2 partial pressure for every cruise since
October 1988, as published in the HOT surface CO2 system data product (J. E. Dore).

Inputs: HOT_surface_CO2.txt (tab-delimited, CRLF lines) and its readme, HOT_surface_CO2_readme.pdf.

What is published. One value per cruise, as printed: the columns pHcalc_insitu and pCO2calc_insitu. Nothing is
averaged: cruises per year vary (from 5 in 2022 to 12 in some years) and fall in different months, so a calendar-year
mean of these values would mix the trend with the season sampled. The readme defines the columns, and every build
checks that the readme still says so (READMES below, matched in the readme's text):
- pHcalc_insitu: "The mean seawater pH, calculated from DIC and TA at in situ temperature, on the total scale."
- pCO2calc_insitu: "The mean seawater CO2 partial pressure, in µatm, calculated from DIC and TA at in situ
  temperature."
- each value is the mean of the cruise's 0-30 dbar samples ("The data in this product represent mean surface (0-30
  dbar) values for each HOT cruise except where otherwise indicated."), and "Missing data points are indicated by
  -999."
Calculated pH is used rather than measured pH because measured pH starts later and has more gaps; the scope says
which one it is.

Periods. The cruise's mid-day: the column `days` ("the number of days from 1 October 1988") added to 1 October 1988.
The `date` column must name the same day (it is checked, not used), and the cruise dates must strictly increase.

Notes. The `notes` column holds one-letter codes that the readme defines (NOTE_CODES below, each checked against the
readme on every build). A cruise's codes become the observation's note in the readme's own words, except c, r and s,
which concern pH samples only and so do not bear on pH and pCO2 calculated from DIC and alkalinity. A code the
readme does not define stops the build. A -999 value becomes a null value whose reason is the -999 marker plus the
cruise's notes (all such cruises in the current file carry k, o or p: no sampling); a value on a cruise noted k, o or
p (no sampling) contradicts the file and stops the build.

Vintage. The header line "Last updated <day> <Month> <year> by J.E. Dore" (1 January 2026 for cruises 1-355, October
1988 to December 2024); the readme must carry the same line. HOT's 2025 cruises are not in this product yet (they
are preliminary data in the HOT data system), so every value here is final.

Entity. ALOHA is a station code of ours, like MLO. It needs a row in envdash/geo.py STATIONS, and so in
pipeline/geo/entities.csv (tests/test_geo.py checks every published entity); that core change is made with the
geo module, not here.

Publisher check. None: no HOT statement of a single cruise value was found. The values are regression-tested
against the file in pipeline/tests/test_ocean_hot_aloha.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from pathlib import Path

from envdash import textmatch
from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "hot-aloha"
DATA = Input(SOURCE, "hot-surface-co2")
README = Input(SOURCE, "readme")
ENTITY = "ALOHA"
EPOCH = date(1988, 10, 1)
MISSING = "-999"

COLUMNS = [
    "cruise",
    "days",
    "date",
    "temp",
    "sal",
    "phos",
    "sil",
    "DIC",
    "TA",
    "nDIC",
    "nTA",
    "pHmeas_25C",
    "pHmeas_insitu",
    "pHcalc_25C",
    "pHcalc_insitu",
    "pCO2calc_insitu",
    "pCO2calc_20C",
    "aragsatcalc_insitu",
    "calcsatcalc_insitu",
    "freeCO2_insitu",
    "carbonate_insitu",
    "notes",
]

# Notes codes, verbatim from the readme (HOT_surface_CO2_readme.pdf, last updated 1 January 2026, pages 4-5).
NOTE_CODES: dict[str, str] = {
    "a": "No HOT DIC data; used Keeling DIC",
    "b": "No HOT TA data; used Keeling TA",
    "c": "No pH samples collected",
    "d": "No TA data; assumed nTA of 2303.2",
    "e": "No DIC data in upper 30 dbar; used value from 34.0 dbar",
    "f": "No TA data in upper 30 dbar; used value from 51.3 dbar",
    "g": "Used temp and sal data from downcast before cable broke",
    "h": "No phos data; assumed 0.07",
    "i": "No sil data; assumed 1.04",
    "j": "Rosette lost; samples collected with Go-flo bottle on Kevlar line",
    "k": "No sampling occurred",
    "l": "No rosette; samples collected with Niskin bottles on Kevlar line",
    "m": "No DIC or TA data in upper 30 dbar; used values from 34.9 dbar",
    "n": "No DIC or TA data in upper 30 dbar; used values from 44.9 dbar",
    "o": "No DIC, TA or pH sampling occurred in upper 200 dbar",
    "p": "No DIC, TA or pH sampling occurred",
    "q": "10-30 dbar averages used due to transient influence of heavy rainfall on 5 dbar sample",
    "r": "No pH measured 0-200 dbar; used value from Sta.50 (WHOTS), 10.5 km from ALOHA",
    "s": "No pH samples collected from upper 1000 dbar",
}
PH_SAMPLE_ONLY = frozenset("crs")
"""Codes about pH samples (measured pH) only: not carried onto values calculated from DIC and alkalinity."""
NO_SAMPLING = frozenset("kop")

READMES = (
    "The data in this product represent mean surface (0-30 dbar) values for each HOT cruise except where otherwise "
    "indicated.",
    "Missing data points are indicated by -999.",
    "The mid-day of the cruise expressed as the number of days from 1 October 1988.",
    "The mean seawater pH, calculated from DIC and TA at in situ temperature, on the total scale.",
    "The mean seawater CO2 partial pressure, in µatm, calculated from DIC and TA at in situ temperature.",
)

UPDATED = re.compile(r"^Last updated (\d{1,2} [A-Z][a-z]+ \d{4}) by J\.E\. Dore\t*$")


class HotFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Cruise:
    cruise: int
    day: date
    values: dict[str, str]
    codes: str


def last_updated(raw: str) -> date:
    for line in raw.split("\r\n")[:8]:
        m = UPDATED.match(line)
        if m:
            return datetime.strptime(m.group(1), "%d %B %Y").date()
    raise HotFormatError("no 'Last updated <date> by J.E. Dore' line in the header")


def read_cruises(raw: str) -> list[Cruise]:
    lines = raw.split("\r\n")
    try:
        at = next(i for i, ln in enumerate(lines) if ln.startswith("cruise\t"))
    except StopIteration:
        raise HotFormatError("no column header line starting 'cruise'") from None
    if lines[at].split("\t") != COLUMNS:
        raise HotFormatError(f"columns {lines[at].split(chr(9))} != expected {COLUMNS}")
    if lines[-1] == "":
        lines = lines[:-1]
    cruises: list[Cruise] = []
    for n, line in enumerate(lines[at + 1 :], start=at + 2):
        cells = line.split("\t")
        if len(cells) != len(COLUMNS):
            raise HotFormatError(f"line {n}: {len(cells)} cells, not {len(COLUMNS)}")
        row = dict(zip(COLUMNS, cells, strict=True))
        day = EPOCH + timedelta(days=int(row["days"]))
        if datetime.strptime(row["date"], "%d-%b-%y").date() != day:
            raise HotFormatError(f"cruise {row['cruise']}: date {row['date']} is not {row['days']} days after {EPOCH}")
        unknown = sorted(set(row["notes"]) - set(NOTE_CODES))
        if unknown:
            raise HotFormatError(f"cruise {row['cruise']}: notes codes {unknown} are not defined in NOTE_CODES")
        cruises.append(Cruise(int(row["cruise"]), day, row, row["notes"]))
    if not cruises:
        raise HotFormatError("no data rows")
    for a, b in pairwise(cruises):
        if not (a.day < b.day and a.cruise < b.cruise):
            raise HotFormatError(f"cruise {b.cruise} ({b.day}) does not follow cruise {a.cruise} ({a.day})")
    return cruises


def _notes(codes: str) -> str | None:
    kept = [c for c in codes if c not in PH_SAMPLE_ONLY]
    if not kept:
        return None
    return "HOT notes for this cruise: " + " ".join(f"{NOTE_CODES[c]} (code {c})." for c in kept)


def series(cruises: list[Cruise], column: str) -> list[Observation]:
    obs: list[Observation] = []
    for c in cruises:
        text = c.values[column]
        note = _notes(c.codes)
        period = c.day.isoformat()
        if text == MISSING:
            obs.append(
                Observation(
                    entity=ENTITY,
                    period=period,
                    value=None,
                    missing_reason=f"HOT's file has {MISSING}, its missing-value marker, for cruise {c.cruise}.",
                    note=note,
                )
            )
            continue
        if set(c.codes) & NO_SAMPLING:
            raise HotFormatError(f"cruise {c.cruise} has a {column} value but is noted as not sampled ({c.codes})")
        try:
            value = Decimal(text)
        except InvalidOperation:
            raise HotFormatError(f"cruise {c.cruise}: {column} {text!r} is not a number") from None
        obs.append(Observation(entity=ENTITY, period=period, value=float(value), note=note))
    return obs


def check_readme(pdf: bytes, updated: date) -> None:
    """Stops unless the readme still defines the columns, the missing marker, the dates and every notes code as this
    module reads them, for the same edition as the data file."""
    text = "\n".join(textmatch.pdf_pages_text(pdf))
    stamp = f"Last updated {updated.day} {updated:%B %Y} by J.E. Dore."
    wanted = [stamp, *READMES, *(f"{code} {meaning}" for code, meaning in NOTE_CODES.items())]
    missing = [w for w in wanted if not textmatch.contains(text, w)]
    if missing:
        raise HotFormatError(f"the readme no longer says {missing}; re-read it before trusting these rules")


def _runner(column: str, what: str):
    def run(files: dict[str, InputFile]) -> Result:
        raw = files[DATA.key].path.read_bytes().decode("utf-8")
        updated = last_updated(raw)
        check_readme(files[README.key].path.read_bytes(), updated)
        cruises = read_cruises(raw)
        obs = series(cruises, column)
        nulls = sum(o.value is None for o in obs)
        return Result(
            observations=obs,
            vintage=updated.isoformat(),
            date_published=updated.isoformat(),
            steps=[
                f"Read HOT_surface_CO2.txt, last updated {updated.day} {updated:%B %Y} (the vintage), and checked "
                "that its readme of the same date still defines the columns, the -999 missing marker and the notes "
                "codes as read here.",
                f"Published the column {column} ({what}) for each of the {len(cruises)} cruises, {cruises[0].day} to "
                f"{cruises[-1].day}, as printed, dated by the cruise's mid-day (1 October 1988 plus the days "
                f"column). {nulls} cruises have -999 and are published as missing.",
                "Each cruise's notes codes are carried as a note in the readme's words, except c, r and s, which "
                "concern pH samples only. Nothing is averaged or filled.",
            ],
        )

    return run


def _scope(basis: str) -> Scope:
    return Scope(
        geography="Station ALOHA, open North Pacific north of Oahu, Hawaii (22°45′N, 158°00′W); one station",
        basis=basis,
    )


CO2SYS = (
    "calculated by HOT with CO2SYS from measured dissolved inorganic carbon and total alkalinity (Mehrbach et al. "
    "constants as refit by Dickson and Millero; 10 dbar pressure assumed)"
)


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    return [
        Transform(
            spec=Spec(
                id="ph.hot-aloha.surface-insitu",
                title="Seawater pH at Station ALOHA, Hawaii, each cruise",
                description="Surface seawater pH in the open North Pacific at Station ALOHA, north of Oahu, for each "
                "Hawaii Ocean Time-series cruise since October 1988. A fall in pH means the water is becoming more "
                "acidic.",
                kind="series",
                unit=Unit(code="pH", label="pH (total hydrogen-ion scale)", short="pH"),
                display=Display(decimals=3),
                scope=_scope(
                    "Mean of the cruise's 0–30 dbar samples; pH on the total scale at in situ temperature, "
                    + CO2SYS
                    + "."
                ),
                geo_coverage="global-only",
                headline_entity=ENTITY,
            ),
            inputs=(DATA, README),
            run=_runner("pHcalc_insitu", "pH calculated from DIC and alkalinity at in situ temperature, total scale"),
            module_file=here,
            validation=Validation(min_rows=355, value_range=(7.9, 8.3)),
        ),
        Transform(
            spec=Spec(
                id="pco2.hot-aloha.surface-insitu",
                title="Seawater carbon dioxide (pCO₂) at Station ALOHA, Hawaii, each cruise",
                description="Partial pressure of carbon dioxide in surface seawater at Station ALOHA, north of Oahu, "
                "for each Hawaii Ocean Time-series cruise since October 1988, in microatmospheres.",
                kind="series",
                unit=Unit(code="uatm", label="microatmospheres", short="µatm"),
                display=Display(decimals=1),
                scope=_scope(
                    "Mean of the cruise's 0–30 dbar samples; CO₂ partial pressure at in situ temperature, "
                    + CO2SYS
                    + "."
                ),
                geo_coverage="global-only",
                headline_entity=ENTITY,
            ),
            inputs=(DATA, README),
            run=_runner(
                "pCO2calc_insitu",
                "CO2 partial pressure in µatm calculated from DIC and alkalinity at in situ temperature",
            ),
            module_file=here,
            validation=Validation(min_rows=355, value_range=(250.0, 550.0)),
        ),
    ]
