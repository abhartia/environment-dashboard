"""EUMETSAT OSI SAF Sea-Ice Index v3.0 (OSI-420-a): Arctic sea ice extent in September, the twin of NSIDC's.

Input: ice_extent_nh_sii-v3p0_monthly.txt, the Northern Hemisphere monthly mean sea ice extent. The file is '#' header
lines, then one row per month: decimal year, year, month, day (always 16) and extent in km². The "# Format" line
names a sixth column (SIE_source) that the monthly rows do not have; a row with any other number of fields than
five stops the build. -999 marks a missing month.

The header lines "# Area: Northern Hemisphere", "# Quantity: Sea Ice Extent" and "# Product: EUMETSAT OSI SAF Sea Ice
Index v3.0" must be present, and the URL must be the v3p0 file, or the transform stops; the version ("3.0") is the
vintage. The file's "# Creation date:" line is the release date. A September row is used only when the file was
created after that September ended, so a month in progress is never published.

Values. Only the September rows are kept. Rows before the first non-missing value (the record starts in late October
1978, so 1978 is -999) are left out; a -999 after that becomes a null with the sentinel as its reason. Extent is
converted from km² to million km² (divided by 1,000,000, exact decimal arithmetic) so it can be read beside NSIDC's
series, which is in million km². The two use different algorithms and are never combined.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from envdash.models import Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "osisaf-sea-ice-index"
MONTHLY = Input(SOURCE, "nh-extent-monthly")
ENTITY = "NH"
MKM2 = Unit(code="million-km2", label="million square kilometres", short="million km²")
MISSING = "-999"
REQUIRED_HEADER = (
    "# Area: Northern Hemisphere",
    "# Quantity: Sea Ice Extent",
    "# Product: EUMETSAT OSI SAF Sea Ice Index v3.0",
)
URL = re.compile(r"/sea-ice-index/v(\d+)p(\d+)/timeseries/nh/ice_extent_nh_sii-v\1p\2_monthly\.txt$")
CREATED = re.compile(r"^# Creation date: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(\.\d+)?\s*$", re.M)


class OsisafFormatError(ValueError):
    pass


def version_of(url: str | None) -> str:
    m = URL.search(url or "")
    if not m:
        raise OsisafFormatError(f"{url!r} is not an OSI SAF sea-ice-index monthly NH file URL")
    return f"{m.group(1)}.{m.group(2)}"


def created_at(text: str) -> datetime:
    m = CREATED.search(text)
    if not m:
        raise OsisafFormatError("no '# Creation date:' line")
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")


def parse_september(raw: bytes) -> tuple[list[Observation], datetime]:
    text = raw.decode("ascii")
    lines = text.splitlines()
    for h in REQUIRED_HEADER:
        if h not in lines:
            raise OsisafFormatError(f"header line {h!r} is missing")
    created = created_at(text)
    obs: list[Observation] = []
    started = False
    last: tuple[int, int] | None = None
    for ln in lines:
        if ln.startswith("#") or not ln.strip():
            continue
        f = ln.split()
        if len(f) != 5:
            raise OsisafFormatError(f"monthly row {ln!r} has {len(f)} fields, expected 5")
        year, month, day, extent = int(f[1]), int(f[2]), int(f[3]), f[4]
        if day != 16 or not 1 <= month <= 12:
            raise OsisafFormatError(f"monthly row {ln!r}: expected a month dated the 16th")
        if last is not None and (year, month) <= last:
            raise OsisafFormatError(f"monthly rows out of order at {year}-{month:02d}")
        last = (year, month)
        if extent != MISSING:
            started = True
        if month != 9 or not started:
            continue
        if created.date() < date(year, 10, 1):
            continue
        period = f"{year:04d}-09"
        if extent == MISSING:
            obs.append(
                Observation(
                    entity=ENTITY,
                    period=period,
                    value=None,
                    missing_reason="OSI SAF's file has -999 (missing) for this month.",
                )
            )
        else:
            obs.append(Observation(entity=ENTITY, period=period, value=float(Decimal(extent) / Decimal(1_000_000))))
    return obs, created


def _run(files: dict[str, InputFile]) -> Result:
    f = files[MONTHLY.key]
    version = version_of(str(f.snapshot.url) if f.snapshot.url else None)
    obs, created = parse_september(f.path.read_bytes())
    return Result(
        observations=obs,
        vintage=version,
        date_published=created.date().isoformat(),
        steps=[
            f"Read the September rows of ice_extent_nh_sii-v{version.replace('.', 'p')}_monthly.txt (OSI SAF Sea-Ice "
            f"Index v{version}, Northern Hemisphere monthly mean extent in km²), created by OSI SAF on "
            f"{created.day} {created:%B %Y}. Only Septembers that had ended when the file was created are used.",
            "Converted km² to million km² (divided by 1,000,000, exact decimal arithmetic). Months marked -999 after "
            "the record starts would be published as missing.",
        ],
        changes="extent converted from km² to million km².",
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id="sea-ice-extent.osisaf.arctic-september",
                title="Arctic sea ice extent in September (OSI SAF)",
                description="Mean extent of Arctic sea ice in September since 1979 from EUMETSAT's OSI SAF Sea-Ice "
                "Index v3.0: the area of ocean with more than 15% ice cover. An independent European estimate made "
                "with a different algorithm from NSIDC's Sea Ice Index, so its values are higher; the two are shown "
                "side by side, never combined. Recent months come from OSI SAF's operational extension of its "
                "climate data record (OSI-438).",
                kind="series",
                unit=MKM2,
                display=Display(decimals=2),
                scope=Scope(
                    geography="Northern Hemisphere oceans (the Arctic Ocean and surrounding seas)",
                    basis="Sea ice extent: monthly mean area with more than 15% ice concentration, from the OSI SAF "
                    "sea ice concentration climate data records OSI-450-a1, OSI-430-a and OSI-438. Not sea ice area, "
                    "and not NSIDC's index.",
                ),
                geo_coverage="global-only",
                headline_entity=ENTITY,
            ),
            inputs=(MONTHLY,),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=47, value_range=(2.0, 10.0)),
        )
    ]
