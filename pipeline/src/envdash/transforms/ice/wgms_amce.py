"""WGMS annual mass-change estimates for the world's glaciers (AMCE): global annual and cumulative mass change.

Input: the release zip wgms-amce-<version>.zip; only its global.csv and README.md are read. global.csv has one row per
hydrological year: year, area_km2, mwe, mwe_sigma, mwe_cumsum, gt, gt_sigma, gt_cumsum, gt_cumsum_sigma, mmsle,
mmsle_sigma, mmsle_cumsum, mmsle_cumsum_sigma. The README defines them (each "_sigma" is a "1-sigma uncertainty") and
the hydrological year ("starting from 1 October in the Northern Hemisphere, from 1 April in the Southern Hemisphere,
and 1 January in the tropics ... labeled by their (end) calendar year"). The build stops unless those README lines,
the column list and the dataset DOI for the version in the zip's file name are all present.

Version. The zip's file name carries it (wgms-amce-2026-02-10.zip); it is the vintage, and WGMS publishes each
version under its own DOI and file name.

Three indicators, values as printed, lower/upper = value ∓ the matching sigma column (exact decimals), 1sigma:
- glacier-mass.wgms-amce.annual: gt ± gt_sigma, the world's glacier mass change in each hydrological year (negative is
  a loss);
- glacier-mass.wgms-amce.cumulative: gt_cumsum ± gt_cumsum_sigma, the change since the start of hydrological year
  1976;
- sea-level-contribution.wgms-amce.glaciers-cumulative: mmsle_cumsum ± mmsle_cumsum_sigma, the same change as global
  mean sea level (positive is a rise; the README defines mm SLE as "The change in global mean sea level that would
  occur if the glacier mass change were distributed evenly across the global ocean").

Checks on meaning (the build stops otherwise): gt_cumsum and mmsle_cumsum equal the running sums of gt and mmsle
within the rounding of the printed values (half a unit of the last digit for every term summed), and mmsle has the
opposite sign of gt in every year where neither is zero, which is what makes a positive mm SLE a rise in sea level.
The cumulative sigmas are not recomputed: WGMS does not say how they combine.

Status. Nothing in the zip or on the landing page marks the latest year as preliminary, so every year is final.

Publisher check: WGMS's own summary for this version (The WGMS Network, "Global glacier mass change in 2025", Nature
Reviews Earth & Environment 7, 213-215, 7 April 2026): "Since 1975, glacier mass loss has totalled 9,583 ± 1,211 Gt,
equivalent to 26.4 ± 3.3 mm of sea-level rise". Its Gt figures are printed as losses without a sign, so only the mm
figure is a check; the Gt values match it in the tests. Its ± ranges are about 1.96 times the file's sigmas (617.629
× 1.96 = 1,210.5 Gt), i.e. 95% ranges; the site shows the file's one-sigma values.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, PublisherCheck, Result, Spec, Transform, Validation

SOURCE = "wgms-amce"
ZIP = Input(SOURCE, "amce-2026-02-10")
ZIP_URL = re.compile(r"/wgms-amce-(\d{4}-\d{2}-\d{2})\.zip$")
ENTITY = "WLD"
GLOBAL_MEMBER = "global.csv"
README_MEMBER = "README.md"
COLUMNS = [
    "year",
    "area_km2",
    "mwe",
    "mwe_sigma",
    "mwe_cumsum",
    "gt",
    "gt_sigma",
    "gt_cumsum",
    "gt_cumsum_sigma",
    "mmsle",
    "mmsle_sigma",
    "mmsle_cumsum",
    "mmsle_cumsum_sigma",
]
GLOBAL_SECTION = "### Global (`global.csv`)"
GLOBAL_COLUMNS_DEFINED = (
    "* `gt`: Glacier mass change [Gt]\n",
    "* `gt_sigma`: 1-sigma uncertainty of `gt`\n",
    "* `gt_cumsum`: Cumulative sum of `gt`\n",
    "* `gt_cumsum_sigma`: 1-sigma uncertainty of `gt_cumsum`\n",
    "* `mmsle`: Glacier mass change [mm SLE]\n",
    "* `mmsle_cumsum`: Cumulative sum of `mmsle`\n",
    "* `mmsle_cumsum_sigma`: 1-sigma uncertainty of `mmsle_cumsum`\n",
)
README_REQUIRED = (
    "A 12-month period starting from 1 October in the Northern Hemisphere, from 1 April in the Southern Hemisphere, "
    "and 1 January in the tropics (region `TRP`). For brevity, hydrological years are labeled by their (end) calendar "
    "year.",
    "The change in global mean sea level that would occur if the glacier mass change were distributed evenly across "
    "the global ocean.",
)

GT = Unit(code="Gt", label="gigatonnes", short="Gt")
MM = Unit(code="mm", label="millimetres", short="mm")
NATURE_URL = "https://www.nature.com/articles/s43017-026-00777-z"


class WgmsFormatError(ValueError):
    pass


def version_of(url: str | None) -> str:
    m = ZIP_URL.search(url or "")
    if not m:
        raise WgmsFormatError(f"cannot read an AMCE version from {url!r}")
    return m.group(1)


def _half_unit(s: str) -> Decimal:
    exp = Decimal(s).as_tuple().exponent
    assert isinstance(exp, int)
    return Decimal(5) * Decimal(10) ** (exp - 1)


@dataclass(frozen=True)
class Year:
    year: int
    cells: dict[str, str]

    def d(self, col: str) -> Decimal:
        return Decimal(self.cells[col])


def read_global(csv_bytes: bytes) -> list[Year]:
    rows = list(csv.reader(io.StringIO(csv_bytes.decode("utf-8"))))
    if rows[0] != COLUMNS:
        raise WgmsFormatError(f"global.csv columns {rows[0]} != {COLUMNS}")
    years = [Year(int(r[0]), dict(zip(COLUMNS, r, strict=True))) for r in rows[1:] if r]
    for a, b in pairwise(years):
        if b.year != a.year + 1:
            raise WgmsFormatError(f"years not consecutive: {a.year} then {b.year}")
    for value, cum in (("gt", "gt_cumsum"), ("mmsle", "mmsle_cumsum")):
        total, slack = Decimal(0), Decimal(0)
        for y in years:
            total += y.d(value)
            slack += _half_unit(y.cells[value])
            if abs(total - y.d(cum)) > slack + _half_unit(y.cells[cum]):
                raise WgmsFormatError(f"{y.year}: {cum} {y.cells[cum]} is not the running sum of {value} ({total})")
    for y in years:
        gt, mm = y.d("gt"), y.d("mmsle")
        if gt != 0 and mm != 0 and (gt > 0) == (mm > 0):
            raise WgmsFormatError(f"{y.year}: gt {gt} and mmsle {mm} have the same sign")
    return years


def check_readme(readme: bytes, version: str) -> None:
    """The column definitions must be in the README's global.csv section (other sections repeat some of them)."""
    text = readme.decode("utf-8")
    start = text.find(GLOBAL_SECTION)
    if start < 0:
        raise WgmsFormatError(f"README.md has no {GLOBAL_SECTION!r} section")
    end = text.find("\n### ", start + len(GLOBAL_SECTION))
    section = text[start : end if end >= 0 else len(text)]
    for s in GLOBAL_COLUMNS_DEFINED:
        if s not in section:
            raise WgmsFormatError(f"README.md's global.csv section no longer says {s!r}")
    for s in (*README_REQUIRED, f"https://doi.org/10.5904/wgms-amce-{version}"):
        if s not in text:
            raise WgmsFormatError(f"README.md no longer says {s!r}")


def read_release(zip_path: Path, version: str) -> list[Year]:
    with zipfile.ZipFile(zip_path) as zf:
        check_readme(zf.read(README_MEMBER), version)
        return read_global(zf.read(GLOBAL_MEMBER))


def observations(years: list[Year], value: str, sigma: str) -> list[Observation]:
    return [
        Observation(
            entity=ENTITY,
            period=f"{y.year:04d}",
            value=float(y.d(value)),
            lower=float(y.d(value) - y.d(sigma)),
            upper=float(y.d(value) + y.d(sigma)),
            interval="1sigma",
        )
        for y in years
    ]


def _runner(value: str, sigma: str, what: str):
    def run(files: dict[str, InputFile]) -> Result:
        f = files[ZIP.key]
        version = version_of(str(f.snapshot.url) if f.snapshot.url else None)
        years = read_release(f.path, version)
        return Result(
            observations=observations(years, value, sigma),
            vintage=version,
            date_published=version,
            steps=[
                f"Read global.csv from wgms-amce-{version}.zip (hydrological years {years[0].year} to "
                f"{years[-1].year}) and published the {value} column ({what}) as printed.",
                f"Lower and upper are {value} minus and plus {sigma}, which the release README defines as the 1-sigma "
                "uncertainty (exact decimal arithmetic).",
                "Checked that gt_cumsum and mmsle_cumsum are the running sums of gt and mmsle (within rounding), and "
                "that mmsle has the opposite sign of gt, so that positive mm is a rise in sea level.",
            ],
        )

    return run


HYDRO_YEAR = (
    "Hydrological years, labelled by the year they end: from 1 October in the Northern Hemisphere, 1 April in the "
    "Southern Hemisphere and 1 January in the tropics."
)
BASELINE = (
    "Zero at the start of hydrological year 1976 (October 1975 in the Northern Hemisphere, April 1975 in the Southern "
    "Hemisphere, January 1976 in the tropics)."
)
BASIS = (
    "All glaciers outside the Greenland and Antarctic ice sheets (Randolph Glacier Inventory 6.0 outlines), from "
    "satellite elevation changes downscaled to single years with field measurements. " + HYDRO_YEAR
)


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    return [
        Transform(
            spec=Spec(
                id="glacier-mass.wgms-amce.annual",
                title="Global glacier mass change each year (WGMS)",
                description="Change in the mass of the world's glaciers in each hydrological year since 1976, from "
                "the World Glacier Monitoring Service's annual estimates, with the one-sigma uncertainty. Negative "
                "values are a loss of ice.",
                kind="series",
                unit=GT,
                display=Display(decimals=0),
                scope=Scope(geography="All glaciers worldwide, excluding the two ice sheets", basis=BASIS),
                geo_coverage="global-only",
                headline_entity=ENTITY,
            ),
            inputs=(ZIP,),
            run=_runner("gt", "gt_sigma", "glacier mass change in Gt"),
            module_file=here,
            validation=Validation(min_rows=50, value_range=(-1000.0, 300.0)),
        ),
        Transform(
            spec=Spec(
                id="glacier-mass.wgms-amce.cumulative",
                title="Global glacier mass change since 1975 (WGMS)",
                description="Cumulative change in the mass of the world's glaciers since the start of hydrological "
                "year 1976 (late 1975), from the World Glacier Monitoring Service's annual estimates, with the "
                "one-sigma uncertainty. Negative values are a loss of ice.",
                kind="series",
                unit=GT,
                display=Display(decimals=0),
                scope=Scope(
                    geography="All glaciers worldwide, excluding the two ice sheets", baseline=BASELINE, basis=BASIS
                ),
                geo_coverage="global-only",
                headline_entity=ENTITY,
            ),
            inputs=(ZIP,),
            run=_runner("gt_cumsum", "gt_cumsum_sigma", "cumulative glacier mass change in Gt"),
            module_file=here,
            validation=Validation(min_rows=50, value_range=(-15000.0, 500.0)),
        ),
        Transform(
            spec=Spec(
                id="sea-level-contribution.wgms-amce.glaciers-cumulative",
                title="Sea level rise from glaciers since 1975 (WGMS)",
                description="How much the world's glaciers have added to global mean sea level since the start of "
                "hydrological year 1976 (late 1975), from the World Glacier Monitoring Service's annual estimates, "
                "with the one-sigma uncertainty.",
                kind="series",
                unit=MM,
                display=Display(decimals=1),
                scope=Scope(
                    geography="All glaciers worldwide, excluding the two ice sheets",
                    baseline=BASELINE,
                    basis=BASIS + " Positive values raise global mean sea level.",
                ),
                geo_coverage="global-only",
                headline_entity=ENTITY,
            ),
            inputs=(ZIP,),
            run=_runner("mmsle_cumsum", "mmsle_cumsum_sigma", "cumulative sea level equivalent in mm"),
            module_file=here,
            validation=Validation(min_rows=50, value_range=(-2.0, 50.0)),
            checks=(
                PublisherCheck(
                    source_id=SOURCE,
                    vintage="2026-02-10",
                    entity=ENTITY,
                    period="2025",
                    stated="26.4",
                    quote="Since 1975, glacier mass loss has totalled 9,583 ± 1,211 Gt, equivalent to 26.4 ± 3.3 mm "
                    "of sea-level rise",
                    url=NATURE_URL,
                ),
            ),
        ),
    ]
