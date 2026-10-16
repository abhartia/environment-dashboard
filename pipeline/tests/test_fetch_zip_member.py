"""Reading one member of a remote zip by HTTP Range requests (envdash/zipmember.py, Artifact.zip_member), against an
in-process handler that serves the bytes of a real zip fixture (Natural Earth's tiny-countries zip) by range."""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date

import httpx
import pytest
import yaml

from envdash import fetch, snapshots, zipmember
from envdash.models import Artifact
from envdash.registry import load_registry

from support import copy_sources, fixture

ZIP_URL = "https://zenodo.org/api/records/22919723/files/power_heat-plants.zip/content"
RANGE = re.compile(r"^bytes=(\d+)-(\d+)$")


@pytest.fixture(autouse=True)
def _no_pacing(monkeypatch):
    monkeypatch.setattr(zipmember, "MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(zipmember, "BACKOFF_SECONDS", (0.0, 0.0, 0.0))


def _real_zip() -> bytes:
    return fixture("natural-earth", "admin-0-tiny-countries-50m")[0].read_bytes()


def _ranged(
    data: bytes,
    seen: list[str] | None = None,
    *,
    etag: str | None = '"a"',
    last_modified: str | None = None,
    ignore_range: bool = False,
):
    validators = {k: v for k, v in (("etag", etag), ("last-modified", last_modified)) if v is not None}

    def handler(request: httpx.Request) -> httpx.Response:
        rng = request.headers.get("range", "")
        if seen is not None:
            seen.append(rng)
        m = RANGE.match(rng)
        if ignore_range or not m:
            return httpx.Response(200, content=data, headers=validators)
        a, b = int(m.group(1)), min(int(m.group(2)), len(data) - 1)
        return httpx.Response(
            206,
            content=data[a : b + 1],
            headers={"content-range": f"bytes {a}-{b}/{len(data)}", **validators},
        )

    return handler


def test_reads_one_member_exactly_with_few_requests():
    data = _real_zip()
    names = [i.filename for i in zipfile.ZipFile(io.BytesIO(data)).infolist()]
    member = next(n for n in names if n.endswith(".dbf"))
    seen: list[str] = []
    with httpx.Client(transport=httpx.MockTransport(_ranged(data, seen))) as c:
        remote = zipmember.RemoteZip(c, ZIP_URL)
        z = zipmember.open_zip(remote)
        m = zipmember.read_member(remote, z, member, max_bytes=10_000_000)
    assert m.data == zipfile.ZipFile(io.BytesIO(data)).read(member)
    assert m.zip_bytes == len(data) and m.etag == '"a"'
    # One byte for the size, the tail; this zip is smaller than the tail, so the member needs no third request.
    assert seen == ["bytes=0-0", f"bytes=0-{len(data) - 1}"]


def test_a_member_outside_the_tail_costs_one_more_request(monkeypatch):
    data = _real_zip()
    monkeypatch.setattr(zipmember, "TAIL_BYTES", 2048)
    z0 = zipfile.ZipFile(io.BytesIO(data))
    first = min(z0.infolist(), key=lambda i: i.header_offset)
    seen: list[str] = []
    with httpx.Client(transport=httpx.MockTransport(_ranged(data, seen))) as c:
        remote = zipmember.RemoteZip(c, ZIP_URL)
        z = zipmember.open_zip(remote)
        m = zipmember.read_member(remote, z, first.filename, max_bytes=10_000_000)
    assert m.data == z0.read(first)
    # The first member starts at byte 0, already held from the size request: the third request starts after it.
    assert first.header_offset == 0
    assert len(seen) == 3 and seen[2].startswith("bytes=1-")


def test_a_server_ignoring_range_is_refused():
    with (
        httpx.Client(transport=httpx.MockTransport(_ranged(_real_zip(), ignore_range=True))) as c,
        pytest.raises(zipmember.ZipMemberError, match="does not serve byte ranges"),
    ):
        zipmember.RemoteZip(c, ZIP_URL)


def test_a_zip_replaced_between_requests_is_refused(monkeypatch):
    data = _real_zip()
    monkeypatch.setattr(zipmember, "TAIL_BYTES", 2048)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return _ranged(data, etag='"a"' if calls["n"] < 3 else '"b"')(request)

    z0 = zipfile.ZipFile(io.BytesIO(data))
    first = min(z0.infolist(), key=lambda i: i.header_offset)
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        remote = zipmember.RemoteZip(c, ZIP_URL)
        z = zipmember.open_zip(remote)
        with pytest.raises(zipmember.ZipMemberError, match="changed between two range requests"):
            zipmember.read_member(remote, z, first.filename, max_bytes=10_000_000)


def test_missing_member_and_size_limit():
    data = _real_zip()
    member = zipfile.ZipFile(io.BytesIO(data)).infolist()[0].filename
    with httpx.Client(transport=httpx.MockTransport(_ranged(data))) as c:
        remote = zipmember.RemoteZip(c, ZIP_URL)
        z = zipmember.open_zip(remote)
        with pytest.raises(zipmember.ZipMemberError, match="has no member"):
            zipmember.read_member(remote, z, "co2e_100yr/DATA/none.csv", max_bytes=10_000_000)
        with pytest.raises(zipmember.ZipMemberError, match="over the 1-byte limit"):
            zipmember.read_member(remote, z, member, max_bytes=1)


def test_artifact_rules():
    base = {"id": "x", "url": ZIP_URL, "description": "d"}
    Artifact.model_validate({**base, "format": "csv", "zip_member": "co2e_100yr/DATA/x.csv"})
    with pytest.raises(ValueError, match="format is the member's"):
        Artifact.model_validate({**base, "format": "zip", "zip_member": "a.csv"})
    with pytest.raises(ValueError, match="needs the zip's url"):
        Artifact.model_validate({**base, "url": None, "format": "csv", "zip_member": "a.csv"})


def _members_registry(tmp_paths, tmp_path, data: bytes, suffixes: tuple[str, ...]):
    """A copy of natural-earth whose artifacts are members of the real tiny-countries zip, read from ZIP_URL."""
    infos = zipfile.ZipFile(io.BytesIO(data)).infolist()
    paths = copy_sources(tmp_paths, tmp_path, "natural-earth")
    y = paths.sources / "natural-earth.yaml"
    doc = yaml.safe_load(y.read_text())
    doc["evidence"]["terms_check"] = "manual"
    doc["artifacts"] = [
        {
            "id": f"member-{suffix}",
            "url": ZIP_URL,
            "format": "txt",
            "description": "one member",
            "zip_member": next(i.filename for i in infos if i.filename.endswith(f".{suffix}")),
        }
        for suffix in suffixes
    ]
    y.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
    reg = load_registry(paths)
    assert not reg.source_errors, reg.source_errors
    return paths, reg


def test_fetch_records_the_member_with_the_zip_url(tmp_paths, tmp_path):
    data = _real_zip()
    member = next(i.filename for i in zipfile.ZipFile(io.BytesIO(data)).infolist() if i.filename.endswith(".prj"))
    paths, reg = _members_registry(tmp_paths, tmp_path, data, ("prj",))
    with fetch.make_client(httpx.MockTransport(_ranged(data))) as c:
        r = fetch.fetch_all(paths, reg, today=date(2026, 10, 8), client=c)["natural-earth"]
        assert r.state == "ok", r.reason
    sha = snapshots.read_current(paths)["natural-earth/member-prj"]
    snap = snapshots.read_manifest(paths, sha)
    assert snap.zip_member == member and str(snap.url) == ZIP_URL and snap.etag == '"a"'
    assert snap.zip_bytes == len(data) and snap.last_modified is None
    assert snapshots.cache_path(paths, sha).read_bytes() == zipfile.ZipFile(io.BytesIO(data)).read(member)
    assert snap.date_accessed == date(2026, 10, 8)


def test_an_unchanged_zip_is_not_read_again(tmp_paths, tmp_path):
    """Same size, ETag and Last-Modified as when the current snapshots were read: one one-byte request for the zip,
    however many of its members are registered, and every member keeps its snapshot."""
    data = _real_zip()
    paths, reg = _members_registry(tmp_paths, tmp_path, data, ("prj", "dbf", "shx"))
    lm = "Tue, 10 Jun 2025 13:12:59 GMT"
    with fetch.make_client(httpx.MockTransport(_ranged(data, etag='"a"', last_modified=lm))) as c:
        first = fetch.fetch_all(paths, reg, today=date(2026, 10, 8), client=c)["natural-earth"]
    assert first.state == "ok" and {a.outcome for a in first.artifacts} == {"new"}
    before = snapshots.read_current(paths)
    seen: list[str] = []
    with fetch.make_client(httpx.MockTransport(_ranged(data, seen, etag='"a"', last_modified=lm))) as c:
        again = fetch.fetch_all(paths, reg, today=date(2026, 10, 15), client=c)["natural-earth"]
    assert again.state == "unchanged", again.reason
    assert [a.outcome for a in again.artifacts] == ["not-modified"] * 3
    assert seen == ["bytes=0-0"]
    assert snapshots.read_current(paths) == before


@pytest.mark.parametrize(
    ("change", "validators"),
    [
        ("etag", {"etag": '"b"', "last_modified": "Tue, 10 Jun 2025 13:12:59 GMT"}),
        ("last-modified", {"etag": '"a"', "last_modified": "Wed, 11 Jun 2025 08:00:00 GMT"}),
        ("no validators", {"etag": None, "last_modified": None}),
        ("bytes not cached", {"etag": '"a"', "last_modified": "Tue, 10 Jun 2025 13:12:59 GMT"}),
    ],
)
def test_a_changed_zip_is_read_again(tmp_paths, tmp_path, change, validators):
    data = _real_zip()
    paths, reg = _members_registry(tmp_paths, tmp_path, data, ("prj", "dbf"))
    first_validators = (
        {"etag": None, "last_modified": None}
        if change == "no validators"
        else {"etag": '"a"', "last_modified": "Tue, 10 Jun 2025 13:12:59 GMT"}
    )
    with fetch.make_client(httpx.MockTransport(_ranged(data, **first_validators))) as c:
        assert fetch.fetch_all(paths, reg, today=date(2026, 10, 8), client=c)["natural-earth"].state == "ok"
    if change == "bytes not cached":
        snapshots.cache_path(paths, snapshots.read_current(paths)["natural-earth/member-dbf"]).unlink()
    seen: list[str] = []
    with fetch.make_client(httpx.MockTransport(_ranged(data, seen, **validators))) as c:
        again = fetch.fetch_all(paths, reg, today=date(2026, 10, 15), client=c)["natural-earth"]
    outcomes = {a.artifact_id: a.outcome for a in again.artifacts}
    if change == "bytes not cached":
        # Only the member whose bytes are gone is read; the other keeps its snapshot.
        assert outcomes == {"member-prj": "not-modified", "member-dbf": "same"}
    else:
        assert outcomes == {"member-prj": "same", "member-dbf": "same"}
    assert len(seen) > 1 and seen[1] != "bytes=0-0"
    assert again.state == "unchanged"
