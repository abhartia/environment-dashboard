"""A diagnostic, not a gate: CCKP's own 0.25° grid against the area values its API publishes, for the hottest day
(txx) and the wettest day (rx1day). It is the evidence for keeping the wettest day withheld
(envdash/transforms/future/cckp_projections.py, "Withheld").

CCKP's Metadata page says each country and region value is the mean of the grid cells inside the World Bank polygon,
each cell weighted by the fraction of it inside the polygon and by the cosine of its latitude. This test does exactly
that with CCKP's gridded ensemble median of 2040–2059 under SSP2-4.5 (wb-cckp's two -grid artifacts, netCDF) and
compares the result with the API's all_countries_subnationals value of the same slice, for the countries in COUNTRIES
and every one of their regions. txx is the control: if the comparison reproduces CCKP's txx values, the shapes, the
cells and the weights are CCKP's, and a gap in rx1day is in CCKP's rx1day values, not in the comparison.

Shapes: the full, unsimplified V1 shapes (envdash/geo_shapes.py), the ADM0 shape for a country and the shapes joined to
a CCKP region for a region. A region joined to a record with no rings (GeoCountry.shapeless) has no cells and is left
out. Cells: centred on the file's grid points (latitude -90 to 90, longitude -180 to 179.75, every 0.25°), each 0.25°
wide; the cell at longitude -180 also takes the strip from 179.875° to 180°. The fraction of a cell inside a shape is
the area of their intersection in square degrees over 0.0625, computed exactly (shapely), band by band of latitude.

What this cannot test: whether CCKP takes the year's wettest day after averaging each model's daily rain over the
area. That needs each model's daily rain; a climatology file holds one 20-year value per cell.

The comparison reads the current snapshots (marked snapshot). The result is committed as
tests/expected/cckp-grid-comparison.csv; after a change in the files or the join, rewrite it with
`uv run python tests/test_cckp_grid.py`, review its diff and the numbers in docs/sources.md and in the transform's
docstring. `uv run python tests/test_cckp_grid.py --all` prints the same summary for every country (several minutes).
"""

from __future__ import annotations

import csv
import io
import math
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import netCDF4
import numpy as np
import pytest
import shapely
from shapely.affinity import translate
from shapely.geometry import MultiPolygon, Polygon

from envdash import geo_shapes as gs
from envdash import snapshots
from envdash.paths import Paths
from envdash.transform import InputFile
from envdash.transforms.country.cckp import SOURCE, entities_of, read_file

EXPECTED = Path(__file__).parent / "expected" / "cckp-grid-comparison.csv"
SCENARIO, START, END, STATISTIC = "ssp245", 2040, 2059, "median"
VARIABLES = ("txx", "rx1day")
# The five large countries the national check flagged, and four of a few cells each.
COUNTRIES = ("USA", "BRA", "IND", "SWE", "PHL", "LUX", "BRB", "GRD", "LCA")
RES = 0.25
HALF = RES / 2
NLAT, NLON = 721, 1440
# CCKP prints two decimals: two values that agree to within two halves of the last digit agree as printed.
TOLERANCE = Decimal("0.01")


def _current(paths: Paths, artifact: str) -> InputFile:
    sha = snapshots.read_current(paths)[f"{SOURCE}/{artifact}"]
    snap = snapshots.read_manifest(paths, sha)
    assert snap is not None
    return InputFile(snapshots.cache_path(paths, sha), snap)


def grid(paths: Paths, variable: str) -> np.ndarray:
    """The file's one 20-year field, [latitude index, longitude index]; it has a value in every cell, land and sea."""
    f = _current(paths, f"cmip6-{variable}-{START}-{END}-{SCENARIO}-{STATISTIC}-grid")
    with netCDF4.Dataset(f.path) as ds:
        assert np.allclose(ds["lat"][:], -90 + RES * np.arange(NLAT))
        assert np.allclose(ds["lon"][:], -180 + RES * np.arange(NLON))
        v = ds[f"climatology-{variable}-annual-mean"]
        assert v.shape == (1, NLAT, NLON) and float(v.percentile) == 50.0
        field = v[0]
        assert np.ma.count_masked(field) == 0
        return np.asarray(field, dtype=np.float64)


def published(paths: Paths, variable: str) -> dict[str, Decimal]:
    artifact = f"cmip6-{variable}-{START}-{END}-{SCENARIO}-{STATISTIC}-subnat"
    f = _current(paths, artifact)
    _, data = read_file(f, artifact, variable=variable, scenario=SCENARIO, start=START, end=END, statistic=STATISTIC)
    return {code: next(iter(series.values())) for code, series in data.items()}


def cells(polys: list[Polygon]) -> dict[tuple[int, int], float]:
    """(latitude index, longitude index) -> the fraction of that cell inside the polygons, for every cell they touch."""
    geom = shapely.make_valid(MultiPolygon(polys))
    out: dict[tuple[int, int], float] = defaultdict(float)
    minx, miny, maxx, maxy = geom.bounds
    first, last = math.floor((miny + 90 + HALF) / RES), math.floor((maxy + 90 + HALF) / RES)
    for i in range(max(first, 0), min(last, NLAT - 1) + 1):
        lat = -90 + RES * i
        band = shapely.clip_by_rect(geom, minx, lat - HALF, maxx, lat + HALF)
        if band.area == 0:
            continue
        cols: set[int] = set()
        for part in shapely.get_parts(band):
            x0, _, x1, _ = part.bounds
            cols.update(range(math.floor((x0 + 180 + HALF) / RES), math.floor((x1 + 180 + HALF) / RES) + 1))
        js = np.array(sorted(cols))
        lon = -180 + RES * js
        areas = shapely.area(shapely.intersection(shapely.box(lon - HALF, lat - HALF, lon + HALF, lat + HALF), band))
        for j, a in zip(js.tolist(), areas.tolist(), strict=True):
            if a > 0:
                out[(i, j % NLON)] += a / (RES * RES)
    return out


def weighted_mean(field: np.ndarray, w: dict[tuple[int, int], float]) -> float:
    ij = np.array(list(w))
    weight = np.array(list(w.values())) * np.cos(np.radians(-90 + RES * ij[:, 0]))
    return float(np.sum(weight * field[ij[:, 0], ij[:, 1]]) / np.sum(weight))


def rows(countries: tuple[str, ...] = COUNTRIES) -> list[dict[str, str]]:
    """One row per country and per region of it: its cells (their fractions summed), and per variable CCKP's value and
    the weighted mean of the grid (2 decimals)."""
    paths = Paths.default()
    inputs = gs.load_inputs(paths)
    layers = gs.read_layers(inputs, ("adm0", "adm1"))
    m = gs.matching(paths, inputs, layers)
    j = m.join()
    adm0: dict[str, list[Polygon]] = defaultdict(list)
    for r in layers["adm0"]:
        adm0[m.entity_of[r.iso]] += r.polygons
    shapeless = {code for c in j.countries for code in c.shapeless}
    fields = {v: grid(paths, v) for v in VARIABLES}
    values = {v: published(paths, v) for v in VARIABLES}
    entity = entities_of(set(countries), "rx1day")
    out = []
    for country in countries:
        places = [(country, "country", adm0[entity[country]])] + [
            (code, "region", [p for r in rs for p in r.polygons])
            for code, rs, _ in j.regions_of.get(entity[country], [])
            if code.startswith(f"{country}.") and code not in shapeless
        ]
        for code, level, polys in places:
            # --all only: a CCKP country with no V1 shape of its own (IOT), and the regions txx does not list (Hong
            # Kong's and Macao's single regions).
            if not polys or any(code not in values[v] for v in VARIABLES):
                continue
            w = cells(polys)
            row = {"country": country, "code": code, "level": level, "cells": f"{sum(w.values()):.4f}"}
            for v in VARIABLES:
                row[f"{v}_cckp"] = str(values[v][code])
                row[f"{v}_grid"] = f"{weighted_mean(fields[v], w):.2f}"
            out.append(row)
    return out


def table_bytes(rs: list[dict[str, str]]) -> bytes:
    buf = io.StringIO(newline="")
    buf.write(
        f"# CCKP's value of each place against the mean of CCKP's gridded {START}-{END} {SCENARIO} {STATISTIC} over "
        "the place's World Bank GAD V1 shape, cells weighted by their fraction inside it and the cosine of their "
        "latitude; cells: those fractions summed (tests/test_cckp_grid.py)\n"
    )
    columns = ["country", "code", "level", "cells", *(f"{v}_{k}" for v in VARIABLES for k in ("cckp", "grid"))]
    w = csv.DictWriter(buf, columns, lineterminator="\n")
    w.writeheader()
    w.writerows(rs)
    return buf.getvalue().encode("utf-8")


def _gap(r: dict[str, str], v: str) -> Decimal:
    return Decimal(r[f"{v}_cckp"]) - Decimal(r[f"{v}_grid"])


def _pct(r: dict[str, str]) -> float:
    """rx1day: CCKP's value less the grid's mean, as a percentage of the grid's mean."""
    return 100 * float(_gap(r, "rx1day")) / float(r["rx1day_grid"])


def summary(rs: list[dict[str, str]]) -> dict[str, object]:
    """What docs/sources.md and the transform's docstring quote. `control`: the places whose txx CCKP value equals the
    grid's mean (within TOLERANCE), where the comparison demonstrably does what CCKP does."""
    control = [r for r in rs if abs(_gap(r, "txx")) <= TOLERANCE]
    regions = [r for r in control if r["level"] == "region"]
    small = [r for r in control if float(r["cells"]) <= 5]
    large = [r for r in regions if float(r["cells"]) >= 100]
    return {
        "places": len(rs),
        "txx within": len(control),
        "rx1day within": sum(abs(_gap(r, "rx1day")) <= TOLERANCE for r in control),
        "rx1day below": sum(_gap(r, "rx1day") < -TOLERANCE for r in control),
        "rx1day above": sum(_gap(r, "rx1day") > TOLERANCE for r in control),
        "regions": len(regions),
        "correlation with log cells": round(
            float(np.corrcoef([_pct(r) for r in regions], np.log10([float(r["cells"]) for r in regions]))[0, 1]), 2
        ),
        "up to 5 cells": (len(small), round(float(np.median([_pct(r) for r in small])), 1)),
        "regions of 100 cells or more": (len(large), round(float(np.median([_pct(r) for r in large])), 1)),
        "countries": {
            r["code"]: (r["rx1day_cckp"], r["rx1day_grid"], round(_pct(r), 1)) for r in rs if r["level"] == "country"
        },
    }


@pytest.fixture(scope="module")
def table() -> list[dict[str, str]]:
    return rows()


@pytest.mark.snapshot
def test_the_table_is_the_committed_one(table):
    assert table_bytes(table) == EXPECTED.read_bytes(), (
        "the comparison changed: rewrite it with `uv run python tests/test_cckp_grid.py`, review its diff and update "
        "docs/sources.md and the transform's docstring"
    )


@pytest.mark.snapshot
def test_the_grid_reproduces_txx_but_not_rx1day(table):
    """The numbers docs/sources.md and cckp_projections.py ("Withheld") quote. When CCKP's rx1day values come to equal
    the grid's mean as its txx values do, this fails and a person decides whether to publish."""
    assert summary(table) == {
        "places": 194,
        # The control: CCKP's txx is the grid's mean in 156 places. The other 38 are the USA as a whole, India as a
        # whole (V1's India leaves out Jammu and Kashmir), and mostly states and provinces on the Great Lakes or the
        # sea (Michigan 1.93 °C), where V1's shapes and CCKP's polygons may take in different water.
        "txx within": 156,
        # In those 156, CCKP's rx1day is never above the grid's mean, and equals it only in places of a few cells.
        "rx1day within": 22,
        "rx1day below": 134,
        "rx1day above": 0,
        # Regions as much as countries: the larger the region, the further below.
        "regions": 149,
        "correlation with log cells": -0.8,
        "up to 5 cells": (44, -0.1),
        "regions of 100 cells or more": (59, -14.0),
        # Every country of COUNTRIES (CCKP's value, the grid's mean, the gap in %), the control holding or not.
        "countries": {
            "USA": ("20.53", "36.35", -43.5),
            "BRA": ("29.11", "43.81", -33.6),
            "IND": ("42.92", "62.10", -30.9),
            "SWE": ("20.47", "25.33", -19.2),
            "PHL": ("54.72", "79.87", -31.5),
            "LUX": ("23.89", "24.20", -1.3),
            "BRB": ("32.66", "32.67", -0.0),
            "GRD": ("28.74", "28.87", -0.5),
            "LCA": ("29.05", "29.38", -1.1),
        },
    }
    by = {r["code"]: r for r in table}
    # Sweden: the control holds for the country and all 21 regions, and every one of them is below the grid's mean
    # in rx1day, its largest region (Norrbotten, 348 cells) by 10.5 %.
    sweden = [r for r in table if r["country"] == "SWE"]
    assert len(sweden) == 22 and all(abs(_gap(r, "txx")) <= TOLERANCE for r in sweden)
    assert all(_gap(r, "rx1day") < -TOLERANCE for r in sweden)
    assert (by["SWE.2362795"]["cells"], round(_pct(by["SWE.2362795"]), 1)) == ("348.0059", -10.5)


def test_cells_take_their_fraction_of_a_shape():
    # A square of one cell's size centred on a grid point is that cell; shifted by half a cell, a quarter of four.
    sq = Polygon([(10 - HALF, 20 - HALF), (10 - HALF, 20 + HALF), (10 + HALF, 20 + HALF), (10 + HALF, 20 - HALF)])
    i, j = round((20 + 90) / RES), round((10 + 180) / RES)
    assert cells([sq]) == {(i, j): 1.0}
    shifted = translate(sq, HALF, HALF)
    assert cells([shifted]) == {(i, j): 0.25, (i + 1, j): 0.25, (i, j + 1): 0.25, (i + 1, j + 1): 0.25}
    # The cell at longitude -180 also takes the strip west of the 180° line: an eighth of it on each side here.
    east = Polygon([(179.875, 0), (179.875, HALF / 2), (180, HALF / 2), (180, 0)])
    west = Polygon([(-180, 0), (-180, HALF / 2), (-179.875, HALF / 2), (-179.875, 0)])
    assert cells([east, west]) == {(round(90 / RES), 0): 0.25}
    # Weights are the fractions times the cosine of the cell's latitude: a cell at 60° counts half one at the equator.
    field = np.zeros((NLAT, NLON))
    field[round(90 / RES), 0], field[round(150 / RES), 0] = 1.0, 4.0
    assert math.isclose(weighted_mean(field, {(round(90 / RES), 0): 1.0, (round(150 / RES), 0): 1.0}), 3 / 1.5)


if __name__ == "__main__":
    if "--all" in sys.argv:  # every country with regions, printed, not committed
        p = Paths.default()
        codes = published(p, "rx1day")
        everyone = tuple(sorted({c.split(".")[0] for c in codes if "." in c and not c.startswith("DIS.")}))
        print(summary(rows(everyone)))
    else:  # rewrite the committed table from the current snapshots
        EXPECTED.write_bytes(table_bytes(rows()))
        print(f"wrote {EXPECTED}")
