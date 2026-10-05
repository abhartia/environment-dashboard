"""IUCN Red List 2026-1 (GBIF checklist): threatened species and their share of assessed species.

Fixtures are byte-exact slices of the real archive's members, cut by tests/fixtures/zip_member_fixture.py: the first
517 lines of taxon.txt (the first 300 accepted taxa and their synonyms), the first 300 lines of distribution.txt (the
Global rows of the same 300 taxa, in the same order), and the whole meta.xml and eml.xml. Their sidecars are checked
in test_nature_fra_2025.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from envdash.paths import Paths
from envdash.transforms.nature import iucn_red_list as iucn

DIR = Path(__file__).parent / "fixtures" / "iucn-red-list-gbif" / "checklist-2026-1"
URL = "https://hosted-datasets.gbif.org/datasets/iucn/iucn-2026-1.zip"


def _lines(name: str) -> list[bytes]:
    return (DIR / f"2ed2c5f75667.{name}").read_bytes().splitlines(keepends=True)


def test_meta_and_version():
    iucn.check_meta((DIR / "2ed2c5f75667.meta.xml").read_bytes())
    eml = (DIR / "2ed2c5f75667.eml.xml").read_bytes()
    assert iucn.version_of(URL, eml) == "2026-1"
    with pytest.raises(iucn.IucnFormatError):
        iucn.version_of(URL.replace("2026-1", "2026-2"), eml)


def test_meta_with_moved_column_is_refused():
    meta = (DIR / "2ed2c5f75667.meta.xml").read_bytes()
    moved = meta.replace(
        b'index="5" term="http://iucn.org/terms/threatStatus"', b'index="4" term="http://iucn.org/terms/threatStatus"'
    )
    assert moved != meta
    with pytest.raises(iucn.IucnFormatError, match="threatStatus"):
        iucn.check_meta(moved)


def test_tally_of_the_slice():
    t = iucn.tally(_lines("taxon.txt"), _lines("distribution.txt"))
    # The first 300 accepted taxa are all plants (species, varieties and plant subspecies).
    assert t.assessed["all"] == t.assessed["plants"] == sum(t.categories.values())
    assert t.assessed["mammals"] == t.threatened["mammals"] == 0
    threatened = sum(n for c, n in t.categories.items() if iucn.CATEGORIES[c])
    assert t.threatened["all"] == threatened
    assert set(t.other_ranks) <= {"variety", "subspecies (plantae)"}


def test_refuses_unknown_category_and_missing_global_row():
    taxa, dist = _lines("taxon.txt"), _lines("distribution.txt")
    odd = [ln.replace(b"\tLeast Concern\t", b"\tLower Risk\t", 1) for ln in dist]
    with pytest.raises(iucn.IucnFormatError, match="unknown Red List category"):
        iucn.tally(taxa, odd)
    with pytest.raises(iucn.IucnFormatError, match="no Global category"):
        iucn.tally(taxa, dist[1:])


@pytest.mark.snapshot
def test_full_archive_reproduces_iucn_totals():
    """175,909 species and 49,505 threatened: the totals the registry research reproduced from this archive."""
    from envdash import snapshots
    from envdash.transform import InputFile, validate

    p = Paths.default()
    snap = snapshots.read_manifest(p, snapshots.read_current(p)[iucn.CHECKLIST.key])
    assert snap is not None
    files = {iucn.CHECKLIST.key: InputFile(snapshots.cache_path(p, snap.sha256), snap)}
    for t in iucn.transforms(p):
        r = t.run(files)
        validate(t, r.observations)
        assert r.vintage == "2026-1"
        by = {o.dims["group"]: o.value for o in r.observations}
        if t.spec.id.endswith("threatened-count"):
            assert by["all"] == 49505 and by["mammals"] == 1372 and by["birds"] == 1256
        else:
            assert round(by["all"], 2) == 28.14
