"""API keys, terms checks on API responses and content keys, against an in-process handler serving real bytes."""

from __future__ import annotations

import io
import zipfile
from datetime import date

import httpx
import pytest
import yaml

from envdash import contentkey, fetch, snapshots
from envdash.registry import load_registry

from support import copy_sources, fixture

TEST_KEY = "test-value-for-the-in-process-handler"


def _edit(paths, source_id: str, change) -> None:
    y = paths.sources / f"{source_id}.yaml"
    doc = yaml.safe_load(y.read_text())
    change(doc)
    y.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))


def _real_csv() -> bytes:
    return fixture("noaa-gml-trends", "co2-mm-mlo")[0].read_bytes()


def _gfw_one_artifact(tmp_paths, tmp_path, access: dict):
    paths = copy_sources(tmp_paths, tmp_path, "gfw-tree-cover-loss")

    def change(doc):
        doc["evidence"]["terms_check"] = "manual"
        doc["artifacts"] = doc["artifacts"][:1]
        doc["artifacts"][0]["access"] = access

    _edit(paths, "gfw-tree-cover-loss", change)
    return paths


def _fetch(paths, handler, today=date(2026, 10, 4)):
    reg = load_registry(paths)
    assert not reg.source_errors, reg.source_errors
    with fetch.make_client(httpx.MockTransport(handler)) as c:
        return fetch.fetch_all(paths, reg, today=today, client=c)


def test_api_key_in_header(tmp_paths, tmp_path, monkeypatch):
    monkeypatch.setenv("GFW_API_KEY", TEST_KEY)
    paths = _gfw_one_artifact(
        tmp_paths, tmp_path, {"auth": "api-key", "auth_env": "GFW_API_KEY", "key_header": "x-api-key"}
    )
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=_real_csv(), headers={"content-type": "text/csv"})

    r = _fetch(paths, handler)["gfw-tree-cover-loss"]
    assert r.state == "ok", r.reason
    assert seen[-1].headers["x-api-key"] == TEST_KEY and TEST_KEY not in str(seen[-1].url)
    snap = snapshots.read_manifest(paths, r.artifacts[0].sha256)
    assert TEST_KEY not in snap.model_dump_json()


def test_api_key_in_query_is_never_recorded(tmp_paths, tmp_path, monkeypatch):
    monkeypatch.setenv("GFW_API_KEY", TEST_KEY)
    paths = _gfw_one_artifact(
        tmp_paths, tmp_path, {"auth": "api-key", "auth_env": "GFW_API_KEY", "key_query": "x-api-key"}
    )
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=_real_csv())

    r = _fetch(paths, handler)["gfw-tree-cover-loss"]
    assert r.state == "ok", r.reason
    assert seen[-1].url.params["x-api-key"] == TEST_KEY
    assert "sql" in seen[-1].url.params  # the registry URL's own query is kept
    snap = snapshots.read_manifest(paths, r.artifacts[0].sha256)
    assert TEST_KEY not in snap.model_dump_json()


def test_api_key_request_does_not_follow_redirects(tmp_paths, tmp_path, monkeypatch):
    monkeypatch.setenv("GFW_API_KEY", TEST_KEY)
    paths = _gfw_one_artifact(
        tmp_paths, tmp_path, {"auth": "api-key", "auth_env": "GFW_API_KEY", "key_query": "x-api-key"}
    )
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(307, headers={"location": f"https://elsewhere.example.org/x?x-api-key={TEST_KEY}"})

    r = _fetch(paths, handler)["gfw-tree-cover-loss"]
    assert r.state == "failed" and "does not follow redirects" in r.reason
    assert TEST_KEY not in r.reason and len(seen) == 1


def test_missing_key_and_unimplemented_auth_fail_clearly(tmp_paths, tmp_path, monkeypatch):
    monkeypatch.delenv("GFW_API_KEY", raising=False)
    paths = _gfw_one_artifact(
        tmp_paths, tmp_path, {"auth": "api-key", "auth_env": "GFW_API_KEY", "key_header": "x-api-key"}
    )
    r = _fetch(paths, lambda request: httpx.Response(200, content=_real_csv()))["gfw-tree-cover-loss"]
    assert r.state == "failed" and "$GFW_API_KEY, which is not set" in r.reason

    paths = _gfw_one_artifact(tmp_paths, tmp_path, {"auth": "api-key", "auth_env": "GFW_API_KEY"})
    r = _fetch(paths, lambda request: httpx.Response(200, content=_real_csv()))["gfw-tree-cover-loss"]
    assert r.state == "failed" and "neither access.key_header nor access.key_query" in r.reason

    paths = _gfw_one_artifact(tmp_paths, tmp_path, {"auth": "cmems", "auth_env": "CMEMS_PASSWORD"})
    r = _fetch(paths, lambda request: httpx.Response(200, content=_real_csv()))["gfw-tree-cover-loss"]
    assert r.state == "failed" and "cmems" in r.reason and "does not implement" in r.reason


def test_terms_check_api_matches_the_json_response(tmp_paths, tmp_path):
    """gcp-fossil-co2-2025's terms_url is the metadata JSON on Zenodo; the fixture is that whole file."""
    body = fixture("gcp-fossil-co2-2025", "mtco2-metadata")[0].read_bytes()
    paths = copy_sources(tmp_paths, tmp_path, "gcp-fossil-co2-2025")
    src = load_registry(paths).sources["gcp-fossil-co2-2025"]
    assert src.evidence.terms_check == "api"
    serve = httpx.MockTransport(
        lambda request: httpx.Response(200, content=body, headers={"content-type": "text/plain"})
    )
    with fetch.make_client(serve) as c:
        assert fetch.check_terms(c, src) == ("unchanged", None)
        changed = src.model_copy(
            update={
                "evidence": src.evidence.model_copy(
                    update={"licence_quote": "Licensed under Creative Commons Attribution-NonCommercial 4.0"}
                )
            }
        )
        assert fetch.check_terms(c, changed)[0] == "changed"


def _rezip(data: bytes, *, date_time=(2030, 1, 2, 3, 4, 6), change: tuple[str, bytes] | None = None) -> bytes:
    """The same real members written again, in reverse order with other timestamps (and optionally one changed)."""
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as z:
        for info in reversed(src.infolist()):
            body = src.read(info)
            if change and info.filename == change[0]:
                body = change[1]
            z.writestr(zipfile.ZipInfo(info.filename, date_time=date_time), body)
    return out.getvalue()


def test_zip_members_fingerprint_ignores_timestamps_and_order():
    data = fixture("natural-earth", "admin-0-tiny-countries-50m")[0].read_bytes()
    again = _rezip(data)
    assert again != data
    assert contentkey.zip_members_sha256(again) == contentkey.zip_members_sha256(data)
    version = "ne_50m_admin_0_tiny_countries.VERSION.txt"
    other = _rezip(data, change=(version, zipfile.ZipFile(io.BytesIO(data)).read(version) + b"\n"))
    assert contentkey.zip_members_sha256(other) != contentkey.zip_members_sha256(data)
    # Removing a pattern from member names: names that collide are an error, never merged.
    with pytest.raises(contentkey.ContentKeyError, match="two members"):
        contentkey.zip_members_sha256(data, r"\.[a-zA-Z]+$")


def test_unchanged_zip_content_keeps_the_current_snapshot(tmp_paths, tmp_path):
    data = fixture("natural-earth", "admin-0-tiny-countries-50m")[0].read_bytes()
    paths = copy_sources(tmp_paths, tmp_path, "natural-earth")

    def change(doc):
        doc["evidence"]["terms_check"] = "manual"
        doc["artifacts"] = [a for a in doc["artifacts"] if a["id"] == "admin-0-tiny-countries-50m"]
        doc["artifacts"][0]["content_key"] = "zip-members"
        doc["artifacts"][0]["access"] = {"conditional": False}

    _edit(paths, "natural-earth", change)
    bodies = [data, _rezip(data), _rezip(data, change=("ne_50m_admin_0_tiny_countries.VERSION.txt", b"5.1.1\n\n"))]

    def handler(request):
        return httpx.Response(200, content=bodies[0])

    k = "natural-earth/admin-0-tiny-countries-50m"
    first = _fetch(paths, handler)["natural-earth"]
    sha1 = snapshots.read_current(paths)[k]
    assert first.state == "ok" and snapshots.read_manifest(paths, sha1).content_sha256 is not None

    bodies.pop(0)
    second = _fetch(paths, handler, date(2026, 10, 11))["natural-earth"]
    assert second.state == "unchanged" and second.artifacts[0].outcome == "same"
    assert "content unchanged" in second.artifacts[0].reason
    assert snapshots.read_current(paths)[k] == sha1

    bodies.pop(0)
    third = _fetch(paths, handler, date(2026, 10, 18))["natural-earth"]
    assert third.state == "ok" and snapshots.read_current(paths)[k] != sha1
