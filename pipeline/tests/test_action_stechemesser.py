"""Stechemesser et al. (2024): successful policy interventions (envdash/transforms/action/stechemesser_2024.py) and the
R serialization reader it uses (envdash/transforms/action/rds.py).

Fixtures: Policy_out.RDS and EU_policies_label_df.csv, each the whole file as served by Zenodo record 12773811 (CC BY
4.0), cut with tests/fixtures/make_fixture.py.
"""

from __future__ import annotations

import gzip
import json
import math
import shutil
from datetime import date
from pathlib import Path

import pytest

from envdash import snapshots
from envdash.export import build_and_export
from envdash.paths import REPO_ROOT, Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, discover, validate
from envdash.transforms.action import rds
from envdash.transforms.action import stechemesser_2024 as st
from envdash.validate import validate_all

FIXTURES = Path(__file__).parent / "fixtures" / st.SOURCE


def _fixture(artifact: str) -> tuple[Path, dict]:
    for side in sorted(FIXTURES.glob("*.provenance.json")):
        meta = json.loads(side.read_text())
        if meta["artifact_id"] == artifact:
            return side.with_name(side.name.removesuffix(".provenance.json")), meta
    raise LookupError(artifact)


def _bytes(artifact: str) -> bytes:
    return _fixture(artifact)[0].read_bytes()


@pytest.fixture(scope="module")
def breaks() -> list[st.Break]:
    return st.with_eu(st.read_breaks(_bytes("policy-out")), st.read_eu_policies(_bytes("eu-policies-label")))


# --- the R reader --------------------------------------------------------------------------------------------------


def test_reader_reads_policy_out_to_its_last_byte():
    tbl = rds.read_rds(_bytes("policy-out"))
    assert tbl.type == rds.VECSXP and tbl.classes == ["tbl_df", "tbl", "data.frame"]
    assert tbl.strings("names") == st.POLICY_OUT_COLUMNS
    assert rds.nrow(tbl) == 8
    assert rds.column(tbl, "country_sample") == ["AC1"] * 4 + ["AC6"] * 4
    out = rds.column(tbl, "out")[0]
    assert rds.nrow(out) == 15 and rds.column(out, "country_code")[0] == "AUS"


def test_reader_refuses_a_truncated_file():
    raw = gzip.decompress(_bytes("policy-out"))
    with pytest.raises(rds.RdsError, match="truncated"):
        rds.read_rds(raw[: len(raw) // 2])


def test_reader_refuses_bytes_after_the_object():
    raw = gzip.decompress(_bytes("policy-out"))
    with pytest.raises(rds.RdsError, match="left after"):
        rds.read_rds(raw + b"\x00\x00\x00\xfe")


def test_reader_refuses_another_format():
    with pytest.raises(rds.RdsError, match="XDR"):
        rds.read_rds(b"A\n" + gzip.decompress(_bytes("policy-out"))[2:])


# --- breaks and matches --------------------------------------------------------------------------------------------


def test_69_breaks_63_matched(breaks):
    assert len(breaks) == 69
    assert sum(b.successful for b in breaks) == 63
    assert sum(1 for b in breaks if b.cas) == 59
    st.check_counts(breaks)
    unmatched = sorted((b.iso, b.sector, b.year) for b in breaks if not b.successful)
    assert unmatched == [
        ("COL", "Transport", 2002),
        ("NZL", "Industry", 2005),
        ("PER", "Buildings", 2003),
        ("PER", "Buildings", 2006),
        ("RUS", "Industry", 2004),
        ("SVK", "Buildings", 2001),
    ]


def test_eu_only_matches_are_the_ones_the_notes_name(breaks):
    eu_only = {(b.sector, b.name, b.year): b.eu for b in breaks if b.successful and not b.cas}
    assert set(eu_only) == st.EU_ONLY_IN_NOTES
    assert eu_only[("Industry", "Romania", 2009)] == (("EU-ETS", 2007), ("EU-MEPS", 2011))


def test_effect_size_is_the_authors_conversion(breaks):
    obs = st.observations(breaks)
    (o,) = [o for o in obs if o.entity == "GBR" and o.period == "2016"]
    assert o.dims == {"sector": "electricity", "economy_group": "developed"}
    assert o.value == (math.exp(-0.28200195560477304) - 1) * 100
    assert "Ban & phase out (coal plants)" in (o.note or "")
    assert all(-100 < x.value < 0 for x in obs if x.value is not None)


def test_a_missing_eu_policy_changes_the_count_and_is_refused():
    eu = st.read_eu_policies(_bytes("eu-policies-label"))
    eu[("Industry", "Romania")] = []
    breaks = st.with_eu(st.read_breaks(_bytes("policy-out")), eu)
    with pytest.raises(st.StechemesserFormatError, match="62 matched"):
        st.check_counts(breaks)


def test_a_changed_eu_header_is_refused():
    raw = _bytes("eu-policies-label").replace(b'"Module"', b'"Sector"', 1)
    with pytest.raises(st.StechemesserFormatError, match="header"):
        st.read_eu_policies(raw)


# --- build ---------------------------------------------------------------------------------------------------------


def _tmp_paths(tmp_path: Path) -> Paths:
    (tmp_path / "literature").mkdir()
    (tmp_path / "sources").mkdir()
    shutil.copy(REPO_ROOT / "pipeline" / "sources" / f"{st.SOURCE}.yaml", tmp_path / "sources")
    return Paths.default().with_(
        sources=tmp_path / "sources",
        literature=tmp_path / "literature",
        manifests=tmp_path / "manifests",
        cache=tmp_path / "cache",
        data=tmp_path / "data",
        private=tmp_path / "data-private",
        schema=tmp_path / "schema",
    )


def test_build_exports_publicly(tmp_path):
    paths = _tmp_paths(tmp_path)
    pointers = {}
    for inp in (st.POLICY_OUT, st.EU_LABELS):
        path, meta = _fixture(inp.artifact_id)
        snap, _ = snapshots.record(
            paths,
            data=path.read_bytes(),
            source_id=st.SOURCE,
            artifact_id=inp.artifact_id,
            url=meta["url"],
            acquisition="automatic",
            today=date.fromisoformat(meta["date_accessed"]),
            note="test fixture: the whole file",
        )
        pointers[snapshots.key(st.SOURCE, inp.artifact_id)] = snap.sha256
    snapshots.set_current(paths, pointers)
    reg = load_registry(paths)
    report = build_and_export(paths, reg, [t for t in discover(paths) if t.spec.id == st.INDICATOR])
    assert [o.state for o in report.outcomes] == ["built"], [o.reason for o in report.outcomes]
    assert validate_all(paths, reg) == []


@pytest.mark.snapshot
def test_the_real_snapshots_give_63_interventions():
    p = Paths.default()
    cur = snapshots.read_current(p)
    files = {}
    for inp in (st.POLICY_OUT, st.EU_LABELS):
        sha = cur[inp.key]
        files[inp.key] = InputFile(snapshots.cache_path(p, sha), snapshots.read_manifest(p, sha))
    (t,) = st.transforms(p)
    result = t.run(files)
    validate(t, result.observations)
    assert len(result.observations) == 63
