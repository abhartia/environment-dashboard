"""World Bank Climate Change Knowledge Portal (CCKP): CMIP6 projections of seven measures for every country and every
CCKP state or province, for four 20-year windows under three emissions scenarios, with the 1995–2014 model baseline.

Inputs (source wb-cckp, the artifact_grids of pipeline/sources/wb-cckp.yaml): the API's all_countries_subnationals
file of each CMIP6 0.25° annual climatology, one file per variable, window, scenario and statistic (median, 10th and
90th percentile of the multi-model ensemble). hd35, tr26, hi39, txx, rx1day and cdd: 1995–2014 from the historical
runs, and 2020–2039, 2040–2059, 2060–2079 and 2080–2099 under SSP1-2.6, SSP2-4.5 and SSP5-8.5 (39 files each); tas:
CCKP's anomaly product, the change from 1995–2014, for the 12 future combinations (36 files; there is no 1995–2014
anomaly). Each file holds every country and every CCKP region in one response. The files are read with
envdash/transforms/country/cckp.py: what each file is, is read from its URL (collection, variable, product, window,
statistic, scenario, area), every key holds exactly one stamp (the window's first year, "2040-07"), a file holding
GLOBAL or a key that is neither three letters nor a region code stops the build, the variable must be one of the
seven this site reads, and a count-type product (popcount, popwgt, *exposure) is refused by name.

Definitions, quoted from CCKP's Metadata page (climateknowledgeportal.worldbank.org/metadata, read in a browser on
2026-10-16; it returns HTTP 403 to scripts):
- hd35, "Number of Hot Days (Tmax >= 35°C)": "The number of days with daily maximum temperature >= 35°C that
  occurred during the aggregation period." 35 °C or more.
- tr26, "Number of Tropical Nights (T-min >= 26°C)": "The number of days where the daily minimum temperature
  remained >= 26°C over the aggregation period." 26 °C or more. (The netCDF of the same collection says both "26 degC
  and higher" and "tasmin > 26.0 C"; CCKP's GitHub notes write "T-min > 26°C". The Metadata page is quoted here.)
- hi39, "Number of Days with Heat Index >= 39°C": "The number of days where the Heat Index >= 39°C over the
  aggregation period. The Heat Index is a measure of apparent temperature that includes the influence of atmospheric
  moisture." The Heat Index is "as defined by US-National Weather Service".
- txx, "Maximum of Daily Max-Temperature": "The single-day maximum value of the daily maximum temperatures over the
  aggregated data period."
- rx1day, "Average Largest 1-Day Precipitation": "The average highest precipitation amount in a 1-day period during
  each data period." In millimetres.
- cdd: the page lists "Maximum Number of Consecutive Dry Days_Max", "The largest number of consecutive dry days
  (>1mm) during the considered period", and "Number of Consecutive Dry Days_Mean", "Monthly, Seasonal or Annual
  maximum of the maximum number of consecutive days with precipitation < 1mm". The netCDF of these files says
  "longest consecutive sequence of dry days (<1mm) within annual data", so a dry day has less than 1 mm.
- tas, "Average Surface Air Temperature": "Average temperature over the aggregation period". Anomalies: "The ensemble
  anomaly is calculated by taking the anomalies from individual models and then determining the median, along with
  the 10th and 90th percentiles"; the reference period is 1995–2014 (the netCDF of the same collection: "anomaly of
  Daily Near-Surface Air Temperature with reference period 1995-2014").
- Climatologies: "For each model, and for each of the climate variables and indicators, 20year climatologies were
  formed from their corresponding time series ... one annual mean value established over the respective time
  windows". So each value is a 20-year average of the yearly figure (txx: of each year's hottest day).
- Areas: "The weighted mean ... computed for each polygon, with weights combining both fractional overlap and
  latitudinal adjustments", on the World Bank's ADM0 and ADM1 boundaries. Values are averaged over each area's land,
  not weighted by where people live.

Published: per measure, one indicator of countries and one of regions. The window is the observation's period
("2040/2059"); the scenario is the dimension scenario (historical, ssp126, ssp245, ssp585); the median is the value
and the 10th and 90th percentiles the range ("range"), as printed. Status projection, except the historical runs
(final; their label says they are a model simulation, not observations). Countries are mapped to entities as in
cckp.py (KSV to KOS). Regions keep CCKP's code and must be in pipeline/geo/entities.csv as kind region with the
country of their prefix as member_of (envdash/geo.py). Left out, as geo.py declares: the 32 DIS.* units and the three
units CCKP lists under China for Hong Kong, Macao and Taiwan (geo.CHINA_LISTED).

Checks that stop the build, besides cckp.read_file's: every file of a measure holds the same codes; every region's
prefix is a country of the same file, or DIS; exactly geo.DISPUTED_UNITS DIS units; 10th percentile <= median <= 90th
percentile for every key; and the national check. A null value stops the build in read_file; none is declared, and
the snapshots of 2026-10-16 have none.

National check. CCKP's national totals of counts are inflated 2-3 times (see cckp.py COUNT_TYPES), so every country
value is compared with its own regions in the same file: it must lie within [lowest region - 0.01, highest region +
0.01] (two halves of the last printed digit), and a country with one region must equal it within 0.01. In the
snapshots of 2026-10-16 this holds for every country in every file of hd35, tr26, hi39 and txx (156 files). For cdd,
rx1day and tas it fails for the countries in NATIONAL_EXCEPTIONS, each declared with the evidence. CCKP's Metadata
page says ensemble values are "calculated from the individual model series" and does not say whether that is before
or after averaging over each area; a median of per-model area means need not lie between the regions' medians. Those
national values are published as CCKP prints them, as CCKP's figure for the whole country; nothing here combines
regions into a country or a country into regions. An offender not declared stops the build, and so does a declared
exception that no longer offends in any file of its measure.

Vintage. CCKP publishes no version label and its API sends no Last-Modified or ETag, so the vintage is the variable
and the newest fetch date of the files read (the sha256 of each file is in the origins).

Publisher checks. None: CCKP states no number from these files in text.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from envdash import geo
from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation
from envdash.transforms.country.cckp import SOURCE, CckpFormatError, entities_of, read_file

BASELINE = (1995, 2014)
WINDOWS = ((2020, 2039), (2040, 2059), (2060, 2079), (2080, 2099))
FUTURES = ("ssp126", "ssp245", "ssp585")
STATISTICS = ("median", "p10", "p90")
NATIONAL_TOLERANCE = Decimal("0.01")


@dataclass(frozen=True)
class Pathway:
    id: str
    """CCKP's scenario code."""
    label: str


# IPCC AR6 calls SSP1-2.6 low, SSP2-4.5 intermediate and SSP5-8.5 very high emissions; this site says "middle" for
# SSP2-4.5 (the owner's plan of 2026-10-16) and "very high" for SSP5-8.5, as the heat chapter does. The historical runs
# are the models' simulation of the past.
PATHS: tuple[Pathway, ...] = (
    Pathway("historical", "Model simulation of 1995–2014, not observations"),
    Pathway("ssp126", "SSP1-2.6, low emissions"),
    Pathway("ssp245", "SSP2-4.5, middle emissions"),
    Pathway("ssp585", "SSP5-8.5, very high emissions"),
)

DAYS_RANGE = (0.0, 366.0)


@dataclass(frozen=True)
class Measure:
    key: str
    """The indicator id's stem: future.wb-cckp.<key>-countries."""
    variable: str
    product: str
    """CCKP's product: climatology, or anomaly (tas)."""
    name: str
    """What is measured, as a noun phrase for titles and descriptions."""
    unit: Unit
    decimals: int
    value_range: tuple[float, float]
    definition: str
    baseline: str | None = None
    """Scope.baseline: only for a change from a reference period."""

    @property
    def stem(self) -> str:
        """The artifact id's variable part: hd35, or tas-anomaly."""
        return self.variable if self.product == "climatology" else f"{self.variable}-{self.product}"

    @property
    def has_baseline_runs(self) -> bool:
        return self.product == "climatology"

    def slices(self) -> list[tuple[str, int, int]]:
        """(scenario, start, end) of every file set of this measure, in publishing order."""
        hist = [("historical", *BASELINE)] if self.has_baseline_runs else []
        return hist + [(s, a, b) for s in FUTURES for a, b in WINDOWS]


def _input(m: Measure, scenario: str, start: int, end: int, statistic: str) -> Input:
    return Input(SOURCE, f"cmip6-{m.stem}-{start}-{end}-{scenario}-{statistic}-subnat")


DAYS = "days"
MEASURES: tuple[Measure, ...] = (
    Measure(
        key="hot-days-35c",
        variable="hd35",
        product="climatology",
        name="Days a year at 35 °C or more",
        unit=Unit(code=DAYS, label="days a year with a daily maximum temperature of 35 °C or more", short="days"),
        decimals=0,
        value_range=DAYS_RANGE,
        definition="Days with a daily maximum temperature of 35 °C or more (CCKP's hd35, Tmax >= 35 °C).",
    ),
    Measure(
        key="hot-nights-26c",
        variable="tr26",
        product="climatology",
        name="Nights a year that stay at 26 °C or more",
        unit=Unit(code=DAYS, label="nights a year with a daily minimum temperature of 26 °C or more", short="nights"),
        decimals=0,
        value_range=DAYS_RANGE,
        definition="Days whose minimum temperature stays at 26 °C or more (CCKP's tr26, tropical nights, T-min >= "
        "26 °C).",
    ),
    Measure(
        key="heat-index-39c-days",
        variable="hi39",
        product="climatology",
        name="Days a year with a heat index of 39 °C or more",
        unit=Unit(code=DAYS, label="days a year with a heat index of 39 °C or more", short="days"),
        decimals=0,
        value_range=DAYS_RANGE,
        definition="Days with a heat index of 39 °C or more (CCKP's hi39). The heat index, as the US National Weather "
        "Service defines it, is how hot it feels once humidity is counted.",
    ),
    Measure(
        key="hottest-day",
        variable="txx",
        product="climatology",
        name="Temperature of the hottest day of the year",
        unit=Unit(code="degC", label="degrees Celsius on the hottest day of the year", short="°C"),
        decimals=1,
        value_range=(-60.0, 70.0),
        definition="The year's highest daily maximum temperature (CCKP's txx), averaged over the 20 years.",
    ),
    Measure(
        key="wettest-day",
        variable="rx1day",
        product="climatology",
        name="Rain on the wettest day of the year",
        unit=Unit(code="mm", label="millimetres of precipitation on the year's wettest day", short="mm"),
        decimals=0,
        value_range=(0.0, 1000.0),
        definition="The year's largest one-day precipitation (CCKP's rx1day), averaged over the 20 years.",
    ),
    Measure(
        key="longest-dry-spell",
        variable="cdd",
        product="climatology",
        name="Longest dry spell of the year",
        unit=Unit(
            code=DAYS, label="days in the year's longest run of days with less than 1 mm of precipitation", short="days"
        ),
        decimals=0,
        value_range=DAYS_RANGE,
        definition="The year's longest run of consecutive dry days, days with less than 1 mm of precipitation (CCKP's "
        "cdd), averaged over the 20 years. A dry spell, not a drought.",
    ),
    Measure(
        key="warming",
        variable="tas",
        product="anomaly",
        name="Warming from 1995–2014",
        unit=Unit(code="degC", label="degrees Celsius warmer than the 1995–2014 average", short="°C"),
        decimals=1,
        value_range=(-5.0, 20.0),
        definition="The change in annual mean near-surface air temperature from 1995–2014 (CCKP's tas anomaly): each "
        "model's change, then the median and the 10th and 90th percentiles of the models.",
        baseline="1995–2014 mean of the same model runs (CCKP's reference period)",
    ),
)

# Countries whose national value lies outside its regions' range in at least one file of the measure (snapshots of
# 2026-10-16), by CCKP's code. See the module docstring.
CDD_NATIONAL = frozenset(
    {
        "BEL", "BES", "BHR", "BIH", "BLR", "CYM", "DNK", "FIN", "GGY", "JEY", "KWT", "LIE", "LTU", "LUX", "NLD", "QAT",
        "SPM", "VCT", "VIR",
    }
)  # fmt: skip
RX1DAY_NATIONAL = frozenset(
    {
        "AGO", "AIA", "ATF", "ATG", "BES", "BLR", "BRB", "BWA", "CAF", "COD", "CUB", "CYM", "CZE", "DEU", "DNK", "EST",
        "FIN", "GMB", "GRD", "HUN", "IDN", "IRL", "KOR", "KWT", "LCA", "LTU", "LUX", "LVA", "MDA", "MDV", "MLT", "MOZ",
        "MWI", "MYS", "NGA", "NIC", "NLD", "NZL", "OMN", "POL", "PRY", "QAT", "ROU", "SAU", "SOM", "SPM", "SSD", "STP",
        "SUR", "SWE", "SYC", "TGO", "THA", "TKM", "TZA", "UKR", "UMI", "URY", "VCT", "VGB", "VIR", "VUT", "ZMB",
    }
)  # fmt: skip
TAS_NATIONAL = frozenset(
    {
        "AUS", "BES", "CAN", "CYP", "ETH", "FIN", "GMB", "GNB", "GTM", "HRV", "KGZ", "MNG", "NAM", "NER", "RWA", "SHN",
        "SLE", "TGO", "TJK", "TKM", "UMI", "USA", "UZB",
    }
)  # fmt: skip

# Measure variable -> (the evidence, the countries).
NATIONAL_EXCEPTIONS: dict[str, tuple[str, frozenset[str]]] = {
    "cdd": (
        "In 46 country values of the 39 files (19 countries), the national value lies outside its regions' range by "
        "up to 1.53 days (Qatar, 2020–2039 SSP1-2.6 p90: 252.88 against 254.41 to 261.66).",
        CDD_NATIONAL,
    ),
    "rx1day": (
        "In 872 country values of the 39 files (63 countries), the national value lies outside its regions' range, "
        "below the lowest region in 859 of them, by up to 14.14 mm (United States Minor Outlying Islands, 2060–2079 "
        "SSP5-8.5 p90: 36.16 against 50.3 to 98.89).",
        RX1DAY_NATIONAL,
    ),
    "tas": (
        "In 31 country values of the 36 files (23 countries), the national warming lies outside its regions' range by "
        "up to 0.08 °C (Kyrgyzstan, 2060–2079 SSP2-4.5 p90: 3.23 against 3.31 to 3.61); CCKP takes each model's "
        "change before the median.",
        TAS_NATIONAL,
    ),
}


# --- reading ------------------------------------------------------------------------------------------------------

Values = dict[str, Decimal]
"""CCKP code -> the file's one value."""


@dataclass(frozen=True)
class Files:
    """One measure's files, read."""

    measure: Measure
    slices: tuple[tuple[str, int, int], ...]
    """(scenario, start, end) read, in publishing order: every one of measure.slices() in a build."""
    values: dict[tuple[str, int, str], Values]
    """(scenario, start, statistic) -> values."""
    codes: frozenset[str]
    vintage: str


def read_measure(m: Measure, files: dict[str, InputFile]) -> Files:
    values: dict[tuple[str, int, str], Values] = {}
    codes: frozenset[str] | None = None
    for scenario, start, end in m.slices():
        for st in STATISTICS:
            i = _input(m, scenario, start, end, st)
            _, data = read_file(
                files[i.key],
                i.key,
                collection="cmip6-x0.25",
                type="climatology",
                variable=m.variable,
                product=m.product,
                start=start,
                end=end,
                statistic=st,
                scenario=scenario,
                model="ensemble_all",
                geocode="all_countries_subnationals",
            )
            if codes is None:
                codes = frozenset(data)
            elif set(data) != codes:
                raise CckpFormatError(f"{i.key} covers other areas than the first file: {sorted(set(data) ^ codes)}")
            values[(scenario, start, st)] = {code: next(iter(series.values())) for code, series in data.items()}
    assert codes is not None
    check_codes(codes, m.variable)
    check_ranges(values, m.variable)
    fetched = max(f.snapshot.date_accessed for k, f in files.items() if k.startswith(f"{SOURCE}/")).isoformat()
    return Files(m, tuple(m.slices()), values, codes, f"cmip6-x0.25 {m.variable} {m.product}, fetched {fetched}")


def _prefix(code: str) -> str:
    return code.split(".", 1)[0]


def check_codes(codes: frozenset[str], name: str) -> None:
    """Every region's prefix is a country of the same file, or DIS; exactly geo.DISPUTED_UNITS DIS units."""
    countries = {c for c in codes if "." not in c}
    regions = [c for c in codes if "." in c]
    orphans = sorted(c for c in regions if _prefix(c) not in countries | {geo.DISPUTED_PREFIX})
    if orphans:
        raise CckpFormatError(f"{name}: regions whose prefix is not a country of the same file: {orphans[:10]}")
    disputed = sum(_prefix(c) == geo.DISPUTED_PREFIX for c in regions)
    if disputed != geo.DISPUTED_UNITS:
        raise CckpFormatError(f"{name}: {disputed} {geo.DISPUTED_PREFIX}.* units, not {geo.DISPUTED_UNITS}")


def check_ranges(values: dict[tuple[str, int, str], Values], name: str) -> None:
    """p10 <= median <= p90 for every key of every scenario and window."""
    bad: list[str] = []
    for (scenario, start, st), median in values.items():
        if st != "median":
            continue
        lo, hi = values[(scenario, start, "p10")], values[(scenario, start, "p90")]
        bad += [f"{scenario} {start} {c}" for c, v in median.items() if not lo[c] <= v <= hi[c]]
    if bad:
        raise CckpFormatError(f"{name}: median outside the 10th-90th percentile for {len(bad)} keys: {bad[:5]}")


def national_offenders(values: dict[tuple[str, int, str], Values]) -> dict[str, list[str]]:
    """CCKP country code -> the files (scenario, start, statistic) where its value lies outside its regions' range
    (beyond NATIONAL_TOLERANCE), or differs from its one region. Every region CCKP lists under the country counts,
    including those this site leaves out (geo.CHINA_LISTED); DIS units belong to no country."""
    out: dict[str, list[str]] = {}
    for (scenario, start, st), vals in sorted(values.items()):
        regions: dict[str, list[Decimal]] = {}
        for code, v in vals.items():
            if "." in code and _prefix(code) != geo.DISPUTED_PREFIX:
                regions.setdefault(_prefix(code), []).append(v)
        for country, rv in sorted(regions.items()):
            n = vals[country]
            if len(rv) == 1:
                ok = abs(n - rv[0]) <= NATIONAL_TOLERANCE
            else:
                ok = min(rv) - NATIONAL_TOLERANCE <= n <= max(rv) + NATIONAL_TOLERANCE
            if not ok:
                out.setdefault(country, []).append(f"{scenario} {start} {st}: {n} against {min(rv)} to {max(rv)}")
    return out


def check_national(f: Files) -> None:
    offenders = national_offenders(f.values)
    declared = NATIONAL_EXCEPTIONS.get(f.measure.variable, ("", frozenset()))[1]
    undeclared = {c: v for c, v in offenders.items() if c not in declared}
    if undeclared:
        shown = [f"{c} ({v[0]}; {len(v)} files)" for c, v in sorted(undeclared.items())[:10]]
        raise CckpFormatError(
            f"{f.measure.variable}: the national value of {len(undeclared)} countries lies outside the range of their "
            f"own regions: {shown}. CCKP's national counts were once inflated 2-3 times; find out why before "
            "declaring an exception in NATIONAL_EXCEPTIONS"
        )
    stale = sorted(declared - set(offenders))
    if stale:
        raise CckpFormatError(
            f"{f.measure.variable}: NATIONAL_EXCEPTIONS declares {stale}, whose national values now lie within their "
            "regions' range in every file; remove them"
        )


# --- entities and observations ------------------------------------------------------------------------------------


def countries_of(f: Files) -> dict[str, str]:
    """CCKP country code -> our entity (cckp.entities_of: KSV to KOS; an unknown code stops the build)."""
    return entities_of({c for c in f.codes if "." not in c}, f.measure.variable)


def regions_of(f: Files, countries: dict[str, str]) -> list[str]:
    """The region codes published: every region of the files but the DIS units and geo.CHINA_LISTED. Each must be a
    region in pipeline/geo/entities.csv whose member_of is the entity of its prefix."""
    out: list[str] = []
    for code in sorted(c for c in f.codes if "." in c):
        if _prefix(code) == geo.DISPUTED_PREFIX or code in geo.CHINA_LISTED:
            continue
        try:
            e = geo.entity(code)
        except geo.UnknownEntity:
            raise CckpFormatError(
                f"{f.measure.variable}: CCKP region {code} is not in pipeline/geo/entities.csv; run envdash geo build "
                "after fetching wb-cckp/subnational-names"
            ) from None
        if e.kind != "region" or e.member_of != (countries[_prefix(code)],):
            raise CckpFormatError(
                f"{f.measure.variable}: {code} is a {e.kind} of {e.member_of} in entities.csv, not a region of "
                f"{countries[_prefix(code)]}"
            )
        out.append(code)
    return out


def observations(f: Files, codes: dict[str, str]) -> list[Observation]:
    """The observations of `codes` (CCKP code -> entity): per scenario and window read, the median as the value and
    the 10th-90th percentile as the range, as printed. Ordered by entity, scenario (as PATHS) and window."""
    order = {p.id: i for i, p in enumerate(PATHS)}
    slices = sorted(f.slices, key=lambda s: (order[s[0]], s[1]))
    obs: list[Observation] = []
    for code, ent in sorted(codes.items(), key=lambda kv: kv[1]):
        for scenario, start, end in slices:
            at = {st: f.values[(scenario, start, st)][code] for st in STATISTICS}
            obs.append(
                Observation(
                    entity=ent,
                    period=f"{start}/{end}",
                    value=float(at["median"]),
                    lower=float(at["p10"]),
                    upper=float(at["p90"]),
                    interval="range",
                    status="final" if scenario == "historical" else "projection",
                    dims={"scenario": scenario},
                )
            )
    return obs


def _windows() -> str:
    return ", ".join(f"{a}–{b}" for a, b in WINDOWS[:-1]) + f" and {WINDOWS[-1][0]}–{WINDOWS[-1][1]}"


def _steps(f: Files, published: str) -> list[str]:
    m = f.measure
    runs = "the 1995–2014 historical runs and " if m.has_baseline_runs else ""
    n = len(m.slices()) * len(STATISTICS)
    declared = NATIONAL_EXCEPTIONS.get(m.variable, ("", frozenset()))
    national = (
        "Checked every country's value against its own regions' values in the same file: within the lowest and "
        "highest region (±0.01, rounding), or equal to its one region. "
        + (
            f"Declared exceptions, whose national values are published as CCKP prints them: {len(declared[1])} "
            f"countries ({', '.join(sorted(declared[1]))}, CCKP's codes). {declared[0]}"
            if declared[1]
            else "It holds for every country in every file."
        )
    )
    return [
        f"Read CCKP's {n} CMIP6 0.25° all_countries_subnationals files of {m.variable} ({m.product}): the multi-model "
        f"ensemble median, 10th and 90th percentiles for {runs}{_windows()} under SSP1-2.6, SSP2-4.5 and SSP5-8.5. "
        f"Every file holds the same {sum('.' not in c for c in f.codes)} countries and "
        f"{sum('.' in c for c in f.codes):,} regions.",
        national,
        f"Published {published}: the median as the value and the 10th and 90th percentiles as the range, as printed, "
        "with the 20-year window as the period and the emissions scenario as a dimension.",
    ]


def _run_countries(m: Measure):
    def run(files: dict[str, InputFile]) -> Result:
        f = read_measure(m, files)
        check_national(f)
        countries = countries_of(f)
        obs = observations(f, countries)
        steps = _steps(
            f,
            f"every country and territory ({len(countries)}), mapping CCKP's codes to the site's entities (ISO "
            "3166-1 alpha-3 codes as they are, KSV, CCKP's code for Kosovo, as KOS)",
        )
        return Result(observations=obs, vintage=f.vintage, steps=steps)

    return run


def _run_regions(m: Measure):
    def run(files: dict[str, InputFile]) -> Result:
        f = read_measure(m, files)
        check_national(f)
        countries = countries_of(f)
        regions = regions_of(f, countries)
        left = sorted(c for c in f.codes if c in geo.CHINA_LISTED)
        obs = observations(f, {c: c for c in regions})
        china = (
            f", and the {len(left)} units CCKP lists under China for Hong Kong, Macao or Taiwan "
            f"({'; '.join(f'{c} {geo.CHINA_LISTED[c]!r}' for c in left)}), places this site publishes under their own "
            "codes"
            if left
            else ""
        )
        steps = _steps(
            f,
            f"{len(regions):,} states, provinces and other first-level regions under CCKP's own codes, leaving out the "
            f"{geo.DISPUTED_UNITS} DIS.* units (areas the World Bank assigns to no country){china}",
        )
        return Result(observations=obs, vintage=f.vintage, steps=steps)

    return run


# --- indicators ---------------------------------------------------------------------------------------------------

COUNTRY_GEOGRAPHY = (
    "Each country or territory as drawn by the World Bank's official boundaries: the area-weighted mean of the 0.25° "
    "grid cells inside it, averaged over the land, not weighted by where people live. No world value."
)
REGION_GEOGRAPHY = (
    "Each state, province or other first-level region as CCKP draws it on the World Bank's official boundaries: the "
    "area-weighted mean of the 0.25° grid cells inside it, averaged over the land, not weighted by where people live. "
    "The 32 areas the World Bank assigns to no country are left out."
)

# The headline is India under SSP2-4.5, and Delhi for the regions: the country and region the source research checked
# by hand (hd35 2040–2059 SSP2-4.5 median: India 94.78 days, Delhi 123.28 days, read from the API on 2026-10-15).
HEADLINE_COUNTRY = "IND"
HEADLINE_REGION = "IND.11510"
HEADLINE_DIMS = (("scenario", "ssp245"),)

# Rows per indicator (snapshots of 2026-10-16): 246 countries; regions per measure after the DIS units and
# geo.CHINA_LISTED are left out. Each times 13 combinations (12 for warming, which has no 1995–2014 row).
MIN_COUNTRIES = 246
MIN_REGIONS = {"hd35": 3492, "tr26": 3492, "hi39": 3493, "txx": 3493, "rx1day": 3495, "cdd": 3495, "tas": 3495}


def _basis(m: Measure) -> str:
    runs = "1995–2014 from the historical runs; " if m.has_baseline_runs else ""
    return (
        "CMIP6 multi-model ensemble (bias-corrected and downscaled to 0.25° by CCKP): the median of the models, with "
        f"their 10th–90th percentile as the range. {m.definition} 20-year averages: {runs}{_windows()} under SSP1-2.6, "
        "SSP2-4.5 and SSP5-8.5. Projections, not forecasts of any one year."
    )


def _spec(m: Measure, level: str) -> Spec:
    countries = level == "countries"
    where = "by country" if countries else "by state or province"
    baseline_runs = "1995–2014 as the models simulate it and " if m.has_baseline_runs else ""
    return Spec(
        id=f"future.wb-cckp.{m.key}-{level}",
        title=f"{m.name} {where}, projected for 20-year windows to 2099 (CMIP6, World Bank CCKP)",
        description=f"{m.name}, {baseline_runs}projected for 2020–2039, 2040–2059, 2060–2079 and 2080–2099 under low, "
        "middle and very high emissions, "
        + ("for every country and territory" if countries else "for every state or province")
        + ", from the CMIP6 climate models as bias-corrected, downscaled and aggregated by the World Bank's Climate "
        "Change Knowledge Portal. Each value is averaged over the land of the place, not weighted by where people "
        "live. The value is the median of the models and the range runs from the 10th to the 90th percentile of the "
        "models."
        + (
            " The 1995–2014 values are the models' simulation of the recent past, not observations."
            if m.has_baseline_runs
            else ""
        ),
        kind="series",
        unit=m.unit,
        display=Display(decimals=m.decimals),
        scope=Scope(
            geography=COUNTRY_GEOGRAPHY if countries else REGION_GEOGRAPHY, baseline=m.baseline, basis=_basis(m)
        ),
        geo_coverage="country" if countries else "subnational",
        headline_entity=HEADLINE_COUNTRY if countries else HEADLINE_REGION,
        headline_dims=HEADLINE_DIMS,
        dimensions=(
            Dimension(
                id="scenario",
                label="Emissions scenario",
                values=[
                    DimensionValue(id=p.id, label=p.label) for p in PATHS if p.id != "historical" or m.has_baseline_runs
                ],
            ),
        ),
    )


def inputs(m: Measure) -> tuple[Input, ...]:
    return tuple(_input(m, s, a, b, st) for s, a, b in m.slices() for st in STATISTICS)


def transforms(paths: Paths) -> list[Transform]:
    module = Path(__file__)
    out: list[Transform] = []
    for m in MEASURES:
        combos = len(m.slices())
        out.append(
            Transform(
                spec=_spec(m, "countries"),
                inputs=inputs(m),
                run=_run_countries(m),
                module_file=module,
                validation=Validation(min_rows=MIN_COUNTRIES * combos, value_range=m.value_range),
            )
        )
        out.append(
            Transform(
                spec=_spec(m, "regions"),
                inputs=inputs(m),
                run=_run_regions(m),
                module_file=module,
                validation=Validation(min_rows=MIN_REGIONS[m.variable] * combos, value_range=m.value_range),
            )
        )
    return out
