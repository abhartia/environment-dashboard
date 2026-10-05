"""Published values quoted from web pages for the impacts family: NOAA Coral Reef Watch's fourth global bleaching
event share, and Carbon Brief's own totals for its attribution map (pipeline/literature/*.yaml).

The CRW page is public domain, so its value is built from the committed fixture (lines 290-345 of the 2026-10-04
snapshot). Carbon Brief is CC BY-NC-ND 4.0 (class no-derivatives, mirror_raw false): no fixture may be committed, so
the tests that read its page use the full snapshot from the cache and are marked `snapshot`.
"""

from __future__ import annotations

import re
import shutil

import pytest

from envdash import snapshots, textmatch
from envdash.export import build_and_export
from envdash.paths import REPO_ROOT, Paths
from envdash.registry import load_registry
from envdash.transform import discover

from support import load_fixture_snapshot

LIT = REPO_ROOT / "pipeline" / "literature"
CRW = "noaa-crw-fourth-event-reef-area"
CB = ("carbon-brief-attribution-extremes-studied", "carbon-brief-attribution-share-more-likely-or-severe")


def _setup(tmp_paths, source_id: str, *entries: str):
    shutil.copy(REPO_ROOT / "pipeline" / "sources" / f"{source_id}.yaml", tmp_paths.sources / f"{source_id}.yaml")
    for e in entries:
        shutil.copy(LIT / f"{e}.yaml", tmp_paths.literature / f"{e}.yaml")
    return tmp_paths


def test_entries_load_and_state_the_number_they_publish():
    reg = load_registry(Paths.default())
    for lid in (CRW, *CB):
        assert lid not in reg.literature_errors, reg.literature_errors.get(lid)
        lit = reg.literature[lid]
        (obs,) = lit.observations
        printed = re.search(r"\d[\d,]*(\.\d+)?", lit.value_text)
        assert printed and float(printed.group().replace(",", "")) == obs.value
        assert lit.pdf_page is None
        art = next(a for a in reg.sources[lit.source_id].artifacts if a.id == lit.artifact_id)
        assert art.format == "html"
    cb = reg.sources["carbon-brief-attribution"]
    assert cb.licence_class == "no-derivatives" and not cb.obligations.mirror_raw


def test_crw_value_is_built_from_the_real_page(tmp_paths):
    paths = _setup(tmp_paths, "noaa-crw", CRW)
    load_fixture_snapshot(paths, "noaa-crw", "global-bleaching-status")
    reg = load_registry(paths)
    ts = [t for t in discover(paths) if t.spec.id == "coral.noaa-crw.fourth-event-reef-area"]
    out = build_and_export(paths, reg, ts).outcomes[0]
    assert out.state == "built", out.reason
    ind = out.indicator
    assert ind.kind == "published-value" and ind.licence_class == "open"
    assert ind.latest.value == 84.4 and ind.latest.period == "2023-01-01/2025-09-30"
    assert "~84.4%" in ind.published_value.quote
    assert (paths.public_indicators / f"{ind.id}.json").exists()


@pytest.mark.snapshot
def test_carbon_brief_totals_are_on_the_cached_page_and_stay_private(tmp_paths):
    real = Paths.default()
    key = "carbon-brief-attribution/article-page"
    sha = snapshots.read_current(real)[key]
    snap = snapshots.read_manifest(real, sha)
    raw = snapshots.cache_path(real, sha).read_bytes()
    text = textmatch.document_text(raw, snap.content_type, str(snap.url))
    assert textmatch.contains(text, "Last updated 19 March 2026")
    assert not textmatch.contains(text, "Across all cases, 78% were found to have been made more likely or severe")

    paths = _setup(tmp_paths, "carbon-brief-attribution", *CB)
    rec, _ = snapshots.record(
        paths,
        data=raw,
        source_id="carbon-brief-attribution",
        artifact_id="article-page",
        url=str(snap.url),
        acquisition="automatic",
        today=snap.date_accessed,
        content_type=snap.content_type,
    )
    snapshots.set_current(paths, {key: rec.sha256})
    reg = load_registry(paths)
    ids = {
        "attribution.carbon-brief.extremes-studied": 967.0,
        "attribution.carbon-brief.share-more-likely-or-severe": 77.0,
    }
    ts = [t for t in discover(paths) if t.spec.id in ids]
    for out in build_and_export(paths, reg, ts).outcomes:
        assert out.state == "built", out.reason
        ind = out.indicator
        assert ind.licence_class == "no-derivatives" and ind.latest.value == ids[ind.id]
        assert ind.latest.period == "2026-03-19"
        assert not (paths.public_indicators / f"{ind.id}.json").exists()
        assert not (paths.public_indicators / f"{ind.id}.csv").exists()
        assert (paths.private_indicators / f"{ind.id}.json").exists()
