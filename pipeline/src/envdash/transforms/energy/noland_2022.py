"""Nøland et al. (2022): power density of electricity generation, watts per square metre, from Table 16.

Input: the published PDF (noland-2022/article-pdf, 26 pages, from nature.com). Table 16 (page 20) is text: one line
per source, "<source> <median W/m2> <mean W/m2> ± <standard deviation W/m2> <median TWh/km2> <mean TWh/km2> ±
<standard deviation TWh/km2> <capacity factor %> <n>". The transform requires exactly the twelve source lines below,
in order, and publishes the three W/m2 statistics of ten of them exactly as printed. The TWh/km2 columns are the same
quantity in another unit and are not published; the capacity factors are not published.

Left out, and checked on every build so the reason stays true:
- Natural gas: its Table 16 mean energy density must equal the upper estimate in Table 6 (page 6), whose inputs
  include "Total primary energy from natural gas (2020)" from reference 35, which must be the IEA's World Energy
  Outlook 2022 (page 24). It is an IEA-derived value, under the IEA's terms rather than this article's.
- Biomass: the row is van Zalk and Behrens (2018)'s value (the caption says "The biomass numbers are based on the
  meta-analysis of van Zalk and Behrens"), whose own licence has not been confirmed on its article page.

Agreement inside the article, checked on every build: the nuclear line equals Table 7's "Incl. safety area" line
(page 8), offshore and onshore wind equal Table 11's "Offshore" and "The World" lines (page 14), and rooftop solar
equals Table 9's "The World" line (page 12). Table 9 counts 40 rooftop samples where Table 16 counts 39; both counts
are given in the value's note.

Not used (see pipeline/sources/noland-2022.yaml): Tables 2, 10, 15, 19 and 20, which rest on BP, IEA and Our World in
Data figures, and the supplementary plant files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from envdash import textmatch
from envdash.models import Dimension, DimensionValue, Display, Observation, PublishedValueRef, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "noland-2022"
PDF = Input(SOURCE, "article-pdf")
INDICATOR = "power-density.noland-2022.by-source"
VINTAGE = "Scientific Reports 12: 21280 (2022)"
PUBLISHED = "2022-12-08"
PERIOD = "2022"
ENTITY = "WLD"
TABLE_PAGE = 20

CAPTION = (
    "Table 16. Aggregated result of the mean and annual power and energy densities of the 10 different energy "
    "resources examined in this paper (cumulative rooftop solar PV technology per country is separated in this "
    "table), referring to the data in Figs. 2, 4, 5, 7, 8, 9, 10, 12, and 13. The mean, median and standard deviation "
    "are given, as well as the average capacity factor and the number of samples (n) per population study. The "
    "biomass numbers are based on the meta-analysis of van Zalk and Behrens"
)
HEADER = "Source mdn ( W/m 2) avg ± dev ( W/m 2) mdn ( TWh/km 2) avg ± dev ( TWh/km 2) avg (%) n"

# Table 16 label as printed -> our source id, or None for a row that is left out. Order is the table's.
LABELS: dict[str, str | None] = {
    "Nuclear": "nuclear",
    "Natural gas": None,
    "Hydro": "hydro",
    "Solar (CSP)": "solar-csp",
    "Solar (PV)": "solar-pv",
    "Wave": "wave",
    "Geothermal": "geothermal",
    "Solar (rooftop)": "rooftop-pv",
    "Wind (offshore)": "wind-offshore",
    "Tidal": "tidal",
    "Wind (onshore)": "wind-onshore",
    "Biomass3": None,
}
SOURCES: dict[str, str] = {
    "nuclear": "Nuclear (plant and its safety area)",
    "hydro": "Hydroelectric (reservoir surface)",
    "solar-csp": "Concentrating solar power",
    "solar-pv": "Solar farms (on land and floating)",
    "wave": "Wave",
    "geothermal": "Geothermal (including the area between wells)",
    "rooftop-pv": "Rooftop solar (per square metre of roof)",
    "wind-offshore": "Offshore wind (whole farm area)",
    "tidal": "Tidal",
    "wind-onshore": "Onshore wind (whole farm area)",
}
STATISTICS: dict[str, str] = {
    "median": "Median across sites",
    "mean": "Mean across sites",
    "standard-deviation": "Standard deviation across sites",
}

LINE = re.compile(
    r"^(?P<label>[A-Za-z][A-Za-z ()]*?\d?) (?P<mdn>\d+\.\d+) (?P<avg>\d+\.\d+) ± (?P<dev>\d+\.\d+) "
    r"(?P<emdn>\d+\.\d+) (?P<eavg>\d+\.\d+) ± (?P<edev>\d+\.\d+) (?P<cf>\d+\.\d+|n\.a\.) (?P<n>\d+)$"
)

# (page, the printed line that must be there, built from a Table 16 row) for the agreement checks.
AGREEMENT: dict[str, tuple[int, str]] = {
    "nuclear": (8, "Incl. safety area {mdn} {avg} ± {dev} {emdn} {eavg} ± {edev}"),
    "wind-offshore": (14, "Offshore {mdn} {avg} ± {dev} {emdn} {eavg} ± {edev}"),
    "wind-onshore": (14, "The World {mdn} {avg} ± {dev} {emdn} {eavg} ± {edev} {n}"),
    "rooftop-pv": (12, "The World {mdn} {avg} ± {dev} {emdn} {eavg} ± {edev} 40"),
}
GAS_TABLE6 = (6, "Upper estimate of mean annual energy density (approx. incl. pipelines and production pads) {eavg}")
GAS_INPUT = (6, "Total primary energy from natural gas (2020)35")
IEA_REFERENCE = (24, "35. Cozzi, L. et al. World Energy Outlook 2022. International Energy Agency (IEA).")


class NolandFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Row:
    label: str
    mdn: str
    avg: str
    dev: str
    emdn: str
    eavg: str
    edev: str
    cf: str
    n: str
    line: str


def read_table(pages: list[str]) -> list[Row]:
    if len(pages) < TABLE_PAGE:
        raise NolandFormatError(f"the PDF has {len(pages)} pages; Table 16 is expected on page {TABLE_PAGE}")
    page = pages[TABLE_PAGE - 1]
    if not textmatch.contains(page, CAPTION) or not textmatch.contains(page, HEADER):
        raise NolandFormatError(f"Table 16's caption or headings are not on PDF page {TABLE_PAGE} as expected")
    rows = []
    for line in page.splitlines():
        m = LINE.match(line.strip())
        if m:
            rows.append(Row(**m.groupdict(), line=line.strip()))
    labels = [r.label for r in rows]
    if labels != list(LABELS):
        raise NolandFormatError(f"Table 16 rows {labels} != {list(LABELS)}")
    return rows


def _on(pages: list[str], page: int, text: str) -> bool:
    return 1 <= page <= len(pages) and textmatch.contains(pages[page - 1], text)


def verify(pages: list[str], rows: list[Row]) -> None:
    by_source = {LABELS[r.label]: r for r in rows if LABELS[r.label]}
    problems = []
    for source, (page, template) in AGREEMENT.items():
        r = by_source[source]
        text = template.format(**{k: getattr(r, k) for k in ("mdn", "avg", "dev", "emdn", "eavg", "edev", "n")})
        if not _on(pages, page, text):
            problems.append(f"{source}: {text!r} is not on PDF page {page}")
    gas = next(r for r in rows if r.label == "Natural gas")
    for page, text in (
        (GAS_TABLE6[0], GAS_TABLE6[1].format(eavg=gas.eavg)),
        GAS_INPUT,
        IEA_REFERENCE,
    ):
        if not _on(pages, page, text):
            problems.append(
                f"natural gas is left out as IEA-derived, but {text!r} is not on PDF page {page}: re-read the article"
            )
    if problems:
        raise NolandFormatError("; ".join(problems))


def _note(r: Row) -> str:
    note = f'Table 16, p. 20, row "{r.label}": n = {r.n} sites.'
    if LABELS[r.label] == "rooftop-pv":
        note = (
            f'Table 16, p. 20, row "{r.label}": n = {r.n} countries (Table 9, p. 12, gives the same values with '
            "n = 40). "
            "Power per square metre of roof, from cumulative installations per country (the paper's reference 5, "
            "Capellán-Pérez et al. 2017), not land."
        )
    return note


def observations(rows: list[Row]) -> list[Observation]:
    obs: list[Observation] = []
    for r in rows:
        source = LABELS[r.label]
        if source is None:
            continue
        for statistic, printed in (("median", r.mdn), ("mean", r.avg), ("standard-deviation", r.dev)):
            obs.append(
                Observation(
                    entity=ENTITY,
                    period=PERIOD,
                    value=float(Decimal(printed)),
                    note=_note(r),
                    dims={"source": source, "statistic": statistic},
                )
            )
    return obs


HEADLINE = "wind-offshore"


def _run(files: dict[str, InputFile]) -> Result:
    f = files[PDF.key]
    pages = textmatch.pdf_pages_text(f.path.read_bytes())
    rows = read_table(pages)
    verify(pages, rows)
    headline = next(r for r in rows if LABELS[r.label] == HEADLINE)
    return Result(
        observations=observations(rows),
        vintage=VINTAGE,
        date_published=PUBLISHED,
        steps=[
            f"Read Table 16 from page {TABLE_PAGE} of the article PDF (sha256 {f.snapshot.sha256[:12]}…): its caption "
            "and headings had to be as expected, and its twelve source lines exactly Nuclear, Natural gas, Hydro, "
            "Solar (CSP), Solar (PV), Wave, Geothermal, Solar (rooftop), Wind (offshore), Tidal, Wind (onshore) and "
            "Biomass, in that order.",
            "Published the median, the mean and the standard deviation of mean specific power in watts per square "
            "metre for ten sources, exactly as printed. The annual energy density columns (the same quantity in "
            "terawatt-hours per square kilometre) and the capacity factors are not published.",
            "Checked that the article agrees with itself: nuclear equals Table 7's line including the safety area, "
            "offshore and onshore wind equal Table 11, rooftop solar equals Table 9's world line.",
            "Left out natural gas, whose Table 16 value is the upper estimate of Table 6, built on the IEA's World "
            "Energy Outlook 2022 (reference 35; both checked in the PDF), and biomass, which is van Zalk and Behrens "
            "(2018)'s value, whose own licence has not been confirmed.",
        ],
        published_value=PublishedValueRef(document=SOURCE, locator=f"Table 16, p. {TABLE_PAGE}", quote=headline.line),
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id=INDICATOR,
                title="Power generated per square metre, by way of making electricity (Nøland et al. 2022)",
                description="Average electric power generated per square metre of land or sea, in watts, for ten "
                "ways of making electricity, from Table 16 of Nøland et al. (2022), who measured 8 to 451 sites per "
                "source on satellite images: the median, the mean and the standard deviation across sites. Nuclear "
                "includes the plant's safety area but not uranium mining; wind counts the whole area inside the "
                "farm's perimeter; rooftop solar is per square metre of roof, not land.",
                kind="published-value",
                unit=Unit(code="W/m2", label="watts per square metre", short="W/m²"),
                display=Display(decimals=2),
                scope=Scope(
                    geography="Sites studied worldwide (8 to 451 per source; rooftop solar: 39 countries)",
                    basis="Mean electric power generated (annual energy over the hours of a year) per square metre of "
                    "the area each site occupies: the plant and its safety area for nuclear, the reservoir surface "
                    "for hydroelectric dams, the area inside the perimeter for wind, wave and tidal farms, the area "
                    "between wells for geothermal, and the roof surface for rooftop solar. Fuel supply land is not "
                    "counted. The period is the year of publication.",
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
                        id="statistic",
                        label="Statistic",
                        values=[DimensionValue(id=k, label=v) for k, v in STATISTICS.items()],
                    ),
                ),
                headline_dims=(("source", HEADLINE), ("statistic", "median")),
            ),
            inputs=(PDF,),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=len(SOURCES) * 3, value_range=(0.0, 5_000.0)),
        )
    ]
