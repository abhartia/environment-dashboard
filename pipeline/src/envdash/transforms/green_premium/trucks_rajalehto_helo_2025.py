"""Rajalehto & Helo (2025): the monthly total cost of ownership of a diesel, a liquid biomethane and a battery electric
heavy truck in one Finnish food logistics company's fleet, from Table 3 of the article.

Input: the version-of-record PDF on the University of Vaasa repository Osuva (CC BY 4.0), 14 pages; PDF page n is
printed page n.

What Table 3 holds (PDF page 8): nine statistics (mean, median, variance, standard deviation, coefficient of variation,
minimum, maximum, range, standard error) of the monthly total cost of ownership from 1,000 Monte Carlo simulations per
truck, in columns Diesel, LBG and EV. The table prints no unit; the costs are in euros (Fig. 2: "TCO (€)") per month
("Comparative monthly TCO statistics"). pypdf extracts the table column by column (all nine Diesel values, then LBG,
then EV), which pdftotext -layout confirmed row by row on 2026-10-08; TABLE_3 is that text, copied verbatim, and each
column is read from it by position. Published: the mean and the median, each with the minimum and maximum of the
simulations as its range. Numbers such as "2.13E4" are published as their value (21,300): no rounding.

Who and when: telemetry and invoices of one company's leased trucks, a Volvo FH6x4 on diesel, a Volvo FH6x4 on liquid
biomethane and a Volvo FH Electric, on comparable routes from January to October 2023, with emissions costed at the
EU ETS price. Not a market average.
"""

from __future__ import annotations

from pathlib import Path

from envdash import textmatch
from envdash.greenpremium import Passage, PrintedValueError, check_passages, printed_number, side_dimension
from envdash.models import Dimension, DimensionValue, Display, Observation, PublishedValueRef, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "rajalehto-helo-2025"
ARTICLE = Input(SOURCE, "article-pdf")
INDICATOR = "green-premium.rajalehto-helo-2025.trucks"
VINTAGE = "Journal of Cleaner Production 509, 145524 (2025)"
PUBLISHED = "2025-04-19"
PERIOD = "2023-01/2023-10"
ENTITY = "FIN"

STATISTICS = (
    "Mean",
    "Median",
    "Variance",
    "Standard Deviation",
    "Coefficient of Variation",
    "Min",
    "Max",
    "Range",
    "Standard Error",
)
# option id -> (side, column header as printed, label, the column's nine printed values in STATISTICS order)
OPTIONS: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "diesel": (
        "conventional",
        "Diesel",
        "Diesel truck (Volvo FH6x4)",
        ("2.13E4", "2.13E4", "6.46E6", "2.54E3", "0,12", "1.53E4", "2.88E4", "1.35E4", "80"),
    ),
    "lbg": (
        "low-carbon",
        "LBG",
        "Liquid biomethane (LBG) truck (Volvo FH6x4)",
        ("1.97E4", "1.92E4", "7.90E6", "2.81E3", "0,14", "1.50E4", "3.95E4", "2.45E4", "89"),
    ),
    "ev": (
        "low-carbon",
        "EV",
        "Battery electric truck (Volvo FH Electric)",
        ("1.76E4", "1.76E4", "1.27E5", "3.57E2", "0,02", "1.63E4", "1.94E4", "3.05E3", "11"),
    ),
}
PUBLISHED_STATISTICS = {
    "mean": ("Mean", "Mean of 1,000 simulations"),
    "median": ("Median", "Median of 1,000 simulations"),
}
SIDE_LABELS = {"conventional": "Diesel", "low-carbon": "Biomethane or electric"}

TABLE_3 = Passage(
    8,
    "Table 3 Comparative monthly TCO statistics from simulations for Diesel, LBG, and EVs. "
    + " ".join(c for _, c, _, _ in OPTIONS.values())
    + " "
    + " ".join(STATISTICS)
    + " "
    + " ".join(" ".join(v) for _, _, _, v in OPTIONS.values()),
    "Table 3, p. 8",
)
CONTEXT = (
    Passage(6, "Fig. 2. TCO (€) as a function of driven kilometers", "Fig. 2 caption, p. 6"),
    Passage(
        4,
        "Vehicle type Volvo FH6x4 Volvo FH6x4 Volvo FH Electric",
        "Table 1, p. 4",
    ),
    Passage(
        1,
        "The dataset comprised telemetry data collected from January to October 2023 from a Finnish food logistics "
        "company utilising low-carbon fuel options.",
        "Abstract, p. 1",
    ),
    Passage(3, "In the present study, 1000 simulations were conducted for each vehicle technology.", "Section 3, p. 3"),
    Passage(
        5,
        "The emissions costs are incorporated into the TCO calculations to evaluate the environmental economic impact "
        "of each vehicle technology.",
        "Section 3, p. 5",
    ),
    Passage(
        6,
        "Fig. 4 illustrates the monthly TCO distributions for each vehicle category, with supplementary statistical "
        "data provided in Table 3.",
        "Section 4, p. 6",
    ),
)
PASSAGES = [TABLE_3, *CONTEXT]


def _value(printed: str) -> float:
    if "," in printed:
        raise PrintedValueError(f"{printed!r}: a decimal comma is not read as a cost")
    return float(printed_number(printed))


def observations() -> list[Observation]:
    """Call check_passages first: TABLE_3 is built from OPTIONS, so this reads exactly the text that was checked."""
    obs = []
    for option, (side, _, _, values) in OPTIONS.items():
        stat = dict(zip(STATISTICS, values, strict=True))
        lower, upper = _value(stat["Min"]), _value(stat["Max"])
        for sid, (printed_name, _) in PUBLISHED_STATISTICS.items():
            obs.append(
                Observation(
                    entity=ENTITY,
                    period=PERIOD,
                    value=_value(stat[printed_name]),
                    lower=lower,
                    upper=upper,
                    interval="range",
                    note=f"Table 3, column {OPTIONS[option][1]}: {printed_name} {stat[printed_name]}, Min "
                    f"{stat['Min']}, Max {stat['Max']} (monthly cost of ownership, 1,000 simulations).",
                    dims={"option": option, "side": side, "statistic": sid},
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
            f"Read the text of the article's version-of-record PDF (sha256 {f.snapshot.sha256[:12]}…, the copy on the "
            f"University of Vaasa repository) and found Table 3 and {len(CONTEXT)} passages of the text and Table 1 "
            "word for word on their pages.",
            "Read each truck's column of Table 3 by position (the PDF's text gives the table column by column) and "
            f"published its mean and median monthly cost of ownership, with the minimum and maximum of the "
            f"simulations as the range: {len(obs)} values, as printed ('2.13E4' is 21,300).",
            "Nothing was subtracted: the diesel, biomethane and electric costs are shown side by side as the table "
            "gives them.",
        ],
        published_value=PublishedValueRef(document=SOURCE, locator=TABLE_3.locator, quote=TABLE_3.text),
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id=INDICATOR,
                title="Monthly cost of running diesel, biomethane and electric trucks in Finland (Rajalehto & Helo "
                "2025)",
                description="What one heavy truck costs a month to run on diesel, on liquid biomethane and on "
                "electricity in one Finnish food logistics company's fleet in 2023: leasing, insurance, driver, "
                "energy and an emissions cost at the EU carbon price, simulated 1,000 times from the company's own "
                "data (Rajalehto and Helo 2025).",
                kind="published-value",
                unit=Unit(code="EUR-per-month", label="euros per truck per month", short="€/month"),
                display=Display(decimals=0),
                scope=Scope(
                    geography="Finland: one food logistics company's leased Volvo trucks (64-tonne combinations, 40 "
                    "pallets) on comparable routes",
                    basis="Monte Carlo simulation (1,000 runs per truck) of the monthly total cost of ownership from "
                    "the company's telemetry, leasing contracts and energy prices of January to October 2023, with "
                    "emissions costed at the EU ETS allowance price. Subsidies are not modelled separately. The "
                    "currency year is not stated.",
                ),
                geo_coverage="country",
                headline_entity=ENTITY,
                dimensions=(
                    Dimension(
                        id="option",
                        label="Truck",
                        values=[DimensionValue(id=k, label=label) for k, (_, _, label, _) in OPTIONS.items()],
                    ),
                    side_dimension(SIDE_LABELS),
                    Dimension(
                        id="statistic",
                        label="Statistic",
                        values=[DimensionValue(id=k, label=label) for k, (_, label) in PUBLISHED_STATISTICS.items()],
                    ),
                ),
                headline_dims=(("option", "diesel"), ("side", "conventional"), ("statistic", "mean")),
            ),
            inputs=(ARTICLE,),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=6, value_range=(1000.0, 100000.0)),
        )
    ]
