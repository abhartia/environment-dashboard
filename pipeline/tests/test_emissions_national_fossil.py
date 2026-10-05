"""Fossil CO2 by country, fuel, person and cumulative (gcp-fossil-co2-2025, 2025v15).

The fixture tests/fixtures/gcp-fossil-co2-2025/20650c19b394.csv keeps the header and the rows of the first ten
countries (Afghanistan to Armenia, 275 years each) and the last three entities (international shipping, international
aviation, Global): byte-exact lines of the real file. A slice cannot satisfy the "Global equals the sum of all rows"
check, so the transforms that rely on it are expected to stop on the fixture; that check, the Netherlands per-person
exception and the full shares run on the real snapshot (marked snapshot).
"""

from __future__ import annotations

import csv
import dataclasses
import io
import json
import shutil
from decimal import Decimal

import pytest

from envdash import snapshots
from envdash.export import build_and_export
from envdash.paths import REPO_ROOT, Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, discover
from envdash.transforms.emissions import gcp_fossil_national as gcp
from envdash.validate import validate_all

from support import exported, fixture, load_fixture_snapshot

IDS = (
    "emissions.gcp-2025.fossil-co2-by-country",
    "emissions.gcp-2025.fossil-co2-by-fuel",
    "emissions.gcp-2025.fossil-co2-cumulative",
    "emissions.gcp-2025.fossil-co2-cumulative-share",
    "emissions.gcp-2025.fossil-co2-per-capita",
)
FIXTURE_ENTITIES = ["AFG", "ALB", "DZA", "AND", "AGO", "AIA", "ATA", "ATG", "ARG", "ARM", "INTL_SEA", "INTL_AIR", "WLD"]


def _raw() -> bytes:
    return fixture(gcp.SOURCE, "mtco2-flat")[0].read_bytes()


def _table() -> gcp.Table:
    rows = gcp.read_flat(_raw())
    gcp._check_series(rows)
    ((version, published),) = gcp.PINNED.values()
    return gcp.Table(version, published, tuple(rows))


def _csv_rows() -> list[list[str]]:
    return list(csv.reader(io.StringIO(_raw().decode("utf-8"), newline="")))[1:]


def test_metadata_states_version_and_units():
    path, _ = fixture(gcp.SOURCE, "mtco2-metadata")
    assert gcp.read_metadata(path.read_bytes()) == "2025v15"
    meta = json.loads(path.read_bytes())
    fields = [dict(f, units="thousands of tonnes of CO2") if f["name"] == "Coal" else f for f in meta["fields"]]
    changed = {"fields": fields}
    with pytest.raises(gcp.GcpFormatError, match="Coal"):
        gcp.read_metadata(json.dumps(changed).encode())


def test_reads_entities_in_file_order_with_every_year():
    t = _table()
    assert [e for e, _ in t.series()] == FIXTURE_ENTITIES
    for _, rows in t.series():
        assert [r.year for r in rows] == list(range(1750, 2025))
    world = {r.year: r for r in t.rows if r.entity == "WLD"}
    assert world[2024].cells["Total"] == Decimal("38598.578033")
    assert world[2024].cells["Per Capita"] == Decimal("4.729075")
    # The Global row's Other column is empty for 1904-1989 although its Total includes other carbonates.
    assert [y for y in range(1904, 1991) if world[y].cells["Other"] is None] == list(range(1904, 1990))


def test_empty_cells_are_not_zero():
    t = _table()
    total = {(o.entity, o.period): o.value for o in gcp.total_observations(t)}
    empty = [(r[1] or r[0], r[3]) for r in _csv_rows() if r[4] == ""]
    assert empty and all((gcp.geo.resolve(c, gcp.SOURCE), y) not in total for c, y in empty)
    stated = sum(1 for r in _csv_rows() if r[4] != "")
    assert len(total) == stated
    fuel = gcp.fuel_observations(t)
    assert len(fuel) == sum(1 for r in _csv_rows() for v in r[5:11] if v != "")
    other = [o.period for o in fuel if o.entity == "WLD" and o.dims == {"fuel": "other"}]
    assert other == [str(y) for y in range(1990, 2025)]


def test_per_capita_is_the_producers_column_without_transport():
    t = _table()
    pc = {(o.entity, o.period): o for o in gcp.per_capita_observations(t)}
    assert not {e for e, _ in pc} & {"INTL_AIR", "INTL_SEA"}
    for r in _csv_rows():
        code = gcp.geo.resolve(r[1] or r[0], gcp.SOURCE)
        if r[11] and code not in gcp.NO_POPULATION:
            assert pc[(code, r[3])].value == float(Decimal(r[11]))
    assert pc[("WLD", "2024")].value == 4.729075


def test_per_capita_stops_if_transport_gets_a_value():
    t = _table()
    rows = [
        gcp.Row(r.entity, r.country, r.year, {**r.cells, "Per Capita": Decimal("0.1")})
        if r.entity == "INTL_SEA" and r.year == 2024
        else r
        for r in t.rows
    ]
    with pytest.raises(gcp.GcpFormatError, match="no population"):
        gcp.per_capita_observations(gcp.Table(t.version, t.published, tuple(rows)))


def test_cumulative_is_an_exact_running_sum():
    t = _table()
    cum = gcp.cumulative_observations(t)
    world = [o for o in cum if o.entity == "WLD"]
    expected = sum((Decimal(r[4]) for r in _csv_rows() if r[1] == "WLD"), Decimal(0)) / 1000
    assert world[0].period == "1750"
    assert world[-1].value == float(expected) == 1849.123858831
    afg = [o for o in cum if o.entity == "AFG"]
    assert afg[0].period == "1949" and afg[-1].value == 0.242635435
    # Armenia's record has empty years after its first value: they add nothing and the note says how many.
    arm = {o.period: o for o in cum if o.entity == "ARM"}
    assert min(arm) == "1830"
    assert arm["1833"].note is None
    assert arm["1834"].value == arm["1833"].value
    assert arm["1834"].note == (
        "Sum of the file's values from 1830 to 1834; 1 year in that span has no value in the file, which adds "
        "nothing to the sum."
    )
    assert arm["2024"].value == 0.406690041 and "22 years in that span have" in arm["2024"].note


def test_share_divides_by_the_global_running_total():
    t = _table()
    cum = {(o.entity, o.period): o.value for o in gcp.cumulative_observations(t)}
    share = {(o.entity, o.period): o for o in gcp.share_observations(t)}
    assert not any(e == "WLD" for e, _ in share)
    assert share[("INTL_SEA", "2024")].value == pytest.approx(1.5996349221138562, abs=1e-12)
    assert share[("ARM", "2024")].value == pytest.approx(cum[("ARM", "2024")] / cum[("WLD", "2024")] * 100, rel=1e-12)
    assert share[("ARM", "2024")].note == {o.entity: o for o in gcp.cumulative_observations(t)}["ARM"].note


def test_the_world_identity_stops_a_file_that_does_not_add_up():
    with pytest.raises(gcp.GcpFormatError, match="no longer add up"):
        gcp.largest_world_residual(list(_table().rows))


def _paths(tmp_paths: Paths) -> Paths:
    shutil.copy(REPO_ROOT / "pipeline" / "sources" / f"{gcp.SOURCE}.yaml", tmp_paths.sources)
    load_fixture_snapshot(tmp_paths, gcp.SOURCE, "mtco2-flat")
    load_fixture_snapshot(tmp_paths, gcp.SOURCE, "mtco2-metadata")
    return tmp_paths


def test_build_on_the_fixture(tmp_paths):
    paths = _paths(tmp_paths)
    reg = load_registry(paths)
    ts = [t for t in discover(paths) if t.spec.id in IDS]
    assert sorted(t.spec.id for t in ts) == sorted(IDS)
    report = build_and_export(paths, reg, ts)
    states = {o.id: (o.state, o.reason or "") for o in report.outcomes}
    # The slice cannot pass the Global = sum of rows check, nor the full file's row minimums.
    for i in IDS[0], IDS[2], IDS[3]:
        assert states[i][0] == "failed" and "no longer add up" in states[i][1], states[i]
    for i in IDS[1], IDS[4]:
        assert states[i][0] == "failed" and "fewer than the minimum" in states[i][1], states[i]


def test_transforms_build_with_the_full_minimums_relaxed(tmp_paths):
    """The same transforms on the fixture, with the row minimums of the full file lowered to the fixture's size."""
    paths = _paths(tmp_paths)
    reg = load_registry(paths)
    ts = [
        dataclasses.replace(t, validation=dataclasses.replace(t.validation, min_rows=1))
        for t in discover(paths)
        if t.spec.id in ("emissions.gcp-2025.fossil-co2-by-fuel", "emissions.gcp-2025.fossil-co2-per-capita")
    ]
    report = build_and_export(paths, reg, ts)
    assert [o.state for o in report.outcomes] == ["built", "built"], [o.reason for o in report.outcomes]
    fuel = exported(paths.public_indicators / "emissions.gcp-2025.fossil-co2-by-fuel.json")
    assert fuel["vintage"] == "2025v15"
    assert fuel["origins"][0]["date_published"] == "2025-10-22"
    assert fuel["latest"] == {"age_bp": None, "dims": {"fuel": "coal"}, "entity": "WLD", "period": "2024",
                              "status": "final", "value": 15805.254152}  # fmt: skip
    assert fuel["scope"]["lulucf"] == "excluded" and fuel["scope"]["bunkers"] == "excluded"
    assert "before the cement carbonation sink" in fuel["scope"]["basis"]
    assert fuel["origins"][0]["version_producer"] == "2025v15"
    assert validate_all(paths, reg) == []


def test_unpinned_url_is_refused(tmp_paths):
    paths = _paths(tmp_paths)
    current = snapshots.read_current(paths)
    files = {}
    for i in (gcp.FLAT, gcp.METADATA):
        snap = snapshots.read_manifest(paths, current[i.key])
        assert snap is not None
        files[i.key] = InputFile(snapshots.cache_path(paths, snap.sha256), snap)
    assert gcp.load(files).version == "2025v15"
    other = files[gcp.FLAT.key].snapshot.model_copy(update={"url": "https://zenodo.org/api/records/1/files/x/content"})
    with pytest.raises(gcp.GcpFormatError, match="not a pinned"):
        gcp.load({**files, gcp.FLAT.key: InputFile(files[gcp.FLAT.key].path, other)})


def test_every_input_is_a_registered_artifact():
    src = load_registry(Paths.default()).sources[gcp.SOURCE]
    ids = {a.id for a in src.artifacts}
    urls = {str(a.url) for a in src.artifacts}
    assert set(gcp.PINNED) <= urls
    for t in gcp.transforms(Paths.default()):
        assert {i.artifact_id for i in t.inputs} <= ids
    assert src.licence_class == "open"


# --- full file (local snapshot cache) -------------------------------------------------------------------------------


def _current_files() -> dict[str, InputFile]:
    paths = Paths.default()
    current = snapshots.read_current(paths)
    out = {}
    for i in (gcp.FLAT, gcp.METADATA):
        snap = snapshots.read_manifest(paths, current[i.key])
        assert snap is not None
        out[i.key] = InputFile(snapshots.cache_path(paths, snap.sha256), snap)
    return out


@pytest.mark.snapshot
def test_full_file_world_identity_and_counts():
    t = gcp.load(_current_files())
    assert gcp.largest_world_residual(list(t.rows)) <= Decimal("0.00001")
    assert len({r.entity for r in t.rows}) == 222
    assert len(gcp.total_observations(t)) == 24_085
    assert len(gcp.fuel_observations(t)) == 95_754
    total = {(o.entity, o.period): o.value for o in gcp.total_observations(t)}
    assert total[("USA", "2024")] == 4904.119652
    assert total[("CHN", "2024")] == 12289.036755
    assert total[("KWT_OILFIRES", "1991")] > 0


@pytest.mark.snapshot
def test_full_file_netherlands_per_capita_exception():
    t = gcp.load(_current_files())
    pc = {(o.entity, o.period): o for o in gcp.per_capita_observations(t)}
    withheld = [p for (e, p), o in pc.items() if e == "NLD" and o.value is None]
    assert withheld == [str(y) for y in range(1900, 1950)]
    assert "a thousandth" in pc[("NLD", "1931")].missing_reason
    assert pc[("NLD", "1899")].value is not None and pc[("NLD", "1950")].value is not None
    # Total / Per Capita in the neighbouring years implies millions of people.
    for y in (1899, 1950):
        r = next(r for r in t.rows if r.entity == "NLD" and r.year == y)
        assert r.cells["Total"] * 1_000_000 / r.cells["Per Capita"] > 5_000_000
    assert sum(1 for o in pc.values() if o.value is None) == 50


@pytest.mark.snapshot
def test_full_file_shares_add_up_to_one_hundred():
    t = gcp.load(_current_files())
    share = gcp.share_observations(t)
    for year in ("1850", "1950", "2024"):
        assert sum(o.value for o in share if o.period == year) == pytest.approx(100, abs=1e-4)
    top = sorted((o for o in share if o.period == "2024"), key=lambda o: -o.value)[:3]
    assert [o.entity for o in top] == ["USA", "CHN", "RUS"]
    cum = {(o.entity, o.period): o.value for o in gcp.cumulative_observations(t)}
    assert cum[("USA", "2024")] == pytest.approx(434.866567813, abs=1e-9)
