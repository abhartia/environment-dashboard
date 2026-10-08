"""Furch et al. (2022): the life cycle cost of a petrol, a diesel and a battery electric car on the Czech market, from
Table 1 of the article, in total and per kilometre.

Input: the article's JATS XML from Europe PMC (PMC9226055, CC BY 4.0).

What Table 1 holds: one column per car (six drive types, one model each, as offered on the Czech market) and one row
per input or result. Two indicators are published from the columns "Petrol 1.5 dm3 TSI 110 kW", "Diesel 2.0 dm3 TSI
110 kW" and "Electric 80 kW":
- the row "Life cycle cumulative costs LCC", which prints no unit; equation 18 sums the purchase, operating and
  maintenance costs, all in euros, over the car's service life, and
- the row "Life cycle specific costs LCCS", which the table prints without a unit; equation 20 defines it as LCC
  divided by the service life in kilometres, so its unit is euros per kilometre.
The row "Selected service life of vehicles tl (km/years)" must read "400,000 15" in each of the three columns.
The petrol and CNG, plug-in hybrid and mild hybrid columns are not published: they are neither the conventional
petrol or diesel car nor the battery electric one.

The electric car's battery: its column lists "Accumulator battery costs CAB (€)" of 18,184, and the text says "the
specific cost of an electric vehicle without battery replacement is €0.21, for an electric vehicle with battery
replacement is €0.25". The electric values are published as Table 1 prints them, with that sentence in their note;
the text's rounded figures are not published.
"""

from __future__ import annotations

from pathlib import Path

from envdash.greenpremium import check_sentences, jats_doi, jats_root, jats_table, printed_number, side_dimension
from envdash.models import Dimension, DimensionValue, Display, Observation, PublishedValueRef, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "furch-2022"
ARTICLE = Input(SOURCE, "article-xml")
DOI = "10.1038/s41598-022-14715-8"
VINTAGE = "Scientific Reports 12, 10661 (2022)"
PUBLISHED = "2022-06-23"
PERIOD = "2022"
ENTITY = "CZE"

LABEL = "Table 1"
CAPTION = "Basic input and calculated values for selected passenger car drive types."
FIRST = "Basic input and calculated values"
COLUMNS: dict[str, str] = {
    "petrol": "Petrol 1.5 dm3 TSI 110 kW",
    "diesel": "Diesel 2.0 dm3 TSI 110 kW",
    "petrol-cng": "Petrol and CNG 1.5 dm3 TGI 96 kW",
    "petrol-phev": "Petrol and PHEV 1.4 dm3 TSI 150 kW",
    "petrol-mhv": "Petrol and MHV 1.5 dm3 TSI 110 kW",
    "electric": "Electric 80 kW",
}
HEADER = (FIRST, *COLUMNS.values())
# option id -> (side, label); the table's column header is COLUMNS[option]
OPTIONS: dict[str, tuple[str, str]] = {
    "petrol": ("conventional", "Petrol car (Petrol 1.5 dm³ TSI 110 kW)"),
    "diesel": ("conventional", "Diesel car (Diesel 2.0 dm³ TSI 110 kW)"),
    "electric": ("low-carbon", "Battery electric car (Electric 80 kW)"),
}
SIDE_LABELS = {"conventional": "Petrol or diesel car", "low-carbon": "Battery electric car"}
SERVICE_LIFE = ("Selected service life of vehicles tl (km/years)", "400,000 15")
BATTERY_SENTENCE = (
    "the specific cost of an electric vehicle without battery replacement is €0.21, for an electric vehicle with "
    "battery replacement is €0.25"
)
SENTENCES: list[tuple[str, str]] = [
    ("Discussion, Figure 11", BATTERY_SENTENCE),
    (
        "Discussion",
        "the results of the LCC analysis to evaluate the cost of selected types of powertrains will not include the "
        "full range of alternative powertrain offerings but only what is currently available on the Czech market",
    ),
]

PER_KM = "green-premium.furch-2022.cars-per-km"
LIFETIME = "green-premium.furch-2022.cars-lifetime"
ROWS = {PER_KM: "Life cycle specific costs LCCS", LIFETIME: "Life cycle cumulative costs LCC"}


def observations(raw: bytes, indicator: str) -> list[Observation]:
    root = jats_root(raw)
    if jats_doi(root) != DOI:
        raise ValueError(f"{SOURCE}: the XML is not the article {DOI}")
    check_sentences(root, SENTENCES)
    table = jats_table(root, LABEL, CAPTION)
    row = ROWS[indicator]
    obs = []
    for option, (side, _) in OPTIONS.items():
        column = COLUMNS[option]
        life = table.cell(HEADER, SERVICE_LIFE[0], column)
        if life != SERVICE_LIFE[1]:
            raise ValueError(f"{LABEL} {column}: service life {life!r} != {SERVICE_LIFE[1]!r}")
        printed = table.cell(HEADER, row, column)
        note = f'{LABEL}, row "{row}", column "{column}": {printed}'
        if option == "electric":
            note += f'. The article\'s text (Discussion, Figure 11): "{BATTERY_SENTENCE}".'
        obs.append(
            Observation(
                entity=ENTITY,
                period=PERIOD,
                value=float(printed_number(printed)),
                note=note,
                dims={"option": option, "side": side},
            )
        )
    return obs


def _run_for(indicator: str):
    def run(files: dict[str, InputFile]) -> Result:
        f = files[ARTICLE.key]
        obs = observations(f.path.read_bytes(), indicator)
        return Result(
            observations=obs,
            vintage=VINTAGE,
            date_published=PUBLISHED,
            steps=[
                f"Read the article's JATS XML from Europe PMC (sha256 {f.snapshot.sha256[:12]}…) and checked its DOI, "
                f"the caption and column headers of {LABEL} and {len(SENTENCES)} sentences of the text.",
                f"Published the row '{ROWS[indicator]}' for the petrol, diesel and electric cars, each cell addressed "
                "by its printed row label and column header and published as printed (thousands separators "
                "removed), after checking that each car's service life reads 400,000 km and 15 years.",
                "Left out the CNG and hybrid cars. Nothing was subtracted: the petrol, diesel and electric costs are "
                "shown side by side as the table gives them.",
            ],
            published_value=PublishedValueRef(document=SOURCE, locator=LABEL, quote=f"{LABEL}. {CAPTION}"),
        )

    return run


def _spec(indicator: str, title: str, description: str, unit: Unit, decimals: int) -> Spec:
    return Spec(
        id=indicator,
        title=title,
        description=description,
        kind="published-value",
        unit=unit,
        display=Display(decimals=decimals),
        scope=Scope(
            geography="Czechia: one car model per drive type as offered on the Czech market in 2022",
            basis="Modelled life cycle cost over 400,000 km and 15 years: purchase price, fuel or electricity, "
            "fluids, tyres, batteries, mandatory costs and maintenance, in euros (currency year not stated). Prices "
            "of 2022; not a market average. For the electric car the article's text gives €0.21 per km without and "
            "€0.25 with a battery replacement; Table 1's value is published as printed.",
        ),
        geo_coverage="country",
        headline_entity=ENTITY,
        dimensions=(
            Dimension(
                id="option",
                label="Car",
                values=[DimensionValue(id=k, label=label) for k, (_, label) in OPTIONS.items()],
            ),
            side_dimension(SIDE_LABELS),
        ),
        headline_dims=(("option", "electric"), ("side", "low-carbon")),
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=_spec(
                PER_KM,
                "Cost per kilometre of petrol, diesel and electric cars in Czechia (Furch et al. 2022)",
                "What a petrol, a diesel and a battery electric car cost per kilometre over 400,000 km and 15 years "
                "on the Czech market in 2022, counting purchase, energy and maintenance, as Furch and colleagues "
                "(2022) model it for one car of each kind.",
                Unit(code="EUR-per-km", label="euros per kilometre", short="€/km"),
                3,
            ),
            inputs=(ARTICLE,),
            run=_run_for(PER_KM),
            module_file=Path(__file__),
            validation=Validation(min_rows=3, value_range=(0.01, 5.0)),
        ),
        Transform(
            spec=_spec(
                LIFETIME,
                "Life cycle cost of petrol, diesel and electric cars in Czechia (Furch et al. 2022)",
                "What a petrol, a diesel and a battery electric car cost in total over 400,000 km and 15 years on "
                "the Czech market in 2022, counting purchase, energy and maintenance, as Furch and colleagues (2022) "
                "model it for one car of each kind.",
                Unit(code="EUR", label="euros over the car's life", short="€"),
                0,
            ),
            inputs=(ARTICLE,),
            run=_run_for(LIFETIME),
            module_file=Path(__file__),
            validation=Validation(min_rows=3, value_range=(1000.0, 1000000.0)),
        ),
    ]
