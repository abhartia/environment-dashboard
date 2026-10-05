"""NOAA GML methane and nitrous oxide: annual means averaged over the global network of marine surface sites.

Inputs: ch4_annmean_gl.csv and n2o_annmean_gl.csv (columns year,mean,unc; a blank line follows the column header).
NOAA cites these as their own product, "Trends in globally-averaged CH4, N2O, and SF6" (doi:10.15138/P8XG-AA10), so
they sit under the registry entry noaa-gml-trends-ch4-n2o-sf6 rather than the CO2 entry.

Vintage. NOAA labels each release by the month it was made ("Version 2026-09" in the citation on
gml.noaa.gov/ccgg/trends_ch4/ and trends_n2o/ for the files created on 5 September 2026). The files carry only
"# File Creation: Sat Sep  5 04:05:12 2026", so the vintage is that line's year and month.

Uncertainty. Both files state: "Standard deviations of the annual means are calculated, and the two terms (network
and analytical) are taken in quadrature to give the reported uncertainties", so lower/upper are mean ∓ unc with
interval 1sigma (exact decimal arithmetic on the printed digits). The trends pages say the same in words: "one
standard deviation from the two terms (network and analytical) is taken in quadrature".

Last year. Both files state "the data presented for the last year are subject to change", so the last year is
published with status preliminary. A negative mean or uncertainty (none in the current files) would be treated as
NOAA's sentinel: a null value with the sentinel as its reason, or a value without a range and a note.

If any quoted header statement or the unit line disappears, the transform stops: a person must re-read the file before
these rules are applied to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import polars as pl

from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation
from envdash.transforms.air.noaa_co2 import file_creation, header_text

SOURCE = "noaa-gml-trends-ch4-n2o-sf6"
PPB = Unit(code="ppb", label="parts per billion", short="ppb")
COLUMNS = ["year", "mean", "unc"]

SHARED_REQUIRED = (
    "Standard deviations of the annual means are calculated, and the two terms (network and analytical) are taken in "
    "quadrature to give the reported uncertainties",
    "the data presented for the last year are subject to change",
)


class NoaaGhgFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Gas:
    formula: str
    """As NOAA writes it in the file, e.g. "CH4"."""
    name: str
    file_name: str
    input: Input
    first_year: int

    @property
    def unit_statement(self) -> str:
        return f"{self.formula} expressed as a mole fraction in dry air, nanomol/mol, abbreviated as ppb"


CH4 = Gas("CH4", "methane", "ch4_annmean_gl.csv", Input(SOURCE, "ch4-annmean-gl"), 1984)
N2O = Gas("N2O", "nitrous oxide", "n2o_annmean_gl.csv", Input(SOURCE, "n2o-annmean-gl"), 2001)


def parse_annual_global(raw: str, gas: Gas) -> tuple[list[Observation], datetime]:
    header = header_text(raw)
    for s in (*SHARED_REQUIRED, gas.unit_statement):
        if s not in header:
            raise NoaaGhgFormatError(
                f"{gas.file_name}: header no longer says {s!r}; re-read the file before trusting these rules"
            )
    created = file_creation(raw)
    df = pl.read_csv(raw.encode("utf-8"), comment_prefix="#", infer_schema=False)
    if df.columns != COLUMNS:
        raise NoaaGhgFormatError(f"{gas.file_name}: columns {df.columns} != expected {COLUMNS}")
    # The blank line after the column header reads as a row of empty cells; it carries no data.
    rows = [r for r in df.iter_rows(named=True) if any(v is not None for v in r.values())]
    if not rows or int(rows[0]["year"]) != gas.first_year:
        raise NoaaGhgFormatError(f"{gas.file_name}: expected the record to start in {gas.first_year}")
    obs: list[Observation] = []
    for i, row in enumerate(rows):
        period = f"{int(row['year']):04d}"
        mean, unc = Decimal(row["mean"]), Decimal(row["unc"])
        status = "preliminary" if i == len(rows) - 1 else "final"
        if mean < 0:
            obs.append(
                Observation(
                    entity="WLD",
                    period=period,
                    value=None,
                    status=status,
                    missing_reason=f"NOAA's file has the sentinel {row['mean']} instead of an annual mean.",
                )
            )
        elif unc < 0:
            obs.append(
                Observation(
                    entity="WLD",
                    period=period,
                    value=float(mean),
                    status=status,
                    note=f"NOAA's file gives no uncertainty for this year (sentinel {row['unc']}).",
                )
            )
        else:
            obs.append(
                Observation(
                    entity="WLD",
                    period=period,
                    value=float(mean),
                    lower=float(mean - unc),
                    upper=float(mean + unc),
                    interval="1sigma",
                    status=status,
                )
            )
    return obs, created


def _runner(gas: Gas):
    def run(files: dict[str, InputFile]) -> Result:
        raw = files[gas.input.key].path.read_text(encoding="utf-8")
        obs, created = parse_annual_global(raw, gas)
        return Result(
            observations=obs,
            vintage=f"{created:%Y-%m}",
            date_published=created.date().isoformat(),
            steps=[
                f"Read {gas.file_name}, created by NOAA on {created.day} {created:%B %Y}. The vintage is the year and "
                "month of that creation date, which is how NOAA labels its versions.",
                "Lower and upper are the mean minus and plus NOAA's stated uncertainty, which the file defines as the "
                "standard deviations of 100 bootstrap (network) and 100 Monte Carlo (measurement) global averages "
                "taken in quadrature (one standard deviation).",
                "The last year is marked preliminary because the file states that the data for the last year are "
                "subject to change.",
            ],
        )

    return run


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    scope = Scope(
        geography="Global mean of marine surface sites",
        basis="Dry-air mole fraction; NOAA's global average of its marine surface air-sampling network, from "
        "smoothed site records weighted by latitude.",
    )
    return [
        Transform(
            spec=Spec(
                id="ch4.noaa-gml.annual-global",
                title="Methane, global annual mean",
                description="Annual mean methane in dry air averaged over NOAA's global network of marine surface "
                "air-sampling sites, since 1984.",
                kind="series",
                unit=PPB,
                display=Display(decimals=2),
                scope=scope,
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(CH4.input,),
            run=_runner(CH4),
            module_file=here,
            validation=Validation(min_rows=40, value_range=(1500.0, 2200.0)),
        ),
        Transform(
            spec=Spec(
                id="n2o.noaa-gml.annual-global",
                title="Nitrous oxide, global annual mean",
                description="Annual mean nitrous oxide in dry air averaged over NOAA's global network of marine "
                "surface air-sampling sites, since 2001.",
                kind="series",
                unit=PPB,
                display=Display(decimals=2),
                scope=scope,
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(N2O.input,),
            run=_runner(N2O),
            module_file=here,
            validation=Validation(min_rows=24, value_range=(300.0, 380.0)),
        ),
    ]
