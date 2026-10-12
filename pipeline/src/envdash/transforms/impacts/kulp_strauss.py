"""Kulp & Strauss (2019): people living on land below the local high-tide line, and below the local once-a-year
coastal flood level, world and by country, from the CoastalDEM elevation model: at today's sea level and with the sea
levels projected for 2050 and 2100.

Inputs: Supplementary Data 1 (kulp-strauss-2019/supplementary-data-1, a CSV in millions of people), the description
of the supplementary files (kulp-strauss-2019/supplementary-descriptions, one page) and the corrected article
(kulp-strauss-2019/article-pdf, 12 pages).

What is read. The CSV has one row per place and sea level, with the 5th, 50th and 95th percentiles of four elevation
models for two exposures: Perm (below the future local high tide line) and RL1 (below that line plus the local
1-year coastal flood return level). The transform requires exactly the 27 column headings below and the 13 rows of
Place "World" in the order below, and reads only the three CoastalDEM columns of each exposure. Each number is
published as printed (a decimal, nothing rounded): the median as the value and the 5th and 95th percentiles as the
lower and upper ends of a 90% interval, which the article calls a CI for both projection sets ("90% credible
intervals when derived from K14, and 90% intervals from simulation frequency distributions when derived from K17").
The present-day row prints each median with one trailing space and "--" for both percentiles; it has no range.

Time. Every row counts the people of LandScan 2010, so the present-day row is dated 2010 (its sea level is that of
2000, the projections' zero) and is final; the projected rows are dated 2050 and 2100, the years of their sea
levels, and are projections. The population stays at its 2010 distribution in every row.

Which projections. The abstract's lead figure, 190 M (150-250 M) below high tide by 2100 under low emissions, is K14
(Kopp et al. 2014), the set the article calls probabilistic and closely aligned with IPCC findings; its high end, up
to 630 M below the annual flood level by 2100 and up to 340 M by mid-century, is the 95th percentile of K17 (Kopp et
al. 2017, with unstable Antarctic ice) under RCP8.5. Both sets are needed to match the paper, so both are published
under a `projection` dimension and never mixed; the present day carries projection "none". The build checks that the
abstract's figures are these cells and not the other set's.

Checks against the corrected article (Author Correction of 12 December 2019, which changed text numbers and one cell
of Table 1 but not the Supplementary Data). Page 1 must be marked "Corrected: Author correction". Table 1 (page 3)
prints the global CoastalDEM total for every projection, emissions scenario, exposure and year as "median (5th-95th)";
each of its 24 cells must equal the CSV's three numbers exactly, so a PDF still printing the superseded
"500 (390-640)" stops the build. The method sentences that the scope relies on (defences not counted, 2010
population, the 2000 baseline, what K14 and K17 are, the intervals, the CoastalDEM coverage) must be on their pages of
the article, and the file description's sentences on units, exposures and percentiles in the description PDF. The
publisher cross-checks quote the corrected text.

Countries. The `-by-country` indicators publish the World rows and the 134 country and territory rows, each place
with the World's 13 sea levels in the same order, in people (the printed millions times one million, exact), since
country values as small as 0.01 million cannot be shown in whole millions. Place names resolve to entities through
the source's alias table in envdash/geo.py; the SIDS rows (the authors' group of small island developing states) are
left out by name. The file omits places whose largest exposure is under 0.01 million: such a country has no value.

Not read: the SRTM, JAXA and MERITDEM columns, the SIDS rows, and Supplementary Data 2-5 (see
pipeline/sources/kulp-strauss-2019.yaml).
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from envdash import geo, textmatch
from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, PublisherCheck, Result, Spec, Transform, Validation

SOURCE = "kulp-strauss-2019"
CSV = Input(SOURCE, "supplementary-data-1")
DESCRIPTIONS = Input(SOURCE, "supplementary-descriptions")
ARTICLE = Input(SOURCE, "article-pdf")
VINTAGE = "Nature Communications 10: 4844 (2019), corrected 12 December 2019"
PUBLISHED = "2019-10-29"
ARTICLE_URL = "https://www.nature.com/articles/s41467-019-12808-z.pdf"
ENTITY = "WLD"
PLACE = "World"
WORLD_TOTAL = "6800"
"""The World rows' Total column (millions), the 2010 population Table 1's footnote gives as roughly 6800 million."""
PRESENT_PERIOD = "2010"

DEMS = ("CoastalDEM", "SRTM", "JAXA", "MERITDEM")
HEADER = ["Place", "Total", "SeaLevel"] + [
    f"{dem}_{exposure}_{p}" for dem in DEMS for exposure in ("Perm", "RL1") for p in ("p5", "p50", "p95")
]


@dataclass(frozen=True)
class SeaLevel:
    label: str
    """The SeaLevel cell as printed."""
    projection: str
    scenario: str
    period: str


PRESENT = SeaLevel("Present day", "none", "present", PRESENT_PERIOD)
# The World rows, in the file's order.
SEA_LEVELS: tuple[SeaLevel, ...] = (
    PRESENT,
    *(
        SeaLevel(f"{projection.upper()}_{scenario}_{year}", projection, scenario, year)
        for projection in ("k14", "k17")
        for scenario in ("rcp26", "rcp45", "rcp85")
        for year in ("2050", "2100")
    ),
)

PROJECTIONS: dict[str, str] = {
    "none": "None: today's sea level",
    "k14": "K14 (Kopp et al. 2014): probabilistic, closely aligned with IPCC findings",
    "k17": "K17 (Kopp et al. 2017): unstable Antarctic ice, not probabilistic",
}
SCENARIOS: dict[str, str] = {
    "present": "Today's sea level (that of 2000)",
    "rcp26": "RCP2.6 (low emissions)",
    "rcp45": "RCP4.5 (moderate emissions)",
    "rcp85": "RCP8.5 (high emissions)",
}


@dataclass(frozen=True)
class Exposure:
    column: str
    """The CSV's exposure label (Perm or RL1)."""
    table: str
    """The same exposure in Table 1's Frequency column."""
    indicator: str


PERM = Exposure("Perm", "Permanent", "coastal.kulp-strauss-2019.below-high-tide")
RL1 = Exposure("RL1", "RL1", "coastal.kulp-strauss-2019.annual-flood")
EXPOSURES = (PERM, RL1)


class KulpStraussFormatError(ValueError):
    pass


# --- Supplementary Data 1 -----------------------------------------------------------------------------------------

NUMBER = re.compile(r"\d+(\.\d+)?")
PRESENT_MEDIAN = re.compile(r"(\d+(?:\.\d+)?) ")
NO_RANGE = "--"


@dataclass(frozen=True)
class Cell:
    """One exposure's CoastalDEM percentiles in one row, as printed (no range for the present day)."""

    p5: str | None
    p50: str
    p95: str | None


@dataclass(frozen=True)
class WorldRow:
    sea_level: SeaLevel
    cells: dict[str, Cell]
    """Exposure column (Perm, RL1) -> its CoastalDEM cell."""


def _cell(row: dict[str, str], exposure: str, present: bool, where: str) -> Cell:
    p5, p50, p95 = (row[f"CoastalDEM_{exposure}_{p}"] for p in ("p5", "p50", "p95"))
    if present:
        m = PRESENT_MEDIAN.fullmatch(p50)
        if p5 != NO_RANGE or p95 != NO_RANGE or not m:
            raise KulpStraussFormatError(
                f"{where} CoastalDEM {exposure}: expected '--', a median with one trailing space and '--', got "
                f"{p5!r}, {p50!r}, {p95!r}"
            )
        return Cell(None, m.group(1), None)
    for v in (p5, p50, p95):
        if not NUMBER.fullmatch(v):
            raise KulpStraussFormatError(f"{where} CoastalDEM {exposure}: {v!r} is not a printed number")
    if not Decimal(p5) <= Decimal(p50) <= Decimal(p95):
        raise KulpStraussFormatError(f"{where} CoastalDEM {exposure}: percentiles {p5}, {p50}, {p95} out of order")
    return Cell(p5, p50, p95)


def _rows(raw: bytes) -> list[dict[str, str]]:
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8"), newline="")))
    if not rows or rows[0] != HEADER:
        raise KulpStraussFormatError(f"column headings {rows[0] if rows else None} != {HEADER}")
    for i, r in enumerate(rows[1:], start=2):
        if len(r) != len(HEADER):
            raise KulpStraussFormatError(f"line {i} has {len(r)} cells, not {len(HEADER)}")
    return [dict(zip(HEADER, r, strict=True)) for r in rows[1:]]


def _place(rows: list[dict[str, str]], place: str) -> list[WorldRow]:
    """One place's 13 rows, in the World rows' order of sea levels, as CoastalDEM cells."""
    labels = [r["SeaLevel"] for r in rows]
    if labels != [s.label for s in SEA_LEVELS]:
        raise KulpStraussFormatError(f"{place} sea levels {labels} != {[s.label for s in SEA_LEVELS]}")
    return [
        WorldRow(s, {e.column: _cell(r, e.column, s is PRESENT, f"{place} {s.label!r}") for e in EXPOSURES})
        for r, s in zip(rows, SEA_LEVELS, strict=True)
    ]


def read_world(raw: bytes) -> list[WorldRow]:
    """The 13 World rows' CoastalDEM cells, checked against the expected headings, sea levels and total."""
    world = [r for r in _rows(raw) if r["Place"] == PLACE]
    for r in world:
        if r["Total"] != WORLD_TOTAL:
            raise KulpStraussFormatError(
                f"World {r['SeaLevel']!r}: Total {r['Total']!r}, not {WORLD_TOTAL} (million, 2010)"
            )
    return _place(world, PLACE)


NOT_PLACES = ("SIDS",)
"""Rows that are no country: the authors' group of small island developing states, left out (World is read apart)."""


def read_places(raw: bytes) -> dict[str, list[WorldRow]]:
    """Each country's or territory's 13 rows, by our entity code: its Place name resolved through the source's alias
    table and the entity crosswalk (never guessed), its rows together and in the World rows' order."""
    rows = [r for r in _rows(raw) if r["Place"] not in (PLACE, *NOT_PLACES)]
    names: list[str] = []
    for r in rows:
        if not names or names[-1] != r["Place"]:
            if r["Place"] in names:
                raise KulpStraussFormatError(f"the rows of {r['Place']!r} are not together")
            names.append(r["Place"])
    codes = {name: geo.resolve(name, SOURCE) for name in names}
    if len(set(codes.values())) != len(codes):
        raise KulpStraussFormatError("two of the file's places resolve to the same entity")
    return {codes[n]: _place([r for r in rows if r["Place"] == n], n) for n in names}


def cell(rows: list[WorldRow], exposure: Exposure, projection: str, scenario: str, period: str) -> Cell:
    (c,) = [
        r.cells[exposure.column]
        for r in rows
        if (r.sea_level.projection, r.sea_level.scenario, r.sea_level.period) == (projection, scenario, period)
    ]
    return c


# --- the article and the file descriptions ------------------------------------------------------------------------


@dataclass(frozen=True)
class Statement:
    locator: str
    page: int
    text: str


CORRECTED = Statement("Page 1", 1, "Corrected: Author correction")
ABSTRACT_LOW = Statement(
    "Abstract, p. 1",
    1,
    "190 M people (150–250 M, 90% CI) currently occupy global land below projected high tide lines for 2100 under "
    "low carbon emissions, up from 110 M today,",
)
ABSTRACT_HIGH = Statement(
    "Abstract, p. 1",
    1,
    "Under high emissions, CoastalDEM indicates up to 630 M people live on land below projected annual flood levels "
    "for 2100, and up to 340 M for mid-century, versus roughly 250 M at present.",
)
PRESENT_DAY = Statement(
    "Results, Global, p. 2",
    2,
    "For the present day, CoastalDEM estimates a global total of 110 M people on land below the current high tide "
    "line and 250 M on land below annual flood levels,",
)
MODERATE_2050 = Statement(
    "Results, Global, p. 2",
    2,
    "For one moderate future scenario, sea levels projected by 2050 are high enough to threaten land currently home "
    "to a total of 150 (140–170) million people to a future permanently below the high tide line,",
)
MODERATE_2100 = Statement(
    "Results, Global, p. 3",
    3,
    "A total of 360 (310–420) million people are on land threatened by annual flood events in 2100, or an extra 110 "
    "(60–170) million beyond the contemporary baseline. This case reflects greenhouse gas emissions cuts roughly "
    "consistent with warming of 2 °C (emissions scenario RCP 4.5) and assumes a mostly stable Antarctic (sea-level "
    "model K14).",
)
# The paragraph names no emissions scenario; its numbers are Table 1's K17, RCP 8.5, RL1 row (checked cell by cell).
INSTABILITY = Statement(
    "Results, Global, p. 3",
    3,
    "In the case of Antarctic instability, a total of 300 (270–340) million people today live on land indicated as "
    "vulnerable to an annual flood event by mid-century, rising to as many as 480 (380–630) million by 2100.",
)
LOW_K14_2100 = Statement(
    "Results, Global, p. 3",
    3,
    "the total median current population on land falling below the projected mean higher high water line in 2100 "
    "under low emissions and a fairly stable Antarctica (RCP 2.6 and K14) is 190 million.",
)
ARTICLE_STATEMENTS: tuple[Statement, ...] = (
    CORRECTED,
    ABSTRACT_LOW,
    ABSTRACT_HIGH,
    Statement(
        "Introduction, p. 2",
        2,
        "SRTM is a near-global satellite-based DEM covering latitudes from 56 south to 60 north and thereby land home "
        "to 99.7% of world population (based on 2010 Landscan data",
    ),
    Statement("Introduction, p. 2", 2, "CoastalDEM covers the same near-global latitudes as SRTM"),
    Statement("Introduction, p. 2", 2, "K14 is a probabilistic projection that is closely aligned with IPCC findings"),
    Statement(
        "Introduction, p. 2",
        2,
        "while K17 is not probabilistic and emphasizes the possibility of more rapid sea-level rise because of "
        "unstable ice-sheet dynamics",
    ),
    Statement(
        "Introduction, p. 2",
        2,
        "These models use 2000 as the baseline year (zero sea-level rise), which we treat as present-day with respect "
        "to sea level for relevant vulnerability estimates.",
    ),
    Statement(
        "Introduction, p. 2",
        2,
        "The results we present here are based on median sea-level projections, along with 90% credible intervals "
        "when derived from K14, and 90% intervals from simulation frequency distributions when derived from K17 (we "
        "abbreviate both interval types as CI).",
    ),
    Statement(
        "Introduction, p. 2",
        2,
        "We use local one-year return level heights (RL1) from the Global Tides and Surge Reanalysis",
    ),
    Statement(
        "Results, Global, p. 2",
        2,
        "Coastal defenses are not considered, but hydrologic connectivity to the ocean is otherwise enforced using "
        "connected components analysis.",
    ),
    Statement(
        "Results, Global, p. 2",
        2,
        "Future population growth and migration are also not considered; rather, we use 2010 (essentially current) "
        "population density data from Landscan",
    ),
    PRESENT_DAY,
    MODERATE_2050,
    MODERATE_2100,
    INSTABILITY,
    LOW_K14_2100,
    Statement(
        "Table 1 footnote, p. 3",
        3,
        "Population data from 2010 was used, when the estimated global total of population was roughly 6800 million",
    ),
    Statement(
        "Results, National, p. 5",
        5,
        "Outside of Asia and excluding the Netherlands, where an extensive flood control network is not captured by "
        "any of the elevation models studied,",
    ),
    Statement(
        "Discussion, p. 9",
        9,
        "However, levee location data are not globally available, to our knowledge, and so are not incorporated into "
        "this analysis.",
    ),
)
DESCRIPTION_STATEMENTS: tuple[Statement, ...] = (
    Statement(
        "Supplementary Data 1",
        1,
        "File Name: Supplementary Data 1 Description: Total current population (millions) occupying vulnerable land. "
        "Totals evaluated using CoastalDEM, SRTM, JAXA and MERITDEM elevation datasets, for present-day sea level and "
        "under multiple RCP scenarios for 2050 and 2100.",
    ),
    Statement(
        "Supplementary Data 1",
        1,
        "Permanent exposure (perm) implies elevation below the future local high tide line, while RL1 exposure adds "
        "the local 1-year coastal flood return level. Results are presented as 5th, 50th and 95th percentiles based "
        "on probability distributions of future sea levels, in the case of projections using K14; and based on "
        "simulation frequency distributions, in the case of projections using K17. Locations with maximum exposure "
        "less than 0.01M removed.",
    ),
)

TABLE_PAGE = 3
TABLE_TITLE = "Table 1 Global populations on land at risk"
TABLE_ROW = re.compile(r"(?:(K14|K17) )?(?:(2\.6|4\.5|8\.5) )?(Permanent|RL1) (.+)")
TABLE_CELL = re.compile(r"(\d+) \((\d+) ?[-–] ?(\d+)\)")
TABLE_RCPS = {"2.6": "rcp26", "4.5": "rcp45", "8.5": "rcp85"}
# Table 1's eight cells per row: 2050 total (CoastalDEM, SRTM), 2050 marginal (CoastalDEM, SRTM), then 2100 alike.
TABLE_COASTALDEM_TOTAL = {"2050": 0, "2100": 4}


def verify_statements(pages: list[str], statements: tuple[Statement, ...], what: str) -> None:
    problems = [
        f"{s.locator}: not on page {s.page} of the {what}: {s.text[:70]!r}..."
        for s in statements
        if not 1 <= s.page <= len(pages) or not textmatch.contains(pages[s.page - 1], s.text)
    ]
    if problems:
        raise KulpStraussFormatError("; ".join(problems))


def read_table_1(page: str) -> dict[tuple[str, str, str, str], tuple[str, str, str]]:
    """Table 1's CoastalDEM totals: (projection, scenario, exposure, year) -> (median, 5th, 95th) as printed. The
    projection and the RCP are printed once per group of rows and carried down, as the table's row spans do."""
    if not textmatch.contains(page, TABLE_TITLE):
        raise KulpStraussFormatError(f"'{TABLE_TITLE}' is not on page {TABLE_PAGE} of the article")
    out: dict[tuple[str, str, str, str], tuple[str, str, str]] = {}
    projection = rcp = None
    for line in page.splitlines():
        m = TABLE_ROW.fullmatch(line.strip())
        if not m:
            continue
        cells = TABLE_CELL.findall(m.group(4))
        if len(cells) != 8 or TABLE_CELL.sub("", m.group(4)).strip():
            raise KulpStraussFormatError(f"Table 1 row {line!r} is not eight 'median (5th–95th)' cells")
        if m.group(1):
            projection, rcp = m.group(1).lower(), None
        if m.group(2):
            rcp = TABLE_RCPS[m.group(2)]
        if projection is None or rcp is None:
            raise KulpStraussFormatError(f"Table 1 row {line!r} has no projection or RCP above it")
        exposure = PERM.column if m.group(3) == PERM.table else RL1.column
        for year, i in TABLE_COASTALDEM_TOTAL.items():
            key = (projection, rcp, exposure, year)
            if key in out:
                raise KulpStraussFormatError(f"Table 1 gives {key} twice")
            out[key] = cells[i]
    return out


def verify_table_1(page: str, rows: list[WorldRow]) -> int:
    """Every projected World cell of the CSV equals Table 1's CoastalDEM total, digit for digit. Returns the count."""
    table = read_table_1(page)
    expected = {
        (r.sea_level.projection, r.sea_level.scenario, e.column, r.sea_level.period): r.cells[e.column]
        for r in rows
        if r.sea_level is not PRESENT
        for e in EXPOSURES
    }
    if set(table) != set(expected):
        raise KulpStraussFormatError(f"Table 1 cells {sorted(table)} != the file's {sorted(expected)}")
    wrong = [
        f"{k}: Table 1 prints {table[k][0]} ({table[k][1]}–{table[k][2]}), the file {c.p50} ({c.p5}–{c.p95})"
        for k, c in expected.items()
        if table[k] != (c.p50, c.p5, c.p95)
    ]
    if wrong:
        raise KulpStraussFormatError("Table 1 and Supplementary Data 1 disagree: " + "; ".join(wrong))
    return len(table)


def verify_abstract(rows: list[WorldRow]) -> None:
    """The abstract's figures are these cells: its lead range is K14 (not K17), its high end is K17 (not K14)."""
    problems = []
    k14, k17 = (cell(rows, PERM, p, "rcp26", "2100") for p in ("k14", "k17"))
    if (k14.p50, k14.p5, k14.p95) != ("190", "150", "250") or (k17.p5, k17.p95) == ("150", "250"):
        problems.append(f"'190 M (150–250 M)' is not K14 alone: K14 {k14}, K17 {k17}")
    for year, high in (("2100", "630"), ("2050", "340")):
        k14, k17 = (cell(rows, RL1, p, "rcp85", year) for p in ("k14", "k17"))
        if k17.p95 != high or k14.p95 == high:
            problems.append(f"'up to {high} M' ({year}) is not K17's 95th percentile alone: K14 {k14}, K17 {k17}")
    present = next(r for r in rows if r.sea_level is PRESENT).cells
    if (present[PERM.column].p50, present[RL1.column].p50) != ("110", "250"):
        problems.append(f"'110 M today' and 'roughly 250 M at present' are not the present-day row: {present}")
    if problems:
        raise KulpStraussFormatError("; ".join(problems))


# --- observations -------------------------------------------------------------------------------------------------


PEOPLE_PER_MILLION = Decimal(1_000_000)


def observations(
    rows: list[WorldRow], exposure: Exposure, entity: str = ENTITY, scale: Decimal = Decimal(1)
) -> list[Observation]:
    """One place's observations of one exposure; `scale` multiplies the printed millions (exact decimal arithmetic)."""

    def v(x: str) -> float:
        return float(Decimal(x) * scale)

    obs = []
    for r in rows:
        s, c = r.sea_level, r.cells[exposure.column]
        dims = {"scenario": s.scenario, "projection": s.projection}
        if s is PRESENT:
            obs.append(Observation(entity=entity, period=s.period, value=v(c.p50), dims=dims))
            continue
        assert c.p5 is not None and c.p95 is not None
        obs.append(
            Observation(
                entity=entity,
                period=s.period,
                value=v(c.p50),
                lower=v(c.p5),
                upper=v(c.p95),
                interval="90ci",
                status="projection",
                dims=dims,
            )
        )
    return obs


def _runner(exposure: Exposure) -> Callable[[dict[str, InputFile]], Result]:
    def run(files: dict[str, InputFile]) -> Result:
        return _run(exposure, files)

    return run


MEANING = {
    PERM.column: "Perm: land below the future local high tide line",
    RL1.column: "RL1: land below the future local high tide line plus the local 1-year coastal flood level",
}


def _verified(files: dict[str, InputFile]) -> tuple[list[WorldRow], str]:
    """The World rows, checked against the corrected article and the file description, and the step saying so."""
    data, desc, art = files[CSV.key], files[DESCRIPTIONS.key], files[ARTICLE.key]
    rows = read_world(data.path.read_bytes())
    pages = textmatch.pdf_pages_text(art.path.read_bytes())
    verify_statements(pages, ARTICLE_STATEMENTS, "article")
    verify_statements(textmatch.pdf_pages_text(desc.path.read_bytes()), DESCRIPTION_STATEMENTS, "file description")
    if len(pages) < TABLE_PAGE:
        raise KulpStraussFormatError(f"the article has {len(pages)} pages; Table 1 is expected on page {TABLE_PAGE}")
    n_cells = verify_table_1(pages[TABLE_PAGE - 1], rows)
    verify_abstract(rows)
    step = (
        f"Checked the file against Table 1 of the corrected article (sha256 {art.snapshot.sha256[:12]}…, page "
        f"{TABLE_PAGE}): each of its {n_cells} CoastalDEM totals, median and 90% interval, equals the file's "
        f"three numbers. Found the {len(ARTICLE_STATEMENTS)} sentences that the scope and the cross-checks rely "
        "on, each on its page of the article (which page 1 marks 'Corrected: Author correction'), and the "
        f"{len(DESCRIPTION_STATEMENTS)} on units, exposures and percentiles in the description of the "
        f"supplementary files (sha256 {desc.snapshot.sha256[:12]}…)."
    )
    return rows, step


DATING = (
    "Dated the present-day row 2010, the year of the LandScan population that every row counts (its sea "
    "level is that of 2000, the zero of both projection sets), and the projected rows 2050 and 2100, the "
    "years of their sea levels; the population stays as it was in 2010."
)


def _run(exposure: Exposure, files: dict[str, InputFile]) -> Result:
    """Both indicators read the same three files and run the same checks; only the exposure's columns differ."""
    data = files[CSV.key]
    rows, checked = _verified(files)
    return Result(
        observations=observations(rows, exposure),
        vintage=VINTAGE,
        date_published=PUBLISHED,
        steps=[
            f"Read Supplementary Data 1 (sha256 {data.snapshot.sha256[:12]}…): its {len(HEADER)} column headings had "
            f"to be exactly as expected. Kept the {len(rows)} rows of Place 'World' (present day, then K14 and K17 "
            "under RCP2.6, 4.5 and 8.5 for 2050 and 2100), whose Total is 6800 million people, and from each only the "
            f"three CoastalDEM columns of {MEANING[exposure.column]}. The SRTM, JAXA and MERITDEM columns and the SIDS "
            "and country rows are not used here (the country rows are published, in people, by the indicators ending "
            "'-by-country').",
            "Published the 50th percentile as the value and the 5th and 95th percentiles as the lower and upper ends "
            "of a 90% interval, exactly as printed in millions of people (nothing rounded or recalculated). The "
            "present-day row prints '--' for both percentiles, so it has no range.",
            DATING,
            "Published both projection sets as values of the 'projection' dimension, side by side and never mixed, "
            "because the abstract uses both: its 190 M (150–250 M) below high tide by 2100 under low emissions is "
            "K14 (K17 gives another range), and its 'up to 630 M' and 'up to 340 M' below the annual flood level by "
            "2100 and mid-century are K17's 95th percentiles under RCP8.5. Checked both, and the present day's 110 M "
            "and 250 M, against these cells.",
            checked,
        ],
    )


def _countries_runner(exposure: Exposure) -> Callable[[dict[str, InputFile]], Result]:
    def run(files: dict[str, InputFile]) -> Result:
        return _run_countries(exposure, files)

    return run


def _run_countries(exposure: Exposure, files: dict[str, InputFile]) -> Result:
    """The World and each country's rows of one exposure, in people: the same file and checks as the world indicator."""
    data = files[CSV.key]
    rows, checked = _verified(files)
    places = read_places(data.path.read_bytes())
    obs = observations(rows, exposure, ENTITY, PEOPLE_PER_MILLION)
    for entity, place_rows in places.items():
        obs += observations(place_rows, exposure, entity, PEOPLE_PER_MILLION)
    return Result(
        observations=obs,
        vintage=VINTAGE,
        date_published=PUBLISHED,
        steps=[
            f"Read Supplementary Data 1 (sha256 {data.snapshot.sha256[:12]}…): its {len(HEADER)} column headings had "
            f"to be exactly as expected. Kept the rows of Place 'World' and of the {len(places)} countries and "
            "territories, each with the same 13 sea levels in the same order (present day, then K14 and K17 under "
            "RCP2.6, 4.5 and 8.5 for 2050 and 2100), and from each only the three CoastalDEM columns of "
            f"{MEANING[exposure.column]}. The authors' group of small island developing states (SIDS), the Total "
            "column and the SRTM, JAXA and MERITDEM columns are not used. The file description says places where "
            "the most people exposed is under 0.01 million are left out of the file, so a country absent here has no "
            "value, never zero.",
            f"Mapped each Place name to the site's entity: {len(geo.SOURCE_SCHEMES[SOURCE].aliases)} names through "
            "the explicit alias table for this source (envdash/geo.py), the rest by their exact name in "
            "pipeline/geo/entities.csv.",
            "Published the 50th percentile as the value and the 5th and 95th percentiles as the lower and upper ends "
            "of a 90% interval, each multiplied by one million to give people (exact decimal arithmetic on the "
            "printed digits, so the values keep the file's two significant figures). The present-day row prints '--' "
            "for both percentiles, so it has no range.",
            DATING,
            checked,
        ],
        changes="millions of people converted to people.",
    )


# --- transforms ---------------------------------------------------------------------------------------------------

UNIT = Unit(code="million-people", label="million people", short="million people")
GEOGRAPHY = (
    "World: land between 56° south and 60° north, where CoastalDEM is defined, home to 99.7% of the world's "
    "population in 2010"
)
COMMON_BASIS = (
    "People are counted where they lived in 2010 (LandScan 2010); population growth and migration are not modelled. "
    "Land cut off from the sea is left out. Present day is the sea level of 2000, the zero of both projection sets. "
    "2050 and 2100 add the median and the 5th to 95th percentiles of the sea-level rise projected by Kopp et al. "
    "2014 (K14) or Kopp et al. 2017 (K17, unstable Antarctic ice) under RCP2.6, 4.5 and 8.5, projections made before "
    "the IPCC's Sixth Assessment Report. A bathtub model: sea walls, levees and other defences are not counted "
    "(levee locations are not available globally), so protected coasts such as the Netherlands are included. It "
    "measures exposure, not flooding."
)
DESCRIPTION = (
    "Two projection sets are published side by side, never mixed: K14 (Kopp et al. 2014), which the paper calls "
    "probabilistic and closely aligned with IPCC findings and which gives the abstract's lead figure (below high tide "
    "by 2100 under low emissions); and K17 (Kopp et al. 2017), which adds unstable Antarctic ice, is not "
    "probabilistic, and gives the abstract's high-end figures. Both predate the IPCC's Sixth Assessment Report. The "
    "population is held at its 2010 distribution (LandScan 2010), so future values show where today's people live "
    "relative to future seas, not projected populations. The method is a bathtub model that ignores sea walls and "
    "other defences, so it measures exposure, not flooding."
)


WHAT = {
    PERM.column: "below the local high-tide line (mean higher-high water)",
    RL1.column: "below the local once-a-year coastal flood level (the high-tide line plus the local 1-year flood "
    "height)",
}


def _spec(exposure: Exposure) -> Spec:
    if exposure is PERM:
        title = (
            "People living on land below the high-tide line: estimated at today's sea level, projected for 2050 and "
            "2100, world (Kulp & Strauss 2019)"
        )
        what = WHAT[PERM.column]
        line = (
            "Below the local mean higher-high water line (roughly the high-tide line) after the given sea-level rise."
        )
    else:
        title = (
            "People living on land below the yearly coastal flood level: estimated at today's sea level, projected for "
            "2050 and 2100, world (Kulp & Strauss 2019)"
        )
        what = WHAT[RL1.column]
        line = (
            "Below the local mean higher-high water line plus the local once-a-year coastal flood height (Global Tides "
            "and Surge Reanalysis), after the given sea-level rise."
        )
    return Spec(
        id=exposure.indicator,
        title=title,
        description=f"Estimated number of people, in millions, living on land {what}, at today's sea level and with "
        "the sea levels projected for 2050 and 2100 under low (RCP2.6), moderate (RCP4.5) and high (RCP8.5) "
        "emissions, from Supplementary Data 1 of Kulp & Strauss (2019), using the CoastalDEM elevation model. "
        "Projected values give the median and the 5th to 95th percentile range of the sea-level projections. "
        + DESCRIPTION,
        kind="series",
        unit=UNIT,
        # The World rows print whole millions (two significant figures).
        display=Display(decimals=0),
        scope=Scope(geography=GEOGRAPHY, basis=f"{line} {COMMON_BASIS}"),
        geo_coverage="global-only",
        headline_entity=ENTITY,
        dimensions=(
            Dimension(
                id="scenario",
                label="Sea level: today's, or projected under an emissions scenario",
                values=[DimensionValue(id=k, label=v) for k, v in SCENARIOS.items()],
            ),
            Dimension(
                id="projection",
                label="Sea-level projection",
                values=[DimensionValue(id=k, label=v) for k, v in PROJECTIONS.items()],
            ),
        ),
        headline_dims=(("scenario", "present"), ("projection", "none")),
    )


def _country_spec(exposure: Exposure) -> Spec:
    world = _spec(exposure)
    where = "below the high-tide line" if exposure is PERM else "below the yearly coastal flood level"
    return Spec(
        id=f"{exposure.indicator}-by-country",
        title=f"People living on land {where}: estimated at today's sea level, projected for 2050 and 2100, world and "
        "by country (Kulp & Strauss 2019)",
        description=f"Estimated number of people living on land {WHAT[exposure.column]}, at today's sea level and with "
        "the sea levels projected for 2050 and 2100 under low (RCP2.6), moderate (RCP4.5) and high (RCP8.5) "
        "emissions, in the world and in 134 countries and territories, from Supplementary Data 1 of Kulp & Strauss "
        "(2019), using the CoastalDEM elevation model. Projected values give the median and the 5th to 95th "
        "percentile range of the sea-level projections. The file prints each value in millions to two significant "
        "figures; it is published here in people. The file leaves out places where the most people exposed is under "
        "0.01 million. " + DESCRIPTION,
        kind="series",
        unit=Unit(code="people", label="people", short="people"),
        display=Display(decimals=0),
        scope=Scope(
            geography=f"{GEOGRAPHY}; countries and territories as the authors name them",
            basis=world.scope.basis,
        ),
        geo_coverage="mixed",
        headline_entity=ENTITY,
        dimensions=world.dimensions,
        headline_dims=world.headline_dims,
    )


def _check(stated: str, statement: Statement, period: str, scenario: str, projection: str) -> PublisherCheck:
    return PublisherCheck(
        source_id=SOURCE,
        vintage=VINTAGE,
        entity=ENTITY,
        period=period,
        stated=stated,
        quote=statement.text,
        url=ARTICLE_URL,
        dims=(("scenario", scenario), ("projection", projection)),
    )


CHECKS: dict[str, tuple[PublisherCheck, ...]] = {
    PERM.column: (
        _check("110", PRESENT_DAY, PRESENT_PERIOD, "present", "none"),
        _check("150", MODERATE_2050, "2050", "rcp45", "k14"),
        _check("190", LOW_K14_2100, "2100", "rcp26", "k14"),
    ),
    RL1.column: (
        _check("250", PRESENT_DAY, PRESENT_PERIOD, "present", "none"),
        _check("360", MODERATE_2100, "2100", "rcp45", "k14"),
        _check("300", INSTABILITY, "2050", "rcp85", "k17"),
        _check("480", INSTABILITY, "2100", "rcp85", "k17"),
    ),
}


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=_spec(e),
            inputs=(CSV, DESCRIPTIONS, ARTICLE),
            run=_runner(e),
            module_file=Path(__file__),
            validation=Validation(min_rows=len(SEA_LEVELS), value_range=(1.0, 1000.0)),
            checks=CHECKS[e.column],
        )
        for e in EXPOSURES
    ] + [
        Transform(
            spec=_country_spec(e),
            inputs=(CSV, DESCRIPTIONS, ARTICLE),
            run=_countries_runner(e),
            module_file=Path(__file__),
            validation=Validation(min_rows=len(SEA_LEVELS) * 130, value_range=(0.0, 1e9)),
        )
        for e in EXPOSURES
    ]
