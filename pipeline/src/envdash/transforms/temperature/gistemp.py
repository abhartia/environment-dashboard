"""GISTEMP v4 global annual land-ocean temperature anomaly, re-based to the dataset's own 1880–1899 mean.

Input: GLB.Ts+dSST.csv, the global Land-Ocean Temperature Index table (a title line, then a header line, then one row
per year from 1880 with twelve monthly anomalies, the January–December mean "J-D" and seasonal means; °C relative to
1951–1980, printed to two decimals; "***" marks values not yet available).

Baseline. GISS publishes no observed series relative to 1850–1900, because its analysis starts in 1880. Its FAQ
(https://data.giss.nasa.gov/gistemp/faq/, read 2026-10-05) gives the method: "we can adjust to 1880-1899 from
1951-1980, and then make that adjustment", the second step being "about 0.038ºC" estimated from "the average of"
the HadCRUT, NOAA and Berkeley Earth analyses. Only the first step is GISTEMP's own, so the site re-bases to the
mean of the 20 J-D values 1880–1899 of the same file and labels the result with those years. The borrowed 0.038 °C
is not applied: that would substitute other datasets' values into this one.

Partial year. A year is published only when all twelve months are present; GISS then prints its J-D value. The
current year has "***" in J-D and is left out. A J-D value without twelve months, or twelve months without a J-D
value, stops the build.

Vintage. The file carries no version or date line. GISS updates it monthly, so the vintage is "v4" plus the last
month with data (for example "v4 2026-08").
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "gistemp-v4"
MONTHLY = Input(SOURCE, "glb-monthly")
TITLE = "Land-Ocean: Global Means"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
HEADER = ["Year", *MONTHS, "J-D", "D-N", "DJF", "MAM", "JJA", "SON"]
MISSING = "***"
BASELINE = (1880, 1899)


class GistempFormatError(ValueError):
    pass


def _num(s: str) -> Decimal:
    # GISS prints ".19" and "-.19"; Decimal reads both.
    return Decimal(s)


def read_table(raw: bytes) -> list[list[str]]:
    lines = raw.decode("ascii").splitlines()
    if not lines or lines[0].strip() != TITLE:
        raise GistempFormatError(f"first line is not {TITLE!r}")
    if lines[1].split(",") != HEADER:
        raise GistempFormatError(f"header {lines[1]!r} != expected {','.join(HEADER)}")
    rows = [ln.split(",") for ln in lines[2:] if ln.strip()]
    for r in rows:
        if len(r) != len(HEADER) or not r[0].isdigit():
            raise GistempFormatError(f"malformed row {','.join(r)!r}")
    return rows


def rebase(raw: bytes) -> tuple[list[Observation], Decimal, dict[int, int], str]:
    """Returns (observations, 1880–1899 mean, {left-out year: months present}, last month with data as YYYY-MM)."""
    rows = read_table(raw)
    annual: list[tuple[int, Decimal]] = []
    partial: dict[int, int] = {}
    last_month = ""
    for r in rows:
        year = int(r[0])
        months = [m != MISSING for m in r[1:13]]
        n = sum(months)
        if n and months != [True] * n + [False] * (12 - n):
            raise GistempFormatError(f"{year}: months present {months} are not a run from January")
        if n:
            last_month = f"{year:04d}-{n:02d}"
        jd = r[13]
        if (n == 12) != (jd != MISSING):
            raise GistempFormatError(f"{year}: {n} months present but J-D is {jd!r}")
        if jd == MISSING:
            partial[year] = n
        else:
            annual.append((year, _num(jd)))
    if len(partial) > 1 or any(y < annual[-1][0] for y in partial):
        raise GistempFormatError(f"years without J-D other than one trailing partial year: {sorted(partial)}")
    base = [v for y, v in annual if BASELINE[0] <= y <= BASELINE[1]]
    if len(base) != BASELINE[1] - BASELINE[0] + 1:
        raise GistempFormatError(f"expected {BASELINE[1] - BASELINE[0] + 1} baseline years, found {len(base)}")
    offset = sum(base, Decimal(0)) / Decimal(len(base))
    obs = [Observation(entity="WLD", period=f"{y:04d}", value=float(v - offset)) for y, v in annual]
    return obs, offset, partial, last_month


def _run(files: dict[str, InputFile]) -> Result:
    obs, offset, partial, last_month = rebase(files[MONTHLY.key].path.read_bytes())
    steps = [
        "Read the January–December mean (J-D) of GISTEMP v4's global Land-Ocean Temperature Index table "
        "GLB.Ts+dSST.csv (°C relative to 1951–1980, two decimals).",
    ]
    for year, n in partial.items():
        steps.append(
            f"Left out {year}: the table has {n} of its 12 months and prints *** for its J-D mean. A year is "
            "published only when GISS prints its J-D value, which it does once all twelve months are in."
        )
    steps.append(
        "Re-based to the dataset's own 1880–1899 mean, the first step of the method in the GISTEMP FAQ: subtracted "
        f"the mean of the 20 J-D values 1880–1899, {float(offset)!r} °C relative to 1951–1980 (exact decimal "
        "arithmetic on the printed values), from every year. GISS has no observations before 1880. The FAQ's second "
        "step, about 0.038 °C estimated from the HadCRUT, NOAA and Berkeley Earth analyses to reach 1850–1900, is not "
        "applied, so these values are relative to 1880–1899, not 1850–1900."
    )
    return Result(
        observations=obs,
        vintage=f"v4 {last_month}",
        steps=steps,
        changes="annual anomalies re-based from 1951–1980 to the 1880–1899 mean of the same dataset"
        + (f"; {', '.join(str(y) for y in partial)} left out as a partial year." if partial else "."),
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="temp.gistemp-v4.annual-1880-1899",
                title="Global surface temperature above 1880–1899 (GISTEMP v4)",
                description="Global mean surface temperature for each complete year since 1880, as the difference "
                "from the 1880–1899 average of the same dataset. NASA GISS has no observations before 1880, so this "
                "series is not relative to 1850–1900.",
                kind="series",
                unit=Unit(code="degC", label="degrees Celsius", short="°C"),
                display=Display(decimals=2),
                scope=Scope(
                    geography="Global mean",
                    baseline="1880–1899 mean of this dataset (GISS publishes no observed 1850–1900 series)",
                    basis="GISTEMP v4 Land-Ocean Temperature Index: NOAA GHCN v4 weather-station air temperatures "
                    "over land and NOAA ERSST v5 sea-surface temperatures over the ocean.",
                ),
                geo_coverage="global-only",
                headline_entity="WLD",
            ),
            inputs=(MONTHLY,),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=140, value_range=(-1.0, 3.0)),
        )
    ]
