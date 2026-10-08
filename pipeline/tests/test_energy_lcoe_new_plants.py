"""Levelised cost of new power plants: US EIA AEO2026 (energy/eia_aeo_lcoe.py) and its UK twin, DESNZ Electricity
Generation Costs 2025 (energy/desnz_generation_costs.py).

Fixtures: tests/fixtures/eia-aeo-2026/e371002d0282.xlsx and 8c11a13bed5b.pdf, the whole figure-data workbook and
report as fetched on 2026-10-08 (an xlsx or a PDF cannot be cut by lines and still be read; both are public domain).
DESNZ's Annex A (1.8 MB) has no committed fixture; its full parsing is tested on the snapshot (-m snapshot, which
needs pipeline/.snapshots populated by envdash fetch), and its header rules on the header strings Annex A prints.
"""

from __future__ import annotations

import io
from dataclasses import replace

import openpyxl
import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.transform import InputFile, discover, run_checks, validate
from envdash.transforms.energy import desnz_generation_costs as uk
from envdash.transforms.energy import eia_aeo_lcoe as us

from support import fixture


def _by(obs, **dims):
    (o,) = [o for o in obs if all(o.dims.get(k) == v for k, v in dims.items())]
    return o


# --- EIA AEO2026, on the fixtures ---------------------------------------------------------------------------------


def _eia_files() -> dict[str, InputFile]:
    out = {}
    for inp in (us.FIGURES, us.REPORT):
        path, meta = fixture(us.SOURCE, inp.artifact_id)
        snap = snapshots.read_manifest(Paths.default(), meta["full_sha256"])
        assert snap is not None
        out[inp.key] = InputFile(path, snap)
    return out


def _eia_rows(sheet: str) -> list[tuple]:
    path, _ = fixture(us.SOURCE, "lcoe-figures")
    wb = openpyxl.load_workbook(io.BytesIO(path.read_bytes()), read_only=True, data_only=True)
    return us._rows(wb[sheet])


def test_eia_workbook_reads_and_checks():
    path, _ = fixture(us.SOURCE, "lcoe-figures")
    w = us.read_workbook(path)
    us.check_workbook(w)
    assert list(w.plants) == list(us.TECHNOLOGIES)
    cc, ccs = w.plants["Combined-cycle"], w.plants["Combined-cycle with CCS"]
    assert (str(cc.capacity_factor), str(ccs.capacity_factor)) == ("0.4", "0.87")
    assert cc.tax_credit is None and ccs.capture_credit is not None and ccs.capture_credit < 0
    assert w.regional["Advanced nuclear"].weighted_with is None  # NB, not built


def test_eia_observations():
    path, _ = fixture(us.SOURCE, "lcoe-figures")
    obs = us.observations(us.read_workbook(path))
    assert len(obs) == 36
    assert {(o.entity, o.period, o.status) for o in obs} == {("USA", "2031", "projection")}
    cc = _by(obs, technology="gas-combined-cycle", cost_basis="before-tax-credits")
    assert round(cc.value, 2) == 77.46 and cc.interval == "range"
    assert (round(cc.lower, 2), round(cc.upper, 2)) == (66.04, 96.0)
    assert cc.note == "EIA models this plant type at a capacity factor of 40%."
    ccs = _by(obs, technology="gas-combined-cycle-ccs", cost_basis="before-tax-credits")
    assert round(ccs.value, 2) == 77.19 and ccs.note.endswith("87%.")
    ccs_credit = _by(obs, technology="gas-combined-cycle-ccs", cost_basis="with-tax-credits", average="simple-average")
    assert round(ccs_credit.value, 2) == 58.47
    nuclear = _by(obs, technology="advanced-nuclear", cost_basis="with-tax-credits", average="capacity-weighted")
    assert nuclear.value is None and "NB" in (nuclear.missing_reason or "")
    solar = _by(obs, technology="solar-pv", cost_basis="with-tax-credits", average="capacity-weighted")
    assert round(solar.value, 2) == 48.76
    assert not [
        o for o in obs if o.dims["cost_basis"] == "before-tax-credits" and o.dims["average"] != "simple-average"
    ]


def test_eia_runs_validates_and_matches_the_report():
    t = next(t for t in discover(Paths.default()) if t.spec.id == us.INDICATOR)
    assert t.inputs == (us.FIGURES, us.REPORT)
    r = t.run(_eia_files())
    validate(t, r.observations)
    outcomes = run_checks(t, {us.SOURCE: us.VINTAGE}, r.observations)
    assert len(outcomes) == 12 and {o.status for o in outcomes} == {"pass"}


def test_eia_report_labels_in_order():
    path, _ = fixture(us.SOURCE, "lcoe-report")
    labels = us.require_report(path.read_bytes())
    assert labels[0] == ("advanced nuclear", "87.81") and labels[-1] == ("battery storage", "152.61")


def test_eia_title_of_another_edition_fails():
    rows = _eia_rows(us.COMPONENTS_SHEET)
    other = [(rows[0][0], *rows[0][1:]), (rows[1][0].replace("AEO2026", "AEO2027"), *rows[1][1:]), *rows[2:]]
    with pytest.raises(us.EiaLcoeFormatError, match="is not the AEO2026 title"):
        us.read_components(other)


def test_eia_a_misread_column_fails():
    path, _ = fixture(us.SOURCE, "lcoe-figures")
    w = us.read_workbook(path)
    p = w.plants["Geothermal"]
    broken = replace(w, plants={**w.plants, "Geothermal": replace(p, total=p.total + 1)})
    with pytest.raises(us.EiaLcoeFormatError, match="components sum to"):
        us.check_workbook(broken)


# --- DESNZ Generation Costs 2025 ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "technology", "estimate"),
    [
        # Header strings as Annex A prints them (sheets 2030 to 2050), footnote numbers and trailing spaces included.
        ("Large Scale Solar ", "large-scale-solar", "unmarked"),
        ("Fixed Offshore Wind5", "offshore-wind-fixed", "unmarked"),
        ("Floating Offshore Wind (FOAK)5,12", "offshore-wind-floating", "foak"),
        ("Gas CCGT 30% Load Factor ", "gas-ccgt-30pc-load", "unmarked"),
        ("Gas Reciprocating Engine 93% Load Factor10", "gas-engine-93pc-load", "unmarked"),
        (
            "CCHT 50% 900MW 93% Load Factor (FOAK) (50% hydrogen / natural gas fuel blend)6, 12",
            "hydrogen-ccht-blend-93pc-load",
            "foak",
        ),
        ("CCHT 900MW 5% Load Factor6", "hydrogen-ccht-5pc-load", "unmarked"),
        ("OCHT 93% Load Factor ", "hydrogen-ocht-93pc-load", "unmarked"),
        ("Hydrogen Reciprocating Engines 30% (FOAK)10, 12", "hydrogen-engine-30pc-load", "foak"),
        ("Hydrogen Reciprocating Engines 5%10", "hydrogen-engine-5pc-load", "unmarked"),
        ("Hydrogen Reciprocating Engines 93% Load Factor10", "hydrogen-engine-93pc-load", "unmarked"),
        ("Gas CCUS 900MW 88% Load Factor9", "gas-ccus-88pc-load", "unmarked"),
        ("Deep Granite Geothermal (FOAK)12", "deep-geothermal", "foak"),
        ("Tidal Stream Energy", "tidal-stream", "unmarked"),
    ],
)
def test_desnz_headers(header, technology, estimate):
    c = uk.parse_header(header)
    assert (c.technology, c.estimate) == (technology, estimate)
    assert technology in uk.TECHNOLOGIES


@pytest.mark.parametrize(
    "header",
    [
        "Gas CCUS 900MW 93% Load Factor9",
        "Gas CCGT",
        "Nuclear",
        "CCHT 900MW 5% Load Factor (50% hydrogen / natural gas fuel blend)",
    ],
)
def test_desnz_unknown_or_inconsistent_headers_fail(header):
    with pytest.raises(uk.DesnzFormatError):
        uk.parse_header(header)


def test_desnz_spec():
    t = next(t for t in discover(Paths.default()) if t.spec.id == uk.INDICATOR)
    assert t.inputs == (uk.ANNEX,) and t.spec.unit.code == "GBP2024/MWh" and t.spec.headline_entity == "GBR"
    assert [d.id for d in t.spec.dimensions] == ["technology", "estimate", "component"]


@pytest.mark.snapshot
def test_desnz_annex_on_the_snapshot():
    p = Paths.default()
    sha = snapshots.read_current(p)[uk.ANNEX.key]
    snap = snapshots.read_manifest(p, sha)
    assert snap is not None
    t = uk.transforms(p)[0]
    r = t.run({uk.ANNEX.key: InputFile(snapshots.cache_path(p, sha), snap)})
    validate(t, r.observations)
    obs = r.observations
    assert len(obs) == 1661

    # Annex A, sheet "Additional Estimates 2030": Gas CCGT 93% total 111 (fuel 45, carbon 41); Gas CCUS 88% total 105
    # (carbon 5, CO2 transport and storage 3); Onshore Wind total 58.
    def v(year, tech, comp, est="unmarked"):
        return _by([o for o in obs if o.period == str(year)], technology=tech, component=comp, estimate=est).value

    assert v(2030, "gas-ccgt-93pc-load", "total") == 111 and v(2030, "gas-ccgt-93pc-load", "carbon") == 41
    assert v(2030, "gas-ccus-88pc-load", "total") == 105 and v(2030, "gas-ccus-88pc-load", "co2-transport-storage") == 3
    assert v(2030, "onshore-wind", "total") == 58
    assert v(2030, "offshore-wind-floating", "total", "foak") == 153
    assert v(2035, "deep-geothermal", "total", "foak") == 261 and v(2035, "deep-geothermal", "total") == 60
    lt1 = _by([o for o in obs if o.period == "2030"], technology="gas-ccgt-93pc-load", component="pre-development")
    assert lt1.value is None and "'<1'" in (lt1.missing_reason or "")
