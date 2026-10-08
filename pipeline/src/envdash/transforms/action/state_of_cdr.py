"""The State of Carbon Dioxide Removal, 3rd Edition (2026), chapter 7: how much CO2 is actually being removed from the
atmosphere each year, by novel methods into durable storage and by forests.

Inputs (registry entry state-of-cdr-3, CC BY 4.0): SoCDR-Edition-3-Chapter-7.csv (UTF-8 with a byte-order mark, one
value per row), the chapter 7 PDF and its technical annex. The PDFs are read only for the sentences checked below.

Rows used, all with Region "World" and Unit "Mt CO2/yr":
- novel CDR: Indicator "Global Novel CDR by year" (Method "All", the report's own world total) and "Global Novel CDR
  by method and year" (one row per method and year, 2017-2025). A method has rows only from the year the report
  first records it; years without a row are not published (nothing is filled).
- conventional CDR: Indicator "Conventional CDR from bookkeeping models by country and year" with Country empty
  (the world rows): the three bookkeeping models BLUE, LUCE and OSCAR and their "Mean of models", 2005-2024, for
  afforestation, reforestation and forest management.
Nothing else in the file is read: not the country rows, the transfers into wood products, the pipeline of planned
capacity, nor the estimate from national inventories. A method, model or label this transform does not know stops the
build.

What novel CDR counts (technical annex, p. 14, checked at every build): projects with CDR data published in
registries, CDR.fyi or government databases; for direct air capture "we include only those where captured CO2 is
demonstrably delivered to durable storage"; and "For active projects not listed on registries, we use the annual
delivered CDR reported in CDR.fyi, which represent net values." CDR.fyi's own terms do not allow republishing its
data, so whether the report's CC BY covers those values is an open question (registry entry and docs/sources.md).

Values are published as printed. The world total ("All") is the report's own, never a sum of ours. A processing step
names the years in which the methods' rows do not add up to it (to the total's printed precision); in the file of 27
May 2026 the total is 0.43 for each of 2017-2020 while the method rows for 2017-2019 hold only BECCS (0.50665,
0.525002, 0.51978). Both are published as the file gives them; the difference is an open question in
docs/sources.md, not resolved here.

Publisher check: chapter 7, p. 2: "Activity from novel CDR methods is estimated to total 2.04 MtCO2 globally in 2025,
up from 1.4 MtCO2 in 2023."
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation
from pathlib import Path

from envdash import textmatch
from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, PublisherCheck, Result, Spec, Transform, Validation

SOURCE = "state-of-cdr-3"
CSV = Input(SOURCE, "chapter-7-csv")
CHAPTER = Input(SOURCE, "chapter-7-pdf")
ANNEX = Input(SOURCE, "technical-annex-ch7")
NOVEL = "cdr.socdr-3.novel-by-method"
CONVENTIONAL = "cdr.socdr-3.conventional-forest"
VINTAGE = "The State of Carbon Dioxide Removal, 3rd Edition (2026)"
CHAPTER_URL = "https://www.stateofcdr.org/asset/SoCDR-Ed3_Chapter-7_Final.pdf"

COLUMNS = [
    "Chapter",
    "Country",
    "Region",
    "Model",
    "Variable",
    "Type",
    "Indicator",
    "Method",
    "Unit",
    "Value",
    "Year",
    "Edition",
    "Notes",
    "Quality",
    "Year Range",
    "Data portal reference",
]
UNIT = "Mt CO2/yr"
NOVEL_TOTAL = "Global Novel CDR by year"
NOVEL_BY_METHOD = "Global Novel CDR by method and year"
CONVENTIONAL_WORLD = "Conventional CDR from bookkeeping models by country and year"
FOREST = "Afforestation, reforestation, forest management"

ALL = ("all", "All novel methods", "All")
METHODS = (
    ("biochar", "Biochar added to soils", "Biochar Soil Amendment"),
    ("beccs", "Bioenergy with carbon capture and storage (BECCS)", "Bioenergy with Carbon Capture and Storage"),
    ("biomass-burial", "Biomass burial", "Biomass Burial"),
    ("mineral-products", "Mineral products", "Mineral Products"),
    ("enhanced-weathering", "Enhanced rock weathering", "Enhanced Weathering"),
    ("bio-oil-storage", "Bio-oil storage", "Bio-Oil Storage"),
    ("alkalinity-enhancement", "Alkalinity enhancement of water bodies", "Alkalinity Enhancement of Water Bodies"),
    ("daccs", "Direct air capture with storage (DACCS)", "Direct Air Carbon Capture and Storage"),
    ("biomass-sinking", "Biomass sinking", "Biomass Sinking"),
    ("other", "Other novel methods", "Other"),
)
MODELS = (
    ("mean", "Mean of the three models", "Mean of models"),
    ("blue", "BLUE", "BLUE"),
    ("luce", "LUCE", "LUCE"),
    ("oscar", "OSCAR", "OSCAR"),
)

CHAPTER_PAGE = 2
Q_TOTAL = (
    "Activity from novel CDR methods is estimated to total 2.04 MtCO2 globally in 2025, up from 1.4 MtCO2 in 2023."
)
ANNEX_PAGE = 14
ANNEX_QUOTES = (
    "For active projects not listed on registries, we use the annual delivered CDR reported in CDR.fyi, which "
    "represent net values.",
    "we include only those where captured CO2 is demonstrably delivered to durable storage.",
)


class StateOfCdrFormatError(ValueError):
    pass


def read_rows(raw: bytes) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    if reader.fieldnames != COLUMNS:
        raise StateOfCdrFormatError(f"columns {reader.fieldnames} != {COLUMNS}")
    return list(reader)


def _value(r: dict[str, str]) -> float:
    try:
        v = Decimal(r["Value"])
    except InvalidOperation:
        raise StateOfCdrFormatError(f"{r['Indicator']} {r['Method']} {r['Year']}: value {r['Value']!r}") from None
    if r["Unit"] != UNIT or r["Region"] != "World" or not (len(r["Year"]) == 4 and r["Year"].isdigit()):
        raise StateOfCdrFormatError(f"unexpected unit, region or year in {r!r}")
    return float(v)


def novel_observations(rows: list[dict[str, str]]) -> list[Observation]:
    by_name = {name: mid for mid, _, name in METHODS}
    found: dict[tuple[str, str], float] = {}
    for r in rows:
        if r["Indicator"] == NOVEL_TOTAL:
            if r["Method"] != ALL[2] or r["Country"] != "World" or r["Variable"] != "Novel":
                raise StateOfCdrFormatError(f"unexpected {NOVEL_TOTAL} row {r!r}")
            key = (ALL[0], r["Year"])
        elif r["Indicator"] == NOVEL_BY_METHOD:
            if r["Method"] not in by_name or r["Country"] != "World" or r["Variable"] != "Novel":
                raise StateOfCdrFormatError(
                    f"{NOVEL_BY_METHOD}: method {r['Method']!r} is not one this transform reads"
                )
            key = (by_name[r["Method"]], r["Year"])
        else:
            continue
        if key in found:
            raise StateOfCdrFormatError(f"two rows for novel CDR {key}")
        found[key] = _value(r)
    order = [ALL[0], *(m for m, _, _ in METHODS)]
    keys = sorted(found, key=lambda k: (order.index(k[0]), k[1]))
    return [Observation(entity="WLD", period=y, value=found[(m, y)], dims={"method": m}) for m, y in keys]


def totals_disagree(obs: list[Observation]) -> list[str]:
    """Years whose methods do not add up to the report's total within half the total's last printed digit."""
    total = {o.period: o.value for o in obs if o.dims["method"] == ALL[0]}
    parts: dict[str, Decimal] = {}
    for o in obs:
        if o.dims["method"] != ALL[0] and o.period is not None and o.value is not None:
            parts[o.period] = parts.get(o.period, Decimal(0)) + Decimal(repr(o.value))
    out = []
    for year, t in sorted(total.items()):
        assert year is not None and t is not None
        exp = Decimal(repr(t)).as_tuple().exponent
        assert isinstance(exp, int)
        if abs(parts.get(year, Decimal(0)) - Decimal(repr(t))) > Decimal(5) * Decimal(10) ** (exp - 1):
            out.append(year)
    return out


def conventional_observations(rows: list[dict[str, str]]) -> list[Observation]:
    by_name = {name: mid for mid, _, name in MODELS}
    found: dict[tuple[str, str], float] = {}
    for r in rows:
        if r["Indicator"] != CONVENTIONAL_WORLD or r["Country"] != "" or r["Region"] != "World":
            continue
        if r["Model"] not in by_name or r["Method"] != FOREST or r["Variable"] != "Conventional":
            raise StateOfCdrFormatError(f"unexpected world conventional CDR row {r!r}")
        key = (by_name[r["Model"]], r["Year"])
        if key in found:
            raise StateOfCdrFormatError(f"two rows for conventional CDR {key}")
        found[key] = _value(r)
    order = [m for m, _, _ in MODELS]
    keys = sorted(found, key=lambda k: (order.index(k[0]), k[1]))
    return [Observation(entity="WLD", period=y, value=found[(m, y)], dims={"model": m}) for m, y in keys]


def _pdf_page(f: InputFile, page: int) -> str:
    pages = textmatch.pdf_pages_text(f.path.read_bytes())
    if len(pages) < page:
        raise StateOfCdrFormatError(f"{f.snapshot.artifact_id} has {len(pages)} pages, fewer than {page}")
    return pages[page - 1]


def check_documents(files: dict[str, InputFile]) -> None:
    if not textmatch.contains(_pdf_page(files[CHAPTER.key], CHAPTER_PAGE), Q_TOTAL):
        raise StateOfCdrFormatError(f"chapter 7 p. {CHAPTER_PAGE} no longer says {Q_TOTAL!r}")
    annex = _pdf_page(files[ANNEX.key], ANNEX_PAGE)
    for q in ANNEX_QUOTES:
        if not textmatch.contains(annex, q):
            raise StateOfCdrFormatError(f"technical annex p. {ANNEX_PAGE} no longer says {q!r}")


def _read_step(f: InputFile) -> str:
    return (
        f"Read SoCDR-Edition-3-Chapter-7.csv (fetched {f.snapshot.date_accessed}, Last-Modified "
        f"{f.snapshot.last_modified}, sha256 {f.snapshot.sha256[:12]}…), UTF-8 with a byte-order mark."
    )


def _run_novel(files: dict[str, InputFile]) -> Result:
    check_documents(files)
    f = files[CSV.key]
    obs = novel_observations(read_rows(f.path.read_bytes()))
    disagree = totals_disagree(obs)
    return Result(
        observations=obs,
        vintage=VINTAGE,
        date_published="2026-06",
        steps=[
            _read_step(f),
            f"Kept the world rows '{NOVEL_TOTAL}' (the report's total) and '{NOVEL_BY_METHOD}', in million tonnes of "
            "CO2 a year, as printed. A method appears from the first year the report records it; no year is filled.",
            "Found in the technical annex (p. 14) that novel CDR counts only removals with published data, direct air "
            "capture only where the CO2 reaches durable storage, and CDR.fyi's delivered values for projects not on "
            "registries; and on p. 2 of chapter 7 the 2025 world total.",
            "Compared the report's total with its method rows for each year (to the total's printed precision): "
            + (
                "they differ in " + ", ".join(disagree) + "; both are published as printed."
                if disagree
                else "they agree in every year."
            ),
        ],
    )


def _run_conventional(files: dict[str, InputFile]) -> Result:
    check_documents(files)
    f = files[CSV.key]
    obs = conventional_observations(read_rows(f.path.read_bytes()))
    return Result(
        observations=obs,
        vintage=VINTAGE,
        date_published="2026-06",
        steps=[
            _read_step(f),
            f"Kept the world rows of '{CONVENTIONAL_WORLD}' (afforestation, reforestation and forest management): the "
            "bookkeeping models BLUE, LUCE and OSCAR and their mean, as printed.",
        ],
    )


MT_YR = Unit(code="MtCO2/yr", label="million tonnes of carbon dioxide per year", short="Mt CO₂/yr")


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id=NOVEL,
                title="Carbon dioxide removed by novel methods, by method",
                description="How much CO2 newer removal methods actually took out of the atmosphere and put into "
                "durable storage each year, world total and by method (biochar, bioenergy with carbon capture and "
                "storage, direct air capture with storage, enhanced rock weathering and others), as compiled project "
                "by project for The State of Carbon Dioxide Removal. These are removals delivered, not capacity.",
                kind="series",
                unit=MT_YR,
                display=Display(decimals=2),
                scope=Scope(
                    geography="World",
                    basis="Removals delivered to durable storage, compiled from registries, government data and "
                    "CDR.fyi; direct air capture only where storage is confirmed. Net of reported losses where the "
                    "source gives them.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(
                    Dimension(
                        id="method",
                        label="Method",
                        values=[DimensionValue(id=ALL[0], label=ALL[1])]
                        + [DimensionValue(id=i, label=lbl) for i, lbl, _ in METHODS],
                    ),
                ),
                headline_dims=(("method", ALL[0]),),
            ),
            inputs=(CSV, CHAPTER, ANNEX),
            run=_run_novel,
            module_file=Path(__file__),
            validation=Validation(min_rows=40, value_range=(0.0, 100.0)),
            checks=(
                PublisherCheck(
                    source_id=SOURCE,
                    vintage=VINTAGE,
                    entity="WLD",
                    period="2025",
                    stated="2.04",
                    quote=Q_TOTAL,
                    url=CHAPTER_URL,
                    dims=(("method", ALL[0]),),
                ),
            ),
        ),
        Transform(
            spec=Spec(
                id=CONVENTIONAL,
                title="Carbon dioxide removed by forests (conventional removal)",
                description="How much CO2 forests that people plant, restore or manage took out of the atmosphere "
                "each year worldwide, as estimated by three land-use bookkeeping models and their mean for The State "
                "of Carbon Dioxide Removal.",
                kind="series",
                unit=MT_YR,
                display=Display(decimals=0),
                scope=Scope(
                    geography="World",
                    basis="Conventional CDR from afforestation, reforestation and forest management, from the "
                    "bookkeeping models BLUE, LUCE and OSCAR and their mean, as compiled for chapter 7.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(
                    Dimension(
                        id="model",
                        label="Model",
                        values=[DimensionValue(id=i, label=lbl) for i, lbl, _ in MODELS],
                    ),
                ),
                headline_dims=(("model", "mean"),),
            ),
            inputs=(CSV, CHAPTER, ANNEX),
            run=_run_conventional,
            module_file=Path(__file__),
            validation=Validation(min_rows=60, value_range=(0.0, 10_000.0)),
        ),
    ]
