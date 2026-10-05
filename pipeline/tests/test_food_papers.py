"""Values quoted from documents: Scarborough et al. (2023) Table 3, UNEP Food Waste Index Report 2024 Table 23, and
the Poore & Nemecek (2018) series as published by OWID.

No fixtures: the article PDF (1.4 MB) cannot be sliced into a valid PDF, the UNEP report is noncommercial and may not
be re-hosted (mirror_raw false), and Poore & Nemecek is display-only. Tests that read those files are marked
snapshot and read the real cache; the others check the declared rows themselves.
"""

from __future__ import annotations

import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.transform import InputFile, validate
from envdash.transforms.food import poore_nemecek_2018 as pn
from envdash.transforms.food import scarborough_2023 as sc
from envdash.transforms.food import unep_food_waste as fw


def _files(inputs) -> dict[str, InputFile]:
    p = Paths.default()
    cur = snapshots.read_current(p)
    out = {}
    for i in inputs:
        snap = snapshots.read_manifest(p, cur[i.key])
        assert snap is not None
        out[i.key] = InputFile(snapshots.cache_path(p, snap.sha256), snap)
    return out


# --- Scarborough et al. (2023) -------------------------------------------------------------------------------------


def test_scarborough_reads_the_gwp100_group_of_each_row():
    assert sc.gwp100(sc.TABLE_ROWS[0]) == ("2.47", "2.09", "3.36")
    assert sc.gwp100(sc.TABLE_ROWS[-1]) == ("10.24", "7.04", "15.95")
    obs = sc.observations()
    assert [o.dims["diet"] for o in obs] == [r.group for r in sc.TABLE_ROWS]
    assert all(o.entity == "GBR" and o.period == "1993/1999" and o.interval == "95ci" for o in obs)


def test_scarborough_refuses_a_malformed_row():
    bad = sc.Row("vegans", "Vegans", "Vegans 2.47 (2.09, 3.36) 2.42 (2.05, 3.29)")
    with pytest.raises(sc.ScarboroughTextError, match="three"):
        sc.gwp100(bad)


@pytest.mark.snapshot
def test_scarborough_rows_are_on_the_page():
    from envdash import textmatch

    files = _files([sc.ARTICLE])
    pages = textmatch.pdf_pages_text(files[sc.ARTICLE.key].path.read_bytes())
    sc.verify(pages)
    changed = [p.replace("10.24 (7.04, 15.95)", "10.42 (7.04, 15.95)") for p in pages]
    with pytest.raises(sc.ScarboroughTextError):
        sc.verify(changed)
    t = sc.transforms(Paths.default())[0]
    r = t.run(files)
    validate(t, r.observations)
    assert r.published_value is not None and "10.24" in r.published_value.quote


# --- UNEP Food Waste Index Report 2024 -----------------------------------------------------------------------------


def test_unep_rows_and_numbers():
    printed = ["Household 79 631", "Food service 36 290", "Retail 17 131", "Total 132 1 052"]
    assert [r.printed for r in fw.ROWS] == printed
    assert fw._number("1 052") == 1052.0
    total = {o.dims["sector"]: o.value for o in fw._observations("total")}
    per_capita = {o.dims["sector"]: o.value for o in fw._observations("per-capita")}
    assert total == {"household": 631.0, "food-service": 290.0, "retail": 131.0, "all-three-sectors": 1052.0}
    assert per_capita["all-three-sectors"] == 132.0
    # The rows add up as printed (rounded figures): 631 + 290 + 131 = 1,052 and 79 + 36 + 17 = 132.
    assert sum(v for k, v in total.items() if k != "all-three-sectors") == total["all-three-sectors"]
    assert sum(v for k, v in per_capita.items() if k != "all-three-sectors") == per_capita["all-three-sectors"]


@pytest.mark.snapshot
def test_unep_table_is_on_page_64():
    files = _files([fw.REPORT])
    page = fw.page_text(files[fw.REPORT.key].path)
    fw.verify(page)
    with pytest.raises(fw.UnepTextError):
        fw.verify(page.replace("Retail 17 131", "Retail 17 113"))
    for t in fw.transforms(Paths.default()):
        r = t.run(files)
        validate(t, r.observations)


# --- Poore & Nemecek (2018) ----------------------------------------------------------------------------------------


def test_poore_food_ids_are_unique_and_readable():
    ids = [pn.food_id(n) for n in pn.FOODS]
    assert len(ids) == len(set(ids))
    assert pn.food_id("Beef (beef herd)") == "beef-beef-herd"
    assert pn.food_id("Berries & Grapes") == "berries-grapes"


@pytest.mark.snapshot
def test_poore_series_build_from_the_snapshots():
    p = Paths.default()
    for t in pn.transforms(p):
        files = _files(t.inputs)
        r = t.run(files)
        validate(t, r.observations)
        by = {o.dims["food"]: o.value for o in r.observations}
        if t.spec.id.endswith("ghg-per-kg"):
            assert by["beef-beef-herd"] == 99.48 and by["apples"] == 0.43 and len(by) == 38
        else:
            assert by["beef-beef-herd"] == 49.889668 and len(by) == 32
    raw = files[pn.PER_PROTEIN.key].path.read_bytes()
    with pytest.raises(pn.PooreFormatError, match="year"):
        pn.read(raw.replace(b"Apples,2010", b"Apples,2011"), pn.COLUMNS[pn.PER_PROTEIN.key])
    with pytest.raises(pn.PooreFormatError, match="FOODS"):
        pn.read(raw.replace(b"Apples,2010", b"Pears,2010"), pn.COLUMNS[pn.PER_PROTEIN.key])


def test_poore_is_display_only():
    from envdash.registry import load_registry

    assert load_registry(Paths.default()).sources[pn.SOURCE].licence_class == "display-only"
