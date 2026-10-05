"""Warming contribution by country (jones-2025-national-contributions, version 2025.1).

The source is noncommercial (CC BY-NC-SA 4.0, inherited from PRIMAP-hist v2.7), so no fixture is cut from it: the
data tests read the real snapshot from the local cache and are marked snapshot. The tests that need no data check the
declared metadata against the registry.
"""

from __future__ import annotations

import shutil
from decimal import Decimal

import pytest

from envdash import geo, snapshots
from envdash.export import build_and_export
from envdash.paths import REPO_ROOT, Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, discover
from envdash.transforms.emissions import jones_warming as jones

from support import exported

ID = "warming.jones-2025.national-contribution"


def test_spec_scope_and_registry():
    (t,) = jones.transforms(Paths.default())
    assert t.spec.id == ID
    s = t.spec.scope
    assert (s.gwp, s.lulucf, s.bunkers) == ("GWP*", "included", "excluded")
    assert s.baseline == "Change since 1850 (the reference year)"
    src = load_registry(Paths.default()).sources[jones.SOURCE]
    assert src.licence_class == "noncommercial"
    assert src.licence.spdx == "CC-BY-NC-SA-4.0"
    assert set(jones.PINNED) <= {str(a.url) for a in src.artifacts}
    assert {i.artifact_id for i in t.inputs} <= {a.id for a in src.artifacts}


def test_groups_are_not_entities_and_aliases_are():
    for g in jones.GROUPS:
        with pytest.raises(geo.UnknownEntity):
            geo.resolve(g, jones.SOURCE)
    assert geo.resolve("GLOBAL", jones.SOURCE) == "WLD"
    assert geo.resolve("EU27", jones.SOURCE) == "EU27"
    assert geo.resolve("KSV", jones.SOURCE) == "KOS"


# --- full file (local snapshot cache) -------------------------------------------------------------------------------


def _file() -> InputFile:
    paths = Paths.default()
    sha = snapshots.read_current(paths)[jones.GMST.key]
    snap = snapshots.read_manifest(paths, sha)
    assert snap is not None
    return InputFile(snapshots.cache_path(paths, sha), snap)


@pytest.fixture(scope="module")
def gmst() -> jones.Gmst:
    return jones.read_gmst(_file().path.read_bytes())


@pytest.mark.snapshot
def test_identities_hold(gmst):
    assert jones.check_identities(gmst) < Decimal("1e-13")


@pytest.mark.snapshot
def test_observations(gmst):
    obs = jones.observations(gmst)
    assert len(obs) == 221 * 174
    by = {(o.entity, o.period): o for o in obs}
    assert by[("WLD", "2024")].value == 1.67836118168202
    assert by[("USA", "2024")].value == 0.29624590833911
    assert by[("CHN", "2024")].value == 0.217370230595971
    assert ("EU27", "2024") in by and ("KOS", "2024") in by
    assert not {o.entity for o in obs} & jones.GROUPS
    assert by[("USA", "2024")].note is None
    assert by[("BMU", "2024")].note == (
        "The file has no land-use carbon dioxide, fossil methane, land-use methane, fossil nitrous oxide or land-use "
        "nitrous oxide rows for this entity; its three-gas value covers the rest."
    )
    assert by[("PSE", "2024")].note.startswith("The file has no fossil carbon dioxide, fossil methane")
    assert min(o.period for o in obs) == "1851" and max(o.period for o in obs) == "2024"


@pytest.mark.snapshot
def test_world_excludes_international_transport(gmst):
    """No rows for international aviation or shipping, and GLOBAL is the sum of the country rows."""
    assert not {iso for iso, _, _ in gmst.values} & {"XIA", "XIS", "INTL_AIR", "INTL_SEA"}
    broken = dict(gmst.values)
    key = ("USA", jones.TOTAL_GAS, "Total")
    broken[key] = {y: v + Decimal("0.001") for y, v in gmst.values[key].items()}
    # USA's own identities would fail first, so break the matching fossil part too.
    fkey = ("USA", jones.TOTAL_GAS, "Fossil")
    broken[fkey] = {y: v + Decimal("0.001") for y, v in gmst.values[fkey].items()}
    ckey = ("USA", "CO[2]", "Total")
    broken[ckey] = {y: v + Decimal("0.001") for y, v in gmst.values[ckey].items()}
    with pytest.raises(jones.JonesFormatError, match="GLOBAL"):
        jones.check_identities(jones.Gmst(broken, gmst.order))


@pytest.mark.snapshot
def test_build_exports_noncommercial_indicator(tmp_paths):
    shutil.copy(REPO_ROOT / "pipeline" / "sources" / f"{jones.SOURCE}.yaml", tmp_paths.sources)
    f = _file()
    snap, _ = snapshots.record(
        tmp_paths,
        data=f.path.read_bytes(),
        source_id=jones.SOURCE,
        artifact_id=jones.GMST.artifact_id,
        url=str(f.snapshot.url),
        acquisition="automatic",
        today=f.snapshot.date_accessed,
    )
    snapshots.set_current(tmp_paths, {jones.GMST.key: snap.sha256})
    reg = load_registry(tmp_paths)
    ts = [t for t in discover(tmp_paths) if t.spec.id == ID]
    report = build_and_export(tmp_paths, reg, ts)
    assert [o.state for o in report.outcomes] == ["built"], [o.reason for o in report.outcomes]
    ind = exported(tmp_paths.public_indicators / f"{ID}.json")
    assert ind["licence_class"] == "noncommercial"
    assert ind["licence"]["spdx"] == "CC-BY-NC-SA-4.0"
    assert "PRIMAP-hist v2.7" in ind["notice"]
    assert ind["vintage"] == "2025.1" and ind["latest"]["entity"] == "WLD"
