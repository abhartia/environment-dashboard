"""Siegrist et al. (2024): the price of meat substitutes relative to conventional meat of the same product category,
in Germany and in Spain, as the article's text states it.

Input: the version of record from the ETH Zurich Research Collection (CC BY 4.0), 12 pages: the repository's cover
page, then the article, so PDF page n is printed page n - 1.

What is published. The results (PDF page 6) explain the country-specific price ratio of meat substitutes to their
conventional benchmarks (the average ratio within each product category, then a weighted average by the number of
substitutes in each category) and state it for two countries: "0.95 for Germany" (one retailer) and, for Spain, "2.15".
These are the premium itself, as the authors computed it from their own price collection; this transform does no
arithmetic.

Not published as values: the abstract's "24 to 115 % more expensive compared to conventional meat, except for the
German samples where price parity has been reached", and the text's "In the remaining countries, it was between 1.24
and 1.46" (France, Italy, the Netherlands and the United Kingdom together). Both are ranges over several countries,
so neither belongs to one country; they are quoted in the indicator's notes and description. The per-country ratios
for those four countries are in the supplementary material, which is only on ScienceDirect.
"""

from __future__ import annotations

from pathlib import Path

from envdash import textmatch
from envdash.greenpremium import Passage, check_passages, stated
from envdash.models import Display, Observation, PublishedValueRef, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "siegrist-2024"
ARTICLE = Input(SOURCE, "article-pdf")
INDICATOR = "green-premium.siegrist-2024.meat-substitutes"
VINTAGE = "Food Research International 197, 115213 (2024)"
PUBLISHED = "2024-10-23"
PERIOD = "2023-08/2023-09"

RATIOS = Passage(
    6,
    "To estimate the price gap, a country-specific price ratio between substitutes and benchmarks was calculated. "
    "For milk substitutes this was calculated by averaging the price of all milk substitutes, then dividing it by the "
    "average price of all milk products in each country. In the case of meat substitutes and conventional meat, the "
    "average ratio was first calculated for each product category separately to avoid that price differences in one "
    "category (e.g., deli meat) are too dominant. Subsequently, a weighted average was taken based on the number of "
    "substitute products in each category. The lowest price ratio for meat substitutes and their corresponding "
    "benchmarks was 0.95 for Germany. In other words, meat substitutes were on average slightly cheaper than "
    "benchmarks of the same product category in the German retailer. In Spain, the average price ratio was highest "
    "with a value of 2.15. In the remaining countries, it was between 1.24 and 1.46.",
    "Section 3 (Results), p. 5",
)
ABSTRACT = Passage(
    2,
    "On average, meat substitutes were found to be 24 to 115 % more expensive compared to conventional meat, except "
    "for the German samples where price parity has been reached.",
    "Abstract, p. 1",
)
CONTEXT = (
    Passage(
        3,
        "were collected manually and semiautomatically from web shops of 13 major retailers in France (n = 3), "
        "Germany (n = 1), Italy (n = 2), the Netherlands (n = 2), Spain (n = 2), and the UK (n = 3)",
        "Section 2.1 (Data collection), p. 2",
    ),
    Passage(3, "The data collection took place in August 2023.", "Section 2.1 (Data collection), p. 2"),
    Passage(
        3,
        "Prices of over 7500 conventional meat and milk products were collected in September 2023 from the same web "
        "shops to allow for a direct price comparison between animal-based benchmarks and substitutes",
        "Section 2.1 (Data collection), p. 2",
    ),
    Passage(2, "This is an open access article under the CC BY license", "Article p. 1"),
)
PASSAGES = [RATIOS, ABSTRACT, *CONTEXT]
# entity -> (the words that state it, the number as printed)
VALUES: dict[str, tuple[str, str]] = {
    "DEU": (
        "The lowest price ratio for meat substitutes and their corresponding benchmarks was 0.95 for Germany",
        "0.95",
    ),
    "ESP": ("In Spain, the average price ratio was highest with a value of 2.15", "2.15"),
}
NOTES = {
    "DEU": "One retailer's web shop (Germany, n = 1).",
    "ESP": "Two retailers' web shops (Spain, n = 2).",
}


def observations() -> list[Observation]:
    """Call check_passages first."""
    obs = []
    for entity, (words, printed) in VALUES.items():
        obs.append(
            Observation(
                entity=entity,
                period=PERIOD,
                value=float(stated(RATIOS, words, printed)),
                note=f'{RATIOS.locator}: "{words}." {NOTES[entity]} Abstract: "{ABSTRACT.text}"',
            )
        )
    return obs


def _run(files: dict[str, InputFile]) -> Result:
    f = files[ARTICLE.key]
    check_passages(textmatch.pdf_pages_text(f.path.read_bytes()), PASSAGES)
    obs = observations()
    return Result(
        observations=obs,
        vintage=VINTAGE,
        date_published=PUBLISHED,
        steps=[
            f"Read the text of the version-of-record PDF from the ETH Zurich Research Collection (sha256 "
            f"{f.snapshot.sha256[:12]}…, one download recorded by hand because the repository's cover page changes "
            f"with every download) and found {len(PASSAGES)} passages from the abstract, the methods and the results "
            "word for word on their pages.",
            "Published the two price ratios of meat substitutes to conventional meat that the results state for one "
            "country each (Germany and Spain), exactly as printed.",
            "Did not publish the ranges stated for several countries at once (the abstract's '24 to 115 %' and "
            "'between 1.24 and 1.46' for France, Italy, the Netherlands and the United Kingdom); they are quoted in "
            "each value's note.",
        ],
        published_value=PublishedValueRef(document=SOURCE, locator=ABSTRACT.locator, quote=ABSTRACT.text),
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id=INDICATOR,
                title="Price of meat substitutes compared with meat in Germany and Spain (Siegrist et al. 2024)",
                description="How the price of meat substitutes compares with conventional meat of the same kind "
                "(minced meat with minced meat, deli meat with deli meat), as the ratio of their prices per kilogram "
                "in supermarket web shops in August and September 2023: 1 means the same price. Siegrist and "
                "colleagues (2024) state it for Germany and Spain; across France, Italy, the Netherlands and the "
                "United Kingdom they give only a range, quoted in the notes.",
                kind="published-value",
                unit=Unit(
                    code="ratio",
                    label="price per kilogram of meat substitutes divided by that of conventional meat",
                    short="ratio",
                ),
                display=Display(decimals=2),
                scope=Scope(
                    geography="Germany (one retailer) and Spain (two retailers): web shops of major supermarket chains",
                    basis="Prices of substitutes collected in August 2023 and of conventional products in September "
                    "2023. The ratio is averaged within each product category, then weighted by the number of "
                    "substitute products in each category.",
                ),
                geo_coverage="country",
                headline_entity="ESP",
            ),
            inputs=(ARTICLE,),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=2, value_range=(0.1, 10.0)),
        )
    ]
