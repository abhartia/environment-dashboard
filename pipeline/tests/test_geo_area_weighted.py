"""A diagnostic, not a gate: CCKP's national value against the area-weighted mean of its regions' values.

The gate stays the national check of envdash/transforms/future/cckp_projections.py: every national value lies within
its own regions' range. A national value can pass it and still be weighted wrongly, so this test measures, for every
country whose CCKP regions are all matched to World Bank GAD V1 shapes and all of whose shapes carry a region
(envdash/geo_shapes.py), with two regions or more, how far the national value is from the mean of its regions'
values weighted by their areas. It reads the 2040–2059 SSP2-4.5 median file of each of the seven measures, the slice
the future map opens on. docs/sources.md records the result and claims no more than it: CCKP weights grid cells by
their overlap with each polygon and by latitude, a median across models need not equal the weighted mean of the
regions' medians, and CCKP does not publish the national polygons it averages over.

Areas: each region's full, unsimplified V1 shapes, measured on the WGS 84 ellipsoid with their edges straight in
longitude and latitude, as the file stores them. The area between a ring and the equator is (a²/2)·∮ q(φ) dλ, q the
authalic function, summed edge by edge with the trapezoid rule; a ring's area is its absolute value, a polygon's its
outer ring's less its holes'. V1's ADM0 shape of each of these countries has the same area as its regions together.

The comparison reads the current snapshots (marked snapshot, as test_geo_cckp_join.py). The per-country result is
committed as tests/expected/cckp-area-weighted.csv; after a change in the files or the join, rewrite it with
`uv run python tests/test_geo_area_weighted.py` and review its diff and the numbers in docs/sources.md.
"""

from __future__ import annotations

import csv
import io
import math
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import Polygon

from envdash import geo_shapes as gs
from envdash import snapshots
from envdash.paths import Paths
from envdash.transform import InputFile
from envdash.transforms.country.cckp import SOURCE, read_file
from envdash.transforms.future import cckp_projections as fp

EXPECTED = Path(__file__).parent / "expected" / "cckp-area-weighted.csv"
SCENARIO, START, END, STATISTIC = "ssp245", 2040, 2059, "median"

WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
E2 = WGS84_F * (2 - WGS84_F)
E = math.sqrt(E2)


def _q(phi: np.ndarray) -> np.ndarray:
    """The authalic function q(φ) of the WGS 84 ellipsoid: (a²/2)·q(φ) per radian of longitude is the area between
    the equator and latitude φ."""
    s = np.sin(phi)
    return (1 - E2) * (s / (1 - E2 * s * s) - np.log((1 - E * s) / (1 + E * s)) / (2 * E))


def ring_area(xy: np.ndarray) -> float:
    """Square metres enclosed by a closed ring of (longitude, latitude) points."""
    lam, phi = np.radians(xy[:, 0]), np.radians(xy[:, 1])
    if np.abs(np.diff(lam)).max(initial=0) >= math.pi:
        raise ValueError("an edge crosses the 180° line")
    q = _q(phi)
    return abs(float(np.sum(np.diff(lam) * (q[1:] + q[:-1]) / 2))) * WGS84_A**2 / 2


def area(polys: list[Polygon]) -> float:
    return sum(
        ring_area(np.asarray(p.exterior.coords)) - sum(ring_area(np.asarray(h.coords)) for h in p.interiors)
        for p in polys
    )


def tolerance(m: fp.Measure) -> Decimal:
    """Half the last digit the site prints for the measure: a gap this small does not show on the page."""
    return Decimal(5) / 10 ** (m.decimals + 1)


def _values(m: fp.Measure, paths: Paths) -> dict[str, Decimal]:
    artifact = f"cmip6-{m.stem}-{START}-{END}-{SCENARIO}-{STATISTIC}-subnat"
    sha = snapshots.read_current(paths)[f"{SOURCE}/{artifact}"]
    snap = snapshots.read_manifest(paths, sha)
    assert snap is not None
    _, data = read_file(
        InputFile(snapshots.cache_path(paths, sha), snap),
        artifact,
        variable=m.variable,
        product=m.product,
        scenario=SCENARIO,
        start=START,
        end=END,
        statistic=STATISTIC,
    )
    return {code: next(iter(series.values())) for code, series in data.items()}


def rows() -> list[dict[str, str]]:
    """One row per country compared: its regions, their area, and per measure the national value less the
    area-weighted mean of its regions' values (2 decimals; empty when a region has no value in the file)."""
    paths = Paths.default()
    inputs = gs.load_inputs(paths)
    layers = gs.read_layers(inputs, ("adm0", "adm1", "ndlsa"))
    m = gs.matching(paths, inputs, layers)
    j = m.join()
    code_of = {e: iso for iso, e in m.entity_of.items()}
    adm0 = {}
    for r in layers["adm0"]:
        adm0[m.entity_of[r.iso]] = adm0.get(m.entity_of[r.iso], 0.0) + area(list(r.polygons))
    values = {x.variable: _values(x, paths) for x in fp.MEASURES}
    out = []
    for c in j.countries:
        if c.unjoined or c.unmatched or c.shapeless or c.cckp_regions < 2:
            continue
        weights = {code: area([p for r in rs for p in r.polygons]) for code, rs, _ in j.regions_of[c.entity]}
        total = sum(weights.values())
        assert math.isclose(total, adm0[c.entity], rel_tol=1e-9), c.entity
        row = {"country": c.entity, "regions": str(len(weights)), "area_km2": f"{total / 1e6:.0f}"}
        for x in fp.MEASURES:
            v = values[x.variable]
            if code_of[c.entity] not in v or any(code not in v for code in weights):
                row[x.variable] = ""
                continue
            mean = sum(w * float(v[code]) for code, w in weights.items()) / total
            row[x.variable] = f"{round(float(v[code_of[c.entity]]) - mean, 2) + 0.0:.2f}"  # + 0.0: no "-0.00"
        out.append(row)
    return out


def table_bytes(rs: list[dict[str, str]]) -> bytes:
    buf = io.StringIO(newline="")
    buf.write(
        f"# CCKP national value less the area-weighted mean of its regions' values, {START}-{END} {SCENARIO} "
        f"{STATISTIC}; areas of the World Bank GAD V1 shapes on the WGS 84 ellipsoid "
        "(tests/test_geo_area_weighted.py)\n"
    )
    w = csv.DictWriter(buf, ["country", "regions", "area_km2", *(x.variable for x in fp.MEASURES)], lineterminator="\n")
    w.writeheader()
    w.writerows(rs)
    return buf.getvalue().encode("utf-8")


@pytest.fixture(scope="module")
def table() -> list[dict[str, str]]:
    return rows()


def summary(rs: list[dict[str, str]]) -> dict[str, tuple[int, int, int, str, str]]:
    """Per measure: (countries compared, within tolerance(), national below the weighted mean, the largest gap's
    country, that gap)."""
    out = {}
    for x in fp.MEASURES:
        gaps = [(Decimal(r[x.variable]), r["country"]) for r in rs if r[x.variable]]
        worst = max(gaps, key=lambda g: (abs(g[0]), g[1]))
        out[x.variable] = (
            len(gaps),
            sum(abs(g) <= tolerance(x) for g, _ in gaps),
            sum(g < 0 for g, _ in gaps),
            worst[1],
            str(worst[0]),
        )
    return out


@pytest.mark.snapshot
def test_the_table_is_the_committed_one(table):
    assert table_bytes(table) == EXPECTED.read_bytes(), (
        "the comparison changed: rewrite it with `uv run python tests/test_geo_area_weighted.py`, review its diff and "
        "update docs/sources.md"
    )


@pytest.mark.snapshot
def test_what_docs_sources_md_says(table):
    """The numbers docs/sources.md quotes ("Decisions on the future map's shapes", the national value against its
    regions)."""
    assert summary(table) == {
        "hd35": (172, 167, 32, "PAK", "-11.45"),
        "tr26": (172, 154, 28, "PAK", "-7.88"),
        "hi39": (172, 169, 11, "PAK", "-4.29"),
        "txx": (172, 166, 34, "PAK", "-1.96"),
        "rx1day": (172, 29, 162, "PHL", "-17.68"),
        "cdd": (172, 135, 83, "PAK", "-6.58"),
        "tas": (172, 167, 60, "GRL", "-0.13"),
    }
    gaps = {r["country"]: r["hd35"] for r in table}
    assert (gaps["GNB"], gaps["IND"]) == ("-5.83", "-3.17")


def test_areas_on_the_ellipsoid():
    # Eight rings from the equator to a pole, 90° of longitude each, make the whole WGS 84 ellipsoid:
    # 510,065,621.7 km² (GeographicLib's value, 5.10065621724e14 m²).
    quarter = np.array([[0.0, 0.0], [0.0, 90.0], [90.0, 90.0], [90.0, 0.0], [0.0, 0.0]])
    assert round(8 * ring_area(quarter) / 1e6, 1) == 510_065_621.7
    # A 1° square at the equator: 110.57 km of latitude by 111.32 km of longitude, to the first order.
    square = np.array([[0.0, 0.0], [0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]])
    assert math.isclose(ring_area(square), 110_574 * 111_319, rel_tol=1e-4)
    # A polygon's area is its outer ring's less its holes'.
    hole = np.array([[0.25, 0.25], [0.75, 0.25], [0.75, 0.75], [0.25, 0.75], [0.25, 0.25]])
    assert math.isclose(area([Polygon(square, [hole])]), ring_area(square) - ring_area(hole))
    # An edge of 180° of longitude or more has no single reading (the file splits its shapes at the 180° line).
    with pytest.raises(ValueError, match="180° line"):
        ring_area(np.array([[-170.0, 0.0], [170.0, 0.0], [170.0, 1.0], [-170.0, 0.0]]))


if __name__ == "__main__":  # rewrite the committed table from the current snapshots
    EXPECTED.write_bytes(table_bytes(rows()))
    print(f"wrote {EXPECTED}")
