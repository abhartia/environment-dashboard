"""World Bank Climate Change Knowledge Portal (CCKP): country temperature from ERA5, and days of 35 °C or more from
the CMIP6 ensemble.

Inputs (source wb-cckp, the CCKP API's JSON for every country at once, plus the "global" aggregate where one is
used): the ERA5 0.25° annual mean near-surface air temperature series (absolute °C, keyed "YYYY-07", the mid-year
stamp of an annual value), CCKP's own ERA5 1991–2020 annual climatology, and CCKP's CMIP6 0.25° climatologies of
hd35 (median, 10th and 90th percentile of the multi-model ensemble) for the 1995–2014 historical reference period
and for 2040–2059 under SSP1-2.6, SSP2-4.5 and SSP5-8.5.

What each file is, is read from its URL rather than assumed. The CCKP collection code in the URL
(`{collection}_{type}_{variable}_{product}_annual_{start}-{end}_{statistic}_{scenario}_{model}_mean/{geocode}`)
must name exactly the variable, period, statistic, scenario and geography this module expects for that artifact,
and every series in the file must hold exactly the stamps that period implies (1950-07 to 2025-07 for the series;
the period's first year for a climatology). A file that says anything else stops the build.

Definitions, from CCKP's Metadata page (read in a browser on 2026-10-05; the site returns HTTP 403 to scripts):
- hd35 is "Number of Hot Days (Tmax >= 35°C)": "The number of days with daily maximum temperature >= 35°C that
  occurred during the aggregation period." So the threshold is 35 °C or more, not strictly above.
- Country values are weighted means of the 0.25° grid: "weights combining both fractional overlap and latitudinal
  adjustments" (the fraction of each cell inside the boundary polygon, times the cosine of latitude).
- The CMIP6 "Multi-Model Ensemble range: 50th (median), 10th, 90th percentiles"; CMIP6 data were bias-corrected and
  downscaled by CCKP from a common 1° grid to 0.25°. The historical reference period is 1995–2014.
- ERA5 "Historical Climatologies ...: 1986-2005, 1991-2020, 1995-2014". There is no 1951–1980 ERA5 climatology on
  CCKP, so the change indicator uses the 1991–2020 one CCKP publishes, never a baseline computed here.

Entities. CCKP keys countries by World Bank Official Boundaries codes, which are ISO 3166-1 alpha-3 except for the
two in ALIASES (each seen in the snapshots below). Every other code goes through geo.resolve(code, "iso3"), which
raises on anything unknown, so an unknown code stops the build. Seven CCKP areas that Natural Earth 1:50m draws inside
another polygon, or not at all (Bouvet Island, Cocos (Keeling) Islands, French Guiana, Mayotte, Réunion, Svalbard and
Jan Mayen, United States Minor Outlying Islands) are entities through envdash/geo.py EXTRA_TERRITORIES. CCKP's
boundaries are the World Bank's, not Natural Earth's de facto ones: CCKP has no separate series for Western Sahara,
Somaliland, Northern Cyprus, the Falkland Islands or South Georgia, so those entities have no data here.

The change from 1991–2020 is each annual value minus CCKP's published 1991–2020 climatology for the same area, in
exact decimal arithmetic on the printed digits. The build first checks that the climatology belongs to the same
series: the mean of the 30 printed annual values 1991–2020 must be within 0.01 °C of it (each printed value carries
up to ±0.005 °C of rounding, so their mean does too, and so does the printed climatology). In the snapshot of
2026-10-05 the largest difference is 0.006 °C (Liberia).

Status. ERA5 values and the 1995–2014 historical-run values are "final"; 2040–2059 values are "projection". The
1995–2014 hd35 values are model simulations of the past (the reference the projections are compared with), not
observations; the indicator's description says so.

Vintage. CCKP publishes no version label and its API sends no Last-Modified or ETag, so the vintage is the collection
period code and the newest fetch date of the files read (the sha256 of each file is in the origins).

Publisher checks. None. CCKP's country pages state no number for these series in text (they are charts, and the
"Climatology" tab uses CRU, not ERA5), and no World Bank statement of a value from these files was found
(searched 2026-10-05).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from envdash import geo
from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "wb-cckp"

TAS_COUNTRIES = Input(SOURCE, "era5-tas-annual-countries")
TAS_GLOBAL = Input(SOURCE, "era5-tas-annual-global")
CLIM_COUNTRIES = Input(SOURCE, "era5-tas-climatology-1991-2020-countries")
CLIM_GLOBAL = Input(SOURCE, "era5-tas-climatology-1991-2020-global")

CLIMATOLOGY = (1991, 2020)
# Half the last printed digit of the 30 annual values' mean (±0.005) plus that of the printed climatology (±0.005).
CLIMATOLOGY_TOLERANCE = Decimal("0.01")

# Producer code -> our code, for codes that are not ISO 3166-1 alpha-3. Both seen in the wb-cckp snapshots of
# 2026-10-05: KSV in every all_countries file (era5-tas-annual-countries sha256 62effa974e35…), GLOBAL in
# era5-tas-annual-global (sha256 589d54de415a…) and era5-tas-climatology-1991-2020-global (sha256 ac58ff0206fa…).
ALIASES: dict[str, str] = {
    # CCKP's code for Kosovo (Kosovo has no ISO 3166-1 code). The files have no XKX or KOS, and CCKP lists Kosovo as a
    # country (climateknowledgeportal.worldbank.org/country/kosovo, read in a browser on 2026-10-05).
    "KSV": "KOS",
    # The geocode of the "global" aggregation (the only key of the /global files).
    "GLOBAL": "WLD",
}

COLLECTION_URL = re.compile(
    r"https://cckpapi\.worldbank\.org/cckp/v1/"
    r"(?P<collection>era5-x0\.25|cmip6-x0\.25)_(?P<type>timeseries|climatology)_(?P<variable>[a-z0-9]+)_"
    r"(?P<product>timeseries|climatology)_annual_(?P<start>\d{4})-(?P<end>\d{4})_"
    r"(?P<statistic>mean|median|p10|p90)_(?P<scenario>historical|ssp\d{3})_(?P<model>era5_x0\.25|ensemble_all)_mean/"
    r"(?P<geocode>all_countries|global)\?_format=json"
)


@dataclass(frozen=True)
class Scenario:
    id: str
    label: str
    code: str
    """CCKP's scenario code in the collection name."""
    start: int
    end: int

    @property
    def period(self) -> str:
        return f"{self.start}/{self.end}"


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("historical", "Historical simulations, 1995–2014", "historical", 1995, 2014),
    Scenario("ssp126", "SSP1-2.6 (low emissions), 2040–2059", "ssp126", 2040, 2059),
    Scenario("ssp245", "SSP2-4.5 (intermediate emissions), 2040–2059", "ssp245", 2040, 2059),
    Scenario("ssp585", "SSP5-8.5 (very high emissions), 2040–2059", "ssp585", 2040, 2059),
)
STATISTICS = ("median", "p10", "p90")


def hd35_input(s: Scenario, statistic: str) -> Input:
    return Input(SOURCE, f"cmip6-hd35-{s.start}-{s.end}{'' if s.code == 'historical' else '-' + s.code}-{statistic}")


HD35_INPUTS: dict[tuple[str, str], Input] = {(s.id, st): hd35_input(s, st) for s in SCENARIOS for st in STATISTICS}

DEGC = Unit(code="degC", label="degrees Celsius", short="°C")
HOT_DAYS = Unit(code="days", label="days per year with a daily maximum of 35 °C or more", short="days")

WB_BOUNDARIES = (
    "Each country or territory as drawn by the World Bank's official boundaries (an area-weighted mean of the 0.25° "
    "grid cells inside it); World is CCKP's global aggregate of the same grid."
)


class CckpFormatError(ValueError):
    pass


# --- reading ------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Collection:
    """The parts of a CCKP collection URL."""

    collection: str
    type: str
    variable: str
    product: str
    start: int
    end: int
    statistic: str
    scenario: str
    model: str
    geocode: str


def collection_of(url: str | None) -> Collection:
    m = COLLECTION_URL.fullmatch(url or "")
    if not m:
        raise CckpFormatError(f"{url!r} is not a CCKP collection URL this module can read")
    g = m.groupdict()
    return Collection(**{**g, "start": int(g["start"]), "end": int(g["end"])})  # type: ignore[arg-type]


def expect(c: Collection, name: str, **want: object) -> None:
    """Stop unless the URL's collection has every field in `want`."""
    wrong = {k: getattr(c, k) for k, v in want.items() if getattr(c, k) != v}
    if wrong:
        raise CckpFormatError(f"{name}: the URL names {wrong}, expected { ({k: want[k] for k in wrong}) }")


def read_payload(raw: bytes, name: str) -> dict[str, dict[str, Decimal]]:
    """The `data` object of a CCKP API response, every value as the printed decimal."""
    doc = json.loads(raw, parse_float=Decimal, parse_int=Decimal)
    if not isinstance(doc, dict) or set(doc) != {"metadata", "data"}:
        raise CckpFormatError(f"{name}: expected keys metadata and data")
    meta = doc["metadata"]
    if meta.get("status") != "success" or meta.get("messages"):
        raise CckpFormatError(f"{name}: API status {meta.get('status')!r}, messages {meta.get('messages')!r}")
    data = doc["data"]
    if not isinstance(data, dict) or not data:
        raise CckpFormatError(f"{name}: data is empty or not an object")
    for code, series in data.items():
        if not isinstance(series, dict):
            raise CckpFormatError(f"{name}: {code} is not a series object")
        for stamp, v in series.items():
            if not isinstance(v, Decimal):
                raise CckpFormatError(f"{name}: {code} {stamp} is {v!r}, not a number")
    return data


def require_stamps(data: dict[str, dict[str, Decimal]], years: range, name: str) -> None:
    """Every series holds exactly "YYYY-07" for each year in `years`, in order."""
    want = [f"{y}-07" for y in years]
    for code, series in data.items():
        if list(series) != want:
            got = list(series)
            raise CckpFormatError(f"{name}: {code} has stamps {got[:2]}…{got[-2:]} ({len(got)}), expected {want[0]}…")


def read_file(f: InputFile, name: str, **want: object) -> tuple[Collection, dict[str, dict[str, Decimal]]]:
    c = collection_of(str(f.snapshot.url) if f.snapshot.url else None)
    expect(c, name, **want)
    data = read_payload(f.path.read_bytes(), name)
    if c.type == "timeseries":
        require_stamps(data, range(c.start, c.end + 1), name)
    else:
        require_stamps(data, range(c.start, c.start + 1), name)
    if c.geocode == "global" and set(data) != {"GLOBAL"}:
        raise CckpFormatError(f"{name}: a global file should hold only GLOBAL, found {sorted(data)[:5]}")
    if c.geocode == "all_countries" and "GLOBAL" in data:
        raise CckpFormatError(f"{name}: the all_countries file holds GLOBAL")
    return c, data


def entities_of(codes: set[str], name: str) -> dict[str, str]:
    """Producer code -> our entity for every code. Raises on a code geo.resolve does not know, and on two codes
    resolving to one entity."""
    mapped: dict[str, str] = {}
    for code in sorted(codes):
        try:
            mapped[code] = geo.resolve(ALIASES.get(code, code), "iso3")
        except geo.UnknownEntity as e:
            raise CckpFormatError(
                f"{name}: CCKP code {code!r} has no entity ({e}); declare it in ALIASES (or envdash/geo.py) after "
                "checking what CCKP means by it"
            ) from None
    targets = list(mapped.values())
    dupes = sorted({t for t in targets if targets.count(t) > 1})
    if dupes:
        raise CckpFormatError(f"{name}: several CCKP codes resolve to {dupes}")
    return mapped


def _fetched(files: list[InputFile]) -> str:
    return max(f.snapshot.date_accessed for f in files).isoformat()


# --- ERA5 temperature ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Era5:
    annual: dict[str, list[tuple[int, Decimal]]]
    """Our entity -> [(year, °C)] in year order, countries and WLD."""
    climatology: dict[str, Decimal]
    """Our entity -> CCKP's 1991–2020 mean (°C)."""
    start: int
    end: int
    vintage: str


def read_era5(files: dict[str, InputFile]) -> Era5:
    era5 = {"collection": "era5-x0.25", "variable": "tas", "statistic": "mean", "scenario": "historical"}
    era5 |= {"model": "era5_x0.25"}
    series = {"type": "timeseries", "product": "timeseries", **era5}
    ts, countries = read_file(files[TAS_COUNTRIES.key], TAS_COUNTRIES.key, geocode="all_countries", **series)
    tg, world = read_file(files[TAS_GLOBAL.key], TAS_GLOBAL.key, geocode="global", **series)
    if (ts.start, ts.end) != (tg.start, tg.end):
        raise CckpFormatError(f"country series {ts.start}-{ts.end} and global series {tg.start}-{tg.end} differ")
    clim = {"type": "climatology", "product": "climatology", "start": CLIMATOLOGY[0], "end": CLIMATOLOGY[1], **era5}
    _, c_countries = read_file(files[CLIM_COUNTRIES.key], CLIM_COUNTRIES.key, geocode="all_countries", **clim)
    _, c_world = read_file(files[CLIM_GLOBAL.key], CLIM_GLOBAL.key, geocode="global", **clim)
    if set(c_countries) != set(countries):
        diff = sorted(set(c_countries) ^ set(countries))
        raise CckpFormatError(f"the climatology and the annual series cover different areas: {diff}")
    if not (ts.start <= CLIMATOLOGY[0] and CLIMATOLOGY[1] <= ts.end):
        raise CckpFormatError(f"the series {ts.start}-{ts.end} does not cover {CLIMATOLOGY[0]}-{CLIMATOLOGY[1]}")
    mapped = entities_of(set(countries), TAS_COUNTRIES.key)
    mapped["GLOBAL"] = geo.resolve(ALIASES["GLOBAL"], "iso3")
    raw_annual = countries | world
    raw_clim = c_countries | c_world
    annual: dict[str, list[tuple[int, Decimal]]] = {}
    climatology: dict[str, Decimal] = {}
    for code, ent in mapped.items():
        annual[ent] = [(int(stamp[:4]), v) for stamp, v in raw_annual[code].items()]
        climatology[ent] = next(iter(raw_clim[code].values()))
    vintage = f"era5-x0.25 {ts.start}-{ts.end}, fetched {_fetched(list(files.values()))}"
    return Era5(annual, climatology, ts.start, ts.end, vintage)


def check_climatology(e: Era5) -> Decimal:
    """The largest |mean of the printed 1991–2020 annual values − printed climatology|; stops above the tolerance."""
    worst = Decimal(0)
    bad: list[str] = []
    n = CLIMATOLOGY[1] - CLIMATOLOGY[0] + 1
    for ent, series in e.annual.items():
        vals = [v for y, v in series if CLIMATOLOGY[0] <= y <= CLIMATOLOGY[1]]
        assert len(vals) == n
        diff = abs(sum(vals, Decimal(0)) / n - e.climatology[ent])
        worst = max(worst, diff)
        if diff > CLIMATOLOGY_TOLERANCE:
            bad.append(f"{ent} {diff:.4f}")
    if bad:
        raise CckpFormatError(
            f"the 1991-2020 climatology differs from the mean of the annual values by more than rounding "
            f"(±{CLIMATOLOGY_TOLERANCE} °C): {bad[:10]}"
        )
    return worst


def absolute_observations(e: Era5) -> list[Observation]:
    return [
        Observation(entity=ent, period=f"{y:04d}", value=float(v)) for ent in sorted(e.annual) for y, v in e.annual[ent]
    ]


def change_observations(e: Era5) -> list[Observation]:
    return [
        Observation(entity=ent, period=f"{y:04d}", value=float(v - e.climatology[ent]))
        for ent in sorted(e.annual)
        for y, v in e.annual[ent]
    ]


def _era5_steps(e: Era5) -> list[str]:
    return [
        f"Read CCKP's ERA5 0.25° annual mean near-surface air temperature for every country and territory and for "
        f'the globe, {e.start}–{e.end} (absolute °C; CCKP stamps each year\'s value "YYYY-07", read as the year).',
        "Mapped CCKP's codes to the site's entities: ISO 3166-1 alpha-3 codes as they are, KSV (CCKP's code for "
        "Kosovo) to KOS and GLOBAL to WLD. Every CCKP area is published, including the overseas territories Natural "
        "Earth draws inside another country (envdash/geo.py EXTRA_TERRITORIES).",
    ]


def _run_absolute(files: dict[str, InputFile]) -> Result:
    e = read_era5(files)
    check_climatology(e)
    return Result(observations=absolute_observations(e), vintage=e.vintage, steps=_era5_steps(e))


def _run_change(files: dict[str, InputFile]) -> Result:
    e = read_era5(files)
    worst = check_climatology(e)
    steps = _era5_steps(e)
    steps.append(
        "Read CCKP's published ERA5 1991–2020 annual climatology for the same areas and checked that it belongs to "
        "the same series: for every area the mean of the 30 printed annual values 1991–2020 is within 0.01 °C of it "
        f"(largest difference {worst.normalize():f} °C, rounding only)."
    )
    steps.append(
        "Subtracted each area's 1991–2020 climatology from each of its annual values (exact decimal arithmetic on the "
        "printed digits). The baseline is CCKP's own; CCKP publishes no 1951–1980 ERA5 climatology, and none is "
        "computed here."
    )
    return Result(
        observations=change_observations(e),
        vintage=e.vintage,
        steps=steps,
        changes="annual mean temperatures expressed as the difference from CCKP's published 1991–2020 mean for the "
        "same area.",
    )


# --- CMIP6 hot days -----------------------------------------------------------------------------------------------


def hd35_observations(files: dict[str, InputFile]) -> list[Observation]:
    """Median with the 10th–90th percentile range, per scenario and area."""
    values: dict[tuple[str, str], dict[str, Decimal]] = {}
    codes: set[str] | None = None
    for s in SCENARIOS:
        for st in STATISTICS:
            i = HD35_INPUTS[(s.id, st)]
            _, data = read_file(
                files[i.key],
                i.key,
                collection="cmip6-x0.25",
                type="climatology",
                variable="hd35",
                product="climatology",
                start=s.start,
                end=s.end,
                statistic=st,
                scenario=s.code,
                model="ensemble_all",
                geocode="all_countries",
            )
            if codes is None:
                codes = set(data)
            elif set(data) != codes:
                raise CckpFormatError(f"{i.key} covers different areas: {sorted(set(data) ^ codes)}")
            values[(s.id, st)] = {code: next(iter(series.values())) for code, series in data.items()}
    assert codes is not None
    mapped = entities_of(codes, "cmip6-hd35")
    obs: list[Observation] = []
    for code, ent in sorted(mapped.items(), key=lambda kv: kv[1]):
        for s in SCENARIOS:
            obs.append(
                Observation(
                    entity=ent,
                    period=s.period,
                    value=float(values[(s.id, "median")][code]),
                    lower=float(values[(s.id, "p10")][code]),
                    upper=float(values[(s.id, "p90")][code]),
                    interval="range",
                    status="final" if s.code == "historical" else "projection",
                    dims={"scenario": s.id},
                )
            )
    return obs


def _run_hd35(files: dict[str, InputFile]) -> Result:
    obs = hd35_observations(files)
    steps = [
        "Read CCKP's CMIP6 0.25° climatologies of hd35, the number of days a year with a daily maximum temperature of "
        "35 °C or more, for every country and territory: the multi-model ensemble median, 10th and 90th percentiles "
        "for the 1995–2014 historical runs and for 2040–2059 under SSP1-2.6, SSP2-4.5 and SSP5-8.5.",
        "Published the median as the value and the 10th and 90th percentiles as the range, as printed. Mapped CCKP's "
        "codes to the site's entities: ISO 3166-1 alpha-3 codes as they are and KSV (CCKP's code for Kosovo) to "
        "KOS. Every CCKP area is published, including the overseas territories Natural Earth draws inside another "
        "country (envdash/geo.py EXTRA_TERRITORIES).",
    ]
    vintage = f"cmip6-x0.25 hd35, fetched {_fetched(list(files.values()))}"
    return Result(observations=obs, vintage=vintage, steps=steps)


# --- indicators ---------------------------------------------------------------------------------------------------

ERA5_INPUTS = (TAS_COUNTRIES, TAS_GLOBAL, CLIM_COUNTRIES, CLIM_GLOBAL)


def transforms(paths: Paths) -> list[Transform]:
    module = Path(__file__)
    return [
        Transform(
            spec=Spec(
                id="temp.wb-cckp.era5-annual-absolute",
                title="Annual mean temperature by country (ERA5, World Bank CCKP)",
                description="Average near-surface air temperature over each country's area for every year since 1950, "
                "in degrees Celsius, from the ERA5 reanalysis as aggregated by the World Bank's Climate Change "
                "Knowledge Portal. These are reanalysis averages over the whole country, not weather-station records; "
                "World is the global average of the same reanalysis.",
                kind="series",
                unit=DEGC,
                display=Display(decimals=1),
                scope=Scope(
                    geography=WB_BOUNDARIES,
                    baseline=None,
                    basis="Absolute temperature (not an anomaly). ERA5 reanalysis (Copernicus Climate Change Service), "
                    "2 m air temperature, annual mean, aggregated by CCKP.",
                ),
                geo_coverage="mixed",
                headline_entity="WLD",
            ),
            inputs=ERA5_INPUTS,
            run=_run_absolute,
            module_file=module,
            validation=Validation(min_rows=18_000, value_range=(-40.0, 35.0)),
        ),
        Transform(
            spec=Spec(
                id="temp.wb-cckp.era5-annual-1991-2020",
                title="Annual temperature compared with 1991–2020 by country (ERA5, World Bank CCKP)",
                description="How much warmer or cooler each year since 1950 was than the 1991–2020 average, for each "
                "country and for the world, from the ERA5 reanalysis as aggregated by the World Bank's Climate Change "
                "Knowledge Portal. The 1991–2020 average is the one CCKP publishes for the same area; it is a recent "
                "baseline, so values near zero already include most of the warming since pre-industrial times.",
                kind="derived",
                unit=DEGC,
                display=Display(decimals=2),
                scope=Scope(
                    geography=WB_BOUNDARIES,
                    baseline="1991–2020 mean of the same CCKP ERA5 aggregate (CCKP's published climatology)",
                    basis="ERA5 reanalysis (Copernicus Climate Change Service), 2 m air temperature, annual mean, "
                    "aggregated by CCKP; difference from CCKP's 1991–2020 climatology computed here.",
                ),
                geo_coverage="mixed",
                headline_entity="WLD",
            ),
            inputs=ERA5_INPUTS,
            run=_run_change,
            module_file=module,
            validation=Validation(min_rows=18_000, value_range=(-10.0, 10.0)),
        ),
        Transform(
            spec=Spec(
                id="hot-days-35c.wb-cckp.cmip6",
                title="Days a year at 35 °C or hotter by country, 1995–2014 and 2040–2059 (CMIP6, World Bank CCKP)",
                description="The average number of days a year whose maximum temperature reaches 35 °C or more, over "
                "each country's area, from the CMIP6 climate models as bias-corrected, downscaled and aggregated by "
                "the World Bank's Climate Change Knowledge Portal. 1995–2014 is the models' simulation of the recent "
                "past (not observations); 2040–2059 is projected under three emissions scenarios. The value is the "
                "median of the models and the range runs from the 10th to the 90th percentile of the models.",
                kind="series",
                unit=HOT_DAYS,
                display=Display(decimals=1),
                scope=Scope(
                    geography="Each country or territory as drawn by the World Bank's official boundaries (an "
                    "area-weighted mean of the 0.25° grid cells inside it). No world value.",
                    baseline=None,
                    basis="CMIP6 multi-model ensemble (bias-corrected and downscaled to 0.25° by CCKP): median, with "
                    "the 10th–90th percentile of the models as the range. Days with daily maximum temperature >= "
                    "35 °C, averaged over each 20-year period. 1995–2014 from the historical runs; 2040–2059 under "
                    "SSP1-2.6, SSP2-4.5 and SSP5-8.5.",
                ),
                geo_coverage="country",
                # There is no world value: CCKP's global aggregate would average over the whole globe, oceans
                # included. India under SSP2-4.5 is the headline because it is the country the source research
                # checked by hand (1995–2014 77.88 days, 2040–2059 SSP2-4.5 94.78 days on 2026-10-04).
                headline_entity="IND",
                headline_dims=(("scenario", "ssp245"),),
                dimensions=(
                    Dimension(
                        id="scenario",
                        label="Period and scenario",
                        values=[DimensionValue(id=s.id, label=s.label) for s in SCENARIOS],
                    ),
                ),
            ),
            inputs=tuple(HD35_INPUTS[(s.id, st)] for s in SCENARIOS for st in STATISTICS),
            run=_run_hd35,
            module_file=module,
            validation=Validation(min_rows=900, value_range=(0.0, 366.0)),
        ),
    ]
