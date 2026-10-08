"""Sacchi et al. (2023): the levelised cost of synthetic jet fuel for European aviation in 2030 and 2050, from Table 4
of the article, with no fossil comparator.

Input: the article's JATS XML from Europe PMC (PMC10326079, CC BY 4.0).

What Table 4 holds: two blocks, each headed by its own column headers. The second block, "LC syn-jet fuel (€/kgJF)
2030" and "... 2050", gives the levelised cost of synthetic (Fischer-Tropsch, from hydrogen and CO2) jet fuel in the
2 °C and the 3.5 °C climate scenario. Those four cells are published. The first block (the levelised cost of
hydrogen) is an intermediate and is not.

Why there is no conventional value. The Methods state "The cost of conventional jet fuel is assumed to be 0.50 €/kg,
corresponding to the average production cost in 2019", citing Becattini et al. (2021), whose Table 1 gives 502 €/t
for jet fuel production and cites an International Energy Agency chart of 2019 production costs. That number is a
third party's cost for 2019 taken as an input, not a cost the study computes on the basis of its 2030 and 2050
synthetic fuel costs, so it is not published. The conventional side carries one missing value per scenario and year,
with that sentence as the reason, so a chart shows "no fossil comparator" instead of nothing.
"""

from __future__ import annotations

from pathlib import Path

from envdash.greenpremium import check_sentences, jats_doi, jats_root, jats_table, printed_number, side_dimension
from envdash.models import Dimension, DimensionValue, Display, Observation, PublishedValueRef, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "sacchi-2023"
ARTICLE = Input(SOURCE, "article-xml")
INDICATOR = "green-premium.sacchi-2023.jet-fuel"
DOI = "10.1038/s41467-023-39749-y"
VINTAGE = "Nature Communications 14, 3989 (2023)"
PUBLISHED = "2023-07-06"
ENTITY = "EUR_STUDY"

LABEL = "Table 4"
CAPTION = (
    "Levelized costs (LC) for H2 and synthetic fuel production and compression estimated for 2030 and 2050 for the 2 ° "
    "and 3.5 °C climate scenarios"
)
YEARS: dict[str, str] = {"2030": "LC syn-jet fuel (€/kgJF) 2030", "2050": "LC syn-jet fuel (€/kgJF) 2050"}
HEADER = ("", *YEARS.values())
# scenario id -> (row label as printed, label)
SCENARIOS: dict[str, tuple[str, str]] = {
    "2c": ("2 °C", "2 °C climate scenario (RCP 2.6)"),
    "3-5c": ("3.5 °C", "3.5 °C climate scenario (RCP 6)"),
}
OPTIONS: dict[str, tuple[str, str]] = {
    "conventional-jet-fuel": ("conventional", "Conventional (fossil) jet fuel"),
    "synthetic-jet-fuel": ("low-carbon", "Synthetic jet fuel from hydrogen and CO2 (Fischer-Tropsch)"),
}
SIDE_LABELS = {"conventional": "Fossil jet fuel", "low-carbon": "Synthetic jet fuel"}
FOSSIL_SENTENCE = (
    "The cost of conventional jet fuel is assumed to be 0.50 €/kg, corresponding to the average production cost in 2019"
)
SENTENCES: list[tuple[str, str]] = [
    ("Methods, Fuel supply", FOSSIL_SENTENCE),
    (
        "Methods, Fuel supply",
        "Table 4 summarizes the levelized cost of synthetic jet fuel supply estimated for 2030 and 2050.",
    ),
    (
        "Methods, European fleet",
        "European air traffic is comprised of flights departing from the EU-27 as well as EFTA member states.",
    ),
    ("Table 6, column headers", "RCP 6 (3.5 °C scenario)"),
    ("Table 6, column headers", "RCP 2.6 (2 °C scenario)"),
]
NO_COMPARATOR = (
    "No fossil comparator in Sacchi et al. (2023). The article's only conventional jet fuel cost is an input it takes "
    f'from another study: "{FOSSIL_SENTENCE}" (Methods, citing Becattini et al. 2021, who cite an International '
    "Energy Agency chart). It is a third party's 2019 cost, not one the study computes for 2030 or 2050."
)


def observations(raw: bytes) -> list[Observation]:
    root = jats_root(raw)
    if jats_doi(root) != DOI:
        raise ValueError(f"{SOURCE}: the XML is not the article {DOI}")
    check_sentences(root, SENTENCES)
    table = jats_table(root, LABEL, CAPTION)
    obs = []
    for option, (side, _) in OPTIONS.items():
        for scenario, (row, _) in SCENARIOS.items():
            for year, column in YEARS.items():
                dims = {"option": option, "side": side, "scenario": scenario}
                if side == "conventional":
                    obs.append(
                        Observation(
                            entity=ENTITY,
                            period=year,
                            value=None,
                            status="projection",
                            missing_reason=NO_COMPARATOR,
                            dims=dims,
                        )
                    )
                    continue
                printed = table.cell(HEADER, row, column)
                obs.append(
                    Observation(
                        entity=ENTITY,
                        period=year,
                        value=float(printed_number(printed)),
                        status="projection",
                        note=f'{LABEL}, row "{row}", column "{column}": {printed}',
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
            f"Read the article's JATS XML from Europe PMC (sha256 {f.snapshot.sha256[:12]}…) and checked its DOI, "
            f"the caption of {LABEL} and {len(SENTENCES)} sentences of the Methods.",
            f"Published the {n} levelised costs of synthetic jet fuel in {LABEL} (two scenarios, 2030 and 2050), each "
            "addressed by its printed scenario row and column header, exactly as printed.",
            "Published no value for conventional jet fuel: the article's 0.50 €/kg is a third party's 2019 production "
            "cost used as an input (via Becattini et al. 2021, from an International Energy Agency chart), so each "
            "conventional cell is a missing value that says so.",
        ],
        published_value=PublishedValueRef(document=SOURCE, locator=LABEL, quote=f"{LABEL}. {CAPTION}"),
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id=INDICATOR,
                title="Cost of synthetic jet fuel for European aviation (Sacchi et al. 2023)",
                description="The projected cost of making a kilogram of synthetic jet fuel from hydrogen and CO2 "
                "with European electricity in 2030 and 2050, under a 2 °C and a 3.5 °C climate scenario, as Sacchi "
                "and colleagues (2023) estimate it. The study gives no cost of fossil jet fuel of its own for those "
                "years, so there is no fossil comparator.",
                kind="published-value",
                unit=Unit(code="EUR-per-kg", label="euros per kilogram of jet fuel", short="€/kg"),
                display=Display(decimals=1),
                scope=Scope(
                    geography="Europe as the study defines it: aviation departing from the EU-27 and EFTA countries, "
                    "with European electricity costs",
                    basis="Modelled levelised cost of production (projections for 2030 and 2050), with electricity "
                    "costs from the REMIND model and learning rates for electrolysis and direct air capture that "
                    "depend on the scenario. The currency year is not stated.",
                ),
                geo_coverage="global-only",
                headline_entity=ENTITY,
                dimensions=(
                    Dimension(
                        id="option",
                        label="Fuel",
                        values=[DimensionValue(id=k, label=label) for k, (_, label) in OPTIONS.items()],
                    ),
                    side_dimension(SIDE_LABELS),
                    Dimension(
                        id="scenario",
                        label="Climate scenario",
                        values=[DimensionValue(id=k, label=label) for k, (_, label) in SCENARIOS.items()],
                    ),
                ),
                headline_dims=(("option", "synthetic-jet-fuel"), ("side", "low-carbon"), ("scenario", "2c")),
            ),
            inputs=(ARTICLE,),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=8, value_range=(0.1, 20.0)),
        )
    ]
