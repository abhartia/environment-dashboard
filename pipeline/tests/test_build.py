"""Build-key skip logic, licence-class routing and the export set, on real fixture slices."""

from __future__ import annotations

import json
import shutil

from envdash import canonical
from envdash.export import build_and_export
from envdash.registry import load_registry
from envdash.transform import discover
from envdash.validate import validate_all

from support import copy_sources, load_fixture_snapshot

ANNUAL = "co2.noaa-gml.annual-global"


def _annual_transform(paths):
    return [t for t in discover(paths) if t.spec.id == ANNUAL]


def test_build_then_skip_then_rebuild_on_key_change(tmp_paths, tmp_path):
    load_fixture_snapshot(tmp_paths, "noaa-gml-trends", "co2-annmean-gl")
    reg = load_registry(tmp_paths)
    ts = _annual_transform(tmp_paths)
    first = build_and_export(tmp_paths, reg, ts)
    assert [o.state for o in first.outcomes] == ["built"], first.outcomes[0].reason
    out = tmp_paths.public_indicators / f"{ANNUAL}.json"
    before = out.read_bytes()

    assert [o.state for o in build_and_export(tmp_paths, reg, ts).outcomes] == ["skipped"]

    # A different uv.lock changes the key: the transform runs again and the output is byte-identical.
    lock = tmp_path / "uv.lock"
    shutil.copy(tmp_paths.lock, lock)
    with lock.open("a") as f:
        f.write("\n")
    p2 = tmp_paths.with_(lock=lock)
    again = build_and_export(p2, reg, ts)
    assert [o.state for o in again.outcomes] == ["built"]
    ind = json.loads(out.read_text())
    assert ind["processing"][0]["lock_sha256"] == canonical.sha256_file(lock)
    assert json.loads(before)["observations"] == ind["observations"]

    # --force always rebuilds; a tampered export is rebuilt rather than trusted.
    assert [o.state for o in build_and_export(p2, reg, ts, force=True).outcomes] == ["built"]
    out.write_bytes(out.read_bytes().replace(b"425.62", b"425.63"))
    assert [o.state for o in build_and_export(p2, reg, ts).outcomes] == ["built"]
    assert b"425.62" in out.read_bytes()


def test_export_set_is_consistent_and_valid(tmp_paths):
    load_fixture_snapshot(tmp_paths, "noaa-gml-trends", "co2-annmean-gl")
    reg = load_registry(tmp_paths)
    report = build_and_export(tmp_paths, reg, _annual_transform(tmp_paths))
    assert report.ok
    d = tmp_paths.data
    csv = (tmp_paths.public_indicators / f"{ANNUAL}.csv").read_text()
    assert csv.startswith("# Carbon dioxide, global annual mean\n")
    assert "# Credit: NOAA Global Monitoring Laboratory (Lan, Tans & Thoning), version 2026-09" in csv
    assert "# Licence: Public domain" in csv
    assert "co2.noaa-gml.annual-global,WLD,2025,425.62,425.57,425.67,1sigma,preliminary,," in csv
    dp = json.loads((d / "datapackage.json").read_text())
    assert [r["name"] for r in dp["resources"]] == [ANNUAL]
    sums = (d / "SHA256SUMS").read_text()
    assert f"v1/indicators/{ANNUAL}.csv" in sums and "status.json" not in sums
    problems = validate_all(tmp_paths, reg)
    assert problems == [], problems


def test_display_only_never_under_data(tmp_paths, tmp_path):
    """Route a real series through a copy of its registry entry re-classed display-only: nothing reaches data/."""
    paths = copy_sources(tmp_paths, tmp_path, "noaa-gml-trends")
    y = paths.sources / "noaa-gml-trends.yaml"
    text = y.read_text().replace("licence_class: open", "licence_class: display-only")
    y.write_text(text.replace("  mirror_raw: true", "  mirror_raw: false"))
    load_fixture_snapshot(paths, "noaa-gml-trends", "co2-annmean-gl")
    reg = load_registry(paths)
    assert reg.sources["noaa-gml-trends"].licence_class == "display-only"
    report = build_and_export(paths, reg, _annual_transform(paths))
    assert report.ok, report.outcomes[0].reason

    assert (paths.private_indicators / f"{ANNUAL}.json").exists()
    public_files = [p.relative_to(paths.data).as_posix() for p in paths.data.rglob("*") if p.is_file()]
    assert not [p for p in public_files if ANNUAL in p and "indicators" in p]
    catalog = json.loads((paths.data / "v1" / "catalog.json").read_text())
    (entry,) = catalog["indicators"]
    assert entry["latest"] is None and entry["downloadable"] is False
    assert json.loads((paths.data / "datapackage.json").read_text())["resources"] == []
    # No value of the series appears anywhere under data/.
    for p in paths.data.rglob("*"):
        if p.is_file():
            assert "425.62" not in p.read_text(), p
    assert validate_all(paths, reg) == []

    # Re-classing back to open moves it to data/ and removes the private copy.
    y.write_text(text.replace("licence_class: display-only", "licence_class: open"))
    reg = load_registry(paths)
    assert build_and_export(paths, reg, _annual_transform(paths)).ok
    assert (paths.public_indicators / f"{ANNUAL}.json").exists()
    assert not (paths.private_indicators / f"{ANNUAL}.json").exists()


def test_failed_build_keeps_previous_export(tmp_paths):
    load_fixture_snapshot(tmp_paths, "noaa-gml-trends", "co2-annmean-gl")
    reg = load_registry(tmp_paths)
    ts = _annual_transform(tmp_paths)
    assert build_and_export(tmp_paths, reg, ts).ok
    out = tmp_paths.public_indicators / f"{ANNUAL}.json"
    good = out.read_bytes()
    # Point the artifact at the monthly Mauna Loa fixture: the annual transform must refuse it.
    load_fixture_snapshot(tmp_paths, "noaa-gml-trends", "co2-mm-mlo")
    from envdash import snapshots

    cur = snapshots.read_current(tmp_paths)
    snapshots.set_current(tmp_paths, {"noaa-gml-trends/co2-annmean-gl": cur["noaa-gml-trends/co2-mm-mlo"]})
    report = build_and_export(tmp_paths, reg, ts)
    assert [o.state for o in report.outcomes] == ["failed"]
    assert out.read_bytes() == good
    assert json.loads((tmp_paths.data / "v1" / "catalog.json").read_text())["indicators"][0]["id"] == ANNUAL
