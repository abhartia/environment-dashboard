from __future__ import annotations

import shutil
from datetime import date

from envdash import snapshots
from envdash.export import build_and_export
from envdash.fetch import SourceFetch, manual_fetch
from envdash.models import Status
from envdash.paths import REPO_ROOT
from envdash.registry import load_registry
from envdash.status import update_status
from envdash.transform import discover
from envdash.transforms.action import ivanova_2020 as iv

from support import fixture, load_fixture_snapshot


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


def test_a_passing_build_lifts_a_manual_sources_build_failure_only(tmp_paths):
    # ivanova-2020 is acquired by hand, so its fetch result is known without a request; noaa-gml-trends is automatic.
    shutil.copy(REPO_ROOT / "pipeline" / "sources" / "ivanova-2020.yaml", tmp_paths.sources / "ivanova-2020.yaml")
    reg = load_registry(tmp_paths)
    path, meta = fixture("ivanova-2020", "article-pdf")
    article, _ = snapshots.record(
        tmp_paths,
        data=path.read_bytes(),
        source_id="ivanova-2020",
        artifact_id="article-pdf",
        url=meta["url"],
        acquisition="manual",
        today=date.fromisoformat(meta["date_accessed"]),
        note="test fixture: the whole article PDF",
    )
    wrong = load_fixture_snapshot(tmp_paths, "noaa-gml-trends", "co2-annmean-gl")
    key = snapshots.key("ivanova-2020", "article-pdf")
    ts = [t for t in discover(tmp_paths) if t.spec.id in {iv.INDICATOR, "co2.noaa-gml.annual-global"}]

    # Run 1: a person records the wrong file as the article, so its build fails; NOAA's fetch fails, its build passes.
    snapshots.set_current(tmp_paths, {key: wrong})
    fetched = {
        "ivanova-2020": manual_fetch(reg.sources["ivanova-2020"], "2026-10-06T10:00:00Z"),
        "noaa-gml-trends": SourceFetch("noaa-gml-trends", "failed", "2026-10-06T10:00:01Z", reason="HTTP 503 from x"),
    }
    st = update_status(tmp_paths, reg, fetched=fetched, built=build_and_export(tmp_paths, reg, ts))
    assert st.sources["ivanova-2020"].state == "failed" and iv.INDICATOR in st.sources["ivanova-2020"].reason
    assert st.sources["ivanova-2020"].last_success is None
    assert st.sources["noaa-gml-trends"].state == "failed"

    # Run 2, a build alone: the article is recorded again and builds. The manual source is manual again; the automatic
    # source's failed fetch stands, because no fetch has run since.
    snapshots.set_current(tmp_paths, {key: article.sha256})
    built = build_and_export(tmp_paths, reg, ts)
    assert {o.id: o.state for o in built.outcomes} == {iv.INDICATOR: "built", "co2.noaa-gml.annual-global": "skipped"}
    st = update_status(tmp_paths, reg, built=built)
    e = st.sources["ivanova-2020"]
    (ind,) = [o.indicator for o in built.outcomes if o.id == iv.INDICATOR]
    assert (e.state, e.reason, e.terms) == ("manual", None, None)  # its terms are re-checked in the PDF, not by hand
    assert e.last_success == e.checked_at == st.generated_at
    assert e.vintage == ind.vintage and e.manual_last_verified == date.fromisoformat(meta["date_accessed"])
    n = st.sources["noaa-gml-trends"]
    assert (n.state, n.reason, n.checked_at) == ("failed", "HTTP 503 from x", "2026-10-06T10:00:01Z")
