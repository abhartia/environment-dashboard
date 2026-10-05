"""C3S Climate Pulse: daily global 2 m air temperature and 60°S–60°N sea-surface temperature anomalies from ERA5.

Inputs: era5_daily_series_2t_global.csv (from 1 January 1940) and era5_daily_series_sst_60S-60N_ocean.csv (from
1 January 1979). Each has a "#" header ending "Last updated: <dd Mon yyyy>", then columns date, <2t|sst>,
clim_91-20, ano_91-20, status, in °C to three decimals.

What is published: the producer's anomaly from its smoothed 1991–2020 daily climatology (ano_91-20), unchanged. The
files carry no 1850–1900 column. The Climate Pulse app shows one by adding C3S's daily offsets, but those offsets are
not in the files, so no pre-industrial value is published here.

Status. Each row is FINAL or PRELIMINARY, and the header states: "If preliminary, the values will likely change
(slightly) once the final ERA5 data for the day are available". PRELIMINARY rows are published with status
preliminary; any other status word stops the build. If that header statement disappears the build stops too, so a
person re-reads the file before these rules are applied to it.

Vintage. The "Last updated" date (YYYY-MM-DD). It also fills the {year} of the Copernicus credit line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import polars as pl

from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "c3s-climate-pulse"
AIR = Input(SOURCE, "air-temperature-daily")
SST = Input(SOURCE, "sea-surface-temperature-daily")
STATUS = {"FINAL": "final", "PRELIMINARY": "preliminary"}
HEADER_REQUIRED = (
    "ano_91-20: Daily anomaly relative to the 1991-2020 daily climatology",
    "If preliminary, the values will likely change (slightly) once the final ERA5 data for the day are available",
    "Units: deg. C",
)


class PulseFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Variable:
    column: str
    description: str
    """The header's own description of the variable, which must be present."""
    name: str


VARIABLES = {
    AIR.key: Variable("2t", "daily global mean near-surface (2m) air temperature", "global 2 m air temperature"),
    SST.key: Variable(
        "sst",
        "daily mean sea surface temperature (SST) data from ERA5 averaged over 60°S-60°N",
        "60°S–60°N sea-surface temperature",
    ),
}


def header_text(raw: str) -> str:
    return re.sub(r"\s+", " ", " ".join(ln[1:].strip() for ln in raw.splitlines() if ln.startswith("#")))


def last_updated(raw: str) -> date:
    m = re.findall(r"^# Last updated: (\d{2} [A-Z][a-z]{2} \d{4})\s*$", raw, re.M)
    if len(m) != 1:
        raise PulseFormatError("expected one '# Last updated:' header line")
    return datetime.strptime(m[0], "%d %b %Y").date()


def parse(raw: str, var: Variable) -> tuple[list[Observation], int]:
    """Returns (observations of ano_91-20, number of preliminary days)."""
    header = header_text(raw)
    for s in (*HEADER_REQUIRED, var.description):
        if s not in header:
            raise PulseFormatError(f"header no longer says {s!r}; re-read the file before trusting these rules")
    df = pl.read_csv(raw.encode("utf-8"), comment_prefix="#", infer_schema=False)
    expected = ["date", var.column, "clim_91-20", "ano_91-20", "status"]
    if df.columns != expected:
        raise PulseFormatError(f"columns {df.columns} != expected {expected}")
    obs: list[Observation] = []
    preliminary = 0
    for day, _abs, _clim, ano, status in df.iter_rows():
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            raise PulseFormatError(f"date {day!r} is not YYYY-MM-DD")
        if status not in STATUS:
            raise PulseFormatError(f"{day}: status {status!r} is neither FINAL nor PRELIMINARY")
        preliminary += status == "PRELIMINARY"
        obs.append(Observation(entity="WLD", period=day, value=float(Decimal(ano)), status=STATUS[status]))  # type: ignore[arg-type]
    return obs, preliminary


def _runner(inp: Input):
    var = VARIABLES[inp.key]

    def run(files: dict[str, InputFile]) -> Result:
        raw = files[inp.key].path.read_text(encoding="utf-8")
        obs, preliminary = parse(raw, var)
        updated = last_updated(raw)
        return Result(
            observations=obs,
            vintage=updated.isoformat(),
            year=str(updated.year),
            date_published=updated.isoformat(),
            steps=[
                f"Read the Climate Pulse daily series of {var.name} from ERA5, last updated by C3S on "
                f"{updated:%d %B %Y}, from {obs[0].period} to {obs[-1].period}.",
                "Published the producer's anomaly from its smoothed 1991–2020 daily climatology (column ano_91-20) "
                "unchanged, rounded as printed (three decimals).",
                f"Kept the file's status of each day: {preliminary} day(s) marked PRELIMINARY are published as "
                "preliminary, because the file states that their values will likely change slightly once the final "
                "ERA5 data for the day are available.",
            ],
        )

    return run


def transforms(paths: Paths) -> list[Transform]:
    degc = Unit(code="degC", label="degrees Celsius", short="°C")
    here = Path(__file__)
    return [
        Transform(
            spec=Spec(
                id="temp.c3s-climate-pulse.daily-1991-2020",
                title="Global air temperature against 1991–2020, daily (ERA5 Climate Pulse)",
                description="Daily global mean air temperature at 2 metres since 1 January 1940 from the ERA5 "
                "reanalysis, as the difference from the 1991–2020 average for the same day of the year. The newest "
                "days are preliminary.",
                kind="series",
                unit=degc,
                display=Display(decimals=2),
                scope=Scope(
                    geography="Global mean",
                    baseline="1991–2020 daily climatology of this dataset, smoothed by C3S",
                    basis="ERA5 reanalysis; daily mean of hourly 2 m air temperature from 00 to 23 UTC.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(AIR,),
            run=_runner(AIR),
            module_file=here,
            validation=Validation(min_rows=31000, value_range=(-2.5, 2.5)),
        ),
        Transform(
            spec=Spec(
                id="sst.c3s-climate-pulse.daily-60s-60n-1991-2020",
                title="Sea-surface temperature against 1991–2020, 60° S–60° N, daily (ERA5 Climate Pulse)",
                description="Daily mean sea-surface temperature over the ocean between 60° S and 60° N since "
                "1 January 1979 from the ERA5 reanalysis, as the difference from the 1991–2020 average for the same "
                "day of the year. The newest days can be preliminary.",
                kind="series",
                unit=degc,
                display=Display(decimals=2),
                scope=Scope(
                    geography="Ocean between 60° S and 60° N (area mean)",
                    baseline="1991–2020 daily climatology of this dataset, smoothed by C3S",
                    basis="ERA5 reanalysis; daily mean sea-surface temperature.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(SST,),
            run=_runner(SST),
            module_file=here,
            validation=Validation(min_rows=17000, value_range=(-1.5, 1.5)),
        ),
    ]
