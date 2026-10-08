"""Rosenow et al. (2025): the lifetime cost of a gas boiler and of an air-source heat pump for a typical home in Great
Britain, from Table 2 of the article.

Input: the article's JATS XML from Europe PMC (PMC11803245, CC BY 4.0).

What Table 2 holds: the total cost of ownership (TCO: installation cost, minus the Boiler Upgrade Scheme grant for the
heat pump, plus running costs over the system's life discounted from the second year) for five columns (the central
scenario and four sensitivity cases) and five rows. This transform publishes the two business-as-usual rows,
"BAU—gas boiler" and "BAU—heat pump", in every column: in each column both systems are costed on the same
assumptions. The policy rows (levies moved to general taxation or to gas, a carbon tax on gas) each give only one of
the two systems and are not published.

The grant: the article says "we assumed grant support for heat pump installs at the current BUS levels" and does not
print the amount. Every column includes it except "No BUS grant and 25% cost reduction", which removes the grant and
also lowers the heat pump's installation cost by 25%; the column labels are published exactly as printed.

Every cell is addressed by its row label and column header, both checked exactly, and the caption and the sentences
the scope relies on are checked too (envdash.greenpremium). "£15,640" is published as 15640: no other change.
"""

from __future__ import annotations

from pathlib import Path

from envdash.greenpremium import check_sentences, jats_doi, jats_root, jats_table, printed_number, side_dimension
from envdash.models import Dimension, DimensionValue, Display, Observation, PublishedValueRef, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "rosenow-2025"
ARTICLE = Input(SOURCE, "article-xml")
INDICATOR = "green-premium.rosenow-2025.heating"
DOI = "10.1016/j.isci.2025.111784"
VINTAGE = "iScience 28, 111784 (2025)"
PUBLISHED = "2025-01-10"
PERIOD = "2025"
ENTITY = "GBR"

LABEL = "Table 2"
CAPTION = (
    "Sensitivity analysis, giving the TCO for different scenarios (gas boiler at 85% efficiency, heat pump with SCOP "
    "of 2.9)"
)
# case id -> column header as printed
CASES: dict[str, str] = {
    "central": "Central scenario",
    "discount-rate-7": "7% discount rate",
    "heat-demand-plus-10": "10% higher heat demand for heat pump",
    "no-grant-cost-minus-25": "No BUS grant and 25% cost reduction",
    "heat-pump-life-20": "20 years lifetime heat pump",
}
HEADER = ("", *CASES.values())
# option id -> (side, row label as printed, label)
OPTIONS: dict[str, tuple[str, str, str]] = {
    "gas-boiler": ("conventional", "BAU—gas boiler", "Gas boiler (85% efficiency)"),
    "heat-pump": ("low-carbon", "BAU—heat pump", "Air-source heat pump (seasonal efficiency 2.9)"),
}
SIDE_LABELS = {"conventional": "Gas boiler", "low-carbon": "Heat pump"}
SENTENCES: list[tuple[str, str]] = [
    ("Sensitivity analysis", "We assumed a 15-year lifetime for both heat pumps and gas boilers."),
    ("Discount rate", "In line with the UK Government’s Green Book we use a discount rate (i) of 3.5%."),
    ("Discussion", "In our calculations, we assumed grant support for heat pump installs at the current BUS levels."),
    (
        "Capital costs",
        "The average cost of an air source heat pump install (including the heating system and labour) in 2022 was "
        "£12,088 according to Microgeneration Certification Scheme (MCS) dashboard.",
    ),
    ("Sensitivity analysis", "(4) assuming no BUS grant and a 25% heat pump cost reduction."),
    ("Energy prices", "price data projections have been obtained from DESNZ"),
]


def observations(raw: bytes) -> list[Observation]:
    root = jats_root(raw)
    if jats_doi(root) != DOI:
        raise ValueError(f"{SOURCE}: the XML is not the article {DOI}")
    check_sentences(root, SENTENCES)
    table = jats_table(root, LABEL, CAPTION)
    obs = []
    for option, (side, row, _) in OPTIONS.items():
        for case, column in CASES.items():
            printed = table.cell(HEADER, row, column)
            obs.append(
                Observation(
                    entity=ENTITY,
                    period=PERIOD,
                    value=float(printed_number(printed, prefix="£")),
                    note=f'{LABEL}, row "{row}", column "{column}": {printed}',
                    dims={"option": option, "side": side, "case": case},
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
            f"the caption of {LABEL} and {len(SENTENCES)} sentences of the methods that the scope relies on.",
            f"Published the {len(obs)} cells of the rows 'BAU—gas boiler' and 'BAU—heat pump' in all five columns, "
            "each addressed by its printed row label and column header, as printed without the pound sign and the "
            "thousands separator.",
            "Left out the policy rows, which each cost only one of the two systems. Nothing was subtracted: the gas "
            "boiler and heat pump totals are shown side by side as the table gives them.",
        ],
        published_value=PublishedValueRef(document=SOURCE, locator=LABEL, quote=f"{LABEL}. {CAPTION}"),
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id=INDICATOR,
                title="Lifetime cost of a gas boiler and a heat pump in Great Britain (Rosenow et al. 2025)",
                description="What heating a typical home in Great Britain costs over 15 years with a gas boiler and "
                "with an air-source heat pump, as Rosenow and colleagues (2025) calculate it: installation, minus the "
                "Boiler Upgrade Scheme grant for the heat pump, plus energy and maintenance, discounted. The central "
                "case and four sensitivity cases are given; all but one include the grant.",
                kind="published-value",
                unit=Unit(
                    code="GBP",
                    label="pounds, total cost of ownership over the system's life",
                    short="£",
                ),
                display=Display(decimals=0),
                scope=Scope(
                    geography="Great Britain, a typical gas-heated home",
                    basis="Modelled total cost of ownership (net present value at a 3.5% discount rate, 7% in one "
                    "case; 15-year life for both systems unless a case says otherwise), with the 2022 average heat "
                    "pump installation cost from the MCS dashboard and DESNZ energy price projections under business "
                    "as usual. The heat pump total includes the Boiler Upgrade Scheme grant at its level when the "
                    "article was written, except in the case 'No BUS grant and 25% cost reduction'. The period is "
                    "the year the article was published; the currency year is not stated.",
                ),
                geo_coverage="country",
                headline_entity=ENTITY,
                dimensions=(
                    Dimension(
                        id="option",
                        label="Heating system",
                        values=[DimensionValue(id=k, label=label) for k, (_, _, label) in OPTIONS.items()],
                    ),
                    side_dimension(SIDE_LABELS),
                    Dimension(
                        id="case",
                        label="Case (Table 2 column)",
                        values=[DimensionValue(id=k, label=v) for k, v in CASES.items()],
                    ),
                ),
                headline_dims=(("option", "heat-pump"), ("side", "low-carbon"), ("case", "central")),
            ),
            inputs=(ARTICLE,),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=10, value_range=(1000.0, 100000.0)),
        )
    ]
