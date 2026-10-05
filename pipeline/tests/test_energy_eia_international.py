"""EIA international energy data: primary energy by fuel, total and fossil share (energy/eia_international.py).

Fixtures:
- tests/fixtures/eia-international/intl-bulk/9251a5920ebe.txt: 162 lines of INTL.txt from INTL.zip of 3 October 2026,
  cut by make_intl_fixture.py (the command is in the sidecar): the annual quad Btu and billion kWh series of total
  energy consumption, its five fuels and hydro, wind, solar, geothermal, tide and wave and nuclear generation, for
  the World, the United States, China, Germany, Laos, Kosovo, the former USSR and two EIA regions (EU27, and WP18,
  which holds Mexico alone);
- tests/fixtures/eia-international/f4a1dc3cf0dc.json: the whole bulk manifest.
The full-file tests (-m snapshot) need pipeline/.snapshots populated by envdash fetch.
"""

from __future__ import annotations

import dataclasses
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from envdash import canonical, snapshots
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, Validation, discover, validate
from envdash.transforms.energy import eia_international as e

from support import FIXTURES, fixture

HERE = FIXTURES / "eia-international"
SIDECARS = sorted((HERE / "intl-bulk").glob("*.provenance.json"))
BULK_URL = "https://www.eia.gov/opendata/bulk/INTL.zip"
IDS = ("energy.eia.primary-by-fuel", "energy.eia.primary-total", "energy.eia.fossil-share")


def _text() -> bytes:
    (side,) = SIDECARS
    return side.with_name(side.name.removesuffix(".provenance.json")).read_bytes()


def _table(text: bytes | None = None) -> e.Table:
    return e.consumption(e.read_series(text if text is not None else _text()))


# --- fixtures ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("side", SIDECARS, ids=lambda p: p.name)
def test_fixture_matches_its_sidecar(side: Path):
    meta = json.loads(side.read_text())
    f = side.with_name(side.name.removesuffix(".provenance.json"))
    assert canonical.sha256_bytes(f.read_bytes()) == meta["fixture_sha256"]
    assert f.name.startswith(meta["full_sha256"][:12])
    assert f.parent.name == meta["artifact_id"] and f.parent.parent.name == meta["source_id"] == e.SOURCE
    for k in ("url", "date_accessed", "rows_kept", "command", "full_bytes"):
        assert meta[k]
    src = load_registry(Paths.default()).sources[meta["source_id"]]
    assert src.licence_class == "open" and src.obligations.mirror_raw


@pytest.mark.snapshot
@pytest.mark.parametrize("side", SIDECARS, ids=lambda p: p.name)
def test_fixture_is_an_exact_slice_of_the_snapshot(side: Path):
    sys.path.insert(0, str(HERE))
    from make_intl_fixture import cut, parse_command

    meta = json.loads(side.read_text())
    raw = (Paths.default().cache / meta["full_sha256"]).read_bytes()
    assert canonical.sha256_bytes(raw) == meta["full_sha256"]
    sliced, _ = cut(raw, *parse_command(meta["command"]))
    assert canonical.sha256_bytes(sliced) == meta["fixture_sha256"]


# --- reading -------------------------------------------------------------------------------------------------------


def test_countries_and_world_only():
    t = _table()
    # EU27 and WP18 (Mexico as an EIA region) are skipped, the former USSR (SUN) has no entity, XKS is Kosovo.
    assert sorted(t.by_entity) == ["CHN", "DEU", "KOS", "LAO", "USA", "WLD"]
    assert t.geography["KOS"] == "XKS" and t.geography["WLD"] == "WLD"


def test_values_as_given():
    t = _table()
    w = t.by_entity["WLD"]
    # INTL.44-2-WORL-QBTU.A and INTL.44xx-2-WORL-QBTU.A, 2024.
    assert float(w["44"]["2024"]) == 606.037013293999
    assert float(w["4411"]["2024"]) == 179.6540438797921
    assert float(w["4417"]["2024"]) == 28.386236755999686
    obs = {(o.entity, o.period, o.dims["fuel"]): o for o in e.fuel_observations(t)}
    assert obs[("CHN", "2024", "coal")].value == 105.29764715297713
    assert obs[("KOS", "1990", "coal")].value is None
    assert obs[("KOS", "1990", "coal")].missing_reason == "EIA's file gives the code '--' instead of a value."


def test_captured_energy_method_and_its_exceptions():
    m = e.check_captured_energy(e.read_series(_text()))
    assert m.checked == 580
    assert set(m.exceptions) == {"USA"} and "solar 2024 3622" in m.exceptions["USA"]
    assert round(m.nuclear_world["2024"]) == 10379


def test_refuses_a_country_off_the_captured_energy_basis():
    # China's wind generation in quad Btu, 2024, made 10% larger: no longer 3,412 Btu per kWh.
    text = _text().replace(b'["2024",3.402041693893881]', b'["2024",3.7422458632832691]', 1)
    with pytest.raises(e.EiaFormatError, match="Wind electricity net generation, China, Annual 2024"):
        e.check_captured_energy(e.read_series(text))


def test_only_the_united_states_total_differs_from_its_fuels():
    gaps = e.sum_gaps(_table())
    assert set(gaps) == {"USA", "WLD"}
    assert gaps["USA"]["2024"] == Decimal("-1.441577539")
    assert abs(gaps["WLD"]["2024"] - gaps["USA"]["2024"]) < Decimal("1e-12")


def test_fossil_share():
    obs = {(o.entity, o.period): o for o in e.fossil_share_observations(_table())}
    assert obs[("WLD", "2024")].value == pytest.approx(
        (179.6540438797921 + 155.4510097134598 + 201.3234359050793) / 606.037013293999 * 100, rel=1e-15
    )
    lao = obs[("LAO", "2017")]
    assert lao.value is not None and lao.value > 100 and "(0.2364 quad Btu) is smaller" in (lao.note or "")
    assert obs[("KOS", "1990")].value is None and "total '--'" in (obs[("KOS", "1990")].missing_reason or "")


def test_vintage_from_the_bulk_manifest():
    path, _ = fixture(e.SOURCE, "bulk-manifest")
    release = e.release_of(path.read_bytes(), BULK_URL)
    assert release.isoformat() == "2026-09-30T21:20:54-04:00"
    assert e.vintage_of(release) == "Sep 2026"
    with pytest.raises(e.EiaFormatError, match=re.escape("not 'https://api.eia.gov/bulk/INTL.zip'")):
        e.release_of(path.read_bytes(), "https://api.eia.gov/bulk/INTL.zip")


def test_refuses_a_renamed_series():
    text = _text().replace(b'"Total energy consumption from coal, World, Annual"', b'"Coal consumption, World, Annual"')
    with pytest.raises(e.EiaFormatError, match="product 4411 is named"):
        _table(text)


def test_indicators_validate_on_the_slice():
    ts = {t.spec.id: t for t in discover(Paths.default())}
    t = _table()
    for tid, compute in zip(IDS, (e.fuel_observations, e.total_observations, e.fossil_share_observations), strict=True):
        assert ts[tid].inputs == (e.BULK, e.MANIFEST)
        validate(dataclasses.replace(ts[tid], validation=Validation(0, ts[tid].validation.value_range)), compute(t))
    assert ts["energy.eia.fossil-share"].spec.kind == "derived"
    assert "captured-energy" in (ts["energy.eia.primary-total"].spec.scope.basis or "")


# --- full snapshot ------------------------------------------------------------------------------------------------


@pytest.mark.snapshot
def test_full_transform_run():
    p = Paths.default()
    cur = snapshots.read_current(p)
    files = {}
    for i in (e.BULK, e.MANIFEST):
        snap = snapshots.read_manifest(p, cur[i.key])
        assert snap is not None
        files[i.key] = InputFile(snapshots.cache_path(p, cur[i.key]), snap)
    ts = {t.spec.id: t for t in discover(p)}
    res = ts["energy.eia.fossil-share"].run(files)
    validate(ts["energy.eia.fossil-share"], res.observations)
    assert res.vintage == "Sep 2026" and res.changes
    assert "(11,140 country-years checked)" in res.steps[2]
    assert "Entities where they differ in this vintage: USA, WLD" in res.steps[3]
    over = [o for o in res.observations if o.value is not None and o.value > 100]
    assert len(over) == 244 and max(o.value for o in over) == pytest.approx(109.637, abs=1e-3)  # type: ignore[type-var]
