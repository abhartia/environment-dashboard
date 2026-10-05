"""IEA Global EV Data Explorer (Global EV Outlook 2026): the electric share of new vehicle sales, by country and mode.

Input: the historical CSV from api.iea.org/evs (registry entry iea-gevo-2026, artifact evs-historical), columns
region, category, parameter, mode, powertrain, year, unit, value; and the Global EV Outlook 2026 report PDF (artifact
report-pdf), read only for the statement used as a publisher check.

Rows used: parameter "EV sales share", category "Historical", powertrain "EV" (battery-electric and plug-in hybrid
vehicles together, as the IEA defines EV), unit "percent", for the modes Cars, Vans, Buses, Trucks and "2 and 3
wheelers". Nothing else in the file is read. In particular the car price rows (parameters price_*_2025USD and
sales-historical-price-data, which the report credits as "IEA analysis based on data from S&P Global Mobility") are
third-party material that the IEA's notice does not license; the transform counts them in a step and never reads
their values.

Values. The file stores single-precision numbers (0.012000000104308128 for 0.012). Each value is published as the
shortest decimal that gives back the same single-precision number (so 0.012, 25, 4.4); a value that is not a
single-precision number stops the build. The IEA rounds its published shares (World cars 2025: 25%).

Shares above 100%. In the file with sha256 43de47975d08… the United Arab Emirates' van sales share is 200% to 310% in
2021-2025, while its car and truck shares are below 20%. A share of sales above 100% cannot be one, so such a value
is published as null with a missing_reason quoting it; nothing is substituted.

Entities. Region names are matched to pipeline/geo/entities.csv by name, with the aliases in NAME_ALIASES. The IEA's
regional groupings (AGGREGATES) are not published: the file does not list their members. Any other name stops the
build.

Edition. The API carries no version label and no Last-Modified date. The vintage is the edition, "Global EV Outlook
2026", and the build stops if the file holds a year after 2025 (a later edition), so that a new edition is labelled
by a person.

Licence. CC BY 4.0 subject to the IEA Notice for CC-licensed Content; the published values are an adaptation
(selected rows, re-expressed numbers), so the build credit carries the IEA's derived-work disclaimer (Result.changes
selects it).

Publisher check: World, cars, 2025, "The sales share of electric cars in the overall car market increased to 25%."
(report page 16), also found in the PDF's text on every build.
"""

from __future__ import annotations

import io
import struct
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import polars as pl
import pypdf

from envdash import geo, textmatch
from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, PublisherCheck, Result, Spec, Transform, Validation

SOURCE = "iea-gevo-2026"
EVS = Input(SOURCE, "evs-historical")
REPORT = Input(SOURCE, "report-pdf")
REPORT_URL = "https://iea.blob.core.windows.net/assets/857aa690-2a43-453f-9f12-147cc8f0a1dd/GlobalEVOutlook2026.pdf"
VINTAGE = "Global EV Outlook 2026"
LAST_YEAR = 2025
COLUMNS = ["region", "category", "parameter", "mode", "powertrain", "year", "unit", "value"]
PARAMETER = "EV sales share"
THIRD_PARTY_PREFIX = ("price_", "sales-historical-price-data")

MODES: dict[str, tuple[str, str]] = {
    "Cars": ("cars", "Cars"),
    "Vans": ("vans", "Vans"),
    "Buses": ("buses", "Buses"),
    "Trucks": ("trucks", "Trucks"),
    "2 and 3 wheelers": ("two-three-wheelers", "Two- and three-wheelers"),
}
# IEA region name -> our entity code, where the name is not the one in pipeline/geo/entities.csv (file of
# sha256 43de47975d08…).
NAME_ALIASES = {
    "Czech Republic": "CZE",
    "Korea": "KOR",
    "Lao PDR": "LAO",
    "Turkiye": "TUR",
    "USA": "USA",
    "Viet Nam": "VNM",
}
AGGREGATES = frozenset(
    {
        "Advanced Economies",
        "Africa",
        "Asia Pacific",
        "Developing Economies excl. China",
        "Europe",
        "European Union",
        "Latin America",
        "Middle East and Caspian",
        "Rest of the world",
        "Southeast Asia",
    }
)

CHECK_PAGE = 16
Q_WORLD = "The sales share of electric cars in the overall car market increased to 25%."


class IeaFormatError(ValueError):
    pass


def read_table(raw: bytes) -> pl.DataFrame:
    df = pl.read_csv(raw, infer_schema=False)
    if df.columns != COLUMNS:
        raise IeaFormatError(f"columns {df.columns} != {COLUMNS}")
    return df


def shortest_single(text: str) -> Decimal:
    """The shortest decimal whose single-precision value equals that of `text`, which must be single-precision."""
    v = float(text)
    packed = struct.pack("<f", v)
    if struct.unpack("<f", packed)[0] != v:
        raise IeaFormatError(f"{text!r} is not a single-precision number; re-read the file's format")
    for digits in range(1, 10):
        cand = f"{v:.{digits}g}"
        if struct.pack("<f", float(cand)) == packed:
            return Decimal(format(Decimal(cand), "f"))  # positional notation: 310, not 3.1E+2
    raise AssertionError("9 significant digits always identify a single-precision number")


def entity_of(region: str) -> str | None:
    if region in AGGREGATES:
        return None
    if region in NAME_ALIASES:
        return geo.resolve(NAME_ALIASES[region], "iso3")
    return geo.resolve(region, "name")


def sales_share_rows(df: pl.DataFrame) -> pl.DataFrame:
    rows = df.filter(pl.col("parameter") == PARAMETER)
    bad = rows.filter(
        (pl.col("category") != "Historical")
        | (pl.col("powertrain") != "EV")
        | (pl.col("unit") != "percent")
        | ~pl.col("mode").is_in(list(MODES))
        | pl.col("region").is_null()
    )
    if bad.height:
        raise IeaFormatError(f"unexpected {PARAMETER} rows, e.g. {bad.row(0)}")
    years = rows["year"].cast(pl.Int32)
    if years.max() > LAST_YEAR:  # type: ignore[operator]
        raise IeaFormatError(f"the file has {years.max()}, after {LAST_YEAR}: a new edition needs a new vintage label")
    return rows


def third_party_count(df: pl.DataFrame) -> int:
    return df.filter(
        pl.col("parameter").str.starts_with(THIRD_PARTY_PREFIX[0]) | (pl.col("parameter") == THIRD_PARTY_PREFIX[1])
    ).height


def observations(df: pl.DataFrame) -> tuple[list[Observation], list[str]]:
    """Observations sorted by entity, mode and year; and the aggregate names left out."""
    rows = sales_share_rows(df)
    out: dict[tuple[str, str, str], Observation] = {}
    left_out: set[str] = set()
    for region, mode, year, value in rows.select("region", "mode", "year", "value").iter_rows():
        ent = entity_of(region)
        if ent is None:
            left_out.add(region)
            continue
        dim = MODES[mode][0]
        key = (ent, dim, year)
        if key in out:
            raise IeaFormatError(f"two {PARAMETER} values for {region} {mode} {year}")
        if value is None or value == "":
            raise IeaFormatError(f"{region} {mode} {year}: empty value")
        v = shortest_single(value)
        if v > 100:
            out[key] = Observation(
                entity=ent,
                period=year,
                value=None,
                missing_reason=f"Not published: the IEA's file gives {v}% for this share of sales, which cannot be a "
                "share of the vehicles sold.",
                dims={"mode": dim},
            )
        else:
            out[key] = Observation(entity=ent, period=year, value=float(v), dims={"mode": dim})
    order = [d for d, _ in MODES.values()]
    keys = sorted(out, key=lambda k: (k[0], order.index(k[1]), k[2]))
    return [out[k] for k in keys], sorted(left_out)


@lru_cache(maxsize=1)
def _page_text(path: Path, page: int) -> str:
    return pypdf.PdfReader(io.BytesIO(path.read_bytes())).pages[page - 1].extract_text()


def run(files: dict[str, InputFile]) -> Result:
    f = files[EVS.key]
    df = read_table(f.path.read_bytes())
    obs, left_out = observations(df)
    if not textmatch.contains(_page_text(files[REPORT.key].path, CHECK_PAGE), Q_WORLD):
        raise IeaFormatError(f"page {CHECK_PAGE} of the report no longer says {Q_WORLD!r}")
    years = sorted({o.period for o in obs})
    return Result(
        observations=obs,
        vintage=VINTAGE,
        date_published="2026-05-20",
        steps=[
            f"Read the IEA Global EV Data Explorer's historical file from api.iea.org/evs (fetched "
            f"{f.snapshot.date_accessed}, sha256 {f.snapshot.sha256[:12]}…), which carries no version label; its "
            f"latest year is {years[-1]}, the year the {VINTAGE} reports on.",
            f"Kept the '{PARAMETER}' rows (category Historical, powertrain EV: battery-electric and plug-in hybrid "
            "together; unit percent) for cars, vans, buses, trucks and two- and three-wheelers, "
            f"{years[0]}–{years[-1]}. The {third_party_count(df):,} car price rows (price_* and "
            "sales-historical-price-data), based on S&P Global Mobility data that the IEA's licence does not cover, "
            "were not read.",
            "Matched IEA region names to countries in pipeline/geo/entities.csv by name (Czech Republic, Korea, Lao "
            "PDR, Turkiye, USA and Viet Nam by declared alias). The IEA's regional groupings were left out because "
            f"the file does not list their members: {', '.join(left_out)}.",
            "Published each value as the shortest decimal that reproduces the single-precision number stored in the "
            "file (for example 0.012 for 0.012000000104308128).",
            "Left as null, with the reason, every value above 100%, which cannot be a share of sales. In this "
            "vintage: "
            + ("; ".join(f"{o.entity} {o.dims['mode']} {o.period}" for o in obs if o.value is None) or "none")
            + ".",
            f"Found the report's statement of the 2025 world share for cars on page {CHECK_PAGE} of the PDF.",
        ],
        changes="selected the EV sales share rows and wrote each stored single-precision value as the shortest decimal "
        "that reproduces it.",
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="ev.iea.sales-share",
                title="Electric share of new vehicle sales",
                description="The part of new cars, vans, buses, trucks and two- and three-wheelers sold each year "
                "since 2010 that were electric (battery-electric or plug-in hybrid), by country and for the world, as "
                "published by the IEA.",
                kind="series",
                unit=Unit(code="percent", label="percent of new vehicle sales", short="%"),
                display=Display(decimals=1),
                scope=Scope(
                    geography="Countries in the IEA's Global EV Data Explorer, and the world",
                    basis="Sales of battery-electric and plug-in hybrid vehicles (the IEA's 'EV') as a share of all "
                    "new vehicle sales of the same mode in the year. Values as rounded by the IEA.",
                ),
                geo_coverage="country",
                headline_entity="WLD",
                dimensions=(
                    Dimension(
                        id="mode",
                        label="Vehicle type",
                        values=[DimensionValue(id=i, label=lab) for i, lab in MODES.values()],
                    ),
                ),
                headline_dims=(("mode", "cars"),),
            ),
            inputs=(EVS, REPORT),
            run=run,
            module_file=Path(__file__),
            validation=Validation(min_rows=2000, value_range=(0.0, 100.0)),
            checks=(
                PublisherCheck(
                    source_id=SOURCE,
                    vintage=VINTAGE,
                    entity="WLD",
                    period="2025",
                    stated="25",
                    quote=Q_WORLD,
                    url=REPORT_URL,
                    dims=(("mode", "cars"),),
                ),
            ),
        )
    ]
