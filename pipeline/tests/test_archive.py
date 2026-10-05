from __future__ import annotations

import pytest

from envdash import archive
from envdash.registry import load_registry

from support import load_fixture_snapshot


def test_bucket_decision(tmp_paths):
    reg = load_registry(tmp_paths)
    noaa, hadcrut, ipcc = (reg.sources[s] for s in ("noaa-gml-trends", "hadcrut5", "ipcc-ar6-wg3-spm"))
    assert archive.bucket_for(noaa) == archive.PUBLIC_BUCKET
    assert archive.bucket_for(hadcrut) == archive.PUBLIC_BUCKET
    assert archive.bucket_for(ipcc) == archive.PRIVATE_BUCKET
    # An open source whose terms forbid a raw mirror (AVISO-style) stays private.
    no_mirror = noaa.model_copy(update={"obligations": noaa.obligations.model_copy(update={"mirror_raw": False})})
    assert archive.bucket_for(no_mirror) == archive.PRIVATE_BUCKET
    # Non-commercial terms that allow mirroring go public; no-derivatives never does (and cannot set mirror_raw).
    nc = noaa.model_copy(update={"licence_class": "noncommercial"})
    assert archive.bucket_for(nc) == archive.PUBLIC_BUCKET
    nd = noaa.model_copy(update={"licence_class": "no-derivatives"})
    assert archive.bucket_for(nd) == archive.PRIVATE_BUCKET


def test_key_is_raw_sha_zst():
    sha = "dcf0198658c87ebb5e3b2ce807fe3a52e1d5f000aa0479fb1bf334afb7adde4d"
    assert archive.r2_key(sha) == f"raw/{sha}.zst"


def test_r2_missing_env_names_the_variables(monkeypatch):
    for n in archive.R2_ENV:
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "set-for-test")
    with pytest.raises(archive.ArchiveConfigError) as e:
        archive.r2_client()
    assert "R2_ACCESS_KEY_ID" in str(e.value) and "R2_SECRET_ACCESS_KEY" in str(e.value)
    assert "CLOUDFLARE_ACCOUNT_ID" not in str(e.value)


def test_compress_round_trip(tmp_paths):
    import zstandard

    from envdash import snapshots

    sha = load_fixture_snapshot(tmp_paths, "noaa-gml-trends", "co2-mm-mlo")
    raw = snapshots.cache_path(tmp_paths, sha).read_bytes()
    assert zstandard.ZstdDecompressor().decompress(archive.compress(raw)) == raw


def test_wayback_without_keys_is_skipped_never_raises(monkeypatch):
    import httpx

    for n in archive.IA_ENV:
        monkeypatch.delenv(n, raising=False)
    with httpx.Client() as c:
        cap = archive.spn2_capture(c, "https://gml.noaa.gov/ccgg/trends/")
    assert cap.status == "skipped" and "IA_ACCESS" in cap.reason


def test_wayback_targets_data_files_only_for_mirror_raw(tmp_paths):
    load_fixture_snapshot(tmp_paths, "hadcrut5", "global-annual")
    reg = load_registry(tmp_paths)
    targets = archive.wayback_targets(tmp_paths, reg.sources)
    kinds = {(t.kind, t.url) for t in targets}
    hadcrut_annual = reg.sources["hadcrut5"].artifacts[0].url
    assert ("data", str(hadcrut_annual)) in kinds
    # NOAA's terms URL is its data file: listed once, as terms.
    assert ("terms", "https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_mlo.csv") in kinds
    assert ("terms", "https://www.ipcc.ch/copyright/") in kinds
    assert ("landing", "https://www.metoffice.gov.uk/hadobs/hadcrut5/") in kinds
    assert all(t.kind != "data" or "ipcc.ch" not in t.url for t in targets)
