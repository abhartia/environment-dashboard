"""Green premiums as their producers state them: how much more the low-emissions way of making something is
estimated to cost than the conventional way, quoted from the producer's own sentence or table row.

Inputs (one PDF per source):
- iea-etp-2026/report-pdf: IEA, Energy Technology Perspectives 2026 (steel, cement, urea);
- iea-ghr-2025/report-pdf: IEA, Global Hydrogen Review 2025 (ammonia, methanol, steel);
- iea-efuels-2023/report-pdf: IEA, The Role of E-fuels in Decarbonising Transport (container shipping);
- gardarsdottir-2019/article-pdf: Gardarsdottir et al. (2019), the CEMCAP cost analysis (cement clinker).

Rules (owner decisions of 2026-10-08):
- A premium is published only as the producer states it (a percentage, or a difference in money per tonne). The
  site never computes one, and nothing here computes one: no clean cost is set against a fossil cost from another
  table, study, region, year or currency year. Where one producer publishes both costs on one basis (CEMCAP's Table
  6), both are published side by side as stated, with the producer's own percentage beside them.
- Costs before subsidies and without a carbon price are preferred; where a statement includes a carbon price (ETP's
  urea figure) or states both (GHR's ammonia with and without USD 100 per tonne of CO2), the scope or a dimension
  says so.
- Values the producer attributes to a third party (BloombergNEF, Argus, S&P Global and others) are not used; each
  source's registry entry lists what was left out.
- IEA material comes only from the PDFs the IEA serves to scripts; nothing is read from iea.org pages or any copy.

Every value comes from a Statement: the verbatim text, the PDF page(s) it is on, and for each value the words inside
the text that state it. Before publishing, the transform
- finds every part of every statement on its page (textmatch rules: whitespace, line-break hyphens, dashes and
  quotation-mark styles are ignored; every letter, digit and punctuation mark must match in order);
- finds every context sentence (currency basis, method notes, figure titles) on its page;
- checks that each value's words are part of its statement and that the number, as printed, is in those words; for a
  table row (`row=True`) the numbers in the row must be exactly the values, in the order given;
- publishes the printed digits as the value (no rounding, no arithmetic). "A-B%" is a range: A is published as the
  low end and B as the high end (dimension "bound"); a single figure ("around 25%", "75% higher") is the stated value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal

from envdash import textmatch
from envdash.models import Dimension, DimensionValue, Display, Observation, PublishedValueRef, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

Status = Literal["final", "preliminary", "projection"]


@dataclass(frozen=True)
class Stated:
    dims: tuple[tuple[str, str], ...]
    printed: str
    """The number exactly as printed."""
    words: str
    """The words of the statement that state it."""


@dataclass(frozen=True)
class Statement:
    locator: str
    parts: tuple[tuple[int, str], ...]
    """(PDF page, verbatim text) in reading order; a sentence broken by a page has two parts."""
    entity: str
    period: str
    values: tuple[Stated, ...]
    status: Status = "projection"
    row: bool = False
    """A table row: the numbers in the text, in order, are exactly the values, in order."""

    @property
    def quote(self) -> str:
        return " ".join(text for _, text in self.parts)


@dataclass(frozen=True)
class Context:
    """A sentence the scope relies on (a currency basis, a method note, a figure title), found on its page."""

    page: int
    text: str


@dataclass(frozen=True)
class Premium:
    id: str
    source: str
    title: str
    description: str
    unit: Unit
    decimals: int
    scope: Scope
    headline_entity: str
    dimensions: tuple[Dimension, ...]
    headline_dims: tuple[tuple[str, str], ...]
    statements: tuple[Statement, ...]
    context: tuple[Context, ...]
    vintage: str
    date_published: str
    value_range: tuple[float, float]
    geo_coverage: Literal["global-only", "country", "mixed"] = "global-only"
    artifact: str = "report-pdf"
    steps: tuple[str, ...] = field(default=())
    """Extra processing notes specific to this indicator."""

    @property
    def input(self) -> Input:
        return Input(self.source, self.artifact)


class GreenPremiumTextError(ValueError):
    pass


def _number_in(printed: str, words: str) -> bool:
    return re.search(rf"(?<![\d.]){re.escape(printed)}(?![\d.]\d|\d)", words) is not None


_NUMBER = re.compile(r"(?<![\d.])\d+(?:\.\d+)?")


def verify(pages: list[str], p: Premium) -> None:
    """Every statement part and context sentence on its page; every value's words in its statement; every number in
    its words; table rows in order; ranges with the low end first."""
    problems: list[str] = []

    def found(page: int, text: str, where: str) -> None:
        if not 1 <= page <= len(pages):
            problems.append(f"{where}: the PDF has {len(pages)} pages; page {page} does not exist")
        elif not textmatch.contains(pages[page - 1], text):
            problems.append(f"{where}: not found on PDF page {page}: {text[:70]!r}...")

    for c in p.context:
        found(c.page, c.text, f"{p.id} context")
    dim_values = {d.id: {v.id for v in d.values} for d in p.dimensions}
    for s in p.statements:
        for page, text in s.parts:
            found(page, text, f"{p.id} {s.locator}")
        for v in s.values:
            if set(dict(v.dims)) != set(dim_values) or any(x not in dim_values[k] for k, x in v.dims):
                problems.append(f"{p.id} {s.locator}: dims {v.dims} do not match the declared dimensions")
            if v.words not in s.quote or not _number_in(v.printed, v.words):
                problems.append(f"{p.id} {s.locator}: {v.printed!r} is not stated by {v.words!r}")
        if s.row and [Decimal(x) for x in _NUMBER.findall(s.quote)] != [Decimal(v.printed) for v in s.values]:
            problems.append(f"{p.id} {s.locator}: the row's numbers are not the values in order")
        bounds: dict[tuple, dict[str, Decimal]] = {}
        for v in s.values:
            d = dict(v.dims)
            if d.get("bound") in ("low", "high"):
                rest = tuple(sorted((k, x) for k, x in v.dims if k != "bound"))
                bounds.setdefault(rest, {})[d["bound"]] = Decimal(v.printed)
        for rest, b in bounds.items():
            if set(b) != {"low", "high"}:
                problems.append(f"{p.id} {s.locator} {rest}: a range needs both ends, has {sorted(b)}")
            elif b["low"] > b["high"]:
                problems.append(f"{p.id} {s.locator} {rest}: low end {b['low']} is above high end {b['high']}")
    if problems:
        raise GreenPremiumTextError("; ".join(problems))


def observations(p: Premium) -> list[Observation]:
    """The published values, in statement order. Call verify() first."""
    return [
        Observation(
            entity=s.entity,
            period=s.period,
            value=float(Decimal(v.printed)),
            status=s.status,
            note=f'{s.locator}: "{s.quote}"',
            dims=dict(v.dims),
        )
        for s in p.statements
        for v in s.values
    ]


def _make(p: Premium) -> Transform:
    def run(files: dict[str, InputFile]) -> Result:
        f = files[p.input.key]
        pages = textmatch.pdf_pages_text(f.path.read_bytes())
        verify(pages, p)
        head = p.statements[0]
        n_pages = sorted({page for s in p.statements for page, _ in s.parts})
        return Result(
            observations=observations(p),
            vintage=p.vintage,
            date_published=p.date_published,
            steps=[
                f"Read the text of the PDF (sha256 {f.snapshot.sha256[:12]}…). Found each of the {len(p.statements)} "
                f"quoted statement(s) word for word on PDF page(s) {', '.join(map(str, n_pages))}, and the "
                f"{len(p.context)} context sentence(s) the scope relies on, before publishing.",
                "Published each number exactly as printed, with its statement in the value's note. A range "
                "'A-B%' is published as its low end A and high end B (dimension 'bound'); nothing was computed, "
                "rounded or combined with any other source.",
                *p.steps,
            ],
            published_value=PublishedValueRef(document=p.source, locator=head.locator, quote=head.quote),
        )

    return Transform(
        spec=Spec(
            id=p.id,
            title=p.title,
            description=p.description,
            kind="published-value",
            unit=p.unit,
            display=Display(decimals=p.decimals),
            scope=p.scope,
            geo_coverage=p.geo_coverage,
            headline_entity=p.headline_entity,
            dimensions=p.dimensions,
            headline_dims=p.headline_dims,
        ),
        inputs=(p.input,),
        run=run,
        module_file=Path(__file__),
        validation=Validation(
            min_rows=sum(len(s.values) for s in p.statements), value_range=p.value_range, monotonic_periods=True
        ),
    )


# --- shared dimensions and units ----------------------------------------------------------------------------------


def _dim(id_: str, label: str, values: dict[str, str]) -> Dimension:
    return Dimension(id=id_, label=label, values=[DimensionValue(id=k, label=v) for k, v in values.items()])


RANGE = _dim("bound", "End of the stated range", {"low": "Low end", "high": "High end"})
POINT_OR_RANGE = _dim(
    "bound",
    "Stated value or end of the stated range",
    {"point": "Stated value", "low": "Low end of the stated range", "high": "High end of the stated range"},
)
PERCENT = Unit(code="percent", label="percent more than the conventional route", short="%")

# --- IEA, Energy Technology Perspectives 2026 ----------------------------------------------------------------------

ETP = "iea-etp-2026"
ETP_VINTAGE = "Energy Technology Perspectives 2026 (IEA, March 2026; revised April and July 2026)"
ETP_PUBLISHED = "2026-03"
ETP_USD = Context(
    32,
    "Unless stated otherwise, USD figures are real 2024 dollars in market exchange rate terms throughout this report.",
)
ETP_STEEL_METHOD = Context(
    162,
    "Conventional production is represented by production from blast furnace basic oxygen furnace and natural gas "
    "direct reduced iron electric arc furnace pathways and near-zero emissions production is represented by hydrogen "
    "direct reduced iron electric arc furnace pathways. Costs do not include any explicit policy supports, e.g. carbon "
    "pricing or subsidies.",
)
ETP_CEMENT_METHOD = Context(
    163,
    "Conventional production is represented by production from dry kiln pathways and near-zero emissions production "
    "is represented by dry kiln with carbon capture and storage pathways. Costs do not include any explicit policy "
    "supports, e.g. carbon pricing or subsidies.",
)
ETP_STEEL_TEXT = (
    "Near-zero emissions steel is more expensive than conventional. This is especially true for iron-based steel, "
    "where levelised costs of production in 2035 are expected to be about 20-145% higher (USD 125-600 per tonne of "
    "crude steel) in the STEPS, in the absence of targeted policy support or significant scale-up."
)
ETP_CEMENT_TEXT = (
    "Near-zero emissions cement remains significantly more expensive, and in 2035 is still 75-150% more costly "
    "(USD 50-175 per tonne) in the STEPS, in the absence of policy support and significant scale-up."
)
ETP_STEEL = Statement(
    "Chapter 3, near-zero emissions steel dashboard, p. 139", ((139, ETP_STEEL_TEXT),), "WLD", "2035", ()
)
ETP_CEMENT = Statement(
    "Chapter 3, near-zero emissions cement dashboard, p. 141", ((141, ETP_CEMENT_TEXT),), "WLD", "2035", ()
)

STEEL_SCOPE = (
    "Levelised cost of producing iron-based steel in 2035 in the IEA's Stated Policies Scenario (STEPS): hydrogen "
    "direct reduced iron with an electric arc furnace, compared with blast furnace-basic oxygen furnace and natural "
    "gas DRI production, region by region; the range runs from lower- to higher-cost regions. Excludes explicit policy "
    "support such as carbon pricing or subsidies (method note, p. 162). Projection."
)
CEMENT_SCOPE = (
    "Levelised cost of producing cement in 2035 in the IEA's Stated Policies Scenario (STEPS): dry kiln with carbon "
    "capture and storage, compared with a dry kiln, region by region; the range runs from lower- to higher-cost "
    "regions. Excludes explicit policy support such as carbon pricing or subsidies (method note, p. 163). Projection."
)


def _range(stmt: Statement, low: str, high: str, words: str) -> Statement:
    return Statement(
        stmt.locator,
        stmt.parts,
        stmt.entity,
        stmt.period,
        (Stated((("bound", "low"),), low, words), Stated((("bound", "high"),), high, words)),
        stmt.status,
    )


URA_DIM = _dim(
    "supply",
    "Where the low-emissions ammonia is made",
    {
        "domestic": "Made in Japan (domestic value chain)",
        "imported-ammonia": "Imported low-emissions ammonia from the Middle East",
    },
)

ETP_PREMIUMS: tuple[Premium, ...] = (
    Premium(
        id="green-premium.iea-etp-2026.steel",
        source=ETP,
        title="Extra cost of near-zero emissions steel in 2035, percent (IEA)",
        description="How much more the IEA expects it to cost to produce near-zero emissions iron-based steel (made "
        "with hydrogen) than conventional steel in 2035 under today's policies, without targeted policy support: "
        "about 20 to 145 percent more, depending on the region.",
        unit=PERCENT,
        decimals=0,
        scope=Scope(geography="World (range across regions)", basis=STEEL_SCOPE),
        headline_entity="WLD",
        dimensions=(RANGE,),
        headline_dims=(("bound", "low"),),
        statements=(_range(ETP_STEEL, "20", "145", "about 20-145% higher"),),
        context=(ETP_STEEL_METHOD,),
        vintage=ETP_VINTAGE,
        date_published=ETP_PUBLISHED,
        value_range=(0, 1000),
    ),
    Premium(
        id="green-premium.iea-etp-2026.steel-usd",
        source=ETP,
        title="Extra cost of near-zero emissions steel in 2035, per tonne (IEA)",
        description="How much more the IEA expects it to cost to produce a tonne of near-zero emissions iron-based "
        "steel (made with hydrogen) than a tonne of conventional steel in 2035 under today's policies, without "
        "targeted policy support: USD 125 to 600 per tonne of crude steel, depending on the region.",
        unit=Unit(
            code="USD2024/t-crude-steel",
            label="US dollars (2024) per tonne of crude steel",
            short="USD/t crude steel",
        ),
        decimals=0,
        scope=Scope(
            geography="World (range across regions)",
            basis=STEEL_SCOPE + " Real 2024 US dollars at market exchange rates (the report's convention, p. 32).",
        ),
        headline_entity="WLD",
        dimensions=(RANGE,),
        headline_dims=(("bound", "low"),),
        statements=(_range(ETP_STEEL, "125", "600", "USD 125-600 per tonne of crude steel"),),
        context=(ETP_STEEL_METHOD, ETP_USD),
        vintage=ETP_VINTAGE,
        date_published=ETP_PUBLISHED,
        value_range=(0, 5000),
    ),
    Premium(
        id="green-premium.iea-etp-2026.cement",
        source=ETP,
        title="Extra cost of near-zero emissions cement in 2035, percent (IEA)",
        description="How much more the IEA expects it to cost to produce near-zero emissions cement (a dry kiln with "
        "carbon capture and storage) than conventional cement in 2035 under today's policies, without policy support: "
        "75 to 150 percent more, depending on the region.",
        unit=PERCENT,
        decimals=0,
        scope=Scope(geography="World (range across regions)", basis=CEMENT_SCOPE),
        headline_entity="WLD",
        dimensions=(RANGE,),
        headline_dims=(("bound", "low"),),
        statements=(_range(ETP_CEMENT, "75", "150", "75-150% more costly"),),
        context=(ETP_CEMENT_METHOD,),
        vintage=ETP_VINTAGE,
        date_published=ETP_PUBLISHED,
        value_range=(0, 1000),
    ),
    Premium(
        id="green-premium.iea-etp-2026.cement-usd",
        source=ETP,
        title="Extra cost of near-zero emissions cement in 2035, per tonne (IEA)",
        description="How much more the IEA expects it to cost to produce a tonne of near-zero emissions cement (a dry "
        "kiln with carbon capture and storage) than a tonne of conventional cement in 2035 under today's policies, "
        "without policy support: USD 50 to 175 per tonne, depending on the region.",
        unit=Unit(code="USD2024/t-cement", label="US dollars (2024) per tonne of cement", short="USD/t cement"),
        decimals=0,
        scope=Scope(
            geography="World (range across regions)",
            basis=CEMENT_SCOPE + " Real 2024 US dollars at market exchange rates (the report's convention, p. 32).",
        ),
        headline_entity="WLD",
        dimensions=(RANGE,),
        headline_dims=(("bound", "low"),),
        statements=(_range(ETP_CEMENT, "50", "175", "USD 50-175 per tonne"),),
        context=(ETP_CEMENT_METHOD, ETP_USD),
        vintage=ETP_VINTAGE,
        date_published=ETP_PUBLISHED,
        value_range=(0, 5000),
    ),
    Premium(
        id="green-premium.iea-etp-2026.urea",
        source=ETP,
        title="Extra cost of low-emissions urea in Japan in 2035 (IEA)",
        description="How much more the IEA expects low-emissions urea fertiliser to cost to produce in Japan than "
        "conventional urea in 2035 under today's policies: about 80 percent more when the low-emissions ammonia in it "
        "is made in Japan, and 55 percent more when that ammonia is imported from the Middle East. Carbon pricing is "
        "included in the costs.",
        unit=PERCENT,
        decimals=0,
        scope=Scope(
            geography="Japan",
            basis="Levelised cost of producing urea in Japan in 2035 in the IEA's Stated Policies Scenario (Figure "
            "1.17), relative to conventional domestic production: the ammonia step by electrolysis compared with "
            "conventional steam methane reforming, biogenic CO2 for the low-emissions case. The cost of carbon pricing "
            "is included (figure note). 'Approximately' applies to the domestic value. Projection.",
        ),
        headline_entity="JPN",
        geo_coverage="country",
        dimensions=(URA_DIM,),
        headline_dims=(("supply", "domestic"),),
        statements=(
            Statement(
                "Chapter 1, question on supply chains, pp. 72-73",
                (
                    (
                        72,
                        "Similarly, Japan faces rising costs in adopting near-zero emissions production, primarily "
                        "as a result of high energy costs due to geographical constraints. Its competitive advantage, "
                        "however, lies in value-added industries further down the supply chain. The Middle East, by "
                        "contrast, benefits from abundant renewable energy resources, making low-emissions ammonia "
                        "imports from this region a",
                    ),
                    (
                        73,
                        "more cost-effective option for Japan; urea cost premiums would fall from approximately "
                        "80% to 55%.",
                    ),
                ),
                "JPN",
                "2035",
                (
                    Stated((("supply", "domestic"),), "80", "urea cost premiums would fall from approximately 80%"),
                    Stated((("supply", "imported-ammonia"),), "55", "to 55%"),
                ),
            ),
        ),
        context=(
            Context(
                73,
                "Production costs of steel and urea using conventional and innovative technologies in the Stated "
                "Policies Scenario, 2035",
            ),
            Context(
                73,
                "for the ammonia step of urea production, electrolysis compared with conventional steam methane "
                "reforming is assumed.",
            ),
            Context(73, "The cost of carbon pricing is included in the LCOP."),
        ),
        vintage=ETP_VINTAGE,
        date_published=ETP_PUBLISHED,
        value_range=(0, 1000),
        steps=(
            "The sentence's 'from approximately 80% to 55%' is read as the premium of the domestic value chain (80) "
            "and of the case with low-emissions ammonia imported from the Middle East (55), the comparison the "
            "sentence makes.",
        ),
    ),
)

# --- IEA, Global Hydrogen Review 2025 ------------------------------------------------------------------------------

GHR = "iea-ghr-2025"
GHR_VINTAGE = "Global Hydrogen Review 2025 (IEA, September 2025; revised October 2025)"
GHR_PUBLISHED = "2025-09"
GHR_FIG = Context(55, "Levelised cost of production of selected materials by technology, 2024")
GHR_FIG_NOTES = Context(
    55,
    "CO2 represents the cost increase if a USD 100/t CO2 tax were in place.",
)
GHR_FIG_SUPPORT = Context(
    55,
    "Costs shown here do not include explicit financial support but may include financial support embedded in "
    "individual cost components (e.g. fossil fuel subsidies).",
)
GHR_BASIS = (
    " Levelised cost of production in 2024 (the text's present tense, matching Figure 2.9, 'Levelised cost of "
    "production of selected materials by technology, 2024'), IEA analysis. Energy costs are regional end-user prices "
    "for industry including taxes and charges; no explicit financial support, though support embedded in cost "
    "components (such as fossil fuel subsidies) may be included (figure note)."
)

ROUTE_NH3 = _dim(
    "route",
    "Low-emissions route",
    {"ccus": "Natural gas with carbon capture (CCUS)", "electrolysis": "Electrolysis (electrolytic hydrogen)"},
)
CO2_COST = _dim(
    "co2_cost",
    "CO2 cost assumed",
    {"none": "Without a CO2 cost", "usd-100": "With a CO2 cost of USD 100 per tonne"},
)
GHR_NH3_TEXT_1 = (
    "In the European Union for instance, the cost gap is around 25% for CCUS and ranges around 120-220% for "
    "electrolysis."
)
GHR_NH3_TEXT_2 = (
    "This could reduce the cost gap to as little as 5% for CCUS, and 75-160% for electrolysis, assuming a CO2 cost of "
    "USD 100/t."
)
METHANOL_ROUTE = _dim(
    "route",
    "Low-emissions route",
    {"ccus": "With carbon capture (CCUS)", "electrolysis": "Electrolysis (electrolytic hydrogen and captured CO2)"},
)
METHANOL_COMPARATOR = _dim(
    "comparator",
    "Conventional route compared with",
    {"unabated-coal": "Unabated coal-based production", "unabated-gas": "Unabated natural gas-based production"},
)
STEEL_COMPARATOR = _dim(
    "comparator",
    "Conventional route compared with",
    {"blast-furnace": "Blast furnace", "unabated-gas-dri": "Unabated natural gas-based direct reduced iron (DRI)"},
)
GHR_STEEL_TEXT = (
    "The cost gap is greater for H2 DRI, ranging from 50% to 140% (depending on the region) when compared with blast "
    "furnaces, and 20% to 80% compared with unabated natural gas-based DRI."
)

GHR_PREMIUMS: tuple[Premium, ...] = (
    Premium(
        id="green-premium.iea-ghr-2025.ammonia",
        source=GHR,
        title="Extra cost of low-emissions ammonia in the European Union (IEA)",
        description="How much more it cost to produce low-emissions ammonia than conventional ammonia from unabated "
        "natural gas in the European Union in 2024, as the IEA states it: around 25 percent more with carbon capture "
        "and about 120 to 220 percent more from electrolysis; as little as 5 percent and 75 to 160 percent more if a "
        "CO2 cost of USD 100 per tonne applied.",
        unit=PERCENT,
        decimals=0,
        scope=Scope(
            geography="European Union",
            basis="Ammonia made with carbon capture or by electrolysis, compared with conventional (unabated natural "
            "gas-based) ammonia." + GHR_BASIS + " The 'with a CO2 cost' values assume USD 100 per tonne of CO2, the "
            "figure's carbon tax case.",
        ),
        headline_entity="EU27",
        geo_coverage="country",
        dimensions=(ROUTE_NH3, CO2_COST, POINT_OR_RANGE),
        headline_dims=(("route", "electrolysis"), ("co2_cost", "none"), ("bound", "low")),
        statements=(
            Statement(
                "Chapter 2, the competitiveness of hydrogen technologies (ammonia), p. 51",
                ((53, GHR_NH3_TEXT_1),),
                "EU27",
                "2024",
                (
                    Stated((("route", "ccus"), ("co2_cost", "none"), ("bound", "point")), "25", "around 25% for CCUS"),
                    Stated(
                        (("route", "electrolysis"), ("co2_cost", "none"), ("bound", "low")),
                        "120",
                        "around 120-220% for electrolysis",
                    ),
                    Stated(
                        (("route", "electrolysis"), ("co2_cost", "none"), ("bound", "high")),
                        "220",
                        "around 120-220% for electrolysis",
                    ),
                ),
                status="final",
            ),
            Statement(
                "Chapter 2, the competitiveness of hydrogen technologies (ammonia), p. 51",
                ((53, GHR_NH3_TEXT_2),),
                "EU27",
                "2024",
                (
                    Stated(
                        (("route", "ccus"), ("co2_cost", "usd-100"), ("bound", "point")),
                        "5",
                        "as little as 5% for CCUS",
                    ),
                    Stated(
                        (("route", "electrolysis"), ("co2_cost", "usd-100"), ("bound", "low")),
                        "75",
                        "75-160% for electrolysis",
                    ),
                    Stated(
                        (("route", "electrolysis"), ("co2_cost", "usd-100"), ("bound", "high")),
                        "160",
                        "75-160% for electrolysis",
                    ),
                ),
                status="final",
            ),
        ),
        context=(GHR_FIG, GHR_FIG_NOTES, GHR_FIG_SUPPORT),
        vintage=GHR_VINTAGE,
        date_published=GHR_PUBLISHED,
        value_range=(0, 1000),
        steps=(
            "'As little as 5%' is published as the stated value 5 for carbon capture with a CO2 cost of USD 100 per "
            "tonne; the sentence gives no other figure for that case.",
        ),
    ),
    Premium(
        id="green-premium.iea-ghr-2025.methanol",
        source=GHR,
        title="Extra cost of low-emissions methanol in China and India (IEA)",
        description="How much more it cost to produce low-emissions methanol than conventional methanol in 2024, as "
        "the IEA states it: in China, around 70 percent more with carbon capture and 160 percent more by electrolysis "
        "than unabated coal-based production; in India, 100 percent more by electrolysis than unabated natural "
        "gas-based production, the lowest gap the IEA found.",
        unit=PERCENT,
        decimals=0,
        scope=Scope(
            geography="China and India",
            basis="Methanol made with carbon capture or from electrolytic hydrogen (with captured CO2), compared with "
            "the country's conventional route: unabated coal in China, unabated natural gas in India." + GHR_BASIS,
        ),
        headline_entity="CHN",
        geo_coverage="country",
        dimensions=(METHANOL_ROUTE, METHANOL_COMPARATOR),
        headline_dims=(("route", "electrolysis"), ("comparator", "unabated-coal")),
        statements=(
            Statement(
                "Chapter 2, the competitiveness of hydrogen technologies (methanol), p. 52",
                (
                    (
                        54,
                        "India currently has the lowest cost gap (100%) between unabated natural gas-based production "
                        "and electrolytic methanol, due to the high cost of imported natural gas.",
                    ),
                ),
                "IND",
                "2024",
                (
                    Stated(
                        (("route", "electrolysis"), ("comparator", "unabated-gas")), "100", "the lowest cost gap (100%)"
                    ),
                ),
                status="final",
            ),
            Statement(
                "Chapter 2, the competitiveness of hydrogen technologies (methanol), p. 52",
                (
                    (
                        54,
                        "In the case of China, the world’s largest producer of methanol, the price gap is around 70% "
                        "for CCUS and 160% for electrolysis compared with unabated coal-based production, which is "
                        "today’s main production route in the country.",
                    ),
                ),
                "CHN",
                "2024",
                (
                    Stated((("route", "ccus"), ("comparator", "unabated-coal")), "70", "around 70% for CCUS"),
                    Stated(
                        (("route", "electrolysis"), ("comparator", "unabated-coal")), "160", "160% for electrolysis"
                    ),
                ),
                status="final",
            ),
        ),
        context=(GHR_FIG, GHR_FIG_SUPPORT),
        vintage=GHR_VINTAGE,
        date_published=GHR_PUBLISHED,
        value_range=(0, 1000),
        steps=(
            "The IEA calls China's figure a 'price gap' in the same paragraph where it calls the others 'cost gaps'; "
            "both describe the levelised cost of production in Figure 2.9.",
        ),
    ),
    Premium(
        id="green-premium.iea-ghr-2025.steel",
        source=GHR,
        title="Extra cost of steel made with hydrogen (IEA, Global Hydrogen Review)",
        description="How much more it cost to make steel from hydrogen-based direct reduced iron (H2 DRI) in 2024, "
        "as the IEA states it: 50 to 140 percent more than blast furnaces and 20 to 80 percent more than unabated "
        "natural gas-based DRI, depending on the region.",
        unit=PERCENT,
        decimals=0,
        scope=Scope(
            geography="World (range across regions)",
            basis="Steel from hydrogen direct reduced iron (captive renewable power, per Figure 2.9), compared with "
            "blast furnaces and with unabated natural gas-based DRI; the range runs across regions." + GHR_BASIS,
        ),
        headline_entity="WLD",
        dimensions=(STEEL_COMPARATOR, RANGE),
        headline_dims=(("comparator", "blast-furnace"), ("bound", "low")),
        statements=(
            Statement(
                "Chapter 2, the competitiveness of hydrogen technologies (steel), p. 51",
                ((53, GHR_STEEL_TEXT),),
                "WLD",
                "2024",
                (
                    Stated((("comparator", "blast-furnace"), ("bound", "low")), "50", "ranging from 50% to 140%"),
                    Stated((("comparator", "blast-furnace"), ("bound", "high")), "140", "ranging from 50% to 140%"),
                    Stated((("comparator", "unabated-gas-dri"), ("bound", "low")), "20", "20% to 80%"),
                    Stated((("comparator", "unabated-gas-dri"), ("bound", "high")), "80", "20% to 80%"),
                ),
                status="final",
            ),
        ),
        context=(GHR_FIG, GHR_FIG_SUPPORT, Context(55, "H2 DRI uses captive power.")),
        vintage=GHR_VINTAGE,
        date_published=GHR_PUBLISHED,
        value_range=(0, 1000),
    ),
)

# --- IEA, The Role of E-fuels in Decarbonising Transport -----------------------------------------------------------

EFUELS = "iea-efuels-2023"
EFUELS_PREMIUMS: tuple[Premium, ...] = (
    Premium(
        id="green-premium.iea-efuels-2023.shipping",
        source=EFUELS,
        title="Extra cost of a containership running on e-fuels in 2030 (IEA)",
        description="How much more the IEA estimates it would cost to own and operate a containership running "
        "entirely on e-ammonia or e-methanol in 2030 than a conventional containership on fossil fuel (heavy fuel "
        "oil): 75 percent more.",
        unit=Unit(code="percent", label="percent more total cost of ownership than a fossil-fuelled ship", short="%"),
        decimals=0,
        scope=Scope(
            geography="World (a representative containership)",
            basis="Total cost of ownership in 2030 of a 9,600 TEU containership with a 58 MW engine at 16 knots, "
            "100,000 nautical miles a year, running on 100% e-ammonia or e-methanol, compared with heavy fuel oil: "
            "vessel modifications, bunkering and fuel costs (Figure 5.7, IEA analysis; port charges and handling fees "
            "excluded). Chapter 5 states the same 75% per tonne-kilometre. Projection.",
        ),
        headline_entity="WLD",
        dimensions=(),
        headline_dims=(),
        statements=(
            Statement(
                "Executive summary, p. 8",
                (
                    (
                        8,
                        "The total cost of ownership of a 100% e-ammonia or e-methanol-fuelled containership would be "
                        "75% higher than a conventional containership operating on fossil fuels.",
                    ),
                ),
                "WLD",
                "2030",
                (Stated((), "75", "would be 75% higher"),),
            ),
        ),
        context=(
            Context(
                56,
                "the use of low-emission e-fuels in containerships would result in a 75% increase in total shipping "
                "costs per unit of activity (tonne kilometres) in 2030",
            ),
            Context(57, "Port charges and handling fees are excluded."),
        ),
        vintage="The Role of E-fuels in Decarbonising Transport (IEA, December 2023; revised January 2024)",
        date_published="2023-12",
        value_range=(0, 1000),
        steps=(
            "The executive summary gives no year in the sentence; chapter 5 (p. 56) states the same 75% for 2030, "
            "which is the period published.",
        ),
    ),
)

# --- Gardarsdottir et al. (2019), CEMCAP ---------------------------------------------------------------------------

CEMCAP = "gardarsdottir-2019"
CEMCAP_ENTITY = "CEMCAP_REF"
CEMCAP_VINTAGE = "Energies 12(3), 542 (2019)"
CEMCAP_PUBLISHED = "2019-02-01"
CEMCAP_BASIS = (
    "One modelled best-available-technology European cement plant (3,000 tonnes of clinker a day, defined by ECRA), "
    "without CO2 capture and with each of six capture technologies, on one set of prices: coal 3 euros per gigajoule, "
    "electricity 58.1 euros per megawatt-hour, 8% discount rate, 91.3% capacity factor, all costs in 2014 euros, no "
    "carbon tax. The reference plant's direct cost is based on IEAGHG estimates. Capture covers most but not all of "
    "the plant's emissions. The period is the price base year (2014); the article was published in 2019."
)
CEMCAP_CONTEXT = (
    Context(7, "All cost figures are expressed in €2014."),
    Context(9, "No carbon tax is considered in the calculation of variable OPEX."),
)
TECH = _dim(
    "technology",
    "Plant",
    {
        "reference": "Reference plant, no CO2 capture",
        "mea": "With MEA absorption capture",
        "oxyfuel": "With oxyfuel capture",
        "cap": "With chilled ammonia process (CAP) capture",
        "mal": "With membrane-assisted CO2 liquefaction (MAL) capture",
        "cal-tail-end": "With calcium looping capture, tail-end",
        "cal-integrated": "With calcium looping capture, integrated",
    },
)
CLINKER_ROW = "Cost of clinker (€/tclk) 62.6 107.4 93.0 104.9 120.0 105.8 110.3"
CLINKER_VALUES = ("62.6", "107.4", "93.0", "104.9", "120.0", "105.8", "110.3")

CEMCAP_PREMIUMS: tuple[Premium, ...] = (
    Premium(
        id="clinker-cost.cemcap-2019.by-technology",
        source=CEMCAP,
        artifact="article-pdf",
        title="Cost of cement clinker with and without CO2 capture (CEMCAP)",
        description="The cost of making a tonne of clinker, the main ingredient of cement, in one modelled European "
        "cement plant without capturing its CO2 (62.6 euros) and with each of six capture technologies (93.0 to 120.0 "
        "euros), all on the same prices, as the CEMCAP project published it.",
        unit=Unit(code="EUR2014/t-clinker", label="euros (2014) per tonne of clinker", short="€/t clinker"),
        decimals=1,
        scope=Scope(geography="A modelled European reference cement plant", basis=CEMCAP_BASIS),
        headline_entity=CEMCAP_ENTITY,
        geo_coverage="global-only",
        dimensions=(TECH,),
        headline_dims=(("technology", "reference"),),
        statements=(
            Statement(
                "Table 6, p. 10",
                ((11, CLINKER_ROW),),
                CEMCAP_ENTITY,
                "2014",
                tuple(
                    Stated((("technology", d.id),), v, CLINKER_ROW)
                    for d, v in zip(TECH.values, CLINKER_VALUES, strict=True)
                ),
                status="final",
                row=True,
            ),
        ),
        context=(
            *CEMCAP_CONTEXT,
            Context(11, "Ref. Cement Plant MEA Oxyfuel CAP MAL CaL-Tail-End CaL-Integrated"),
            Context(9, "Price of electricity (€/MWh) 58.1"),
        ),
        vintage=CEMCAP_VINTAGE,
        date_published=CEMCAP_PUBLISHED,
        value_range=(0, 500),
        steps=(
            "Table 6's column order (Ref. Cement Plant, MEA, Oxyfuel, CAP, MAL, CaL-Tail-End, CaL-Integrated) was "
            "checked in the page text, and the row's numbers had to be exactly the seven values in that order.",
        ),
    ),
    Premium(
        id="green-premium.cemcap-2019.clinker",
        source=CEMCAP,
        artifact="article-pdf",
        title="Extra cost of cement clinker with CO2 capture, percent (CEMCAP)",
        description="How much CO2 capture raises the cost of making clinker in one modelled European cement plant, as "
        "the CEMCAP project states it: by 49 to 92 percent, depending on the capture technology.",
        unit=PERCENT,
        decimals=0,
        scope=Scope(geography="A modelled European reference cement plant", basis=CEMCAP_BASIS),
        headline_entity=CEMCAP_ENTITY,
        geo_coverage="global-only",
        dimensions=(RANGE,),
        headline_dims=(("bound", "low"),),
        statements=(
            Statement(
                "Section 4.1, p. 9",
                (
                    (
                        10,
                        "In general, the cost of clinker increases with 49–92% from the 62.6 €/tclk in the reference "
                        "cement plant when the investigated CO 2 capture technologies are implemented.",
                    ),
                ),
                CEMCAP_ENTITY,
                "2014",
                (
                    Stated((("bound", "low"),), "49", "increases with 49–92%"),
                    Stated((("bound", "high"),), "92", "increases with 49–92%"),
                ),
                status="final",
            ),
        ),
        context=(
            *CEMCAP_CONTEXT,
            Context(
                17,
                "Overall, the cost of clinker is shown to increase with 49–92% when CO2 capture is retrofitted to "
                "the cement plant.",
            ),
        ),
        vintage=CEMCAP_VINTAGE,
        date_published=CEMCAP_PUBLISHED,
        value_range=(0, 1000),
    ),
)

PREMIUMS: tuple[Premium, ...] = (*ETP_PREMIUMS, *GHR_PREMIUMS, *EFUELS_PREMIUMS, *CEMCAP_PREMIUMS)


def transforms(paths: Paths) -> list[Transform]:
    return [_make(p) for p in PREMIUMS]
