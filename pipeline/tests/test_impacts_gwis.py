"""GWIS burned area by land cover (envdash/transforms/impacts/gwis_burned_area.py).

Each GWIS response is a single 125-134 kB line of JSON, which tests/fixtures/make_fixture.py can neither cut by lines
nor keep whole (its limit is 100,000 bytes). The value tests therefore read the full real responses from the
snapshot cache and are marked `snapshot` (run with `uv run pytest -m snapshot`); the tests without the marker need
only the registry.
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from decimal import Decimal

import pytest

from envdash import snapshots
from envdash.export import build_and_export
from envdash.models import ENTITY
from envdash.paths import REPO_ROOT, Paths
from envdash.registry import load_registry
from envdash.transform import discover
from envdash.transforms.impacts import gwis_burned_area as gwis

SOURCE = "gwis-burned-area"
ID = "burned-area.gwis.annual-by-land-cover"


# --- no raw data needed -------------------------------------------------------------------------------------------


def test_every_area_is_a_registered_artifact_whose_url_names_that_area():
    src = load_registry(Paths.default()).sources[SOURCE]
    urls = {a.id: str(a.url) for a in src.artifacts}
    assert set(urls) == {a for a, *_ in gwis.AREAS}
    for artifact, aoi, entity, _name in gwis.AREAS:
        assert gwis.aoi_of(urls[artifact]) == aoi
        assert ENTITY.fullmatch(entity)
    assert src.licence_class == "open"


def test_aoi_of_refuses_urls_without_one_area():
    with pytest.raises(gwis.GwisFormatError):
        gwis.aoi_of("https://cprof.effis.emergency.copernicus.eu/api/v3/banf?level=ADM0&value=ITA&year=2024")
    with pytest.raises(gwis.GwisFormatError):
        gwis.aoi_of(None)


# --- full real responses (snapshot cache) -------------------------------------------------------------------------


def _current(artifact: str) -> tuple[bytes, snapshots.Snapshot]:
    p = Paths.default()
    sha = snapshots.read_current(p)[f"{SOURCE}/{artifact}"]
    snap = snapshots.read_manifest(p, sha)
    assert snap is not None
    return snapshots.cache_path(p, sha).read_bytes(), snap


@pytest.mark.snapshot
def test_world_values_and_identities():
    raw, snap = _current("banf-world")
    years = gwis.parse_banf(raw, snap.date_accessed, "banf-world")
    assert [y.year for y in years] == list(range(2002, 2026))
    last = years[-1]
    # 332,928,197.5 ha for 2025 is also the value Our World in Data republishes from this API.
    assert last.year == 2025 and last.values["lc_tot"] == Decimal("332928197.51000077")
    assert last.months == 12 and not last.partial
    assert years[0].values["lc_tot"] == Decimal("463548794.4740024")
    assert all(not y.partial for y in years)


@pytest.mark.snapshot
def test_a_changed_class_or_missing_month_is_refused():
    raw, snap = _current("banf-world")
    doc = json.loads(raw)
    doc["banfyear"][5]["lc1"] += 1000.0
    with pytest.raises(gwis.GwisFormatError, match=r"2007: lc1\.\.lc5 add up"):
        gwis.parse_banf(json.dumps(doc).encode(), snap.date_accessed, "banf-world")
    doc = json.loads(raw)
    doc["banfmonth"] = [m for m in doc["banfmonth"] if not (m["year"] == 2010 and m["month"] == 7)]
    with pytest.raises(gwis.GwisFormatError, match="2010: a past year with 11 months"):
        gwis.parse_banf(json.dumps(doc).encode(), snap.date_accessed, "banf-world")


@pytest.mark.snapshot
def test_the_fetch_year_is_year_to_date_and_later_years_are_refused():
    raw, _ = _current("banf-world")
    years = gwis.parse_banf(raw, date(2025, 11, 30), "banf-world")
    assert [y.year for y in years if y.partial] == [2025]
    obs = gwis.observations("WLD", years, date(2025, 11, 30))
    ytd = [o for o in obs if o.period == "2025"]
    assert len(ytd) == len(gwis.LAND_COVER)
    assert all(o.status == "preliminary" and "Year to date" in o.note for o in ytd)
    with pytest.raises(gwis.GwisFormatError, match="after the fetch date"):
        gwis.parse_banf(raw, date(2024, 12, 31), "banf-world")


@pytest.mark.snapshot
def test_built_from_the_current_snapshots(tmp_paths):
    shutil.copy(REPO_ROOT / "pipeline" / "sources" / f"{SOURCE}.yaml", tmp_paths.sources / f"{SOURCE}.yaml")
    for artifact, *_ in gwis.AREAS:
        raw, snap = _current(artifact)
        rec, _ = snapshots.record(
            tmp_paths,
            data=raw,
            source_id=SOURCE,
            artifact_id=artifact,
            url=str(snap.url),
            acquisition="automatic",
            today=snap.date_accessed,
        )
        snapshots.set_current(tmp_paths, {snapshots.key(SOURCE, artifact): rec.sha256})
    reg = load_registry(tmp_paths)
    ts = [t for t in discover(tmp_paths) if t.spec.id == ID]
    out = build_and_export(tmp_paths, reg, ts).outcomes[0]
    assert out.state == "built", out.reason
    ind = out.indicator
    assert {o.entity for o in ind.observations} == {"WLD", "UN_AFR", "UN_AME", "UN_ASI", "UN_EUR", "UN_OCE"}
    assert len(ind.observations) == 6 * 6 * 24
    assert ind.latest.entity == "WLD" and ind.latest.period == "2025" and ind.latest.dims == {"land_cover": "total"}
    by = {(o.entity, o.period, o.dims["land_cover"]): o.value for o in ind.observations}
    assert by[("UN_AFR", "2025", "total")] == 225525253.7269997
    assert by[("UN_EUR", "2025", "total")] == 7554890.639999972
    assert all(o.status == "final" for o in ind.observations)
