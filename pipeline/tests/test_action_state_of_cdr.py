"""The State of Carbon Dioxide Removal, 3rd Edition, chapter 7 (envdash/transforms/action/state_of_cdr.py).

The fixture is data rows 1-20 (the world mean of the bookkeeping models, 2005-2024) and 16745-17329 (every world novel
CDR row, then the 2025 country rows and the country averages) of SoCDR-Edition-3-Chapter-7.csv of 27 May 2026. The
chapter and annex PDFs are too large for fixtures, so the full run (-m snapshot) needs pipeline/.snapshots.
"""

from __future__ import annotations

import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.transform import InputFile, run_checks, validate
from envdash.transforms.action import state_of_cdr as cdr

from support import fixture


def _rows() -> list[dict[str, str]]:
    path, _ = fixture(cdr.SOURCE, cdr.CSV.artifact_id)
    return cdr.read_rows(path.read_bytes())


def test_novel_cdr_as_printed():
    obs = cdr.novel_observations(_rows())
    by = {(o.dims["method"], o.period): o.value for o in obs}
    assert by[("all", "2025")] == 2.04 and by[("all", "2023")] == 1.4 and by[("all", "2017")] == 0.43
    assert by[("biochar", "2025")] == 1.4629
    assert by[("beccs", "2025")] == 0.5105
    assert by[("daccs", "2025")] == 0.0015 and by[("daccs", "2024")] == 0.0014
    # A method appears from the first year the report records it; earlier years are not filled.
    assert min(y for m, y in by if m == "biochar") == "2021"
    assert ("biochar", "2020") not in by
    assert len(obs) == 63


def test_years_where_the_methods_do_not_add_up_to_the_total_are_named():
    obs = cdr.novel_observations(_rows())
    assert cdr.totals_disagree(obs) == ["2017", "2018", "2019", "2020", "2025"]


def test_conventional_cdr_mean_of_models():
    obs = cdr.conventional_observations(_rows())
    by = {(o.dims["model"], o.period): o.value for o in obs}
    assert by[("mean", "2005")] == 1825.49 and by[("mean", "2024")] == 2178.59
    assert {m for m, _ in by} == {"mean"}  # the fixture keeps only the mean's rows


def test_an_unknown_method_stops_the_build():
    rows = _rows()
    i = next(i for i, r in enumerate(rows) if r["Indicator"] == cdr.NOVEL_BY_METHOD)
    rows[i] = {**rows[i], "Method": "Ocean Iron Fertilisation"}
    with pytest.raises(cdr.StateOfCdrFormatError, match="Ocean Iron Fertilisation"):
        cdr.novel_observations(rows)


def _current() -> dict[str, InputFile]:
    p = Paths.default()
    cur = snapshots.read_current(p)
    out = {}
    for inp in (cdr.CSV, cdr.CHAPTER, cdr.ANNEX):
        sha = cur[inp.key]
        out[inp.key] = InputFile(snapshots.cache_path(p, sha), snapshots.read_manifest(p, sha))
    return out


@pytest.mark.snapshot
def test_full_run_checks_the_documents_and_the_published_total():
    novel, conventional = cdr.transforms(Paths.default())
    files = _current()
    result = novel.run(files)
    validate(novel, result.observations)
    (check,) = run_checks(novel, {cdr.SOURCE: cdr.VINTAGE}, result.observations)
    assert check.status == "pass"
    result = conventional.run(files)
    validate(conventional, result.observations)
    assert len(result.observations) == 80
    by = {(o.dims["model"], o.period): o.value for o in result.observations}
    assert by[("oscar", "2024")] == 2284.39 and by[("blue", "2024")] == 2518.94 and by[("luce", "2024")] == 1732.45
