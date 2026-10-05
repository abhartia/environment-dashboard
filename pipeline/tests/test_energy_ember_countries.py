"""Ember yearly electricity by country: mix, clean share and lifecycle intensity (energy/ember_countries.py).

The fixture is the ember-yearly slice shared with test_ember_yearly.py (rows 1 and 102513-104203 of the file of
22 September 2026: one ASEAN row, every World row, and Yemen, Zambia and Zimbabwe, each with data to 2024). The
full-file tests (-m snapshot) need pipeline/.snapshots populated by envdash fetch.
"""

from __future__ import annotations

import dataclasses

import pytest

from envdash import geo, snapshots
from envdash.models import Snapshot
from envdash.paths import Paths
from envdash.transform import InputFile, Validation, discover, validate
from envdash.transforms.energy import ember_countries as ec
from envdash.transforms.energy.ember_yearly import GENERATION, METHODOLOGY, EmberFormatError, read_table

from support import fixture

IDS = (
    "electricity.ember.mix-by-country",
    "electricity.ember.clean-share-by-country",
    "electricity.ember.lifecycle-intensity-by-country",
)


def _raw() -> bytes:
    path, _ = fixture("ember-yearly", "generation-yearly-global")
    return path.read_bytes()


def _read(raw: bytes | None = None) -> ec.Read:
    return ec.read(read_table(raw if raw is not None else _raw()))


def _by(obs, **dims):
    return {(o.entity, o.period): o for o in obs if o.dims == dims}


def test_world_and_the_three_countries_from_2000():
    r = _read()
    assert {ay.entity for ay in r.groups} == {"WLD", "YEM", "ZMB", "ZWE"}
    assert min(int(ay.year) for ay in r.groups) == 2000


def test_shares_and_intensity_are_published_as_printed():
    r = _read()
    mix = _by(ec.mix_observations(r), source="solar")
    clean = _by(ec.clean_observations(r))
    inten = _by(ec.intensity_observations(r))
    # release_generation_yearly_global.csv, Year 2024: Solar / Clean "Share of generation (%)", Total generation
    # "Emissions intensity (gCO2e/kWh)".
    assert mix[("ZMB", "2024")].value == 0.862 and mix[("YEM", "2024")].value == 11.238
    assert clean[("ZMB", "2024")].value == 87.475 and clean[("ZWE", "2024")].value == 57.115
    assert inten[("ZMB", "2024")].value == 125.761 and inten[("YEM", "2024")].value == 591.429
    # The World values equal those of electricity.ember.mix-world and clean-share-world (test_ember_yearly.py).
    assert mix[("WLD", "2025")].value == 8.737 and clean[("WLD", "2025")].value == 42.309
    assert inten[("WLD", "2025")].value == 460.503


def test_status_world_by_gaps_countries_by_latest_year():
    r = _read()
    clean = _by(ec.clean_observations(r))
    # The slice's countries stop in 2024, so the World's 2025 is preliminary (as in ember_yearly.py)...
    assert clean[("WLD", "2025")].status == "preliminary"
    assert clean[("WLD", "2024")].status == "final"
    # ...and their own 2024 values are final: the file's latest year is 2025.
    assert r.status.latest_year == "2025"
    assert clean[("ZMB", "2024")].status == "final" and clean[("ZMB", "2024")].note is None


def test_series_are_ordered_and_pass_validation():
    ts = {t.spec.id: t for t in discover(Paths.default())}
    r = _read()
    for tid, compute in zip(IDS, (ec.mix_observations, ec.clean_observations, ec.intensity_observations), strict=True):
        t = ts[tid]
        assert t.inputs == (GENERATION, METHODOLOGY)
        assert t.spec.geo_coverage == "country" and t.spec.headline_entity == "WLD"
        obs = compute(r)
        # The slice is too small for min_rows; everything else must hold.
        validate(dataclasses.replace(t, validation=Validation(0, t.validation.value_range)), obs)
    assert ts[IDS[2]].spec.unit.code == "gCO2e/kWh"
    assert "lifecycle" in ts[IDS[2]].spec.unit.label
    assert ts[IDS[2]].spec.scope.gwp is None and "21 times" in (ts[IDS[2]].spec.scope.basis or "")


def test_refuses_a_country_year_whose_shares_do_not_add_up():
    lines = _raw().splitlines(keepends=True)
    i = next(k for k, ln in enumerate(lines) if ln.startswith(b"Zambia,ZMB,2024,Country or economy,Solar,"))
    cols = lines[i].split(b",")
    assert cols[9] == b"0.862"  # Share of generation (%)
    cols[9] = b"5.862"
    lines[i] = b",".join(cols)
    with pytest.raises(EmberFormatError, match="Zambia 2024: the source shares add up to"):
        _read(b"".join(lines))


def test_refuses_an_intensity_that_is_not_emissions_over_generation():
    lines = _raw().splitlines(keepends=True)
    i = next(k for k, ln in enumerate(lines) if ln.startswith(b"Zambia,ZMB,2024,Country or economy,Total generation,"))
    cols = lines[i].split(b",")
    assert cols[16] == b"125.761"
    cols[16] = b"135.761"
    lines[i] = b",".join(cols)
    with pytest.raises(EmberFormatError, match=r"intensity 135\.761"):
        _read(b"".join(lines))


def test_entity_codes_are_resolved_explicitly():
    assert ec.entity_of("XKX", "Kosovo") == "KOS"
    assert ec.entity_of("GUF", "French Guiana") == "GUF" and ec.entity_of("REU", "Reunion") == "REU"
    assert ec.entity_of("ZMB", "Zambia") == "ZMB"
    with pytest.raises(EmberFormatError, match="no ISO 3 code"):
        ec.entity_of(None, "Zambia")
    with pytest.raises(geo.UnknownEntity):
        ec.entity_of("ZZZ", "an ISO code with no entity")


# --- full snapshot ------------------------------------------------------------------------------------------------


def _current(key: str) -> InputFile:
    p = Paths.default()
    sha = snapshots.read_current(p)[key]
    snap = snapshots.read_manifest(p, sha)
    assert isinstance(snap, Snapshot)
    return InputFile(snapshots.cache_path(p, sha), snap)


@pytest.mark.snapshot
def test_full_file_withholds_negative_generation_years_and_publishes_the_overseas_regions():
    r = ec.read(read_table(_current(GENERATION.key).path.read_bytes()))
    assert {"GUF", "REU"} <= {ay.entity for ay in r.groups}
    withheld = [(ay.entity, ay.year) for ay in r.groups if ec.negative_rows(ay)]
    assert ("CRI", "2025") in withheld and len(withheld) == 11
    clean = _by(ec.clean_observations(r))
    cri = clean[("CRI", "2025")]
    assert cri.value is None and "Other fossil -1.15 TWh" in (cri.missing_reason or "")
    assert clean[("CRI", "2024")].value == 99.909
    assert clean[("KOS", "2024")].value is not None
    assert clean[("DEU", "2025")].status == "preliminary" and clean[("DEU", "2024")].status == "final"
    # Germany's partial 1985-1999 rows are not published.
    assert min(o.period for o in clean.values() if o.entity == "DEU") == "2000"


@pytest.mark.snapshot
def test_full_transforms_run_and_validate():
    files = {GENERATION.key: _current(GENERATION.key), METHODOLOGY.key: _current(METHODOLOGY.key)}
    ts = {t.spec.id: t for t in discover(Paths.default())}
    for tid in IDS:
        res = ts[tid].run(files)
        validate(ts[tid], res.observations)
        assert res.vintage == "2026-09-22" and res.changes is None
        assert "pages 10, 11, 12, 15, 16" in res.steps[0]


@pytest.mark.snapshot
def test_methodology_statements_are_in_the_real_pdf():
    pages = ec.require_methodology(_current(METHODOLOGY.key).path.read_bytes())
    assert pages[ec.METHODOLOGY_REQUIRED[-1]] == 16 and pages["We provide data for 215 countries from 2000"] == 10
