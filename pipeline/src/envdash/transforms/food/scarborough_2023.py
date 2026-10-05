"""Scarborough et al. (2023), Nature Food 4, 565–574: daily greenhouse gas emissions of six UK diet groups (GWP100),
with their 95% uncertainty intervals, from Table 3 of the CC BY 4.0 article.

Input: the version-of-record PDF (scarborough-2023/article-pdf), 10 pages; PDF page n is printed page 564 + n. Not the
ORA dataset (all rights reserved) and not the authors' code (no licence); see docs/sources.md, Rejected.

What Table 3 holds (PDF page 5, printed p. 569): for each diet group, the median and the 2.5th and 97.5th percentiles
of 1,000 Monte Carlo iterations of the dietary GHG footprint in kg CO₂e per day, standardized to 2,000 kcal and by age
and gender, aggregated with three metrics (GWP100, GTP100, GWP20). This transform publishes the GWP100 column. The
Methods (PDF page 7) state that GWP100 uses the IPCC Sixth Assessment Report factors (CH4 27, N2O 273), hence
AR6-GWP100.

Every value comes from TABLE_ROWS: the row as printed (diet group, then three "median (2.5th, 97.5th)" groups). Before
publishing, the transform finds the table title, the column header, the table note, the Methods sentence and every
row in the text of their pages (textmatch rules), reads the first group of each row (GWP100) and publishes the printed
digits: no arithmetic.

Who and when. 55,504 adults of the EPIC-Oxford cohort (UK, recruited 1993–1999; the diets are those reported at
baseline in 1993–1999), a health-conscious cohort with many vegetarians and vegans, not a sample of the UK
population. The period is the diet-reporting period, 1993/1999. The food-level footprints come from a database of
life-cycle assessments published between 2000 and 2016 (Methods, PDF page 7).

No publisher cross-check: the article itself is the authors' statement of these values, and checking it against
itself would add nothing; the verbatim match of every row is the check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from envdash import textmatch
from envdash.models import Dimension, DimensionValue, Display, Observation, PublishedValueRef, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "scarborough-2023"
ARTICLE = Input(SOURCE, "article-pdf")
VINTAGE = "Nature Food 4, 565–574 (2023)"
PUBLISHED = "2023-07-20"
ENTITY = "GBR"
PERIOD = "1993/1999"
TABLE_PAGE = 5
LOCATOR = "Table 3, p. 569"

TITLE = (
    "Table 3 | Dietary GHG emissions by diet group aggregated using the GWP100, GTP100 and GWP20, standardized to "
    "2,000 kcal and by age and gender"
)
HEADER = "Diet group GHG emissions GWP100 CO2e (kg d−1) GTP100 CO2e (kg d−1) GWP20 CO2e (kg d−1)"
NOTE = (
    "Results presented for all adults (N = 55,504). All results are presented as median (2.5th percentile, 97.5th "
    "percentile) from a Monte Carlo analysis with 1,000 iterations."
)
METHODS = (
    7,
    "We used data on the GHGs to estimate aggregated GWP100 (CH4 conversion factor = 27, N2O = 273) using conversion "
    "factors from the Sixth Assessment Report of the Intergovernmental Panel on Climate Change",
)


@dataclass(frozen=True)
class Row:
    group: str
    label: str
    printed: str
    """The table row exactly as printed."""


TABLE_ROWS: tuple[Row, ...] = (
    Row("vegans", "Vegans", "Vegans 2.47 (2.09, 3.36) 2.42 (2.05, 3.29) 2.73 (2.30, 3.64)"),
    Row("vegetarians", "Vegetarians", "Vegetarians 4.16 (3.31, 5.82) 3.84 (3.04, 5.19) 5.35 (4.37, 7.95)"),
    Row("fish-eaters", "Fish-eaters", "Fish-eaters 4.74 (3.85, 6.27) 4.39 (3.54, 5.72) 6.08 (5.00, 8.73)"),
    Row("low-meat-eaters", "Low meat-eaters", "Low meat-eaters 5.37 (4.26, 6.99) 4.92 (3.87, 6.31) 7.08 (5.78, 9.93)"),
    Row(
        "medium-meat-eaters",
        "Medium meat-eaters",
        "Medium meat-eaters 7.04 (5.26, 9.39) 6.34 (4.71, 8.53) 9.55 (7.31, 13.04)",
    ),
    Row(
        "high-meat-eaters",
        "High meat-eaters",
        "High meat-eaters 10.24 (7.04, 15.95) 8.97 (6.17, 14.15) 14.77 (10.23, 22.55)",
    ),
)
GROUP = re.compile(r"(\d+\.\d+) \((\d+\.\d+), (\d+\.\d+)\)")
HEADLINE = "high-meat-eaters"


class ScarboroughTextError(ValueError):
    pass


def gwp100(row: Row) -> tuple[str, str, str]:
    """(median, 2.5th, 97.5th percentile) of the row's first group, as printed."""
    if not row.printed.startswith(row.label + " "):
        raise ScarboroughTextError(f"row {row.printed!r} does not start with {row.label!r}")
    groups = GROUP.findall(row.printed.removeprefix(row.label + " "))
    if len(groups) != 3:
        raise ScarboroughTextError(f"row {row.printed!r} does not have three 'median (low, high)' groups")
    return groups[0]


def verify(pages: list[str]) -> None:
    problems = []
    texts = [(TABLE_PAGE, TITLE), (TABLE_PAGE, HEADER), (TABLE_PAGE, NOTE), METHODS]
    texts += [(TABLE_PAGE, r.printed) for r in TABLE_ROWS]
    for page, text in texts:
        if not textmatch.contains(pages[page - 1], text):
            problems.append(f"not found on PDF page {page}: {text[:70]!r}")
    if problems:
        raise ScarboroughTextError("; ".join(problems))


def observations() -> list[Observation]:
    obs = []
    for r in TABLE_ROWS:
        median, low, high = (float(x) for x in gwp100(r))
        if not low <= median <= high:
            raise ScarboroughTextError(f"{r.label}: median {median} outside ({low}, {high})")
        obs.append(
            Observation(
                entity=ENTITY,
                period=PERIOD,
                value=median,
                lower=low,
                upper=high,
                interval="95ci",
                dims={"diet": r.group},
            )
        )
    return obs


def _run(files: dict[str, InputFile]) -> Result:
    f = files[ARTICLE.key]
    verify(textmatch.pdf_pages_text(f.path.read_bytes()))
    headline = next(r for r in TABLE_ROWS if r.group == HEADLINE)
    return Result(
        observations=observations(),
        vintage=VINTAGE,
        date_published=PUBLISHED,
        steps=[
            f"Read the text of the article's version-of-record PDF (sha256 {f.snapshot.sha256[:12]}…). Found Table "
            f"3's title, column header, note and all {len(TABLE_ROWS)} rows on PDF page {TABLE_PAGE} (printed p. 569), "
            "and the Methods sentence on the GWP100 factors on PDF page 7, word for word, before publishing.",
            "Published the GWP100 column (the first of the table's three metrics): for each diet group the median as "
            "the value and the 2.5th and 97.5th percentiles of the authors' 1,000-iteration Monte Carlo analysis as "
            "the 95% uncertainty interval, exactly as printed. The GTP100 and GWP20 columns are not published here.",
        ],
        published_value=PublishedValueRef(document=SOURCE, locator=LOCATOR, quote=headline.printed),
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="food.scarborough-2023.diet-ghg-per-day",
                title="Greenhouse gas emissions of UK diets, by diet group",
                description="Greenhouse gas emissions caused by producing the food eaten in a day by vegans, "
                "vegetarians, fish-eaters and low, medium and high meat-eaters in a large UK study, per 2,000 "
                "kilocalories, in kilograms of carbon dioxide equivalent, with the range that holds 95% of the "
                "authors' uncertainty estimates (Scarborough et al. 2023).",
                kind="published-value",
                unit=Unit(
                    code="kgCO2e-per-person-per-day",
                    label="kilograms of carbon dioxide equivalent per person per day (2,000 kcal)",
                    short="kg CO₂e/day",
                ),
                display=Display(decimals=2),
                scope=Scope(
                    geography="United Kingdom: 55,504 adults of the EPIC-Oxford cohort (not a representative "
                    "sample of the UK population)",
                    gwp="AR6-GWP100",
                    basis="Dietary footprint from farm to retail of the food eaten (self-reported in a food "
                    "frequency questionnaire at the cohort's baseline, 1993–1999), standardized to 2,000 kcal a day "
                    "and to the cohort's age and gender mix; food-level emissions from a database of life-cycle "
                    "assessments published 2000–2016. Median and 2.5th–97.5th "
                    "percentiles of a 1,000-iteration Monte Carlo analysis. GWP100 with IPCC AR6 factors (CH4 27, "
                    "N2O 273). The period is the years the diets were reported.",
                ),
                geo_coverage="country",
                headline_entity=ENTITY,
                dimensions=(
                    Dimension(
                        id="diet",
                        label="Diet group",
                        values=[DimensionValue(id=r.group, label=r.label) for r in TABLE_ROWS],
                    ),
                ),
                headline_dims=(("diet", HEADLINE),),
            ),
            inputs=(ARTICLE,),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=len(TABLE_ROWS), value_range=(0.0, 30.0)),
        )
    ]
