"""Project Drawdown, Use Heat Pumps: the yearly cost of a heat pump system and of the baseline heating equipment it
replaces, from the results sheet of Drawdown's solution assessment spreadsheet (CC BY 4.0).

Inputs: drawdown-explorer/use-heat-pumps (the spreadsheet) and drawdown-explorer/methodology-pdf (the June 2026
methodology, which defines the cost rows).

What the results sheet holds: the adoption unit ("installed heat pump system"), then two blocks headed "Cost: 2023
Baseline" and "Cost: Solution", each in "2023 US$/unit/yr", with the initial cost, operating cost, new revenues and
net cost per unit, then the difference "cost per unit solution compared to BAU". Published: the operating cost and the
net cost of the baseline ("BAU") and of the heat pump, as the sheet's cached values. The methodology (p. 17) says
the net cost amortises the initial cost "without discounting" over the equipment's life and adds the operating cost
and subtracts revenues. Not published: the initial cost (a one-off cost per unit, though the block's heading says
per year, so its unit is unclear), the new revenues (zero for both) and Drawdown's own difference (the site shows the
two costs side by side and computes nothing).

The baseline is what Drawdown calls the "Baseline Alternative Unit (BAU)": the heating equipment a heat pump replaces,
as a weighted average across equipment types and regions (its sheet "2. current state cost" labels the operating cost
"operating cost per unit BAU (weighted average)"), not one gas boiler. Only the results sheet is read: the other
sheets embed third-party input tables (EIA, IEA, and others) that the CC BY deposit cannot relicense.

Every label cell beside a value is checked exactly before the value is read; any difference stops the transform.
"""

from __future__ import annotations

from pathlib import Path

from envdash import textmatch
from envdash.greenpremium import Passage, check_passages, side_dimension
from envdash.models import Dimension, DimensionValue, Display, Observation, PublishedValueRef, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation
from envdash.transforms.action.drawdown_explorer import sheet_rows

SOURCE = "drawdown-explorer"
SPREADSHEET = Input(SOURCE, "use-heat-pumps")
METHODOLOGY = Input(SOURCE, "methodology-pdf")
INDICATOR = "green-premium.drawdown-explorer.heating"
SHEET = "results"
PERIOD = "2023"
ENTITY = "WLD"

# (row, column, exact text) of the label cells that must read as declared (1-based row, 0-based column)
LABELS: tuple[tuple[int, int, str], ...] = (
    (4, 0, "Adoption unit"),
    (4, 1, "installed heat pump system"),
    (22, 0, "Cost: 2023 Baseline "),
    (22, 1, "2023 US$/unit/yr"),
    (28, 0, "Cost: Solution"),
    (28, 1, "2023 US$/unit/yr"),
)
# option id -> (side, label)
OPTIONS: dict[str, tuple[str, str]] = {
    "baseline": ("conventional", "Baseline heating equipment (Drawdown's 'BAU', a weighted average, 2023)"),
    "heat-pump": ("low-carbon", "Installed heat pump system"),
}
SIDE_LABELS = {"conventional": "Baseline heating equipment", "low-carbon": "Heat pump"}
COSTS: dict[str, str] = {
    "net": "Net cost per unit (initial cost spread over the equipment's life, plus operating cost)",
    "operating": "Operating cost per unit",
}
# (option, cost) -> (row, label in column 0); the value is in column 1
CELLS: dict[tuple[str, str], tuple[int, str]] = {
    ("baseline", "operating"): (24, "operating cost per unit BAU"),
    ("baseline", "net"): (26, "net cost per unit BAU"),
    ("heat-pump", "operating"): (30, "operating cost per unit solution"),
    ("heat-pump", "net"): (32, "net cost per unit solution"),
}
NET_COST = Passage(
    17,
    "When we include the initial cost in the Net Cost, we amortize it without discounting over 30 years. If 30 years "
    "is not an appropriate time period for implementing the solution, we may choose a different period and state it "
    "in the narrative.",
    "Methodology for Project Drawdown Solutions Assessments (June 2026), p. 17",
)


class DrawdownCostError(ValueError):
    pass


def observations(rows: list[tuple]) -> list[Observation]:
    def cell(r: int, c: int) -> object:
        row = rows[r - 1] if r - 1 < len(rows) else ()
        return row[c] if c < len(row) else None

    for r, c, text in LABELS:
        if cell(r, c) != text:
            raise DrawdownCostError(f"use-heat-pumps '{SHEET}' row {r} column {c}: {cell(r, c)!r} != {text!r}")
    obs = []
    for option, (side, _) in OPTIONS.items():
        for cost in COSTS:
            r, label = CELLS[(option, cost)]
            if cell(r, 0) != label:
                raise DrawdownCostError(f"use-heat-pumps '{SHEET}' row {r}: label {cell(r, 0)!r} != {label!r}")
            v = cell(r, 1)
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise DrawdownCostError(f"use-heat-pumps '{SHEET}' row {r} column 1: {v!r} is not a number")
            obs.append(
                Observation(
                    entity=ENTITY,
                    period=PERIOD,
                    value=float(v),
                    note=f"Use Heat Pumps spreadsheet, sheet '{SHEET}', row {r}: '{label}' (2023 US$/unit/yr).",
                    dims={"option": option, "side": side, "cost": cost},
                )
            )
    return obs


def _run(files: dict[str, InputFile]) -> Result:
    sheet = files[SPREADSHEET.key]
    method = files[METHODOLOGY.key]
    check_passages(textmatch.pdf_pages_text(method.path.read_bytes()), [NET_COST])
    obs = observations(sheet_rows(sheet.path.read_bytes(), SHEET))
    return Result(
        observations=obs,
        vintage="Drawdown Explorer, Use Heat Pumps spreadsheet on Zenodo (methodology June 2026)",
        year="2026",
        steps=[
            "Read the results sheet of Project Drawdown's Use Heat Pumps spreadsheet, checking the adoption unit, "
            "the headings and unit of the baseline and solution cost blocks and the label of every value cell.",
            f"Published {len(obs)} cached cell values as Drawdown gives them: the operating cost and the net cost per "
            "unit per year of the baseline heating equipment and of a heat pump system, in 2023 US dollars.",
            "Checked in the methodology that the net cost amortises the initial cost without discounting. Left out "
            "the initial cost, the revenues and Drawdown's difference between the two; nothing was subtracted.",
        ],
        published_value=PublishedValueRef(document=SOURCE, locator=NET_COST.locator, quote=NET_COST.text),
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id=INDICATOR,
                title="Yearly cost of a heat pump and of today's heating equipment (Project Drawdown)",
                description="What heating with a heat pump system costs per year, and what the equipment it "
                "replaces costs, in Project Drawdown's 2026 assessment of heat pumps: the running cost alone, and "
                "the running cost plus the purchase cost spread over the equipment's life without discounting. The "
                "baseline is a weighted average of the heating equipment heat pumps replace, not one type of boiler.",
                kind="published-value",
                unit=Unit(
                    code="USD2023-per-unit-per-year",
                    label="US dollars (2023) per heating system per year",
                    short="US$/system/yr",
                ),
                display=Display(decimals=0),
                scope=Scope(
                    geography="World (Project Drawdown's global estimate)",
                    basis="Project Drawdown's meta-analysis of equipment and energy costs against a 2023 baseline, "
                    "per installed heat pump system and per baseline unit it replaces, in 2023 US dollars. The net "
                    "cost amortises the initial cost without discounting over the equipment's life.",
                ),
                geo_coverage="global-only",
                headline_entity=ENTITY,
                dimensions=(
                    Dimension(
                        id="option",
                        label="Heating",
                        values=[DimensionValue(id=k, label=label) for k, (_, label) in OPTIONS.items()],
                    ),
                    side_dimension(SIDE_LABELS),
                    Dimension(
                        id="cost",
                        label="Cost",
                        values=[DimensionValue(id=k, label=v) for k, v in COSTS.items()],
                    ),
                ),
                headline_dims=(("option", "heat-pump"), ("side", "low-carbon"), ("cost", "net")),
            ),
            inputs=(SPREADSHEET, METHODOLOGY),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=4, value_range=(1.0, 100000.0)),
        )
    ]
