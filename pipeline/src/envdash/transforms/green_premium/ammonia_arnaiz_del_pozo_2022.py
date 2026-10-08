"""Arnaiz del Pozo & Cloete (2022): the levelised cost of ammonia from natural gas without and with CO2 capture and
from wind and solar power, as the article states it.

Input: the version-of-record PDF on the Universidad Politécnica de Madrid repository (CC BY 4.0), 17 pages; PDF page
n is printed page n.

What is published. Section 4 (Summary & conclusions) states the levelised cost of ammonia (LCOA) of every plant, and
the abstract repeats two of them:
- at European energy prices (natural gas 6.5 €/GJ, electricity 60 €/MWh, CO2 tax 100 €/ton, Table 4): the KBR
  Purifier plant without CO2 capture (479.0), the KBR plant with capture (385.9), the Linde Ammonia Concept with
  capture (385.1) and the gas switching reforming plant, the paper's advanced blue process (332.1);
- green ammonia from optimised wind and solar power with electrolysers and storage, with 2050 technology costs, in
  northern Germany (772.1), southern Spain (569.3) and Saudi Arabia (484.7);
- the gas switching reforming plant at Saudi Arabian energy prices (192.7).
Section 3.2.3 says the blue plants "were compared to green NH3 plants under consistent assumptions for the year
2050", so every value has the period 2050 and the status projection. Costs are in 2020 euros on a Western Europe
cost basis (Table 3).

Each value is read from a Passage copied verbatim from its page (envdash.greenpremium); a list of values with a list
of places ("772.1, 569.3, and 484.7 €/ton in Northern Germany, Southern Spain, and Saudi Arabia, respectively") is
read in the order the places are named. Where the abstract states a value again, both statements must agree, or the
value is published as missing with both statements as the reason. The abstract's ranges ("385.1–385.9 €/ton for the
conventional plants", "484.7–772.1 €/ton") are joint statements for several plants and are not read.

The European-price plants are placed at the entity EUR_STUDY ("Europe, as the study cited defines it"): the article
prices them at "European energy prices", which its Table 5 applies alike to Germany and Spain, and does not cost them
for any one country. No value is copied to another place.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from envdash import textmatch
from envdash.greenpremium import Passage, check_passages, side_dimension, stated
from envdash.models import Dimension, DimensionValue, Display, Observation, PublishedValueRef, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "arnaiz-del-pozo-2022"
ARTICLE = Input(SOURCE, "article-pdf")
INDICATOR = "green-premium.arnaiz-del-pozo-2022.ammonia"
VINTAGE = "Energy Conversion and Management 255, 115312 (2022)"
PUBLISHED = "2022-02-05"
PERIOD = "2050"

# option id -> (side, label)
OPTIONS: dict[str, tuple[str, str]] = {
    "kbr-without-capture": ("conventional", "KBR Purifier process without CO2 capture"),
    "kbr": ("conventional-with-capture", "KBR Purifier process with CO2 capture"),
    "lac": ("conventional-with-capture", "Linde Ammonia Concept (LAC) with CO2 capture"),
    "gsr": ("conventional-with-capture", "Gas switching reforming (GSR), advanced blue ammonia"),
    "green": ("low-carbon", "Green ammonia from wind and solar power"),
}
SIDE_LABELS = {
    "conventional": "Natural gas, CO2 released",
    "conventional-with-capture": "Natural gas with CO2 capture (blue)",
    "low-carbon": "Wind and solar power (green)",
}
# setting id -> (entity, label)
SETTINGS: dict[str, tuple[str, str]] = {
    "european-prices": ("EUR_STUDY", "European energy prices (natural gas 6.5 €/GJ, electricity 60 €/MWh)"),
    "northern-germany": ("DEU", "Northern Germany, 2050 technology costs"),
    "southern-spain": ("ESP", "Southern Spain, 2050 technology costs"),
    "saudi-arabia": ("SAU", "Saudi Arabia"),
}

ABSTRACT = Passage(
    1,
    "A cash flow analysis showed that the GSR concept achieved an attractive levelized cost of ammonia (LCOA) of 332.1 "
    "€/ton relative to 385.1–385.9 €/ton for the conventional plants at European energy prices (6.5 €/GJ natural gas "
    "and 60 €/MWh electricity). Optimal technology integration for green ammonia using technology costs "
    "representative of 2050 was considerably more expensive: 484.7–772.1 €/ton when varying the location from Saudi "
    "Arabia to Germany. Furthermore, the LCOA of the GSR technology drops to 192.7 €/ton when benefitting from low "
    "Saudi Arabian energy costs (2 €/GJ natural gas and 40 €/MWh electricity).",
    "Abstract, p. 1",
)
BLUE_P14 = Passage(
    14,
    "From an economic perspective, the KBR process achieves a levelized cost of ammonia (LCOA) of 385.9 €/ton. When "
    "the plant is designed without CCS, the cost rises to 479.0 €/ton (19.4% increase) at a CO2",
    "Section 4 (Summary & conclusions), p. 14",
)
BLUE_P15 = Passage(
    15,
    "tax of 100 €/ton. The LAC plant reaches an almost identical LCOA as the KBR (385.1 €/ton), while for the GSR "
    "concept the cost falls to 332.1 €/ton (-13.9%). Variations in natural gas price and CO2 tax presented the "
    "largest effect on the LCOA.",
    "Section 4 (Summary & conclusions), p. 15",
)
GREEN_P15 = Passage(
    15,
    "Using cost assumptions applicable to 2050, fully optimized green ammonia production from wind and solar power "
    "with electrolysers and energy storage showed substantially higher costs than the blue NH3 alternatives: 772.1, "
    "569.3, and 484.7 €/ton in Northern Germany, Southern Spain, and Saudi Arabia, respectively. Moreover, the LCOA "
    "of blue NH3 production in Saudi Arabia reduced to 192.7 €/ton with the GSR process due to much lower energy "
    "costs.",
    "Section 4 (Summary & conclusions), p. 15",
)
# Statements the indicator's scope relies on, checked like the values.
CONTEXT = (
    Passage(8, "Target cost basis details. Location Western Europe Year 2020 Currency €", "Table 3, p. 8"),
    Passage(9, "Natural gas 6.5 €/GJ Electricity 60 €/MWh", "Table 4, p. 9"),
    Passage(9, "CO2 transport & storage 20 €/ton CO2 tax 100 €/ton", "Table 4, p. 9"),
    Passage(9, "Discount Rate 8 % Construction period 4 years Plant Lifetime 25 years", "Table 4, p. 9"),
    Passage(
        9,
        "Natural gas price (€/GJ) 6.5 6.5 2 Electricity price (€/MWh) 60 60 40 CO2 transport and storage (€/ton) 20 "
        "20 0",
        "Table 5, p. 9",
    ),
    Passage(
        13,
        "The blue NH3 plants evaluated in this work were compared to green NH3 plants under consistent assumptions "
        "for the year 2050",
        "Section 3.2.3, p. 13",
    ),
)
GREEN_WORDS = "772.1, 569.3, and 484.7 €/ton in Northern Germany, Southern Spain, and Saudi Arabia, respectively"


@dataclass(frozen=True)
class Value:
    option: str
    setting: str
    passage: Passage
    words: str
    printed: str


VALUES: tuple[Value, ...] = (
    Value("kbr-without-capture", "european-prices", BLUE_P14, "without CCS, the cost rises to 479.0", "479.0"),
    Value(
        "kbr",
        "european-prices",
        BLUE_P14,
        "the KBR process achieves a levelized cost of ammonia (LCOA) of 385.9",
        "385.9",
    ),
    Value(
        "lac", "european-prices", BLUE_P15, "The LAC plant reaches an almost identical LCOA as the KBR (385.1", "385.1"
    ),
    Value("gsr", "european-prices", BLUE_P15, "for the GSR concept the cost falls to 332.1", "332.1"),
    Value(
        "gsr",
        "european-prices",
        ABSTRACT,
        "the GSR concept achieved an attractive levelized cost of ammonia (LCOA) of 332.1",
        "332.1",
    ),
    Value("green", "northern-germany", GREEN_P15, GREEN_WORDS, "772.1"),
    Value("green", "southern-spain", GREEN_P15, GREEN_WORDS, "569.3"),
    Value("green", "saudi-arabia", GREEN_P15, GREEN_WORDS, "484.7"),
    Value(
        "gsr", "saudi-arabia", GREEN_P15, "the LCOA of blue NH3 production in Saudi Arabia reduced to 192.7", "192.7"
    ),
    Value("gsr", "saudi-arabia", ABSTRACT, "the LCOA of the GSR technology drops to 192.7", "192.7"),
)
PASSAGES = [ABSTRACT, BLUE_P14, BLUE_P15, GREEN_P15, *CONTEXT]
HEADLINE = ("kbr-without-capture", "european-prices")


def observations(values: tuple[Value, ...] = VALUES) -> list[Observation]:
    """One observation per (option, setting), in OPTIONS then SETTINGS order. Call check_passages first."""
    found: dict[tuple[str, str], list[Value]] = defaultdict(list)
    for v in values:
        if v.option not in OPTIONS or v.setting not in SETTINGS:
            raise ValueError(f"unknown option or setting in {v}")
        found[(v.option, v.setting)].append(v)
    obs = []
    for option, (side, _) in OPTIONS.items():
        for setting, (entity, _) in SETTINGS.items():
            said = found.get((option, setting))
            if not said:
                continue
            numbers = {stated(v.passage, v.words, v.printed) for v in said}
            note = " / ".join(f'{v.passage.locator}: "{v.words}"' for v in said)
            dims = {"option": option, "side": side, "setting": setting}
            if len(numbers) > 1:
                obs.append(
                    Observation(
                        entity=entity,
                        period=PERIOD,
                        value=None,
                        status="projection",
                        missing_reason="The article states different values: "
                        + "; ".join(f"{v.printed} in {v.passage.locator}" for v in said),
                        note=note,
                        dims=dims,
                    )
                )
                continue
            obs.append(
                Observation(
                    entity=entity, period=PERIOD, value=float(numbers.pop()), status="projection", note=note, dims=dims
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
            f"Read the text of the article's version-of-record PDF (sha256 {f.snapshot.sha256[:12]}…, the copy on "
            f"the Universidad Politécnica de Madrid repository) and found {len(PASSAGES)} passages from the abstract, "
            "section 3.2.3, section 4 and Tables 3 and 4 word for word on their pages.",
            f"Published the {len(obs)} levelised costs of ammonia that the passages state, exactly as printed, in "
            "euros per tonne. Values listed with several places are read in the order the places are named. Where "
            "the abstract repeats a value, both statements agree and both are in the value's note.",
            "Placed the plants costed at European energy prices at 'Europe, as the study defines it', the green "
            "plants in Germany, Spain and Saudi Arabia, and the gas switching reforming plant at Saudi prices in "
            "Saudi Arabia. Nothing was subtracted or divided: the conventional and lower-carbon costs are shown side "
            "by side as the article gives them.",
        ],
        published_value=PublishedValueRef(document=SOURCE, locator=GREEN_P15.locator, quote=GREEN_P15.text),
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id=INDICATOR,
                title="Cost of making ammonia from natural gas and from wind and solar power (Arnaiz del Pozo & "
                "Cloete 2022)",
                description="The levelised cost of a tonne of ammonia from natural-gas plants that release their "
                "CO2, natural-gas plants that capture it (blue ammonia) and plants run on wind and solar power "
                "(green ammonia), modelled by Arnaiz del Pozo and Cloete (2022) with one synthesis loop and one cost "
                "method. The natural-gas plants pay a CO2 tax of 100 euros per tonne on what they emit, which is "
                "included in their cost; the green plants use technology costs expected for 2050.",
                kind="published-value",
                unit=Unit(code="EUR-per-t", label="euros per tonne of ammonia (2020 euros)", short="€/t"),
                display=Display(decimals=1),
                scope=Scope(
                    geography="Natural-gas plants at European energy prices (Western Europe cost basis) and in Saudi "
                    "Arabia; green plants in northern Germany, southern Spain and Saudi Arabia",
                    basis="Modelled levelised cost (cash-flow analysis: discount rate 8%, 25-year life, 2020 euros), "
                    "not market prices. The article compares all plants under what it calls consistent assumptions "
                    "for 2050. The cost of the natural-gas plants includes a CO2 tax of 100 euros per tonne of CO2 "
                    "emitted and 20 euros per tonne for CO2 transport and storage (none in Saudi Arabia).",
                ),
                geo_coverage="mixed",
                headline_entity=SETTINGS[HEADLINE[1]][0],
                dimensions=(
                    Dimension(
                        id="option",
                        label="How the ammonia is made",
                        values=[DimensionValue(id=k, label=label) for k, (_, label) in OPTIONS.items()],
                    ),
                    side_dimension(SIDE_LABELS),
                    Dimension(
                        id="setting",
                        label="Where and at what energy prices",
                        values=[DimensionValue(id=k, label=label) for k, (_, label) in SETTINGS.items()],
                    ),
                ),
                headline_dims=(
                    ("option", HEADLINE[0]),
                    ("side", OPTIONS[HEADLINE[0]][0]),
                    ("setting", HEADLINE[1]),
                ),
            ),
            inputs=(ARTICLE,),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=8, value_range=(100.0, 1000.0)),
        )
    ]
