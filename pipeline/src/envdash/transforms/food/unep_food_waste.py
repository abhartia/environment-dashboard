"""UNEP Food Waste Index Report 2024: global food waste in 2022 at household, food service and retail level (SDG
12.3.1b), in million tonnes and in kilograms per person per year, as published in the report's Table 23.

Input: the English report PDF (unep-food-waste-index-2024/report-pdf). unep.org and wedocs.unep.org refuse scripted
requests (HTTP 403), so a person downloads the file from UNEP's repository (https://wedocs.unep.org/handle/20.500.11822/
45230, Download > English) and records it with envdash snapshot add; the snapshot manifest's note says who, when and
from where.

Which page: the file UNEP serves now is its August 2024 re-save (193 pages). It adds two pages after PDF page 11, so
every later page moves on by two: Table 23 was PDF page 64 in the March 2024 copy (191 pages) and is PDF page 66 here.
Its printed page number, 46, is the same in both. PAGE is fixed: there is no search for the table and no second page
to try. If UNEP replaces the file again and the table moves, the declared texts are not found on PAGE and the build
fails until PAGE is checked against the new file.

What Table 23 holds (PDF page 66, printed p. 46, "Estimates of global food waste in 2022"): per sector, the global
average in kg per capita per year and the 2022 total in million tonnes, for Household, Food service, Retail and Total.
Food waste here includes inedible parts (bones, peels, shells). Manufacturing and food lost before retail (SDG
12.3.1a) are not included. The page states how the global figures are made: food waste "has been estimated for every
country in the world using the per capita figures and United Nations population statistics for 2022", and these are
added together; many country estimates are extrapolated rather than measured.

Every value comes from ROWS: each row as printed ("<sector> <kg per capita> <million tonnes>") and the two numbers it
states. Before publishing, the transform finds the table title, its column header and the sentence that introduces
the table in the text of PAGE (textmatch rules, which ignore whitespace), and checks that each row is a whole line of
that text reading "<label> <per capita> <total>", spaces included (any run of whitespace, such as the no-break space
in "1 052", counts as one space), so the split between the two columns is checked too. It publishes the printed
digits ("1 052" is 1,052): no arithmetic. The 2021 report's 2019 estimates used other data and methods, so they are
not a trend with these and are not published here.

Licence class noncommercial (UNEP's notice: reproduction for educational or non-profit services with acknowledgement,
no commercial use).
"""

from __future__ import annotations

import functools
import logging
from dataclasses import dataclass
from pathlib import Path

from envdash import textmatch
from envdash.models import Dimension, DimensionValue, Display, Observation, PublishedValueRef, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "unep-food-waste-index-2024"
REPORT = Input(SOURCE, "report-pdf")
VINTAGE = "Food Waste Index Report 2024"
PUBLISHED = "2024-03-27"
PAGE = 66
LOCATOR = "Table 23, p. 46"
PERIOD = "2022"

TITLE = "Table 23: Estimates of global food waste in 2022"
HEADER = "GLOBAL AVERAGE (KG/CAPITA/YEAR) 2022 TOTAL (MILLION TONNES)"
INTRO = (
    "The results indicate that 1.05 billion tonnes of food were wasted across the three sectors considered in this "
    "report in 2022 (Table 23), equal to 132 kilograms per capita per year."
)


@dataclass(frozen=True)
class Row:
    sector: str
    label: str
    per_capita: str
    """kg per capita per year, as printed."""
    total: str
    """million tonnes, as printed (thousands grouped by a space)."""

    @property
    def printed(self) -> str:
        return f"{self.label} {self.per_capita} {self.total}"


ROWS: tuple[Row, ...] = (
    Row("household", "Household", "79", "631"),
    Row("food-service", "Food service", "36", "290"),
    Row("retail", "Retail", "17", "131"),
    Row("all-three-sectors", "Total", "132", "1 052"),
)
LABELS = {
    "household": "Households",
    "food-service": "Food service",
    "retail": "Retail",
    "all-three-sectors": "Households, food service and retail together",
}


class UnepTextError(ValueError):
    pass


@functools.lru_cache(maxsize=1)
def page_text(path: Path) -> str:
    """The text of PDF page PAGE, extracted as textmatch.pdf_pages_text does (pypdf), without reading the other
    pages. Cached by the content-addressed snapshot path."""
    from pypdf import PdfReader

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = PdfReader(path)
    if len(reader.pages) < PAGE:
        raise UnepTextError(f"the PDF has {len(reader.pages)} pages; page {PAGE} does not exist")
    return reader.pages[PAGE - 1].extract_text() or ""


def verify(page: str) -> None:
    """The title, header and introducing sentence must be in the text of page PAGE, and every row must be a whole line
    of it. textmatch ignores whitespace, which would let "Household 79 631" match "Household 796 31"; comparing lines
    with their whitespace collapsed checks which number is in which column."""
    missing = [t for t in (TITLE, HEADER, INTRO) if not textmatch.contains(page, t)]
    lines = {" ".join(line.split()) for line in page.splitlines()}
    missing += [r.printed for r in ROWS if r.printed not in lines]
    if missing:
        raise UnepTextError(f"not found on PDF page {PAGE}: {missing}")


def _number(printed: str) -> float:
    digits = printed.replace(" ", "")
    if not digits.isdigit():
        raise UnepTextError(f"{printed!r} is not a whole number as printed")
    return float(digits)


def _observations(which: str) -> list[Observation]:
    return [
        Observation(
            entity="WLD",
            period=PERIOD,
            value=_number(r.per_capita if which == "per-capita" else r.total),
            dims={"sector": r.sector},
        )
        for r in ROWS
    ]


def _runner(which: str):
    def run(files: dict[str, InputFile]) -> Result:
        f = files[REPORT.key]
        verify(page_text(f.path))
        column = "global average (kg per capita per year)" if which == "per-capita" else "2022 total (million tonnes)"
        return Result(
            observations=_observations(which),
            vintage=VINTAGE,
            date_published=PUBLISHED,
            steps=[
                f"Read the text of UNEP's report PDF (sha256 {f.snapshot.sha256[:12]}…, downloaded by hand from "
                "UNEP's repository; see the snapshot note). Found Table 23's title, column header and all four rows, "
                f"and the sentence introducing the table, word for word on PDF page {PAGE} (printed p. 46) before "
                "publishing.",
                f'Published the column "{column}" for Household, Food service, Retail and Total, exactly as printed '
                '("1 052" is read as 1,052).',
            ],
            published_value=PublishedValueRef(document=SOURCE, locator=LOCATOR, quote=INTRO),
        )

    return run


_DIMENSION = Dimension(
    id="sector", label="Sector", values=[DimensionValue(id=r.sector, label=LABELS[r.sector]) for r in ROWS]
)
_SCOPE = Scope(
    geography="World (sum of UNEP's estimates for every country, many extrapolated)",
    basis="SDG 12.3.1b food waste in 2022: food and its associated inedible parts (bones, peels, shells) removed from "
    "the human food supply at household, food service and retail level. Food lost before retail (SDG 12.3.1a) and "
    "in manufacturing is not included. Not comparable with the 2021 report's 2019 estimates (different data and "
    "methods).",
)


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    return [
        Transform(
            spec=Spec(
                id="food-waste.unep-fwi-2024.total",
                title="Food wasted by households, food service and retail, world",
                description="How much food, including inedible parts such as bones and peels, was thrown away in "
                "2022 by households, by restaurants, canteens and other food service, and by shops, in million "
                "tonnes, as estimated by UNEP's Food Waste Index Report 2024.",
                kind="published-value",
                unit=Unit(code="Mt", label="million tonnes", short="Mt"),
                display=Display(decimals=0),
                scope=_SCOPE,
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(_DIMENSION,),
                headline_dims=(("sector", "all-three-sectors"),),
            ),
            inputs=(REPORT,),
            run=_runner("total"),
            module_file=here,
            validation=Validation(min_rows=len(ROWS), value_range=(0.0, 5_000.0)),
        ),
        Transform(
            spec=Spec(
                id="food-waste.unep-fwi-2024.per-capita",
                title="Food wasted per person by households, food service and retail, world",
                description="How much food, including inedible parts such as bones and peels, was thrown away per "
                "person in 2022 by households, by restaurants, canteens and other food service, and by shops, in "
                "kilograms a year, as the global average estimated by UNEP's Food Waste Index Report 2024.",
                kind="published-value",
                unit=Unit(code="kg-per-capita-per-year", label="kilograms per person per year", short="kg/person/yr"),
                display=Display(decimals=0),
                scope=_SCOPE,
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(_DIMENSION,),
                headline_dims=(("sector", "all-three-sectors"),),
            ),
            inputs=(REPORT,),
            run=_runner("per-capita"),
            module_file=here,
            validation=Validation(min_rows=len(ROWS), value_range=(0.0, 500.0)),
        ),
    ]
