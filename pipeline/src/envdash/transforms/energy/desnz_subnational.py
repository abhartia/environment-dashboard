"""DESNZ subnational electricity consumption (Great Britain): the average household's electricity and London's total,
as published and as average power.

Input: the workbook "Subnational electricity consumption statistics, 2005 to 2024" (desnz-subnational-electricity/
workbook). Only the latest year's sheet is read (YEAR); its title, its 24 column headings and the code, name and
'All local authorities' of each row used must be exactly as expected:
- K03000001 'Great Britain (inc unallocated)': column X, 'Mean domestic consumption (kWh per household)';
- E12000007 'London': column M, 'Total consumption (GWh): All meters'.
The workbook is read from its XML parts (workbook, relationships, shared strings, the cover sheet and that year's
sheet), so each value is the decimal text Excel stored, published as it is; nothing is rounded or recalculated.

Electricity years. The cover sheet says half-hourly meters cover the calendar year and non-half-hourly meters
(almost all domestic meters) February to January ("the 2024 electricity year was February 2024 to January 2025"),
and that domestic consumption is based on non-half-hourly meters; those sentences are required. Average power divides
each value by the hours of the span it covers, counted from those dates (envdash.power): the household mean by the
February-to-January span; London's total, which mixes both kinds of meter, by the common length of the two spans, and
the build stops if the two spans ever differ in length (a February-to-January year contains the 29 February of the
year it starts in, so for every year they are equal: 8,784 hours for 2024).
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from envdash import power, textmatch
from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "desnz-subnational-electricity"
WORKBOOK = Input(SOURCE, "workbook")
YEAR = 2024
VINTAGE = "2005 to 2024 (published 18 December 2025)"
PUBLISHED = "2025-12-18"

TITLE = f"Subnational electricity consumption, Great Britain, {YEAR}"
HEADINGS = [
    "Code",
    "Country or region",
    "Local authority",
    "Number of meters\n(thousands):\nDomestic Standard",
    "Number of meters\n(thousands):\nDomestic E7",
    "Number of meters\n(thousands):\nAll Domestic",
    "Number of meters\n(thousands):\nAll Non-Domestic",
    "Number of meters\n(thousands):\nAll meters",
    "Total consumption\n(GWh):\nDomestic Standard",
    "Total consumption\n(GWh):\nDomestic E7",
    "Total consumption\n(GWh):\nAll Domestic",
    "Total consumption\n(GWh):\nAll Non-Domestic",
    "Total consumption\n(GWh):\nAll meters",
    "Mean consumption\n(kWh per meter):\nDomestic Standard",
    "Mean consumption\n(kWh per meter):\nDomestic E7",
    "Mean consumption\n(kWh per meter):\nAll Domestic",
    "Mean consumption\n(kWh per meter):\nAll Non-Domestic",
    "Mean consumption\n(kWh per meter):\nAll meters",
    "Median consumption\n(kWh per meter):\nDomestic Standard",
    "Median consumption\n(kWh per meter):\nDomestic E7",
    "Median consumption\n(kWh per meter):\nAll Domestic",
    "Median consumption\n(kWh per meter):\nAll Non-Domestic",
    "Median consumption\n(kWh per meter):\nAll meters",
    "Mean domestic\nconsumption\n(kWh per household)",
]
COLUMNS = [chr(ord("A") + i) for i in range(len(HEADINGS))]
TOTAL_ALL = "Total consumption\n(GWh):\nAll meters"
MEAN_HOUSEHOLD = "Mean domestic\nconsumption\n(kWh per household)"
ALL_LAS = "All local authorities"
GB = ("K03000001", "Great Britain (inc unallocated)")
LONDON = ("E12000007", "London")
COVER = "Cover sheet"

COVER_REQUIRED = (
    "Half-hourly data (generally higher-consuming non-domestic meters) covers consumption over the calendar year "
    "(January to December).",
    "For non-half hourly data (almost all domestic and the vast majority of non-domestic meters) the electricity years "
    f"cover the months February to January (for example the 2024 electricity year was February {YEAR} to January "
    f"{YEAR + 1}).",
    "Domestic consumption is based on Non-Half Hourly (NHH) meters with profiles 1 and 2",
    "Publication date: 18 December 2025",
    "The figures for total electricity consumption are presented in gigawatt hours (GWh).",
)
HH_SPAN = (date(YEAR, 1, 1), date(YEAR + 1, 1, 1))
NHH_SPAN = (date(YEAR, 2, 1), date(YEAR + 1, 2, 1))

# The workbook is read from its XML parts (an xlsx is a zip), so a value is the exact decimal text Excel stored.
MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
DOC_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
WORKBOOK_XML = "xl/workbook.xml"
WORKBOOK_RELS = "xl/_rels/workbook.xml.rels"
SHARED_STRINGS = "xl/sharedStrings.xml"
CELL = re.compile(r"^([A-Z]+)([0-9]+)$")
NUMBER = re.compile(r"^-?[0-9]+(\.[0-9]+)?([Ee][+-]?[0-9]+)?$")


class DesnzFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Values:
    gb_household_kwh: Decimal
    london_gwh: Decimal


def sheet_members(workbook_xml: bytes, rels_xml: bytes) -> dict[str, str]:
    """Sheet name -> its zip member, from xl/workbook.xml and its relationships."""
    targets = {r.get("Id"): r.get("Target") or "" for r in ET.fromstring(rels_xml).iter(f"{PKG_REL}Relationship")}
    out: dict[str, str] = {}
    for sheet in ET.fromstring(workbook_xml).iter(f"{MAIN}sheet"):
        target = targets[sheet.get(f"{DOC_REL}id")]
        out[sheet.get("name") or ""] = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
    return out


def shared_strings(xml: bytes) -> list[str]:
    """Each shared string's text: its <t>, or the <t> of each rich-text run, in order (phonetic runs left out)."""
    out = []
    for si in ET.fromstring(xml).iter(f"{MAIN}si"):
        parts = []
        for child in si:
            if child.tag == f"{MAIN}t":
                parts.append(child.text or "")
            elif child.tag == f"{MAIN}r":
                t = child.find(f"{MAIN}t")
                parts.append(t.text or "" if t is not None else "")
        out.append("".join(parts))
    return out


@dataclass(frozen=True)
class Cell:
    kind: str
    """'text' or 'number'."""
    text: str


def sheet_cells(xml: bytes, strings: list[str]) -> dict[tuple[int, str], Cell]:
    """(row number, column letters) -> the cell's text: a shared or inline string, a formula's string result, or a
    number exactly as stored. Empty cells are absent; error and boolean cells stop the read."""
    out: dict[tuple[int, str], Cell] = {}
    for c in ET.fromstring(xml).iter(f"{MAIN}c"):
        m = CELL.match(c.get("r") or "")
        if not m:
            raise DesnzFormatError(f"cell reference {c.get('r')!r}")
        key = (int(m.group(2)), m.group(1))
        kind, v = c.get("t", "n"), c.find(f"{MAIN}v")
        if kind == "s" and v is not None and v.text is not None:
            out[key] = Cell("text", strings[int(v.text)])
        elif kind == "inlineStr":
            out[key] = Cell("text", "".join(t.text or "" for t in c.iter(f"{MAIN}t")))
        elif kind == "str" and v is not None:
            out[key] = Cell("text", v.text or "")
        elif kind == "n" and v is not None and v.text is not None:
            if not NUMBER.fullmatch(v.text):
                raise DesnzFormatError(f"cell {c.get('r')} holds {v.text!r}, not a number")
            out[key] = Cell("number", v.text)
        elif v is not None:
            raise DesnzFormatError(f"cell {c.get('r')} has type {kind!r}")
    return out


def _text(cells: dict[tuple[int, str], Cell], row: int, col: str) -> str | None:
    c = cells.get((row, col))
    return c.text if c is not None and c.kind == "text" else None


def values_from(members: dict[str, bytes]) -> Values:
    """The two values, from the workbook's XML parts (zip member path -> bytes)."""
    sheets = sheet_members(members[WORKBOOK_XML], members[WORKBOOK_RELS])
    strings = shared_strings(members[SHARED_STRINGS])
    if COVER not in sheets or str(YEAR) not in sheets:
        raise DesnzFormatError(f"the workbook has no sheet {COVER!r} or {str(YEAR)!r}: {sorted(sheets)}")
    cover_cells = sheet_cells(members[sheets[COVER]], strings)
    cover = " ".join(c.text for _, c in sorted(cover_cells.items()) if c.kind == "text")
    for sentence in COVER_REQUIRED:
        if not textmatch.contains(cover, sentence):
            raise DesnzFormatError(f"the cover sheet no longer says {sentence!r}")
    cells = sheet_cells(members[sheets[str(YEAR)]], strings)
    if _text(cells, 1, "A") != TITLE:
        raise DesnzFormatError(f"sheet {YEAR} is titled {_text(cells, 1, 'A')!r}, not {TITLE!r}")
    headings = [_text(cells, 5, col) for col in COLUMNS]
    if headings != HEADINGS or (5, chr(ord("A") + len(HEADINGS))) in cells:
        raise DesnzFormatError(f"sheet {YEAR} row 5 headings are {headings}")
    col = dict(zip(HEADINGS, COLUMNS, strict=True))

    def number(code: str, name: str, heading: str) -> Decimal:
        rows = [r for (r, c), cell in cells.items() if c == "A" and r > 5 and cell.text == code]
        if len(rows) != 1 or _text(cells, rows[0], "B") != name or _text(cells, rows[0], "C") != ALL_LAS:
            raise DesnzFormatError(f"expected one row {code} {name!r} {ALL_LAS!r} on sheet {YEAR}, found rows {rows}")
        cell = cells.get((rows[0], col[heading]))
        if cell is None or cell.kind != "number":
            raise DesnzFormatError(f"{code} {heading!r} is {cell!r}, not a number")
        return Decimal(cell.text)

    return Values(
        gb_household_kwh=number(*GB, MEAN_HOUSEHOLD),
        london_gwh=number(*LONDON, TOTAL_ALL),
    )


def needed_members(raw: bytes) -> dict[str, bytes]:
    """The parts values_from reads: the workbook, its relationships, the shared strings and the two sheets."""
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        parts = {m: z.read(m) for m in (WORKBOOK_XML, WORKBOOK_RELS, SHARED_STRINGS)}
        sheets = sheet_members(parts[WORKBOOK_XML], parts[WORKBOOK_RELS])
        for name in (COVER, str(YEAR)):
            if name not in sheets:
                raise DesnzFormatError(f"the workbook has no sheet {name!r}")
            parts[sheets[name]] = z.read(sheets[name])
    return parts


def read(raw: bytes) -> Values:
    return values_from(needed_members(raw))


@lru_cache(maxsize=1)
def _read_path(path: Path) -> Values:
    # Snapshot paths are content-addressed (pipeline/.snapshots/<sha256>), so the four indicators read it once.
    return read(path.read_bytes())


def household_hours() -> int:
    return power.hours_between(*NHH_SPAN)


def all_meter_hours() -> int:
    hh, nhh = power.hours_between(*HH_SPAN), power.hours_between(*NHH_SPAN)
    if hh != nhh:
        raise DesnzFormatError(
            f"the calendar year ({hh} h) and the February-to-January year ({nhh} h) differ in length: a total that "
            "mixes both kinds of meter has no single span to divide by"
        )
    return hh


def _read_step(files: dict[str, InputFile], what: str) -> str:
    f = files[WORKBOOK.key]
    return (
        f"Read sheet '{YEAR}' of the workbook (sha256 {f.snapshot.sha256[:12]}…), after checking its title and its "
        f"24 column headings, and took {what}. Checked the cover sheet's statements on electricity years, units and "
        "the publication date."
    )


GB_WHAT = (
    "row K03000001 'Great Britain (inc unallocated)', 'All local authorities', column 'Mean domestic consumption "
    "(kWh per household)'"
)
LONDON_WHAT = "row E12000007 'London', 'All local authorities', column 'Total consumption (GWh): All meters'"
YEAR_NOTE = (
    f"DESNZ's {YEAR} electricity year: February {YEAR} to January {YEAR + 1} for non-half-hourly meters (almost all "
    "homes), January to December for half-hourly meters."
)


def _run_gb_energy(files: dict[str, InputFile]) -> Result:
    v = _read_path(files[WORKBOOK.key].path)
    return Result(
        observations=[Observation(entity="GBR_GB", period=str(YEAR), value=float(v.gb_household_kwh), note=YEAR_NOTE)],
        vintage=VINTAGE,
        date_published=PUBLISHED,
        steps=[_read_step(files, GB_WHAT), "Published the mean as the workbook holds it."],
    )


def _run_gb_power(files: dict[str, InputFile]) -> Result:
    v = _read_path(files[WORKBOOK.key].path)
    hours = household_hours()
    return Result(
        observations=[
            Observation(
                entity="GBR_GB",
                period=str(YEAR),
                value=float(power.average_power(v.gb_household_kwh, hours)),
                note=YEAR_NOTE,
            )
        ],
        vintage=VINTAGE,
        date_published=PUBLISHED,
        steps=[
            _read_step(files, GB_WHAT),
            "Unit conversion to average power: divided the household's annual kilowatt-hours by the "
            f"{power.hours_words(hours)} of the span domestic meters cover, 1 February {YEAR} to 31 January "
            f"{YEAR + 1} (the cover sheet's electricity year for non-half-hourly meters, on which domestic "
            "consumption is based), giving kilowatts (kWh / h = kW), in exact decimal arithmetic. The result is the "
            "constant power that would deliver the same electricity over the year, not the home's peak demand.",
        ],
        changes=f"annual electricity per household divided by the {hours:,} hours of DESNZ's {YEAR} electricity "
        "year to give average power in kilowatts.",
    )


def _run_london_energy(files: dict[str, InputFile]) -> Result:
    v = _read_path(files[WORKBOOK.key].path)
    return Result(
        observations=[Observation(entity="GBR_LONDON", period=str(YEAR), value=float(v.london_gwh), note=YEAR_NOTE)],
        vintage=VINTAGE,
        date_published=PUBLISHED,
        steps=[_read_step(files, LONDON_WHAT), "Published the total as the workbook holds it."],
    )


def _run_london_power(files: dict[str, InputFile]) -> Result:
    v = _read_path(files[WORKBOOK.key].path)
    hours = all_meter_hours()
    return Result(
        observations=[
            Observation(
                entity="GBR_LONDON",
                period=str(YEAR),
                value=float(power.average_power(v.london_gwh, hours)),
                note=YEAR_NOTE,
            )
        ],
        vintage=VINTAGE,
        date_published=PUBLISHED,
        steps=[
            _read_step(files, LONDON_WHAT),
            "Unit conversion to average power: divided London's annual gigawatt-hours by "
            f"{power.hours_words(hours)}, giving gigawatts (GWh / h = GW), in exact decimal arithmetic. The total "
            f"mixes half-hourly meters (1 January to 31 December {YEAR}) and the others (1 February {YEAR} to 31 "
            f"January {YEAR + 1}); both spans have {hours:,} hours, which was checked. The result is the constant "
            "power that would deliver the same electricity over the year, not the city's peak demand.",
        ],
        changes=f"annual electricity divided by the {hours:,} hours of DESNZ's {YEAR} electricity year to give "
        "average power in gigawatts.",
    )


HOUSEHOLD_BASIS = (
    "Mean metered domestic electricity consumption per household: domestic consumption (standard and Economy 7 "
    "meters, including consumption DESNZ could not allocate to a local authority) divided by DESNZ's count of "
    "households (ONS, Welsh Government and National Records of Scotland estimates; Wales 2024 projected by DESNZ). "
    "Northern Ireland is not included."
)
LONDON_BASIS = (
    "Metered electricity consumption of all domestic and non-domestic meters in the 33 London local authorities "
    "(the London region of England), as allocated by postcode."
)


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    inputs = (WORKBOOK,)
    key = (Path(power.__file__),)
    gb_geo = "Great Britain (England, Scotland and Wales)"
    london_geo = "London (the London region of England)"
    return [
        Transform(
            spec=Spec(
                id="electricity-use.desnz.gb-household",
                title="Electricity used by the average household in Great Britain in a year",
                description="Metered electricity used at home in a year by the average household in Great Britain, "
                "in kilowatt-hours, from the UK Department for Energy Security and Net Zero.",
                kind="series",
                unit=Unit(
                    code="kWh-per-household-per-year",
                    label="kilowatt-hours per household per year",
                    short="kWh/household/yr",
                ),
                display=Display(decimals=0),
                scope=Scope(geography=gb_geo, basis=HOUSEHOLD_BASIS),
                geo_coverage="country",
                headline_entity="GBR_GB",
            ),
            inputs=inputs,
            run=_run_gb_energy,
            module_file=here,
            validation=Validation(min_rows=1, value_range=(500.0, 20_000.0)),
        ),
        Transform(
            spec=Spec(
                id="power-scale.desnz.gb-household",
                title="Average electric power of the average household in Great Britain",
                description="The electricity the average household in Great Britain used at home in a year, "
                "expressed as average power in kilowatts: the year's kilowatt-hours spread evenly over its hours. "
                "From the UK Department for Energy Security and Net Zero.",
                kind="derived",
                unit=Unit(code="kW", label="kilowatts (average over the year)", short="kW"),
                display=Display(decimals=2),
                scope=Scope(
                    geography=gb_geo,
                    basis=HOUSEHOLD_BASIS + " Average power is the annual energy divided by the hours of the "
                    "February-to-January electricity year, not the home's peak demand.",
                ),
                geo_coverage="country",
                headline_entity="GBR_GB",
            ),
            inputs=inputs,
            run=_run_gb_power,
            module_file=here,
            validation=Validation(min_rows=1, value_range=(0.05, 5.0)),
            key_files=key,
        ),
        Transform(
            spec=Spec(
                id="electricity-use.desnz.london",
                title="Electricity used in London in a year",
                description="Metered electricity used in a year by all homes and businesses in London's 33 local "
                "authorities, in gigawatt-hours, from the UK Department for Energy Security and Net Zero.",
                kind="series",
                unit=Unit(code="GWh-per-year", label="gigawatt-hours per year", short="GWh/yr"),
                display=Display(decimals=0),
                scope=Scope(geography=london_geo, basis=LONDON_BASIS),
                geo_coverage="country",
                headline_entity="GBR_LONDON",
            ),
            inputs=inputs,
            run=_run_london_energy,
            module_file=here,
            validation=Validation(min_rows=1, value_range=(1_000.0, 200_000.0)),
        ),
        Transform(
            spec=Spec(
                id="power-scale.desnz.london",
                title="Average electric power of London",
                description="The electricity all homes and businesses in London used in a year, expressed as average "
                "power in gigawatts: the year's gigawatt-hours spread evenly over its hours. From the UK Department "
                "for Energy Security and Net Zero.",
                kind="derived",
                unit=Unit(code="GW", label="gigawatts (average over the year)", short="GW"),
                display=Display(decimals=2),
                scope=Scope(
                    geography=london_geo,
                    basis=LONDON_BASIS + " Average power is the annual energy divided by the hours of the year, not "
                    "the city's peak demand.",
                ),
                geo_coverage="country",
                headline_entity="GBR_LONDON",
            ),
            inputs=inputs,
            run=_run_london_power,
            module_file=here,
            validation=Validation(min_rows=1, value_range=(0.1, 50.0)),
            key_files=key,
        ),
    ]
