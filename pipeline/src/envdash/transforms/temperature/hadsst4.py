"""HadSST.4 global annual sea-surface temperature anomaly, on the dataset's own 1961–1990 baseline.

Inputs: HadSST.<version>_annual_GLOBE.csv and HadSST.<version>_monthly_GLOBE.csv. Columns are defined in the Product
User Guide (HadSST.4.2.0.0_product_user_guide.pdf, section 3.1, read 2026-10-05): "anomaly" is the "SST anomaly
relative to 1961-1990" in K; "total_uncertainty" is the "1σ uncertainty combining all sources of uncertainty:
uncorrelated measurement error, sampling error, correlated measurement error, bias correction and coverage
uncertainties". The 95% bounds in the file cover bias uncertainty only ("accounting for bias uncertainty only"), so
they are not used as the range.

Published: the anomaly as printed, with lower and upper equal to the anomaly minus and plus total_uncertainty
(interval 1sigma; exact decimal arithmetic on the printed digits). Kelvin and degrees Celsius are the same size, so
the values are unchanged. No re-basing: 1961–1990 is HadSST's own stated baseline.

Complete years. The annual file holds complete years; each of its years must have all 12 months in the monthly file,
or the build stops. Later months in the monthly file (the current year) are not published here.

Version. The version is in both file names and must agree. The Met Office acknowledgement needs "[year of first
publication]" of that version, which the files do not carry, so FIRST_PUBLISHED lists it from the Product User Guide
(section 5.1: "HadSST.4.2.0.0 (September 2025 to present)"). An unlisted version stops the build until a person adds
it.
"""

from __future__ import annotations

import re
from collections import Counter
from decimal import Decimal
from pathlib import Path

import polars as pl

from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "hadsst4"
ANNUAL = Input(SOURCE, "global-annual")
MONTHLY = Input(SOURCE, "global-monthly")
UNCERTAINTY = [
    "total_uncertainty",
    "uncorrelated_uncertainty",
    "correlated_uncertainty",
    "bias_uncertainty",
    "coverage_uncertainty",
    "lower_bound_95pct_bias_uncertainty_range",
    "upper_bound_95pct_bias_uncertainty_range",
]
ANNUAL_COLUMNS = ["year", "anomaly", *UNCERTAINTY]
MONTHLY_COLUMNS = ["year", "month", "anomaly", *UNCERTAINTY]

FIRST_PUBLISHED: dict[str, str] = {
    # Product User Guide section 5.1, "HadSST.4.2.0.0 (September 2025 to present)".
    "4.2.0.0": "2025",
}

VERSION_IN_URL = re.compile(r"/HadSST\.(\d+\.\d+\.\d+\.\d+)_(?:annual|monthly)_GLOBE\.csv$")


class HadsstFormatError(ValueError):
    pass


def version_of(url: str | None) -> str:
    m = VERSION_IN_URL.search(url or "")
    if not m:
        raise HadsstFormatError(f"cannot read the HadSST version from {url!r}")
    return m.group(1)


def _table(raw: bytes, columns: list[str], name: str) -> pl.DataFrame:
    df = pl.read_csv(raw, infer_schema=False)
    if df.columns != columns:
        raise HadsstFormatError(f"{name}: columns {df.columns} != expected {columns}")
    return df


def month_counts(monthly_raw: bytes) -> Counter[int]:
    counts: Counter[int] = Counter()
    for y, m in _table(monthly_raw, MONTHLY_COLUMNS, "monthly").select("year", "month").iter_rows():
        if not 1 <= int(m) <= 12:
            raise HadsstFormatError(f"monthly: month {m} in {y}")
        counts[int(y)] += 1
    if any(n > 12 for n in counts.values()):
        raise HadsstFormatError("monthly: a year has more than 12 months")
    return counts


def parse(annual_raw: bytes, monthly_raw: bytes) -> list[Observation]:
    counts = month_counts(monthly_raw)
    df = _table(annual_raw, ANNUAL_COLUMNS, "annual")
    obs: list[Observation] = []
    for year, anomaly, total in df.select("year", "anomaly", "total_uncertainty").iter_rows():
        y = int(year)
        if counts.get(y, 0) != 12:
            raise HadsstFormatError(f"annual file has {y}, but the monthly file has {counts.get(y, 0)} of its months")
        a, u = Decimal(anomaly), Decimal(total)
        if u < 0:
            raise HadsstFormatError(f"{y}: negative total_uncertainty {total}")
        obs.append(
            Observation(
                entity="WLD",
                period=f"{y:04d}",
                value=float(a),
                lower=float(a - u),
                upper=float(a + u),
                interval="1sigma",
            )
        )
    return obs


def _run(files: dict[str, InputFile]) -> Result:
    a, m = files[ANNUAL.key], files[MONTHLY.key]
    version = version_of(str(a.snapshot.url) if a.snapshot.url else None)
    if version_of(str(m.snapshot.url) if m.snapshot.url else None) != version:
        raise HadsstFormatError("annual and monthly files are from different HadSST versions")
    if version not in FIRST_PUBLISHED:
        raise HadsstFormatError(
            f"HadSST.{version} has no year of first publication in FIRST_PUBLISHED; add it from the Product User Guide"
        )
    obs = parse(a.path.read_bytes(), m.path.read_bytes())
    return Result(
        observations=obs,
        vintage=version,
        year=FIRST_PUBLISHED[version],
        steps=[
            f"Read the global annual series of HadSST.{version} (sea-surface temperature anomaly in kelvin relative "
            "to 1961–1990, as published; a difference of 1 K equals 1 °C, so the values are unchanged). The file "
            f"holds complete years, {obs[0].period} to {obs[-1].period}; each was confirmed to have all 12 months in "
            "the global monthly file.",
            "Lower and upper are the anomaly minus and plus the file's total_uncertainty, which the Product User "
            "Guide defines as the 1σ uncertainty combining uncorrelated measurement, sampling, correlated "
            "measurement, bias-correction and coverage uncertainties. The file's 95% bounds cover bias uncertainty "
            "only and are not used.",
        ],
        changes="range shown as the anomaly minus and plus the published total uncertainty (one standard deviation).",
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="sst.hadsst4.annual-1961-1990",
                title="Global sea-surface temperature against 1961–1990 (HadSST4)",
                description="Global mean sea-surface temperature for each complete year since 1850, from ship and "
                "buoy measurements, as the difference from the 1961–1990 average, with a one-standard-deviation "
                "range.",
                kind="series",
                unit=Unit(code="degC", label="degrees Celsius", short="°C"),
                display=Display(decimals=2),
                scope=Scope(
                    geography="Global ocean, averaged over 5° grid boxes that have measurements (not interpolated)",
                    baseline="1961–1990, the dataset's own baseline (as published)",
                    basis="In situ sea-surface temperature from ships and buoys, adjusted for changes in how it was "
                    "measured.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(ANNUAL, MONTHLY),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=170, value_range=(-1.5, 2.0)),
        )
    ]
