"""Ivanova et al. (2020) consumption options, on the real article PDF (the whole file is the fixture: a PDF cannot be
cut by lines and still be read)."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from envdash import snapshots, textmatch
from envdash.export import build_and_export
from envdash.paths import REPO_ROOT, Paths
from envdash.registry import load_registry
from envdash.transform import discover
from envdash.transforms.action import ivanova_2020 as iv
from envdash.validate import validate_all

from support import exported

FIXTURES = Path(__file__).parent / "fixtures"
SOURCE, ARTIFACT = "ivanova-2020", "article-pdf"


def _fixture() -> tuple[Path, dict]:
    # Copied from support.fixture, which this file must not change.
    for side in sorted(FIXTURES.glob(f"{SOURCE}/*.provenance.json")):
        meta = json.loads(side.read_text())
        if meta["artifact_id"] == ARTIFACT:
            return side.with_name(side.name.removesuffix(".provenance.json")), meta
    raise LookupError(f"no fixture for {SOURCE}/{ARTIFACT}")


@pytest.fixture(scope="module")
def pages() -> list[str]:
    path, _ = _fixture()
    return textmatch.pdf_pages_text(path.read_bytes())


def _by(obs, option, statistic):
    (o,) = [o for o in obs if o.dims["option"] == option and o.dims["statistic"] == statistic]
    return o


def _with(statement_index: int, **changes) -> tuple[iv.Statement, ...]:
    out = list(iv.STATEMENTS)
    out[statement_index] = replace(out[statement_index], **changes)
    return tuple(out)


def _index(option: str) -> int:
    return next(
        i
        for i, s in enumerate(iv.STATEMENTS)
        if not s.locator.startswith("Abstract") and any(v.option == option for v in s.values)
    )


def test_every_statement_is_on_its_page(pages):
    assert len(pages) == 20
    iv.verify(pages)


def test_values_are_the_printed_numbers():
    obs = iv.observations()
    assert len(obs) == 39 and len({o.dims["option"] for o in obs}) == 28
    car_free = _by(obs, "living-car-free", "median")
    assert (car_free.value, car_free.lower, car_free.upper, car_free.interval) == (2.0, 0.6, 3.6, "range")
    bev = _by(obs, "shift-to-bev", "mean")
    assert (bev.value, bev.lower, bev.upper) == (2.0, -1.9, 5.4)
    assert _by(obs, "fuel-cell-vehicles", "mean").value == 0.0
    assert _by(obs, "fuel-cell-vehicles", "mean").lower == -3.4
    assert _by(obs, "food-waste-management", "mean").value == 0.03
    assert _by(obs, "energy-and-material-efficiency", "mean").upper == 1.46
    assert _by(obs, "renewable-electricity", "median").value == 1.6
    assert _by(obs, "refurbishment-and-renovation", "median").value == 0.9
    assert _by(obs, "regional-and-local-food", "mean").value == 0.4
    assert _by(obs, "seasonal-and-fresh-food", "mean").value == 0.2
    # A stated maximum alone ("up to 1.0") is not a range.
    co = _by(obs, "less-living-space-and-co-housing", "mean")
    assert co.value == 0.3 and co.lower is None and "up to 1.0" in co.note
    # Joint statements are not split between options.
    assert not {"car-pooling-and-car-sharing", "fuel-efficient-driving", "food-sufficiency"} & {
        o.dims["option"] for o in obs
    }


def test_two_different_statements_of_one_value_publish_null():
    obs = iv.observations()
    vegan = _by(obs, "vegan-diet", "median")
    assert vegan.value is None
    assert "0.8 in Abstract, p. 1" in vegan.missing_reason and "0.9 in Section 3.2 (Food), p. 8" in vegan.missing_reason
    # Repeated values that agree are published once, with both sentences.
    mean = _by(obs, "vegan-diet", "mean")
    assert mean.value == 0.9 and mean.note.count('"') == 4


def test_a_lost_minus_sign_is_refused(pages):
    i = _index("shift-to-bev")
    s = iv.STATEMENTS[i]
    text = s.parts[0][1].replace(iv.MINUS, "")
    # textmatch alone ignores the sign; this transform must not.
    assert textmatch.contains(pages[5], text)
    with pytest.raises(iv.IvanovaTextError, match="not found on PDF page 6"):
        iv.verify(pages, _with(i, parts=((6, text),)))


def test_a_changed_number_is_refused(pages):
    i = _index("one-less-flight-long-return")
    s = iv.STATEMENTS[i]
    text = s.parts[0][1].replace("(mean of 1.9)", "(mean of 1.8)")
    with pytest.raises(iv.IvanovaTextError, match="not found"):
        iv.verify(pages, _with(i, parts=((6, text),)))


def test_a_value_must_be_in_its_words(pages):
    i = _index("telecommuting")
    s = iv.STATEMENTS[i]
    wrong = replace(s.values[0], printed="0.1")  # 0.1 is in the sentence, but not in "(mean of 0.4)"
    with pytest.raises(iv.IvanovaTextError, match="is not stated by"):
        iv.verify(pages, _with(i, values=(wrong,)))


def test_a_sentence_on_another_page_is_refused(pages):
    i = _index("passive-house")
    s = iv.STATEMENTS[i]
    with pytest.raises(iv.IvanovaTextError, match="not found on PDF page 11"):
        iv.verify(pages, _with(i, parts=((11, s.parts[0][1]),)))


def _tmp_paths(tmp_path: Path) -> Paths:
    # As support.make_tmp_paths, with this source's registry entry.
    (tmp_path / "literature").mkdir()
    (tmp_path / "sources").mkdir()
    shutil.copy(REPO_ROOT / "pipeline" / "sources" / f"{SOURCE}.yaml", tmp_path / "sources" / f"{SOURCE}.yaml")
    return Paths.default().with_(
        sources=tmp_path / "sources",
        literature=tmp_path / "literature",
        manifests=tmp_path / "manifests",
        cache=tmp_path / "cache",
        data=tmp_path / "data",
        private=tmp_path / "data-private",
        schema=tmp_path / "schema",
    )


def test_build_exports_an_open_published_value(tmp_path):
    paths = _tmp_paths(tmp_path)
    path, meta = _fixture()
    snap, _ = snapshots.record(
        paths,
        data=path.read_bytes(),
        source_id=SOURCE,
        artifact_id=ARTIFACT,
        url=meta["url"],
        acquisition="manual",
        today=date.fromisoformat(meta["date_accessed"]),
        note="test fixture: the whole article PDF",
    )
    snapshots.set_current(paths, {snapshots.key(SOURCE, ARTIFACT): snap.sha256})
    reg = load_registry(paths)
    ts = [t for t in discover(paths) if t.spec.id == iv.INDICATOR]
    report = build_and_export(paths, reg, ts)
    assert [o.state for o in report.outcomes] == ["built"], report.outcomes[0].reason
    ind = exported(paths.public_indicators / f"{iv.INDICATOR}.json")
    assert ind["kind"] == "published-value" and ind["licence_class"] == "open"
    assert ind["latest"]["value"] == 2.0 and ind["latest"]["dims"]["option"] == "living-car-free"
    assert ind["published_value"]["quote"].startswith("Living car-free has the highest median")
    assert ind["origins"][0]["sha256"] == meta["full_sha256"] == snap.sha256
    assert ind["attribution"].startswith("Ivanova, D., Barrett, J.")
    assert validate_all(paths, reg) == []
