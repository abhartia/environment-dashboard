"""Naturvårdsverket: the consumption-based greenhouse gas footprint of an average person in Sweden, 2008-2023, in tonnes
of carbon dioxide equivalent per person per year, split by consumption area as the producer publishes it.

Input: the statistics page "Konsumtionsbaserade växthusgasutsläpp per person och år" (artifact per-person-page,
HTML). There is no data file: the series lives in the page model, the JSON inside
<script id="__model_data" type="application/json">. Its content.highChartsOptions is itself a JSON string (the chart's
Highcharts options), whose data.csv holds the table the chart draws: a header line
'"null";"Transporter ";"Livsmedel ";"Boende ";"Övrigt ";"Offentlig konsumtion ";"Investeringar ";"Totalt "' and one
line per year, values separated by ';' with a decimal point (for example '2023;1.37;1.35;1;0.98;0.83;2.09;7.62').

Checks on every build, so that a change to the page stops the transform rather than being misread: exactly one page
model; the page heading, the responsible authority (Statistikmyndigheten SCB), the y-axis title ('Ton
koldioxidekvivalenter per person') and the chart's seven series names are the ones above; the CSV header is exactly
the seven columns above; every row is a year followed by seven numbers; the years run without a gap; and in every year
the six parts add up to Totalt within 0.01 t; and the page's tab 'Koldioxidekvivalenter' still holds the conversion
table described below. The parts are rounded by the producer to two decimals, so they differ from Totalt by 0.01 t in
some years (2009, 2010, 2020, 2021 and 2022 in the page reviewed 2025-10-28); the transform names those years in a
processing step. Nothing is computed: the values are published as printed.

The six parts, from the page: the four household consumption areas (Transporter, Livsmedel, Boende and Övrigt, which
"består av rekreation och kultur, kläder och skor, hälso- och sjukvård, post- och telekommunikationer med mera"), then
Offentlig konsumtion (goods and services bought by schools, hospitals and agencies) and Investeringar ("byggnader,
maskiner, datorer, värdeföremål och lagerinvesteringar", and elsewhere on the page "byggnader, maskiner, bostäder och
värdeföremål": buildings including new homes, machinery, computers, valuables and changes in inventories). The last
two are not personal choices. The page does not say whether meals eaten out are under Livsmedel (food products) or
Övrigt, so the food label does not claim to cover all food. The per-person split is Naturvårdsverket's own
processing of SCB's official statistics (the verifier could not rebuild 'Övrigt' from SCB's COICOP tables), so
Naturvårdsverket is credited as the publisher of these values and SCB as the responsible authority.

Scope, from the page: emissions from goods and services used in Sweden wherever they happen, by an environmentally
extended input-output model (SCB's environmental accounts). Household transport does not capture the full effect of
international flights: emissions are based on jet fuel bought in Sweden for flights leaving the country, stopovers are
missed and the high-altitude effect is not counted. Global warming potentials: the page's tab 'Koldioxidekvivalenter'
shows a general conversion table ('Omräkningstabell': CO2 1, CH4 25, N2O 298, the IPCC Fourth Assessment Report (AR4)
100-year values, linked to that report and sourced to Sweden's 2017 reporting to the UNFCCC), but does not say that
this series uses it. So the scope records no GWP and says why; the transform checks the table is still there.

Vintage: the years covered and the page's own review date (content.lastReviewed, shown as 'Granskad').
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from envdash import textmatch
from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "naturvardsverket-consumption-footprint"
PAGE = Input(SOURCE, "per-person-page")
ENTITY = "SWE"

MODEL = re.compile(r'<script id="__model_data" type="application/json">(.*?)</script>', re.S)
HEADING = "Konsumtionsbaserade växthusgasutsläpp per person och år"
RESPONSIBLE = "Statistikmyndigheten SCB"
Y_AXIS = "Ton koldioxidekvivalenter per person"
TOTAL = "Totalt"
# (dimension value id, producer's Swedish column name, label). The order is the page's.
AREAS: tuple[tuple[str, str, str], ...] = (
    ("transport", "Transporter", "Households: transport (Transporter)"),
    ("food", "Livsmedel", "Households: food products (Livsmedel)"),
    ("housing", "Boende", "Households: housing (Boende)"),
    (
        "other-household",
        "Övrigt",
        "Households: other goods and services, such as recreation and culture, clothing and shoes, health, post and "
        "telecommunications (Övrigt)",
    ),
    (
        "public-consumption",
        "Offentlig konsumtion",
        "Public consumption: schools, hospitals, agencies (Offentlig konsumtion)",
    ),
    (
        "investment",
        "Investeringar",
        "Investment: buildings including new homes, machinery, computers, valuables and changes in inventories "
        "(Investeringar)",
    ),
)
COLUMNS = ("null", *(sv for _, sv, _ in AREAS), TOTAL)
PART_TOLERANCE = Decimal("0.01")
GWP_TAB = "Koldioxidekvivalenter"
GWP_TABLE = ("Omräkningstabell", "CO2 (koldioxid) 1", "CH4 (metan) 25", "N2O (dikväveoxid) 298")
"""The page's general conversion table, as its visible text reads (subscripts as plain digits; textmatch ignores
spaces), in the order it appears; these are the IPCC AR4 100-year values."""
GWP_AR4_LINK = "Koldioxidekvivalenter för ytterligare växthusgaser i IPCC:s fjärde utvärderingsrapport"
GWP_WORDS = (
    "Global warming potentials: the page shows the IPCC Fourth Assessment Report (AR4) values (methane 25, nitrous "
    "oxide 298) in a general conversion table, without saying they apply to this series."
)

T_CO2E_PERSON_YR = Unit(
    code="tCO2e/person/yr",
    label="tonnes of carbon dioxide equivalent per person per year",
    short="t CO₂e/person/yr",
)

SCOPE = Scope(
    geography="Sweden: the average person in Sweden's population",
    lulucf=None,
    bunkers=None,
    basis="Consumption-based footprint: greenhouse gas emissions in Sweden and abroad from producing the goods and "
    "services used in Sweden (by households, the public sector and investment), divided by the population; emissions "
    "from producing Sweden's exports are not counted. International flights are undercounted: only jet fuel bought in "
    "Sweden is counted, stopovers are missed and the high-altitude effect is not included. " + GWP_WORDS,
)


class NaturvardsverketFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Chart:
    csv: str
    last_reviewed: str
    gwp_step: str
    """The processing step stating what the page says about global warming potentials (gwp_table)."""


def page_model(raw: bytes) -> dict:
    """The page model: the JSON of the page's one <script id="__model_data">."""
    found = MODEL.findall(raw.decode("utf-8"))
    if len(found) != 1:
        raise NaturvardsverketFormatError(f"expected one __model_data script, found {len(found)}")
    model = json.loads(found[0])
    if not isinstance(model, dict) or not isinstance(model.get("content"), dict):
        raise NaturvardsverketFormatError("the page model has no content object")
    return model


def chart(model: dict) -> Chart:
    """The chart's CSV and the page's review date, after checking that the page is the one described above."""
    c = model["content"]
    for key, want in (("heading", HEADING), ("responsibleAuthority", RESPONSIBLE)):
        if c.get(key) != want:
            raise NaturvardsverketFormatError(f"content.{key} is {c.get(key)!r}, not {want!r}")
    reviewed = c.get("lastReviewed")
    if not isinstance(reviewed, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", reviewed):
        raise NaturvardsverketFormatError(f"content.lastReviewed {reviewed!r} is not a date")
    if not isinstance(c.get("highChartsOptions"), str):
        raise NaturvardsverketFormatError("content.highChartsOptions is not a JSON string")
    opts = json.loads(c["highChartsOptions"])
    y_axis = ((opts.get("yAxis") or {}).get("title") or {}).get("text")
    if y_axis != Y_AXIS:
        raise NaturvardsverketFormatError(f"y-axis title {y_axis!r}, not {Y_AXIS!r}")
    names = tuple(s.get("name") for s in opts.get("series", []))
    if names != COLUMNS[1:]:
        raise NaturvardsverketFormatError(f"chart series {names} != {COLUMNS[1:]}")
    csv = (opts.get("data") or {}).get("csv")
    if not isinstance(csv, str):
        raise NaturvardsverketFormatError("the chart options have no data.csv string")
    return Chart(csv=csv, last_reviewed=reviewed, gwp_step=gwp_table(c))


def gwp_table(content: dict) -> str:
    """The page's tab GWP_TAB must still hold the conversion table GWP_TABLE and its link to the IPCC's fourth
    assessment, which the scope and description describe; returns the step that says so."""
    tabs = [t for t in content.get("tabItems") or [] if isinstance(t, dict) and t.get("heading") == GWP_TAB]
    if len(tabs) != 1 or not isinstance(tabs[0].get("text"), str):
        raise NaturvardsverketFormatError(f"expected one tab {GWP_TAB!r} with text, found {len(tabs)}")
    text = textmatch.html_to_text(tabs[0]["text"])
    key = textmatch.match_key(text)
    at = 0
    for cell in GWP_TABLE:
        found = key.find(textmatch.match_key(cell), at)
        if found < 0:
            raise NaturvardsverketFormatError(f"tab {GWP_TAB!r} no longer shows {cell!r} after the cells before it")
        at = found
    if not textmatch.contains(text, GWP_AR4_LINK):
        raise NaturvardsverketFormatError(f"tab {GWP_TAB!r} no longer links {GWP_AR4_LINK!r}")
    return (
        f"Checked the page's tab '{GWP_TAB}': its general conversion table ('Omräkningstabell') gives CO2 1, CH4 25 "
        "and N2O 298, the IPCC Fourth Assessment Report (AR4) 100-year values, and links that report "
        f"('{GWP_AR4_LINK}'), but the page does not say that this series uses them. So no global warming potential "
        "is recorded in the scope; the basis says what the page shows."
    )


def _number(text: str, where: str) -> Decimal:
    if not re.fullmatch(r"\d+(\.\d+)?", text):
        raise NaturvardsverketFormatError(f"{where}: {text!r} is not a number")
    try:
        return Decimal(text)
    except InvalidOperation:
        raise NaturvardsverketFormatError(f"{where}: {text!r} is not a number") from None


def read_csv(text: str) -> dict[int, dict[str, Decimal]]:
    """{year: {Swedish column name: value}} from the chart's CSV, values exactly as printed."""
    lines = text.split("\n")
    header = tuple(h.strip('"').strip() for h in lines[0].split(";"))
    if header != COLUMNS:
        raise NaturvardsverketFormatError(f"CSV header {header} != {COLUMNS}")
    rows: dict[int, dict[str, Decimal]] = {}
    for n, line in enumerate(lines[1:], start=2):
        cells = line.split(";")
        if len(cells) != len(COLUMNS) or not re.fullmatch(r"\d{4}", cells[0]):
            raise NaturvardsverketFormatError(f"CSV line {n} {line!r} is not a year and {len(COLUMNS) - 1} values")
        year = int(cells[0])
        if year in rows:
            raise NaturvardsverketFormatError(f"CSV line {n}: year {year} twice")
        rows[year] = {col: _number(v, f"{year} {col}") for col, v in zip(COLUMNS[1:], cells[1:], strict=True)}
    if not rows:
        raise NaturvardsverketFormatError("the CSV has no rows")
    years = sorted(rows)
    if years != list(range(years[0], years[-1] + 1)) or list(rows) != years:
        raise NaturvardsverketFormatError(f"years {list(rows)} are not consecutive and in order")
    return rows


def rounding_years(rows: dict[int, dict[str, Decimal]]) -> dict[int, Decimal]:
    """{year: parts minus Totalt} for the years whose parts do not add exactly to Totalt. More than 0.01 t is refused:
    rounding to two decimals cannot explain it."""
    out: dict[int, Decimal] = {}
    for year, r in rows.items():
        diff = sum((r[sv] for _, sv, _ in AREAS), Decimal(0)) - r[TOTAL]
        if abs(diff) > PART_TOLERANCE:
            raise NaturvardsverketFormatError(f"{year}: the six parts differ from Totalt by {diff} t")
        if diff:
            out[year] = diff
    return out


def _read(f: InputFile) -> tuple[Chart, dict[int, dict[str, Decimal]], dict[int, Decimal]]:
    c = chart(page_model(f.path.read_bytes()))
    rows = read_csv(c.csv)
    return c, rows, rounding_years(rows)


def _vintage(c: Chart, rows: dict) -> str:
    return f"{min(rows)}-{max(rows)} series, page reviewed {c.last_reviewed}"


def _read_step(f: InputFile, c: Chart, rows: dict) -> str:
    return (
        f"Read the statistics page 'Konsumtionsbaserade växthusgasutsläpp per person och år' (sha256 "
        f"{f.snapshot.sha256[:12]}…, retrieved {f.snapshot.date_accessed.isoformat()}, reviewed by the producer on "
        f"{c.last_reviewed}). The series is the CSV inside the page's chart options (page model <script "
        'id="__model_data">, content.highChartsOptions, data.csv): '
        f"{len(rows)} years, {min(rows)}–{max(rows)}, in tonnes of carbon dioxide equivalent per person ('Ton "
        "koldioxidekvivalenter per person'). Checked the page heading, the responsible authority (SCB), the axis "
        "title, the series names and the CSV header before reading any value."
    )


def _run_by_area(files: dict[str, InputFile]) -> Result:
    f = files[PAGE.key]
    c, rows, rounding = _read(f)
    obs = [
        Observation(entity=ENTITY, period=f"{year:04d}", value=float(r[sv]), dims={"area": aid})
        for aid, sv, _ in AREAS
        for year, r in rows.items()
    ]
    differ = ", ".join(f"{y} ({d:+} t)" for y, d in sorted(rounding.items())) or "none"
    return Result(
        observations=obs,
        vintage=_vintage(c, rows),
        date_published=c.last_reviewed,
        steps=[
            _read_step(f, c, rows),
            "Selected the six parts as published, each with its Swedish column name kept in its label: "
            + "; ".join(f"{sv} = {aid}" for aid, sv, _ in AREAS)
            + ". The first four are households' consumption; public consumption and investment are not household "
            "spending.",
            "Checked that in every year the six parts add up to the published Totalt within 0.01 t (the producer "
            f"rounds each value to two decimals). Years where they differ by 0.01 t: {differ}. No value was changed.",
            c.gwp_step,
        ],
    )


def _run_total(files: dict[str, InputFile]) -> Result:
    f = files[PAGE.key]
    c, rows, _ = _read(f)
    obs = [Observation(entity=ENTITY, period=f"{year:04d}", value=float(r[TOTAL])) for year, r in rows.items()]
    return Result(
        observations=obs,
        vintage=_vintage(c, rows),
        date_published=c.last_reviewed,
        steps=[
            _read_step(f, c, rows),
            "Selected the column Totalt as published (the producer's own total, not a sum of ours). No value was "
            "changed.",
            c.gwp_step,
        ],
    )


DESCRIPTION = (
    "The consumption-based greenhouse gas footprint of an average person in Sweden: emissions in Sweden and abroad "
    "from producing everything used in Sweden, divided by the population, in tonnes of carbon dioxide equivalent per "
    "person per year, as published by Naturvårdsverket from Statistics Sweden's official statistics. "
)
CAVEATS = (
    " International flights are undercounted: only jet fuel bought in Sweden is counted, without stopovers or the "
    "high-altitude effect. The page shows the IPCC Fourth Assessment Report (AR4) global warming potentials (methane "
    "25, nitrous oxide 298) in a general conversion table, without saying they apply to this series. Sweden only; it "
    "is not a world average or a measure of any one person."
)


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="footprint.naturvardsverket.per-person-by-area",
                title="Greenhouse gas footprint of an average person in Sweden, by consumption area (Naturvårdsverket)",
                description=DESCRIPTION
                + "Split into the six parts the producer publishes. Four are household consumption (transport, food "
                "products, housing, and other goods and services); the page does not say whether meals eaten out "
                "count under food products or under other goods and services. The other two, public consumption "
                "(schools, hospitals, agencies) and investment (buildings including new homes, machinery, computers, "
                "valuables and changes in inventories), are shared out per person but are not personal choices; "
                "buying a new home counts under investment, not housing. The parts are rounded by the producer and "
                "may differ from the published total by 0.01 t." + CAVEATS,
                kind="series",
                unit=T_CO2E_PERSON_YR,
                display=Display(decimals=2),
                scope=SCOPE,
                geo_coverage="country",
                headline_entity=ENTITY,
                dimensions=(
                    Dimension(
                        id="area",
                        label="Consumption area",
                        values=[DimensionValue(id=aid, label=label) for aid, _, label in AREAS],
                    ),
                ),
                headline_dims=(("area", "food"),),
            ),
            inputs=(PAGE,),
            run=_run_by_area,
            module_file=Path(__file__),
            validation=Validation(min_rows=6 * 16, value_range=(0.0, 10.0)),
        ),
        Transform(
            spec=Spec(
                id="footprint.naturvardsverket.per-person-total",
                title="Greenhouse gas footprint of an average person in Sweden (Naturvårdsverket)",
                description=DESCRIPTION
                + "This is the producer's published total (Totalt). It includes household consumption and also public "
                "consumption and investment, which are shared out per person but are not personal choices." + CAVEATS,
                kind="series",
                unit=T_CO2E_PERSON_YR,
                display=Display(decimals=2),
                scope=SCOPE,
                geo_coverage="country",
                headline_entity=ENTITY,
            ),
            inputs=(PAGE,),
            run=_run_total,
            module_file=Path(__file__),
            validation=Validation(min_rows=16, value_range=(0.0, 30.0)),
        ),
    ]
