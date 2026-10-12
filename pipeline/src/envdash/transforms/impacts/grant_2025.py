"""Grant et al. (2025): the share of the people born in 1960 and in 2020 projected to face unprecedented lifetime
exposure to heatwaves, worldwide, as the article's text states it.

Input: the article's JATS XML from Europe PMC (PMC12058528, CC BY 4.0).

What the article computes. For every 0.5° land grid cell, birth year (1960-2020) and warming pathway (21 pathways
reaching 1.5 to 3.5 °C above 1850-1900 by 2100), it adds up the heatwaves a person born there lives through over the
country's average lifetime, and compares that total with lifetimes resampled from pre-industrial control simulations.
When the total passes the 99.99th percentile of those pre-industrial lifetimes, the whole cohort of the grid cell is
counted as facing "unprecedented lifetime exposure" (ULE). The world share is the people counted divided by the world
cohort. A heatwave is a 3-day extreme heat event expected about once a century in a pre-industrial climate, computed
directly from the output of the four bias-adjusted CMIP5 climate models of ISIMIP2b (the other five extremes also need
an impact model, and are not published here).

What is published. Every value is a number the Results text prints, checked inside its sentence:
- born in 1960: "around 16% (13 million people) face ULE to heatwaves regardless of the scenario". The article gives
  this one value for every pathway, so it is published under each of the three pathways, with the sentence as its note.
- born in 2020: 52% on the 1.5 °C pathway and 92% on the 3.5 °C pathway. The abstract states both again; each abstract
  sentence must print the same number as the Results sentence, and both are publisher checks.
The text states no world share for the 2020 cohort on the 2.5 °C pathway (Fig. 2a draws it only as a box plot), so
that cell is a missing value that says so. Nothing is read from a figure and nothing is computed. The 2.7 °C
current-policies pathway has no world heatwave share in the text (only shares of the most and least deprived fifths of
the cohort), and the other birth years have none either, so neither is a dimension value.

Reading rules (envdash.greenpremium): every sentence must be in the article's text (whitespace, dashes and quotation
marks ignored, every other character in order); the words that state a value must be part of the sentence; the
printed number must stand in those words as a whole number, and is published as its digits.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from envdash import textmatch
from envdash.greenpremium import (
    PrintedValueError,
    check_sentences,
    jats_doi,
    jats_licence,
    jats_root,
    number_in,
    printed_number,
)
from envdash.models import Dimension, DimensionValue, Display, Observation, PublishedValueRef, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, PublisherCheck, Result, Spec, Transform, Validation

SOURCE = "grant-2025"
ARTICLE = Input(SOURCE, "article-xml")
INDICATOR = "lifetime.grant-2025.unprecedented-heatwaves"
DOI = "10.1038/s41586-025-08907-1"
URL = f"https://doi.org/{DOI}"
VINTAGE = "Nature 641, 374–379 (2025)"
PUBLISHED = "2025-05-07"
PERIOD = "2025"
ENTITY = "WLD"
LICENCE = "This article is licensed under a Creative Commons Attribution 4.0 International License"

COHORTS: dict[str, str] = {"1960": "Born in 1960", "2020": "Born in 2020"}
PATHWAYS: dict[str, str] = {
    "1-5c": "Warming reaching 1.5 °C by 2100",
    "2-5c": "Warming reaching 2.5 °C by 2100",
    "3-5c": "Warming reaching 3.5 °C by 2100",
}


@dataclass(frozen=True)
class Statement:
    locator: str
    sentence: str
    """Copied verbatim from the article ("CFheatwaves" is CF with "heatwaves" as a subscript)."""
    words: str
    """The part of the sentence that states the value."""
    printed: str
    """The number as printed inside `words`."""

    def value(self) -> Decimal:
        if self.words not in self.sentence:
            raise PrintedValueError(f"{self.locator}: {self.words!r} is not part of the sentence")
        if not number_in(self.printed, self.words):
            raise PrintedValueError(f"{self.locator}: {self.printed!r} is not printed in {self.words!r}")
        return printed_number(self.printed)


HEATWAVES = '"Unprecedented exposure to heatwaves", second paragraph'
BORN_1960 = Statement(
    HEATWAVES,
    "Of the 81 million people born in 1960, on average, around 16% (13 million people) face ULE to heatwaves "
    "regardless of the scenario.",
    "around 16% (13 million people)",
    "16",
)
BORN_2020_LOW = Statement(
    HEATWAVES,
    "In a 1.5 °C pathway, CFheatwaves stabilizes for recent birth cohorts, reaching an average of 52% for the 2020 "
    "birth cohort (62 million people).",
    "an average of 52% for the 2020 birth cohort",
    "52",
)
BORN_2020_HIGH = Statement(
    HEATWAVES,
    "Comparatively, CFheatwaves of the 2020 birth cohort is almost doubled in a 3.5 °C pathway, reaching 92%.",
    "reaching 92%",
    "92",
)
ABSTRACT_LOW = Statement(
    "Abstract",
    "Under a 1.5 °C pathway, 52% of people born in 2020 will experience unprecedented lifetime exposure to heatwaves.",
    "52% of people born in 2020",
    "52",
)
ABSTRACT_HIGH = Statement(
    "Abstract",
    "If global warming reaches 3.5 °C by 2100, this fraction rises to 92% for heatwaves, 29% for crop failures and 14% "
    "for river floods.",
    "92% for heatwaves",
    "92",
)
RESULTS: tuple[Statement, ...] = (BORN_1960, BORN_2020_LOW, BORN_2020_HIGH)
ABSTRACT: tuple[Statement, ...] = (ABSTRACT_LOW, ABSTRACT_HIGH)
# (cohort, pathway) -> the Results sentence that states the value, and the abstract sentence that states it again.
STATED: dict[tuple[str, str], tuple[Statement, Statement | None]] = {
    ("1960", "1-5c"): (BORN_1960, None),
    ("1960", "2-5c"): (BORN_1960, None),
    ("1960", "3-5c"): (BORN_1960, None),
    ("2020", "1-5c"): (BORN_2020_LOW, ABSTRACT_LOW),
    ("2020", "3-5c"): (BORN_2020_HIGH, ABSTRACT_HIGH),
}
NOT_STATED: dict[tuple[str, str], str] = {
    ("2020", "2-5c"): "Grant et al. (2025) state no world share for people born in 2020 on the 2.5 °C pathway: the "
    "text gives the 1.5 °C and 3.5 °C values only, and Fig. 2a draws the 2.5 °C value as a box plot, which is not "
    "read.",
}
ONE_VALUE_FOR_ALL = "The article gives this one value for the 1960 cohort on every pathway."
# Sentences the scope and description rely on, checked like the values' sentences.
SENTENCES: list[tuple[str, str]] = [
    (
        "Methods, Emergence of ULE",
        "We define an emergence threshold for ULE to extreme events as the 99.99th percentile of our grid-scale "
        "samples of pre-industrial lifetime exposure.",
    ),
    (
        "Methods, Emergence of ULE",
        "If this threshold is passed, we consider the whole birth cohort in this grid cell to have emerged",
    ),
    (
        "Methods, ISIMIP and exposure projections",
        "Although we refer to heatwaves throughout the paper, our definition technically refers to a 3-day extreme "
        "heat event that is expected on average once per century under pre-industrial climate conditions.",
    ),
    (
        "Discussion",
        "projecting these events requires an additional impact-modelling step relative to heatwaves, which are "
        "computed directly from global climate model output",
    ),
    (
        "Methods, Mapping impacts to GMT trajectories",
        "These warming levels are reported relative to pre-industrial temperatures from 1850 to 1900.",
    ),
    (
        "Methods, Mapping impacts to GMT trajectories",
        "Note that the 1.5 °C anchor scenario maximally reaches 1.57 °C before reducing to 1.5 °C by 2100.",
    ),
    (
        "Methods, Demographics",
        "Countries that can be spatially resolved at the ISIMIP grid scale and have cohort and life expectancy "
        "estimates in these datasets meet the requirements of this study and total 177.",
    ),
    (
        "Discussion",
        "here we apply country-average life expectancy and cohort size distribution uniformly within each country.",
    ),
    (
        "Discussion",
        "By contrast, we do not capture how people adapt to extremes and thereby potentially reduce their exposure or "
        "vulnerability.",
    ),
    (
        "Discussion",
        "Factors such as within-country migration, fertility and mortality respond in reality to the climate extremes "
        "considered here",
    ),
]


def check_abstract(root: ET.Element, statements: list[Statement]) -> None:
    """Every statement's sentence is in the article's abstract (the <abstract> without an abstract-type)."""
    found = [a for a in root.iter("abstract") if a.get("abstract-type") is None]
    if len(found) != 1:
        raise PrintedValueError(f"expected one main <abstract>, found {len(found)}")
    text = " ".join(found[0].itertext())
    missing = [s.sentence[:80] for s in statements if not textmatch.contains(text, s.sentence)]
    if missing:
        raise PrintedValueError(f"not found in the abstract: {missing}")


def _quoted(s: Statement) -> str:
    return f'{s.locator}: "{s.sentence}"'


def observations(raw: bytes) -> list[Observation]:
    root = jats_root(raw)
    if jats_doi(root) != DOI:
        raise ValueError(f"{SOURCE}: the XML is not the article {DOI}")
    if LICENCE not in jats_licence(root):
        raise ValueError(f"{SOURCE}: the article's <license> no longer says {LICENCE!r}")
    keys = [(c, p) for c in COHORTS for p in PATHWAYS]
    if sorted(keys) != sorted([*STATED, *NOT_STATED]):
        raise ValueError(f"{SOURCE}: every cohort and pathway must be either stated or not stated, once")
    check_sentences(root, [(s.locator, s.sentence) for s in RESULTS] + SENTENCES)
    check_abstract(root, list(ABSTRACT))
    obs = []
    for cohort, pathway in keys:
        dims = {"cohort": cohort, "pathway": pathway}
        if (cohort, pathway) in NOT_STATED:
            obs.append(
                Observation(
                    entity=ENTITY,
                    period=PERIOD,
                    value=None,
                    status="projection",
                    missing_reason=NOT_STATED[(cohort, pathway)],
                    dims=dims,
                )
            )
            continue
        stated, again = STATED[(cohort, pathway)]
        if stated not in RESULTS or (again is not None and again not in ABSTRACT):
            raise ValueError(f"{SOURCE}: cohort {cohort}, pathway {pathway} uses a sentence that is not checked")
        value = stated.value()
        note = _quoted(stated)
        if again is not None:
            if again.value() != value:
                raise PrintedValueError(
                    f"{SOURCE}: the abstract prints {again.printed} where the Results text prints {stated.printed} "
                    f"for cohort {cohort}, pathway {pathway}"
                )
            note += f" {_quoted(again)}"
        else:
            note += f" {ONE_VALUE_FOR_ALL}"
        obs.append(
            Observation(
                entity=ENTITY,
                period=PERIOD,
                value=float(value),
                status="projection",
                note=note,
                dims=dims,
            )
        )
    return obs


def _run(files: dict[str, InputFile]) -> Result:
    f = files[ARTICLE.key]
    obs = observations(f.path.read_bytes())
    n = sum(o.value is not None for o in obs)
    return Result(
        observations=obs,
        vintage=VINTAGE,
        date_published=PUBLISHED,
        steps=[
            f"Read the article's JATS XML from Europe PMC (sha256 {f.snapshot.sha256[:12]}…), checked its DOI and its "
            f"CC BY 4.0 licence statement, and found in its text the {len(RESULTS)} Results sentences and "
            f"{len(ABSTRACT)} abstract sentences that state the values, and {len(SENTENCES)} sentences of the Methods "
            "and Discussion that the scope relies on.",
            f"Published {n} world shares exactly as the Results text prints them, each read from the words that state "
            "it inside its checked sentence: 16% for people born in 1960, which the article gives 'regardless of the "
            "scenario' and which is therefore shown under each of the three pathways, and 52% (1.5 °C) and 92% "
            "(3.5 °C) for people born in 2020. The abstract states 52% and 92% again; each was checked to print the "
            "same number.",
            "Published people born in 2020 on the 2.5 °C pathway as missing, because the text states no world share "
            "for it. Nothing was read from a figure or computed, and the numbers of people in the same sentences "
            "(13, 62 and 111 million) are not published.",
        ],
        published_value=PublishedValueRef(
            document=SOURCE,
            locator=f"Abstract; Results, {HEATWAVES}",
            quote=f"{ABSTRACT_LOW.sentence} {ABSTRACT_HIGH.sentence}",
        ),
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id=INDICATOR,
                title="Share of people born in 1960 and 2020 projected to face unprecedented lifetime exposure to "
                "heatwaves (Grant et al. 2025)",
                description="The share of the people born in 1960 and in 2020 who are projected to live through more "
                "heatwaves in their lifetime than all but 1 in 10,000 lifetimes in a pre-industrial climate, along "
                "warming pathways that reach 1.5, 2.5 or 3.5 °C by 2100, as Grant and colleagues (2025) state it for "
                "the world. It is modelled from the ISIMIP2b climate simulations, and 'unprecedented' is a "
                "statistical threshold (beyond the 99.99th percentile of pre-industrial lifetimes), not a count of "
                "deaths or of illness. The article gives one value for people born in 1960 whatever the pathway, and "
                "no world value for people born in 2020 on the 2.5 °C pathway.",
                kind="published-value",
                unit=Unit(code="percent", label="percent of the people born that year", short="%"),
                display=Display(decimals=0),
                scope=Scope(
                    geography="World: the 177 countries the article covers, every 0.5° land grid cell",
                    baseline="Pre-industrial control climate (lifetimes resampled from pre-industrial simulations); "
                    "warming levels relative to 1850–1900",
                    basis="Projected (modelled) lifetime exposure. A heatwave is a 3-day extreme heat event expected "
                    "about once a century in a pre-industrial climate, from four bias-adjusted CMIP5 climate models "
                    "(ISIMIP2b). A birth cohort in a grid cell faces unprecedented lifetime exposure when its "
                    "lifetime count passes the 99.99th percentile of pre-industrial lifetimes there; the whole cohort "
                    "of that cell is then counted. Lifetimes use each country's average life expectancy, with no "
                    "migration and no adaptation (such as air conditioning). Pathways are constructed from AR6 "
                    "scenarios; the 1.5 °C pathway peaks at 1.57 °C. The period is the year of publication; each "
                    "value covers the cohort's whole lifetime.",
                ),
                geo_coverage="global-only",
                headline_entity=ENTITY,
                dimensions=(
                    Dimension(
                        id="cohort",
                        label="Birth year",
                        values=[DimensionValue(id=k, label=v) for k, v in COHORTS.items()],
                    ),
                    Dimension(
                        id="pathway",
                        label="Warming pathway",
                        values=[DimensionValue(id=k, label=v) for k, v in PATHWAYS.items()],
                    ),
                ),
                headline_dims=(("cohort", "2020"), ("pathway", "1-5c")),
            ),
            inputs=(ARTICLE,),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=6, value_range=(0.0, 100.0)),
            checks=(
                PublisherCheck(
                    source_id=SOURCE,
                    vintage=VINTAGE,
                    entity=ENTITY,
                    period=PERIOD,
                    stated=ABSTRACT_LOW.printed,
                    quote=ABSTRACT_LOW.sentence,
                    url=URL,
                    dims=(("cohort", "2020"), ("pathway", "1-5c")),
                ),
                PublisherCheck(
                    source_id=SOURCE,
                    vintage=VINTAGE,
                    entity=ENTITY,
                    period=PERIOD,
                    stated=ABSTRACT_HIGH.printed,
                    quote=ABSTRACT_HIGH.sentence,
                    url=URL,
                    dims=(("cohort", "2020"), ("pathway", "3-5c")),
                ),
            ),
        )
    ]
