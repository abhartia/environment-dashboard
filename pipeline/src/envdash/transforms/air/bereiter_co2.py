"""Antarctic ice-core CO2 composite, 805,669 years ago to 2001 (Bereiter et al. 2015), dated in years before 1950.

Input: antarctica2015co2composite-noaa.txt (NOAA template v4; '#' header, then tab-separated, CRLF lines):
age_gas_calBP (gas age in calendar years before 1950, printed with two decimals, from -51.03 to 805668.87), co2_ppm
and co2_1s_ppm (one standard deviation; the header says "Where no individual sigma is given we use average for
system/record"). 1,901 samples, ages strictly increasing, i.e. the file runs backwards in time.

Time axis. The ages cannot be written as ISO calendar periods without changing them: 1,648 samples are older than
1 CE, and the Common Era samples have fractional ages (two in 1983) that would collide as calendar years. So both
indicators use the contract's time_basis "years-before-1950": each observation carries `age_bp`, the gas age exactly
as printed, and no period. Observations are published oldest first (the reverse of the file's order) so that time
runs forward as in every other series; nothing else about a sample changes.

Two indicators, in this one module so its sha256 covers both:

- co2.bereiter-2015.800k: every sample as printed, with value ± its published one standard deviation as the range
  (exact decimal arithmetic on the printed digits). Entity ANT_ICECORES: the composite is stitched from several
  Antarctic cores (Law Dome, Dome C, WAIS Divide, Siple Dome, Talos Dome, EDML, Vostok), so it is not one site.
- co2.bereiter-2015.800k.max-before-1000bp: the highest CO2 value among the samples older than 1,000 years before
  1950 (before 950 CE, so well before the industrial era), with that sample's age and standard deviation. This is the
  composite's pre-industrial maximum that the site compares today's CO2 with ("highest in 800,000 years"); the site
  shows the comparison next to NOAA's own value and never blends the two sources. A tie for the maximum stops the
  build rather than pick a sample. On the snapshot of 4 October 2026 it is 298.60 ppm at 335,102.31 years before 1950
  (docs/research/sources-atmosphere-and-temperature.json, verified independently by an awk scan of the same file).

`read_composite` checks the header statements that decide how the file is read; if any changes, the build stops.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "bereiter-2015-co2"
COMPOSITE = Input(SOURCE, "composite")
COLUMNS = ["age_gas_calBP", "co2_ppm", "co2_1s_ppm"]
REQUIRED = (
    "Age unit is in years before present (yr BP) where present refers to 1950 AD",
    "## co2_1s_ppm\tcarbon dioxide,bulk atmosphere,one standard deviation,parts per million",
    "## co2_ppm\tcarbon dioxide,bulk atmosphere,,parts per million",
    "Time_Unit: cal yr BP",
)
CONTRIBUTION_DATE = re.compile(r"^# Contribution_Date\s*\n#\s+Date: (\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)
ENTITY = "ANT_ICECORES"
PREINDUSTRIAL_MIN_AGE = Decimal(1000)
"""Samples older than this many years before 1950 (before 950 CE) count for the pre-industrial maximum."""

PPM = Unit(code="ppm", label="parts per million", short="ppm")
SCOPE_BASIS = (
    "Carbon dioxide in air trapped in Antarctic ice, by gas age (AICC2012 chronology except Law Dome, WAIS and Siple "
    "Dome). Composite stitched by the producers from Law Dome (the most recent 2,000 years), Dome C, WAIS Divide "
    "(lowered by 4 ppm by the producers), Siple Dome, Talos Dome, EDML, Dome C sublimation, Vostok and Dome C. Ice "
    "smooths the air record over decades to centuries, so short peaks do not show. Range: ± one standard deviation "
    "as published (an average for the system or record where a sample has none of its own)."
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


def contribution_date(raw: str) -> str:
    """The header's Contribution_Date (the dataset's publication date at NCEI), e.g. 2015-02-04."""
    m = CONTRIBUTION_DATE.search(raw.replace("\r\n", "\n"))
    if not m:
        raise BereiterFormatError("no '# Contribution_Date' / '#   Date: YYYY-MM-DD' lines in the header")
    return m.group(1)


def observation(s: Sample) -> Observation:
    return Observation(
        entity=ENTITY,
        age_bp=float(s.age_bp),
        value=float(s.co2_ppm),
        lower=float(s.co2_ppm - s.sigma_ppm),
        upper=float(s.co2_ppm + s.sigma_ppm),
        interval="1sigma",
    )


def preindustrial_max(samples: list[Sample]) -> tuple[Sample, int]:
    """The sample with the highest CO2 among those older than PREINDUSTRIAL_MIN_AGE, and how many were compared."""
    older = [s for s in samples if s.age_bp > PREINDUSTRIAL_MIN_AGE]
    if not older:
        raise BereiterFormatError(f"no sample older than {PREINDUSTRIAL_MIN_AGE} years before 1950")
    top = max(s.co2_ppm for s in older)
    hits = [s for s in older if s.co2_ppm == top]
    if len(hits) != 1:
        ages = ", ".join(str(s.age_bp) for s in hits)
        raise BereiterFormatError(f"{len(hits)} samples share the maximum {top} ppm (ages {ages}); not choosing one")
    return hits[0], len(older)


def _read(files: dict[str, InputFile]) -> tuple[str, list[Sample], str]:
    raw = files[COMPOSITE.key].path.read_bytes().decode("utf-8")
    return raw, read_composite(raw), contribution_date(raw)


def _series(files: dict[str, InputFile]) -> Result:
    _, samples, contributed = _read(files)
    obs = [observation(s) for s in reversed(samples)]
    return Result(
        observations=obs,
        vintage=contributed,
        date_published=contributed,
        steps=[
            f"Read all {len(samples):,} samples of antarctica2015co2composite-noaa.txt (NOAA template v4, contributed "
            f"{contributed}): gas age in calendar years before 1950 (age_gas_calBP), carbon dioxide in parts per "
            "million (co2_ppm) and its one standard deviation (co2_1s_ppm), each as printed.",
            "Published each sample's gas age as age_bp, unrounded, with no calendar period (time basis "
            f"years-before-1950), from the oldest ({samples[-1].age_bp}) to the youngest ({samples[0].age_bp}); the "
            "file lists them youngest first.",
            "Range: value minus and plus the published one standard deviation (exact decimal arithmetic on the printed "
            "digits). The file's header says that where a sample has no sigma of its own, the average for the "
            "system or record is given.",
        ],
    )


def _max(files: dict[str, InputFile]) -> Result:
    _, samples, contributed = _read(files)
    top, compared = preindustrial_max(samples)
    return Result(
        observations=[observation(top)],
        vintage=contributed,
        date_published=contributed,
        steps=[
            f"Read all {len(samples):,} samples of antarctica2015co2composite-noaa.txt (contributed {contributed}), as "
            "for co2.bereiter-2015.800k.",
            f"Kept the {compared:,} samples with a gas age above {PREINDUSTRIAL_MIN_AGE:,} years before 1950 (before "
            f"950 CE) and took the one with the highest co2_ppm: {top.co2_ppm} ppm at {top.age_bp} years before 1950, "
            f"one standard deviation {top.sigma_ppm} ppm. No other sample has that value. The value, age and standard "
            "deviation are published as printed; the range is value ± one standard deviation.",
        ],
        changes="selected the highest carbon dioxide value among the samples older than 1,000 years before 1950.",
    )


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    return [
        Transform(
            spec=Spec(
                id="co2.bereiter-2015.800k",
                title="Carbon dioxide over the last 800,000 years (Antarctic ice cores)",
                description="Carbon dioxide in air trapped in Antarctic ice, from 805,669 years before 1950 to 2001, "
                "as the composite record of Bereiter et al. (2015). Each value is one ice or firn sample, dated by "
                "the age of its air in years before 1950, with one standard deviation.",
                kind="series",
                unit=PPM,
                display=Display(decimals=1),
                scope=Scope(geography="Antarctica (composite of several ice cores)", basis=SCOPE_BASIS),
                geo_coverage="global-only",
                headline_entity=ENTITY,
                time_basis="years-before-1950",
            ),
            inputs=(COMPOSITE,),
            run=_series,
            module_file=here,
            validation=Validation(min_rows=1900, value_range=(150.0, 400.0)),
        ),
        Transform(
            spec=Spec(
                id="co2.bereiter-2015.800k.max-before-1000bp",
                title="Highest carbon dioxide in Antarctic ice before the industrial era",
                description="The highest carbon dioxide value in the 800,000-year Antarctic ice-core composite of "
                "Bereiter et al. (2015) among the samples older than 1,000 years before 1950 (before 950 CE), with "
                "the age of that sample's air and its one standard deviation. Today's carbon dioxide, measured "
                "directly in the air, can be compared with it.",
                kind="derived",
                unit=PPM,
                display=Display(decimals=1),
                scope=Scope(
                    geography="Antarctica (composite of several ice cores)",
                    basis="Maximum of co2_ppm over every sample of the composite with a gas age above 1,000 years "
                    "before 1950. " + SCOPE_BASIS,
                ),
                geo_coverage="global-only",
                headline_entity=ENTITY,
                time_basis="years-before-1950",
            ),
            inputs=(COMPOSITE,),
            run=_max,
            module_file=here,
            validation=Validation(min_rows=1, value_range=(150.0, 400.0)),
        ),
    ]
