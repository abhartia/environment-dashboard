"""Lovering et al. (2022): land-use intensity of electricity (LUIE), hectares per terawatt-hour per year, Table 1.

Inputs: the article's JATS XML (lovering-2022/article-xml), whose Table 1 is a table of cells, and the printed PDF
(lovering-2022/article-pdf), whose page 8 prints the same table as text.

What is read. Table 1 (table-wrap pone.0270155.t001) has one row per way of making electricity and the columns ANOVA
group, median, interquartile range, mean, standard error and n. The transform requires exactly the twelve row labels
and seven column headings below, parses each printed number (thousands commas removed, nothing rounded), and then
finds every row, as the cells read in order, in the text of PDF page 8, so a value the XML and the printed table
disagree on stops the build. The paper's "IQR" is the interquartile range itself, the 75th minus the 25th percentile:
a width, not a pair of bounds, so it is published as its own statistic and never as lower and upper.

Rooftop solar is not in Table 1. The methods assign it zero ("Integrated Solar PV, i.e. rooftop solar, is assigned an
LUIE of zero in this study."); that sentence is required in both files, and the value is published with the
statistic "assigned", never as a median.

Sentences required in the XML's text and on their PDF page (textmatch rules), which the scope and dimension labels
rely on: the footprint and spacing definitions for wind and natural gas, the share of fuel-supply land for coal, gas,
biomass and nuclear, the exclusion of manufacturing land, and the results sentence naming the lowest and highest
median (nuclear, 7.1; dedicated biomass, 58,000), which is also checked against the table so that "lowest" and
"highest" stay true of the published values.

Not read: the supplementary site-level file (see pipeline/sources/lovering-2022.yaml).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from envdash import textmatch
from envdash.models import Dimension, DimensionValue, Display, Observation, PublishedValueRef, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "lovering-2022"
XML = Input(SOURCE, "article-xml")
PDF = Input(SOURCE, "article-pdf")
INDICATOR = "land-use-intensity.lovering-2022.by-source"
VINTAGE = "PLOS ONE 17(7): e0270155 (2022)"
PUBLISHED = "2022-07-06"
PERIOD = "2022"
ENTITY = "WLD"

TABLE_ID = "pone.0270155.t001"
TABLE_PAGE = 8
TABLE_TITLE = "Land use intensity of electricity (LUIE) showing total direct and indirect land use (ha/TWh/y)."
HEADER = ["", "ANOVA Tukey’s Pairwise", "LUIE Median", "LUIE IQR", "LUIE Mean", "LUIE Standard Error", "LUIE n"]

SOURCES: dict[str, str] = {
    "nuclear": "Nuclear (plant and uranium fuel cycle)",
    "geothermal": "Geothermal",
    "wind": "Wind",
    "residue-biomass": "Residue biomass",
    "natural-gas": "Natural gas (plant and gas fields)",
    "hydro": "Hydroelectric (single-purpose dams)",
    "coal": "Coal (plant and mining)",
    "solar-csp": "Concentrating solar power",
    "ground-pv": "Ground-mounted solar panels",
    "dedicated-biomass": "Dedicated biomass (energy crops)",
    "rooftop-pv": "Rooftop solar panels",
}
AREAS: dict[str, str] = {
    "single": "The paper's one definition for this source",
    "footprint": "Footprint: land physically occupied by turbine pads, well pads, roads and pipelines",
    "spacing": "Spacing: the whole area inside the wind farm or gas field boundary",
}
STATISTICS: dict[str, str] = {
    "median": "Median across the observations",
    "iqr": "Interquartile range across the observations (the 75th minus the 25th percentile: a width, not two bounds)",
    "mean": "Mean across the observations",
    "assigned": "Assigned by the authors, not measured",
}

# Table 1 row label, as printed -> (source, area). Order is the table's.
ROWS: dict[str, tuple[str, str]] = {
    "Nuclear": ("nuclear", "single"),
    "Geothermal": ("geothermal", "single"),
    "Wind (footprint)": ("wind", "footprint"),
    "Residue biomass": ("residue-biomass", "single"),
    "Natural gas (footprint)": ("natural-gas", "footprint"),
    "Hydroelectric (single purpose dams)": ("hydro", "single"),
    "Coal": ("coal", "single"),
    "Solar CSP": ("solar-csp", "single"),
    "Natural gas (spacing)": ("natural-gas", "spacing"),
    "Ground-mounted PV": ("ground-pv", "single"),
    "Wind (spacing)": ("wind", "spacing"),
    "Dedicated biomass": ("dedicated-biomass", "single"),
}


@dataclass(frozen=True)
class Statement:
    locator: str
    page: int
    text: str


ROOFTOP = Statement(
    "Section 2 (Methods), solar PV, p. 6",
    6,
    "Integrated Solar PV, i.e. rooftop solar, is assigned an LUIE of zero in this study.",
)
LOWEST_HIGHEST = Statement(
    "Section 3 (Results), p. 7",
    7,
    "Nuclear had the lowest median LUIE at 7.1 ha/TWh/y, and dedicated biomass the highest at 58,000 ha/TWh/y.",
)
STATEMENTS: tuple[Statement, ...] = (
    ROOFTOP,
    Statement(
        "Section 3 (Results), p. 7",
        7,
        "For wind, footprint area measures only the area covered by turbine pads and access roads, while spacing area "
        "measures the entire area within the boundaries of the wind farm.",
    ),
    Statement(
        "Section 3 (Results), p. 7",
        7,
        "For natural gas, footprint area for the indirect land use measures only the area covered by well pads, access "
        "roads, and pipelines, while spacing area includes the entire area inside the perimeter of a natural gas "
        "production field.",
    ),
    LOWEST_HIGHEST,
    Statement(
        "Section 3 (Results), p. 8",
        8,
        "Indirect land use for combustion-based electricity–land used for fuel sourcing for coal, natural gas, and "
        "biomass—is a larger share of LUIE than direct land use.",
    ),
    Statement(
        "Section 3 (Results), p. 8",
        8,
        "The opposite is true for nuclear power, where indirect land use for uranium mining is only 10% of total LUIE "
        "and the majority of land impacts come from the power plant itself.",
    ),
    Statement(
        "Section 3 (Results), p. 8",
        8,
        "Although our calculations do not include upstream land impacts from manufacturing of materials,",
    ),
)
LOWEST = ("Nuclear", "7.1")
HIGHEST = ("Dedicated biomass", "58,000")


class LoveringFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Row:
    label: str
    anova: str
    median: str
    iqr: str
    mean: str
    se: str
    n: str
    """Each cell exactly as printed."""

    @property
    def printed(self) -> str:
        return " ".join([self.label, self.anova, self.median, self.iqr, self.mean, self.se, self.n])


NUMBER = re.compile(r"^\d{1,3}(,\d{3})*(\.\d+)?$")


def number(printed: str) -> Decimal:
    if not NUMBER.fullmatch(printed):
        raise LoveringFormatError(f"{printed!r} is not a printed number")
    return Decimal(printed.replace(",", ""))


def _text(el: ET.Element) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def read_table(xml: bytes) -> list[Row]:
    """Table 1's rows, checked against the expected title, headings and row labels."""
    root = ET.fromstring(xml)
    found = [t for t in root.iter("table-wrap") if t.get("id") == TABLE_ID]
    if len(found) != 1:
        raise LoveringFormatError(f"expected one table-wrap {TABLE_ID}, found {len(found)}")
    tw = found[0]
    label, title = tw.find("label"), tw.find("caption/title")
    if label is None or _text(label) != "Table 1" or title is None or _text(title) != TABLE_TITLE:
        raise LoveringFormatError(f"{TABLE_ID} is not Table 1 '{TABLE_TITLE}'")
    header = [_text(th) for th in tw.iter("th")]
    if header != HEADER:
        raise LoveringFormatError(f"Table 1 headings {header} != {HEADER}")
    body = tw.find(".//tbody")
    assert body is not None
    rows = []
    for tr in body.findall("tr"):
        cells = [_text(td) for td in tr.findall("td")]
        if len(cells) != len(HEADER):
            raise LoveringFormatError(f"Table 1 row {cells} has {len(cells)} cells, not {len(HEADER)}")
        row = Row(*cells)
        for v in (row.median, row.iqr, row.mean, row.se, row.n):
            number(v)
        rows.append(row)
    labels = [r.label for r in rows]
    if labels != list(ROWS):
        raise LoveringFormatError(f"Table 1 rows {labels} != {list(ROWS)}")
    return rows


def verify(xml: bytes, pages: list[str], rows: list[Row]) -> None:
    """Every row in the printed table; every statement in the XML's text and on its PDF page; the lowest and highest
    medians as the results sentence says."""
    problems: list[str] = []
    if len(pages) < TABLE_PAGE:
        raise LoveringFormatError(f"the PDF has {len(pages)} pages; Table 1 is expected on page {TABLE_PAGE}")
    table_page = pages[TABLE_PAGE - 1]
    if not textmatch.contains(table_page, f"Table 1. {TABLE_TITLE}"):
        problems.append(f"Table 1's title is not on PDF page {TABLE_PAGE}")
    for r in rows:
        if not textmatch.contains(table_page, r.printed):
            problems.append(f"row {r.printed!r} is not printed on PDF page {TABLE_PAGE}")
    xml_text = textmatch.document_text(xml, "application/xml")
    for s in STATEMENTS:
        if not textmatch.contains(xml_text, s.text):
            problems.append(f"{s.locator}: not in the XML: {s.text[:70]!r}...")
        if not 1 <= s.page <= len(pages) or not textmatch.contains(pages[s.page - 1], s.text):
            problems.append(f"{s.locator}: not on PDF page {s.page}: {s.text[:70]!r}...")
    by_median = sorted(rows, key=lambda r: number(r.median))
    if (by_median[0].label, by_median[0].median) != LOWEST or (by_median[-1].label, by_median[-1].median) != HIGHEST:
        problems.append(
            f"the lowest and highest medians are {by_median[0].label} {by_median[0].median} and "
            f"{by_median[-1].label} {by_median[-1].median}, not as the results sentence says"
        )
    if problems:
        raise LoveringFormatError("; ".join(problems))


def observations(rows: list[Row]) -> list[Observation]:
    obs: list[Observation] = []
    for r in rows:
        source, area = ROWS[r.label]
        note = f'Table 1, p. 8, row "{r.label}": n = {r.n} observations; Tukey group {r.anova}.'
        if r.anova == "---":
            note = (
                f'Table 1, p. 8, row "{r.label}": n = {r.n} observations; left out of the ANOVA for its large variance.'
            )
        for statistic, printed in (("median", r.median), ("iqr", r.iqr), ("mean", r.mean)):
            obs.append(
                Observation(
                    entity=ENTITY,
                    period=PERIOD,
                    value=float(number(printed)),
                    note=note,
                    dims={"source": source, "area": area, "statistic": statistic},
                )
            )
    obs.append(
        Observation(
            entity=ENTITY,
            period=PERIOD,
            value=0.0,
            note=f'{ROOFTOP.locator}: "{ROOFTOP.text}" Not measured: an assumption of the study.',
            dims={"source": "rooftop-pv", "area": "single", "statistic": "assigned"},
        )
    )
    return obs


def _run(files: dict[str, InputFile]) -> Result:
    x, p = files[XML.key], files[PDF.key]
    xml = x.path.read_bytes()
    pages = textmatch.pdf_pages_text(p.path.read_bytes())
    rows = read_table(xml)
    verify(xml, pages, rows)
    return Result(
        observations=observations(rows),
        vintage=VINTAGE,
        date_published=PUBLISHED,
        steps=[
            f"Read Table 1 from the article's XML (sha256 {x.snapshot.sha256[:12]}…): its title, its seven column "
            f"headings and its {len(rows)} row labels had to be exactly as expected. Found each row, cell by cell, in "
            f"the printed table on page {TABLE_PAGE} of the PDF (sha256 {p.snapshot.sha256[:12]}…) before publishing.",
            "Published the median, the interquartile range and the mean of each row as printed (thousands commas "
            "removed, nothing rounded or recalculated). The interquartile range is the paper's own column: the width "
            "between the 25th and 75th percentiles, published as its own statistic, not as bounds. The number of "
            "observations and the paper's ANOVA group are in each value's note; the standard error is not "
            "published.",
            "Wind and natural gas each have two rows, footprint and spacing, published as two values of the 'area' "
            "dimension; the other sources have one definition each.",
            "Added rooftop solar at zero, labelled 'assigned', because the methods state that the study assigns it "
            "zero (sentence found in both files); it is an assumption, not a measurement.",
            f"Found {len(STATEMENTS)} sentences that the scope relies on (footprint and spacing, fuel-supply land, "
            "manufacturing land left out, and the lowest and highest medians) in the XML's text and on their PDF "
            "pages, and checked that nuclear has the lowest and dedicated biomass the highest median in the table.",
        ],
        published_value=PublishedValueRef(document=SOURCE, locator=LOWEST_HIGHEST.locator, quote=LOWEST_HIGHEST.text),
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id=INDICATOR,
                title="Land used per unit of electricity, by way of making it (Lovering et al. 2022)",
                description="Hectares of land occupied for each terawatt-hour of electricity generated in a year, for "
                "eleven ways of making electricity, from Table 1 of Lovering et al. (2022): the median, the "
                "interquartile range and the mean across the sites and studies observed. Coal, natural gas, nuclear "
                "and dedicated biomass include the land used to mine, drill or grow their fuel. Wind and natural gas "
                "are given two "
                "ways: the land physically occupied, and the whole area inside the site's boundary. Rooftop solar is "
                "zero by the study's assumption.",
                kind="published-value",
                unit=Unit(
                    code="ha-per-TWh-per-year",
                    label="hectares per terawatt-hour generated in a year",
                    short="ha/TWh/yr",
                ),
                # Table 1 prints two significant figures; the smallest value is 4.8.
                display=Display(decimals=1),
                scope=Scope(
                    geography="Sites studied: nuclear, wind and ground-mounted solar in the United States, coal in the "
                    "United States and Canada, dams in 80 countries, other sources from published studies worldwide",
                    basis="Land occupied per unit of electricity generated, in hectares per terawatt-hour per year. "
                    "Includes the land used to supply fuel (mining, processing, transport, gas fields, energy crops) "
                    "for coal, natural gas, nuclear and dedicated biomass. Excludes land to make panels, turbines and "
                    "plants, transmission lines, offshore areas and underground impacts. Hydroelectric covers "
                    "single-purpose dams only (the reservoir area). Rooftop solar is zero by assumption, not measured. "
                    "The period is the year of publication.",
                ),
                geo_coverage="global-only",
                headline_entity=ENTITY,
                dimensions=(
                    Dimension(
                        id="source",
                        label="Way of making electricity",
                        values=[DimensionValue(id=k, label=v) for k, v in SOURCES.items()],
                    ),
                    Dimension(
                        id="area",
                        label="Land counted",
                        values=[DimensionValue(id=k, label=v) for k, v in AREAS.items()],
                    ),
                    Dimension(
                        id="statistic",
                        label="Statistic",
                        values=[DimensionValue(id=k, label=v) for k, v in STATISTICS.items()],
                    ),
                ),
                headline_dims=(("source", "nuclear"), ("area", "single"), ("statistic", "median")),
            ),
            inputs=(XML, PDF),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=len(ROWS) * 3 + 1, value_range=(0.0, 200_000.0)),
        )
    ]
