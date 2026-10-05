"""FRA 2025 forest area and annual net change.

The fixture is a byte-exact slice of FRA_Years_2026-10-05.csv inside the real bulk-download snapshot (header,
Afghanistan to American Samoa, Brazil, French Guiana), cut by tests/fixtures/zip_member_fixture.py. Sidecars of zip
member fixtures (FRA and IUCN) sit one directory lower than make_fixture.py's, so their two checks are run here.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from envdash import canonical
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transforms.nature import fra_2025 as fra

FIXTURES = Path(__file__).parent / "fixtures"
MEMBER_SIDECARS = sorted(
    [*FIXTURES.glob("fao-fra-2025/*/*.provenance.json"), *FIXTURES.glob("iucn-red-list-gbif/*/*.provenance.json")]
)
YEARS_FIXTURE = FIXTURES / "fao-fra-2025" / "bulk-download-world" / "d93c84204f61.years.csv"


@pytest.mark.parametrize("side", MEMBER_SIDECARS, ids=lambda p: p.name)
def test_member_fixture_matches_its_sidecar(side):
    meta = json.loads(side.read_text())
    f = side.with_name(side.name.removesuffix(".provenance.json"))
    assert canonical.sha256_bytes(f.read_bytes()) == meta["fixture_sha256"]
    assert f.name.startswith(meta["full_sha256"][:12])
    assert f.parent.name == meta["artifact_id"] and f.parent.parent.name == meta["source_id"]
    for k in ("url", "date_accessed", "rows_kept", "command", "full_bytes", "member"):
        assert meta[k]
    src = load_registry(Paths.default()).sources[meta["source_id"]]
    assert src.licence_class == "open" and src.obligations.mirror_raw


@pytest.mark.snapshot
@pytest.mark.parametrize("side", MEMBER_SIDECARS, ids=lambda p: p.name)
def test_member_fixture_is_an_exact_slice_of_the_snapshot(side):
    sys.path.insert(0, str(FIXTURES))
    from zip_member_fixture import cut, parse_command

    meta = json.loads(side.read_text())
    raw = (Paths.default().cache / meta["full_sha256"]).read_bytes()
    assert canonical.sha256_bytes(raw) == meta["full_sha256"]
    source, artifact, member, ranges = parse_command(meta["command"])
    assert (source, artifact, member) == (meta["source_id"], meta["artifact_id"], meta["member"])
    assert canonical.sha256_bytes(cut(raw, member, ranges)[0]) == meta["fixture_sha256"]


def _by():
    rows, legend = fra.read_rows(YEARS_FIXTURE.read_bytes())
    return fra.forest_area(rows, legend), legend


def test_reads_legend_and_forest_area():
    by, legend = _by()
    assert legend["A"] == "Normal value, official data reported by country/area"
    assert legend["I"] == "Imputed value, desk study, data compiled by FAO"
    assert set(by) == {"AFG", "ALB", "DZA", "ASM", "BRA", "GUF"}
    assert by["BRA"][2025] == (Decimal("486086.64"), "A")
    assert by["AFG"][1990] == (Decimal("1209.44"), "I")


def test_area_world_is_the_sum_and_overseas_areas_are_published():
    by, legend = _by()
    obs = fra.area_observations(by, legend)
    entities = {o.entity for o in obs}
    assert "GUF" in entities and "FRA" not in entities and "BRA" in entities and "WLD" in entities
    world = {o.period: o.value for o in obs if o.entity == "WLD"}
    assert world["2025"] == float(sum(by[c][2025][0] for c in by))
    bra = next(o for o in obs if o.entity == "BRA" and o.period == "2025")
    assert bra.value == 486086.64 and bra.note == "FRA flag A: Normal value, official data reported by country/area."


def test_net_change_per_interval():
    by, legend = _by()
    obs = fra.net_change_observations(by, legend)
    bra = {o.period: o.value for o in obs if o.entity == "BRA"}
    assert list(bra) == ["1990/2000", "2000/2010", "2010/2015", "2015/2020", "2020/2025"]
    # (486,086.64 - 502,366.88) / 5, exact decimals.
    assert bra["2020/2025"] == -3256.048
    assert bra["1990/2000"] == float((Decimal("560720.37") - Decimal("618443.26")) / 10)


def test_refuses_missing_year_unknown_flag_and_empty_area():
    raw = YEARS_FIXTURE.read_bytes()
    lines = raw.splitlines(keepends=True)
    rows, legend = fra.read_rows(b"".join(ln for ln in lines if b'"BRA","BR","076","Brazil","No","2015"' not in ln))
    with pytest.raises(fra.FraFormatError, match="years"):
        fra.forest_area(rows, legend)
    rows, legend = fra.read_rows(raw.replace(b'"2025","486086.64","A"', b'"2025","486086.64","Z"'))
    with pytest.raises(fra.FraFormatError, match="flag"):
        fra.forest_area(rows, legend)
    rows, legend = fra.read_rows(raw.replace(b'"2025","486086.64"', b'"2025",""'))
    with pytest.raises(fra.FraFormatError, match="empty"):
        fra.forest_area(rows, legend)


def test_member_name_and_report_numbers():
    name, d = fra.member_name(["README.txt", "FRA_Years_2026-10-05.csv", "FRA_Years_variables/1a_x_2026-10-05.csv"])
    assert name == "FRA_Years_2026-10-05.csv" and d.isoformat() == "2026-10-05"
    with pytest.raises(fra.FraFormatError):
        fra.member_name(["README.txt"])
    assert fra._report_numbers(fra.REPORT_TABLE_5[1])[-1] == Decimal("4140217")
    assert fra._report_numbers(fra.REPORT_TABLE_6[1])[:2] == [Decimal("-10695"), Decimal("-0.25")]


@pytest.mark.snapshot
def test_full_snapshot_world_totals_and_report_rows():
    from envdash import snapshots
    from envdash.transform import InputFile, validate

    p = Paths.default()
    cur = snapshots.read_current(p)
    for t in fra.transforms(p):
        files = {}
        for i in t.inputs:
            snap = snapshots.read_manifest(p, cur[i.key])
            assert snap is not None
            files[i.key] = InputFile(snapshots.cache_path(p, snap.sha256), snap)
        r = t.run(files)
        validate(t, r.observations)
        world = {o.period: o.value for o in r.observations if o.entity == "WLD"}
        if t.spec.id.endswith(".area"):
            # The report's headline: "the world has 4.14 billion hectares (ha) of forest".
            assert round(world["2025"] / 1e6, 2) == 4.14
        else:
            # Report Table 6: WORLD -10 695 thousand ha a year in 1990-2000.
            assert round(world["1990/2000"]) == -10695
