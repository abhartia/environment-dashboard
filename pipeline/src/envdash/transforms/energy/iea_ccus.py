"""IEA CCUS Projects Database: the capacity of carbon capture projects that operate, are being built or are planned,
counted the way the IEA's own CCUS Projects Explorer counts it.

Input: data/projects.json of the explorer (registry entry iea-ccus-projects, artifact projects-json, CC BY 4.0 under
the IEA Notice): a JSON array, one object per project, with country, projectType, year (start of operation), status,
sector, region and capacity (the explorer's unit, "Mt CO2 per year"). Read with exact decimals.

These are announced capacities of facilities, what they are designed or announced to capture, not CO2 actually
captured or stored. Most of it captures CO2 from fossil fuel use or industrial processes, so it is not carbon
removal; the State of CDR (state-of-cdr-3) measures removals.

The explorer's rule. The explorer's script (https://iea.blob.core.windows.net/scripts/ccus-projects-database/ccus.js,
sha256 2e0952491a4d…, read 2026-10-08) does three things, applied here unchanged:
- it keeps only projects with capacity above zero and a status other than "Suspended/cancelled/decommissioned"
  (`validProjects`: `!["Suspended/cancelled/decommissioned"].includes(n.status) && n.capacity > 0`);
- capture capacity is the sum over projects whose projectType is not transport or storage. Its chart notes say
  "Obtained by summing the estimated capacity of capture, full chain and CCU projects". The status chart leaves out
  `["T&S", "Transport", "Storage"]`; the sector chart also leaves out "Industrial cluster" and projects with no year
  or a year after 2030 (`["T&S", "Transport", "Storage", "Industrial cluster"].includes(o.projectType) || !o.year ||
  o.year > 2030`). In this file, capture types are Capture, "Full chain" (also spelled "Full Chain") and CCU;
- the status chart is cumulative by start year at the horizons 2026, 2030 and 2035 (`years: [2026, 2030, 2035]`; a
  project counts at every horizon from the first that is not before its year), and projects starting after 2035 are
  in none.
A projectType, status or sector this transform does not list stops the build, so a change in the file's vocabulary
is read by a person before it is counted.

Published:
- ccus.iea.operating-capture-capacity: the sector chart's operating column: operating capture capacity by the
  explorer's sectors, and their total (sector "all"), dated by the file's Last-Modified date.
- ccus.iea.capture-capacity-by-status: the status chart: capture capacity operating, under construction and planned
  to start by 2026, 2030 and 2035. Capacity not yet operating is a projection.
- ccus.iea.capture-projects-by-status: the number of projects behind each value of the status chart.
Sums are exact decimal sums of the file's values (at most three decimals in this file).
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from email.utils import parsedate_to_datetime
from pathlib import Path

from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "iea-ccus-projects"
PROJECTS = Input(SOURCE, "projects-json")
OPERATING = "ccus.iea.operating-capture-capacity"
BY_STATUS = "ccus.iea.capture-capacity-by-status"
COUNTS = "ccus.iea.capture-projects-by-status"
FIELDS = {"country", "projectType", "year", "status", "sector", "region", "capacity"}

CAPTURE_TYPES = frozenset({"Capture", "Full chain", "Full Chain", "CCU"})
NOT_CAPTURE_STATUS_CHART = frozenset({"T&S", "Transport", "Storage"})
NOT_CAPTURE_SECTOR_CHART = NOT_CAPTURE_STATUS_CHART | {"Industrial cluster"}
EXCLUDED_STATUS = "Suspended/cancelled/decommissioned"
SECTOR_CHART_LAST_YEAR = 2030
HORIZONS = (2026, 2030, 2035)

STATUSES = (
    ("operational", "Operating", "Operational"),
    ("under-construction", "Under construction", "Under construction"),
    ("planned", "Planned", "Planned"),
)
# The explorer's sectorOrder, with our ids. "CO2 T&S" is the sector of transport and storage projects only.
SECTORS = (
    ("natural-gas-processing", "Natural gas processing and LNG", "Natural gas processing/LNG"),
    ("hydrogen-ammonia", "Hydrogen or ammonia", "Hydrogen or ammonia"),
    ("biofuels", "Biofuels", "Biofuels"),
    ("other-fuel-transformation", "Other fuel transformation", "Other fuel transformation"),
    ("power", "Power", "Power"),
    ("cement", "Cement", "Cement"),
    ("iron-steel", "Iron and steel", "Iron and steel"),
    ("chemicals", "Chemicals", "Chemicals"),
    ("other-industry", "Other industry", "Other industry"),
    ("dac", "Direct air capture", "DAC"),
)
TRANSPORT_STORAGE_SECTOR = "CO2 T&S"
ALL = ("all", "All sectors")


class IeaCcusFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Project:
    project_type: str
    year: int | None
    status: str
    sector: str
    capacity: Decimal


def read_projects(raw: bytes) -> list[Project]:
    rows = json.loads(raw, parse_float=Decimal)
    if not isinstance(rows, list) or not rows:
        raise IeaCcusFormatError("expected a non-empty JSON array of projects")
    types = CAPTURE_TYPES | NOT_CAPTURE_SECTOR_CHART
    statuses = {s for *_, s in STATUSES} | {EXCLUDED_STATUS}
    sectors = {s for *_, s in SECTORS} | {TRANSPORT_STORAGE_SECTOR}
    out: list[Project] = []
    for i, r in enumerate(rows):
        if not isinstance(r, dict) or set(r) != FIELDS:
            raise IeaCcusFormatError(f"project {i}: fields {sorted(r) if isinstance(r, dict) else r!r} != {FIELDS}")
        if r["projectType"] not in types:
            raise IeaCcusFormatError(f"project {i}: projectType {r['projectType']!r} is not one this transform reads")
        if r["status"] not in statuses:
            raise IeaCcusFormatError(f"project {i}: status {r['status']!r} is not one this transform reads")
        if r["sector"] not in sectors:
            raise IeaCcusFormatError(f"project {i}: sector {r['sector']!r} is not one this transform reads")
        if r["sector"] == TRANSPORT_STORAGE_SECTOR and r["projectType"] in CAPTURE_TYPES:
            raise IeaCcusFormatError(f"project {i}: a {r['projectType']} project in sector {TRANSPORT_STORAGE_SECTOR}")
        cap = r["capacity"]
        if isinstance(cap, bool) or not isinstance(cap, int | Decimal) or cap < 0:
            raise IeaCcusFormatError(f"project {i}: capacity {cap!r} is not a non-negative number")
        year = r["year"]
        if year is not None and (isinstance(year, bool) or not isinstance(year, int)):
            raise IeaCcusFormatError(f"project {i}: year {year!r} is not a whole year")
        out.append(Project(r["projectType"], year, r["status"], r["sector"], Decimal(cap)))
    return out


def valid(projects: list[Project]) -> list[Project]:
    """The explorer's validProjects."""
    return [p for p in projects if p.status != EXCLUDED_STATUS and p.capacity > 0]


def _num(d: Decimal) -> float:
    return float(d)


def operating_by_sector(projects: list[Project], period: str) -> list[Observation]:
    keep = [
        p
        for p in valid(projects)
        if p.project_type not in NOT_CAPTURE_SECTOR_CHART
        and p.year is not None
        and p.year <= SECTOR_CHART_LAST_YEAR
        and p.status == "Operational"
    ]
    by: dict[str, Decimal] = defaultdict(Decimal)
    for p in keep:
        by[p.sector] += p.capacity
    obs = [Observation(entity="WLD", period=period, value=_num(sum(by.values(), Decimal(0))), dims={"sector": ALL[0]})]
    obs += [
        Observation(entity="WLD", period=period, value=_num(by[name]), dims={"sector": sid})
        for sid, _, name in SECTORS
        if name in by
    ]
    return obs


def status_chart(projects: list[Project]) -> dict[tuple[str, int], tuple[int, Decimal]]:
    """(status id, horizon) -> (number of projects, capacity), as the explorer's byStatus."""
    out: dict[tuple[str, int], tuple[int, Decimal]] = {}
    keep = [p for p in valid(projects) if p.project_type not in NOT_CAPTURE_STATUS_CHART]
    for sid, _, name in STATUSES:
        for h in HORIZONS:
            ps = [p for p in keep if p.status == name and p.year is not None and p.year <= h]
            out[(sid, h)] = (len(ps), sum((p.capacity for p in ps), Decimal(0)))
    return out


def chart_observations(projects: list[Project], *, count: bool) -> list[Observation]:
    chart = status_chart(projects)
    obs: list[Observation] = []
    for sid, _, _ in STATUSES:
        for h in HORIZONS:
            n, cap = chart[(sid, h)]
            obs.append(
                Observation(
                    entity="WLD",
                    period=str(h),
                    value=float(n) if count else _num(cap),
                    status="final" if sid == "operational" else "projection",
                    dims={"status": sid},
                )
            )
    return obs


def vintage_of(last_modified: str | None) -> str:
    if not last_modified:
        raise IeaCcusFormatError("the snapshot has no Last-Modified date, which is this file's only version label")
    return parsedate_to_datetime(last_modified).date().isoformat()


def _read(files: dict[str, InputFile]) -> tuple[InputFile, list[Project], str]:
    f = files[PROJECTS.key]
    return f, read_projects(f.path.read_bytes()), vintage_of(f.snapshot.last_modified)


def _common_steps(f: InputFile, projects: list[Project], vintage: str) -> list[str]:
    v = valid(projects)
    return [
        f"Read the CCUS Projects Explorer's data file (fetched {f.snapshot.date_accessed}, Last-Modified {vintage}, "
        f"sha256 {f.snapshot.sha256[:12]}…): {len(projects)} projects, read with exact decimals.",
        f"Kept the {len(v)} projects the explorer counts: capacity above zero and a status other than "
        f"'{EXCLUDED_STATUS}'.",
    ]


def _run_operating(files: dict[str, InputFile]) -> Result:
    f, projects, vintage = _read(files)
    obs = operating_by_sector(projects, vintage)
    return Result(
        observations=obs,
        vintage=f"CCUS Projects Database, file of {vintage}",
        date_published=vintage,
        steps=[
            *_common_steps(f, projects, vintage),
            "Applied the explorer's sector chart rule: left out transport and storage projects (projectType T&S, "
            "Transport, Storage) and industrial clusters, and projects without a start year or starting after "
            f"{SECTOR_CHART_LAST_YEAR}; kept those with status Operational.",
            "Summed their capacity (Mt CO2 per year) by the explorer's sectors, and over all sectors, exactly.",
        ],
        changes="Summed the announced capacity of operating capture projects by sector, as the IEA's explorer does.",
    )


def _run_by_status(files: dict[str, InputFile]) -> Result:
    f, projects, vintage = _read(files)
    return Result(
        observations=chart_observations(projects, count=False),
        vintage=f"CCUS Projects Database, file of {vintage}",
        date_published=vintage,
        steps=[
            *_common_steps(f, projects, vintage),
            "Applied the explorer's status chart rule: left out transport and storage projects (projectType T&S, "
            "Transport, Storage), and summed, for each status, the capacity of projects starting by 2026, by 2030 "
            "and by 2035 (cumulative; later projects are in none).",
        ],
        changes="Summed the announced capacity of capture projects by status and start year, as the IEA's explorer "
        "does.",
    )


def _run_counts(files: dict[str, InputFile]) -> Result:
    f, projects, vintage = _read(files)
    return Result(
        observations=chart_observations(projects, count=True),
        vintage=f"CCUS Projects Database, file of {vintage}",
        date_published=vintage,
        steps=[
            *_common_steps(f, projects, vintage),
            "Applied the explorer's status chart rule (no transport or storage projects) and counted, for each "
            "status, the projects starting by 2026, by 2030 and by 2035 (cumulative).",
        ],
        changes="Counted the capture projects behind the IEA explorer's capacity by status.",
    )


CAPACITY = Unit(
    code="MtCO2/yr", label="million tonnes of carbon dioxide per year of capture capacity", short="Mt CO₂/yr"
)
BASIS = (
    "Announced capacity of capture facilities (capture, full-chain and utilisation projects; transport and storage "
    "projects left out), as the IEA's CCUS Projects Explorer sums it. Capacity is what a facility is designed or "
    "announced to capture, not CO2 actually captured or stored. Only projects above 100,000 tonnes a year (1,000 "
    "for direct air capture) with an announced timeline are in the database."
)
STATUS_DIM = Dimension(
    id="status", label="Project status", values=[DimensionValue(id=i, label=lbl) for i, lbl, _ in STATUSES]
)


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id=OPERATING,
                title="Carbon capture capacity in operation, by sector",
                description="How much CO2 the world's operating carbon capture facilities are built to capture each "
                "year, by the sector they capture it from, including direct air capture, as recorded in the IEA's "
                "CCUS Projects Database. This is capacity, not the CO2 actually captured.",
                kind="derived",
                unit=CAPACITY,
                display=Display(decimals=3),
                scope=Scope(geography="World (projects in every country in the database)", basis=BASIS),
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(
                    Dimension(
                        id="sector",
                        label="Sector",
                        values=[DimensionValue(id=ALL[0], label=ALL[1])]
                        + [DimensionValue(id=i, label=lbl) for i, lbl, _ in SECTORS],
                    ),
                ),
                headline_dims=(("sector", ALL[0]),),
            ),
            inputs=(PROJECTS,),
            run=_run_operating,
            module_file=Path(__file__),
            validation=Validation(min_rows=5, value_range=(0.0, 1000.0)),
        ),
        Transform(
            spec=Spec(
                id=BY_STATUS,
                title="Carbon capture capacity operating, being built and planned",
                description="How much CO2 a year the world's carbon capture projects are built or announced to "
                "capture: in operation, under construction and planned, counting projects due to start by 2026, by "
                "2030 and by 2035, as the IEA's CCUS Projects Explorer shows them. Capacity not yet operating is what "
                "developers have announced, not a forecast by the IEA.",
                kind="derived",
                unit=CAPACITY,
                display=Display(decimals=1),
                scope=Scope(geography="World (projects in every country in the database)", basis=BASIS),
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(STATUS_DIM,),
                headline_dims=(("status", "operational"),),
            ),
            inputs=(PROJECTS,),
            run=_run_by_status,
            module_file=Path(__file__),
            validation=Validation(min_rows=len(STATUSES) * len(HORIZONS), value_range=(0.0, 5000.0)),
        ),
        Transform(
            spec=Spec(
                id=COUNTS,
                title="Number of carbon capture projects operating, being built and planned",
                description="The number of carbon capture projects in the IEA's CCUS Projects Database that operate, "
                "are under construction or are planned, counting those due to start by 2026, by 2030 and by 2035, "
                "with the IEA explorer's rule for which projects capture CO2.",
                kind="derived",
                unit=Unit(code="projects", label="projects", short="projects"),
                display=Display(decimals=0),
                scope=Scope(geography="World (projects in every country in the database)", basis=BASIS),
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(STATUS_DIM,),
                headline_dims=(("status", "operational"),),
            ),
            inputs=(PROJECTS,),
            run=_run_counts,
            module_file=Path(__file__),
            validation=Validation(min_rows=len(STATUSES) * len(HORIZONS), value_range=(0.0, 5000.0)),
        ),
    ]
