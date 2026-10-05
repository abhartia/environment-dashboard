"""Andre, Boneva, Chopra & Falk (2024): actual and perceived support for climate action in 125 countries, from the
national averages the authors publish in their Supplementary Information.

Input: the Supplementary Information PDF (artifact supplementary-information, CC BY 4.0 with the article), Table S4
"National averages" on PDF pages 6 to 8. Each row is a country (and, last, "World") with five shares in percent:
- Willingness to contribute 1%: the share willing to give 1% of household income every month to fight global
  warming (actual support);
- Approval of pro-climate norms: the share saying people in their country should try to fight global warming;
- Demand for political action: the share saying their national government should do more;
- Beliefs about others' WTC: the average of respondents' estimates of the share of their compatriots willing to
  contribute (perceived support);
- Belief that a majority is WTC: the share who believe 50% or more of their compatriots are willing.
Table notes (verbatim, p. S7): national averages use "Gallup's sampling weights", each question's missing answers
are excluded, and "Global averages are derived as population-weighted averages of the national shares".

Reading. The text of each page (envdash.textmatch.pdf_pages_text) is split into lines; a data line is a name
followed by exactly five values, each a number with one decimal or the dash "–" the table prints where a question
was not asked or not answered. Every line between the column header and the notes must be a data line, the table
must hold 125 countries plus World with no name twice, and every country name maps to an entity through NAMES below
(the names exactly as the PDF text gives them, including "T ogo", "T ajikistan" and "T urkey", where the text layer
splits the capital T from the rest of the word). A dash is published as a null value with that reason.

Not used: the survey microdata on the IZA Data Service Center (registration and a non-commercial licence).
"""

from __future__ import annotations

import re
from pathlib import Path

from envdash import textmatch
from envdash.geo import resolve
from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, PublisherCheck, Result, Spec, Transform, Validation

SOURCE = "andre-2024"
SI = Input(SOURCE, "supplementary-information")
INDICATOR = "attitudes.andre-2024.climate-support"
PAGES = (6, 7, 8)
TITLE = "T able S4: National averages"
HEADER_END = "is WTC"
LAST_LINE = "World"
NOTES_START = "Notes: This table presents national averages"
PERIOD = "2021/2022"
DASH = "–"
N_COUNTRIES = 125

# (dimension id, label), in the table's column order.
MEASURES: tuple[tuple[str, str], ...] = (
    ("willing-to-contribute", "Willing to contribute 1% of income (actual support)"),
    ("approve-pro-climate-norms", "Approve of pro-climate social norms"),
    ("demand-political-action", "Want their government to do more (demand for political action)"),
    ("perceived-willing-others", "Believed share of compatriots willing to contribute (perceived support)"),
    ("believe-majority-willing", "Believe that a majority of compatriots are willing to contribute"),
)

VALUE = rf"(\d{{1,3}}\.\d|{DASH})"
ROW = re.compile(rf"^(?P<name>\S.*?) {VALUE} {VALUE} {VALUE} {VALUE} {VALUE}$")

# Country names as the PDF text gives them -> our entity code. Every name of Table S4 is listed: no name is matched
# by similarity, and a name not listed stops the transform.
NAMES: dict[str, str] = {
    "Afghanistan": "AFG",
    "Albania": "ALB",
    "Algeria": "DZA",
    "Argentina": "ARG",
    "Armenia": "ARM",
    "Australia": "AUS",
    "Austria": "AUT",
    "Bangladesh": "BGD",
    "Belgium": "BEL",
    "Benin": "BEN",
    "Bolivia": "BOL",
    "Bosnia Herzegovina": "BIH",
    "Botswana": "BWA",
    "Brazil": "BRA",
    "Bulgaria": "BGR",
    "Burkina Faso": "BFA",
    "Cambodia": "KHM",
    "Cameroon": "CMR",
    "Canada": "CAN",
    "Chile": "CHL",
    "China": "CHN",
    "Colombia": "COL",
    "Congo Brazzaville": "COG",
    "Costa Rica": "CRI",
    "Croatia": "HRV",
    "Cyprus": "CYP",
    "Czech Republic": "CZE",
    "Denmark": "DNK",
    "Dominican Republic": "DOM",
    "Ecuador": "ECU",
    "Egypt": "EGY",
    "El Salvador": "SLV",
    "Estonia": "EST",
    "Finland": "FIN",
    "France": "FRA",
    "Gabon": "GAB",
    "Georgia": "GEO",
    "Germany": "DEU",
    "Ghana": "GHA",
    "Greece": "GRC",
    "Guatemala": "GTM",
    "Guinea": "GIN",
    "Honduras": "HND",
    "Hong Kong": "HKG",
    "Hungary": "HUN",
    "Iceland": "ISL",
    "India": "IND",
    "Indonesia": "IDN",
    "Iran": "IRN",
    "Iraq": "IRQ",
    "Ireland": "IRL",
    "Israel": "ISR",
    "Italy": "ITA",
    "Ivory Coast": "CIV",
    "Jamaica": "JAM",
    "Japan": "JPN",
    "Jordan": "JOR",
    "Kazakhstan": "KAZ",
    "Kenya": "KEN",
    "Kosovo": "KOS",
    "Kyrgyzstan": "KGZ",
    "Laos": "LAO",
    "Latvia": "LVA",
    "Lebanon": "LBN",
    "Lithuania": "LTU",
    "Madagascar": "MDG",
    "Malawi": "MWI",
    "Malaysia": "MYS",
    "Mali": "MLI",
    "Malta": "MLT",
    "Mauritius": "MUS",
    "Mexico": "MEX",
    "Moldova": "MDA",
    "Mongolia": "MNG",
    "Morocco": "MAR",
    "Mozambique": "MOZ",
    "Myanmar": "MMR",
    "Namibia": "NAM",
    "Nepal": "NPL",
    "Netherlands": "NLD",
    "New Zealand": "NZL",
    "Nicaragua": "NIC",
    "Nigeria": "NGA",
    "North Macedonia": "MKD",
    "Norway": "NOR",
    "Pakistan": "PAK",
    "Panama": "PAN",
    "Paraguay": "PRY",
    "Peru": "PER",
    "Philippines": "PHL",
    "Poland": "POL",
    "Portugal": "PRT",
    "Romania": "ROU",
    "Russia": "RUS",
    "Saudi Arabia": "SAU",
    "Senegal": "SEN",
    "Serbia": "SRB",
    "Sierra Leone": "SLE",
    "Singapore": "SGP",
    "Slovakia": "SVK",
    "Slovenia": "SVN",
    "South Africa": "ZAF",
    "South Korea": "KOR",
    "Spain": "ESP",
    "Sri Lanka": "LKA",
    "Sweden": "SWE",
    "Switzerland": "CHE",
    "T aiwan": "TWN",
    "T ajikistan": "TJK",
    "T anzania": "TZA",
    "Thailand": "THA",
    "T ogo": "TGO",
    "T unisia": "TUN",
    "T urkey": "TUR",
    "Uganda": "UGA",
    "Ukraine": "UKR",
    "United Arab Emirates": "ARE",
    "United Kingdom": "GBR",
    "United States": "USA",
    "Uruguay": "URY",
    "Uzbekistan": "UZB",
    "Venezuela": "VEN",
    "Vietnam": "VNM",
    "Zambia": "ZMB",
    "Zimbabwe": "ZWE",
    "World": "WLD",
}

UNIT = Unit(code="percent", label="percent of people", short="%")
VINTAGE = "Nature Climate Change 14, 253–259 (2024), Supplementary Information"

# The article's abstract (PDF page 1) rounds the World row of Table S4 to whole percent.
_ABSTRACT = (
    "Notably, 69% of the global population expresses a willingness to contribute 1% of their personal income, 86% "
    "endorse pro-climate social norms and 89% demand intensified political action."
)
CHECKS = tuple(
    PublisherCheck(
        source_id=SOURCE,
        vintage=VINTAGE,
        entity="WLD",
        period=PERIOD,
        stated=stated,
        quote=_ABSTRACT,
        url="https://doi.org/10.1038/s41558-024-01925-3",
        dims=(("measure", measure),),
    )
    for measure, stated in (
        ("willing-to-contribute", "69"),
        ("approve-pro-climate-norms", "86"),
        ("demand-political-action", "89"),
    )
)


class AndreFormatError(ValueError):
    pass


def read_table(pdf: bytes) -> list[tuple[str, list[str]]]:
    """Table S4's rows in order: (name as printed, the five values as printed)."""
    pages = textmatch.pdf_pages_text(pdf)
    rows: list[tuple[str, list[str]]] = []
    for p in PAGES:
        if p > len(pages):
            raise AndreFormatError(f"the PDF has {len(pages)} pages, not {p}")
        lines = [ln.strip() for ln in pages[p - 1].splitlines()]
        if not lines or lines[0] != TITLE:
            raise AndreFormatError(f"page {p} does not start with {TITLE!r}: {lines[:1]}")
        if HEADER_END not in lines:
            raise AndreFormatError(f"page {p}: column header ending {HEADER_END!r} not found")
        body = lines[lines.index(HEADER_END) + 1 :]
        for ln in body:
            if ln.startswith(NOTES_START) or re.fullmatch(r"S\d+", ln):
                break
            m = ROW.match(ln)
            if m is None:
                raise AndreFormatError(f"page {p}: {ln!r} is not a row of five values")
            rows.append((m["name"], [m[i] for i in range(2, 7)]))
    names = [n for n, _ in rows]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes or names[-1:] != [LAST_LINE] or len(names) != N_COUNTRIES + 1:
        raise AndreFormatError(f"{len(names)} rows (repeated {dupes}, last {names[-1:]}); expected 125 and World")
    unknown = [n for n in names if n not in NAMES]
    if unknown:
        raise AndreFormatError(f"names not in NAMES: {unknown}")
    return rows


def observations(rows: list[tuple[str, list[str]]]) -> list[Observation]:
    obs: list[Observation] = []
    for name, values in rows:
        entity = resolve(NAMES[name], "iso3")
        for (mid, _), printed in zip(MEASURES, values, strict=True):
            if printed == DASH:
                obs.append(
                    Observation(
                        entity=entity,
                        period=PERIOD,
                        value=None,
                        missing_reason="Table S4 prints a dash for this country and question.",
                        dims={"measure": mid},
                    )
                )
            else:
                obs.append(Observation(entity=entity, period=PERIOD, value=float(printed), dims={"measure": mid}))
    return obs


def _run(files: dict[str, InputFile]) -> Result:
    f = files[SI.key]
    rows = read_table(f.path.read_bytes())
    dashes = sum(v == DASH for _, vs in rows for v in vs)
    return Result(
        observations=observations(rows),
        vintage=VINTAGE,
        date_published="2024-02-09",
        steps=[
            f"Extracted the text of PDF pages {PAGES[0]}–{PAGES[-1]} of the Supplementary Information (sha256 "
            f"{f.snapshot.sha256[:12]}…), Table S4 'National averages', and read every row between the column "
            f"header and the notes: {len(rows) - 1} countries and World, five values each, as printed (percent, one "
            "decimal).",
            "Mapped each country name, exactly as printed, to its ISO 3166-1 code through a fixed table; World is the "
            "authors' population-weighted average of the national shares.",
            f"Published the {dashes} dashes the table prints as missing values.",
        ],
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id=INDICATOR,
                title="Actual and perceived support for climate action (Andre et al. 2024)",
                description="From a survey of nearly 130,000 people in 125 countries (Gallup World Poll 2021–2022): "
                "the share willing to give 1% of their household income every month to fight global warming, the "
                "share who approve of pro-climate norms, the share who want their government to do more, and what "
                "people believe about their compatriots: the average believed share willing to contribute and the "
                "share who think a majority is willing. In almost every country, people underestimate how many of "
                "their compatriots are willing.",
                kind="series",
                unit=UNIT,
                display=Display(decimals=1),
                scope=Scope(
                    geography="125 countries; World is the authors' population-weighted average of national shares",
                    basis="Nationally representative samples weighted with Gallup's sampling weights; missing "
                    "answers to each question excluded. Surveyed between 2021 and 2022, dates varying by country.",
                ),
                geo_coverage="mixed",
                headline_entity="WLD",
                dimensions=(
                    Dimension(
                        id="measure",
                        label="Question",
                        values=[DimensionValue(id=i, label=label) for i, label in MEASURES],
                    ),
                ),
                headline_dims=(("measure", "willing-to-contribute"),),
            ),
            inputs=(SI,),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=5 * (N_COUNTRIES + 1), value_range=(0.0, 100.0)),
            checks=CHECKS,
        )
    ]
