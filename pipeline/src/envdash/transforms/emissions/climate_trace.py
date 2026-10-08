"""Where the world's greenhouse gases come from: Climate TRACE's emissions of all greenhouse gases by subsector, and
the same emissions grouped into the five activities of Bill Gates's "How to Avoid a Climate Disaster" (2021): making
things, plugging in, growing things, getting around, and keeping warm and cool (source climate-trace, class open).

Inputs. Climate TRACE Emissions Inventory V5.10.0 (Zenodo record 22919723, 27 August 2026). Each subsector is one zip
of up to 4.9 GB on Zenodo; only its country-level CSV is read, by HTTP Range requests (Artifact.zip_member, see
envdash/zipmember.py): <gas>/DATA/<subsector>_country_emissions_v5_10_0.csv. Columns iso3_country, sector, subsector,
start_time, end_time, gas, emissions_quantity, emissions_quantity_units, temporal_granularity, created_date,
modified_date; one row per code and year, 2015-2026, 252 codes, values in tonnes. The data guide: "If reported quantity
is zero, it means that gas is not emitted. If reported quantity is empty/null/N-A, data is not yet available." The
transform stops on any other header, sector or subsector name, gas, unit, granularity, period shape, duplicate row or
a code set that differs between years.

Which values may be published (the registry entry, pipeline/sources/climate-trace.yaml, holds the evidence):
- Subsectors Climate TRACE models itself, including those whose country totals its methodology builds from EDGAR,
  CEDS or IEA inputs (road transport, both buildings subsectors, heat plants, glass, lime, food, textiles, other
  chemicals, other metals, wood, other mining): Climate TRACE's CC BY 4.0, by the owner's decision of 2026-10-08. The
  co2e_100yr file is read. These are marked IEA_LINEAGE below and in the scope.
- Subsectors Climate TRACE's terms list as FAOSTAT data (enteric fermentation and manure management of other animals,
  other agricultural soil emissions, rice cultivation in some geographies): FAO's CC BY 4.0. co2e_100yr is read.
- Subsectors Climate TRACE's terms (or its data guide) list as EDGAR data: their carbon dioxide is IEA-EDGAR CO2
  (CC BY-NC-ND 4.0, which forbids this regrouping), so it is never fetched. Only their methane and nitrous oxide files
  (EDGAR CH4 and N2O, CC BY 4.0) are read, and converted to CO2-equivalent with the IPCC AR6 100-year global warming
  potentials Climate TRACE uses for that subsector (GWP_CH4 per subsector below: 29.8 for fossil methane, 27.0 for
  methane from waste and crop burning; nitrous oxide 273). The GWPs were read off V5.10.0 itself on 2026-10-08: for
  each of these subsectors, co2e_100yr minus co2 equals ch4 x GWP_CH4 + n2o x 273 in every row to within 1e-15
  relative, and the other AR6 methane value misses by up to 10 percent (research only; the co2 and co2e files of
  these subsectors are not snapshotted), so the values here equal Climate TRACE's own CO2-equivalent minus its CO2.
- Fluorinated gases (EDGAR F-gases, CC BY 4.0, CO2-equivalent only): co2e_100yr is read.
- Other manufacturing is left out entirely: its carbon dioxide is IEA-EDGAR CO2, and its other gases mix EDGAR with
  plant-level reports from the European, US and Israeli pollutant registers whose terms have not been read for the
  Israeli register, so its non-CO2 part cannot be separated by producer.

Entities. ISO 3166 codes through geo.resolve with the source's alias table (XKX Kosovo, ZNC Northern Cyprus). UNK
(Climate TRACE's "unknown" country: vessels whose port is not known) is counted in the world value only. Climate TRACE
publishes no world rows; the world value of a subsector and year is the sum of every one of its 252 country rows, and
is missing if any row is empty, never a partial sum.

Years. 2015-2025. The 2026 rows cover January to June only (V5.10.0 came out on 27 August 2026 with Climate TRACE's
60-day lag), so they are left out. In V5.10.0 every country's 2025 row of removals, net-forest-land, net-shrubgrass and
net-wetland is 0: those land fluxes were not yet estimated for 2025 (V5.11.0 on Climate TRACE's site has values), so
they are treated as missing, never as zero (NOT_ESTIMATED); so is 2015 of net-soil-organic-carbon, a subsector new in
V5.10.0 whose every 2015 row is 0. Any other subsector and year whose every row is 0 stops the transform, so a new
release cannot slip a not-yet-estimated year through as zero. Where every country's value in a year equals the year
before (Climate TRACE carrying an EDGAR or FAOSTAT input forward, e.g. heat plants and other animals' enteric
fermentation in 2024 and 2025), the values are published as given with a note on each.

Activities. MAPPING puts each subsector into one of Gates's five activities or one of three bands that are not one of
the five, with a one-line reason each. It follows how Gates's own shares were built: the book's numbers are Rhodium
Group's, whose five sectors are the same five and whose published grouping (Rhodium, "Global Greenhouse Gas Emissions:
1990-2022 and Preliminary 2023 Estimates", Figure 6) counts fossil fuel production, coal mining and refining under
industry (making things), landfills and waste with agriculture and land use (growing things), refrigerants under
buildings (keeping warm and cool), electricity where it is generated (plugging in), and leaves out forest fires. A
group's value is missing in any year in which any of its member subsectors is missing; it is never a partial sum.

Land use. The five are gross of natural uptake. Growing things includes the land-use emissions people cause:
clearing forest (gross carbon dioxide released), forest degradation, and the net change of carbon in cropland soils
(net-soil-organic-carbon, which is below zero for some countries). Wildfires (forest, shrub and grassland, wetland
fires) are their own band, as Rhodium leaves forest fires out. Carbon taken up by standing forests (removals, below
zero) and the net carbon change of forest, shrub and grassland, and wetland that stays as it is are their own band
("land taking up carbon"), shown beside the five and never netted into them. Methane from reservoirs is a third band.

Shares. Each activity's share is its value divided by the sum of the five in the same entity and year, so the five add
up to 100. The three bands are expressed against that same sum (wildfires as a positive percent, land uptake usually
negative) and are outside the 100. A share is published only where all five activities have values and their sum is
above zero.

Publisher checks: none apply. Climate TRACE states no annual value for V5.10.0: its release note of 27 August 2026
(https://climatetrace.org/news, "Climate TRACE data show marginal increase in global emissions in the first half of
2026") gives only January-June 2026 and June 2026 values, and 2026 is not published here; the full-year 2025 total it
announced earlier belongs to an older version, and its v5.11.0 API values are another vintage. World values are
pinned by regression tests on the snapshots (tests/test_emissions_climate_trace.py).
"""

from __future__ import annotations

import csv
import functools
import io
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

from envdash import geo
from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation


class ClimateTraceError(ValueError):
    pass


SOURCE = "climate-trace"
RELEASE = "5.10.0"
FILE_VERSION = "v5_10_0"
ZENODO_RECORD = "22919723"
DATE_PUBLISHED = "2026-08-27"
"""Zenodo record 22919723, publication_date (read 2026-10-08)."""
YEARS = range(2015, 2026)
PARTIAL_YEAR = 2026
FILE_YEARS = frozenset(range(2015, 2027))
WORLD = "WLD"
WORLD_ONLY = frozenset({"UNK"})
"""Climate TRACE codes counted in the world value and published under no entity."""
EXPECTED_CODES = 252

COLUMNS = (
    "iso3_country",
    "sector",
    "subsector",
    "start_time",
    "end_time",
    "gas",
    "emissions_quantity",
    "emissions_quantity_units",
    "temporal_granularity",
    "created_date",
    "modified_date",
)
UNIT_TONNES = "tonnes"
ANNUAL = "annual"
CO2E = "co2e_100yr"
CH4 = "ch4"
N2O = "n2o"
GWP_N2O = Decimal(273)
GWP_CH4_FOSSIL = Decimal("29.8")
GWP_CH4_NON_FOSSIL = Decimal("27.0")
MILLION = Decimal(1_000_000)

Basis = Literal["ct", "ct-iea", "ct-faostat", "faostat", "edgar-non-co2", "edgar-fgas"]

SECTORS: dict[str, str] = {
    "power": "Power",
    "manufacturing": "Manufacturing",
    "mineral-extraction": "Mineral extraction",
    "fossil-fuel-operations": "Fossil fuel operations",
    "transportation": "Transportation",
    "buildings": "Buildings",
    "agriculture": "Agriculture",
    "waste": "Waste",
    "fluorinated-gases": "Fluorinated gases",
    "forestry-and-land-use": "Forestry and land use",
}

ACTIVITIES: dict[str, str] = {
    "making-things": "Making things",
    "plugging-in": "Plugging in",
    "growing-things": "Growing things",
    "getting-around": "Getting around",
    "keeping-warm-and-cool": "Keeping warm and cool",
}
BANDS: dict[str, str] = {
    "wildfires": "Not one of the five: wildfires",
    "land-uptake": "Not one of the five: land taking up carbon",
    "reservoirs": "Not one of the five: reservoirs",
}
GROUPS: dict[str, str] = {**ACTIVITIES, **BANDS}


@dataclass(frozen=True)
class Sub:
    slug: str
    """Climate TRACE's subsector id, as in the file."""
    sector: str
    label: str
    basis: Basis
    group: str
    """An ACTIVITIES or BANDS key."""
    reason: str
    gwp_ch4: Decimal | None = None
    """edgar-non-co2 only: the CH4 GWP Climate TRACE applies to this subsector."""

    @property
    def zip_name(self) -> str:
        if self.sector == "fluorinated-gases":
            return "fluorinated_gases.zip"
        return f"{self.sector.replace('-', '_')}_{self.slug}.zip"

    @property
    def gases(self) -> tuple[str, ...]:
        return (CH4, N2O) if self.basis == "edgar-non-co2" else (CO2E,)

    def artifact(self, gas: str) -> str:
        return self.slug if gas == CO2E else f"{self.slug}-{gas}"

    def member(self, gas: str) -> str:
        return f"{gas}/DATA/{self.slug}_country_emissions_{FILE_VERSION}.csv"

    @property
    def inputs(self) -> tuple[Input, ...]:
        return tuple(Input(SOURCE, self.artifact(g)) for g in self.gases)

    @property
    def published_label(self) -> str:
        return f"{self.label} (methane and nitrous oxide only)" if self.basis == "edgar-non-co2" else self.label


def _s(slug, sector, label, basis, group, reason, gwp_ch4=None) -> Sub:  # type: ignore[no-untyped-def]
    return Sub(slug, sector, label, basis, group, reason, gwp_ch4)


F, NF = GWP_CH4_FOSSIL, GWP_CH4_NON_FOSSIL
MAPPING: tuple[Sub, ...] = (
    # power
    _s(
        "electricity-generation",
        "power",
        "Electricity generation",
        "ct",
        "plugging-in",
        "Power plants making electricity.",
    ),
    _s(
        "heat-plants",
        "power",
        "Heat plants",
        "ct-iea",
        "plugging-in",
        "District heat plants; IPCC and Rhodium count heat with electricity.",
    ),
    _s(
        "other-energy-use",
        "power",
        "Other energy use",
        "edgar-non-co2",
        "plugging-in",
        "EDGAR's other energy industries; Rhodium counts it with electricity.",
        F,
    ),
    # manufacturing
    _s("aluminum", "manufacturing", "Aluminium", "ct", "making-things", "Aluminium smelting."),
    _s("cement", "manufacturing", "Cement", "ct", "making-things", "Cement."),
    _s("chemicals", "manufacturing", "Chemicals", "ct", "making-things", "Ammonia, methanol and soda ash plants."),
    _s(
        "food-beverage-tobacco",
        "manufacturing",
        "Food, beverage and tobacco",
        "ct-iea",
        "making-things",
        "Food and drink factories.",
    ),
    _s("glass", "manufacturing", "Glass", "ct-iea", "making-things", "Glass."),
    _s("iron-and-steel", "manufacturing", "Iron and steel", "ct", "making-things", "Steel."),
    _s("lime", "manufacturing", "Lime", "ct-iea", "making-things", "Lime."),
    _s("other-chemicals", "manufacturing", "Other chemicals", "ct-iea", "making-things", "Other chemical industry."),
    _s(
        "other-metals",
        "manufacturing",
        "Other metals",
        "ct-iea",
        "making-things",
        "Metals other than iron, steel and aluminium.",
    ),
    _s(
        "petrochemical-steam-cracking",
        "manufacturing",
        "Petrochemical steam cracking",
        "ct",
        "making-things",
        "Ethylene and other plastic feedstocks.",
    ),
    _s("pulp-and-paper", "manufacturing", "Pulp and paper", "ct", "making-things", "Paper."),
    _s(
        "textiles-leather-apparel",
        "manufacturing",
        "Textiles, leather and apparel",
        "ct-iea",
        "making-things",
        "Textiles and clothing.",
    ),
    _s(
        "wood-and-wood-products",
        "manufacturing",
        "Wood and wood products",
        "ct-iea",
        "making-things",
        "Sawmills and wood products.",
    ),
    # mineral extraction
    _s("bauxite-mining", "mineral-extraction", "Bauxite mining", "ct", "making-things", "Mining the ore of aluminium."),
    _s("copper-mining", "mineral-extraction", "Copper mining", "ct", "making-things", "Mining copper ore."),
    _s("iron-mining", "mineral-extraction", "Iron mining", "ct", "making-things", "Mining iron ore for steel."),
    _s(
        "other-mining-quarrying",
        "mineral-extraction",
        "Other mining and quarrying",
        "ct-iea",
        "making-things",
        "Other mines and quarries.",
    ),
    _s(
        "rock-quarrying", "mineral-extraction", "Rock quarrying", "ct", "making-things", "Quarrying stone for building."
    ),
    _s(
        "sand-quarrying",
        "mineral-extraction",
        "Sand quarrying",
        "ct",
        "making-things",
        "Quarrying sand for concrete and glass.",
    ),
    # fossil fuel operations: Rhodium counts fuel supply under industry
    _s(
        "coal-mining",
        "fossil-fuel-operations",
        "Coal mining",
        "ct",
        "making-things",
        "Methane from coal mines; Rhodium counts fuel supply under industry.",
    ),
    _s(
        "oil-and-gas-production",
        "fossil-fuel-operations",
        "Oil and gas production",
        "ct",
        "making-things",
        "Venting, flaring, leaks and fuel use at oil and gas fields; fuel supply.",
    ),
    _s(
        "oil-and-gas-refining",
        "fossil-fuel-operations",
        "Oil and gas refining",
        "ct",
        "making-things",
        "Refineries; Rhodium counts refining under industry.",
    ),
    _s(
        "oil-and-gas-transport",
        "fossil-fuel-operations",
        "Oil and gas transport",
        "ct",
        "making-things",
        "Pipelines and liquefied gas; fuel supply.",
    ),
    _s(
        "other-fossil-fuel-operations",
        "fossil-fuel-operations",
        "Other fossil fuel operations",
        "edgar-non-co2",
        "making-things",
        "EDGAR's other fuel supply.",
        F,
    ),
    _s(
        "other-solid-fuels",
        "fossil-fuel-operations",
        "Other solid fuels",
        "edgar-non-co2",
        "making-things",
        "Coke ovens, charcoal and other solid-fuel making; fuel supply.",
        F,
    ),
    # transportation
    _s("domestic-aviation", "transportation", "Domestic aviation", "ct", "getting-around", "Flights within a country."),
    _s("domestic-shipping", "transportation", "Domestic shipping", "ct", "getting-around", "Ships within a country."),
    _s(
        "international-aviation",
        "transportation",
        "International aviation",
        "ct",
        "getting-around",
        "Flights between countries, counted in the country of departure.",
    ),
    _s(
        "international-shipping",
        "transportation",
        "International shipping",
        "ct",
        "getting-around",
        "Ships between countries.",
    ),
    _s(
        "non-broadcasting-vessels",
        "transportation",
        "Non-broadcasting vessels",
        "ct",
        "getting-around",
        "Ships without transponders, seen by radar satellites.",
    ),
    _s(
        "other-transport",
        "transportation",
        "Other transport",
        "edgar-non-co2",
        "getting-around",
        "EDGAR's other transport, such as pipelines and off-road vehicles.",
        F,
    ),
    _s("railways", "transportation", "Railways", "edgar-non-co2", "getting-around", "Trains.", F),
    _s(
        "road-transportation",
        "transportation",
        "Road transportation",
        "ct-iea",
        "getting-around",
        "Cars, trucks and buses.",
    ),
    # buildings
    _s(
        "non-residential-onsite-fuel-usage",
        "buildings",
        "Non-residential onsite fuel usage",
        "ct-iea",
        "keeping-warm-and-cool",
        "Fuel burned in offices, shops and public buildings.",
    ),
    _s(
        "other-onsite-fuel-usage",
        "buildings",
        "Other onsite fuel usage",
        "edgar-non-co2",
        "keeping-warm-and-cool",
        "EDGAR's other fuel use in buildings and farms; Rhodium counts it with buildings.",
        F,
    ),
    _s(
        "residential-onsite-fuel-usage",
        "buildings",
        "Residential onsite fuel usage",
        "ct-iea",
        "keeping-warm-and-cool",
        "Fuel burned in homes for heat, hot water and cooking.",
    ),
    _s(
        "fluorinated-gases",
        "fluorinated-gases",
        "Fluorinated gases",
        "edgar-fgas",
        "keeping-warm-and-cool",
        "Refrigerants and other fluorinated gases; Rhodium counts refrigerants under buildings.",
    ),
    # agriculture
    _s("crop-residues", "agriculture", "Crop residues", "ct", "growing-things", "Crop residues left on fields."),
    _s(
        "cropland-fires",
        "agriculture",
        "Cropland fires",
        "edgar-non-co2",
        "growing-things",
        "Burning crop residues in fields.",
        NF,
    ),
    _s(
        "enteric-fermentation-cattle-operation",
        "agriculture",
        "Enteric fermentation, cattle operations",
        "ct",
        "growing-things",
        "Methane from cattle in feedlots.",
    ),
    _s(
        "enteric-fermentation-cattle-pasture",
        "agriculture",
        "Enteric fermentation, cattle pasture",
        "ct",
        "growing-things",
        "Methane from grazing cattle.",
    ),
    _s(
        "enteric-fermentation-other",
        "agriculture",
        "Enteric fermentation, other animals",
        "faostat",
        "growing-things",
        "Methane from other livestock.",
    ),
    _s(
        "manure-applied-to-soils",
        "agriculture",
        "Manure applied to soils",
        "ct",
        "growing-things",
        "Manure spread on fields.",
    ),
    _s(
        "manure-left-on-pasture-cattle",
        "agriculture",
        "Manure left on pasture, cattle",
        "ct",
        "growing-things",
        "Cattle dung on pasture.",
    ),
    _s(
        "manure-management-cattle-operation",
        "agriculture",
        "Manure management, cattle operations",
        "ct",
        "growing-things",
        "Cattle manure stored at feedlots.",
    ),
    _s(
        "manure-management-other",
        "agriculture",
        "Manure management, other animals",
        "faostat",
        "growing-things",
        "Manure of other livestock.",
    ),
    _s(
        "other-agricultural-soil-emissions",
        "agriculture",
        "Other agricultural soil emissions",
        "faostat",
        "growing-things",
        "Farmed soils, including drained organic soils.",
    ),
    _s(
        "rice-cultivation",
        "agriculture",
        "Rice cultivation",
        "ct-faostat",
        "growing-things",
        "Methane from flooded rice fields.",
    ),
    _s(
        "synthetic-fertilizer-application",
        "agriculture",
        "Synthetic fertilizer application",
        "ct",
        "growing-things",
        "Nitrous oxide from fertiliser.",
    ),
    # waste: Rhodium groups landfills and waste with agriculture and land use
    _s(
        "biological-treatment-of-solid-waste-and-biogenic",
        "waste",
        "Biological treatment of solid waste",
        "edgar-non-co2",
        "growing-things",
        "Composting and digestion; Rhodium groups waste with agriculture.",
        NF,
    ),
    _s(
        "domestic-wastewater-treatment-and-discharge",
        "waste",
        "Domestic wastewater treatment and discharge",
        "ct",
        "growing-things",
        "Sewage; Rhodium groups waste with agriculture.",
    ),
    _s(
        "incineration-and-open-burning-of-waste",
        "waste",
        "Incineration and open burning of waste",
        "edgar-non-co2",
        "growing-things",
        "Burning waste; Rhodium groups waste with agriculture.",
        NF,
    ),
    _s(
        "industrial-wastewater-treatment-and-discharge",
        "waste",
        "Industrial wastewater treatment and discharge",
        "ct",
        "growing-things",
        "Factory wastewater; Rhodium groups waste with agriculture.",
    ),
    _s(
        "solid-waste-disposal",
        "waste",
        "Solid waste disposal",
        "edgar-non-co2",
        "growing-things",
        "Landfill methane; Rhodium groups landfills with agriculture.",
        NF,
    ),
    # forestry and land use
    _s(
        "forest-land-clearing",
        "forestry-and-land-use",
        "Forest land clearing",
        "ct",
        "growing-things",
        "Clearing forest, mostly for farming; gross carbon released.",
    ),
    _s(
        "forest-land-degradation",
        "forestry-and-land-use",
        "Forest land degradation",
        "ct",
        "growing-things",
        "Logging and thinning forests.",
    ),
    _s(
        "net-soil-organic-carbon",
        "forestry-and-land-use",
        "Net soil organic carbon",
        "ct",
        "growing-things",
        "Carbon lost or gained by cropland soils (net).",
    ),
    _s(
        "forest-land-fires",
        "forestry-and-land-use",
        "Forest land fires",
        "ct",
        "wildfires",
        "Forest fires; Rhodium leaves them out.",
    ),
    _s(
        "shrubgrass-fires",
        "forestry-and-land-use",
        "Shrub and grass fires",
        "ct",
        "wildfires",
        "Grassland and savanna fires; as forest fires.",
    ),
    _s(
        "wetland-fires",
        "forestry-and-land-use",
        "Wetland fires",
        "ct",
        "wildfires",
        "Wetland and peat fires; as forest fires.",
    ),
    _s(
        "removals",
        "forestry-and-land-use",
        "Removals",
        "ct",
        "land-uptake",
        "Carbon taken up by standing forests; a sink, not an activity.",
    ),
    _s(
        "net-forest-land",
        "forestry-and-land-use",
        "Net forest land",
        "ct",
        "land-uptake",
        "Net carbon change of forest that stays forest.",
    ),
    _s(
        "net-shrubgrass",
        "forestry-and-land-use",
        "Net shrub and grass land",
        "ct",
        "land-uptake",
        "Net carbon change of shrub and grassland that stays so.",
    ),
    _s(
        "net-wetland",
        "forestry-and-land-use",
        "Net wetland",
        "ct",
        "land-uptake",
        "Net carbon change of wetland that stays wetland.",
    ),
    _s(
        "water-reservoirs",
        "forestry-and-land-use",
        "Water reservoirs",
        "ct",
        "reservoirs",
        "Methane from dam reservoirs for power, water and irrigation alike.",
    ),
)

EXCLUDED: dict[str, str] = {
    "other-manufacturing": "Its carbon dioxide is IEA-EDGAR CO2 (CC BY-NC-ND 4.0) and its other gases mix EDGAR with "
    "plant reports from the European, US and Israeli pollutant registers, so they cannot be separated by producer.",
}
"""Climate TRACE subsectors not read at all."""

IEA_LINEAGE = frozenset(s.slug for s in MAPPING if s.basis == "ct-iea")
NOT_ESTIMATED: dict[str, tuple[int, ...]] = {
    # net-soil-organic-carbon is new in V5.10.0; every country's 2015 row is 0, as in the land rows above.
    "net-soil-organic-carbon": (2015,),
    "removals": (2025,),
    "net-forest-land": (2025,),
    "net-shrubgrass": (2025,),
    "net-wetland": (2025,),
}
"""Subsector years whose every row V5.10.0 writes as 0 although they are not estimated yet."""
NET_SUBSECTORS = frozenset({"removals", "net-forest-land", "net-shrubgrass", "net-wetland", "net-soil-organic-carbon"})
"""The only subsectors whose values may be below zero; a negative value anywhere else stops the transform."""


# --- reading -------------------------------------------------------------------------------------------------------


Key = tuple[str, int]
"""(Climate TRACE code, year)"""


@dataclass(frozen=True)
class CountryFile:
    values: dict[Key, Decimal | None]
    """Tonnes; None where Climate TRACE leaves the quantity empty."""
    codes: frozenset[str]


def read_country_file(data: bytes, sub: Sub, gas: str, *, expected_codes: int = EXPECTED_CODES) -> CountryFile:
    """One country CSV, checked. expected_codes is the number of codes every year must have (252 in V5.10.0)."""
    what = sub.member(gas)
    reader = csv.reader(io.StringIO(data.decode("utf-8")))
    header = tuple(next(reader))
    if header != COLUMNS:
        raise ClimateTraceError(f"{what}: columns {list(header)} != {list(COLUMNS)}")
    values: dict[Key, Decimal | None] = {}
    for n, row in enumerate(reader, start=1):
        if len(row) != len(COLUMNS):
            raise ClimateTraceError(f"{what}: row {n} has {len(row)} fields")
        r = dict(zip(COLUMNS, row, strict=True))
        if (r["sector"], r["subsector"], r["gas"]) != (sub.sector, sub.slug, gas):
            raise ClimateTraceError(f"{what}: row {n} is {r['sector']}/{r['subsector']}/{r['gas']}")
        if r["emissions_quantity_units"] != UNIT_TONNES or r["temporal_granularity"] != ANNUAL:
            raise ClimateTraceError(
                f"{what}: row {n} unit {r['emissions_quantity_units']!r} / {r['temporal_granularity']!r}"
            )
        year = int(r["start_time"][:4])
        if (r["start_time"], r["end_time"]) != (f"{year}-01-01 00:00:00", f"{year}-12-31 00:00:00"):
            raise ClimateTraceError(f"{what}: row {n} covers {r['start_time']} to {r['end_time']}, not one year")
        k = (r["iso3_country"], year)
        if k in values:
            raise ClimateTraceError(f"{what}: two rows for {k}")
        q = r["emissions_quantity"]
        v = Decimal(q) if q != "" else None
        if v is not None and v < 0 and sub.slug not in NET_SUBSECTORS:
            raise ClimateTraceError(f"{what}: {k} is {q}, below zero in a subsector that is not a net flux")
        values[k] = v
    years = {y for _, y in values}
    if years != FILE_YEARS:
        raise ClimateTraceError(f"{what}: years {sorted(years)} != {sorted(FILE_YEARS)}")
    codes = frozenset(c for c, _ in values)
    if len(codes) != expected_codes or len(values) != len(codes) * len(FILE_YEARS):
        raise ClimateTraceError(f"{what}: {len(codes)} codes and {len(values)} rows; every code needs every year")
    return CountryFile(values, codes)


@dataclass(frozen=True)
class SubSeries:
    """One subsector's CO2-equivalent tonnes by (code, year), 2015-2025, with why a value is missing."""

    sub: Sub
    tonnes: dict[Key, Decimal | None]
    missing: dict[Key, str]
    codes: frozenset[str]
    repeated: tuple[int, ...]
    """Years whose every country value equals the year before (Climate TRACE carrying an input forward)."""


NOT_ESTIMATED_WORDS = "Climate TRACE V{release} writes 0 for every country in {year}: not yet estimated, so missing"


def _check_not_estimated(
    sub: Sub, tonnes: dict[Key, Decimal | None], codes: frozenset[str], *, full_release: bool = True
) -> dict[Key, str]:
    """{key: why missing} for the declared not-estimated years; any other year whose every country is 0 stops. On a
    slice of the codes (tests: full_release=False) a year of zeros is ordinary, so only the declared years apply."""
    out: dict[Key, str] = {}
    declared = NOT_ESTIMATED.get(sub.slug, ())
    for year in YEARS:
        all_zero = all(tonnes[(c, year)] is not None and tonnes[(c, year)] == 0 for c in codes)
        if year in declared:
            if not all_zero:
                raise ClimateTraceError(
                    f"{sub.slug} {year} is declared not estimated (every row 0) but has other values: re-read the "
                    "release and update NOT_ESTIMATED"
                )
            for c in codes:
                out[(c, year)] = NOT_ESTIMATED_WORDS.format(release=RELEASE, year=year)
        elif all_zero and full_release:
            raise ClimateTraceError(
                f"{sub.slug} {year}: every country is 0, which in this release means not yet estimated; declare it "
                "in NOT_ESTIMATED after checking, never publish it as zero"
            )
    return out


def subsector_series(
    sub: Sub, files: dict[str, bytes], *, expected_codes: int = EXPECTED_CODES, full_release: bool | None = None
) -> SubSeries:
    """files: {gas: country CSV bytes}. full_release defaults to whether all EXPECTED_CODES codes are expected."""
    if full_release is None:
        full_release = expected_codes == EXPECTED_CODES
    read = {g: read_country_file(files[g], sub, g, expected_codes=expected_codes) for g in sub.gases}
    codes = {f.codes for f in read.values()}
    if len(codes) != 1:
        raise ClimateTraceError(f"{sub.slug}: the gas files list different codes")
    code_set = codes.pop()
    tonnes: dict[Key, Decimal | None] = {}
    missing: dict[Key, str] = {}
    for c in code_set:
        for y in YEARS:
            k = (c, y)
            if sub.basis == "edgar-non-co2":
                ch4, n2o = read[CH4].values[k], read[N2O].values[k]
                if ch4 is None or n2o is None:
                    tonnes[k], missing[k] = None, "Climate TRACE leaves the methane or nitrous oxide empty"
                    continue
                assert sub.gwp_ch4 is not None
                tonnes[k] = ch4 * sub.gwp_ch4 + n2o * GWP_N2O
            else:
                v = read[CO2E].values[k]
                if v is None:
                    missing[k] = "Climate TRACE leaves the value empty (not yet available)"
                tonnes[k] = v
    for k, why in _check_not_estimated(sub, tonnes, code_set, full_release=full_release).items():
        tonnes[k], missing[k] = None, why
    repeated = tuple(
        y
        for y in YEARS[1:]
        if all(tonnes[(c, y)] is not None and tonnes[(c, y)] == tonnes[(c, y - 1)] for c in code_set)
    )
    return SubSeries(sub, tonnes, missing, code_set, repeated)


@functools.lru_cache(maxsize=1)
def _load(paths_key: tuple[tuple[str, str], ...]) -> tuple[SubSeries, ...]:
    # Snapshot paths are content-addressed, so the three indicators read and check each file once per build.
    by_art = dict(paths_key)
    out = []
    for sub in MAPPING:
        files = {g: Path(by_art[f"{SOURCE}/{sub.artifact(g)}"]).read_bytes() for g in sub.gases}
        out.append(subsector_series(sub, files))
    return tuple(out)


def load(files: dict[str, InputFile]) -> tuple[SubSeries, ...]:
    for sub in MAPPING:
        for g in sub.gases:
            snap = files[f"{SOURCE}/{sub.artifact(g)}"].snapshot
            expected = f"https://zenodo.org/api/records/{ZENODO_RECORD}/files/{sub.zip_name}/content"
            if str(snap.url) != expected or snap.zip_member != sub.member(g):
                raise ClimateTraceError(
                    f"{sub.artifact(g)}: snapshot is {snap.url} member {snap.zip_member}, expected {expected} member "
                    f"{sub.member(g)} (release {RELEASE})"
                )
    return _load(tuple(sorted((k, str(f.path)) for k, f in files.items())))


# --- entities and totals -------------------------------------------------------------------------------------------


def entity_of(code: str) -> str | None:
    """Our entity for a Climate TRACE code; None for the world-only codes."""
    if code in WORLD_ONLY:
        return None
    return geo.resolve(code, SOURCE)


def tonnes_by_entity(s: SubSeries) -> dict[tuple[str, int], tuple[Decimal | None, str | None]]:
    """{(entity, year): (tonnes or None, why missing)}, the world value included."""
    out: dict[tuple[str, int], tuple[Decimal | None, str | None]] = {}
    for c in sorted(s.codes):
        e = entity_of(c)
        if e is None:
            continue
        for y in YEARS:
            out[(e, y)] = (s.tonnes[(c, y)], s.missing.get((c, y)))
    for y in YEARS:
        empty = sorted(c for c in s.codes if s.tonnes[(c, y)] is None)
        if empty:
            reasons = {s.missing[(c, y)] for c in empty}
            why = (
                next(iter(reasons))
                if len(empty) == len(s.codes) and len(reasons) == 1
                else f"no world value: {len(empty)} country rows are missing ({', '.join(empty[:5])}…), and a "
                "partial sum is never published"
            )
            out[(WORLD, y)] = (None, why)
        else:
            out[(WORLD, y)] = (sum((s.tonnes[(c, y)] for c in s.codes), Decimal(0)), None)  # type: ignore[misc]
    return out


def group_tonnes(series: Iterable[SubSeries]) -> dict[str, dict[tuple[str, int], tuple[Decimal | None, str | None]]]:
    """{group: {(entity, year): (tonnes, why missing)}}: the sum of the group's subsectors; None if any is missing."""
    members: dict[str, list[dict]] = defaultdict(list)
    for s in series:
        members[s.sub.group].append({"slug": s.sub.slug, "values": tonnes_by_entity(s)})
    out: dict[str, dict[tuple[str, int], tuple[Decimal | None, str | None]]] = {}
    for g in GROUPS:
        keys = set().union(*(m["values"] for m in members[g]))
        vals: dict[tuple[str, int], tuple[Decimal | None, str | None]] = {}
        for k in sorted(keys):
            parts = [(m["slug"], m["values"][k]) for m in members[g]]
            gaps = [slug for slug, (v, _) in parts if v is None]
            if gaps:
                vals[k] = (None, f"no value for {', '.join(gaps)} in this year, and a partial sum is never published")
            else:
                vals[k] = (sum((v for _, (v, _) in parts), Decimal(0)), None)  # type: ignore[misc]
        out[g] = vals
    return out


def _obs(
    entity: str, year: int, value: Decimal | None, why: str | None, dims: dict[str, str], note: str | None = None
) -> Observation:
    return Observation(
        entity=entity,
        period=f"{year:04d}",
        value=float(value) if value is not None else None,
        missing_reason=why if value is None else None,
        note=note if value is not None else None,
        dims=dims,
    )


REPEATED_NOTE = "Climate TRACE repeats the previous year's value for every country in this year."


def _entity_order(keys: Iterable[tuple[str, int]]) -> list[str]:
    ents = sorted({e for e, _ in keys} - {WORLD})
    return [WORLD, *ents]


# --- the three indicators ------------------------------------------------------------------------------------------


def by_subsector(series: tuple[SubSeries, ...]) -> tuple[list[Observation], list[str]]:
    obs: list[Observation] = []
    per = [(s, tonnes_by_entity(s)) for s in series]
    # The world only: every country's subsectors make a file too large to serve (over 20 MiB as CSV); countries'
    # activity totals are published in by-activity.
    for e in [WORLD]:
        for s, vals in per:
            # The activity each subsector is grouped into for ghg.climate-trace.by-activity, so that grouping is
            # published with the values and nothing downstream has to repeat it.
            dims = {"sector": s.sub.sector, "subsector": s.sub.slug, "activity": s.sub.group}
            for y in YEARS:
                v, why = vals[(e, y)]
                note = REPEATED_NOTE if y in s.repeated else None
                obs.append(_obs(e, y, v / MILLION if v is not None else None, why, dims, note))
    return obs, [
        *_common_steps(series),
        "Converted tonnes to million tonnes by dividing by 1,000,000 (exact decimal arithmetic on the printed values).",
    ]


def by_activity(series: tuple[SubSeries, ...]) -> tuple[list[Observation], list[str]]:
    groups = group_tonnes(series)
    entities = _entity_order(groups["making-things"])
    obs = [
        _obs(e, y, v / MILLION if v is not None else None, why, {"activity": g})
        for e in entities
        for g in GROUPS
        for y in YEARS
        for v, why in [groups[g][(e, y)]]
    ]
    return obs, _common_steps(series) + _group_steps() + [
        "Converted tonnes to million tonnes by dividing by 1,000,000 (exact decimal arithmetic)."
    ]


def five_total(series: tuple[SubSeries, ...]) -> tuple[list[Observation], list[str]]:
    """The five activities together: the total each share in by-activity-share is a percentage of."""
    groups = group_tonnes(series)
    entities = _entity_order(groups["making-things"])
    obs: list[Observation] = []
    for e in entities:
        for y in YEARS:
            parts = [(a, groups[a][(e, y)][0]) for a in ACTIVITIES]
            gaps = [ACTIVITIES[a].lower() for a, v in parts if v is None]
            if gaps:
                why = f"no value for {', '.join(gaps)} in this year, and a partial sum is never published"
                obs.append(_obs(e, y, None, why, {}))
            else:
                obs.append(_obs(e, y, sum((v for _, v in parts), Decimal(0)) / MILLION, None, {}))  # type: ignore[misc]
    return obs, _common_steps(series) + _group_steps() + [
        "Added the five activities (making things, plugging in, growing things, getting around, keeping warm and "
        "cool) in the same place and year; missing where any of the five is missing. Wildfires, land taking up carbon "
        "and reservoirs are not included. Converted tonnes to million tonnes by dividing by 1,000,000 (exact decimal "
        "arithmetic)."
    ]


def by_activity_share(series: tuple[SubSeries, ...]) -> tuple[list[Observation], list[str]]:
    groups = group_tonnes(series)
    entities = _entity_order(groups["making-things"])
    obs: list[Observation] = []
    not_positive: list[str] = []
    for e in entities:
        for g in GROUPS:
            for y in YEARS:
                five = [groups[a][(e, y)][0] for a in ACTIVITIES]
                v = groups[g][(e, y)][0]
                if any(x is None for x in five):
                    obs.append(_obs(e, y, None, "not all five activities have a value in this year", {"activity": g}))
                    continue
                total = sum(five, Decimal(0))  # type: ignore[arg-type]
                if total <= 0:
                    if g == "making-things":
                        not_positive.append(f"{e} {y}")
                    obs.append(_obs(e, y, None, "the five activities add up to zero or less", {"activity": g}))
                    continue
                if v is None:
                    obs.append(_obs(e, y, None, groups[g][(e, y)][1], {"activity": g}))
                    continue
                obs.append(_obs(e, y, v * 100 / total, None, {"activity": g}))
    steps = _common_steps(series) + _group_steps()
    steps.append(
        "Divided each activity's value by the sum of the five activities in the same place and year and multiplied by "
        "100, so the five shares add up to 100. The three bands that are not one of the five (wildfires, land taking "
        "up carbon, reservoirs) are divided by the same sum: they are shown against the five and are not part of the "
        "100. Shares are left missing where any of the five is missing, or where the five add up to zero or less"
        + (f" ({len(not_positive)} place-years: {', '.join(not_positive[:20])})." if not_positive else " (none here).")
    )
    return obs, steps


def _common_steps(series: tuple[SubSeries, ...]) -> list[str]:
    by_basis: dict[str, list[str]] = defaultdict(list)
    for s in series:
        by_basis[s.sub.basis].append(s.sub.slug)
    gwp = defaultdict(list)
    for s in series:
        if s.sub.basis == "edgar-non-co2":
            gwp[str(s.sub.gwp_ch4)].append(s.sub.slug)
    missing_counts = sum(1 for s in series for k in s.missing)
    return [
        f"Read the country-level CSV of each of {len(series)} subsectors of Climate TRACE Emissions Inventory "
        f"V{RELEASE} (Zenodo record {ZENODO_RECORD}), by HTTP range requests from each subsector's zip: "
        "<gas>/DATA/<subsector>_country_emissions_v5_10_0.csv. Checked the columns, that every row names its own "
        "sector, subsector and gas, is in tonnes, covers one calendar year, and that each of the 252 codes has one row "
        "in every year 2015–2026.",
        "Used the 100-year CO₂-equivalent file (co2e_100yr, IPCC AR6 global warming potentials) for "
        + ", ".join(sorted(by_basis["ct"] + by_basis["ct-iea"] + by_basis["ct-faostat"] + by_basis["faostat"]))
        + ", and for fluorinated-gases (EDGAR F-gases, CO₂-equivalent only).",
        "For the subsectors Climate TRACE takes from EDGAR ("
        + ", ".join(sorted(by_basis["edgar-non-co2"]))
        + ") read only the methane and nitrous oxide files (EDGAR CH4 and N2O, CC BY 4.0) and converted them to "
        "CO₂-equivalent with the IPCC AR6 100-year global warming potentials Climate TRACE applies: nitrous oxide 273; "
        + "; ".join(f"methane {k} for {', '.join(sorted(v))}" for k, v in sorted(gwp.items()))
        + ". Their carbon dioxide is IEA-EDGAR CO2, licensed CC BY-NC-ND 4.0, and is not included anywhere: these "
        "subsectors are methane and nitrous oxide only.",
        "Left out other-manufacturing entirely: " + EXCLUDED["other-manufacturing"],
        "The country totals of "
        + ", ".join(sorted(IEA_LINEAGE))
        + " are built by Climate TRACE from EDGAR, CEDS or IEA World Energy Balances inputs (IEA energy statistics); "
        "Climate TRACE publishes them under CC BY 4.0 and they are used under that licence.",
        "Climate TRACE publishes no world rows. The world value of a subsector and year is the sum of all 252 country "
        "rows, including UNK (vessels whose country is not known), which is published under no country; it is "
        "missing if any row is missing. Kosovo (XKX) and Northern Cyprus (ZNC) are Climate TRACE's own codes.",
        f"Left out {PARTIAL_YEAR}: its rows cover January to June only (V{RELEASE} was released on 27 August "
        f"{PARTIAL_YEAR} with Climate TRACE's 60-day lag).",
        "Treated as missing, not zero: "
        + ", ".join(f"{k} {', '.join(str(y) for y in v)}" for k, v in NOT_ESTIMATED.items())
        + f", where V{RELEASE} writes 0 for every country because those land fluxes were not yet estimated. "
        f"{missing_counts:,} country-years are missing in all.",
        "Published as Climate TRACE gives them, and flagged: subsector years in which every country's value equals "
        "the year before, where Climate TRACE carries its EDGAR, FAOSTAT or other input forward: "
        + ("; ".join(f"{s.sub.slug} {', '.join(str(y) for y in s.repeated)}" for s in series if s.repeated) or "none")
        + ".",
    ]


def _group_steps() -> list[str]:
    lines = []
    for g, label in GROUPS.items():
        subs = [s for s in MAPPING if s.group == g]
        lines.append(f"{label}: " + "; ".join(f"{s.slug} ({s.reason.rstrip('.')})" for s in subs) + ".")
    return [
        "Grouped the subsectors into Gates's five activities and three bands that are not one of the five, following "
        "Rhodium Group's grouping behind the book's shares (fuel supply under making things, waste with growing "
        "things, fluorinated gases with keeping warm and cool, electricity where generated, forest fires left out). "
        + " ".join(lines),
        "A group's value is the sum of its subsectors; it is missing in any place and year in which any of its "
        "subsectors is missing, never a partial sum. Land taking up carbon is kept as its own band and never "
        "subtracted from the five.",
    ]


# --- what is published ---------------------------------------------------------------------------------------------

MT_CO2E = Unit(code="MtCO2e", label="million tonnes of carbon dioxide equivalent", short="Mt CO₂e")
PERCENT = Unit(code="percent", label="percent of the five activities' total", short="%")
GEOGRAPHY = "The world and 251 countries and territories (international aviation and shipping assigned to countries)"
BASIS = (
    "Climate TRACE V5.10.0 country-level estimates (modelled, mostly from satellite and other remote sensing and "
    "facility data, revised every month), 100-year global warming potentials from the IPCC Sixth Assessment Report. "
    "Some subsectors' country totals are built by Climate TRACE from EDGAR, CEDS or IEA World Energy Balances inputs "
    "(road transport, residential and non-residential buildings, heat plants, glass, lime, food, textiles, other "
    "chemicals, other metals, wood, other mining) and are used under Climate TRACE's CC BY 4.0. For the subsectors "
    "Climate TRACE takes from EDGAR (other energy use, railways, other transport, other onsite fuel use, other solid "
    "fuels, other fossil fuel operations, landfills, composting, waste burning, cropland fires) only methane and "
    "nitrous oxide are included: their carbon dioxide is IEA-EDGAR CO2, licensed CC BY-NC-ND 4.0. Other manufacturing "
    "is not included. 2026 is a partial year and is not shown. International aviation and shipping are included."
)
LAND = (
    "Land use is shown in parts: clearing and degrading forest (gross carbon released) and the net carbon change of "
    "cropland soils; wildfires; and carbon taken up by standing forests with the net change of forest, shrub and "
    "grassland, and wetland that stays as it is (below zero where land takes up carbon). In V5.10.0 the 2025 values of "
    "that uptake are not yet estimated and are missing."
)

SECTOR_DIM = Dimension(
    id="sector",
    label="Climate TRACE sector",
    values=[DimensionValue(id=k, label=v) for k, v in SECTORS.items() if any(s.sector == k for s in MAPPING)],
)
SUBSECTOR_DIM = Dimension(
    id="subsector",
    label="Climate TRACE subsector",
    values=[DimensionValue(id=s.slug, label=s.published_label) for s in MAPPING],
)
ACTIVITY_DIM = Dimension(
    id="activity",
    label="Activity (Gates's five, and what is not one of them)",
    values=[DimensionValue(id=k, label=v) for k, v in GROUPS.items()],
)


def _mapping_words() -> str:
    return " ".join(
        f"{label}: " + ", ".join(s.published_label.lower() for s in MAPPING if s.group == g) + "."
        for g, label in GROUPS.items()
    )


def _runner(compute, changes: str):  # type: ignore[no-untyped-def]
    def run(files: dict[str, InputFile]) -> Result:
        series = load(files)
        obs, steps = compute(series)
        return Result(
            observations=obs,
            vintage=RELEASE,
            year=DATE_PUBLISHED[:4],
            date_published=DATE_PUBLISHED,
            steps=steps,
            changes=changes,
        )

    return run


INPUTS: tuple[Input, ...] = tuple(i for s in MAPPING for i in s.inputs)
SUM_CHANGES = (
    "converted to million tonnes; world values summed from every country; methane and nitrous oxide of subsectors "
    "taken from EDGAR converted to CO₂-equivalent with IPCC AR6 100-year global warming potentials, their carbon "
    "dioxide left out; other manufacturing left out."
)


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    scope = Scope(geography=GEOGRAPHY, gwp="AR6-GWP100", lulucf="included", bunkers="included", basis=f"{BASIS} {LAND}")
    return [
        Transform(
            spec=Spec(
                id="ghg.climate-trace.by-subsector",
                title="World greenhouse gas emissions by subsector, Climate TRACE",
                description="Each year's emissions of all greenhouse gases, in carbon dioxide equivalent, from each of "
                f"{len(MAPPING)} subsectors that Climate TRACE estimates, for the world (the sum of every country), "
                "2015–2025, each with the activity it is grouped into in ghg.climate-trace.by-activity. Countries' "
                "activity totals are in ghg.climate-trace.by-activity; their subsectors are not republished here, to "
                "keep the file small enough to serve. Subsectors do not overlap. Land use is split into its parts, "
                "some of them below zero where land "
                "takes up carbon. For ten subsectors that Climate TRACE takes from EDGAR only methane and nitrous "
                "oxide are shown, because their carbon dioxide comes from the International Energy Agency under terms "
                "that do not allow regrouping; other manufacturing is not shown for the same reason.",
                kind="series",
                unit=MT_CO2E,
                display=Display(decimals=2),
                scope=scope,
                geo_coverage="global-only",
                headline_entity=WORLD,
                dimensions=(SECTOR_DIM, SUBSECTOR_DIM, ACTIVITY_DIM),
                headline_dims=(
                    ("sector", "power"),
                    ("subsector", "electricity-generation"),
                    ("activity", "plugging-in"),
                ),
            ),
            inputs=INPUTS,
            run=_runner(by_subsector, SUM_CHANGES),
            module_file=here,
            validation=Validation(min_rows=700, value_range=(-30_000.0, 30_000.0)),
        ),
        Transform(
            spec=Spec(
                id="ghg.climate-trace.by-activity",
                title="Greenhouse gas emissions by activity: making things, plugging in, growing things, getting "
                "around, keeping warm and cool",
                description="Climate TRACE's emissions of all greenhouse gases grouped into the five activities Bill "
                "Gates uses in How to Avoid a Climate Disaster, for the world and each country, 2015–2025, plus three "
                "bands that are not one of the five: wildfires, land taking up carbon (below zero), and reservoirs. "
                "The grouping follows Rhodium Group's, which Gates's numbers come from: fuel production and refining "
                "count as making things, landfills and waste as growing things, fluorinated gases as keeping warm "
                "and cool, electricity where it is generated, and forest fires are left out. " + _mapping_words() + " "
                "A group is missing in a year in which any of its subsectors is missing: growing things starts in "
                "2016, because V5.10.0 has no 2015 estimate of cropland soil carbon, and land taking up carbon ends in "
                "2024, because its 2025 values are not yet estimated. Carbon dioxide from the "
                "subsectors Climate TRACE takes from EDGAR, and other manufacturing, are not included, so making "
                "things, plugging in, getting around and keeping warm and cool are somewhat smaller than their full "
                "emissions.",
                kind="derived",
                unit=MT_CO2E,
                display=Display(decimals=1),
                scope=scope,
                geo_coverage="mixed",
                headline_entity=WORLD,
                dimensions=(ACTIVITY_DIM,),
                headline_dims=(("activity", "making-things"),),
            ),
            inputs=INPUTS,
            run=_runner(by_activity, SUM_CHANGES + " Subsectors grouped into activities and summed."),
            module_file=here,
            validation=Validation(min_rows=20_000, value_range=(-40_000.0, 40_000.0)),
        ),
        Transform(
            spec=Spec(
                id="ghg.climate-trace.five-activities-total",
                title="Greenhouse gas emissions from Gates's five activities together",
                description="Climate TRACE's emissions of all greenhouse gases from the five activities Bill Gates "
                "uses in How to Avoid a Climate Disaster, added together, for the world and each country, 2016–2025: "
                "the total that each share in ghg.climate-trace.by-activity-share is a percentage of. Like Gates's "
                "total (Rhodium Group's), it counts emissions from human activity before what land takes up and "
                "without wildfires. Carbon dioxide from the subsectors Climate TRACE takes from EDGAR, and other "
                "manufacturing, are not included, so it is somewhat smaller than all emissions.",
                kind="derived",
                unit=MT_CO2E,
                display=Display(decimals=0),
                scope=scope,
                geo_coverage="mixed",
                headline_entity=WORLD,
            ),
            inputs=INPUTS,
            run=_runner(five_total, SUM_CHANGES + " Subsectors grouped into activities; the five added."),
            module_file=here,
            validation=Validation(min_rows=2_000, value_range=(-40_000.0, 100_000.0)),
        ),
        Transform(
            spec=Spec(
                id="ghg.climate-trace.by-activity-share",
                title="Share of greenhouse gas emissions by activity: Gates's five",
                description="Each of Gates's five activities as a percentage of the five together, for the world and "
                "each country, 2015–2025, from Climate TRACE's emissions grouped as in "
                "ghg.climate-trace.by-activity; the five add up to 100. Wildfires, land taking up carbon and "
                "reservoirs, which are not one of the five, are given as a percentage of the same total and are "
                "outside the 100. Shares start in 2016, the first year with all five. Like Gates's shares (Rhodium "
                "Group's), these are shares of emissions from human "
                "activity, before what land takes up and without wildfires. Carbon dioxide from the subsectors "
                "Climate TRACE takes from EDGAR, and other manufacturing, are not included.",
                kind="derived",
                unit=PERCENT,
                display=Display(decimals=1),
                scope=scope,
                geo_coverage="mixed",
                headline_entity=WORLD,
                dimensions=(ACTIVITY_DIM,),
                headline_dims=(("activity", "making-things"),),
            ),
            inputs=INPUTS,
            run=_runner(by_activity_share, SUM_CHANGES + " Subsectors grouped into activities; shares computed."),
            module_file=here,
            # Bands against a small five total reach tens of thousands of percent (savanna fires in the Central
            # African Republic are many times its other emissions); the five themselves are always 0-100.
            validation=Validation(min_rows=20_000, value_range=(-200_000.0, 200_000.0)),
        ),
    ]
