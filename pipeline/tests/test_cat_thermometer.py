"""Climate Action Tracker thermometer (warming.cat-2025.thermometer).

CAT's terms do not allow adaptation, so the source is class no-derivatives. tests/fixtures holds slices of open-class
sources only (make_fixture.py refuses any other class and test_fixtures_provenance asserts it), so there is no
committed CAT fixture: the tests that read CAT's values are marked `snapshot` and read the full raw workbook from the
local snapshot cache (`uv run envdash fetch -s cat-2025-thermometer`, or restored from the private R2 bucket), as the
IPCC quote test does. The others check the registry entry and the transform's declaration and need no data.
"""

from __future__ import annotations

import copy
import io
import json
import shutil
from datetime import date
from pathlib import Path

import openpyxl
import pytest

from envdash import canonical, snapshots
from envdash.build import export_path
from envdash.export import build_and_export
from envdash.models import REDISTRIBUTABLE
from envdash.paths import REPO_ROOT, Paths
from envdash.registry import load_registry
from envdash.transform import discover, run_checks, validate
from envdash.transforms.future import cat_thermometer as cat
from envdash.validate import validate_all

ID = "warming.cat-2025.thermometer"
SHA = "44044cda8f851f77d6ca0eeb0750848fb6ee32bab50939df2cc2363e63a8c6c1"
"""The COP30 workbook, 1,165,847 bytes, fetched 2026-10-04 (pipeline/manifests/snapshots/<SHA>.json)."""

# CAT Thermometer sheet, rows 15, 19, 20 and 22, columns D / E / F (Lower bound / Median / Upper bound), as displayed.
TABLE = {
    "policies-action": (2.1, 2.6, 3.3),
    "targets-2030-2035": (2.1, 2.6, 3.2),
    "pledges-targets": (1.8, 2.2, 2.8),
    "optimistic": (1.5, 1.9, 2.4),
}


def _transform(paths: Paths):
    (t,) = [t for t in discover(paths) if t.spec.id == ID]
    return t


# --- no data needed ------------------------------------------------------------------------------------------------


def test_registry_entry_is_no_derivatives_with_its_obligations():
    src = load_registry(Paths.default()).sources[cat.SOURCE]
    assert src.licence_class == "no-derivatives" and src.licence_class not in REDISTRIBUTABLE
    assert src.obligations.mirror_raw is False
    assert src.obligations.attribution_modified is None
    assert "All rights reserved." in src.evidence.licence_quote
    assert "view, download, print and distribute" in src.evidence.licence_quote
    assert src.obligations.notice.startswith("Copyright © 2025 by Climate Analytics and NewClimate Institute.")
    assert [a.id for a in src.artifacts] == [cat.WORKBOOK.artifact_id]


def test_transform_declares_one_verbatim_indicator_routed_to_data_private():
    paths = Paths.default()
    t = _transform(paths)
    assert t.inputs == (cat.WORKBOOK,)
    assert [v.id for v in t.spec.dimensions[0].values] == list(TABLE)
    assert dict(t.spec.headline_dims) == {"scenario": "policies-action"}
    assert export_path(paths, ID, "no-derivatives") == paths.private_indicators / f"{ID}.json"
    # Each publisher check names one declared scenario, for this vintage.
    assert {c.vintage for c in t.checks} == {cat.VINTAGE}
    assert {dict(c.dims)["scenario"] for c in t.checks} == set(TABLE)
    for c in t.checks:
        assert c.stated in c.quote and c.url.startswith("https://climateactiontracker.org/")


# --- full raw snapshot ---------------------------------------------------------------------------------------------


def _raw() -> bytes:
    p = snapshots.cache_path(Paths.default(), SHA)
    if not p.exists():
        pytest.skip(f"raw snapshot {SHA[:12]} not in the local cache; run envdash fetch -s {cat.SOURCE}")
    raw = p.read_bytes()
    assert canonical.sha256_bytes(raw) == SHA
    return raw


def _edited(raw: bytes, edit) -> bytes:
    wb = openpyxl.load_workbook(io.BytesIO(raw))
    edit(wb)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


@pytest.mark.snapshot
def test_published_values_equal_the_table_cells():
    obs, published = cat.parse(_raw())
    assert published.date() == date(2025, 11, 13)
    got = {o.dims["scenario"]: (o.lower, o.value, o.upper) for o in obs}
    assert got == TABLE
    assert {(o.entity, o.period, o.status, o.interval) for o in obs} == {("WLD", "2100", "projection", "range")}
    assert "High and Low variants" in next(o.note for o in obs if o.dims["scenario"] == "policies-action")


@pytest.mark.snapshot
def test_publisher_statements_for_november_2025_pass():
    t = _transform(Paths.default())
    obs, _ = cat.parse(_raw())
    validate(t, obs)
    outcomes = run_checks(t, {cat.SOURCE: cat.VINTAGE}, obs)
    assert [o.status for o in outcomes] == ["pass"] * 4, [o.detail for o in outcomes]
    # A later CAT update is not checked against these statements.
    assert {o.status for o in run_checks(t, {cat.SOURCE: "November 2026"}, obs)} == {"not-applicable"}


@pytest.mark.snapshot
@pytest.mark.parametrize(
    ("edit", "match"),
    [
        # A cell holding more digits than the table displays must not be published.
        (lambda wb: setattr(wb["CAT Thermometer"]["E20"], "value", 2.23), "more digits than the table displays"),
        (lambda wb: setattr(wb["CAT Thermometer"]["E15"], "number_format", "0.00"), "not one decimal"),
        # Which rows are on the thermometer is the sheet's bold marking; a change stops the build.
        (
            lambda wb: setattr(wb["CAT Thermometer"]["D18"], "font", copy.copy(wb["CAT Thermometer"]["D15"].font)),
            "some value cells are bold",
        ),
        (lambda wb: setattr(wb["CAT Thermometer"]["B20"], "value", "Pledges"), "row 20 reads"),
        (lambda wb: setattr(wb["CAT Thermometer"]["B24"], "value", "Values in bold are old."), "re-read the file"),
        (lambda wb: setattr(wb["Info"]["B32"], "value", "Copyright"), "Info!B32"),
    ],
    ids=["unrounded", "format", "bold", "label", "bold-note", "copyright"],
)
def test_refuses_a_workbook_that_differs_from_the_read_layout(edit, match):
    with pytest.raises(cat.CatFormatError, match=match):
        cat.parse(_edited(_raw(), edit))


def _tmp_store(tmp_path: Path) -> Paths:
    """This source's registry entry, and the real workbook recorded in a temporary snapshot store."""
    sources = tmp_path / "sources"
    sources.mkdir()
    shutil.copy(REPO_ROOT / "pipeline" / "sources" / f"{cat.SOURCE}.yaml", sources / f"{cat.SOURCE}.yaml")
    lit = tmp_path / "literature"
    lit.mkdir()
    paths = Paths.default().with_(
        sources=sources,
        literature=lit,
        manifests=tmp_path / "manifests",
        cache=tmp_path / "cache",
        data=tmp_path / "data",
        private=tmp_path / "data-private",
        schema=tmp_path / "schema",
    )
    meta = snapshots.read_manifest(Paths.default(), SHA)
    assert meta is not None
    snap, _ = snapshots.record(
        paths,
        data=_raw(),
        source_id=cat.SOURCE,
        artifact_id=cat.WORKBOOK.artifact_id,
        url=str(meta.url),
        acquisition="automatic",
        today=meta.date_accessed,
    )
    snapshots.set_current(paths, {cat.WORKBOOK.key: snap.sha256})
    return paths


@pytest.mark.snapshot
def test_build_writes_only_the_private_export(tmp_path):
    paths = _tmp_store(tmp_path)
    reg = load_registry(paths)
    report = build_and_export(paths, reg, [_transform(paths)])
    assert report.ok, [(o.id, o.reason) for o in report.outcomes]

    ind = json.loads((paths.private_indicators / f"{ID}.json").read_text())
    assert ind["licence_class"] == "no-derivatives" and ind["vintage"] == "November 2025"
    assert ind["notice"].startswith("Copyright © 2025 by Climate Analytics and NewClimate Institute.")
    assert "Changes:" not in ind["attribution"]
    assert ind["origins"][0]["sha256"] == SHA and ind["origins"][0]["r2_url"] is None
    assert {o["dims"]["scenario"]: (o["lower"], o["value"], o["upper"]) for o in ind["observations"]} == TABLE

    (entry,) = json.loads((paths.data / "v1" / "catalog.json").read_text())["indicators"]
    assert entry["id"] == ID and entry["latest"] is None and entry["downloadable"] is False
    assert not [p for p in paths.data.rglob("*") if p.is_file() and ID in p.name]
    assert json.loads((paths.data / "datapackage.json").read_text())["resources"] == []
    assert validate_all(paths, reg) == []
