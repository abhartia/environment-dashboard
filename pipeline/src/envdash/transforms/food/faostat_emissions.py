"""FAOSTAT Emissions totals (GT): world agrifood-systems emissions, their share of all emissions, and livestock methane.

Input. The GT bulk zip holds Emissions_Totals_E_All_Data_(Normalized).csv (latin-1, CRLF, every field quoted; columns
Area Code, Area Code (M49), Area, Item Code, Item, Element Code, Element, Year Code, Year, Source Code, Source, Unit,
Value, Flag, Note) and a flag codebook, Emissions_Totals_E_Flags.csv. Only rows for Area Code 5000 ("World") and
Source "FAO TIER 1" are used; FAO's "UNFCCC" rows (country inventory submissions) are never mixed in. Items and
elements are matched by code, and the names next to the codes must be the ones below, or the transform stops.

- Agrifood systems (item 6518), Emissions (CO2eq) (AR5) (element 723113): farm gate, land-use change, and pre- and
  post-production emissions in kilotonnes of CO₂-equivalent using the IPCC AR5 100-year global warming potentials.
  Published in billion tonnes (kt / 1,000,000, exact decimal arithmetic).
- Share: item 6518 divided by All sectors with LULUCF (item 6825), same element and year, times 100. FAO's own brief
  states 38 percent for 2001 and 32 percent for 2023; with the without-LULUCF total (item 6829) 2001 would be 38.57
  percent, which FAO would print as 39, so the brief's denominator is the with-LULUCF total. Both items must cover
  exactly the same years.
- Emissions from livestock (item 5085), Emissions (CH4) (element 7225): methane from enteric fermentation and manure
  management (for World 2023 the two items sum to 115,211.2589 kt against this item's 115,211.2600 kt). Published in
  million tonnes of methane (kt / 1,000).

Scope of the share. FAO's denominator "All sectors with LULUCF" (item 6825) equals the sum of items Energy, IPPU,
Waste, Other, IPCC Agriculture and LULUCF, without "International bunkers" (item 6820), and the agrifood item
"Land-use change" (6516) equals Net Forest conversion + Fires in humid tropical forests + Fires in organic soils,
without "Forestland" (6751, the forest sink). Both identities hold in every year of the World FAO TIER 1 rows of the
release of 28 October 2025 (tests/test_faostat_emissions.py, snapshot test), which is what the scope's
bunkers="excluded" and the basis text rely on.

Projections. The file carries 2030 and 2050 rows for some items, flagged F ("Forecast value" in the codebook). Rows
flagged F are not published, and they must come after the last year of measured-based estimates. Every other flag must
be in the codebook; its description is stated in a processing step (one flag for the whole series) or on each
observation (several flags). A non-empty Note is copied to the observation.

Vintage. FAOSTAT's bulk catalogue datasets_E.json gives the domain's DateUpdate (2025-10-28 for the data to 2023) and
FileRows. The zip on the server was re-uploaded later (Last-Modified 6 December 2025), so the date alone does not
identify the bytes: the transform requires the catalogue entry's FileLocation to be the zip's URL and its FileRows to
equal the number of data rows in the CSV, and stops otherwise. The vintage is that DateUpdate (ISO date); its year
fills {year} in FAO's citation.

Publisher checks: the FAO highlight of 29 October 2025 for the release of 28 October 2025 (16.5 Gt, 38 and 32
percent). No FAO statement of world livestock methane in mass units for this release was found (searched 2026-10-04:
the highlight and FAOSTAT Analytical Brief 115 give livestock only as 4.3 Gt CO₂eq, all gases), so that series has
no publisher check.
"""

from __future__ import annotations

import csv
import functools
import io
import json
import zipfile
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, PublisherCheck, Result, Spec, Transform, Validation

SOURCE = "faostat"
TOTALS = Input(SOURCE, "emissions-totals")
CATALOGUE = Input(SOURCE, "datasets-catalogue")
DATA_MEMBER = "Emissions_Totals_E_All_Data_(Normalized).csv"
FLAGS_MEMBER = "Emissions_Totals_E_Flags.csv"
DATASET_CODE = "GT"
COLUMNS = [
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
]
WORLD = ("5000", "World")
WORLD_PREFIX = b'"5000",'
TIER1 = "FAO TIER 1"
UNIT_KT = "kt"
FORECAST = "F"

AGRIFOOD = ("6518", "Agrifood systems")
ALL_WITH_LULUCF = ("6825", "All sectors with LULUCF")
LIVESTOCK = ("5085", "Emissions from livestock")
CO2EQ_AR5 = ("723113", "Emissions (CO2eq) (AR5)")
CH4 = ("7225", "Emissions (CH4)")

HIGHLIGHT_URL = (
    "https://www.fao.org/statistics/highlights-archive/highlights-detail/"
    "greenhouse-gas-emissions-from-agrifood-systems.-global--regional-and-country-trends--2001-2023/en"
)
VINTAGE_2023 = "2025-10-28"


class FaostatFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Scan:
    data_rows: int
    """Every data row in the CSV, for comparison with the catalogue's FileRows."""
    world: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class Point:
    year: int
    value: Decimal
    flag: str
    note: str


def _fields(line: bytes) -> list[str]:
    return next(csv.reader(io.StringIO(line.decode("latin-1"))))


def scan(lines: Iterable[bytes]) -> Scan:
    """Count the data rows and keep the World rows. `lines` is the CSV member, header first."""
    it = iter(lines)
    header = _fields(next(it))
    if header != COLUMNS:
        raise FaostatFormatError(f"{DATA_MEMBER}: columns {header} != expected {COLUMNS}")
    n = 0
    world: list[dict[str, str]] = []
    for line in it:
        n += 1
        # Area Code is the first column and every field is quoted, so the World rows are exactly the lines that start
        # with "5000",. A line that does not start with a quote would break that, so it stops the transform.
        if not line.startswith(b'"'):
            raise FaostatFormatError(f"{DATA_MEMBER}: data row {n} does not start with a quoted Area Code")
        if line.startswith(WORLD_PREFIX):
            f = _fields(line)
            if len(f) != len(COLUMNS):
                raise FaostatFormatError(f"{DATA_MEMBER}: data row {n} has {len(f)} fields, not {len(COLUMNS)}")
            row = dict(zip(COLUMNS, f, strict=True))
            if row["Area"] != WORLD[1]:
                raise FaostatFormatError(f"{DATA_MEMBER}: Area Code {WORLD[0]} is {row['Area']!r}, not {WORLD[1]!r}")
            world.append(row)
    return Scan(n, tuple(world))


def read_flags(raw: bytes) -> dict[str, str]:
    """The flag codebook: {"E": "Estimated value", ...}."""
    rows = list(csv.reader(io.StringIO(raw.decode("latin-1"))))
    if [c.strip() for c in rows[0]] != ["Flag", "Description"]:
        raise FaostatFormatError(f"{FLAGS_MEMBER}: header {rows[0]} is not Flag, Description")
    flags = {r[0].strip(): r[1].strip() for r in rows[1:] if r}
    if flags.get(FORECAST) != "Forecast value":
        raise FaostatFormatError(f"{FLAGS_MEMBER}: flag {FORECAST} is {flags.get(FORECAST)!r}, not 'Forecast value'")
    return flags


def series(s: Scan, item: tuple[str, str], element: tuple[str, str]) -> tuple[list[Point], list[int]]:
    """World, FAO TIER 1 values of one item and element: (estimates by year, forecast years left out)."""
    points: list[Point] = []
    forecast: list[int] = []
    for r in s.world:
        if r["Item Code"] != item[0] or r["Element Code"] != element[0] or r["Source"] != TIER1:
            continue
        if (r["Item"], r["Element"]) != (item[1], element[1]):
            raise FaostatFormatError(
                f"item {item[0]} / element {element[0]} are named {r['Item']!r} / {r['Element']!r}, expected "
                f"{item[1]!r} / {element[1]!r}"
            )
        if r["Unit"] != UNIT_KT:
            raise FaostatFormatError(f"{item[1]} {r['Year']}: unit {r['Unit']!r}, expected {UNIT_KT!r}")
        if r["Year"] != r["Year Code"] or not r["Year"].isdigit() or len(r["Year"]) != 4:
            raise FaostatFormatError(f"{item[1]}: Year {r['Year']!r} / Year Code {r['Year Code']!r} is not one year")
        if r["Value"] == "":
            raise FaostatFormatError(f"{item[1]} {r['Year']}: empty Value; re-read the file before trusting it")
        year = int(r["Year"])
        if r["Flag"] == FORECAST:
            forecast.append(year)
        else:
            points.append(Point(year, Decimal(r["Value"]), r["Flag"], r["Note"]))
    years = [p.year for p in points]
    if not points:
        raise FaostatFormatError(f"no World {TIER1} rows for {item[1]} / {element[1]}")
    if len(set(years)) != len(years):
        raise FaostatFormatError(f"{item[1]} / {element[1]}: more than one World {TIER1} value for a year")
    if forecast and min(forecast) <= max(years):
        raise FaostatFormatError(f"{item[1]}: forecast years {forecast} are not all after {max(years)}")
    return sorted(points, key=lambda p: p.year), sorted(forecast)


def _flag_words(flags: dict[str, str], used: Iterable[str]) -> dict[str, str]:
    out = {}
    for f in sorted(set(used)):
        if f not in flags:
            raise FaostatFormatError(f"flag {f!r} is not in {FLAGS_MEMBER}")
        out[f] = flags[f]
    return out


def _observations(
    pairs: list[tuple[int, Decimal, list[Point]]], flags: dict[str, str]
) -> tuple[list[Observation], str]:
    """(year, value, the points it came from) -> observations, plus the processing step that states the flags."""
    used = _flag_words(flags, (p.flag for _, _, ps in pairs for p in ps))
    single = len(used) == 1
    obs = []
    for year, value, ps in pairs:
        notes = [f"FAO note: {p.note}" for p in ps if p.note]
        if not single:
            notes += [f"FAO flag {p.flag}: {used[p.flag]}." for p in ps]
        obs.append(Observation(entity="WLD", period=f"{year:04d}", value=float(value), note=" ".join(notes) or None))
    counts = Counter(p.flag for _, _, ps in pairs for p in ps)
    if single:
        ((f, words),) = used.items()
        step = f"Every value used carries FAO's flag {f}, which the file's codebook defines as \"{words}\"."
    else:
        listed = "; ".join(f'{f} "{w}" ({counts[f]} values)' for f, w in used.items())
        step = f"The values used carry several FAO flags ({listed}); each observation names its flag in a note."
    return obs, step


def agrifood_total(s: Scan, flags: dict[str, str]) -> tuple[list[Observation], list[str]]:
    pts, forecast = series(s, AGRIFOOD, CO2EQ_AR5)
    million = Decimal(1_000_000)
    obs, flag_step = _observations([(p.year, p.value / million, [p]) for p in pts], flags)
    steps = [
        f'Kept the World (area code 5000), "FAO TIER 1" rows of item "{AGRIFOOD[1]}" (code {AGRIFOOD[0]}), element '
        f'"{CO2EQ_AR5[1]}" (code {CO2EQ_AR5[0]}): one value per year, {pts[0].year}–{pts[-1].year}, in kilotonnes '
        'of CO₂-equivalent (IPCC AR5 100-year global warming potentials). Rows from FAO\'s "UNFCCC" source are not '
        "used.",
        "Converted kilotonnes to billion tonnes by dividing by 1,000,000 (exact decimal arithmetic on the printed "
        "values).",
        flag_step,
        *_forecast_step(forecast),
    ]
    return obs, steps


def agrifood_share(s: Scan, flags: dict[str, str]) -> tuple[list[Observation], list[str]]:
    num, f1 = series(s, AGRIFOOD, CO2EQ_AR5)
    den, f2 = series(s, ALL_WITH_LULUCF, CO2EQ_AR5)
    if [p.year for p in num] != [p.year for p in den]:
        raise FaostatFormatError(
            f"{AGRIFOOD[1]} covers {[p.year for p in num]} but {ALL_WITH_LULUCF[1]} covers {[p.year for p in den]}"
        )
    hundred = Decimal(100)
    obs, flag_step = _observations(
        [(a.year, a.value / b.value * hundred, [a, b]) for a, b in zip(num, den, strict=True)], flags
    )
    steps = [
        f'Kept the World (area code 5000), "FAO TIER 1" rows of element "{CO2EQ_AR5[1]}" (code {CO2EQ_AR5[0]}) for '
        f'items "{AGRIFOOD[1]}" (code {AGRIFOOD[0]}) and "{ALL_WITH_LULUCF[1]}" (code {ALL_WITH_LULUCF[0]}), '
        f"{num[0].year}–{num[-1].year}, in kilotonnes of CO₂-equivalent (IPCC AR5 100-year global warming "
        "potentials). Both items cover the same years.",
        f'Share = "{AGRIFOOD[1]}" divided by "{ALL_WITH_LULUCF[1]}" for the same year, times 100 (exact decimal '
        "arithmetic on the printed values). The denominator is FAO's total of all IPCC sectors including land use, "
        "land-use change and forestry.",
        flag_step,
        *_forecast_step(sorted(set(f1) | set(f2))),
    ]
    return obs, steps


def livestock_ch4(s: Scan, flags: dict[str, str]) -> tuple[list[Observation], list[str]]:
    pts, forecast = series(s, LIVESTOCK, CH4)
    thousand = Decimal(1000)
    obs, flag_step = _observations([(p.year, p.value / thousand, [p]) for p in pts], flags)
    steps = [
        f'Kept the World (area code 5000), "FAO TIER 1" rows of item "{LIVESTOCK[1]}" (code {LIVESTOCK[0]}), element '
        f'"{CH4[1]}" (code {CH4[0]}): methane from enteric fermentation and manure management, one value per year, '
        f"{pts[0].year}–{pts[-1].year}, in kilotonnes of methane.",
        "Converted kilotonnes to million tonnes by dividing by 1,000 (exact decimal arithmetic on the printed values).",
        flag_step,
        *_forecast_step(forecast),
    ]
    return obs, steps


def _forecast_step(years: list[int]) -> list[str]:
    if not years:
        return []
    shown = " and ".join(str(y) for y in years)
    return [f'Left out FAO\'s projections for {shown}, which the file flags F ("Forecast value").']


def catalogue_entry(raw: bytes, url: str) -> tuple[date, int]:
    """(DateUpdate, FileRows) of the GT entry of datasets_E.json, which must name `url` as its file."""
    doc = json.loads(raw.decode("utf-8"))
    entries = [d for d in doc["Datasets"]["Dataset"] if d["DatasetCode"] == DATASET_CODE]
    if len(entries) != 1:
        raise FaostatFormatError(f"datasets_E.json has {len(entries)} entries for {DATASET_CODE}")
    e = entries[0]
    if e["FileLocation"] != url:
        raise FaostatFormatError(f"datasets_E.json gives {DATASET_CODE} at {e['FileLocation']!r}, not {url!r}")
    return date.fromisoformat(e["DateUpdate"][:10]), int(e["FileRows"])


@functools.lru_cache(maxsize=1)
def _read_zip(path: Path) -> tuple[Scan, dict[str, str]]:
    # Snapshot paths are content-addressed (pipeline/.snapshots/<sha256>), so caching by path is caching by content:
    # the three indicators read the same 364 MB member once.
    with zipfile.ZipFile(path) as z:
        with z.open(DATA_MEMBER) as f:
            s = scan(f)
        flags = read_flags(z.read(FLAGS_MEMBER))
    return s, flags


def _runner(compute):
    def run(files: dict[str, InputFile]) -> Result:
        t, c = files[TOTALS.key], files[CATALOGUE.key]
        url = str(t.snapshot.url) if t.snapshot.url else ""
        updated, file_rows = catalogue_entry(c.path.read_bytes(), url)
        s, flags = _read_zip(t.path)
        if s.data_rows != file_rows:
            raise FaostatFormatError(
                f"datasets_E.json says {DATASET_CODE} has {file_rows} rows but {DATA_MEMBER} has {s.data_rows}: the "
                "catalogue describes another file, so its DateUpdate cannot be this file's vintage"
            )
        obs, steps = compute(s, flags)
        modified = (
            f" The zip was last modified on the server on {t.snapshot.last_modified}."
            if t.snapshot.last_modified
            else ""
        )
        return Result(
            observations=obs,
            vintage=updated.isoformat(),
            year=str(updated.year),
            date_published=updated.isoformat(),
            steps=[
                f"Read {DATA_MEMBER} from FAOSTAT's Emissions totals (GT) bulk zip. The vintage is the domain's "
                f"DateUpdate, {updated.day} {updated:%B %Y}, from FAOSTAT's bulk-download catalogue "
                f"(datasets_E.json), whose entry names this zip and gives FileRows {file_rows:,}, the number of data "
                f"rows in this file.{modified}",
                *steps,
            ],
            changes=_CHANGES[compute],
        )

    return run


_CHANGES = {
    agrifood_total: "converted from kilotonnes to billion tonnes of CO₂-equivalent.",
    agrifood_share: "share calculated as agrifood systems emissions divided by all-sector emissions including land "
    "use, land-use change and forestry.",
    livestock_ch4: "converted from kilotonnes to million tonnes of methane.",
}

_AGRIFOOD_BASIS = (
    'FAOSTAT item "Agrifood systems": emissions within the farm gate (crops and livestock), from land-use change, and '
    "from pre- and post-production (fertilizer manufacturing, processing, packaging, transport, retail, household "
    "consumption and waste disposal). Land-use change counts only what FAO attributes to agriculture: its item "
    '"Land-use change" is net forest conversion (deforestation) plus fires in humid tropical forests and fires in '
    'organic soils (peat). The carbon taken up by forests (FAOSTAT item "Forestland", a net removal) is not '
    "subtracted. FAO Tier 1 estimates, not country inventory submissions."
)


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    world_ar5 = Scope(geography="World", gwp="AR5-GWP100", lulucf="included", basis=_AGRIFOOD_BASIS)
    return [
        Transform(
            spec=Spec(
                id="food.faostat.agrifood-emissions-world",
                title="Greenhouse gas emissions from agrifood systems, world",
                description="Greenhouse gas emissions from the world's food and farming systems each year since "
                "1990, in carbon dioxide equivalent: on farms, from clearing land for agriculture, and from making, "
                "moving, selling, cooking and throwing away food, as estimated by FAO.",
                kind="series",
                unit=Unit(
                    code="GtCO2e",
                    label="billion tonnes of carbon dioxide equivalent",
                    short="Gt CO₂e",
                ),
                display=Display(decimals=1),
                scope=world_ar5,
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(TOTALS, CATALOGUE),
            run=_runner(agrifood_total),
            module_file=here,
            validation=Validation(min_rows=30, value_range=(5.0, 30.0)),
            checks=(
                PublisherCheck(
                    source_id=SOURCE,
                    vintage=VINTAGE_2023,
                    entity="WLD",
                    period="2023",
                    stated="16.5",
                    quote="According to the latest data available, global agrifood systems emissions reached 16.5 "
                    "billion tonnes of carbon dioxide equivalent (Gt CO2eq) in 2023, up 21 percent since 2001.",
                    url=HIGHLIGHT_URL,
                ),
            ),
        ),
        Transform(
            spec=Spec(
                id="food.faostat.agrifood-emissions-world.share",
                title="Agrifood systems' share of global greenhouse gas emissions",
                description="The part of the world's greenhouse gas emissions, including land use, land-use change "
                "and forestry, that comes from food and farming systems, each year since 1990, as estimated by FAO.",
                kind="derived",
                unit=Unit(
                    code="percent",
                    label="percent of global greenhouse gas emissions",
                    short="%",
                ),
                display=Display(decimals=1),
                scope=Scope(
                    geography="World",
                    gwp="AR5-GWP100",
                    lulucf="included",
                    bunkers="excluded",
                    basis=_AGRIFOOD_BASIS + ' Denominator: FAOSTAT item "All sectors with LULUCF", the total of all '
                    "IPCC sectors including land use, land-use change and forestry (energy, industrial processes, "
                    "waste, other, agriculture and LULUCF, with the forest sink netted in); international aviation "
                    'and shipping bunkers are a separate FAOSTAT item ("International bunkers") and are not in it.',
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(TOTALS, CATALOGUE),
            run=_runner(agrifood_share),
            module_file=here,
            validation=Validation(min_rows=30, value_range=(10.0, 60.0)),
            checks=tuple(
                PublisherCheck(
                    source_id=SOURCE,
                    vintage=VINTAGE_2023,
                    entity="WLD",
                    period=period,
                    stated=stated,
                    quote="Their share in total emissions fell from 38 to 32 percent in 2023.",
                    url=HIGHLIGHT_URL,
                )
                for period, stated in (("2001", "38"), ("2023", "32"))
            ),
        ),
        Transform(
            spec=Spec(
                id="food.faostat.livestock-ch4-world",
                title="Methane from livestock, world",
                description="Methane released each year since 1961 by the world's farm animals, from digestion "
                "(enteric fermentation) and from manure management, as estimated by FAO.",
                kind="series",
                unit=Unit(code="MtCH4", label="million tonnes of methane", short="Mt CH₄"),
                display=Display(decimals=1),
                scope=Scope(
                    geography="World",
                    basis='FAOSTAT item "Emissions from livestock", element "Emissions (CH4)": methane from enteric '
                    "fermentation and manure management, mass of methane (not CO₂-equivalent). FAO Tier 1 estimates "
                    "(IPCC 2006 Guidelines), not country inventory submissions.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(TOTALS, CATALOGUE),
            run=_runner(livestock_ch4),
            module_file=here,
            validation=Validation(min_rows=60, value_range=(30.0, 200.0)),
        ),
    ]
