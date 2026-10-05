"""Systems Change Lab: the share of its outcome indicators that are on track, off track or heading the wrong way
for limiting warming to 1.5 °C, leaving out every indicator built from International Energy Agency data.

Input: the "Download all available data" export (artifact scl-data-all), a zip with one folder per indicator code,
each holding <code>.csv (values) and <code>_metadata.csv. Only the metadata files are read. Each is a small CSV: a
preamble (download time, suggested citations), a header row starting "Title" (Title, Units, Last Updated, Indicator
Type, Category (factors only), Status (targets only), ..., System, Shift, ...), one row of values, then "Data
source(s):" and a table Name, Provider, URL.

What is used: Systems Change Lab's own progress assessment, the "Status (targets only)" field of each indicator
whose Indicator Type is "Outcome" (enablers and barriers carry no status). No values of the underlying data are
used, so the licences of the original sources are not engaged; the status is Systems Change Lab's work, under its
CC BY 4.0 licence.

IEA exclusion. The Systems Change Lab licensing page says IEA data "falls under the IEA Terms and Conditions". An
indicator is left out when any of its data-source rows mentions the IEA in Name, Provider or URL (the word "IEA",
"International Energy Agency", or iea.org). The count left out is stated in the processing steps.

Published: for the remaining outcome indicators, the percent in each status category, out of all of them (the six
categories add up to 100%), dated by the day the export was downloaded. Statuses are Systems Change Lab's labels as
printed; any other label, or a status on a non-outcome indicator, stops the transform.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path

from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "systems-change-lab"
EXPORT = Input(SOURCE, "scl-data-all")
INDICATOR = "progress.scl.outcome-status"
MEMBER = re.compile(r"(?P<code>[A-Z]+(?:-[A-Z]+)?-\d+)/(?P=code)_metadata\.csv")
STATUS_FIELD = "Status (targets only)"
TYPE_FIELD = "Indicator Type"
OUTCOME, ENABLER = "Outcome", "Enabler and Barrier"
SOURCES_MARK = "Data source(s):"
SOURCES_HEADER = ["Name", "Provider", "URL"]
IEA = re.compile(r"\bIEA\b|International Energy Agency|iea\.org", re.IGNORECASE)

# Status as printed -> (dimension id, label), from best to worst, then no assessment.
STATUSES: dict[str, tuple[str, str]] = {
    "On Track": ("on-track", "On track"),
    "Off Track": ("off-track", "Off track"),
    "Well Off Track": ("well-off-track", "Well off track"),
    "Right Direction": ("right-direction", "Heading in the right direction"),
    "Wrong Direction": ("wrong-direction", "Heading in the wrong direction"),
    "Insufficient Data": ("insufficient-data", "Insufficient data to assess"),
}

UNIT = Unit(code="percent", label="percent of Systems Change Lab outcome indicators", short="%")


class SclFormatError(ValueError):
    pass


def read_metadata(text: str, where: str) -> tuple[dict[str, str], list[list[str]]]:
    rows = list(csv.reader(io.StringIO(text)))
    heads = [i for i, r in enumerate(rows) if r and r[0] == "Title"]
    marks = [i for i, r in enumerate(rows) if r and r[0] == SOURCES_MARK]
    if len(heads) != 1 or len(marks) != 1 or marks[0] < heads[0] + 2:
        raise SclFormatError(f"{where}: expected one 'Title' header row and one '{SOURCES_MARK}' line after it")
    h, values = rows[heads[0]], rows[heads[0] + 1]
    if len(values) != len(h):
        raise SclFormatError(f"{where}: {len(h)} columns in the header, {len(values)} values")
    if rows[marks[0] + 1] != SOURCES_HEADER:
        raise SclFormatError(f"{where}: data-source header {rows[marks[0] + 1]} != {SOURCES_HEADER}")
    sources = [r for r in rows[marks[0] + 2 :] if any(c.strip() for c in r)]
    if not sources or any(len(r) != len(SOURCES_HEADER) for r in sources):
        raise SclFormatError(f"{where}: data sources {sources!r}")
    return dict(zip(h, values, strict=True)), sources


def classify(raw: bytes) -> tuple[dict[str, list[str]], list[str], int]:
    """Outcome indicator codes by status (IEA-sourced left out), the IEA-sourced outcome codes, and the number of
    indicators read."""
    z = zipfile.ZipFile(io.BytesIO(raw))
    members = sorted(n for n in z.namelist() if n.endswith("_metadata.csv"))
    by_status: dict[str, list[str]] = {s: [] for s in STATUSES}
    iea: list[str] = []
    for name in members:
        m = MEMBER.fullmatch(name)
        if m is None:
            raise SclFormatError(f"metadata file {name!r} is not <code>/<code>_metadata.csv")
        meta, sources = read_metadata(z.read(name).decode("utf-8"), name)
        kind, status = meta.get(TYPE_FIELD), meta.get(STATUS_FIELD)
        if kind == ENABLER:
            if status:
                raise SclFormatError(f"{name}: enabler or barrier with a status {status!r}")
            continue
        if kind != OUTCOME:
            raise SclFormatError(f"{name}: indicator type {kind!r}")
        if status not in STATUSES:
            raise SclFormatError(f"{name}: status {status!r} is not one of {list(STATUSES)}")
        if any(IEA.search(cell) for r in sources for cell in r):
            iea.append(m["code"])
        else:
            by_status[status].append(m["code"])
    if not members:
        raise SclFormatError("no metadata files in the export")
    return by_status, iea, len(members)


def observations(by_status: dict[str, list[str]], period: str) -> list[Observation]:
    total = sum(len(v) for v in by_status.values())
    if total == 0:
        raise SclFormatError("no outcome indicators left")
    return [
        Observation(
            entity="WLD",
            period=period,
            value=100 * len(codes) / total,
            note=f"{len(codes)} of {total} outcome indicators: {', '.join(sorted(codes)) or 'none'}.",
            dims={"status": STATUSES[s][0]},
        )
        for s, codes in by_status.items()
    ]


def _run(files: dict[str, InputFile]) -> Result:
    f = files[EXPORT.key]
    by_status, iea, n = classify(f.path.read_bytes())
    accessed = f.snapshot.date_accessed.isoformat()
    total = sum(len(v) for v in by_status.values())
    return Result(
        observations=observations(by_status, accessed),
        vintage=f"export retrieved {accessed}",
        steps=[
            f"Read the {n} indicator metadata files in the Systems Change Lab export (sha256 "
            f"{f.snapshot.sha256[:12]}…, retrieved {accessed}); {total + len(iea)} are outcome indicators with a "
            "progress status, the rest "
            "enablers and barriers, which have none.",
            f"Left out the {len(iea)} outcome indicators whose data sources name the International Energy Agency "
            f"({', '.join(sorted(iea))}).",
            f"Counted the remaining {total} outcome indicators by Systems Change Lab's status and divided each count "
            "by their total, times 100.",
        ],
        changes="indicators counted by progress status and expressed as percent of the outcome indicators not built "
        "from IEA data.",
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id=INDICATOR,
                title="Progress of the shifts needed for 1.5 °C (Systems Change Lab)",
                description="Of the outcome indicators Systems Change Lab tracks across power, buildings, industry, "
                "transport, cities, land, food, freshwater, the circular economy, carbon removal and finance, the "
                "share it assesses as on track for 2030, off track, well off track, heading in the right direction "
                "but too slowly, heading in the wrong direction, or with too little data to say. Indicators built "
                "from International Energy Agency data are left out.",
                kind="derived",
                unit=UNIT,
                display=Display(decimals=0),
                scope=Scope(
                    geography="World (Systems Change Lab's global indicators)",
                    basis="Systems Change Lab's own progress status for each outcome indicator, as listed in its "
                    "data export on the day it was downloaded; enabler and barrier indicators carry no status and "
                    "are not counted.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(
                    Dimension(
                        id="status",
                        label="Progress status",
                        values=[DimensionValue(id=i, label=label) for i, label in STATUSES.values()],
                    ),
                ),
                headline_dims=(("status", "on-track"),),
            ),
            inputs=(EXPORT,),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=len(STATUSES), value_range=(0.0, 100.0)),
        )
    ]
