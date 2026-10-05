from __future__ import annotations

from envdash.export import build_and_export
from envdash.fetch import SourceFetch
from envdash.models import Status
from envdash.registry import load_registry
from envdash.status import update_status
from envdash.transform import discover

from support import load_fixture_snapshot


def test_status_written_every_run_and_failures_recorded(tmp_paths):
    reg = load_registry(tmp_paths)
    # A run where nothing was fetched or built still writes the heartbeat.
    st = update_status(tmp_paths, reg)
    assert tmp_paths.status_file.exists() and st.sources == {}

    fetched = {
        "noaa-gml-trends": SourceFetch("noaa-gml-trends", "ok", "2026-10-04T12:00:00Z", terms="unchanged"),
        "hadcrut5": SourceFetch("hadcrut5", "failed", "2026-10-04T12:00:01Z", reason="HTTP 503 from x"),
    }
    load_fixture_snapshot(tmp_paths, "noaa-gml-trends", "co2-annmean-gl")
    ts = [t for t in discover(tmp_paths) if t.spec.id == "co2.noaa-gml.annual-global"]
    built = build_and_export(tmp_paths, reg, ts)
    st = update_status(tmp_paths, reg, fetched=fetched, built=built)
    on_disk = Status.model_validate_json(tmp_paths.status_file.read_bytes())
    assert on_disk == st
    assert st.sources["noaa-gml-trends"].state == "ok"
    assert st.sources["noaa-gml-trends"].vintage == "2026-09"
    assert st.sources["noaa-gml-trends"].last_success == "2026-10-04T12:00:00Z"
    assert st.sources["hadcrut5"].state == "failed" and st.sources["hadcrut5"].last_success is None

    # Next run: noaa unchanged but its build fails -> failed, keeping its last success and vintage.
    from envdash import snapshots

    load_fixture_snapshot(tmp_paths, "noaa-gml-trends", "co2-mm-mlo")
    cur = snapshots.read_current(tmp_paths)
    snapshots.set_current(tmp_paths, {"noaa-gml-trends/co2-annmean-gl": cur["noaa-gml-trends/co2-mm-mlo"]})
    built = build_and_export(tmp_paths, reg, ts)
    fetched = {"noaa-gml-trends": SourceFetch("noaa-gml-trends", "unchanged", "2026-10-11T12:00:00Z")}
    st = update_status(tmp_paths, reg, fetched=fetched, built=built)
    e = st.sources["noaa-gml-trends"]
    assert e.state == "failed" and "co2.noaa-gml.annual-global" in e.reason
    assert e.last_success == "2026-10-04T12:00:00Z" and e.vintage == "2026-09"
    assert st.sources["hadcrut5"].reason == "HTTP 503 from x"  # not checked this run: kept as it was
