"""Ember monthly electricity: World monthly mix, clean share and fossil change (energy/ember_monthly.py).

The fixture is rows 1 and 175679-178200 of the file of 18 September 2026: one ASEAN row, every Viet Nam row (January
2019 to October 2025) and every World row (January 2019 to July 2026). The full-file tests (-m snapshot) need
pipeline/.snapshots populated by envdash fetch.
"""

from __future__ import annotations

import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.transform import InputFile, discover, validate
from envdash.transforms.energy import ember_monthly as em
from envdash.transforms.energy.ember_yearly import EmberFormatError

from support import fixture


def _raw() -> bytes:
    path, _ = fixture("ember-monthly", "generation-monthly-global")
    return path.read_bytes()


def _df(raw: bytes | None = None):
    return em.read_table(raw if raw is not None else _raw())


def _replace_cell(raw: bytes, prefix: bytes, col: int, old: bytes, new: bytes) -> bytes:
    lines = raw.splitlines(keepends=True)
    i = next(k for k, ln in enumerate(lines) if ln.startswith(prefix))
    cols = lines[i].split(b",")
    assert cols[col] == old
    cols[col] = new
    lines[i] = b",".join(cols)
    return b"".join(lines)


def test_world_monthly_values_as_printed():
    df = _df()
    mix = {(o.period, o.dims["source"]): o.value for o in em.mix_observations(df)}
    clean = {o.period: o.value for o in em.clean_observations(df)}
    fossil = {o.period: o.value for o in em.fossil_change_observations(df)}
    # release_generation_monthly_global.csv, Area World: "Share of generation (%)" of Solar and Clean, and
    # "Generation YoY change (%)" of Fossil.
    assert mix[("2026-07", "solar")] == 11.277 and mix[("2019-01", "solar")] == 1.584
    assert clean["2026-07"] == 43.503
    assert fossil["2026-07"] == -0.886 and fossil["2020-01"] == -2.769
    assert min(fossil) == "2020-01" and min(clean) == "2019-01" and max(clean) == "2026-07"
    assert len(mix) == 9 * len(clean)


def test_months_after_a_country_stops_are_preliminary_with_counts():
    df = _df()
    cov = em.country_coverage(df)
    # In the slice only Viet Nam has country rows, January 2019 to October 2025.
    assert cov["2025-10"] == (1, 1, []) and cov["2025-11"] == (0, 1, ["Viet Nam"])
    clean = {o.period: o for o in em.clean_observations(df)}
    assert clean["2025-10"].status == "final"
    assert "Total generation for 1 countries" in (clean["2025-10"].note or "")
    assert clean["2025-11"].status == "preliminary"
    assert "1 of the 1 with generation for an earlier month have none" in (clean["2025-11"].note or "")


def test_refuses_a_fossil_change_that_is_not_the_difference():
    raw = _replace_cell(_raw(), b"World,,2026-07-01,Region,Fossil,", 7, b"-14.838", b"-24.838")
    with pytest.raises(EmberFormatError, match=r"Fossil change -24\.838 TWh"):
        em.fossil_change_observations(_df(raw))


def test_refuses_shares_that_do_not_add_up():
    raw = _replace_cell(_raw(), b"World,,2026-07-01,Region,Solar,", 9, b"11.277", b"12.277")
    with pytest.raises(EmberFormatError, match="add up to"):
        em.mix_observations(_df(raw))


def test_refuses_changed_columns():
    with pytest.raises(EmberFormatError, match="columns"):
        _df(_raw().replace(b"Generation YoY change (%)", b"Generation YoY change (pct)", 1))


def test_three_indicators_validate():
    ts = {t.spec.id: t for t in discover(Paths.default())}
    df = _df()
    for tid, compute in (
        ("electricity.ember.monthly-mix-world", em.mix_observations),
        ("electricity.ember.monthly-clean-share-world", em.clean_observations),
        ("electricity.ember.monthly-fossil-change-world", em.fossil_change_observations),
    ):
        assert ts[tid].inputs == (em.MONTHLY,)
        validate(ts[tid], compute(df))
    assert dict(ts["electricity.ember.monthly-mix-world"].spec.headline_dims) == {"source": "solar"}


# --- full snapshot ------------------------------------------------------------------------------------------------


@pytest.mark.snapshot
def test_full_transform_run():
    p = Paths.default()
    sha = snapshots.read_current(p)[em.MONTHLY.key]
    snap = snapshots.read_manifest(p, sha)
    assert snap is not None
    files = {em.MONTHLY.key: InputFile(snapshots.cache_path(p, sha), snap)}
    ts = {t.spec.id: t for t in discover(p)}
    res = ts["electricity.ember.monthly-clean-share-world"].run(files)
    assert res.vintage == "2026-09-18"
    by = {o.period: o for o in res.observations}
    # Ukraine's monthly series stops in September 2022.
    assert by["2022-09"].status == "final" and by["2022-10"].status == "preliminary"
    assert "Total generation for 56 countries" in (by["2026-07"].note or "")
    assert "Preliminary months in this vintage: 46, the first 2022-10 and the last 2026-07." in res.steps[2]
