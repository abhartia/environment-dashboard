"""Grant et al. (2025): the world share of the 1960 and 2020 birth cohorts projected to face unprecedented lifetime
exposure to heatwaves, read from the article's text (envdash/transforms/impacts/grant_2025.py).

The fixture is the whole article XML from Europe PMC (a JATS XML cannot be cut and still be read), so every sentence
the transform relies on is checked against the real article here.
"""

from __future__ import annotations

import shutil
from dataclasses import replace
from datetime import date

import pytest

from envdash import snapshots
from envdash.export import build_and_export
from envdash.greenpremium import PrintedValueError, check_sentences, jats_root
from envdash.models import Snapshot
from envdash.paths import REPO_ROOT, Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, discover, validate
from envdash.transforms.impacts import grant_2025 as g
from envdash.validate import validate_all

from support import exported, fixture


@pytest.fixture(scope="module")
def raw() -> bytes:
    path, meta = fixture(g.SOURCE, "article-xml")
    assert meta["fixture_sha256"] == meta["full_sha256"]  # the whole file
    return path.read_bytes()


def _by(obs, **dims):
    (o,) = [o for o in obs if o.dims == dims]
    return o


def test_values_are_the_numbers_the_text_prints(raw):
    obs = g.observations(raw)
    got = {(o.dims["cohort"], o.dims["pathway"]): o.value for o in obs}
    assert got == {
        ("1960", "1-5c"): 16.0,
        ("1960", "2-5c"): 16.0,
        ("1960", "3-5c"): 16.0,
        ("2020", "1-5c"): 52.0,
        ("2020", "2-5c"): None,
        ("2020", "3-5c"): 92.0,
    }
    assert {(o.entity, o.period, o.status) for o in obs} == {("WLD", "2025", "projection")}
    assert "regardless of the scenario" in _by(obs, cohort="1960", pathway="2-5c").note
    high = _by(obs, cohort="2020", pathway="3-5c").note
    assert g.BORN_2020_HIGH.sentence in high and g.ABSTRACT_HIGH.sentence in high  # both quoted
    missing = _by(obs, cohort="2020", pathway="2-5c")
    assert missing.note is None and "state no world share" in missing.missing_reason


def test_every_sentence_is_in_the_article(raw):
    root = jats_root(raw)
    check_sentences(root, [(s.locator, s.sentence) for s in g.RESULTS] + g.SENTENCES)
    g.check_abstract(root, list(g.ABSTRACT))
    # The abstract sentences are not in the body, and a body sentence is not in the abstract.
    with pytest.raises(PrintedValueError, match="not found in the article's text"):
        check_sentences(root, [(g.ABSTRACT_LOW.locator, g.ABSTRACT_LOW.sentence)])
    with pytest.raises(PrintedValueError, match="not found in the abstract"):
        g.check_abstract(root, [g.BORN_2020_HIGH])


def test_a_changed_number_is_refused(raw):
    root = jats_root(raw)
    for s in (*g.RESULTS, *g.ABSTRACT):
        wrong = s.sentence.replace(f"{s.printed}%", f"{int(s.printed) + 1}%")
        assert wrong != s.sentence
        with pytest.raises(PrintedValueError):
            if s in g.RESULTS:
                check_sentences(root, [(s.locator, wrong)])
            else:
                g.check_abstract(root, [replace(s, sentence=wrong)])


def test_a_number_must_stand_whole_in_its_words():
    assert g.BORN_2020_HIGH.value() == 92
    with pytest.raises(PrintedValueError, match="is not printed"):
        replace(g.BORN_2020_HIGH, printed="2").value()
    with pytest.raises(PrintedValueError, match="is not printed"):
        replace(g.BORN_1960, printed="1").value()
    with pytest.raises(PrintedValueError, match="not part of the sentence"):
        replace(g.BORN_2020_LOW, words="an average of 53% for the 2020 birth cohort", printed="53").value()


def test_the_abstract_must_agree_with_the_results(raw, monkeypatch):
    monkeypatch.setitem(g.STATED, ("2020", "3-5c"), (g.BORN_2020_HIGH, g.ABSTRACT_LOW))
    with pytest.raises(PrintedValueError, match="the abstract prints 52 where the Results text prints 92"):
        g.observations(raw)


def test_every_cohort_and_pathway_is_stated_or_says_why(raw, monkeypatch):
    monkeypatch.delitem(g.NOT_STATED, ("2020", "2-5c"))
    with pytest.raises(ValueError, match="either stated or not stated"):
        g.observations(raw)


def test_a_sentence_that_is_not_checked_is_refused(raw, monkeypatch):
    unchecked = replace(g.BORN_2020_HIGH, sentence=g.BORN_2020_HIGH.sentence + " ")
    monkeypatch.setitem(g.STATED, ("2020", "3-5c"), (unchecked, g.ABSTRACT_HIGH))
    with pytest.raises(ValueError, match="not checked"):
        g.observations(raw)


def test_the_article_and_its_licence_are_checked(raw):
    with pytest.raises(ValueError, match="not the article"):
        g.observations(raw.replace(g.DOI.encode(), b"10.1038/s41586-025-00000-0"))
    with pytest.raises(ValueError, match="license"):
        g.observations(raw.replace(b"Attribution 4.0 International License", b"Attribution-NonCommercial 4.0"))


def test_transform_runs_and_validates_on_the_fixture(raw):
    (t,) = g.transforms(Paths.default())
    path, meta = fixture(g.SOURCE, "article-xml")
    snap = Snapshot(
        sha256=meta["full_sha256"],
        bytes=meta["full_bytes"],
        source_id=g.SOURCE,
        artifact_id="article-xml",
        url=meta["url"],
        date_accessed=meta["date_accessed"],
        acquisition="automatic",
    )
    result = t.run({g.ARTICLE.key: InputFile(path, snap)})
    validate(t, result.observations)
    assert result.published_value is not None and result.published_value.document == g.SOURCE
    assert t.spec.kind == "published-value" and t.spec.geo_coverage == "global-only"
    assert {d.id: [v.id for v in d.values] for d in t.spec.dimensions} == {
        "cohort": ["1960", "2020"],
        "pathway": ["1-5c", "2-5c", "3-5c"],
    }


def test_build_exports_the_open_indicator_with_its_checks(tmp_paths):
    shutil.copy(REPO_ROOT / "pipeline" / "sources" / f"{g.SOURCE}.yaml", tmp_paths.sources / f"{g.SOURCE}.yaml")
    path, meta = fixture(g.SOURCE, "article-xml")
    snap, _ = snapshots.record(
        tmp_paths,
        data=path.read_bytes(),
        source_id=g.SOURCE,
        artifact_id="article-xml",
        url=meta["url"],
        acquisition="automatic",
        today=date.fromisoformat(meta["date_accessed"]),
        note="test fixture: the whole article XML",
    )
    snapshots.set_current(tmp_paths, {snapshots.key(g.SOURCE, "article-xml"): snap.sha256})
    reg = load_registry(tmp_paths)
    ts = [t for t in discover(tmp_paths) if t.spec.id == g.INDICATOR]
    out = build_and_export(tmp_paths, reg, ts).outcomes[0]
    assert out.state == "built", out.reason
    assert [c.status for c in out.checks] == ["pass", "pass"]
    ind = exported(tmp_paths.public_indicators / f"{g.INDICATOR}.json")
    assert ind["licence_class"] == "open" and ind["kind"] == "published-value"
    assert ind["latest"] == {
        "entity": "WLD",
        "period": "2025",
        "age_bp": None,
        "value": 52.0,
        "status": "projection",
        "dims": {"cohort": "2020", "pathway": "1-5c"},
    }
    assert "99.99th percentile" in ind["scope"]["basis"] and "not a count of deaths" in ind["description"]
    assert validate_all(tmp_paths, reg) == []
