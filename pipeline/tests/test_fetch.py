"""Fetch logic against an in-process HTTP handler that serves the real fixture bytes."""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from envdash import fetch, snapshots
from envdash.registry import load_registry

from support import copy_sources, fixture


def _serve(seen: list[httpx.Request]):
    terms, _ = fixture("noaa-gml-trends", "co2-mm-mlo")
    body = terms.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.headers.get("if-none-match") == '"real-etag"':
            return httpx.Response(304)
        return httpx.Response(200, content=body, headers={"etag": '"real-etag"', "content-type": "text/csv"})

    return handler


def _one_artifact_registry(tmp_paths, tmp_path):
    paths = copy_sources(tmp_paths, tmp_path, "noaa-gml-trends")
    y = paths.sources / "noaa-gml-trends.yaml"
    text = y.read_text()
    head, arts = text.split("artifacts:\n", 1)
    first = arts.split("  - id: co2-annmean-mlo", 1)[0]
    rest = arts.split("status:\n", 1)[1]
    y.write_text(head + "artifacts:\n" + first + "status:\n" + rest)
    return paths


def test_conditional_get_and_pointer(tmp_paths, tmp_path):
    paths = _one_artifact_registry(tmp_paths, tmp_path)
    reg = load_registry(paths)
    assert [a.id for a in reg.sources["noaa-gml-trends"].artifacts] == ["co2-mm-mlo"]
    seen: list[httpx.Request] = []
    with fetch.make_client(httpx.MockTransport(_serve(seen))) as c:
        r1 = fetch.fetch_all(paths, reg, today=date(2026, 10, 4), client=c)["noaa-gml-trends"]
        assert r1.state == "ok" and r1.terms == "unchanged"
        r2 = fetch.fetch_all(paths, reg, today=date(2026, 10, 11), client=c)["noaa-gml-trends"]
    assert r2.state == "unchanged" and r2.artifacts[0].outcome == "not-modified"
    data_requests = [r for r in seen if r.url.path.endswith("co2_mm_mlo.csv")]
    assert data_requests[-1].headers["if-none-match"] == '"real-etag"'
    assert "EnvironmentDashboard" in data_requests[-1].headers["user-agent"]
    sha = snapshots.read_current(paths)["noaa-gml-trends/co2-mm-mlo"]
    assert snapshots.read_manifest(paths, sha).date_accessed == date(2026, 10, 4)  # first fetch, immutable


def test_size_limit(tmp_paths):
    seen: list[httpx.Request] = []
    with fetch.make_client(httpx.MockTransport(_serve(seen))) as c, pytest.raises(fetch.PermanentFetchError):
        fetch.download(c, "https://gml.noaa.gov/x.csv", max_bytes=1000)


def test_changed_terms_freeze_the_source(tmp_paths, tmp_path):
    paths = _one_artifact_registry(tmp_paths, tmp_path)
    y = paths.sources / "noaa-gml-trends.yaml"
    y.write_text(y.read_text().replace("made freely available", "made available"))
    reg = load_registry(paths)
    with fetch.make_client(httpx.MockTransport(_serve([]))) as c:
        r = fetch.fetch_all(paths, reg, client=c)["noaa-gml-trends"]
    assert r.state == "failed" and r.terms == "changed" and r.artifacts == []
    assert snapshots.read_current(paths) == {}


def test_manual_snapshot_keeps_first_access_date(tmp_paths):
    path, meta = fixture("hadcrut5", "global-monthly")
    data = path.read_bytes()
    snap, new = snapshots.record(
        tmp_paths,
        data=data,
        source_id="hadcrut5",
        artifact_id="global-monthly",
        url=None,
        acquisition="manual",
        today=date(2026, 10, 4),
        note="downloaded in a browser from the HadCRUT5 download page",
    )
    assert new and snap.acquisition == "manual" and snap.url is None
    again, new2 = snapshots.record(
        tmp_paths,
        data=data,
        source_id="hadcrut5",
        artifact_id="global-monthly",
        url=meta["url"],
        acquisition="automatic",
        today=date(2026, 11, 1),
    )
    assert not new2 and again == snap
    with pytest.raises(ValueError):
        snapshots.update_manifest(tmp_paths, snap.sha256, date_accessed=date(2026, 11, 1))
