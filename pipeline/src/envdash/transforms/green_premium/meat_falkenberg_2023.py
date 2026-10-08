"""Falkenberg et al. (2023): the retail price per kilogram of plant-based and conventional minced meat and sausages in
Austrian supermarkets (Vienna, May 2022), from Table 3 of the article.

Input: the article's JATS XML from Europe PMC (PMC10253197, CC BY 4.0).

What Table 3 holds: for each of four product groups (plant-based and conventional minced meat, plant-based and
conventional sausages) the mean, standard deviation, median, minimum and maximum price per kilogram in euros. Published:
the mean and the median, each with the minimum and maximum as its range. The standard deviation is not published.

The prices are the authors' own observations in the nationwide supermarket chains, each price per kilogram
recalculated from the price and mass on the pack. "Minced meat" includes products based on mince, such as burger
patties and meatballs; "sausages" include sausage slices, cold cuts and spreadable sausages, not ham or bacon
(Materials and Methods). Conventional meat is not split by species.
"""

from __future__ import annotations

from pathlib import Path

from envdash.greenpremium import check_sentences, jats_doi, jats_root, jats_table, printed_number, side_dimension
from envdash.models import Dimension, DimensionValue, Display, Observation, PublishedValueRef, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "falkenberg-2023"
ARTICLE = Input(SOURCE, "article-xml")
INDICATOR = "green-premium.falkenberg-2023.meat"
DOI = "10.3390/foods12112211"
VINTAGE = "Foods 12, 2211 (2023)"
PUBLISHED = "2023-05-31"
PERIOD = "2022-05"
ENTITY = "AUT"

LABEL = "Table 3"
CAPTION = "Descriptive indicators for price per kilogram (kg) for each product group in euro (EUR)."
HEADER = ("Product Group", "Mean", "Standard Dev.", "Median", "Min.", "Max.")
PRODUCTS: dict[str, str] = {"mince": "Minced meat", "sausages": "Sausages"}
# (product, side) -> row label as printed
ROWS: dict[tuple[str, str], str] = {
    ("mince", "conventional"): "Conventional minced meat",
    ("mince", "low-carbon"): "Plant-based minced meat",
    ("sausages", "conventional"): "Conventional sausages",
    ("sausages", "low-carbon"): "Plant-based sausages",
}
SIDE_LABELS = {"conventional": "Conventional meat", "low-carbon": "Plant-based alternative"}
STATISTICS: dict[str, tuple[str, str]] = {
    "mean": ("Mean", "Mean of the products"),
    "median": ("Median", "Median of the products"),
}
SENTENCES: list[tuple[str, str]] = [
    (
        "Materials and Methods",
        "Standardized observations were conducted to collect data in May 2022 in Vienna, the capital city of Austria.",
    ),
    (
        "Results",
        "All prices per kilogram were recalculated to avoid any incorrect price tags in the supermarket",
    ),
]


def observations(raw: bytes) -> list[Observation]:
    root = jats_root(raw)
    if jats_doi(root) != DOI:
        raise ValueError(f"{SOURCE}: the XML is not the article {DOI}")
    check_sentences(root, SENTENCES)
    table = jats_table(root, LABEL, CAPTION)
    obs = []
    for (product, side), row in ROWS.items():
        lower = float(printed_number(table.cell(HEADER, row, "Min.")))
        upper = float(printed_number(table.cell(HEADER, row, "Max.")))
        for sid, (column, _) in STATISTICS.items():
            printed = table.cell(HEADER, row, column)
            obs.append(
                Observation(
                    entity=ENTITY,
                    period=PERIOD,
                    value=float(printed_number(printed)),
                    lower=lower,
                    upper=upper,
                    interval="range",
                    note=f'{LABEL}, row "{row}": {column} {printed}, Min. {table.cell(HEADER, row, "Min.")}, Max. '
                    f"{table.cell(HEADER, row, 'Max.')}",
                    dims={"product": product, "side": side, "statistic": sid},
                )
            )
    return obs


def _run(files: dict[str, InputFile]) -> Result:
    f = files[ARTICLE.key]
    obs = observations(f.path.read_bytes())
    return Result(
        observations=obs,
        vintage=VINTAGE,
        date_published=PUBLISHED,
        steps=[
            f"Read the article's JATS XML from Europe PMC (sha256 {f.snapshot.sha256[:12]}…) and checked its DOI, "
            f"the caption and column headers of {LABEL} and {len(SENTENCES)} sentences of the text.",
            f"Published the mean and the median price per kilogram of the four product groups, with the minimum and "
            f"maximum as the range: {len(obs)} values, each addressed by its printed row label and column header and "
            "published as printed.",
            "Nothing was subtracted: plant-based and conventional prices are shown side by side as the table gives "
            "them.",
        ],
        published_value=PublishedValueRef(document=SOURCE, locator=LABEL, quote=f"{LABEL}. {CAPTION}"),
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id=INDICATOR,
                title="Price of plant-based and conventional mince and sausages in Vienna (Falkenberg et al. 2023)",
                description="What a kilogram of plant-based mince and sausages cost in Austrian supermarkets in "
                "Vienna in May 2022, beside conventional minced meat and sausages in the same shops, as Falkenberg "
                "and colleagues (2023) recorded them: the mean and median of the products on sale, with the cheapest "
                "and dearest.",
                kind="published-value",
                unit=Unit(code="EUR-per-kg", label="euros per kilogram (retail price)", short="€/kg"),
                display=Display(decimals=2),
                scope=Scope(
                    geography="Vienna, Austria: the nationwide supermarket chains Billa, Billa Plus, "
                    "Spar/Eurospar/Interspar, Hofer and Lidl",
                    basis="Shelf prices observed in May 2022, recalculated per kilogram from price and pack mass; "
                    "statistics across the products observed. Conventional meat is not split by species.",
                ),
                geo_coverage="country",
                headline_entity=ENTITY,
                dimensions=(
                    Dimension(
                        id="product",
                        label="Product",
                        values=[DimensionValue(id=k, label=v) for k, v in PRODUCTS.items()],
                    ),
                    side_dimension(SIDE_LABELS),
                    Dimension(
                        id="statistic",
                        label="Statistic",
                        values=[DimensionValue(id=k, label=label) for k, (_, label) in STATISTICS.items()],
                    ),
                ),
                headline_dims=(("product", "mince"), ("side", "low-carbon"), ("statistic", "mean")),
            ),
            inputs=(ARTICLE,),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=8, value_range=(1.0, 100.0)),
        )
    ]
