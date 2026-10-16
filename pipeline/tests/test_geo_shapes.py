"""World Bank Official Boundaries GAD V1, read and simplified into the future map's files (envdash/geo_shapes.py).

The small members are whole-file fixtures: the shared .prj and .cpg, and the NDLSA and ADM0 .dbf and .shx. The .shp
members (614,164 to 100,520,904 bytes) and the ADM1 .dbf (2,040,730 bytes) are over the whole-file limit, and a
shapefile cannot be cut byte-exactly (its header states the file's length and the .shx every record's offset), so the
tests that draw shapes read the current snapshots and are marked `snapshot`, as for the repo's other formats that
cannot be sliced (run with `uv run pytest -m snapshot` after `envdash fetch -s wb-gad-v1 -s wb-cckp`).
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys

import pytest
import shapefile

from envdash import canonical, geo
from envdash import geo_shapes as gs
from envdash.models import GeoIndex
from envdash.paths import Paths
from envdash.registry import load_registry

from support import fixture


def _bytes(artifact: str) -> bytes:
    return fixture("wb-gad-v1", artifact)[0].read_bytes()


def _records(artifact: str) -> list[dict]:
    return [r.as_dict() for r in shapefile.Reader(dbf=io.BytesIO(_bytes(artifact)), encoding="utf-8").records()]


# --- fixtures (no snapshot needed) -----------------------------------------------------------------------------------


def test_the_projection_and_code_page_are_checked():
    prj, cpg = _bytes("prj"), _bytes("cpg")
    gs.check_projection(prj, cpg)
    with pytest.raises(gs.GeoShapesError, match="not WGS 84"):
        gs.check_projection(prj.replace(b"D_WGS_1984", b"D_WGS_1972"), cpg)
    with pytest.raises(gs.GeoShapesError, match="not UTF-8"):
        gs.check_projection(prj, b"ISO-8859-1")


def test_every_admin0_code_has_an_entity():
    rows = _records("adm0-dbf")
    assert len(rows) == (len(_bytes("adm0-shx")) - 100) // 8 == 267
    codes = {r["ISO_A3"] for r in rows}
    entity_of = gs.entity_of_codes(Paths.default(), codes)
    assert len(codes) == len(set(entity_of.values())) == 245
    assert entity_of["KSV"] == "KOS" and entity_of["TWN"] == "TWN" and entity_of["REU"] == "REU"
    # Why ISO_A3 and not WB_A3: WB_A3 is blank for Iraq and Haiti and puts Taiwan and France's overseas regions under
    # another country's code, while CCKP keys its values by these ISO_A3 codes.
    wb = {r["ISO_A3"]: r["WB_A3"] for r in rows if r["ISO_A3"] in {"IRQ", "HTI", "TWN", "REU"}}
    assert wb == {"IRQ": "", "HTI": "", "TWN": "CHN", "REU": "FRA"}


def test_disputed_areas_keep_the_world_banks_names():
    rows = _records("ndlsa-dbf")
    assert len(rows) == (len(_bytes("ndlsa-shx")) - 100) // 8 == 24
    names = [r["NAM_0"] for r in rows]
    assert {"Aksai Chin", "Arunachal Pradesh", "Jammu and Kashmir", "Western Sahara", "Abyei"} <= set(names)
    # The file's own line break after one name; the build strips leading and trailing spaces only.
    assert "Kauirik\r\n" in names
    with_codes = {r["ISO_A3"] for r in rows if r["ISO_A3"]}
    assert with_codes == {"IOT", "SGS", "ESH", "FLK"}
    assert all(geo.resolve(c, "wb-gad-v1") == c for c in with_codes)


def test_declared_pairs_are_complete_rows():
    rows = gs.read_declared(gs.declared_path(Paths.default()))
    assert len(rows) == 151
    assert sum(d.decision == "accept" for d in rows) == 79 and sum(d.decision == "reject" for d in rows) == 72
    assert all(d.reason.strip() and "." in d.cckp_code for d in rows)
    assert sum(d.cckp_code.startswith("KEN.") for d in rows) == 45


def test_names_compare_without_accents_case_or_punctuation():
    # Real pairs from CCKP's names and GAD V1's.
    assert gs.norm("Elgeyo-Marakwet") == gs.norm("Elgeyo Marakwet")
    assert gs.norm("Murang'a") == gs.norm("Murang’a")
    assert gs.norm("Ségou") == gs.norm("Segou")
    assert gs.norm("Dki Jakarta") == gs.norm("DKI Jakarta")
    # Nothing fuzzy: GAD V1's "Akwa lbom" (a lower-case L) is not CCKP's "Akwa Ibom".
    assert gs.norm("Akwa lbom") != gs.norm("Akwa Ibom")
    assert not gs.is_name("HKG.33364910", "HKG.33364910") and not gs.is_name("GBR.1", "Name Unknown")


# --- the real files (snapshot) ---------------------------------------------------------------------------------------

ONLY = {"world", "IND", "KEN", "FJI", "MDV", "GNB", "RUS", "CAN", "USA"}


@pytest.fixture(scope="module")
def built() -> gs.Built:
    paths = Paths.default()
    return gs.build(paths, load_registry(paths), only=ONLY)


def _topo(built: gs.Built, path: str) -> dict:
    return json.loads(built.files[path])


@pytest.mark.snapshot
def test_the_world_has_every_country_and_disputed_area(built):
    data = built.files["v1/geo/world.topo.json"]
    assert len(data) <= gs.WORLD_LIMIT
    topo = json.loads(data)
    countries = topo["objects"]["countries"]["geometries"]
    disputed = topo["objects"]["disputed"]["geometries"]
    assert len(countries) == 245 and len(disputed) == 24
    assert [g["id"] for g in countries] == sorted(g["id"] for g in countries)
    for g in countries + disputed:
        lon, lat = g["properties"]["rp"]
        assert -180 <= lon <= 180 and -90 <= lat <= 90
    dots = {g["id"] for g in countries if g["type"] is None}
    # Places too small to draw at world scale stay, as a point: Tuvalu, Nauru, the Vatican, Monaco.
    assert {"TUV", "NRU", "VAT", "MCO"} <= dots and len(dots) < 60
    assert topo["meta"]["credit"].startswith("Simplified by Environment Dashboard from The World Bank")
    assert {d["properties"]["name"] for d in disputed} >= {"Kauirik", "Aksai Chin"}


@pytest.mark.snapshot
def test_country_files_hold_every_region_and_nearby_disputed_area(built):
    for e in ONLY - {"world"}:
        assert len(built.files[f"v1/geo/adm1/{e}.topo.json"]) <= gs.COUNTRY_LIMIT, e
    india = _topo(built, "v1/geo/adm1/IND.topo.json")
    regions = india["objects"]["regions"]["geometries"]
    assert len(regions) == 35 and all(g["id"].startswith("IND.115") for g in regions)
    assert {g["properties"]["m"] for g in regions} == {"adm1cd"}
    names = {g["properties"]["name"] for g in india["objects"]["disputed"]["geometries"]}
    # Aksai Chin borders China and Jammu and Kashmir, not an Indian state: it is in the files of China, not India.
    assert {"Jammu and Kashmir", "Arunachal Pradesh", "Doklam"} <= names and "Aksai Chin" not in names
    kenya = _topo(built, "v1/geo/adm1/KEN.topo.json")
    assert {g["properties"]["name"] for g in kenya["objects"]["disputed"]["geometries"]} == {"Ilemi Triangle"}
    # Wisconsin is two records, one feature.
    usa = _topo(built, "v1/geo/adm1/USA.topo.json")
    assert len(usa["objects"]["regions"]["geometries"]) == 51
    # The Maldives' atolls are mostly too small for its own map: they stay as points.
    maldives = _topo(built, "v1/geo/adm1/MDV.topo.json")["objects"]["regions"]["geometries"]
    assert all("rp" in g["properties"] for g in maldives) and any(g["type"] is None for g in maldives)


@pytest.mark.snapshot
def test_a_country_across_the_180th_meridian_is_measured_the_short_way(built):
    inputs = gs.load_inputs(Paths.default())
    fiji = [p for r in gs.read_layer(inputs.files, "adm1") if r.iso == "FJI" for p in r.polygons]
    side, width, _ = gs.extent(fiji)
    assert width > 359 and side < 10
    s = gs.country_simplify(fiji)
    assert s.epsilon < 0.01 and s.quantize > 30 * gs.COUNTRY_QUANTIZE


@pytest.mark.snapshot
def test_the_index_traces_every_file_and_input(built):
    index = GeoIndex.model_validate_json(built.files["v1/geo/index.json"])
    assert canonical.dump_bytes(index) == built.files["v1/geo/index.json"]
    for f in index.files:
        assert canonical.sha256_bytes(built.files[f.path]) == f.sha256 and len(built.files[f.path]) == f.bytes
    current = gs.load_inputs(Paths.default()).snaps
    assert {o.sha256 for o in index.origins} == {s.sha256 for s in current.values()}
    assert index.licence_class == "open" and "UNCITRAL" not in index.attribution
    crosswalk = built.files["v1/geo/cckp-adm1-crosswalk.csv"].decode()
    header = next(line for line in crosswalk.splitlines() if not line.startswith("#"))
    assert header == ",".join(gs.CROSSWALK_COLUMNS)


@pytest.mark.snapshot
def test_a_lost_feature_or_an_open_ring_stops_the_build(built):
    india = _topo(built, "v1/geo/adm1/IND.topo.json")
    expected = {k: [g["id"] for g in v["geometries"]] for k, v in india["objects"].items()}
    gs.check_topology(india, expected, "IND")
    lost = json.loads(json.dumps(india))
    lost["objects"]["regions"]["geometries"].pop(0)
    with pytest.raises(gs.GeoShapesError, match="features lost"):
        gs.check_topology(lost, expected, "IND")
    broken = json.loads(json.dumps(india))
    first = next(g for g in broken["objects"]["regions"]["geometries"] if g["type"] is not None)
    rings = first["arcs"][0] if first["type"] == "MultiPolygon" else first["arcs"]
    broken["arcs"][rings[0][0] if rings[0][0] >= 0 else ~rings[0][0]].append([1, 1])
    with pytest.raises(gs.GeoShapesError, match=r"do not join|does not close"):
        gs.check_topology(broken, expected, "IND")


@pytest.mark.snapshot
def test_another_process_writes_the_same_bytes(built):
    """Python randomises string hashing per process: the same build in a process with another seed must give the
    same bytes for every file."""
    code = (
        "import json, sys\n"
        "from envdash import canonical, geo_shapes as gs\n"
        "from envdash.paths import Paths\n"
        "from envdash.registry import load_registry\n"
        "p = Paths.default()\n"
        f"b = gs.build(p, load_registry(p), only={sorted(ONLY)!r})\n"
        "json.dump({k: canonical.sha256_bytes(v) for k, v in b.files.items()}, sys.stdout)\n"
    )
    env = {**os.environ, "PYTHONHASHSEED": "12345"}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
    assert json.loads(out.stdout) == {k: canonical.sha256_bytes(v) for k, v in built.files.items()}
