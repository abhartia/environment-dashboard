"""Indicators of Global Climate Change 2025 (IGCC; Forster et al. 2026, data release IGCC-2025a).

Three indicators, all in this one module so that its sha256 (recorded in every processing step and build key) covers
every line of code that decides them:

- warming.igcc-2025.human-induced: human-induced warming in each year since 1850 with the likely range;
- forcing.igcc-2025.erf-by-agent: effective radiative forcing relative to 1750 by agent, with the 5–95% range;
- budget.igcc-2025.remaining-1p5: the remaining carbon budget for 1.5 °C (50% likelihood) from the start of 2026,
  quoted from the paper and cross-checked against the data file it was rounded from.

Release. The DOI-pinned deposit is the Zenodo zip (artifact data-igcc-2025a). The transforms read single CSVs from
raw.githubusercontent.com at the commit that tag IGCC-2025a points to, so tests can use byte-exact slices of real
files. Every build checks that each CSV is byte-identical to the same path inside the zip and that the zip is the
release listed in RELEASES (its file name gives the release label, its top directory the short commit). Anything else
stops the build until a person adds the new release here.

Human-induced warming. The files give, for each of the three attribution methods IGCC uses (Global Warming Index,
Walsh; regularised optimal fingerprinting, Gillett; kriging for climate change, Ribes), annual percentiles of the
warming attributable to human activity, relative to 1850–1900 (the annual-mean definition). IGCC states its
assessment rule (ESSD Sect. 8, PDF page 17): "the best estimate is given as the 0.01 °C-precision mean of the 50th
percentiles from each method, and the likely range is given as the smallest 0.1 °C-precision range that envelops the
5th to 95th percentile ranges of each method." That rule is applied to every year: the mean of the three medians,
rounded half up to 0.01 °C (a mean exactly halfway stops the build rather than pick a side), and the range from the
lowest 5th percentile rounded down to 0.1 °C to the highest 95th percentile rounded up to 0.1 °C. IGCC published
the result of that rule for 2017 and 2025 (annual-mean rows of Assessment-Update-2025_GMST_headlines.csv); the
transform stops unless it reproduces both exactly, which is what shows the rule is read correctly. The Walsh
timeseries file's 2017 and 2025 medians differ from its own headline file in the third decimal (1.3289 against
1.3302 °C in 2025); the assessed values are the same either way, and the timeseries is what is used. IGCC's headline
for a single year (1.37 °C in 2025) uses a different, trend-based definition from the IPCC 1.5 °C report, for which
the release has no per-method annual percentiles, so it is not this series.

Effective radiative forcing. ERF_best/p05/p95_aggregates.csv: best estimate, 5th and 95th percentiles in W/m2,
1750–2025. Eighteen columns are published, one dimension value each. Their meaning is checked on every build: in the
best-estimate file the aggregates must equal the sum of their parts to 1e-6 W/m2 (aerosol = aerosol–radiation +
aerosol–cloud; well-mixed GHGs = CO2 + CH4 + N2O + halogenated gases; anthropogenic = well-mixed GHGs + ozone +
stratospheric water vapour + aerosol + contrails + land use + black carbon on snow; natural = solar + volcanic;
total = anthropogenic + natural). Three other columns (minor, nonco2wmghg, anthro_nonwmghg) are not defined in the
release and are not published. Percentile files are not summed: a percentile of a sum is not a sum of percentiles.

Remaining carbon budget. The paper's figure is published as quoted. The quote and the Table 8 caption that dates
it ("Estimates are expressed relative to the start of 2026.") must both be found on PDF page 22 (printed p. 3910).
The data file with the paper's Table 8 assumptions (MAGICC, 1.24 °C historical warming, 213 GtCO2 already emitted)
must give a 1.5 °C, 50% value within 5 GtCO2 of the quoted figure: the paper says its values are rounded to the
nearest 10 GtCO2, so a larger difference means the file and the paper do not describe the same estimate.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from pathlib import Path

import polars as pl

from envdash.models import (
    Dimension,
    DimensionValue,
    Display,
    LiteratureObservation,
    LiteratureValue,
    Observation,
    PublishedValueRef,
    Scope,
    Unit,
)
from envdash.paths import Paths
from envdash.transform import Input, InputFile, PublisherCheck, Result, Spec, Transform, Validation
from envdash.transforms.literature import verify_quote

SOURCE = "igcc-2025"
ZIP = Input(SOURCE, "data-igcc-2025a")
HEADLINES = Input(SOURCE, "warming-assessment-headlines")
METHODS = (
    Input(SOURCE, "warming-walsh-timeseries"),
    Input(SOURCE, "warming-gillett-timeseries"),
    Input(SOURCE, "warming-ribes-timeseries"),
)
ERF_BEST = Input(SOURCE, "erf-best-aggregates")
ERF_P05 = Input(SOURCE, "erf-p05-aggregates")
ERF_P95 = Input(SOURCE, "erf-p95-aggregates")
RCB = Input(SOURCE, "rcb-magicc-hdt-1p24")
PAPER = Input(SOURCE, "essd-paper-pdf")

PAPER_URL = "https://doi.org/10.5194/essd-18-3889-2026"


@dataclass(frozen=True)
class Release:
    commit: str
    """The ClimateIndicator/data commit the release tag points to (GitHub API)."""
    published: date
    """Zenodo publication date of the release."""


RELEASES: dict[str, Release] = {
    # GitHub API (read 2026-10-04): refs/tags/IGCC-2025a -> 0f2765dc2e96c98aebceb78fb12cd28fcfb9ac6f, committed
    # 2026-07-22; Zenodo record 21494229 "Version IGCC-2025a", published 2026-07-22.
    "IGCC-2025a": Release("0f2765dc2e96c98aebceb78fb12cd28fcfb9ac6f", date(2026, 7, 22)),
}

ZIP_URL = re.compile(r"/records/\d+/files/ClimateIndicator/data-(IGCC-\d{4}[a-z]?)\.zip/content$")
RAW_URL = re.compile(r"^https://raw\.githubusercontent\.com/ClimateIndicator/data/([0-9a-f]{40})/(data/base/[^?#]+)$")

DEGC = Unit(code="degC", label="degrees Celsius", short="°C")
WM2 = Unit(code="W/m2", label="watts per square metre", short="W/m²")
GTCO2 = Unit(code="GtCO2", label="billion tonnes of carbon dioxide", short="Gt CO₂")


class IgccFormatError(ValueError):
    pass


# --- release -----------------------------------------------------------------------------------------------------


def release_of(zip_url: str | None) -> tuple[str, Release]:
    m = ZIP_URL.search(zip_url or "")
    if not m:
        raise IgccFormatError(f"cannot read an IGCC release label from the zip URL {zip_url!r}")
    label = m.group(1)
    if label not in RELEASES:
        raise IgccFormatError(f"release {label} is not in RELEASES; add its commit and date after checking it")
    return label, RELEASES[label]


def zip_member(csv_url: str | None, release: Release) -> str:
    """The path inside the release zip that a raw.githubusercontent.com URL of the release commit names."""
    m = RAW_URL.match(csv_url or "")
    if not m:
        raise IgccFormatError(f"{csv_url!r} is not a raw.githubusercontent.com URL of ClimateIndicator/data")
    if m.group(1) != release.commit:
        raise IgccFormatError(f"{csv_url} is at commit {m.group(1)}, not the release commit {release.commit}")
    return f"ClimateIndicator-data-{release.commit[:7]}/{m.group(2)}"


def verify_against_zip(files: dict[str, InputFile], csvs: tuple[Input, ...]) -> tuple[str, Release]:
    """Check every CSV is byte-identical to its path in the DOI-pinned zip. Returns (release label, release)."""
    z = files[ZIP.key]
    label, release = release_of(str(z.snapshot.url) if z.snapshot.url else None)
    with zipfile.ZipFile(z.path) as zf:
        names = set(zf.namelist())
        for i in csvs:
            f = files[i.key]
            member = zip_member(str(f.snapshot.url) if f.snapshot.url else None, release)
            if member not in names:
                raise IgccFormatError(f"{i.key}: {member} is not in the {label} zip")
            if zf.read(member) != f.path.read_bytes():
                raise IgccFormatError(f"{i.key}: bytes differ from {member} in the {label} zip")
    return label, release


def _zip_step(label: str, z: InputFile, csvs: list[InputFile]) -> str:
    names = ", ".join(sorted(Path(str(f.snapshot.url)).name for f in csvs))
    return (
        f"Checked that each file read ({names}) is byte-identical to the same path inside the {label} release zip "
        f"deposited on Zenodo (doi:10.5281/zenodo.21494229, sha256 {z.snapshot.sha256[:12]}…)."
    )


# --- CSV helpers -------------------------------------------------------------------------------------------------


def read_rows(raw: bytes, name: str, required: tuple[str, ...]) -> tuple[list[str], list[dict[str, str | None]]]:
    df = pl.read_csv(raw, infer_schema=False)
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise IgccFormatError(f"{name}: columns {missing} missing (has {df.columns})")
    return df.columns, list(df.iter_rows(named=True))


def _dec(row: dict[str, str | None], col: str, name: str) -> Decimal:
    v = row[col]
    if v is None or v.strip() == "":
        raise IgccFormatError(f"{name}: empty {col} at time {row.get('time')}")
    return Decimal(v)


def annual_period(row: dict[str, str | None], name: str) -> str:
    """'2025.5,2025,2026' -> '2025'. Anything that is not one whole calendar year stops the build."""
    t, lo, hi = (_dec(row, c, name) for c in ("time", "timebound_lower", "timebound_upper"))
    if lo != lo.to_integral_value() or hi - lo != 1 or t != lo + Decimal("0.5"):
        raise IgccFormatError(
            f"{name}: time {row['time']} ({row['timebound_lower']}–{row['timebound_upper']}) is "
            "not a single calendar year"
        )
    return f"{int(lo):04d}"


# --- human-induced warming ---------------------------------------------------------------------------------------

P05, P50, P95 = "anthropogenic_p05", "anthropogenic_p50", "anthropogenic_p95"
HUNDREDTH, TENTH = Decimal("0.01"), Decimal("0.1")


@dataclass(frozen=True)
class Assessed:
    period: str
    best: Decimal
    lower: Decimal
    upper: Decimal


def method_series(raw: bytes, name: str) -> dict[str, tuple[Decimal, Decimal, Decimal]]:
    _, rows = read_rows(raw, name, ("time", "timebound_lower", "timebound_upper", P05, P50, P95))
    out: dict[str, tuple[Decimal, Decimal, Decimal]] = {}
    last = ""
    for r in rows:
        p = annual_period(r, name)
        if p <= last:
            raise IgccFormatError(f"{name}: year {p} does not follow {last}")
        last = p
        out[p] = (_dec(r, P05, name), _dec(r, P50, name), _dec(r, P95, name))
    return out


def best_estimate(medians: list[Decimal], period: str) -> Decimal:
    mean = sum(medians, Decimal(0)) / Decimal(len(medians))
    scaled = mean * 100
    if scaled - scaled.to_integral_value(rounding=ROUND_FLOOR) == Decimal("0.5"):
        raise IgccFormatError(f"{period}: mean of medians {mean} is exactly halfway between two 0.01 °C steps")
    return mean.quantize(HUNDREDTH, rounding=ROUND_HALF_UP)


def assess(methods: list[tuple[bytes, str]]) -> list[Assessed]:
    """IGCC's multi-method rule applied to each year the three method files share."""
    series = [method_series(raw, name) for raw, name in methods]
    periods = list(series[0])
    for (_, name), s in zip(methods[1:], series[1:], strict=True):
        if list(s) != periods:
            raise IgccFormatError(f"{name} covers years {min(s)}–{max(s)} ({len(s)}), not those of {methods[0][1]}")
    out: list[Assessed] = []
    for p in periods:
        vals = [s[p] for s in series]
        for lo, mid, hi in vals:
            if not lo <= mid <= hi:
                raise IgccFormatError(f"{p}: percentiles out of order ({lo}, {mid}, {hi})")
        out.append(
            Assessed(
                period=p,
                best=best_estimate([v[1] for v in vals], p),
                lower=min(v[0] for v in vals).quantize(TENTH, rounding=ROUND_FLOOR),
                upper=max(v[2] for v in vals).quantize(TENTH, rounding=ROUND_CEILING),
            )
        )
    return out


def producer_assessment(raw: bytes) -> dict[str, tuple[Decimal, Decimal, Decimal]]:
    """The single-year annual-mean rows of the producer's assessment file: {year: (p05, p50, p95)}."""
    name = "Assessment-Update-2025_GMST_headlines.csv"
    _, rows = read_rows(raw, name, ("time", "timebound_lower", "timebound_upper", P05, P50, P95, "notes"))
    out: dict[str, tuple[Decimal, Decimal, Decimal]] = {}
    for r in rows:
        note = (r["notes"] or "").strip()
        if note not in ("", "SR15 definition"):
            raise IgccFormatError(f"{name}: unknown note {note!r}; re-read the file before trusting these rules")
        if note or _dec(r, "timebound_upper", name) - _dec(r, "timebound_lower", name) != 1:
            continue  # trend-based (SR1.5) rows and decade rows are other definitions
        p = annual_period(r, name)
        if p in out:
            raise IgccFormatError(f"{name}: two annual-mean rows for {p}")
        out[p] = (_dec(r, P05, name), _dec(r, P50, name), _dec(r, P95, name))
    if not out:
        raise IgccFormatError(f"{name}: no single-year annual-mean rows to check the assessment rule against")
    return out


def check_against_producer(assessed: list[Assessed], producer: dict[str, tuple[Decimal, Decimal, Decimal]]) -> None:
    by = {a.period: a for a in assessed}
    for p, (lo, mid, hi) in sorted(producer.items()):
        a = by.get(p)
        if a is None:
            raise IgccFormatError(f"the producer assessed {p}, which the method files do not cover")
        if (a.lower, a.best, a.upper) != (lo, mid, hi):
            raise IgccFormatError(
                f"{p}: the rule gives {a.best} [{a.lower} to {a.upper}] but IGCC published {mid} [{lo} to {hi}]"
            )


def _warming(files: dict[str, InputFile]) -> Result:
    csvs = (HEADLINES, *METHODS)
    label, release = verify_against_zip(files, csvs)
    methods = [(files[i.key].path.read_bytes(), Path(str(files[i.key].snapshot.url)).name) for i in METHODS]
    assessed = assess(methods)
    producer = producer_assessment(files[HEADLINES.key].path.read_bytes())
    check_against_producer(assessed, producer)
    by = {a.period: a for a in assessed}
    reproduced = "; ".join(f"{p}: {by[p].best} [{by[p].lower} to {by[p].upper}] °C" for p in sorted(producer))
    obs = [
        Observation(
            entity="WLD",
            period=a.period,
            value=float(a.best),
            lower=float(a.lower),
            upper=float(a.upper),
            interval="likely",
        )
        for a in assessed
    ]
    return Result(
        observations=obs,
        vintage=label,
        date_published=release.published.isoformat(),
        steps=[
            _zip_step(label, files[ZIP.key], [files[i.key] for i in csvs]),
            "Read the annual 5th, 50th and 95th percentiles of human-induced (anthropogenic) warming relative to "
            "1850–1900 from the timeseries files of the three attribution methods IGCC assesses: Global Warming "
            "Index (Walsh), regularised optimal fingerprinting (Gillett) and kriging for climate change (Ribes).",
            "Applied IGCC's stated assessment rule to every year (ESSD Sect. 8): the best estimate is the mean of the "
            "three medians to 0.01 °C (rounded half up), and the likely range runs from the lowest 5th percentile "
            "rounded down to 0.1 °C to the highest 95th percentile rounded up to 0.1 °C.",
            "Checked that this reproduces every single-year annual-mean assessment IGCC published in "
            f"Assessment-Update-2025_GMST_headlines.csv ({reproduced}); it does, exactly. IGCC's headline single-"
            "year figure uses the trend-based definition of the IPCC 1.5 °C report instead, which is not this series.",
        ],
        changes="best estimate and likely range for each year computed from the three methods' annual percentiles "
        "with IGCC's stated multi-method assessment rule.",
    )


# --- effective radiative forcing ---------------------------------------------------------------------------------

ERF_COLUMNS = [
    "time",
    "timebound_lower",
    "timebound_upper",
    "CO2",
    "CH4",
    "N2O",
    "aerosol-radiation_interactions",
    "aerosol-cloud_interactions",
    "O3",
    "contrails",
    "land_use",
    "BC_on_snow",
    "H2O_stratospheric",
    "solar",
    "volcanic",
    "aerosol",
    "nonco2wmghg",
    "halogen",
    "anthro",
    "total",
    "minor",
    "natural",
    "wmghg",
    "anthro_nonwmghg",
]

# (file column, published dimension value id, label), in the order shown.
AGENTS: tuple[tuple[str, str, str], ...] = (
    ("anthro", "anthropogenic", "Total human-caused"),
    ("wmghg", "wmghg", "Well-mixed greenhouse gases (total)"),
    ("CO2", "co2", "Carbon dioxide"),
    ("CH4", "ch4", "Methane"),
    ("N2O", "n2o", "Nitrous oxide"),
    ("halogen", "halogens", "Halogenated gases"),
    ("O3", "o3", "Ozone"),
    ("H2O_stratospheric", "h2o-stratospheric", "Stratospheric water vapour from methane"),
    ("aerosol", "aerosol", "Aerosols (total)"),
    ("aerosol-radiation_interactions", "aerosol-radiation", "Aerosol–radiation interactions"),
    ("aerosol-cloud_interactions", "aerosol-cloud", "Aerosol–cloud interactions"),
    ("contrails", "contrails", "Contrails and contrail-induced cirrus"),
    ("land_use", "land-use", "Land use"),
    ("BC_on_snow", "bc-on-snow", "Black carbon on snow and ice"),
    ("natural", "natural", "Natural (solar and volcanic)"),
    ("solar", "solar", "Solar"),
    ("volcanic", "volcanic", "Volcanic"),
    ("total", "total", "Total (human-caused and natural)"),
)
UNPUBLISHED = ("minor", "nonco2wmghg", "anthro_nonwmghg")

SUMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("aerosol", ("aerosol-radiation_interactions", "aerosol-cloud_interactions")),
    ("wmghg", ("CO2", "CH4", "N2O", "halogen")),
    ("anthro", ("wmghg", "O3", "H2O_stratospheric", "aerosol", "contrails", "land_use", "BC_on_snow")),
    ("natural", ("solar", "volcanic")),
    ("total", ("anthro", "natural")),
)
SUM_TOLERANCE = Decimal("1e-6")

AGENT_DIM = Dimension(
    id="agent",
    label="Agent",
    values=[DimensionValue(id=d, label=label) for _, d, label in AGENTS],
)


def _erf_table(raw: bytes, name: str) -> list[dict[str, str | None]]:
    cols, rows = read_rows(raw, name, tuple(ERF_COLUMNS))
    if cols != ERF_COLUMNS:
        raise IgccFormatError(f"{name}: columns {cols} != expected {ERF_COLUMNS}")
    return rows


def erf_by_agent(best_raw: bytes, p05_raw: bytes, p95_raw: bytes) -> list[Observation]:
    best = _erf_table(best_raw, "ERF_best_aggregates.csv")
    p05 = _erf_table(p05_raw, "ERF_p05_aggregates.csv")
    p95 = _erf_table(p95_raw, "ERF_p95_aggregates.csv")
    if not (len(best) == len(p05) == len(p95)):
        raise IgccFormatError(f"ERF files have {len(best)}, {len(p05)} and {len(p95)} rows")
    obs: list[Observation] = []
    last = ""
    for b, lo, hi in zip(best, p05, p95, strict=True):
        period = annual_period(b, "ERF_best_aggregates.csv")
        if (
            annual_period(lo, "ERF_p05_aggregates.csv") != period
            or annual_period(hi, "ERF_p95_aggregates.csv") != period
        ):
            raise IgccFormatError(f"ERF files are not aligned at {period}")
        if period <= last:
            raise IgccFormatError(f"ERF_best_aggregates.csv: year {period} does not follow {last}")
        last = period
        for total, parts in SUMS:
            s = sum((_dec(b, c, "ERF_best_aggregates.csv") for c in parts), Decimal(0))
            if abs(s - _dec(b, total, "ERF_best_aggregates.csv")) > SUM_TOLERANCE:
                raise IgccFormatError(
                    f"ERF_best_aggregates.csv {period}: {total} {b[total]} is not the sum of {', '.join(parts)} ({s}); "
                    "the column meanings may have changed"
                )
        for col, dim, _ in AGENTS:
            obs.append(
                Observation(
                    entity="WLD",
                    period=period,
                    value=float(_dec(b, col, "ERF_best_aggregates.csv")),
                    lower=float(_dec(lo, col, "ERF_p05_aggregates.csv")),
                    upper=float(_dec(hi, col, "ERF_p95_aggregates.csv")),
                    interval="90ci",
                    dims={"agent": dim},
                )
            )
    return obs


def _erf(files: dict[str, InputFile]) -> Result:
    csvs = (ERF_BEST, ERF_P05, ERF_P95)
    label, release = verify_against_zip(files, csvs)
    obs = erf_by_agent(*(files[i.key].path.read_bytes() for i in csvs))
    return Result(
        observations=obs,
        vintage=label,
        date_published=release.published.isoformat(),
        steps=[
            _zip_step(label, files[ZIP.key], [files[i.key] for i in csvs]),
            "Read the best estimate, 5th and 95th percentile of effective radiative forcing relative to 1750 for "
            f"each year and each of {len(AGENTS)} agents and aggregates, as published (W/m²). The 5–95% range is "
            "IGCC's, taken from its own percentile files; nothing is re-estimated.",
            "Checked in the best-estimate file that each aggregate equals the sum of its parts to 1e-6 W/m² "
            "(aerosols, well-mixed greenhouse gases, total human-caused, natural, total), which confirms what each "
            f"column means. Not published: {', '.join(UNPUBLISHED)}, which the release does not define.",
        ],
    )


def _erf_check(dim: str, stated: str, quote: str) -> PublisherCheck:
    return PublisherCheck(
        source_id=SOURCE,
        vintage="IGCC-2025a",
        entity="WLD",
        period="2025",
        stated=stated,
        quote=quote,
        url=PAPER_URL,
        dims=(("agent", dim),),
    )


# The paper (ESSD Sect. 5, p. 3899, PDF page 11). Its data statement cites the v2026.06.02 release; every figure
# below is unchanged at IGCC-2025a to the stated precision (tests verify each quote is in the PDF snapshot).
WMGHG_QUOTE = (
    "The ERF from well-mixed GHGs is 3.58 [3.27 to 3.91] W m⁻² for 1750–2025, of which 2.37 W m⁻² is from CO₂, "
    "0.57 W m⁻² from CH₄, 0.23 W m⁻² from N₂O and 0.41 W m⁻² from halogenated gases."
)
ERF_CHECKS = (
    _erf_check(
        "anthropogenic",
        "3.10",
        "Total anthropogenic ERF has increased to 3.10 [2.35 to 3.83] W m⁻² in 2025 relative to 1750",
    ),
    _erf_check("wmghg", "3.58", WMGHG_QUOTE),
    _erf_check("co2", "2.37", WMGHG_QUOTE),
    _erf_check("ch4", "0.57", WMGHG_QUOTE),
    _erf_check("n2o", "0.23", WMGHG_QUOTE),
    _erf_check("halogens", "0.41", WMGHG_QUOTE),
    _erf_check(
        "aerosol",
        "-0.96",
        "The total aerosol ERF (sum of the ERF from aerosol–radiation interactions (ERFari) and aerosol–cloud "
        "interactions (ERFaci)) for 1750–2025 is −0.96 [−1.58 to −0.40] W m⁻²",
    ),
    _erf_check("o3", "0.48", "Ozone ERF is determined to be 0.48 [0.24 to 0.72] W m⁻² for 1750–2025"),
    _erf_check(
        "contrails",
        "0.07",
        "We estimate ERF from contrails and contrail-induced cirrus to be 0.07 [0.02 to 0.12] W m⁻² in 2025.",
    ),
    _erf_check("solar", "0.10", "we provide a single-year solar ERF for 2025 of +0.10 [+0.02 to +0.19] W m⁻²"),
)


# --- remaining carbon budget -------------------------------------------------------------------------------------

RCB_PAGE = 22
RCB_CAPTION = "Estimates are expressed relative to the start of 2026."
RCB_COLUMNS = ["Future_warming", "dT_targets", "0.1", "0.17", "0.33", "0.5", "0.67", "0.83", "0.9"]
RCB_TARGET = Decimal("1.5")
RCB_HISTORICAL = Decimal("1.24")
RCB_FILE_ASSUMPTIONS = ("magicc_True_fair_False", "_zecsd_0.0_", "_hdT_1.24", "_recEm213.csv")
FLOAT_SLACK = Decimal("1e-9")
"""The file writes its 0.1 °C steps as accumulated binary floats (1.5000000000000004); this only absorbs that."""
ROUNDING_HALF_STEP = Decimal(5)
"""The paper: "All values are rounded to the nearest 10 GtCO2." Half of that step."""

BUDGET = LiteratureValue(
    id="igcc-2025-rcb-1p5",
    indicator_id="budget.igcc-2025.remaining-1p5",
    source_id=SOURCE,
    artifact_id=PAPER.artifact_id,
    title="Remaining carbon budget for 1.5 °C from the start of 2026 (50% likelihood)",
    description=(
        "How much more carbon dioxide could be emitted from the start of 2026 while keeping a 50% chance of limiting "
        "global warming to 1.5 °C, as estimated by Indicators of Global Climate Change 2025. The likelihood reflects "
        "only uncertainty in how much warming each tonne of carbon dioxide causes. The estimate assumes deep cuts in "
        "other greenhouse gases and aerosols; IGCC states it could be around 200 billion tonnes higher or lower "
        "depending on how far those cuts go."
    ),
    unit=GTCO2,
    display=Display(decimals=0),
    scope=Scope(
        geography="World",
        basis=(
            "Carbon dioxide budget from the start of 2026 (1 January 2026) for 1.5 °C above 1850–1900, 50% "
            "likelihood considering only uncertainty in the transient climate response to cumulative emissions "
            "(TCRE); rounded by IGCC to the nearest 10 GtCO₂. Non-CO₂ warming from the AR6 scenarios that reach net "
            "zero CO₂, modelled with MAGICC; starts from 1.24 °C of human-induced warming over 2016–2025."
        ),
    ),
    geo_coverage="global-only",
    headline_entity="WLD",
    vintage="IGCC 2025 (Forster et al. 2026)",
    locator="Sect. 9, p. 3910 (with Table 8 on the same page)",
    pdf_page=RCB_PAGE,
    quote=(
        "Note that the RCB estimate of 130 GtCO₂ (50 % likelihood) would be exhausted in a little more than 3 years "
        "if global CO₂ emissions remain at 2025 levels (42 GtCO₂ yr⁻¹, from Table 1 with additional accounting for "
        "cement carbonation sink)."
    ),
    value_text="130 GtCO₂ (50 % likelihood)",
    value_reading=(
        '"130 GtCO₂ (50 % likelihood)" is published as 130 billion tonnes of carbon dioxide from the start of 2026, '
        "as Table 8 on the same page dates it."
    ),
    observations=[LiteratureObservation(entity="WLD", period="2026-01-01", value=130)],
    checked_on=date(2026, 10, 4),
    research_ref="docs/research/sources-atmosphere-and-temperature.json#Indicators of Global Climate Change 2025",
)


def budget_from_file(raw: bytes, url: str | None) -> Decimal:
    """The 1.5 °C, 50% value of the remaining-carbon-budget file with the paper's Table 8 assumptions."""
    name = Path(url or "").name
    missing = [a for a in RCB_FILE_ASSUMPTIONS if a not in name]
    if missing:
        raise IgccFormatError(f"{name!r} does not carry the Table 8 assumptions {missing} in its name")
    cols, rows = read_rows(raw, name, tuple(RCB_COLUMNS))
    if cols != RCB_COLUMNS:
        raise IgccFormatError(f"{name}: columns {cols} != expected {RCB_COLUMNS}")
    hits = [r for r in rows if abs(_dec(r, "dT_targets", name) - RCB_TARGET) <= FLOAT_SLACK]
    if len(hits) != 1:
        raise IgccFormatError(f"{name}: {len(hits)} rows for a {RCB_TARGET} °C target")
    r = hits[0]
    future = _dec(r, "Future_warming", name)
    if abs(_dec(r, "dT_targets", name) - future - RCB_HISTORICAL) > FLOAT_SLACK:
        raise IgccFormatError(f"{name}: target minus future warming is not the {RCB_HISTORICAL} °C historical warming")
    return _dec(r, "0.5", name)


def cross_check_budget(file_value: Decimal, quoted: Decimal) -> None:
    if abs(file_value - quoted) > ROUNDING_HALF_STEP:
        raise IgccFormatError(
            f"the data file gives {file_value} GtCO2, more than {ROUNDING_HALF_STEP} from the quoted {quoted}: the "
            "file and the paper do not describe the same estimate"
        )


def _budget(files: dict[str, InputFile]) -> Result:
    label, _ = verify_against_zip(files, (RCB,))
    pdf = files[PAPER.key]
    pdf_bytes = pdf.path.read_bytes()
    verify_quote(pdf_bytes, BUDGET.pdf_page, BUDGET.quote)
    verify_quote(pdf_bytes, BUDGET.pdf_page, RCB_CAPTION)
    (o,) = BUDGET.observations
    quoted = Decimal(str(o.value))
    rcb = files[RCB.key]
    file_value = budget_from_file(rcb.path.read_bytes(), str(rcb.snapshot.url) if rcb.snapshot.url else None)
    cross_check_budget(file_value, quoted)
    return Result(
        observations=[Observation(entity=o.entity, period=o.period, value=o.value, status=o.status)],
        vintage=label,
        date_published="2026-06-11",
        steps=[
            f"Quoted from {BUDGET.locator} of Forster et al. (2026), Earth Syst. Sci. Data 18. The quote was found in "
            f"the text of page {BUDGET.pdf_page} of the PDF snapshot (sha256 {pdf.snapshot.sha256[:12]}…) before "
            f"publishing, and so was the Table 8 caption that dates the budgets: {RCB_CAPTION!r}",
            f"Value: {BUDGET.value_reading}",
            _zip_step(label, files[ZIP.key], [rcb]),
            f"Cross-check: the release's budget file with the Table 8 assumptions ({Path(str(rcb.snapshot.url)).name}) "
            f"gives {file_value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)} GtCO₂ for {RCB_TARGET} °C at 50% "
            f"likelihood. The paper rounds to the nearest 10 GtCO₂; the build stops if the file value is more than "
            f"{ROUNDING_HALF_STEP} GtCO₂ from the quoted {o.value:g}. Difference: "
            f"{abs(file_value - quoted).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)} GtCO₂.",
        ],
        published_value=PublishedValueRef(document=SOURCE, locator=BUDGET.locator, quote=BUDGET.quote),
    )


# --- transforms --------------------------------------------------------------------------------------------------


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    return [
        Transform(
            spec=Spec(
                id="warming.igcc-2025.human-induced",
                title="Human-induced warming since 1850–1900, each year (IGCC 2025)",
                description="How much of the global surface warming in each year since 1850 was caused by human "
                "activity, relative to the 1850–1900 average, with the likely range. Indicators of Global Climate "
                "Change combines three attribution methods; this series applies its stated assessment rule to each "
                "year's annual-mean estimate. IGCC's own headline figure for a single year uses a trend-based "
                "definition from the IPCC 1.5 °C report and can differ by a few hundredths of a degree.",
                kind="series",
                unit=DEGC,
                display=Display(decimals=2),
                scope=Scope(
                    geography="Global mean",
                    baseline="1850–1900",
                    basis="Global mean surface temperature (GMST); warming attributed to all human influences "
                    "(greenhouse gases, aerosols and other human forcings), annual-mean definition. Best estimate: "
                    "mean of the three methods' medians to 0.01 °C. Likely range: the smallest 0.1 °C-step range "
                    "covering each method's 5–95% range.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(ZIP, HEADLINES, *METHODS),
            run=_warming,
            module_file=here,
            validation=Validation(min_rows=170, value_range=(-0.5, 3.0)),
            checks=(
                # No sentence in the paper states the annual-mean value for 2025 (its text gives the trend-based
                # 1.37 °C). The producer's own statement of it, for this release, is this row of its assessment file.
                PublisherCheck(
                    source_id=SOURCE,
                    vintage="IGCC-2025a",
                    entity="WLD",
                    period="2025",
                    stated="1.38",
                    quote="2025.5,2025,2026,1.1,1.38,1.7,1.1,1.63,2.1,-0.8,-0.26,0.2,-0.1,0.04,0.2,",
                    url="https://raw.githubusercontent.com/ClimateIndicator/data/"
                    "0f2765dc2e96c98aebceb78fb12cd28fcfb9ac6f/data/base/anthropogenic_warming/"
                    "Assessment-Update-2025_GMST_headlines.csv",
                ),
            ),
        ),
        Transform(
            spec=Spec(
                id="forcing.igcc-2025.erf-by-agent",
                title="Effective radiative forcing by agent since 1750 (IGCC 2025)",
                description="Effective radiative forcing: the change in the energy balance at the top of the "
                "atmosphere caused by each agent since 1750, after the atmosphere has adjusted. Positive values warm "
                "the planet, negative values (most aerosols) cool it. Best estimate with the 5–95% range for each "
                "year from 1750, by greenhouse gas, aerosol and other agents, from Indicators of Global Climate "
                "Change 2025.",
                kind="series",
                unit=WM2,
                display=Display(decimals=2),
                scope=Scope(
                    geography="Global mean",
                    baseline="1750",
                    basis="Single-year values (solar included as the single-year estimate, volcanic included), "
                    "relative to 1750; 5th to 95th percentile range from IGCC's ensemble.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(AGENT_DIM,),
                headline_dims=(("agent", "anthropogenic"),),
            ),
            inputs=(ZIP, ERF_BEST, ERF_P05, ERF_P95),
            run=_erf,
            module_file=here,
            validation=Validation(min_rows=270 * len(AGENTS), value_range=(-10.0, 6.0)),
            checks=ERF_CHECKS,
        ),
        Transform(
            spec=Spec(
                id=BUDGET.indicator_id,
                title=BUDGET.title,
                description=BUDGET.description,
                kind="published-value",
                unit=BUDGET.unit,
                display=BUDGET.display,
                scope=BUDGET.scope,
                geo_coverage=BUDGET.geo_coverage,
                headline_entity=BUDGET.headline_entity,
            ),
            inputs=(ZIP, PAPER, RCB),
            run=_budget,
            module_file=here,
            validation=Validation(min_rows=1, value_range=(0.0, 5000.0)),
        ),
    ]
