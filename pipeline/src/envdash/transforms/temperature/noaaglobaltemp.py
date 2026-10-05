"""NOAAGlobalTemp v6.1 global annual land-ocean temperature anomaly, re-based to the dataset's own 1850–1900 mean.

Inputs (NCEI's areal-average time series, whitespace columns, anomalies in kelvin relative to 1991–2020 at six
decimals; every error-variance column is -999):
- aravg.ann.land_ocean.90S.90N.v6.1.0.<yyyymm>.asc, global annual: year, anomaly, four error variances;
- aravg.mon.land_ocean.90S.90N.v6.1.0.<yyyymm>.asc, global monthly: year, month, anomaly, ...;
- aravg.ann.land_ocean.60N.90N.v6.1.0.<yyyymm>.asc, read only to confirm it belongs to the same release;
- 00_Readme_timeseries.txt, which defines the columns and states the baseline.

One release. NCEI keeps only the current set and names each file by "yyyymm=date for the latest data" (readme). The
three files are found independently by `discover`, so a fetch during NCEI's monthly swap could mix releases. The
three URLs must carry the same version and yyyymm, and the monthly file's last month must be that yyyymm; anything
else stops the build.

Partial year. The annual file includes the current year as an average of the months so far. When yyyymm is not a
December, its year is left out. The annual file's years must run without a gap up to yyyymm's year, and the monthly
file must hold exactly yyyymm's months of that year.

Re-basing. The baseline is the mean of the 51 annual anomalies 1850–1900 of the same annual file (exact decimal
arithmetic on the printed digits), subtracted from every year. The readme's statement that "anomalies are based on
the climatology from 1991 to 2020" must still be there, or the build stops for a person to re-read it.
"""

from __future__ import annotations

import re
from collections import Counter
from decimal import Decimal
from pathlib import Path

from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "noaaglobaltemp-v6"
ANNUAL = Input(SOURCE, "global-annual")
MONTHLY = Input(SOURCE, "global-monthly")
ARCTIC = Input(SOURCE, "arctic-annual")
README = Input(SOURCE, "timeseries-readme")
BASELINE = (1850, 1900)

FILE_NAME = re.compile(
    r"/aravg\.(?P<freq>ann|mon)\.land_ocean\.(?P<region>90S\.90N|60N\.90N)\.v(?P<version>\d+\.\d+\.\d+)\."
    r"(?P<yyyymm>\d{6})\.asc$"
)
README_REQUIRED = (
    "yyyymm=date for the latest data",
    "2nd column = anomaly of temperature (K)",
    "3rd column = anomaly of temperature (K)",
    "anomalies are based on the climatology from 1991 to 2020",
)


class NoaaGlobalTempFormatError(ValueError):
    pass


def release_of(urls: dict[str, str | None]) -> tuple[str, str]:
    """(version, yyyymm) shared by every file name; urls maps a label (for errors) to the snapshot URL."""
    found: dict[str, tuple[str, str]] = {}
    for label, url in urls.items():
        m = FILE_NAME.search(url or "")
        if not m:
            raise NoaaGlobalTempFormatError(f"{label}: cannot read version and yyyymm from {url!r}")
        found[label] = (m.group("version"), m.group("yyyymm"))
    if len(set(found.values())) != 1:
        raise NoaaGlobalTempFormatError(f"the files are from different releases: {found}")
    return next(iter(found.values()))


def check_readme(text: str) -> None:
    flat = re.sub(r"\s+", " ", text)
    for s in README_REQUIRED:
        if s not in flat:
            raise NoaaGlobalTempFormatError(f"readme no longer says {s!r}; re-read it before trusting these rules")


def _rows(raw: bytes, ncols: int, name: str) -> list[list[str]]:
    rows = [ln.split() for ln in raw.decode("ascii").splitlines() if ln.strip()]
    for r in rows:
        if len(r) != ncols:
            raise NoaaGlobalTempFormatError(f"{name}: expected {ncols} columns, got {r}")
    return rows


def read_annual(raw: bytes) -> list[tuple[int, Decimal]]:
    return [(int(r[0]), Decimal(r[1])) for r in _rows(raw, 6, "annual")]


def month_counts(raw: bytes) -> tuple[Counter[int], str]:
    """Months per year in the monthly file, and its last month as yyyymm."""
    counts: Counter[int] = Counter()
    last = ""
    for r in _rows(raw, 10, "monthly"):
        y, m = int(r[0]), int(r[1])
        if not 1 <= m <= 12:
            raise NoaaGlobalTempFormatError(f"monthly: month {m} in {y}")
        counts[y] += 1
        last = f"{y:04d}{m:02d}"
    if any(n > 12 for n in counts.values()):
        raise NoaaGlobalTempFormatError("monthly: a year has more than 12 months")
    return counts, last


def rebase(annual_raw: bytes, monthly_raw: bytes, yyyymm: str) -> tuple[list[Observation], Decimal, int | None, int]:
    """Returns (observations, 1850–1900 mean, left-out partial year or None, months present in that year)."""
    annual = read_annual(annual_raw)
    counts, last = month_counts(monthly_raw)
    if last != yyyymm:
        raise NoaaGlobalTempFormatError(f"monthly file ends at {last}, but the file names say {yyyymm}")
    last_year, last_month = int(yyyymm[:4]), int(yyyymm[4:])
    excluded = last_year if last_month < 12 else None
    years = [y for y, _ in annual]
    if years != list(range(years[0], years[-1] + 1)) or years[-1] != last_year:
        raise NoaaGlobalTempFormatError(f"annual years {years[0]}–{years[-1]} are not consecutive up to {last_year}")
    if counts.get(last_year, 0) != last_month:
        raise NoaaGlobalTempFormatError(
            f"monthly file has {counts.get(last_year, 0)} months of {last_year}, but the file names say {yyyymm}"
        )
    base = [a for y, a in annual if BASELINE[0] <= y <= BASELINE[1]]
    if len(base) != BASELINE[1] - BASELINE[0] + 1:
        raise NoaaGlobalTempFormatError(f"expected {BASELINE[1] - BASELINE[0] + 1} baseline years, found {len(base)}")
    offset = sum(base, Decimal(0)) / Decimal(len(base))
    obs = [Observation(entity="WLD", period=f"{y:04d}", value=float(a - offset)) for y, a in annual if y != excluded]
    return obs, offset, excluded, (last_month if excluded is not None else 0)


def _run(files: dict[str, InputFile]) -> Result:
    a, m, arc, rd = (files[i.key] for i in (ANNUAL, MONTHLY, ARCTIC, README))
    version, yyyymm = release_of(
        {
            "global-annual": str(a.snapshot.url) if a.snapshot.url else None,
            "global-monthly": str(m.snapshot.url) if m.snapshot.url else None,
            "arctic-annual": str(arc.snapshot.url) if arc.snapshot.url else None,
        }
    )
    check_readme(rd.path.read_text(encoding="ascii"))
    obs, offset, excluded, months = rebase(a.path.read_bytes(), m.path.read_bytes(), yyyymm)
    steps = [
        f"Read the global (90°S–90°N) annual land-ocean anomaly of NOAAGlobalTemp v{version}, release {yyyymm} "
        "(kelvin relative to 1991–2020, as the readme states; a difference of 1 K equals 1 °C). The error-variance "
        "columns are all -999 and are not used.",
        f"Confirmed one release: the global annual, global monthly and 60°N–90°N annual file names all carry "
        f"v{version}.{yyyymm}, and the monthly file's last month is {yyyymm[:4]}-{yyyymm[4:]}.",
    ]
    if excluded is not None:
        steps.append(
            f"Left out {excluded}: the release runs to month {months} of {excluded}, so the annual file's value for "
            "it averages only those months. Earlier years are complete: the file names give the month of the "
            "latest data."
        )
    steps.append(
        "Re-based to the dataset's own 1850–1900 mean: subtracted the mean of the 51 annual anomalies 1850–1900, "
        f"{float(offset)!r} K relative to 1991–2020 (exact decimal arithmetic on the printed values), from every year."
    )
    return Result(
        observations=obs,
        vintage=f"{version}.{yyyymm}",
        steps=steps,
        changes="annual anomalies re-based from 1991–2020 to the 1850–1900 mean of the same dataset"
        + (f"; {excluded} left out as a partial year." if excluded is not None else "."),
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="temp.noaaglobaltemp-v6.annual-1850-1900",
                title="Global surface temperature above 1850–1900 (NOAAGlobalTemp)",
                description="Global mean surface temperature for each complete year since 1850, as the difference "
                "from the 1850–1900 average of the same dataset.",
                kind="series",
                unit=Unit(code="degC", label="degrees Celsius", short="°C"),
                display=Display(decimals=2),
                scope=Scope(
                    geography="Global mean (90° S–90° N)",
                    baseline="1850–1900 mean of this dataset",
                    basis="NOAAGlobalTemp 6.1: NOAA GHCN monthly land-station temperatures merged with ERSST "
                    "version 6 sea-surface temperatures, with gaps filled by an artificial neural network.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(ANNUAL, MONTHLY, ARCTIC, README),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=170, value_range=(-1.5, 3.5)),
        )
    ]
