"""Kulp & Strauss (2019): people on land below high tide and below the yearly flood level, world, CoastalDEM
(envdash/transforms/impacts/kulp_strauss.py).

Fixtures (each with its .provenance.json sidecar, cut from the snapshots of 2026-10-12):
- kulp-strauss-2019/supplementary-data-1: the header, data rows 1-26 (the 13 World rows, then the 13 SIDS rows) and
  the last 13 (Western Sahara) of Supplementary Data 1, so the reader must pick the World rows out of others;
- kulp-strauss-2019/supplementary-descriptions: the whole one-page description of the supplementary files.

The corrected article PDF (3,903,782 bytes) is not committed as a fixture. The tests that read it (Table 1, the
method sentences, a whole run of both transforms) use the snapshot cache and are marked `snapshot` (run with
`uv run pytest -m snapshot`).
"""

from __future__ import annotations

import pytest

from envdash import snapshots, textmatch
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, Transform, run_checks, validate
from envdash.transforms.impacts import kulp_strauss as ks

from support import fixture

IDS = {"coastal.kulp-strauss-2019.below-high-tide", "coastal.kulp-strauss-2019.annual-flood"}


def _csv() -> bytes:
    path, _ = fixture(ks.SOURCE, "supplementary-data-1")
    return path.read_bytes()


def _edited(raw: bytes, old: str, new: str) -> bytes:
    """The real file with one line changed, to show that a changed file is refused."""
    text = raw.decode("utf-8")
    assert text.count(old) == 1, old
    return text.replace(old, new).encode("utf-8")


def _transforms() -> dict[str, Transform]:
    return {t.spec.id: t for t in ks.transforms(Paths.default())}


def _by(obs, period: str, scenario: str, projection: str):
    (o,) = [o for o in obs if (o.period, o.dims["scenario"], o.dims["projection"]) == (period, scenario, projection)]
    return o


# --- registry and specs -------------------------------------------------------------------------------------------


def test_registry_entry_is_the_open_article_and_its_supplement():
    src = load_registry(Paths.default()).sources[ks.SOURCE]
    assert src.licence_class == "open" and src.licence.spdx == "CC-BY-4.0" and src.obligations.mirror_raw
    assert src.evidence.terms_check == "pdf" and str(src.evidence.terms_url) == ks.ARTICLE_URL
    assert src.evidence.licence_quote.startswith("Open Access This article is licensed under a Creative Commons")
    assert [(a.id, a.format) for a in src.artifacts] == [
        ("supplementary-data-1", "csv"),
        ("supplementary-descriptions", "pdf"),
        ("article-pdf", "pdf"),
    ]
    assert str(src.artifacts[2].url) == ks.ARTICLE_URL
    assert src.citation.DOI == "10.1038/s41467-019-12808-z"


def test_specs():
    ts = _transforms()
    assert set(ts) == IDS
    for t in ts.values():
        s = t.spec
        assert s.kind == "series" and s.geo_coverage == "global-only" and s.headline_entity == "WLD"
        assert s.unit.code == "million-people" and s.display.decimals == 0
        assert s.headline_dims == (("scenario", "present"), ("projection", "none"))
        assert [d.id for d in s.dimensions] == ["scenario", "projection"]
        assert [v.id for v in s.dimensions[0].values] == ["present", "rcp26", "rcp45", "rcp85"]
        assert [v.id for v in s.dimensions[1].values] == ["none", "k14", "k17"]
        assert [i.key for i in t.inputs] == [
            "kulp-strauss-2019/supplementary-data-1",
            "kulp-strauss-2019/supplementary-descriptions",
            "kulp-strauss-2019/article-pdf",
        ]
        # The caveats the evidence says every use must carry.
        for words in ("2010", "bathtub", "exposure, not flooding", "Sixth Assessment Report", "projected"):
            assert words in s.description, words
        assert "sea walls" in s.scope.basis and "Netherlands" in s.scope.basis
        assert all(c.quote and c.url == ks.ARTICLE_URL and c.vintage == ks.VINTAGE for c in t.checks)


def test_each_check_quotes_a_declared_sentence_of_the_corrected_article():
    quotes = {s.text for s in ks.ARTICLE_STATEMENTS}
    for t in _transforms().values():
        for c in t.checks:
            assert c.quote in quotes and c.stated in c.quote
    # The superseded numbers of the Author Correction are never quoted.
    for c in (c for t in _transforms().values() for c in t.checks):
        assert "500 (390" not in c.quote and "95 million" not in c.quote


# --- Supplementary Data 1 (fixture) -------------------------------------------------------------------------------


def test_reads_the_world_rows_only():
    rows = ks.read_world(_csv())
    assert [r.sea_level.label for r in rows] == [s.label for s in ks.SEA_LEVELS]
    assert rows[0].cells == {"Perm": ks.Cell(None, "110", None), "RL1": ks.Cell(None, "250", None)}
    k17_85_2100 = ks.cell(rows, ks.RL1, "k17", "rcp85", "2100")
    assert (k17_85_2100.p5, k17_85_2100.p50, k17_85_2100.p95) == ("380", "480", "630")


def test_observations_as_printed():
    rows = ks.read_world(_csv())
    ts = _transforms()
    perm = ks.observations(rows, ks.PERM)
    validate(ts[ks.PERM.indicator], perm)
    present = _by(perm, "2010", "present", "none")
    assert (present.value, present.lower, present.upper, present.interval, present.status) == (
        110.0,
        None,
        None,
        None,
        "final",
    )
    low = _by(perm, "2100", "rcp26", "k14")
    assert (low.value, low.lower, low.upper, low.interval, low.status) == (190.0, 150.0, 250.0, "90ci", "projection")
    flood = ks.observations(rows, ks.RL1)
    validate(ts[ks.RL1.indicator], flood)
    assert _by(flood, "2010", "present", "none").value == 250.0
    high = _by(flood, "2100", "rcp85", "k17")
    assert (high.value, high.lower, high.upper) == (480.0, 380.0, 630.0)
    assert len(perm) == len(flood) == 13
    assert {o.status for o in perm if o.period != "2010"} == {"projection"}


def test_publisher_checks_pass_on_the_file():
    rows = ks.read_world(_csv())
    for e in ks.EXPOSURES:
        t = _transforms()[e.indicator]
        outcomes = run_checks(t, {ks.SOURCE: ks.VINTAGE}, ks.observations(rows, e))
        assert outcomes and all(o.status == "pass" for o in outcomes), outcomes


def test_the_abstract_needs_both_projection_sets():
    raw = _csv()
    ks.verify_abstract(ks.read_world(raw))
    # The lead range is K14's: were it K17's, the check would say so.
    k14 = "World,6800,K14_rcp26_2100,150,190,250,"
    with pytest.raises(ks.KulpStraussFormatError, match="not K14 alone"):
        ks.verify_abstract(ks.read_world(_edited(raw, k14, "World,6800,K14_rcp26_2100,140,190,280,")))
    # The 'up to 630 M' is K17's 95th percentile under RCP8.5.
    k17 = "World,6800,K17_rcp85_2100,220,340,520,380,480,630,"
    with pytest.raises(ks.KulpStraussFormatError, match="up to 630 M"):
        ks.verify_abstract(ks.read_world(_edited(raw, k17, "World,6800,K17_rcp85_2100,220,340,520,380,480,640,")))


def test_a_changed_file_is_refused():
    raw = _csv()
    with pytest.raises(ks.KulpStraussFormatError, match="column headings"):
        ks.read_world(_edited(raw, "Place,Total,SeaLevel,", "Place,Population,SeaLevel,"))
    with pytest.raises(ks.KulpStraussFormatError, match="World sea levels"):
        ks.read_world(_edited(raw, "World,6800,K17_rcp45_2050,", "World,6800,K17_rcp45_2060,"))
    with pytest.raises(ks.KulpStraussFormatError, match="expected '--'"):
        ks.read_world(_edited(raw, "World,6800,Present day,--,110 ,--,", "World,6800,Present day,90,110 ,130,"))
    with pytest.raises(ks.KulpStraussFormatError, match="out of order"):
        ks.read_world(_edited(raw, "World,6800,K14_rcp26_2050,130,150,160,", "World,6800,K14_rcp26_2050,160,150,130,"))
    with pytest.raises(ks.KulpStraussFormatError, match="Total"):
        ks.read_world(_edited(raw, "World,6800,K14_rcp45_2100,", "World,7000,K14_rcp45_2100,"))


# --- the description of the supplementary files (fixture) ---------------------------------------------------------


def test_file_description_states_units_exposures_and_percentiles():
    path, _ = fixture(ks.SOURCE, "supplementary-descriptions")
    pages = textmatch.pdf_pages_text(path.read_bytes())
    ks.verify_statements(pages, ks.DESCRIPTION_STATEMENTS, "file description")
    with pytest.raises(ks.KulpStraussFormatError, match="not on page 1 of the file description"):
        edited = [pages[0].replace("(millions)", "(thousands)")]
        ks.verify_statements(edited, ks.DESCRIPTION_STATEMENTS, "file description")


# --- the corrected article and whole runs (snapshot cache) --------------------------------------------------------


def _files() -> dict[str, InputFile]:
    p = Paths.default()
    cur = snapshots.read_current(p)
    out = {}
    for i in (ks.CSV, ks.DESCRIPTIONS, ks.ARTICLE):
        snap = snapshots.read_manifest(p, cur[i.key])
        assert snap is not None
        out[i.key] = InputFile(snapshots.cache_path(p, snap.sha256), snap)
    return out


def _article_pages() -> list[str]:
    return textmatch.pdf_pages_text(_files()[ks.ARTICLE.key].path.read_bytes())


@pytest.mark.snapshot
def test_builds_from_the_snapshots():
    files = _files()
    got = {}
    for t in ks.transforms(Paths.default()):
        r = t.run({i.key: files[i.key] for i in t.inputs})
        validate(t, r.observations)
        outcomes = run_checks(t, {ks.SOURCE: r.vintage}, r.observations)
        assert len(outcomes) == len(t.checks) and all(o.status == "pass" for o in outcomes), outcomes
        got[t.spec.id] = {(o.period, o.dims["scenario"], o.dims["projection"]): o.value for o in r.observations}
    perm, flood = got[ks.PERM.indicator], got[ks.RL1.indicator]
    assert perm[("2010", "present", "none")] == 110.0 and flood[("2010", "present", "none")] == 250.0
    assert perm[("2100", "rcp45", "k14")] == 200.0 and perm[("2100", "rcp85", "k17")] == 340.0
    assert flood[("2050", "rcp85", "k17")] == 300.0 and flood[("2100", "rcp85", "k17")] == 480.0


@pytest.mark.snapshot
def test_table_1_of_the_corrected_article_matches_the_file():
    page = _article_pages()[ks.TABLE_PAGE - 1]
    rows = ks.read_world(_files()[ks.CSV.key].path.read_bytes())
    assert ks.verify_table_1(page, rows) == 24
    assert ks.read_table_1(page)[("k14", "rcp26", "Perm", "2100")] == ("190", "150", "250")
    # The cell the Author Correction replaced: the superseded print stops the build.
    assert "480 (380 –630)" in page
    with pytest.raises(ks.KulpStraussFormatError, match="disagree"):
        ks.verify_table_1(page.replace("480 (380 –630)", "500 (390 –640)"), rows)
    with pytest.raises(ks.KulpStraussFormatError, match="eight"):
        ks.verify_table_1(page.replace("480 (380 –630)", "480"), rows)


@pytest.mark.snapshot
def test_the_article_must_be_the_corrected_one_and_state_the_method():
    pages = _article_pages()
    ks.verify_statements(pages, ks.ARTICLE_STATEMENTS, "article")
    uncorrected = [pages[0].replace("Corrected: Author correction", ""), *pages[1:]]
    with pytest.raises(ks.KulpStraussFormatError, match="Page 1"):
        ks.verify_statements(uncorrected, ks.ARTICLE_STATEMENTS, "article")
    # "Coastal defenses are not con-\nsidered": the scope's "defences are not counted" rests on this sentence.
    assert "Coastal defenses are not con-" in pages[1]
    defended = [pages[0], pages[1].replace("Coastal defenses are not con-", "Coastal defenses are con-"), *pages[2:]]
    with pytest.raises(ks.KulpStraussFormatError, match="Coastal defenses are not considered"):
        ks.verify_statements(defended, ks.ARTICLE_STATEMENTS, "article")
