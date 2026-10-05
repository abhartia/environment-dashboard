"""FAOSTAT greenhouse gas emissions from all sectors: the six IPCC sectors, their total, the split by gas, emissions
per person, food systems' share and methane by sector (source faostat-all-sectors, class noncommercial).

Inputs. Emissions totals (GT): Emissions_Totals_E_All_Data_(Normalized).csv (UTF-8, CRLF, every field quoted; columns
Area Code, Area Code (M49), Area, Item Code, Item, Element Code, Element, Year Code, Year, Source Code, Source, Unit,
Value, Flag, Note) and its flag codebook. Emissions indicators (EM): Climate_change_Emissions_indicators_E_All_Data_
(Normalized).csv (the same layout without Source Code, Source and Note) and its flag codebook. Both are read in place
from the zips; nothing is extracted. Rows are matched by code (area, item, element) and the names and unit next to the
codes must be the ones declared below, or the transform stops. Only GT's "FAO TIER 1" rows are used; its "UNFCCC" rows
(country inventory submissions) are never mixed in.

What the items are. FAO computes Agriculture (1711 "IPCC Agriculture") and LULUCF (1707) itself, by IPCC Tier 1
methods. Energy (6821), IPPU (6817, industrial processes and product use), Waste (6818) and Other (6819) are the
PRIMAP-hist v2.7 third-party-priority series (see pipeline/sources/faostat-all-sectors.yaml for the evidence). LULUCF is
a net, inventory-style figure: net forest conversion, minus the carbon taken up by existing forests ("Forestland"),
plus drained organic soils and fires, so it can be negative. "All sectors with LULUCF" (6825) is the sum of the six;
"International bunkers" (6820, aviation and shipping fuel sold for international trips) is a separate memo item outside
it and is not used.

Identities the transform enforces (in every area and year it publishes, missing items counted as absent, never zero):
- the six sectors add up to item 6825, element "Emissions (CO2eq) (AR5)" (723113);
- for item 6825, "Emissions (CO2)" (7273) plus the CO2-equivalent of CH4 (724413), N2O (724313) and F-gases (717815)
  equals element 723113 (CO2 counts at a global warming potential of 1, so its kilotonnes are CO2-equivalent);
- in EM, the shares of all methane (element 7265) of the six sectors add up to 100 within the rounding of the printed
  values, where FAO publishes all six.
A release that breaks one stops the transform. The tolerances are stated next to the constants below.

Areas. FAO area codes go through faostat_bulk.area_entity, the crosswalk the other FAOSTAT transforms use: countries
and territories, the European Union (27) and the World are published; FAO's regional and analytical groups, former
states and Sark are not, and "China" (351, FAO's sum of mainland China, Hong Kong, Macao and Taiwan) is never published
beside its parts. PRIMAP-hist counts some territories inside their parent country (GT_en.pdf annex: Bermuda, the
Cayman Islands, Anguilla and other UK territories in the United Kingdom; the Faroe Islands and Greenland in Denmark;
Palestine in Israel; Western Sahara in Morocco; Guam, Puerto Rico and the other US territories in the United States;
Tokelau in New Zealand), while FAO publishes those territories' agriculture and land use separately. So such a parent's
energy, industry, waste and other emissions include its territories and its agriculture and land use do not, and the
territory itself has no energy, industry, waste or other rows: its "all sectors" total is agriculture and land use
only. Missing sector rows stay missing; a processing step names every area and item concerned.

Years. Energy, IPPU, Waste, Other and Agriculture run from 1961, LULUCF and the all-sector total from 1990. The sector
split is published for the years in which FAO publishes the area's all-sector total, so the parts always make up a
published total; earlier sector rows are left out and counted in a processing step.

Units. GT values are kilotonnes; they are divided by 1,000,000 (exact decimal arithmetic on the printed values) to give
billion tonnes. EM values (percent, tonnes per person) are published as printed.

Vintage: each domain's DateUpdate in FAOSTAT's bulk catalogue (datasets_E.json), accepted only when the catalogue entry
names the zip's URL and its FileRows equals the number of data rows in the CSV.

Publisher checks: FAOSTAT Analytical Brief 115 (November 2025) for the release of 28 October 2025: "global
anthropogenic emissions reached 52.1 Gt CO2eq in 2023" and the agrifood share of 38 percent (2001) and 32 percent
(2023). The brief states no world per-capita value of all sectors, by-sector or by-gas value, or methane share; those
are pinned by regression tests on the snapshot (tests/test_ghg_faostat_all_sectors.py).
"""

from __future__ import annotations

import csv
import functools
import io
import zipfile
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, PublisherCheck, Result, Spec, Transform, Validation
from envdash.transforms.food.faostat_bulk import (
    FaostatBulkError,
    area_entity,
    catalogue_entry,
    flag_step,
    flag_words,
    not_published_step,
    read_flags,
)

SOURCE = "faostat-all-sectors"
TOTALS = Input(SOURCE, "emissions-totals")
INDICATORS = Input(SOURCE, "emissions-indicators")
CATALOGUE = Input(SOURCE, "datasets-catalogue")

ENCODING = "utf-8"
TIER1 = "FAO TIER 1"
FORECAST = "F"
WORLD = "WLD"


@dataclass(frozen=True)
class Domain:
    code: str
    """FAOSTAT DatasetCode in datasets_E.json."""
    name: str
    data_member: str
    flags_member: str
    columns: tuple[str, ...]


GT = Domain(
    "GT",
    "Emissions totals",
    "Emissions_Totals_E_All_Data_(Normalized).csv",
    "Emissions_Totals_E_Flags.csv",
    (
        "Area Code",
        "Area Code (M49)",
        "Area",
        "Item Code",
        "Item",
        "Element Code",
        "Element",
        "Year Code",
        "Year",
        "Source Code",
        "Source",
        "Unit",
        "Value",
        "Flag",
        "Note",
    ),
)
EM = Domain(
    "EM",
    "Emissions indicators",
    "Climate_change_Emissions_indicators_E_All_Data_(Normalized).csv",
    "Climate_change_Emissions_indicators_E_Flags.csv",
    (
        "Area Code",
        "Area Code (M49)",
        "Area",
        "Item Code",
        "Item",
        "Element Code",
        "Element",
        "Year Code",
        "Year",
        "Unit",
        "Value",
        "Flag",
    ),
)


@dataclass(frozen=True)
class Code:
    code: str
    name: str
    """FAO's name next to the code; a different name stops the transform."""


@dataclass(frozen=True)
class Part:
    """One value of a published dimension and the FAO code it is read from."""

    id: str
    label: str
    fao: Code


# The six IPCC sectors, in the order they are published. They do not overlap and add up to ALL_SECTORS.
SECTORS: tuple[Part, ...] = (
    Part("energy", "Energy", Code("6821", "Energy")),
    Part("industry", "Industrial processes and product use", Code("6817", "IPPU")),
    Part("agriculture", "Agriculture", Code("1711", "IPCC Agriculture")),
    Part("land-use", "Land use, land-use change and forestry (net)", Code("1707", "LULUCF")),
    Part("waste", "Waste", Code("6818", "Waste")),
    Part("other", "Other", Code("6819", "Other")),
)
ALL_SECTORS = Code("6825", "All sectors with LULUCF")
AGRIFOOD = Code("6518", "Agrifood systems")

CO2EQ = Code("723113", "Emissions (CO2eq) (AR5)")
# The split of ALL_SECTORS by gas, in the order published; each is a CO2-equivalent at AR5 GWP100 (CO2 at 1).
GASES: tuple[Part, ...] = (
    Part("co2", "Carbon dioxide", Code("7273", "Emissions (CO2)")),
    Part("ch4", "Methane", Code("724413", "Emissions (CO2eq) from CH4 (AR5)")),
    Part("n2o", "Nitrous oxide", Code("724313", "Emissions (CO2eq) from N2O (AR5)")),
    Part("f-gases", "Fluorinated gases", Code("717815", "Emissions (CO2eq) from F-gases (AR5)")),
)
SHARE = Code("726313", "Emissions Share (CO2eq) (AR5)")
CH4_SHARE = Code("7265", "Emissions Share (CH4)")
PER_CAPITA = Code("7279", "Emissions per capita")

UNIT_KT = "kt"
UNIT_PERCENT = "%"
UNIT_PER_CAPITA = "t CO2eq/cap"

KT_TOLERANCE = Decimal("0.001")
"""GT prints kilotonnes to 0.0001 kt. Seven printed values (six parts and a total) can differ from an exact sum by at
most 7 x 0.00005 = 0.00035 kt; 0.001 kt allows that and nothing a real mismatch could hide in."""
SHARE_TOLERANCE = Decimal("0.03")
"""EM prints shares to 0.01 percent. Six rounded parts can miss 100 by at most 6 x 0.005 = 0.03."""

BRIEF_URL = "https://openknowledge.fao.org/server/api/core/bitstreams/7278290b-334e-457e-a589-439a971ecc84/content"
VINTAGE_2023 = "2025-10-28"


@dataclass(frozen=True, slots=True)
class Row:
    area: str
    """FAO Area Code."""
    entity: str | None
    """Our entity code; None for an area that is not published (see faostat_bulk)."""
    item: str
    element: str
    year: int
    value: Decimal
    flag: str
    note: str


@dataclass(frozen=True)
class Table:
    data_rows: int
    """Every data row in the CSV, for comparison with the catalogue's FileRows."""
    rows: tuple[Row, ...]
    """The estimates kept (forecast rows removed)."""
    left_out: frozenset[str]
    """FAO area codes of kept item/element rows whose area is not published."""
    forecast: tuple[tuple[str, str, str, int], ...]
    """(area, item, element, year) of rows flagged F, which are not published."""


# --- reading -------------------------------------------------------------------------------------------------------


def _fields(line: bytes) -> list[str]:
    return next(csv.reader(io.StringIO(line.decode(ENCODING))))


def scan(lines: Iterable[bytes], domain: Domain, wanted: dict[tuple[str, str], tuple[str, str, str]]) -> Table:
    """Count every data row of a domain's CSV and keep the rows of the wanted (item code, element code) pairs, each
    mapped to (item name, element name, unit) as FAO must print them. GT rows other than "FAO TIER 1" are skipped."""
    it = iter(lines)
    header = tuple(_fields(next(it)))
    if header != domain.columns:
        raise FaostatBulkError(f"{domain.data_member}: columns {list(header)} != expected {list(domain.columns)}")
    has_source = "Source" in domain.columns
    markers = tuple(sorted({f'","{item}","'.encode() for item, _ in wanted}))
    n = 0
    kept: list[Row] = []
    forecast: list[tuple[str, str, str, int]] = []
    left_out: set[str] = set()
    for line in it:
        n += 1
        if not line.startswith(b'"'):
            raise FaostatBulkError(f"{domain.data_member}: data row {n} does not start with a quoted Area Code")
        if not any(m in line for m in markers):
            continue
        f = _fields(line)
        if len(f) != len(domain.columns):
            raise FaostatBulkError(f"{domain.data_member}: data row {n} has {len(f)} fields, not {len(domain.columns)}")
        r = dict(zip(domain.columns, f, strict=True))
        key = (r["Item Code"], r["Element Code"])
        if key not in wanted or (has_source and r["Source"] != TIER1):
            continue
        what = f"{domain.code} area {r['Area Code']} item {key[0]} element {key[1]} {r['Year']}"
        item_name, element_name, unit = wanted[key]
        if (r["Item"], r["Element"]) != (item_name, element_name):
            raise FaostatBulkError(
                f"{what}: named {r['Item']!r} / {r['Element']!r}, expected {item_name!r} / {element_name!r}"
            )
        if r["Unit"] != unit:
            raise FaostatBulkError(f"{what}: unit {r['Unit']!r}, expected {unit!r}")
        if r["Year"] != r["Year Code"] or not r["Year"].isdigit() or len(r["Year"]) != 4:
            raise FaostatBulkError(f"{what}: Year {r['Year']!r} / Year Code {r['Year Code']!r} is not one year")
        if r["Value"] == "":
            raise FaostatBulkError(f"{what}: empty Value; re-read the file before trusting it")
        entity = area_entity(r["Area Code"], r["Area Code (M49)"])
        if entity is None:
            left_out.add(r["Area Code"])
            continue
        year = int(r["Year"])
        if r["Flag"] == FORECAST:
            forecast.append((r["Area Code"], key[0], key[1], year))
            continue
        kept.append(
            Row(r["Area Code"], entity, key[0], key[1], year, Decimal(r["Value"]), r["Flag"], r.get("Note", ""))
        )
    _check_unique_and_forecasts(kept, forecast, domain)
    return Table(n, tuple(kept), frozenset(left_out), tuple(sorted(forecast)))


def _check_unique_and_forecasts(rows: list[Row], forecast: list[tuple[str, str, str, int]], domain: Domain) -> None:
    seen: set[tuple[str, str, str, int]] = set()
    last: dict[tuple[str, str, str], int] = {}
    for r in rows:
        k = (r.area, r.item, r.element, r.year)
        if k in seen:
            raise FaostatBulkError(f"{domain.code}: more than one value for area {r.area} item {r.item} {r.year}")
        seen.add(k)
        s = (r.area, r.item, r.element)
        last[s] = max(last.get(s, r.year), r.year)
    for area, item, element, year in forecast:
        if year <= last.get((area, item, element), 0):
            raise FaostatBulkError(
                f"{domain.code}: area {area} item {item} element {element}: forecast year {year} is not after the "
                "last estimate"
            )


def _wanted_gt() -> dict[tuple[str, str], tuple[str, str, str]]:
    w = {(p.fao.code, CO2EQ.code): (p.fao.name, CO2EQ.name, UNIT_KT) for p in SECTORS}
    w[(ALL_SECTORS.code, CO2EQ.code)] = (ALL_SECTORS.name, CO2EQ.name, UNIT_KT)
    for g in GASES:
        w[(ALL_SECTORS.code, g.fao.code)] = (ALL_SECTORS.name, g.fao.name, UNIT_KT)
    return w


def _wanted_em() -> dict[tuple[str, str], tuple[str, str, str]]:
    w = {(p.fao.code, CH4_SHARE.code): (p.fao.name, CH4_SHARE.name, UNIT_PERCENT) for p in SECTORS}
    w[(ALL_SECTORS.code, PER_CAPITA.code)] = (ALL_SECTORS.name, PER_CAPITA.name, UNIT_PER_CAPITA)
    w[(AGRIFOOD.code, SHARE.code)] = (AGRIFOOD.name, SHARE.name, UNIT_PERCENT)
    return w


@functools.lru_cache(maxsize=2)
def read_zip(path: Path, domain_code: str) -> tuple[Table, dict[str, str]]:
    # Snapshot paths are content-addressed (pipeline/.snapshots/<sha256>), so caching by path is caching by content:
    # the indicators of one domain read its CSV member once, streamed from the zip.
    domain, wanted = (GT, _wanted_gt()) if domain_code == GT.code else (EM, _wanted_em())
    with zipfile.ZipFile(path) as z:
        with z.open(domain.data_member) as f:
            table = scan(f, domain, wanted)
        flags = read_flags(z.read(domain.flags_member), domain.flags_member)
    if flags.get(FORECAST, "Forecast value") != "Forecast value":
        raise FaostatBulkError(f"{domain.flags_member}: flag {FORECAST} is {flags[FORECAST]!r}, not 'Forecast value'")
    return table, flags


# --- selection -----------------------------------------------------------------------------------------------------


Key = tuple[str, int]
"""(entity, year)"""


def values(table: Table, item: Code, element: Code) -> dict[Key, Row]:
    """{(entity, year): row} of one item and element. Two FAO areas resolving to one entity stop the transform."""
    out: dict[Key, Row] = {}
    for r in table.rows:
        if r.item == item.code and r.element == element.code:
            assert r.entity is not None  # rows of unpublished areas are never kept
            k = (r.entity, r.year)
            if k in out:
                raise FaostatBulkError(f"areas {out[k].area} and {r.area} are both {r.entity}, {item.name} {r.year}")
            out[k] = r
    return out


def _need_world(found: dict[Key, Row], what: str) -> None:
    if not any(e == WORLD for e, _ in found):
        raise FaostatBulkError(f"no World values of {what}")


def missing_parts(totals: dict[Key, Row], parts: dict[str, dict[Key, Row]]) -> dict[str, dict[str, list[int]]]:
    """{entity: {part id: [years with a total but no row of that part]}}, for the processing step."""
    out: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for entity, year in sorted(totals):
        for pid, rows in parts.items():
            if (entity, year) not in rows:
                out[entity][pid].append(year)
    return {e: dict(v) for e, v in out.items()}


def identity_gap(total: Row, parts: list[Row]) -> Decimal:
    """Published parts minus the published total, in the file's units (a check, never published)."""
    return sum((p.value for p in parts), Decimal(0)) - total.value


def _years(ys: list[int]) -> str:
    """1990-2023, or a list of runs: 1990-1995, 2001."""
    runs: list[tuple[int, int]] = []
    for y in sorted(ys):
        if runs and y == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], y)
        else:
            runs.append((y, y))
    return ", ".join(f"{a}" if a == b else f"{a}–{b}" for a, b in runs)


TOTAL_TAIL = "the published total of those areas is the sum of the parts that exist."


def missing_step(
    missing: dict[str, dict[str, list[int]]], labels: dict[str, str], whole: str, tail: str = TOTAL_TAIL
) -> str:
    """Words naming every entity and part with no row in a year that has a total; `tail` says what that means."""
    if not missing:
        return f"Every published {whole} has all its parts."
    # Group entities by the same (part, years) pattern so the step stays readable.
    groups: dict[tuple[tuple[str, str], ...], list[str]] = defaultdict(list)
    for entity, parts in missing.items():
        sig = tuple(
            (labels[pid], _years(ys)) for pid, ys in sorted(parts.items(), key=lambda kv: list(labels).index(kv[0]))
        )
        groups[sig].append(entity)
    phrases = []
    for sig, entities in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[1])):
        parts = "; ".join(f"{label} ({years})" for label, years in sig)
        phrases.append(f"{', '.join(sorted(entities))}: no {parts}")
    return (
        f"FAO publishes no row for some parts of some areas' {whole}. Those parts are left missing, never filled or "
        f"set to zero, and {tail} " + ". ".join(phrases) + "."
    )


def _observations(
    selected: list[tuple[str, int, Decimal, Row, dict[str, str]]], flags: dict[str, str], member: str
) -> tuple[list[Observation], str]:
    """(entity, year, value, source row, dims) -> observations in the given order, plus the flag step."""
    counts = Counter(r.flag for _, _, _, r, _ in selected)
    words = flag_words(flags, counts, member)
    obs = []
    for entity, year, value, r, dims in selected:
        notes = [f"FAO note: {r.note}"] if r.note else []
        if len(words) > 1:
            notes.append(f"FAO flag {r.flag}: {words[r.flag]}.")
        obs.append(
            Observation(
                entity=entity, period=f"{year:04d}", value=float(value), note=" ".join(notes) or None, dims=dims
            )
        )
    return obs, flag_step(words, counts)


def _forecast_step(table: Table) -> list[str]:
    if not table.forecast:
        return []
    years = sorted({y for _, _, _, y in table.forecast})
    return [f'Left out FAO\'s projections for {_years(years)}, which the file flags F ("Forecast value").']


MILLION = Decimal(1_000_000)


def by_sector(table: Table, flags: dict[str, str]) -> tuple[list[Observation], list[str]]:
    totals = values(table, ALL_SECTORS, CO2EQ)
    _need_world(totals, ALL_SECTORS.name)
    parts = {p.id: values(table, p.fao, CO2EQ) for p in SECTORS}
    for (entity, year), total in totals.items():
        present = [parts[p.id][(entity, year)] for p in SECTORS if (entity, year) in parts[p.id]]
        if not present:
            raise FaostatBulkError(f"{entity} {year}: an all-sector total with no sector rows")
        gap = identity_gap(total, present)
        if abs(gap) > KT_TOLERANCE:
            raise FaostatBulkError(
                f"{entity} {year}: the sectors add up to {gap:+} kt away from {ALL_SECTORS.name} ({total.value} kt)"
            )
    dropped = [k for p in SECTORS for k in parts[p.id] if k not in totals]
    selected = [
        (entity, year, parts[p.id][(entity, year)].value / MILLION, parts[p.id][(entity, year)], {"sector": p.id})
        for entity in sorted({e for e, _ in totals})
        for p in SECTORS
        for year in sorted(y for e, y in totals if e == entity)
        if (entity, year) in parts[p.id]
    ]
    obs, fstep = _observations(selected, flags, GT.flags_member)
    years = sorted({y for _, y in totals})
    labels = {p.id: f'{p.label} (item {p.fao.code} "{p.fao.name}")' for p in SECTORS}
    steps = [
        f'Kept the "{TIER1}" rows of element "{CO2EQ.name}" (code {CO2EQ.code}) for the six IPCC sector items '
        + ", ".join(f'"{p.fao.name}" ({p.fao.code})' for p in SECTORS)
        + ', in kilotonnes of CO₂-equivalent (IPCC AR5 100-year global warming potentials). Rows from FAO\'s "UNFCCC" '
        'source and the memo item "International bunkers" (6820) are not used.',
        f"Kept each sector's values for the years in which FAO publishes the area's \"{ALL_SECTORS.name}\" total "
        f"(item {ALL_SECTORS.code}; {years[0]}–{years[-1]} for the World), so the sectors of every published year make "
        f"up a published total. {_dropped_words(dropped)}",
        f'Checked in every area and year that the sectors present add up to "{ALL_SECTORS.name}" within '
        f"{KT_TOLERANCE} kt (the rounding of the printed values); the transform stops otherwise.",
        missing_step(missing_parts(totals, parts), labels, "all-sector totals"),
        not_published_step(table.left_out),
        "Converted kilotonnes to billion tonnes by dividing by 1,000,000 (exact decimal arithmetic on the printed "
        "values).",
        fstep,
        *_forecast_step(table),
    ]
    return obs, steps


def _dropped_words(dropped: list[Key]) -> str:
    if not dropped:
        return "No sector value is left out."
    early = sum(1 for _, y in dropped if y < 1990)
    words = f"{len(dropped):,} sector values of area-years without a total are left out"
    if early == len(dropped):
        return (
            f"{words}, all from {min(y for _, y in dropped)}–1989, before FAO's land-use and all-sector series begin."
        )
    later = _years(sorted({y for _, y in dropped if y >= 1990}))
    return f"{words}: {early:,} from before 1990 and {len(dropped) - early:,} from {later}."


def total(table: Table, flags: dict[str, str]) -> tuple[list[Observation], list[str]]:
    totals = values(table, ALL_SECTORS, CO2EQ)
    _need_world(totals, ALL_SECTORS.name)
    parts = {p.id: values(table, p.fao, CO2EQ) for p in SECTORS}
    selected = [(e, y, r.value / MILLION, r, {}) for (e, y), r in sorted(totals.items())]
    obs, fstep = _observations(selected, flags, GT.flags_member)
    labels = {p.id: f"{p.label} (item {p.fao.code})" for p in SECTORS}
    years = sorted({y for _, y in totals})
    steps = [
        f'Kept the "{TIER1}" rows of item "{ALL_SECTORS.name}" (code {ALL_SECTORS.code}), element "{CO2EQ.name}" '
        f"(code {CO2EQ.code}), {years[0]}–{years[-1]}, in kilotonnes of CO₂-equivalent (IPCC AR5 100-year global "
        'warming potentials). Rows from FAO\'s "UNFCCC" source are not used.',
        "FAO's total is the sum of its six IPCC sector items (energy, industrial processes and product use, "
        "agriculture, net land use, land-use change and forestry, waste, other); international aviation and shipping "
        '("International bunkers", item 6820) are outside it. '
        + missing_step(missing_parts(totals, parts), labels, "all-sector totals"),
        not_published_step(table.left_out),
        "Converted kilotonnes to billion tonnes by dividing by 1,000,000 (exact decimal arithmetic on the printed "
        "values).",
        fstep,
        *_forecast_step(table),
    ]
    return obs, steps


def by_gas(table: Table, flags: dict[str, str]) -> tuple[list[Observation], list[str]]:
    totals = values(table, ALL_SECTORS, CO2EQ)
    _need_world(totals, ALL_SECTORS.name)
    parts = {g.id: values(table, ALL_SECTORS, g.fao) for g in GASES}
    for k in set().union(*parts.values()) - set(totals):
        raise FaostatBulkError(f"{k[0]} {k[1]}: a gas value of {ALL_SECTORS.name} without its CO2eq total")
    for (entity, year), t in totals.items():
        present = [parts[g.id][(entity, year)] for g in GASES if (entity, year) in parts[g.id]]
        gap = identity_gap(t, present)
        if abs(gap) > KT_TOLERANCE:
            raise FaostatBulkError(
                f"{entity} {year}: the gases add up to {gap:+} kt away from the total ({t.value} kt)"
            )
    selected = [
        (entity, year, parts[g.id][(entity, year)].value / MILLION, parts[g.id][(entity, year)], {"gas": g.id})
        for entity in sorted({e for e, _ in totals})
        for g in GASES
        for year in sorted(y for e, y in totals if e == entity)
        if (entity, year) in parts[g.id]
    ]
    obs, fstep = _observations(selected, flags, GT.flags_member)
    labels = {g.id: f"{g.label} (element {g.fao.code})" for g in GASES}
    steps = [
        f'Kept the "{TIER1}" rows of item "{ALL_SECTORS.name}" (code {ALL_SECTORS.code}) for the elements '
        + ", ".join(f'"{g.fao.name}" ({g.fao.code})' for g in GASES)
        + ", in kilotonnes. Carbon dioxide is in kilotonnes of CO₂, which is its own CO₂-equivalent (global warming "
        "potential 1); the other three are FAO's CO₂-equivalents at IPCC AR5 100-year global warming potentials "
        "(methane 28, nitrous oxide 265).",
        f'Checked in every area and year that the four gases present add up to element "{CO2EQ.name}" '
        f"(code {CO2EQ.code}) of the same item within {KT_TOLERANCE} kt; the transform stops otherwise.",
        missing_step(missing_parts(totals, parts), labels, "all-sector totals"),
        not_published_step(table.left_out),
        "Converted kilotonnes to billion tonnes by dividing by 1,000,000 (exact decimal arithmetic on the printed "
        "values).",
        fstep,
        *_forecast_step(table),
    ]
    return obs, steps


def per_capita(table: Table, flags: dict[str, str]) -> tuple[list[Observation], list[str]]:
    found = values(table, ALL_SECTORS, PER_CAPITA)
    _need_world(found, PER_CAPITA.name)
    selected = [(e, y, r.value, r, {}) for (e, y), r in sorted(found.items())]
    obs, fstep = _observations(selected, flags, EM.flags_member)
    years = sorted({y for _, y in found})
    steps = [
        f'Kept the rows of item "{ALL_SECTORS.name}" (code {ALL_SECTORS.code}), element "{PER_CAPITA.name}" (code '
        f'{PER_CAPITA.code}), unit "{UNIT_PER_CAPITA}", {years[0]}–{years[-1]}, as FAO prints them. FAO divides each '
        "area's all-sector emissions by its population; nothing is computed here.",
        not_published_step(table.left_out),
        fstep,
        *_forecast_step(table),
    ]
    return obs, steps


def agrifood_share(table: Table, flags: dict[str, str]) -> tuple[list[Observation], list[str]]:
    found = {k: r for k, r in values(table, AGRIFOOD, SHARE).items() if k[0] == WORLD}
    _need_world(found, f"{AGRIFOOD.name} / {SHARE.name}")
    selected = [(e, y, r.value, r, {}) for (e, y), r in sorted(found.items())]
    obs, fstep = _observations(selected, flags, EM.flags_member)
    years = sorted({y for _, y in found})
    steps = [
        f'Kept the World (area code 5000) rows of item "{AGRIFOOD.name}" (code {AGRIFOOD.code}), element '
        f'"{SHARE.name}" (code {SHARE.code}), unit "{UNIT_PERCENT}", {years[0]}–{years[-1]}, as FAO prints them: '
        f'FAO\'s own share of agrifood-system emissions in its "{ALL_SECTORS.name}" total. Nothing is computed here.',
        fstep,
        *_forecast_step(table),
    ]
    return obs, steps


def ch4_share_by_sector(table: Table, flags: dict[str, str]) -> tuple[list[Observation], list[str]]:
    parts = {p.id: values(table, p.fao, CH4_SHARE) for p in SECTORS}
    keys = sorted(set().union(*parts.values()))
    if not any(e == WORLD for e, _ in keys):
        raise FaostatBulkError(f"no World values of {CH4_SHARE.name}")
    complete = 0
    off: dict[str, list[tuple[int, Decimal]]] = defaultdict(list)
    for k in keys:
        present = [parts[p.id][k] for p in SECTORS if k in parts[p.id]]
        added = sum((r.value for r in present), Decimal(0))
        if len(present) == len(SECTORS):
            complete += 1
            if abs(added - 100) > SHARE_TOLERANCE:
                raise FaostatBulkError(f"{k[0]} {k[1]}: the six sectors' methane shares add up to {added}, not 100")
        elif abs(added - 100) > len(present) * SHARE_TOLERANCE / len(SECTORS):
            off[k[0]].append((k[1], added))
    selected = [
        (entity, year, parts[p.id][(entity, year)].value, parts[p.id][(entity, year)], {"sector": p.id})
        for entity in sorted({e for e, _ in keys})
        for p in SECTORS
        for year in sorted(y for e, y in keys if e == entity)
        if (entity, year) in parts[p.id]
    ]
    obs, fstep = _observations(selected, flags, EM.flags_member)
    years = sorted({y for _, y in keys})
    labels = {p.id: f"{p.label} (item {p.fao.code})" for p in SECTORS}
    steps = [
        f'Kept the rows of element "{CH4_SHARE.name}" (code {CH4_SHARE.code}), unit "{UNIT_PERCENT}", for the six IPCC '
        "sector items "
        + ", ".join(f'"{p.fao.name}" ({p.fao.code})' for p in SECTORS)
        + f", {years[0]}–{years[-1]}, as FAO prints them: each sector's methane as a percentage of the area's methane "
        f'from all sectors (item "{ALL_SECTORS.name}"). Nothing is computed here.',
        f"Checked that the six shares add up to 100 within {SHARE_TOLERANCE} (the rounding of values printed to "
        f"0.01) in each of the {complete:,} area-years where FAO publishes all six; the transform stops otherwise.",
        _ch4_missing_step(keys, parts, labels),
        *_ch4_off_step(off),
        not_published_step(table.left_out),
        fstep,
        *_forecast_step(table),
    ]
    return obs, steps


def _ch4_missing_step(keys: list[Key], parts: dict[str, dict[Key, Row]], labels: dict[str, str]) -> str:
    missing: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for k in keys:
        for pid, rows in parts.items():
            if k not in rows:
                missing[k[0]][pid].append(k[1])
    return missing_step(
        {e: dict(v) for e, v in missing.items()},
        labels,
        "methane splits",
        "a sector without a share is one for which FAOSTAT's emissions totals (GT) have no methane row for that area "
        "and year, so it is not part of the whole.",
    )


def _ch4_off_step(off: dict[str, list[tuple[int, Decimal]]]) -> list[str]:
    """Area-years with fewer than six sectors whose published shares do not add up to 100 within rounding."""
    if not off:
        return []
    listed = "; ".join(
        f"{entity} " + ", ".join(f"{year} ({added.normalize():f})" for year, added in sorted(pts))
        for entity, pts in sorted(off.items())
    )
    return [
        "Published as printed, although the shares FAO publishes for these areas and years add up to a little less "
        f"or more than 100 beyond the rounding of their printed values (the sum in brackets): {listed}."
    ]


# --- running -------------------------------------------------------------------------------------------------------


def vintage(files: dict[str, InputFile], data: Input, domain: Domain, data_rows: int) -> tuple[date, str]:
    """(DateUpdate, the processing step stating it) for a domain zip whose CSV has `data_rows` rows."""
    t, c = files[data.key], files[CATALOGUE.key]
    url = str(t.snapshot.url) if t.snapshot.url else ""
    updated, file_rows = catalogue_entry(c.path.read_bytes(), domain.code, url)
    if data_rows != file_rows:
        raise FaostatBulkError(
            f"datasets_E.json says {domain.code} has {file_rows} rows but {domain.data_member} has {data_rows}: the "
            "catalogue describes another file, so its DateUpdate cannot be this file's vintage"
        )
    modified = (
        f" The zip was last modified on the server on {t.snapshot.last_modified}." if t.snapshot.last_modified else ""
    )
    step = (
        f"Read {domain.data_member} from FAOSTAT's {domain.name} ({domain.code}) bulk zip. The vintage is the domain's "
        f"DateUpdate, {updated.day} {updated:%B %Y}, from FAOSTAT's bulk-download catalogue (datasets_E.json), whose "
        f"entry names this zip and gives FileRows {data_rows:,}, the number of data rows in this file.{modified}"
    )
    return updated, step


Compute = Callable[[Table, dict[str, str]], tuple[list[Observation], list[str]]]


def _runner(data: Input, domain: Domain, compute: Compute, changes: str | None):
    def run(files: dict[str, InputFile]) -> Result:
        table, flags = read_zip(files[data.key].path, domain.code)
        updated, vstep = vintage(files, data, domain, table.data_rows)
        obs, steps = compute(table, flags)
        return Result(
            observations=obs,
            vintage=updated.isoformat(),
            year=str(updated.year),
            date_published=updated.isoformat(),
            steps=[vstep, *steps],
            changes=changes,
        )

    return run


# --- what is published ---------------------------------------------------------------------------------------------

GT_TO_GT = "converted from kilotonnes to billion tonnes of CO₂-equivalent."
GT_CO2E = Unit(code="GtCO2e", label="billion tonnes of carbon dioxide equivalent", short="Gt CO₂e")
PERCENT = Unit(code="percent", label="percent", short="%")

GEOGRAPHY = "The world, countries and territories, and the European Union (27)"
WHAT_IS_COUNTED = (
    "FAOSTAT's six IPCC sectors: energy, industrial processes and product use, agriculture, land use, land-use change "
    "and forestry (net: emissions from deforestation, drained organic soils and fires minus the carbon taken up by "
    "existing forests, so it can be negative), waste and other. International aviation and shipping (bunker fuels) "
    "are not included. Agriculture and land use are FAO's own Tier 1 estimates; energy, industry, waste and other are "
    "PRIMAP-hist v2.7 third-party estimates, which count some territories inside their parent country (for example "
    "Bermuda in the United Kingdom, Greenland and the Faroe Islands in Denmark, Palestine in Israel, Puerto Rico in "
    "the United States). So such a parent country's energy, industry, waste and other emissions include those "
    "territories while its agriculture and land use do not, and for 28 territories in the October 2025 release FAO "
    "has no energy, industry, waste or other rows, so their total covers agriculture and land use only. Estimates, "
    "not country inventory submissions."
)
SECTOR_DIM = Dimension(
    id="sector", label="IPCC sector", values=[DimensionValue(id=p.id, label=p.label) for p in SECTORS]
)
GAS_DIM = Dimension(id="gas", label="Gas", values=[DimensionValue(id=g.id, label=g.label) for g in GASES])


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    all_ghg_scope = Scope(
        geography=GEOGRAPHY, gwp="AR5-GWP100", lulucf="included", bunkers="excluded", basis=WHAT_IS_COUNTED
    )
    gt = (TOTALS, CATALOGUE)
    em = (INDICATORS, CATALOGUE)
    return [
        Transform(
            spec=Spec(
                id="ghg.faostat.by-sector",
                title="Greenhouse gas emissions by sector, all gases including land use",
                description="Each year's emissions of all greenhouse gases, in carbon dioxide equivalent, split into "
                "six sectors that do not overlap and add up to the total: energy, industrial processes and product "
                "use, agriculture, land use (net, which can be below zero where forests take up more carbon than "
                "land clearing releases), waste and other, as published by FAO for the world and each country since "
                "1990. Food is not a seventh sector: its emissions run across agriculture, land use, energy, industry "
                "and waste. Where FAO publishes no row for a sector (28 territories in the October 2025 release, "
                "whose energy, industry and waste are counted in their parent country; Tokelau, Nauru and Tuvalu in "
                "part) the sector is left missing, never set to zero. International aviation and shipping are not "
                "included.",
                kind="series",
                unit=GT_CO2E,
                display=Display(decimals=2),
                scope=all_ghg_scope,
                geo_coverage="mixed",
                headline_entity=WORLD,
                dimensions=(SECTOR_DIM,),
                headline_dims=(("sector", "energy"),),
            ),
            inputs=gt,
            run=_runner(TOTALS, GT, by_sector, GT_TO_GT),
            module_file=here,
            validation=Validation(min_rows=30_000, value_range=(-5.0, 60.0)),
        ),
        Transform(
            spec=Spec(
                id="ghg.faostat.total",
                title="Greenhouse gas emissions, all gases and all sectors including land use",
                description="Each year's emissions of all greenhouse gases (carbon dioxide, methane, nitrous oxide and "
                "fluorinated gases) from all sectors, in carbon dioxide equivalent, including net land use, land-use "
                "change and forestry and excluding international aviation and shipping, as published by FAO for the "
                "world and each country since 1990. For 28 territories in the October 2025 release, whose energy, "
                "industry and waste emissions are counted in their parent country, the total covers only agriculture "
                "and land use.",
                kind="series",
                unit=GT_CO2E,
                display=Display(decimals=1),
                scope=all_ghg_scope,
                geo_coverage="mixed",
                headline_entity=WORLD,
            ),
            inputs=gt,
            run=_runner(TOTALS, GT, total, GT_TO_GT),
            module_file=here,
            validation=Validation(min_rows=7_000, value_range=(-5.0, 60.0)),
            checks=(
                PublisherCheck(
                    source_id=SOURCE,
                    vintage=VINTAGE_2023,
                    entity=WORLD,
                    period="2023",
                    stated="52.1",
                    quote="By comparison, global anthropogenic emissions reached 52.1 Gt CO2eq in 2023, the highest "
                    "level on record and a 47 percent increase since 2001.",
                    url=BRIEF_URL,
                ),
            ),
        ),
        Transform(
            spec=Spec(
                id="ghg.faostat.by-gas",
                title="Greenhouse gas emissions by gas, all sectors including land use",
                description="Each year's emissions from all sectors, including net land use and excluding "
                "international aviation and shipping, split by gas: carbon dioxide, methane, nitrous oxide and "
                "fluorinated gases, each in carbon dioxide equivalent (carbon dioxide counts as itself), as published "
                "by FAO for the world and each country since 1990. The four gases add up to the all-gas total. Where "
                "FAO publishes no fluorinated-gas row (67 countries and territories in the October 2025 release) the "
                "gas is left missing, never set to zero.",
                kind="series",
                unit=GT_CO2E,
                display=Display(decimals=2),
                scope=Scope(
                    geography=GEOGRAPHY,
                    gwp="AR5-GWP100",
                    lulucf="included",
                    bunkers="excluded",
                    basis="Carbon dioxide is in tonnes of CO₂, its own CO₂-equivalent (global warming potential 1); "
                    "methane, nitrous oxide and fluorinated gases are FAO's CO₂-equivalents at IPCC AR5 100-year "
                    "global warming potentials (methane 28, nitrous oxide 265). The total split is " + WHAT_IS_COUNTED,
                ),
                geo_coverage="mixed",
                headline_entity=WORLD,
                dimensions=(GAS_DIM,),
                headline_dims=(("gas", "co2"),),
            ),
            inputs=gt,
            run=_runner(TOTALS, GT, by_gas, GT_TO_GT),
            module_file=here,
            validation=Validation(min_rows=25_000, value_range=(-5.0, 60.0)),
        ),
        Transform(
            spec=Spec(
                id="ghg.faostat.per-capita",
                title="Greenhouse gas emissions per person: each country's emissions divided by its population",
                description="Each country's emissions of all greenhouse gases from all sectors on its territory, "
                "including net land use and excluding international aviation and shipping, divided by its population, "
                "in tonnes of carbon dioxide equivalent per person per year, as published by FAO since 1990. This is "
                "a national average where emissions happen, not one person's footprint: it does not follow what "
                "people buy (emissions in imported goods count where they are made) and says nothing about how "
                "emissions differ between people in a country. FAO has no energy row for Mayotte and Tokelau "
                "(October 2025 release), so their values leave energy out.",
                kind="series",
                unit=Unit(
                    code="tCO2e-per-person",
                    label="tonnes of carbon dioxide equivalent per person",
                    short="t CO₂e per person",
                ),
                display=Display(decimals=2),
                scope=Scope(
                    geography=GEOGRAPHY,
                    gwp="AR5-GWP100",
                    lulucf="included",
                    bunkers="excluded",
                    basis='FAO\'s published value of all-sector emissions (FAOSTAT item "All sectors with LULUCF") '
                    "divided by population, territorial (production-based) accounting. " + WHAT_IS_COUNTED,
                ),
                geo_coverage="mixed",
                headline_entity=WORLD,
            ),
            inputs=em,
            run=_runner(INDICATORS, EM, per_capita, None),
            module_file=here,
            validation=Validation(min_rows=6_000, value_range=(-1000.0, 1000.0)),
        ),
        Transform(
            spec=Spec(
                id="food.faostat.agrifood-emissions-world.share",
                title="Agrifood systems' share of global greenhouse gas emissions",
                description="The part of the world's greenhouse gas emissions that comes from food and farming systems "
                "each year since 1990, as published by FAO: FAO's agrifood-systems emissions (on farms, from clearing "
                "land for agriculture, and from making, moving, selling, cooking and throwing away food) as a "
                "percentage of FAO's own total of all sectors, which includes net land use, land-use change and "
                "forestry and excludes international aviation and shipping. Food's emissions run across the "
                "agriculture, land-use, energy, industry and waste sectors; they are not a sector of their own.",
                kind="series",
                unit=Unit(code="percent", label="percent of global greenhouse gas emissions", short="%"),
                display=Display(decimals=1),
                scope=Scope(
                    geography="World",
                    gwp="AR5-GWP100",
                    lulucf="included",
                    bunkers="excluded",
                    basis='FAO\'s published share (FAOSTAT Emissions indicators, item "Agrifood systems", element '
                    '"Emissions Share (CO2eq) (AR5)"). Numerator: emissions within the farm gate, from land-use change '
                    "and from pre- and post-production (fertilizer manufacturing, processing, packaging, transport, "
                    "retail, household consumption and waste disposal); its land-use change counts only what FAO "
                    "attributes to agriculture (deforestation and fires in humid tropical forests and organic soils), "
                    "with the carbon taken up by forests not subtracted. Denominator: FAO's \"All sectors with "
                    'LULUCF" total of the six IPCC sectors, in which land use is net of the forest sink; '
                    "international aviation and shipping bunkers are a separate item and are not in it.",
                ),
                geo_coverage="global-only",
                headline_entity=WORLD,
            ),
            inputs=em,
            run=_runner(INDICATORS, EM, agrifood_share, None),
            module_file=here,
            validation=Validation(min_rows=30, value_range=(10.0, 60.0)),
            checks=tuple(
                PublisherCheck(
                    source_id=SOURCE,
                    vintage=VINTAGE_2023,
                    entity=WORLD,
                    period=period,
                    stated=stated,
                    quote="The share of agrifood systems emissions in global anthropogenic emissions has decreased "
                    "from 38 percent in 2001 to 32 percent in 2023.",
                    url=BRIEF_URL,
                )
                for period, stated in (("2001", "38"), ("2023", "32"))
            ),
        ),
        Transform(
            spec=Spec(
                id="ghg.faostat.ch4-share-by-sector",
                title="Where methane comes from: each sector's share of all methane emissions",
                description="Each sector's methane emissions as a percentage of all methane emitted by the world or "
                "a country in a year, since 1990, as published by FAO, for the six sectors that make up FAO's total: "
                "energy (fossil fuel production and use), industrial processes and product use, agriculture "
                "(livestock, rice, manure), land use (fires), waste and other. Where FAO publishes all six, they add "
                "up to 100. Food systems' methane runs across several of these sectors.",
                kind="series",
                unit=Unit(code="percent", label="percent of all methane emissions", short="%"),
                display=Display(decimals=1),
                scope=Scope(
                    geography=GEOGRAPHY,
                    lulucf="included",
                    bunkers="excluded",
                    basis='FAO\'s published shares (FAOSTAT Emissions indicators, element "Emissions Share (CH4)") '
                    "of methane by mass, so no global warming potential is involved. The whole is FAO's all-sector "
                    'methane ("All sectors with LULUCF"). ' + WHAT_IS_COUNTED,
                ),
                geo_coverage="mixed",
                headline_entity=WORLD,
                dimensions=(SECTOR_DIM,),
                headline_dims=(("sector", "agriculture"),),
            ),
            inputs=em,
            run=_runner(INDICATORS, EM, ch4_share_by_sector, None),
            module_file=here,
            validation=Validation(min_rows=20_000, value_range=(0.0, 100.0)),
        ),
    ]
