"""Net Zero Tracker, Net Zero Stocktake 2025 dataset: which national governments have a net zero target, how firm it
is, and for which year.

Input: Data_finalised_for_Zenodo_16_09(Sheet1).csv from the Zenodo deposit doi:10.5281/zenodo.17143240 (registry
entry net-zero-tracker-2025, CC BY-NC 4.0 as the Tracker's data terms say; the deposit itself says CC BY 4.0). The
file is cp1252 text, one row per entity. The build stops unless its md5 is the one Zenodo lists for it.

Rows used: Entity_type "Country" (198 rows in this deposit: national governments and three self-governing territories,
Bermuda, the Cayman Islands and Niue, plus the European Union, code EUU, published as EU27). Regions, cities and
companies are not read. Columns used: Country, End_target, End_target_year, Status_of_end_target,
Date_of_last_status_update, and the Tracker's own flags data_is_nzt (1 when the end target is a net zero or similar
target), data_NonNZ_EndTarget (1 when the end target is another kind of target) and "No target at all". The GDP,
population and emissions context columns are never read: national emissions come from Climate Watch's CAIT data,
whose fuel-combustion values are the IEA's.

Which targets count as net zero. The Tracker's methodology lists the target names in scope (TARGET_NAMES_IN_SCOPE).
The build stops unless, for every country row, data_is_nzt is 1 exactly when End_target is one of those names,
"No target at all" is 1 exactly when End_target is "No target", and data_NonNZ_EndTarget is 1 for every other end
target; and unless every net zero target has a four-digit year and one of the Tracker's five status labels. A label
this transform does not know stops the build.

Published:
- net-zero.nzt-2025.target-by-country: one observation per country row. The value is the year of its net zero
  target; the dimension `status` is the target's status in the Tracker's own words. A country whose end target is
  not net zero (status "other-end-target") or that has no target ("no-target") has a null value, with the Tracker's
  end target, year and status as the reason. Every observation carries the Tracker's labels as its note.
- net-zero.nzt-2025.countries-by-status: the number of those rows with each status, and the number with any net
  zero target, as the Tracker counts them (the European Union is one of the 198, as in the Stocktake report).

Both are dated 2025-09-17, the day the deposit was published; the Tracker coded each target as in effect on the day
it was analysed, up to the Stocktake's data cut-off.

Publisher check: the Net Zero Stocktake 2025 report, section 3.2: "As of 2025, 137 of the 198 national governments
and self-governing territories (including the EU and Taiwan) have set net zero targets." The deposit has no row for
Taiwan (only its regions, cities and companies), yet its country rows number 198 and 137 of them have a net zero
target; that difference is recorded in docs/sources.md, not resolved here.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path

from envdash import geo
from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, PublisherCheck, Result, Spec, Transform, Validation

SOURCE = "net-zero-tracker-2025"
CSV = Input(SOURCE, "stocktake-2025-csv")
BY_COUNTRY = "net-zero.nzt-2025.target-by-country"
COUNTS = "net-zero.nzt-2025.countries-by-status"

# Zenodo record 17143240, files[0].checksum.
ZENODO_MD5 = "68515520c574f51bf5d69af4d493ca57"
PUBLISHED = "2025-09-17"
VINTAGE = "Net Zero Stocktake 2025 (Zenodo doi:10.5281/zenodo.17143240, 17 September 2025)"
REPORT_URL = "https://ca1-nzt.edcdn.com/PDFs-and-Excels/Net_Zero_Stocktake_2025.pdf?v=1758570577"
Q_COUNT = (
    "As of 2025, 137 of the 198 national governments and self-governing territories (including the EU and Taiwan) "
    "have set net zero targets."
)

COLUMNS = (
    "Country",
    "Entity_type",
    "Name",
    "End_target",
    "End_target_year",
    "Status_of_end_target",
    "Date_of_last_status_update",
    "data_is_nzt",
    "data_NonNZ_EndTarget",
    "No target at all",
)
# The Tracker's methodology page, "The following target names are considered in scope" (read 2026-10-08).
TARGET_NAMES_IN_SCOPE = frozenset(
    {
        "Net zero",
        "Zero emissions",
        "Zero carbon",
        "Climate neutral",
        "Climate positive",
        "Carbon neutral(ity)",
        "GHG neutral(ity)",
        "Carbon negative",
        "Net negative",
    }
)
NO_TARGET = "No target"
# Other end targets seen in the deposit's country rows. Any other label stops the build.
OTHER_TARGETS = frozenset({"Emissions reduction target", "Reduction v. BAU", "Absolute emissions target", "Other"})
ALIASES = {"EUU": "EU27"}
YEAR = re.compile(r"\d{4}")


@dataclass(frozen=True)
class Status:
    id: str
    label: str
    tracker: str | None
    """The Tracker's label in Status_of_end_target, for the five net zero statuses."""


NET_ZERO_STATUSES: tuple[Status, ...] = (
    Status("achieved-self-declared", "Achieved (self-declared)", "Achieved (self-declared)"),
    Status("in-law", "In law", "In law"),
    Status("in-policy-document", "In policy document", "In policy document"),
    Status("declaration-pledge", "Declaration / pledge", "Declaration / pledge"),
    Status("proposed-in-discussion", "Proposed / in discussion", "Proposed / in discussion"),
)
OTHER = Status("other-end-target", "Another kind of end target, not net zero", None)
NONE = Status("no-target", "No target", None)
STATUSES = (*NET_ZERO_STATUSES, OTHER, NONE)
BY_TRACKER_LABEL = {s.tracker: s for s in NET_ZERO_STATUSES}
ANY = DimensionValue(id="any-net-zero-target", label="Any net zero target")


class NetZeroTrackerFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Target:
    entity: str
    status: Status
    end_target: str
    year: int | None
    tracker_status: str
    status_updated: str


def read_rows(raw: bytes) -> list[dict[str, str]]:
    md5 = hashlib.md5(raw, usedforsecurity=False).hexdigest()
    if md5 != ZENODO_MD5:
        raise NetZeroTrackerFormatError(f"md5 {md5} is not the {ZENODO_MD5} Zenodo lists for this file")
    reader = csv.DictReader(io.StringIO(raw.decode("cp1252"), newline=""))
    missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise NetZeroTrackerFormatError(f"columns missing: {missing}")
    return [r for r in reader if r["Entity_type"] == "Country"]


def entity(code: str) -> str:
    return geo.resolve(ALIASES.get(code, code), "iso3")


def target(row: dict[str, str]) -> Target:
    end, status, year = row["End_target"], row["Status_of_end_target"], row["End_target_year"]
    where = f"{row['Name']} ({row['Country']})"
    nzt, other, none = (row[c] == "1" for c in ("data_is_nzt", "data_NonNZ_EndTarget", "No target at all"))
    if (end in TARGET_NAMES_IN_SCOPE) != nzt:
        raise NetZeroTrackerFormatError(f"{where}: End_target {end!r} disagrees with data_is_nzt {row['data_is_nzt']}")
    if (end == NO_TARGET) != none:
        raise NetZeroTrackerFormatError(f"{where}: End_target {end!r} disagrees with 'No target at all'")
    if not (nzt or none):
        if end not in OTHER_TARGETS:
            raise NetZeroTrackerFormatError(f"{where}: End_target {end!r} is not a label this transform reads")
        if not other:
            raise NetZeroTrackerFormatError(f"{where}: End_target {end!r} without data_NonNZ_EndTarget 1")
    if nzt:
        if status not in BY_TRACKER_LABEL:
            raise NetZeroTrackerFormatError(f"{where}: net zero status {status!r} is not one of the Tracker's five")
        if not YEAR.fullmatch(year):
            raise NetZeroTrackerFormatError(f"{where}: net zero target year {year!r} is not a year")
        s = BY_TRACKER_LABEL[status]
    else:
        s = OTHER if other else NONE
    updated = row["Date_of_last_status_update"]
    if updated and not YEAR.fullmatch(updated):
        raise NetZeroTrackerFormatError(f"{where}: Date_of_last_status_update {updated!r} is not a year")
    return Target(
        entity=entity(row["Country"]),
        status=s,
        end_target=end,
        year=int(year) if YEAR.fullmatch(year) else None,
        tracker_status=status,
        status_updated=updated,
    )


def targets(raw: bytes) -> list[Target]:
    out = sorted((target(r) for r in read_rows(raw)), key=lambda t: t.entity)
    seen = [t.entity for t in out]
    dupes = sorted({e for e in seen if seen.count(e) > 1})
    if dupes:
        raise NetZeroTrackerFormatError(f"countries with more than one row: {dupes}")
    return out


def _labels(t: Target) -> str:
    parts = [f"end target '{t.end_target}'"]
    if t.year is not None:
        parts.append(f"for {t.year}")
    parts.append(f"status '{t.tracker_status}'" if t.tracker_status else "no status given")
    if t.status_updated:
        parts.append(f"status last updated {t.status_updated}")
    return "Net Zero Tracker: " + ", ".join(parts) + "."


def country_observations(ts: list[Target]) -> list[Observation]:
    obs: list[Observation] = []
    for t in ts:
        common = {"entity": t.entity, "period": PUBLISHED, "dims": {"status": t.status.id}, "note": _labels(t)}
        if t.status in NET_ZERO_STATUSES:
            obs.append(Observation(value=float(t.year), **common))  # type: ignore[arg-type]
        elif t.status is OTHER:
            reason = f"No net zero target: the Net Zero Tracker records the end target '{t.end_target}'" + (
                f" for {t.year}." if t.year is not None else "."
            )
            obs.append(Observation(value=None, missing_reason=reason, **common))
        else:
            obs.append(Observation(value=None, missing_reason="The Net Zero Tracker records no target.", **common))
    return obs


def count_observations(ts: list[Target]) -> list[Observation]:
    n = {s.id: sum(1 for t in ts if t.status == s) for s in STATUSES}
    any_nz = sum(n[s.id] for s in NET_ZERO_STATUSES)
    if any_nz + n[OTHER.id] + n[NONE.id] != len(ts):
        raise AssertionError("every country row has exactly one status")
    out = [Observation(entity="WLD", period=PUBLISHED, value=float(any_nz), dims={"status": ANY.id})]
    out += [Observation(entity="WLD", period=PUBLISHED, value=float(n[s.id]), dims={"status": s.id}) for s in STATUSES]
    return out


def _steps(f: InputFile, ts: list[Target]) -> list[str]:
    return [
        f"Read Data_finalised_for_Zenodo_16_09(Sheet1).csv from Zenodo record 17143240 (fetched "
        f"{f.snapshot.date_accessed}, sha256 {f.snapshot.sha256[:12]}…), as cp1252 text, and checked that its md5 is "
        f"the {ZENODO_MD5} Zenodo lists.",
        f"Kept the {len(ts)} rows with Entity_type 'Country' (the European Union, EUU, is published as EU27) and only "
        "their target columns; the GDP, population and emissions context columns were not read.",
        "Took the Tracker's own classification: data_is_nzt marks a net zero or similar end target (net zero, zero "
        "emissions, zero carbon, climate neutral, climate positive, carbon neutral(ity), GHG neutral(ity), carbon "
        "negative, net negative), data_NonNZ_EndTarget another kind of end target, and 'No target at all' none; the "
        "build checks that each flag agrees with the End_target label.",
    ]


def _run_by_country(files: dict[str, InputFile]) -> Result:
    f = files[CSV.key]
    ts = targets(f.path.read_bytes())
    return Result(
        observations=country_observations(ts),
        vintage=VINTAGE,
        date_published=PUBLISHED,
        steps=[
            *_steps(f, ts),
            "Published, for each country, the year of its net zero target with the Tracker's status label as a "
            "dimension, and for countries without one a missing value with the Tracker's end target as the reason. "
            "Each value keeps the Tracker's labels (end target, year, status, year of the last status update) as "
            "its note.",
        ],
    )


def _run_counts(files: dict[str, InputFile]) -> Result:
    f = files[CSV.key]
    ts = targets(f.path.read_bytes())
    return Result(
        observations=count_observations(ts),
        vintage=VINTAGE,
        date_published=PUBLISHED,
        steps=[
            *_steps(f, ts),
            f"Counted the {len(ts)} country rows by status: each of the Tracker's five statuses of a net zero target, "
            "any net zero target (their sum), another kind of end target, and no target. The European Union counts "
            "once, as one of the 198, as in the Tracker's own report; its member states count too.",
        ],
        changes="Counted the countries the Net Zero Tracker records with each status.",
    )


SCOPE_BASIS = (
    "Targets as coded by the Net Zero Tracker from public documents for its Net Zero Stocktake 2025 (deposited 17 "
    "September 2025). 'Net zero' includes the Tracker's similar target names (carbon neutrality, climate neutrality, "
    "net negative and others). The status is the Tracker's: in law, in a policy document, a declaration or pledge, "
    "proposed or in discussion, or achieved by the government's own account."
)


def transforms(paths: Paths) -> list[Transform]:
    status_dim = Dimension(
        id="status", label="Status of the target", values=[DimensionValue(id=s.id, label=s.label) for s in STATUSES]
    )
    return [
        Transform(
            spec=Spec(
                id=BY_COUNTRY,
                title="Net zero targets of national governments: target year and status",
                description="For each national government in the Net Zero Tracker, the year by which it aims to "
                "reach net zero emissions (or carbon or climate neutrality), and how firm the target is: written into "
                "law, set out in a policy document, declared or pledged, proposed or under discussion, or already "
                "achieved by the government's own account. Governments whose end target is not net zero, or that "
                "have no target, are shown without a year.",
                kind="derived",
                unit=Unit(code="year", label="target year", short=""),
                display=Display(decimals=0),
                scope=Scope(
                    geography="198 national governments and self-governing territories in the Net Zero Tracker, "
                    "including the European Union",
                    basis=SCOPE_BASIS,
                ),
                geo_coverage="mixed",
                headline_entity="EU27",
                dimensions=(status_dim,),
                headline_dims=(("status", "in-law"),),
            ),
            inputs=(CSV,),
            run=_run_by_country,
            module_file=Path(__file__),
            validation=Validation(min_rows=190, value_range=(2000.0, 2100.0)),
        ),
        Transform(
            spec=Spec(
                id=COUNTS,
                title="How many national governments have a net zero target, and how firm it is",
                description="The number of national governments in the Net Zero Tracker with a net zero (or carbon "
                "or climate neutrality) target, by how firm the target is, and the number with another kind of end "
                "target or none, as recorded for the Net Zero Stocktake 2025.",
                kind="derived",
                unit=Unit(code="countries", label="national governments", short="governments"),
                display=Display(decimals=0),
                scope=Scope(
                    geography="198 national governments and self-governing territories in the Net Zero Tracker; the "
                    "European Union counts as one of them, as in the Tracker's report, and its member states also "
                    "count",
                    basis=SCOPE_BASIS,
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(Dimension(id="status", label=status_dim.label, values=[ANY, *status_dim.values]),),
                headline_dims=(("status", ANY.id),),
            ),
            inputs=(CSV,),
            run=_run_counts,
            module_file=Path(__file__),
            validation=Validation(min_rows=len(STATUSES) + 1, value_range=(0.0, 250.0)),
            checks=(
                PublisherCheck(
                    source_id=SOURCE,
                    vintage=VINTAGE,
                    entity="WLD",
                    period=PUBLISHED,
                    stated="137",
                    quote=Q_COUNT,
                    url=REPORT_URL,
                    dims=(("status", ANY.id),),
                ),
            ),
        ),
    ]
