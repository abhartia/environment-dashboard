"""IPCC AR6 WGI Figure SPM.3 data (Otto, Zhang & Seneviratne 2023, CEDA): in how many of the 45 inhabited AR6 regions
hot extremes, heavy precipitation and agricultural and ecological drought have increased since the 1950s, and with
what confidence the IPCC finds a human contribution.

One indicator, extremes.ipcc-ar6.observed-regions, counted from the three panel files of source ipcc-ar6-wg1-spm3.
Each file has one row per region with two of the IPCC's assessed categories: the type of observed change (Increase,
Decrease, Low agreement in the type of change, Limited data and/or literature) and the confidence in human
contribution to it (High, Medium, Low due to limited agreement, Low due to limited evidence). The indicator counts
the regions in each type of change, and splits the increases by confidence, using the producer's own labels. Counts
are the only thing computed; no region is weighted by area or population, and no regional value is published (the
site shows the world, and regions are not countries).

Reading. The files are BADC-CSV: metadata rows (title, comments, "years 1950 to 2021"), then a data block between
"data" and "end_data" with a column-number row, a header row and one row per region. Panel a writes "Low agreement in
type of change" where panels b and c and the printed figure write "Low agreement in the type of change"; both are
read as the same category, and the step says so. Any other label, a region missing or repeated, a region set that
differs between panels or from the region list in the files' comments, or a span other than the one shared by all
three files stops the build.

What the categories imply. In every file, a region with low agreement in the type of change has "Low due to limited
agreement" confidence and a region with limited data has "Low due to limited evidence"; an increase has High, Medium
or "Low due to limited agreement". The build checks these pairings (so the split loses nothing) and states the
confidence of any decrease in the processing step. "Limited data" and "low agreement" mean the evidence is missing or
mixed, not that nothing changed; confidence in a human contribution is a confidence level, not the size of the
contribution.

Period. The files say "years 1950 to 2021" and the IPCC assessed each region "for the 1950s to the present"; every
count is dated 1950/2021. The description and the publisher checks name that span (SPAN_STATED), and the build stops
if the files state any other.

Checks. The published figure (SPM, p. 10) prints the count of each type of change beside its legend, e.g. "Increase
(41)". Each is a publisher cross-check. The split of increases by confidence is not printed; it is counted from the
IPCC data, and the indicator is kind derived.
"""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, PublisherCheck, Result, Spec, Transform, Validation

SOURCE = "ipcc-ar6-wg1-spm3"
PUBLISHED = "2023-07-03"
"""CEDA catalogue "DOI Publication Date: 2023-07-03" for version v20221116."""
SPM_URL = "https://www.ipcc.ch/report/ar6/wg1/downloads/report/IPCC_AR6_WGI_SPM.pdf"
SPM_PAGE = 10
"""Figure SPM.3 is on page 10 of the SPM PDF (printed page 10)."""
REGION_COUNT = 45
SPAN_STATED = ("1950", "2021")
"""The span all three files state ("years 1950 to 2021"); the words below use it, and the build checks the files."""


@dataclass(frozen=True)
class Panel:
    dim: str
    label: str
    input: Input
    file: str
    title: str
    """What the file's title row says it assesses."""
    printed: str
    """The figure's legend for this panel with its tallies, as printed (SPM p. 10)."""


PANELS: tuple[Panel, ...] = (
    Panel(
        "hot",
        "Hot extremes",
        Input(SOURCE, "panel-a-hot"),
        "SPM3_panel_a.csv",
        "Synthesis of assessment of observed change in hot extremes",
        "Increase (41) Type of observed change in hot extremes Decrease (0) Low agreement in the type of change (2) "
        "Limited data and/or literature (2)",
    ),
    Panel(
        "heavy-rain",
        "Heavy precipitation",
        Input(SOURCE, "panel-b-heavy-precipitation"),
        "SPM3_panel_b.csv",
        "Synthesis of assessment of observed change in heavy precipitation",
        "Type of observed change in heavy precipitation Increase (19) Decrease (0) Low agreement in the type of change "
        "(8) Limited data and/or literature (18)",
    ),
    Panel(
        "drought",
        "Agricultural and ecological drought",
        Input(SOURCE, "panel-c-drought"),
        "SPM3_panel_c.csv",
        "Synthesis of assessment of observed change in agricultural and ecological drought",
        "Increase (12) Decrease (1) Low agreement in the type of change (28) Limited data and/or literature (4)",
    ),
)

# The producer's labels, as written in the files -> our ids.
CHANGES: dict[str, str] = {
    "Increase": "increase",
    "Decrease": "decrease",
    "Low agreement in the type of change": "low-agreement",
    "Low agreement in type of change": "low-agreement",  # panel a's wording
    "Limited data and/or literature": "limited-data",
}
CONFIDENCE: dict[str, str] = {
    "High": "high",
    "Medium": "medium",
    "Low due to limited agreement": "low-agreement",
    "Low due to limited evidence": "low-evidence",
}
CONFIDENCE_LABEL = {v: k for k, v in CONFIDENCE.items()}
ALLOWED: dict[str, frozenset[str]] = {
    "increase": frozenset({"high", "medium", "low-agreement"}),
    "decrease": frozenset({"high", "medium", "low-agreement"}),
    "low-agreement": frozenset({"low-agreement"}),
    "limited-data": frozenset({"low-evidence"}),
}
"""The confidence each type of change takes in the files; any other pairing stops the build."""

# (dimension value id, label, (type of change, confidence or None for any)), in the order shown.
ASSESSMENTS: tuple[tuple[str, str, tuple[str, str | None]], ...] = (
    ("increase", "Increase", ("increase", None)),
    ("increase-high", "Increase, high confidence in a human contribution", ("increase", "high")),
    ("increase-medium", "Increase, medium confidence in a human contribution", ("increase", "medium")),
    (
        "increase-low",
        "Increase, low confidence in a human contribution (due to limited agreement)",
        ("increase", "low-agreement"),
    ),
    ("decrease", "Decrease", ("decrease", None)),
    ("low-agreement", "Low agreement in the type of change", ("low-agreement", None)),
    ("limited-data", "Limited data and/or literature", ("limited-data", None)),
)
EXCLUSIVE = ("increase", "decrease", "low-agreement", "limited-data")
"""The four types of change: every region is in exactly one, so their counts add up to the number of regions."""

HEADER = ["IPCC AR6 WGI reference regions", "Type of observed change", "Confidence in human contribution"]
SPAN = re.compile(r"^years (\d{4}) to (\d{4})$")
WHOLE_REGION = "All assessments are made for each region as a whole and for the 1950s to the present."
REGION_LIST_PREFIX = "IPCC AR6 WGI reference regions:"
REGION_CODE = re.compile(r"\b([A-Z]{2,4}) \(")
URL = re.compile(r"^https://dap\.ceda\.ac\.uk/badc/ar6_wg1/data/spm/spm_03/(v\d{8})/([^/]+)$")
PRINTED_TALLY = re.compile(
    r"(Increase|Decrease|Low agreement in the type of change|Limited data and/or literature) \((\d+)\)"
)

EXTREME_DIM = Dimension(id="extreme", label="Extreme", values=[DimensionValue(id=p.dim, label=p.label) for p in PANELS])
ASSESSMENT_DIM = Dimension(
    id="assessment",
    label="Type of observed change since the 1950s, and confidence in a human contribution",
    values=[DimensionValue(id=d, label=label) for d, label, _ in ASSESSMENTS],
)
REGIONS = Unit(code="regions", label=f"of the {REGION_COUNT} inhabited IPCC AR6 regions", short="regions")


class Spm3FormatError(ValueError):
    pass


@dataclass(frozen=True)
class PanelData:
    title: str
    span: tuple[str, str]
    listed: frozenset[str]
    """The region codes the comments list."""
    rows: dict[str, tuple[str, str]]
    """Region code -> (type of change id, confidence id)."""
    labels: frozenset[str]
    """The type-of-change labels as written in this file."""


def read_badc(raw: bytes, name: str) -> PanelData:
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8"))))
    for r in rows:
        while r and r[-1] == "":
            r.pop()
    if not rows or rows[0][:3] != ["Conventions", "G", "BADC-CSV"]:
        raise Spm3FormatError(f"{name}: not a BADC-CSV file")
    try:
        start = rows.index(["data"])
        end = rows.index(["end_data"])
    except ValueError:
        raise Spm3FormatError(f"{name}: no data ... end_data block") from None
    meta = rows[:start]
    titles = [r[2] for r in meta if r[:2] == ["title", "G"]]
    comments = [",".join(r[2:]) for r in meta if r[:2] == ["comments", "G"]]
    spans = [m.groups() for c in comments if (m := SPAN.match(c))]
    listed = [c for c in comments if c.startswith(REGION_LIST_PREFIX)]
    if len(titles) != 1 or len(spans) != 1 or len(listed) != 1:
        raise Spm3FormatError(f"{name}: expected one title, one 'years ... to ...' and one region-list comment")
    if not any(WHOLE_REGION in c for c in comments):
        raise Spm3FormatError(f"{name}: the comment {WHOLE_REGION!r} is missing")
    if rows[start + 1] != ["1", "2", "3"] or rows[start + 2] != HEADER:
        raise Spm3FormatError(f"{name}: data block header {rows[start + 1 : start + 3]} != expected {HEADER}")
    out: dict[str, tuple[str, str]] = {}
    labels: set[str] = set()
    for r in rows[start + 3 : end]:
        if len(r) != 3:
            raise Spm3FormatError(f"{name}: row {r} does not have 3 cells")
        region, change, confidence = r
        if region in out:
            raise Spm3FormatError(f"{name}: region {region} appears twice")
        if change not in CHANGES or confidence not in CONFIDENCE:
            raise Spm3FormatError(f"{name}: {region} has unknown categories ({change!r}, {confidence!r})")
        c, k = CHANGES[change], CONFIDENCE[confidence]
        if k not in ALLOWED[c]:
            raise Spm3FormatError(f"{name}: {region} pairs {change!r} with {confidence!r}; re-read the categories")
        out[region] = (c, k)
        labels.add(change)
    return PanelData(
        title=titles[0],
        span=spans[0],
        listed=frozenset(REGION_CODE.findall(listed[0])),
        rows=out,
        labels=frozenset(labels),
    )


def counts(data: PanelData) -> dict[str, int]:
    """The count of regions for each assessment id."""
    tally = Counter(data.rows.values())
    out: dict[str, int] = {}
    for d, _, (change, confidence) in ASSESSMENTS:
        out[d] = sum(n for (c, k), n in tally.items() if c == change and (confidence is None or k == confidence))
    if sum(out[d] for d in EXCLUSIVE) != len(data.rows):
        raise Spm3FormatError(f"the types of change count {sum(out[d] for d in EXCLUSIVE)}, not {len(data.rows)}")
    if out["increase"] != out["increase-high"] + out["increase-medium"] + out["increase-low"]:
        raise Spm3FormatError("the increases split by confidence do not add up to the increases")
    return out


def read_panels(files: dict[str, InputFile]) -> tuple[str, tuple[str, str], dict[str, PanelData]]:
    """(version, span, {panel dim: data}) after checking the three files belong together."""
    versions: set[str] = set()
    out: dict[str, PanelData] = {}
    for p in PANELS:
        f = files[p.input.key]
        m = URL.match(str(f.snapshot.url) if f.snapshot.url else "")
        if not m or m.group(2) != p.file:
            raise Spm3FormatError(f"{p.input.key}: {f.snapshot.url} is not {p.file} of the Figure SPM.3 dataset")
        versions.add(m.group(1))
        data = read_badc(f.path.read_bytes(), p.file)
        if not data.title.startswith(p.title):
            raise Spm3FormatError(f"{p.file}: title {data.title!r} does not start {p.title!r}")
        if set(data.rows) != data.listed or len(data.rows) != REGION_COUNT:
            raise Spm3FormatError(
                f"{p.file}: {len(data.rows)} region rows; the comments list {len(data.listed)}; expected "
                f"{REGION_COUNT} of each, the same set"
            )
        out[p.dim] = data
    if len(versions) != 1:
        raise Spm3FormatError(f"the panels are from different versions: {sorted(versions)}")
    spans = {d.span for d in out.values()}
    sets = {frozenset(d.rows) for d in out.values()}
    if len(spans) != 1 or len(sets) != 1:
        raise Spm3FormatError(f"the panels differ in span {sorted(spans)} or in their regions")
    (version,) = versions
    (span,) = spans
    if span != SPAN_STATED:
        raise Spm3FormatError(f"the files say years {span[0]} to {span[1]}, but the words say {SPAN_STATED}")
    return version, span, out


def read_printed(text: str) -> dict[str, int]:
    """'Increase (41) ... Limited data and/or literature (2)' -> {type of change id: tally}."""
    found = PRINTED_TALLY.findall(text)
    out = {CHANGES[label]: int(n) for label, n in found}
    if len(found) != len(EXCLUSIVE) or set(out) != set(EXCLUSIVE):
        raise Spm3FormatError(f"{text!r} does not print one tally for each type of change")
    return out


def _checks() -> tuple[PublisherCheck, ...]:
    return tuple(
        PublisherCheck(
            source_id=SOURCE,
            vintage="v20221116",
            entity="WLD",
            period="/".join(SPAN_STATED),
            stated=str(n),
            quote=p.printed,
            url=SPM_URL,
            dims=(("extreme", p.dim), ("assessment", change)),
        )
        for p in PANELS
        for change, n in read_printed(p.printed).items()
    )


def _run(files: dict[str, InputFile]) -> Result:
    version, (first, last), panels = read_panels(files)
    period = f"{first}/{last}"
    tallies = {p.dim: counts(panels[p.dim]) for p in PANELS}
    obs = [
        Observation(
            entity="WLD",
            period=period,
            value=float(tallies[p.dim][d]),
            dims={"extreme": p.dim, "assessment": d},
        )
        for p in PANELS
        for d, _, _ in ASSESSMENTS
    ]
    decreases = "; ".join(
        f"{p.label.lower()}: {region} ({CONFIDENCE_LABEL[k]})"
        for p in PANELS
        for region, (c, k) in sorted(panels[p.dim].rows.items())
        if c == "decrease"
    )
    wordings = "; ".join(
        f"{p.file} {label!r}"
        for p in PANELS
        for label in sorted(panels[p.dim].labels)
        if CHANGES[label] == "low-agreement"
    )
    return Result(
        observations=obs,
        vintage=version,
        date_published=PUBLISHED,
        changes="counted the regions in each of the IPCC's assessed categories.",
        steps=[
            f"Read the three panel files of Figure SPM.3 (CEDA version {version}: "
            f"{', '.join(p.file for p in PANELS)}), BADC-CSV, one row per region. Checked that each has the "
            f"{REGION_COUNT} inhabited AR6 regions listed in its comments, once each, the same in all three; that "
            f"all three say 'years {first} to {last}' and that each region is assessed as a whole for the 1950s to "
            f"the present. Every count is dated {period}.",
            "Counted the regions in each type of observed change (Increase, Decrease, Low agreement in the type of "
            "change, Limited data and/or literature), and split the increases by the confidence in a human "
            "contribution (High, Medium, Low due to limited agreement), using the producer's labels. The files word "
            f"the low-agreement category as {wordings}; each is read as the printed figure's 'Low agreement in "
            "the type of change'. Checked that the four types add up to the regions and the split adds "
            "up to the increases. No region is weighted by area or population.",
            "Checked the pairings the split relies on: every region with low agreement in the type of change has "
            "'Low due to limited agreement' confidence, every region with limited data has 'Low due to limited "
            "evidence', and every increase has High, Medium or 'Low due to limited agreement'. Regions with a "
            f"decrease, and their confidence: {decreases or 'none'}.",
            f"Checked against the published figure (IPCC AR6 WGI SPM, p. {SPM_PAGE}): the count of each type of "
            "change printed beside its legend is a publisher cross-check. The split of increases by confidence is "
            "not printed there; it is counted from the IPCC data.",
        ],
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="extremes.ipcc-ar6.observed-regions",
                title="Regions where hot extremes, heavy rain and drought have increased since the 1950s, with the "
                "IPCC's confidence in a human contribution (IPCC AR6)",
                description=f"Of the {REGION_COUNT} inhabited regions the IPCC uses, how many have seen an increase, "
                "a decrease, low agreement in the type of change, or too little data and literature to say, in hot "
                "extremes, heavy precipitation and agricultural and ecological drought from the 1950s to "
                f"{SPAN_STATED[1]}, as assessed in the IPCC Sixth Assessment Report (2021, Figure SPM.3). Increases "
                "are split by the IPCC's confidence that human influence contributed: high, medium, or low because "
                "studies disagree. Calculated by counting the regions in the IPCC data; the totals of each type of "
                "change match the counts printed on the published figure, and the split by confidence is counted "
                "from the same data. Regions differ in size and population, and each is assessed as a whole. "
                "'Limited data' and 'low agreement' mean the evidence is missing or mixed, not that nothing changed, "
                "and a confidence level says how sure the IPCC is that people contributed, not how large the "
                "contribution was.",
                kind="derived",
                unit=REGIONS,
                display=Display(decimals=0),
                scope=Scope(
                    geography=f"{REGION_COUNT} inhabited IPCC AR6 regions",
                    basis="Counts of the IPCC AR6 WGI reference regions in each assessed category, for the world; no "
                    "regional values are published. Expert assessment of observed change since the 1950s (files: "
                    f"years {SPAN_STATED[0]} to {SPAN_STATED[1]}), each region as a whole. Categories and labels are "
                    "the IPCC's; only counts are computed.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(EXTREME_DIM, ASSESSMENT_DIM),
                headline_dims=(("extreme", "hot"), ("assessment", "increase")),
            ),
            inputs=tuple(p.input for p in PANELS),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=len(PANELS) * len(ASSESSMENTS), value_range=(0.0, float(REGION_COUNT))),
            checks=_checks(),
        ),
    ]
