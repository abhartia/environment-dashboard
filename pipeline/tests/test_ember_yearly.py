"""Ember yearly electricity: World generation mix and clean share (envdash/transforms/energy/ember_yearly.py).

The fixture is rows 1 and 102513-104203 of the file of 22 September 2026: one ASEAN row, every World row (2000-2025)
and the countries after World in the file (Yemen, Zambia, Zimbabwe, each with data to 2024). The full-file tests
(-m snapshot) need pipeline/.snapshots populated by envdash fetch.
"""

from __future__ import annotations

import pytest

from envdash import snapshots
from envdash.models import Snapshot
from envdash.paths import Paths
from envdash.transform import InputFile, discover, validate
from envdash.transforms.energy.ember_yearly import (
    GENERATION,
    METHODOLOGY,
    METHODOLOGY_REQUIRED,
    EmberFormatError,
    clean_observations,
    country_gaps,
    mix_observations,
    read_table,
    require_methodology,
    vintage_of,
)

from support import fixture


def _df():
    path, _ = fixture("ember-yearly", "generation-yearly-global")
    return read_table(path.read_bytes())


def _manifest(sha: str) -> Snapshot:
    snap = snapshots.read_manifest(Paths.default(), sha)
    assert snap is not None
    return snap


def test_vintage_is_the_files_last_modified_date():
    _, meta = fixture("ember-yearly", "generation-yearly-global")
    snap = _manifest(meta["full_sha256"])
    assert snap.last_modified == "Tue, 22 Sep 2026 16:24:55 GMT"
    assert vintage_of(snap.last_modified) == "2026-09-22"
    with pytest.raises(EmberFormatError, match="Last-Modified"):
        vintage_of(None)


def test_mix_publishes_embers_world_shares_as_printed():
    obs = mix_observations(_df())
    assert len(obs) == 26 * 9 and {o.entity for o in obs} == {"WLD"}
    by = {(o.period, o.dims["source"]): o.value for o in obs}
    # release_generation_yearly_global.csv, Area World, Year 2025, column "Share of generation (%)".
    assert by[("2025", "solar")] == 8.737
    assert by[("2025", "wind")] == 8.499
    assert by[("2025", "nuclear")] == 8.829
    assert by[("2025", "coal")] == 33.347
    assert by[("2025", "gas")] == 21.762
    assert by[("2000", "solar")] == 0.007
    assert {o.period for o in obs} == {str(y) for y in range(2000, 2026)}
    assert {o.dims["source"] for o in obs} == {
        "solar",
        "wind",
        "hydro",
        "bioenergy",
        "other-renewables",
        "nuclear",
        "coal",
        "gas",
        "other-fossil",
    }


def test_clean_share_is_embers_clean_row():
    obs = clean_observations(_df())
    by = {o.period: o.value for o in obs}
    assert by["2025"] == 42.309 and by["2024"] == 40.603 and by["2000"] == 35.288
    assert len(obs) == 26


def test_country_gaps_count_only_series_that_stopped():
    gaps = country_gaps(_df())
    # In the slice, Yemen, Zambia and Zimbabwe all have Total generation for 2000-2024 and none for 2025.
    assert gaps["2025"] == (3, ["Yemen", "Zambia", "Zimbabwe"])
    assert gaps["2024"] == (3, [])
    assert gaps["2000"] == (0, [])


def test_year_with_missing_countries_is_preliminary_with_a_note():
    obs = clean_observations(_df())
    by = {o.period: o for o in obs}
    assert by["2025"].status == "preliminary"
    assert "no 2025 generation for 3 of the 3 countries" in by["2025"].note
    assert by["2024"].status == "final" and by["2024"].note is None
    mix = mix_observations(_df())
    assert {o.status for o in mix if o.period == "2025"} == {"preliminary"}
    assert {o.status for o in mix if o.period != "2025"} == {"final"}


def test_refuses_a_world_year_without_one_of_the_nine_sources():
    path, _ = fixture("ember-yearly", "generation-yearly-global")
    raw = b"".join(
        ln for ln in path.read_bytes().splitlines(keepends=True) if not ln.startswith(b"World,,2025,Region,Nuclear,")
    )
    with pytest.raises(EmberFormatError, match="non-aggregated sources"):
        mix_observations(read_table(raw))


def test_refuses_changed_columns():
    path, _ = fixture("ember-yearly", "generation-yearly-global")
    raw = path.read_bytes().replace(b"Share of generation (%)", b"Share of generation (pct)", 1)
    with pytest.raises(EmberFormatError, match="columns"):
        read_table(raw)


def test_both_indicators_are_discovered_and_pass_their_validation():
    ts = {t.spec.id: t for t in discover(Paths.default())}
    mix, clean = ts["electricity.ember.mix-world"], ts["electricity.ember.clean-share-world"]
    assert mix.inputs == clean.inputs == (GENERATION, METHODOLOGY)
    assert dict(mix.spec.headline_dims) == {"source": "solar"}
    validate(mix, mix_observations(_df()))
    validate(clean, clean_observations(_df()))


# --- full snapshot ------------------------------------------------------------------------------------------------


def _current(key: str) -> InputFile:
    p = Paths.default()
    sha = snapshots.read_current(p)[key]
    return InputFile(snapshots.cache_path(p, sha), _manifest(sha))


@pytest.mark.snapshot
def test_full_file_marks_2023_to_2025_partly_estimated():
    df = read_table(_current(GENERATION.key).path.read_bytes())
    gaps = country_gaps(df)
    assert {y: (n, len(m)) for y, (n, m) in gaps.items() if m and int(y) >= 2000} == {
        "2023": (209, 1),
        "2024": (209, 15),
        "2025": (209, 116),
    }
    assert gaps["2023"][1] == ["Ukraine"]
    obs = {o.period: o for o in clean_observations(df)}
    assert obs["2025"].value == 42.309 and obs["2025"].status == "preliminary"
    assert obs["2022"].status == "final"


@pytest.mark.snapshot
def test_methodology_statements_are_in_the_real_pdf_and_a_changed_one_is_not(monkeypatch):
    import envdash.transforms.energy.ember_yearly as m

    pdf = _current(METHODOLOGY.key).path.read_bytes()
    assert require_methodology(pdf) == {METHODOLOGY_REQUIRED[0]: 10, METHODOLOGY_REQUIRED[1]: 12}
    changed = (METHODOLOGY_REQUIRED[0].replace("monthly data", "weekly data"), METHODOLOGY_REQUIRED[1])
    monkeypatch.setattr(m, "METHODOLOGY_REQUIRED", changed)
    with pytest.raises(EmberFormatError, match="re-read"):
        require_methodology(pdf)


@pytest.mark.snapshot
def test_full_transform_run():
    files = {GENERATION.key: _current(GENERATION.key), METHODOLOGY.key: _current(METHODOLOGY.key)}
    ts = {t.spec.id: t for t in discover(Paths.default())}
    res = ts["electricity.ember.clean-share-world"].run(files)
    assert res.vintage == "2026-09-22" and res.changes is None
    assert "Preliminary years in this vintage: 2023, 2024, 2025." in res.steps[2]
    assert "pages 10, 12" in res.steps[2]
