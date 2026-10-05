"""Defra: the UK's carbon footprint (consumption-based greenhouse gas emissions), as published in "Carbon footprint for
the UK dataset, 1990 to 2023" (release of 30 June 2026, data produced by the University of Leeds).

Input: artifact uk-dataset, an OpenDocument spreadsheet. It is a zip package; the cells are read from its content.xml
with the standard library (table:table-row and table:table-cell, expanding number-columns-repeated and
number-rows-repeated; a number is the cell's office:value as written, a text the cell's paragraphs with <text:s/>
read as spaces). Four sheets are used:

- Cover_sheet: must state "This data is licensed under the Open Government Licence 3.0." (the registry's licence
  quote) and the release date ("originally published at 9:30am on 30 June 2026"), and must still say that 1990 to 1996
  are more uncertain; that sentence is copied as the note of every 1990-1996 value.
- Summary_1990_to_2023: Year, 'Greenhouse gases (ktCO2e)', 'Greenhouse gases (tCO2e per capita)', 'Carbon dioxide
  (ktCO2)'. The per-capita column is published as printed (footprint.defra.per-capita).
- Summary_2023, Table 3 'Greenhouse gas emissions by broad category of end use, UK, 2023': the 14 rows above its
  Total, with these exact labels (note markers such as '[note 3]' removed from the label; the note's own text from the
  Notes sheet becomes the value's note). They must add up to the table's Total and that Total must equal the year's
  'Greenhouse gases (ktCO2e)' in Summary_1990_to_2023, within 0.001 kt (footprint.defra.by-end-use).
- Summary_product, Table 1 'Greenhouse gas emissions from household and household direct expenditure by broad product
  category, UK, 1990 to 2023 (ktCO2e)': 34 COICOP product columns and a Total. In every year the 34 must add up to the
  Total, and the Total must equal Households plus Households direct in Summary_final_demand Table 1, within 0.001 kt
  (footprint.defra.households-by-product). Table 2 of that sheet (carbon dioxide only, though its title says ktCO2e)
  is not used.

Kilotonnes are divided by 1,000 to give million tonnes (exact decimal arithmetic on the values as written). Nothing
else is computed: no shares, sums or per-person values of our own.

Scope, from the dataset and the methods paper: consumption-based, so emissions anywhere in the world from producing
what UK residents, government and capital investment use, plus households' own emissions from heating fuels and
private vehicles; UK exports are excluded. GWP100 values from the IPCC Fifth Assessment Report (AR5): artifact
methods, the release's "Summary of methods" PDF, is an input of every indicator here, and each build refuses it unless
GWP_QUOTE is in the text of its page GWP_PAGE (section 1.4), then cites it in a processing step. The cover sheet says
"there are no specific results available for air travel": households' flights are inside transport, and business and
government travel sit in the supply chains of other rows. Every annual release revises earlier years.
"""

from __future__ import annotations

import functools
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree as ET

from envdash import textmatch
from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "defra-uk-carbon-footprint"
DATASET = Input(SOURCE, "uk-dataset")
METHODS = Input(SOURCE, "methods")
ENTITY = "GBR"
GWP_QUOTE = (
    "Non-CO2 gasses are converted to CO2e using the Global Warming Potential values from the IPCC Fifth Assessment "
    "Report (AR5)."
)
GWP_PAGE = 6
"""Page of the methods PDF (1-based) whose text holds GWP_QUOTE, in section 1.4 'Greenhouse gasses included in the
UK's consumption-based emissions'."""

_TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
_OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
_REPEAT_CAP = 1000
"""Repeated non-empty cells or rows beyond this many are a malformed or unexpected sheet (ODS writers repeat only the
empty cells and rows that pad a sheet to its full size)."""

LICENCE_SENTENCE = "This data is licensed under the Open Government Licence 3.0."
UNCERTAIN_SENTENCE = (
    "There is a higher degree of uncertainty around the estimates for 1990 to 1996, so they should be interpreted "
    "with caution."
)
UNCERTAIN_YEARS = range(1990, 1997)
PUBLISHED = re.compile(
    r"The data tables in this spreadsheet were originally published at [^ ]+ on (\d{1,2} \w+ \d{4})\."
)
TOLERANCE = Decimal("0.001")
THOUSAND = Decimal(1000)

ANNUAL_HEADER = (
    "Year",
    "Greenhouse gases (ktCO2e)",
    "Greenhouse gases (tCO2e per capita)",
    "Carbon dioxide (ktCO2)",
)
END_USE_TITLE = "Table 3: Greenhouse gas emissions by broad category of end use, UK, {year}"
# (dimension value id, label exactly as published without its note marker). The order is the table's.
END_USES: tuple[tuple[str, str], ...] = (
    ("food-and-beverages", "Food and beverages"),
    ("alcohol-and-tobacco", "Alcohol and tobacco"),
    ("clothing-and-footwear", "Clothing and footwear"),
    ("housing-and-power", "Housing and power"),
    ("furnishing-appliances", "Furnishing, appliances"),
    ("health", "Health"),
    ("transportation", "Transportation"),
    ("recreation-and-communication", "Recreation and communication"),
    ("education", "Education"),
    ("hotels-and-restaurants", "Hotels and restaurants"),
    ("other-consumption", "Other consumption"),
    ("central-and-local-government", "Central and local government"),
    ("gross-fixed-capital-formation", "Gross fixed capital formation"),
    ("other", "Other"),
)
PRODUCT_TITLE = (
    "Table 1: Greenhouse gas emissions from household and household direct expenditure by broad product category, "
    "UK, {first} to {last} (ktCO2e)"
)
PRODUCTS: tuple[tuple[str, str], ...] = (
    ("food", "Food"),
    ("non-alcoholic-beverages", "Non-alcoholic beverages"),
    ("alcoholic-beverages", "Alcoholic beverages"),
    ("tobacco", "Tobacco"),
    ("clothing", "Clothing"),
    ("footwear", "Footwear"),
    ("actual-rentals", "Actual rentals for households"),
    ("imputed-rentals", "Imputed rentals for households"),
    ("dwelling-maintenance-and-repair", "Maintenance and repair of the dwelling"),
    ("water-and-dwelling-services", "Water supply and miscellaneous dwelling services"),
    ("electricity-gas-and-other-fuels", "Electricity, gas and other fuels"),
    ("furniture-and-carpets", "Furniture, furnishings, carpets etc"),
    ("household-textiles", "Household textiles"),
    ("household-appliances", "Household appliances"),
    ("glassware-and-utensils", "Glassware, tableware and household utensils"),
    ("tools-and-equipment", "Tools and equipment for house and garden"),
    ("household-maintenance", "Goods and services for household maintenance"),
    ("medical-products", "Medical products, appliances and equipment"),
    ("out-patient-services", "Out-patient services"),
    ("hospital-services", "Hospital services"),
    ("purchase-of-vehicles", "Purchase of vehicles"),
    ("operation-of-personal-transport", "Operation of personal transport equipment"),
    ("transport-services", "Transport services"),
    ("postal-services", "Postal services"),
    ("telephone-equipment", "Telephone and telefax equipment"),
    ("telephone-services", "Telephone and telefax services"),
    ("audio-visual-and-computing-equipment", "Audio-visual, photo and info processing equipment"),
    ("other-recreation-durables", "Other major durables for recreation and culture"),
    ("other-recreational-equipment", "Other recreational equipment etc"),
    ("recreational-and-cultural-services", "Recreational and cultural services"),
    ("newspapers-books-and-stationery", "Newspapers, books and stationery"),
    ("education", "Education"),
    ("restaurants-and-hotels", "Restaurants and hotels"),
    ("miscellaneous-goods-and-services", "Miscellaneous goods and services"),
)
DEMAND_TITLE = "Table 1: Greenhouse gas emissions by broad category of final demand, UK, {first} to {last} (ktCO2e)"
HOUSEHOLDS, HOUSEHOLDS_DIRECT = "Households", "Households direct"

MT_CO2E_YR = Unit(code="MtCO2e/yr", label="million tonnes of carbon dioxide equivalent per year", short="Mt CO₂e/yr")
T_CO2E_PERSON_YR = Unit(
    code="tCO2e/person/yr",
    label="tonnes of carbon dioxide equivalent per person per year",
    short="t CO₂e/person/yr",
)
BASIS = (
    "Consumption-based footprint: greenhouse gas emissions anywhere in the world from producing the goods and services "
    "used in the UK, plus households' own emissions from heating fuels and private vehicles; emissions from producing "
    "UK exports are not counted. Estimated by the University of Leeds with a multi-regional input-output model. "
    "Flights have no separate figure; they are inside transport."
)


class DefraFormatError(ValueError):
    pass


# --- reading the spreadsheet ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Cell:
    value: str | None
    """office:value as written, for a number cell; None otherwise."""
    text: str
    """The cell's paragraphs, with every run of whitespace (line breaks, no-break spaces, trailing spaces) read as one
    space and the ends trimmed."""


Sheet = dict[tuple[int, int], Cell]
"""(row, column) -> cell, 0-based, for every non-empty cell."""


def _paragraph_text(p: ET.Element) -> str:
    out: list[str] = [p.text or ""]
    for child in p:
        if child.tag == _TEXT + "s":
            out.append(" " * int(child.get(_TEXT + "c", "1")))
        elif child.tag == _TEXT + "tab":
            out.append("\t")
        elif child.tag == _TEXT + "line-break":
            out.append("\n")
        else:
            out.append(_paragraph_text(child))
        out.append(child.tail or "")
    return "".join(out)


def _cell(c: ET.Element) -> Cell | None:
    value = c.get(_OFFICE + "value") if c.get(_OFFICE + "value-type") in ("float", "percentage") else None
    text = " ".join("\n".join(_paragraph_text(p) for p in c.findall(_TEXT + "p")).split())
    if value is None and not text:
        return None
    return Cell(value, text)


def read_sheets(raw: bytes) -> dict[str, Sheet]:
    """Every sheet of the OpenDocument spreadsheet `raw`, by name."""
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        if z.read("mimetype") != b"application/vnd.oasis.opendocument.spreadsheet":
            raise DefraFormatError("the file is not an OpenDocument spreadsheet")
        root = ET.fromstring(z.read("content.xml"))
    except (zipfile.BadZipFile, KeyError) as e:
        raise DefraFormatError(f"not a readable OpenDocument spreadsheet: {e}") from None
    sheets: dict[str, Sheet] = {}
    for table in root.iter(_TABLE + "table"):
        name = table.get(_TABLE + "name") or ""
        cells: Sheet = {}
        r = 0
        for row in table.iter(_TABLE + "table-row"):
            row_cells: dict[int, Cell] = {}
            col = 0
            for c in row:
                if c.tag not in (_TABLE + "table-cell", _TABLE + "covered-table-cell"):
                    continue
                rep = int(c.get(_TABLE + "number-columns-repeated", "1"))
                cell = _cell(c)
                if cell is not None:
                    if rep > _REPEAT_CAP:
                        raise DefraFormatError(f"{name}: a non-empty cell repeated {rep} times")
                    for k in range(rep):
                        row_cells[col + k] = cell
                col += rep
            rrep = int(row.get(_TABLE + "number-rows-repeated", "1"))
            if row_cells and rrep > _REPEAT_CAP:
                raise DefraFormatError(f"{name}: a non-empty row repeated {rrep} times")
            for k in range(rrep if row_cells else 0):
                for cc, cell in row_cells.items():
                    cells[(r + k, cc)] = cell
            r += rrep
        if name in sheets:
            raise DefraFormatError(f"two sheets named {name!r}")
        sheets[name] = cells
    return sheets


def _sheet(sheets: dict[str, Sheet], name: str) -> Sheet:
    if name not in sheets:
        raise DefraFormatError(f"no sheet {name!r} (sheets: {sorted(sheets)})")
    return sheets[name]


def _text(s: Sheet, r: int, c: int) -> str:
    cell = s.get((r, c))
    return cell.text if cell is not None else ""


def _num(s: Sheet, r: int, c: int, where: str) -> Decimal:
    cell = s.get((r, c))
    if cell is None or cell.value is None:
        raise DefraFormatError(f"{where}: row {r + 1} column {c + 1} is not a number ({_text(s, r, c)!r})")
    try:
        d = Decimal(cell.value)
    except InvalidOperation:
        raise DefraFormatError(f"{where}: {cell.value!r} is not a number") from None
    if not d.is_finite():
        raise DefraFormatError(f"{where}: {cell.value!r} is not a finite number")
    return d


def _find(s: Sheet, text: str, where: str) -> tuple[int, int]:
    hits = [rc for rc, cell in s.items() if cell.text == text]
    if len(hits) != 1:
        raise DefraFormatError(f"{where}: {len(hits)} cells read {text!r}, expected one")
    return hits[0]


_NOTE_MARKER = re.compile(r"\s*\[notes? ([\d ,and]+)\]$")


def split_label(text: str) -> tuple[str, list[str]]:
    """('Health', ['note 3']) from 'Health [note 3]' or 'Health\\n[note 3]'; 'notes 4 and 5' gives two notes."""
    m = _NOTE_MARKER.search(text)
    if m is None:
        return text, []
    numbers = re.findall(r"\d+", m.group(1))
    return text[: m.start()], [f"note {n}" for n in numbers]


def read_notes(sheets: dict[str, Sheet]) -> dict[str, str]:
    """{'note 1': text, ...} from the Notes sheet's table (Note number, Note text)."""
    s = _sheet(sheets, "Notes")
    r0, c0 = _find(s, "Note number", "Notes")
    if _text(s, r0, c0 + 1) != "Note text":
        raise DefraFormatError("Notes: the second column is not 'Note text'")
    notes: dict[str, str] = {}
    r = r0 + 1
    while _text(s, r, c0):
        notes[_text(s, r, c0)] = _text(s, r, c0 + 1)
        r += 1
    return notes


def _note_text(markers: list[str], notes: dict[str, str]) -> str | None:
    for m in markers:
        if m not in notes:
            raise DefraFormatError(f"label refers to {m}, which the Notes sheet does not have")
    return " ".join(f"Defra {m}: {notes[m]}" for m in markers) or None


# --- the tables ----------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Cover:
    published: str
    """The release date as the cover sheet prints it, e.g. '30 June 2026'."""


def read_cover(sheets: dict[str, Sheet]) -> Cover:
    texts = [c.text for c in _sheet(sheets, "Cover_sheet").values()]
    if LICENCE_SENTENCE not in texts:
        raise DefraFormatError(f"Cover_sheet no longer says {LICENCE_SENTENCE!r}: re-read the terms")
    if UNCERTAIN_SENTENCE not in texts:
        raise DefraFormatError("Cover_sheet no longer carries the 1990-1996 uncertainty sentence the notes copy")
    dates = [m.group(1) for t in texts if (m := PUBLISHED.fullmatch(t))]
    if len(dates) != 1:
        raise DefraFormatError(f"Cover_sheet: {len(dates)} publication-date sentences, expected one")
    return Cover(published=dates[0])


def read_annual(sheets: dict[str, Sheet]) -> dict[int, dict[str, Decimal]]:
    """{year: {column: value}} from Summary_1990_to_2023 (the sheet name is checked against the years it holds)."""
    names = [n for n in sheets if re.fullmatch(r"Summary_\d{4}_to_\d{4}", n)]
    if len(names) != 1:
        raise DefraFormatError(f"expected one Summary_<first>_to_<last> sheet, found {names}")
    s = sheets[names[0]]
    r0, c0 = _find(s, "Year", names[0])
    header = tuple(_text(s, r0, c0 + k) for k in range(len(ANNUAL_HEADER)))
    if header != ANNUAL_HEADER:
        raise DefraFormatError(f"{names[0]}: header {header} != {ANNUAL_HEADER}")
    rows: dict[int, dict[str, Decimal]] = {}
    r = r0 + 1
    while (r, c0) in s:
        year = int(_num(s, r, c0, names[0]))
        rows[year] = {h: _num(s, r, c0 + k, f"{names[0]} {year} {h}") for k, h in enumerate(ANNUAL_HEADER) if k}
        r += 1
    years = list(rows)
    if not years or years != list(range(years[0], years[-1] + 1)):
        raise DefraFormatError(f"{names[0]}: years {years} are not consecutive")
    if names[0] != f"Summary_{years[0]}_to_{years[-1]}":
        raise DefraFormatError(f"sheet {names[0]} holds {years[0]}-{years[-1]}")
    return rows


def read_end_use(
    sheets: dict[str, Sheet], year: int, notes: dict[str, str]
) -> tuple[list[tuple[str, Decimal, str | None]], Decimal]:
    """([(id, ktCO2e, note)] in table order, the table's Total) from Summary_<year> Table 3."""
    name = f"Summary_{year}"
    s = _sheet(sheets, name)
    r0, c0 = _find(s, END_USE_TITLE.format(year=year), name)
    if (_text(s, r0 + 1, c0), _text(s, r0 + 1, c0 + 1)) != ("End use", "ktCO2e"):
        raise DefraFormatError(f"{name}: Table 3 columns are not 'End use', 'ktCO2e'")
    rows: list[tuple[str, Decimal, str | None]] = []
    r = r0 + 2
    while _text(s, r, c0) != "Total":
        if not _text(s, r, c0):
            raise DefraFormatError(f"{name}: Table 3 ends without a Total row")
        label, markers = split_label(_text(s, r, c0))
        rows.append((label, _num(s, r, c0 + 1, f"{name} {label}"), _note_text(markers, notes)))
        r += 1
    labels = tuple(label for label, _, _ in rows)
    expected = tuple(label for _, label in END_USES)
    if labels != expected:
        raise DefraFormatError(f"{name}: Table 3 rows {labels} != {expected}")
    total = _num(s, r, c0 + 1, f"{name} Total")
    parts = sum((v for _, v, _ in rows), Decimal(0))
    if abs(parts - total) > TOLERANCE:
        raise DefraFormatError(f"{name}: the 14 end uses add up to {parts} kt, not the Total {total} kt")
    ids = {label: i for i, label in END_USES}
    return [(ids[label], v, note) for label, v, note in rows], total


def read_final_demand(sheets: dict[str, Sheet], first: int, last: int) -> dict[int, Decimal]:
    """{year: Households + Households direct (ktCO2e)} from Summary_final_demand Table 1 (two published values)."""
    name = "Summary_final_demand"
    s = _sheet(sheets, name)
    r0, c0 = _find(s, DEMAND_TITLE.format(first=first, last=last), name)
    header = [split_label(_text(s, r0 + 1, c0 + k))[0] for k in range(3)]
    if header != ["Year", HOUSEHOLDS, HOUSEHOLDS_DIRECT]:
        raise DefraFormatError(f"{name}: Table 1 starts with columns {header}")
    out: dict[int, Decimal] = {}
    for k, year in enumerate(range(first, last + 1)):
        r = r0 + 2 + k
        if int(_num(s, r, c0, name)) != year:
            raise DefraFormatError(f"{name}: row {r + 1} is not {year}")
        out[year] = _num(s, r, c0 + 1, f"{name} {year}") + _num(s, r, c0 + 2, f"{name} {year}")
    return out


def read_products(
    sheets: dict[str, Sheet], first: int, last: int, notes: dict[str, str]
) -> tuple[dict[int, dict[str, Decimal]], dict[int, Decimal], dict[str, str | None]]:
    """({year: {product id: ktCO2e}}, {year: Total}, {product id: note}) from Summary_product Table 1."""
    name = "Summary_product"
    s = _sheet(sheets, name)
    r0, c0 = _find(s, PRODUCT_TITLE.format(first=first, last=last), name)
    head = r0 + 1
    if _text(s, head, c0) != "Year" or _text(s, head, c0 + len(PRODUCTS) + 1) != "Total":
        raise DefraFormatError(f"{name}: Table 1 is not Year, {len(PRODUCTS)} products, Total")
    split = [split_label(_text(s, head, c0 + 1 + k)) for k in range(len(PRODUCTS))]
    labels = tuple(label for label, _ in split)
    expected = tuple(label for _, label in PRODUCTS)
    if labels != expected:
        raise DefraFormatError(f"{name}: product columns {labels} != {expected}")
    product_notes = {pid: _note_text(m, notes) for (pid, _), (_, m) in zip(PRODUCTS, split, strict=True)}
    values: dict[int, dict[str, Decimal]] = {}
    totals: dict[int, Decimal] = {}
    for k, year in enumerate(range(first, last + 1)):
        r = head + 1 + k
        if int(_num(s, r, c0, name)) != year:
            raise DefraFormatError(f"{name}: row {r + 1} is not {year}")
        values[year] = {
            pid: _num(s, r, c0 + 1 + j, f"{name} {year} {label}") for j, (pid, label) in enumerate(PRODUCTS)
        }
        totals[year] = _num(s, r, c0 + len(PRODUCTS) + 1, f"{name} {year} Total")
        parts = sum(values[year].values(), Decimal(0))
        if abs(parts - totals[year]) > TOLERANCE:
            raise DefraFormatError(f"{name} {year}: the 34 products add up to {parts} kt, not the Total {totals[year]}")
    return values, totals, product_notes


def _mt(kt: Decimal) -> float:
    return float(kt / THOUSAND)


@dataclass(frozen=True)
class Workbook:
    cover: Cover
    annual: dict[int, dict[str, Decimal]]
    notes: dict[str, str]
    sheets: dict[str, Sheet]

    @property
    def first(self) -> int:
        return min(self.annual)

    @property
    def last(self) -> int:
        return max(self.annual)


def read_workbook(raw: bytes) -> Workbook:
    sheets = read_sheets(raw)
    return Workbook(read_cover(sheets), read_annual(sheets), read_notes(sheets), sheets)


@functools.lru_cache(maxsize=2)
def _gwp_found(path: Path) -> bool:
    # Snapshot paths are content-addressed, so caching by path is caching by content: the three indicators parse the
    # PDF once.
    pages = textmatch.pdf_pages_text(path.read_bytes())
    return len(pages) >= GWP_PAGE and textmatch.contains(pages[GWP_PAGE - 1], GWP_QUOTE)


def gwp_step(f: InputFile) -> str:
    """The step citing the methods PDF for the scope's AR5 100-year global warming potentials; refuses a PDF that no
    longer says so on GWP_PAGE."""
    if not _gwp_found(f.path):
        raise DefraFormatError(f"the methods PDF no longer says {GWP_QUOTE!r} on page {GWP_PAGE}")
    return (
        "Global warming potentials: Defra's 'Consumption-based accounts for the UK, 1990 to 2023: Summary of methods' "
        f"(University of Leeds; PDF, sha256 {f.snapshot.sha256[:12]}…, retrieved {f.snapshot.date_accessed.isoformat()}"
        f"), section 1.4, page {GWP_PAGE}: '{GWP_QUOTE}' The quote was found in the text of that page before "
        "publishing; the scope records AR5 100-year values from it."
    )


def _uncertain_note(year: int) -> str | None:
    return f"Defra cover sheet: {UNCERTAIN_SENTENCE}" if year in UNCERTAIN_YEARS else None


def _vintage(wb: Workbook) -> str:
    return f"UK carbon footprint {wb.first} to {wb.last}, published {wb.cover.published}"


def _date_published(wb: Workbook) -> str:
    return datetime.strptime(wb.cover.published, "%d %B %Y").date().isoformat()


def _read_step(f: InputFile, wb: Workbook) -> str:
    return (
        f"Read 'Carbon footprint for the UK dataset, {wb.first} to {wb.last}' (OpenDocument spreadsheet, sha256 "
        f"{f.snapshot.sha256[:12]}…, retrieved {f.snapshot.date_accessed.isoformat()}; the cover sheet says the "
        f"tables were published on {wb.cover.published} and are licensed under the Open Government Licence 3.0). "
        "Cells were read from the file's content.xml as written."
    )


def _run_per_capita(files: dict[str, InputFile]) -> Result:
    f = files[DATASET.key]
    wb = read_workbook(f.path.read_bytes())
    col = "Greenhouse gases (tCO2e per capita)"
    obs = [
        Observation(entity=ENTITY, period=f"{y:04d}", value=float(r[col]), note=_uncertain_note(y))
        for y, r in wb.annual.items()
    ]
    return Result(
        observations=obs,
        vintage=_vintage(wb),
        date_published=_date_published(wb),
        steps=[
            _read_step(f, wb),
            f"Selected the column '{col}' of sheet Summary_{wb.first}_to_{wb.last}, {wb.first}–{wb.last}, as "
            "published (Defra's own per-person figure). No value was changed.",
            "Copied the cover sheet's sentence on 1990 to 1996 ('There is a higher degree of uncertainty around the "
            "estimates for 1990 to 1996, so they should be interpreted with caution.') as the note of each of those "
            "years.",
            gwp_step(files[METHODS.key]),
        ],
    )


def _run_by_end_use(files: dict[str, InputFile]) -> Result:
    f = files[DATASET.key]
    wb = read_workbook(f.path.read_bytes())
    rows, total = read_end_use(wb.sheets, wb.last, wb.notes)
    annual_total = wb.annual[wb.last]["Greenhouse gases (ktCO2e)"]
    if abs(total - annual_total) > TOLERANCE:
        raise DefraFormatError(f"Table 3 Total {total} kt differs from the {wb.last} footprint {annual_total} kt")
    obs = [
        Observation(entity=ENTITY, period=f"{wb.last:04d}", value=_mt(kt), note=note, dims={"end_use": eid})
        for eid, kt, note in rows
    ]
    return Result(
        observations=obs,
        vintage=_vintage(wb),
        date_published=_date_published(wb),
        steps=[
            _read_step(f, wb),
            f"Selected the 14 rows of sheet Summary_{wb.last}, Table 3 'Greenhouse gas emissions by broad category of "
            f"end use, UK, {wb.last}' (ktCO2e), with their labels as published; note markers such as '[note 3]' were "
            "moved from the label to the value's note, which quotes that note from the Notes sheet.",
            f"Checked that the 14 rows add up to the table's Total ({total} kt) and that this Total equals the "
            f"{wb.last} greenhouse gas footprint in Summary_{wb.first}_to_{wb.last}, both within 0.001 kt.",
            "Converted kilotonnes to million tonnes (divided by 1,000, exact decimal arithmetic).",
            gwp_step(files[METHODS.key]),
        ],
        changes="converted from thousand tonnes to million tonnes of carbon dioxide equivalent.",
    )


def _run_households(files: dict[str, InputFile]) -> Result:
    f = files[DATASET.key]
    wb = read_workbook(f.path.read_bytes())
    values, totals, product_notes = read_products(wb.sheets, wb.first, wb.last, wb.notes)
    households = read_final_demand(wb.sheets, wb.first, wb.last)
    for y in values:
        if abs(totals[y] - households[y]) > TOLERANCE:
            raise DefraFormatError(
                f"{y}: Summary_product Total {totals[y]} kt differs from Households + Households direct "
                f"{households[y]} kt in Summary_final_demand"
            )
    obs: list[Observation] = []
    for pid, _ in PRODUCTS:
        for y, row in values.items():
            notes = [n for n in (product_notes[pid], _uncertain_note(y)) if n]
            obs.append(
                Observation(
                    entity=ENTITY,
                    period=f"{y:04d}",
                    value=_mt(row[pid]),
                    note=" ".join(notes) or None,
                    dims={"product": pid},
                )
            )
    return Result(
        observations=obs,
        vintage=_vintage(wb),
        date_published=_date_published(wb),
        steps=[
            _read_step(f, wb),
            f"Selected the {len(PRODUCTS)} product columns of sheet Summary_product, Table 1 'Greenhouse gas "
            "emissions from household and household direct expenditure by broad product category' (ktCO2e), "
            f"{wb.first}–{wb.last}, with their labels as published (note markers moved to the value's note, which "
            "quotes the Notes sheet). Table 2 of the sheet (carbon dioxide only) was not used.",
            "Checked that in every year the products add up to the table's Total, and that the Total equals "
            "Households plus Households direct in Summary_final_demand Table 1, both within 0.001 kt. "
            f"{wb.last}: Total {totals[wb.last]} kt.",
            "Copied the cover sheet's sentence on 1990 to 1996 as the note of each of those years.",
            "Converted kilotonnes to million tonnes (divided by 1,000, exact decimal arithmetic).",
            gwp_step(files[METHODS.key]),
        ],
        changes="converted from thousand tonnes to million tonnes of carbon dioxide equivalent.",
    )


def transforms(paths: Paths) -> list[Transform]:
    revised = " Defra revises earlier years in every annual release. UK only."
    uncertain = (
        " Defra revises earlier years in every annual release, and says the estimates for 1990 to 1996 are more "
        "uncertain. UK only."
    )
    return [
        Transform(
            spec=Spec(
                id="footprint.defra.per-capita",
                title="UK carbon footprint per resident, average (Defra)",
                description="The UK's consumption-based greenhouse gas footprint divided by its population, as "
                "published by Defra, in tonnes of carbon dioxide equivalent per person per year. It counts emissions "
                "anywhere in the world from producing what is used in the UK, by households, government and "
                "investment, plus households' own emissions from heating and driving; it is an average over everyone "
                "in the UK, not a measure of any one person's choices." + uncertain,
                kind="series",
                unit=T_CO2E_PERSON_YR,
                display=Display(decimals=1),
                scope=Scope(geography="United Kingdom: average per resident", gwp="AR5-GWP100", basis=BASIS),
                geo_coverage="country",
                headline_entity=ENTITY,
            ),
            inputs=(DATASET, METHODS),
            run=_run_per_capita,
            module_file=Path(__file__),
            validation=Validation(min_rows=34, value_range=(0.0, 40.0)),
        ),
        Transform(
            spec=Spec(
                id="footprint.defra.by-end-use",
                title="UK carbon footprint by end use, latest year (Defra)",
                description="The UK's whole consumption-based greenhouse gas footprint in the latest year of Defra's "
                "release, split into the 14 broad categories of end use Defra publishes for that year only, in "
                "million tonnes of carbon dioxide equivalent. The first eleven are households' spending and their "
                "direct emissions from heating and driving; 'Central and local government', "
                "'Gross fixed capital formation' (investment, including buying houses) and 'Other' (charities, "
                "valuables, inventories) are not. 'Food and beverages' covers food and non-alcoholic drinks bought "
                "by households; it excludes 'Hotels and restaurants' and 'Alcohol and tobacco', which are separate "
                "rows. Flights have no row of their own: households' spending on flights is inside 'Transportation', "
                "while business and government travel sits in the supply chains of the other rows. Health and "
                "education paid for by government are under government. The rows add up to the published total."
                + revised,
                kind="series",
                unit=MT_CO2E_YR,
                display=Display(decimals=1),
                scope=Scope(geography="United Kingdom", gwp="AR5-GWP100", basis=BASIS),
                geo_coverage="country",
                headline_entity=ENTITY,
                dimensions=(
                    Dimension(
                        id="end_use",
                        label="Broad category of end use",
                        values=[DimensionValue(id=i, label=label) for i, label in END_USES],
                    ),
                ),
                headline_dims=(("end_use", "food-and-beverages"),),
            ),
            inputs=(DATASET, METHODS),
            run=_run_by_end_use,
            module_file=Path(__file__),
            validation=Validation(min_rows=14, value_range=(0.0, 1000.0)),
        ),
        Transform(
            spec=Spec(
                id="footprint.defra.households-by-product",
                title="UK households' carbon footprint by product (Defra)",
                description="The consumption-based greenhouse gas footprint of UK households' own spending and their "
                "direct emissions from heating fuels and private vehicles, split into the 34 COICOP product groups "
                "Defra publishes, in million tonnes of carbon dioxide equivalent per year. Government spending, "
                "investment (including buying houses) and charities are not included, so these add up to the "
                "households' part of the UK footprint, not to the whole. 'Food' and 'Non-alcoholic beverages' do not "
                "include meals and drinks bought in restaurants, cafés and hotels, which are in 'Restaurants and "
                "hotels'. Flights have no "
                "group of their own; they are inside 'Transport services'." + uncertain,
                kind="series",
                unit=MT_CO2E_YR,
                display=Display(decimals=1),
                scope=Scope(geography="United Kingdom: households", gwp="AR5-GWP100", basis=BASIS),
                geo_coverage="country",
                headline_entity=ENTITY,
                dimensions=(
                    Dimension(
                        id="product",
                        label="Product group (COICOP)",
                        values=[DimensionValue(id=i, label=label) for i, label in PRODUCTS],
                    ),
                ),
                headline_dims=(("product", "food"),),
            ),
            inputs=(DATASET, METHODS),
            run=_run_households,
            module_file=Path(__file__),
            validation=Validation(min_rows=34 * 34, value_range=(0.0, 1000.0)),
        ),
    ]
