"""IPCC AR6 WGI Figure SPM.6 data (Li & Hauser 2021, CEDA): how many times as often extremes occur at each level of
global warming, relative to a climate without human influence.

One indicator, extremes.ipcc-ar6.frequency-by-warming-level, from the four frequency files of source
ipcc-ar6-wg1-spm6. Each file gives, at global warming levels of 1.0, 1.5, 2.0, 3.0 and 4.0 °C, how many times as often
an extreme that occurred once in 10 (or 50) years in 1850–1900 occurs: the median of the CMIP6 multi-model ensemble
and its 17th, 83rd, 5th and 95th percentiles. Published as printed: the median as the value and the 5th to 95th
percentile as the range, which is what the published figure shows. The 17th–83rd percentiles are read and checked
but not published. The four intensity files are registered but not published this round.

What each extreme is (from the caption in metadata.yaml, checked on every build): the hottest day of the year over
global land (TXx) that was exceeded once in a decade (hot-10yr) or once in 50 years (hot-50yr) in 1851–1900; the
wettest day of the year over global land (Rx1day) exceeded once in a decade in 1851–1900 (rain-10yr); and an
agricultural and ecological drought, annual mean total-column soil moisture below the 1850–1900 10th percentile, in
the AR6 regions projected to dry (drought-10yr). The caption lists 17 drying regions and says the Caribbean "is not
included in the calculation of the figure", so the drought values cover 16; the build counts the list and stops if
either number changes. Drought is not a global figure.

Files. metadata.yaml and the CEDA catalogue map panel a to the 10-year hot extreme, b to the 50-year hot extreme, c to
heavy precipitation and d to drought; the Readme's panel letters for precipitation and drought predate that layout.
Each file is identified by its URL (panel directory and file name), and the build checks that metadata.yaml lists it
under the same panel. The CSVs have CRLF line endings, the header "warming_level,50th,17th,83th,5th,95th" (sic), and a
trailing comma on some lines; the header and the five warming levels must be exactly as expected, and the five
percentiles must be in order.

Levels and dates. A warming level is not a year. Every value is dated 2021, the year of the assessment (dataset
version v20210809, published with the report on 9 August 2021), and is status projection: the IPCC calls all of them
"projected changes", including at 1 °C. The 3.0 °C level is in the files but not in the published figure (1, 1.5, 2
and 4 °C); its observations carry a note saying so. The published figure labels the 1 °C level "Present"; the world
has warmed further since, so the 1 °C values are not "today", and no value between levels is ever interpolated.

Checks against the published figure. The figure (SPM, p. 18) prints each median and range to one decimal, for
example "Once now likely occurs 2.8 times (1.8–3.2)". Each printed median is a publisher cross-check (tolerance half
the last digit), and the build stops unless each printed range equals the 5th and 95th percentiles rounded half up to
one decimal, which confirms which columns the figure draws as its range. The figure's words are display-only (IPCC
copyright); only these sixteen short labels are quoted, and pipeline/tests checks that each is on page 18 of the SPM
snapshot.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, PublisherCheck, Result, Spec, Transform, Validation

SOURCE = "ipcc-ar6-wg1-spm6"
METADATA = Input(SOURCE, "metadata")
PUBLISHED = "2021-08-09"
"""CEDA catalogue "Publication Date: 2021-08-09", the day the report was released."""
SPM_URL = "https://www.ipcc.ch/report/ar6/wg1/downloads/report/IPCC_AR6_WGI_SPM.pdf"
SPM_PAGE = 18
"""Figure SPM.6 is on page 18 of the SPM PDF (printed page 18)."""


@dataclass(frozen=True)
class Extreme:
    dim: str
    label: str
    input: Input
    path: str
    """panel directory and file name, as in the artifact URL and in metadata.yaml."""
    panel: str
    """The figure panel name metadata.yaml gives the file."""


EXTREMES: tuple[Extreme, ...] = (
    Extreme(
        "hot-10yr",
        "Hottest day of the year over land, once-in-10-year event",
        Input(SOURCE, "txx-freq-10yr"),
        "panel_a/TXx_freq_change_10_year_event.csv",
        "Hot temperature extremes",
    ),
    Extreme(
        "hot-50yr",
        "Hottest day of the year over land, once-in-50-year event",
        Input(SOURCE, "txx-freq-50yr"),
        "panel_b/TXx_freq_change_50_year_event.csv",
        "Hot temperature extremes",
    ),
    Extreme(
        "rain-10yr",
        "Wettest day of the year over land, once-in-10-year event",
        Input(SOURCE, "rx1day-freq-10yr"),
        "panel_c/Rx1day_freq_change_10_year_event.csv",
        "Extreme precipitation over land",
    ),
    Extreme(
        "drought-10yr",
        "Agricultural and ecological drought in drying regions, once-in-10-year event",
        Input(SOURCE, "drought-freq-10yr"),
        "panel_d/drought_freq_change_10_year_event.csv",
        "Drought",
    ),
)

HEADER = ["warming_level", "50th", "17th", "83th", "5th", "95th"]
LEVELS: tuple[tuple[str, str], ...] = (
    ("1.0", "1 °C of warming"),
    ("1.5", "1.5 °C of warming"),
    ("2.0", "2 °C of warming"),
    ("3.0", "3 °C of warming (in the data, not in the published figure)"),
    ("4.0", "4 °C of warming"),
)
NOT_IN_FIGURE = "3.0"
NOT_IN_FIGURE_NOTE = "In the data file but not shown in the published Figure SPM.6, which shows 1, 1.5, 2 and 4 °C."

URL = re.compile(r"^https://dap\.ceda\.ac\.uk/badc/ar6_wg1/data/spm/spm_06/(v(\d{4})\d{4})/(.+)$")
DRYING_REGIONS = re.compile(
    r"These regions include (?P<regions>.+?) \((?P<excluded>[A-Za-z]+) is not included in the calculation of the figure"
)
DRYING_LISTED = 17
DRYING_EXCLUDED = "Caribbean"
BASE_PERIODS = (
    "relative to conditions in the 2nd-half of the 19th century (1850-1900 for agricultural and ecological droughts, "
    "and 1851-1900 for hot extremes and precipitation extremes)"
)
RANGE_SHOWN = "The 50th, 5th, and 95th percentiles are shown on the figure"
TENTH = Decimal("0.1")

EXTREME_DIM = Dimension(
    id="extreme", label="Extreme", values=[DimensionValue(id=e.dim, label=e.label) for e in EXTREMES]
)
LEVEL_DIM = Dimension(
    id="level", label="Global warming level", values=[DimensionValue(id=v, label=label) for v, label in LEVELS]
)
TIMES = Unit(code="times", label="times as often as in 1850–1900", short="×")


class Spm6FormatError(ValueError):
    pass


@dataclass(frozen=True)
class Row:
    level: str
    p50: Decimal
    p17: Decimal
    p83: Decimal
    p05: Decimal
    p95: Decimal


def version_and_path(url: str | None) -> tuple[str, str, str]:
    """(version label, its year, path in the version directory) of a CEDA URL of this dataset."""
    m = URL.match(url or "")
    if not m:
        raise Spm6FormatError(f"{url!r} is not a file of the Figure SPM.6 dataset on dap.ceda.ac.uk")
    return m.group(1), m.group(2), m.group(3)


def read_frequency(raw: bytes, name: str) -> list[Row]:
    """The five rows of a frequency file, in file order. Trailing empty cells (the trailing comma) are dropped."""
    lines = [ln for ln in raw.decode("utf-8").splitlines() if ln.strip()]
    cells = [ln.split(",") for ln in lines]
    for c in cells:
        while c and c[-1] == "":
            c.pop()
    if cells[0] != HEADER:
        raise Spm6FormatError(f"{name}: header {cells[0]} != expected {HEADER}")
    rows: list[Row] = []
    for c in cells[1:]:
        if len(c) != len(HEADER):
            raise Spm6FormatError(f"{name}: row {c} does not have {len(HEADER)} cells")
        p50, p17, p83, p05, p95 = (Decimal(x) for x in c[1:])
        if not p05 <= p17 <= p50 <= p83 <= p95:
            raise Spm6FormatError(f"{name}: percentiles out of order at {c[0]} °C ({', '.join(c[1:])})")
        rows.append(Row(c[0], p50, p17, p83, p05, p95))
    levels = [r.level for r in rows]
    if levels != [v for v, _ in LEVELS]:
        raise Spm6FormatError(f"{name}: warming levels {levels} != expected {[v for v, _ in LEVELS]}")
    return rows


def check_metadata(raw: bytes) -> list[str]:
    """Check what the module assumes against the caption and file list in metadata.yaml; return the drying regions
    the caption lists."""
    meta = json.loads(raw.decode("utf-8"), strict=False)  # JSON text with raw line breaks inside its strings
    caption: str = meta["computation"]["description"]
    files: str = meta["description"]
    if BASE_PERIODS not in caption:
        raise Spm6FormatError("metadata.yaml: the caption no longer states the base periods this module labels")
    if RANGE_SHOWN not in files:
        raise Spm6FormatError("metadata.yaml: no longer says the figure shows the 50th, 5th and 95th percentiles")
    for e in EXTREMES:
        if f"- Data file: {e.path} ['{e.panel}', column 2 dark dots, columns 5 and 6 light dots]" not in files:
            raise Spm6FormatError(f"metadata.yaml does not list {e.path} under '{e.panel}'")
    m = DRYING_REGIONS.search(caption)
    if not m:
        raise Spm6FormatError("metadata.yaml: the caption no longer lists the drying regions")
    regions = m.group("regions").split(", ")
    if len(regions) != DRYING_LISTED or len(set(regions)) != len(regions):
        raise Spm6FormatError(f"metadata.yaml lists {len(regions)} drying regions, not {DRYING_LISTED}: {regions}")
    if m.group("excluded") != DRYING_EXCLUDED or DRYING_EXCLUDED not in regions:
        raise Spm6FormatError(f"metadata.yaml leaves out {m.group('excluded')!r}, not {DRYING_EXCLUDED}")
    return regions


# --- the published figure ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Printed:
    extreme: str
    level: str
    quote: str
    """The figure's label for this value, as printed (SPM p. 18)."""


PRINTED: tuple[Printed, ...] = (
    Printed("hot-10yr", "1.0", "Once now likely occurs 2.8 times (1.8–3.2)"),
    Printed("hot-10yr", "1.5", "will likely occur 4.1 times (2.8–4.7)"),
    Printed("hot-10yr", "2.0", "will likely occur 5.6 times (3.8–6.0)"),
    Printed("hot-10yr", "4.0", "will likely occur 9.4 times (8.3–9.6)"),
    Printed("hot-50yr", "1.0", "Once now likely occurs 4.8 times (2.3–6.4)"),
    Printed("hot-50yr", "1.5", "will likely occur 8.6 times (4.3–10.7)"),
    Printed("hot-50yr", "2.0", "will likely occur 13.9 times (6.9–16.6)"),
    Printed("hot-50yr", "4.0", "will likely occur 39.2 times (27.0–41.4)"),
    Printed("rain-10yr", "1.0", "Once now likely occurs 1.3 times (1.2–1.4)"),
    Printed("rain-10yr", "1.5", "will likely occur 1.5 times (1.4–1.7)"),
    Printed("rain-10yr", "2.0", "will likely occur 1.7 times (1.6–2.0)"),
    Printed("rain-10yr", "4.0", "will likely occur 2.7 times (2.3–3.6)"),
    Printed("drought-10yr", "1.0", "Once now likely occurs 1.7 times (0.7–4.1)"),
    Printed("drought-10yr", "1.5", "will likely occur 2.0 times (1.0–5.1)"),
    Printed("drought-10yr", "2.0", "will likely occur 2.4 times (1.3–5.8)"),
    Printed("drought-10yr", "4.0", "will likely occur 4.1 times (1.7–7.2)"),
)
PRINTED_VALUE = re.compile(r"(?P<median>\d+\.\d) times \((?P<lower>\d+\.\d)–(?P<upper>\d+\.\d)\)$")


def read_printed(quote: str) -> tuple[str, Decimal, Decimal]:
    """'... 2.8 times (1.8–3.2)' -> ('2.8', 1.8, 3.2): the median as printed and the range."""
    m = PRINTED_VALUE.search(quote)
    if not m:
        raise Spm6FormatError(f"{quote!r} does not end in '<median> times (<lower>–<upper>)'")
    return m["median"], Decimal(m["lower"]), Decimal(m["upper"])


def check_printed_ranges(rows: dict[str, dict[str, Row]]) -> None:
    """Each range the figure prints equals the 5th and 95th percentiles rounded half up to one decimal."""
    for p in PRINTED:
        _, lower, upper = read_printed(p.quote)
        r = rows[p.extreme][p.level]
        ours = (r.p05.quantize(TENTH, rounding=ROUND_HALF_UP), r.p95.quantize(TENTH, rounding=ROUND_HALF_UP))
        if ours != (lower, upper):
            raise Spm6FormatError(
                f"{p.extreme} at {p.level} °C: the figure prints the range {lower}–{upper}, but the file's 5th and "
                f"95th percentiles round to {ours[0]}–{ours[1]}"
            )


def _checks() -> tuple[PublisherCheck, ...]:
    return tuple(
        PublisherCheck(
            source_id=SOURCE,
            vintage="v20210809",
            entity="WLD",
            period="2021",
            stated=read_printed(p.quote)[0],
            quote=p.quote,
            url=SPM_URL,
            dims=(("extreme", p.extreme), ("level", p.level)),
        )
        for p in PRINTED
    )


# --- transform ---------------------------------------------------------------------------------------------------


def observations(rows: dict[str, dict[str, Row]], year: str) -> list[Observation]:
    return [
        Observation(
            entity="WLD",
            period=year,
            value=float(r.p50),
            lower=float(r.p05),
            upper=float(r.p95),
            interval="very-likely",
            status="projection",
            note=NOT_IN_FIGURE_NOTE if level == NOT_IN_FIGURE else None,
            dims={"extreme": e.dim, "level": level},
        )
        for e in EXTREMES
        for level, r in rows[e.dim].items()
    ]


def _run(files: dict[str, InputFile]) -> Result:
    versions: set[tuple[str, str]] = set()
    rows: dict[str, dict[str, Row]] = {}
    for e in EXTREMES:
        f = files[e.input.key]
        version, year, path = version_and_path(str(f.snapshot.url) if f.snapshot.url else None)
        if path != e.path:
            raise Spm6FormatError(f"{e.input.key} is {path}, not {e.path}")
        versions.add((version, year))
        rows[e.dim] = {r.level: r for r in read_frequency(f.path.read_bytes(), path)}
    meta = files[METADATA.key]
    m_version, m_year, m_path = version_and_path(str(meta.snapshot.url) if meta.snapshot.url else None)
    versions.add((m_version, m_year))
    if m_path != "metadata.yaml" or len(versions) != 1:
        raise Spm6FormatError(f"the files are not one version of the dataset: {sorted(versions)}, {m_path}")
    ((version, year),) = versions
    regions = check_metadata(meta.path.read_bytes())
    check_printed_ranges(rows)
    return Result(
        observations=observations(rows, year),
        vintage=version,
        date_published=PUBLISHED,
        steps=[
            "Read the four frequency files of Figure SPM.6 (CEDA version "
            f"{version}: {', '.join(e.path for e in EXTREMES)}). Each gives, at global warming levels of "
            f"{', '.join(v for v, _ in LEVELS)} °C, how many times as often an extreme that occurred once in 10 (or "
            "50) years in 1850–1900 occurs: the median of the CMIP6 multi-model ensemble and its 17th, 83rd, 5th and "
            "95th percentiles. Checked that the five percentiles are in order in every row.",
            "Published the median as the value and the 5th to 95th percentile as the range (very likely range), as "
            "the published figure shows them; the 17th–83rd percentiles are not published. Values are as printed in "
            f"the files. Each is dated {year}, the year of the assessment: the warming level, not the date, is what "
            f"varies. The {NOT_IN_FIGURE} °C level is in the files but not in the published figure, and is noted.",
            "Checked against metadata.yaml: each file is listed under its figure panel (the Readme's panel letters "
            "for precipitation and drought are out of date); the caption gives the base periods used in the labels "
            f"(1851–1900 for heat and rain, 1850–1900 for drought); and it lists {len(regions)} drying regions for "
            f"drought, of which the {DRYING_EXCLUDED} is not included in the calculation, so the drought values "
            f"cover {len(regions) - 1}.",
            f"Checked against the published figure (IPCC AR6 WGI SPM, p. {SPM_PAGE}): each of the {len(PRINTED)} "
            "ranges it prints equals the 5th and 95th percentiles rounded half up to one decimal, and each printed "
            "median is a publisher cross-check.",
        ],
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="extremes.ipcc-ar6.frequency-by-warming-level",
                title="How many times as often heat, rain and drought extremes occur at each level of global "
                "warming, modelled (IPCC AR6)",
                description="How many times as often an extreme that came once in 10 years (or once in 50) in "
                "1850–1900, a climate without human influence, occurs at global warming levels of 1, 1.5, 2, 3 and 4 "
                "°C: the hottest day of the year over land (once-in-10 and once-in-50-year events), the wettest day "
                "of the year over land, and agricultural and ecological drought in the regions projected to dry. "
                "Modelled: the median of the CMIP6 climate models assessed for Figure SPM.6 of the IPCC Sixth "
                "Assessment Report (2021), with the 5–95% range the figure shows (a range reaching below 1 "
                "includes no increase at all). These are model estimates for "
                "each level of warming, not counts of observed events, and a warming level is not a year: every "
                "value is dated 2021, the year of the assessment. The published figure labels the 1 °C level "
                "'Present'; the world has warmed further since, so 1 °C is not today's warming, and nothing between "
                "levels is interpolated. The 3 °C level is in the data but not in the published figure. Drought "
                "covers 16 drying regions, not the whole world.",
                kind="series",
                unit=TIMES,
                display=Display(decimals=2),
                scope=Scope(
                    geography="Global land for the hottest and the wettest day of the year. For drought, the AR6 "
                    "regions projected to dry: the caption lists 17 (W. and C. North America, N. and S. Central "
                    "America, the Caribbean, N., N.E., S.W. and S. South America, the South American Monsoon, West "
                    "and Central Europe, the Mediterranean, W. and E. Southern Africa, Madagascar, E. and S. "
                    "Australia) and the Caribbean is not included in the calculation, so 16.",
                    baseline="A once-in-10 or once-in-50-year event in 1851–1900 (heat and rain) or 1850–1900 "
                    "(drought), which the IPCC treats as a climate without human influence",
                    basis="CMIP6 multi-model ensemble under several SSP scenarios, at global warming levels "
                    "relative to 1850–1900; extremes defined at model grid-box scale. Value: the ensemble median; "
                    "range: its 5th to 95th percentile (very likely range), as in the published figure. Projected "
                    "changes in the IPCC's words, including at 1 °C; dated 2021, the year of the assessment.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
                dimensions=(EXTREME_DIM, LEVEL_DIM),
                headline_dims=(("extreme", "hot-10yr"), ("level", "1.0")),
            ),
            inputs=(*(e.input for e in EXTREMES), METADATA),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=len(EXTREMES) * len(LEVELS), value_range=(0.0, 100.0)),
            checks=_checks(),
        ),
    ]
