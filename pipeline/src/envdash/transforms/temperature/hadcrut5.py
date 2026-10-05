"""HadCRUT5 global annual temperature anomaly, re-based to the dataset's own 1850–1900 mean.

Inputs: the global annual and global monthly summary series of the HadCRUT5 analysis (ensemble means, anomalies in
°C relative to 1961–1990, with the 2.5% and 97.5% limits of the 95% range).

Version. The version is in the file name and URL (".../HadCRUT.5.2.0.0/.../HadCRUT.5.2.0.0.analysis..."); both
inputs must agree. The Met Office acknowledgement needs the year of first publication of that version, which the
files do not carry, so each version's release date is listed in RELEASED below from the landing page. An unlisted
version stops the build until a person adds it.

Partial year. The annual file includes the current year as an average of the months so far (2026 in the files of
September 2026). A year is published only when the monthly file has all 12 of its months; the one later year, which
must have between 1 and 11 months in the monthly file, is excluded. Anything else stops the build.

Re-basing. The baseline is the mean of the 51 annual anomalies 1850–1900 of the same file (exact decimal
arithmetic on the printed digits). It is subtracted from every anomaly and from both limits, and recorded in the
processing step. The 95% range is the published range shifted, not a re-estimate.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl

from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, PublisherCheck, Result, Spec, Transform, Validation

SOURCE = "hadcrut5"
ANNUAL = Input(SOURCE, "global-annual")
MONTHLY = Input(SOURCE, "global-monthly")
COLUMNS = ["Time", "Anomaly (deg C)", "Lower confidence limit (2.5%)", "Upper confidence limit (97.5%)"]
BASELINE = (1850, 1900)

RELEASED: dict[str, date] = {
    # https://www.metoffice.gov.uk/hadobs/hadcrut5/ (read 2026-10-04): "Data set version updated to HadCRUT.5.2.0.0
    # on 18/09/2026".
    "5.2.0.0": date(2026, 9, 18),
}

VERSION_IN_URL = re.compile(r"/HadCRUT\.(\d+\.\d+\.\d+\.\d+)/.*HadCRUT\.(\d+\.\d+\.\d+\.\d+)\.analysis\.")


class HadcrutFormatError(ValueError):
    pass


def version_of(url: str | None) -> str:
    m = VERSION_IN_URL.search(url or "")
    if not m or m.group(1) != m.group(2):
        raise HadcrutFormatError(f"cannot read one HadCRUT version from {url!r}")
    return m.group(1)


def read_series(raw: bytes, name: str) -> list[tuple[str, Decimal, Decimal, Decimal]]:
    df = pl.read_csv(raw, infer_schema=False)
    if df.columns != COLUMNS:
        raise HadcrutFormatError(f"{name}: columns {df.columns} != expected {COLUMNS}")
    return [(r[0], Decimal(r[1]), Decimal(r[2]), Decimal(r[3])) for r in df.iter_rows()]


def complete_years(monthly: list[tuple[str, Decimal, Decimal, Decimal]]) -> tuple[set[int], Counter[int]]:
    counts: Counter[int] = Counter()
    for t, *_ in monthly:
        if not re.fullmatch(r"\d{4}-\d{2}", t):
            raise HadcrutFormatError(f"monthly Time {t!r} is not YYYY-MM")
        counts[int(t[:4])] += 1
    if any(n > 12 for n in counts.values()):
        raise HadcrutFormatError("a year has more than 12 months in the monthly file")
    return {y for y, n in counts.items() if n == 12}, counts


def rebase(annual_raw: bytes, monthly_raw: bytes) -> tuple[list[Observation], Decimal, int | None, int]:
    """Returns (observations, baseline offset, excluded partial year or None, months present in that year)."""
    annual = read_series(annual_raw, "annual")
    monthly = read_series(monthly_raw, "monthly")
    complete, counts = complete_years(monthly)
    years = [int(t) for t, *_ in annual]
    last_complete = max(complete)
    later = [y for y in years if y > last_complete]
    excluded: int | None = None
    if later:
        if len(later) != 1 or not (1 <= counts.get(later[0], 0) <= 11):
            raise HadcrutFormatError(
                f"annual years after the last complete year {last_complete}: {later} with months "
                f"{[counts.get(y, 0) for y in later]}; expected one partial year"
            )
        excluded = later[0]
    base = [a for (t, a, _, _) in annual if BASELINE[0] <= int(t) <= BASELINE[1]]
    if len(base) != BASELINE[1] - BASELINE[0] + 1:
        raise HadcrutFormatError(f"expected {BASELINE[1] - BASELINE[0] + 1} baseline years, found {len(base)}")
    offset = sum(base, Decimal(0)) / Decimal(len(base))
    obs = [
        Observation(
            entity="WLD",
            period=f"{int(t):04d}",
            value=float(a - offset),
            lower=float(lo - offset),
            upper=float(hi - offset),
            interval="95ci",
        )
        for (t, a, lo, hi) in annual
        if int(t) != excluded
    ]
    return obs, offset, excluded, counts.get(excluded, 0) if excluded else 0


def _run(files: dict[str, InputFile]) -> Result:
    a, m = files[ANNUAL.key], files[MONTHLY.key]
    version = version_of(str(a.snapshot.url) if a.snapshot.url else None)
    if version_of(str(m.snapshot.url) if m.snapshot.url else None) != version:
        raise HadcrutFormatError("annual and monthly files are from different HadCRUT versions")
    if version not in RELEASED:
        raise HadcrutFormatError(f"HadCRUT.{version} has no release date in RELEASED; add it from the landing page")
    obs, offset, excluded, months = rebase(a.path.read_bytes(), m.path.read_bytes())
    steps = [
        f"Read the global annual and global monthly summary series of HadCRUT.{version} (analysis ensemble means; "
        "anomalies relative to 1961–1990 with the 2.5% and 97.5% limits).",
    ]
    if excluded is not None:
        steps.append(
            f"Excluded {excluded}: the monthly file has {months} of its 12 months, so the annual file's value for it "
            "is a partial-year average. A year is published only when all 12 months are in the monthly file."
        )
    steps.append(
        "Re-based to the dataset's own 1850–1900 mean: subtracted the mean of the 51 annual anomalies 1850–1900, "
        f"{float(offset)!r} °C relative to 1961–1990 (exact decimal arithmetic on the printed values), from every "
        "anomaly and from both limits of the 95% range."
    )
    return Result(
        observations=obs,
        vintage=version,
        year=str(RELEASED[version].year),
        date_published=RELEASED[version].isoformat(),
        steps=steps,
        changes="anomalies and their 95% range re-based from 1961–1990 to the 1850–1900 mean of the same dataset"
        + (f"; {excluded} left out as a partial year." if excluded is not None else "."),
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="temp.hadcrut5.annual-1850-1900",
                title="Global surface temperature above 1850–1900 (HadCRUT5)",
                description="Global mean near-surface temperature for each complete year since 1850, as the "
                "difference from the 1850–1900 average of the same dataset, with the 95% range.",
                kind="series",
                unit=Unit(code="degC", label="degrees Celsius", short="°C"),
                display=Display(decimals=2),
                scope=Scope(
                    geography="Global mean",
                    baseline="1850–1900 mean of this dataset",
                    basis="Blend of land air temperature (CRUTEM5) and sea-surface temperature (HadSST4), with "
                    "statistical infilling of data-sparse regions (HadCRUT5 analysis).",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(ANNUAL, MONTHLY),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=170, value_range=(-1.5, 3.5)),
            checks=(
                # No Met Office or CRU statement tied to HadCRUT.5.2.0.0 was found (searched 2026-10-04). The
                # statement below is dated January 2026, before 5.2.0.0 was released on 18 September 2026, when
                # HadCRUT.5.1.0.0 was the current version; the page does not name the version. It is kept so the
                # check runs if that vintage is ever rebuilt, and is reported as not applicable for 5.2.0.0.
                PublisherCheck(
                    source_id=SOURCE,
                    vintage="5.1.0.0",
                    entity="WLD",
                    period="2025",
                    stated="1.41",
                    quote="2025 was 1.41 (uncertainty range 1.32 to 1.49) °C above the 1850 to 1900 baseline",
                    url="https://crudata.uea.ac.uk/cru/data/t2025/",
                ),
            ),
        )
    ]
