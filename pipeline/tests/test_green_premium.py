"""Green premiums quoted from their producers (action/green_premium.py).

Fixture: tests/fixtures/gardarsdottir-2019/50f05980ed4f.pdf, the whole CEMCAP article as recorded (a PDF cannot be
cut by lines and still be read). The IEA reports are not re-hosted (mirror_raw false: they hold third-party figures),
so their statements are checked on the snapshots (-m snapshot, which needs pipeline/.snapshots populated by envdash
fetch).
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from envdash import snapshots, textmatch
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, discover, validate
from envdash.transforms.action import green_premium as gp

from support import fixture

IDS = {p.id: p for p in gp.PREMIUMS}


def _by(obs, **dims):
    (o,) = [o for o in obs if all(o.dims.get(k) == v for k, v in dims.items())]
    return o


@pytest.fixture(scope="module")
def cemcap_pages() -> list[str]:
    path, _ = fixture("gardarsdottir-2019", "article-pdf")
    return textmatch.pdf_pages_text(path.read_bytes())


# --- the statements themselves ------------------------------------------------------------------------------------


def test_every_value_is_stated_by_its_words():
    reg = load_registry(Paths.default())
    for p in gp.PREMIUMS:
        assert p.source in reg.sources and any(a.id == p.artifact for a in reg.sources[p.source].artifacts)
        assert reg.sources[p.source].licence_class == "open"
        for s in p.statements:
            for v in s.values:
                assert v.words in s.quote, (p.id, v)
                assert gp._number_in(v.printed, v.words), (p.id, v)


def test_number_matching_needs_the_whole_number():
    assert gp._number_in("20", "about 20-145% higher")
    assert gp._number_in("145", "about 20-145% higher")
    assert not gp._number_in("14", "about 20-145% higher")
    assert not gp._number_in("45", "about 20-145% higher")
    assert not gp._number_in("93", "93.0")
    assert gp._number_in("93.0", "62.6 107.4 93.0 104.9")


def test_specs_are_discovered_with_their_inputs():
    ts = {t.spec.id: t for t in discover(Paths.default())}
    for pid, p in IDS.items():
        t = ts[pid]
        assert t.inputs == (p.input,) and t.spec.kind == "published-value"
        assert {d.id for d in t.spec.dimensions} == {k for k, _ in t.spec.headline_dims}
    assert ts["green-premium.iea-etp-2026.steel-usd"].spec.unit.code == "USD2024/t-crude-steel"
    assert ts["clinker-cost.cemcap-2019.by-technology"].spec.unit.code == "EUR2014/t-clinker"


# --- CEMCAP, on the fixture ---------------------------------------------------------------------------------------


def test_cemcap_statements_are_on_their_pages(cemcap_pages):
    assert len(cemcap_pages) == 21
    for pid in ("clinker-cost.cemcap-2019.by-technology", "green-premium.cemcap-2019.clinker"):
        gp.verify(cemcap_pages, IDS[pid])


def test_cemcap_values_are_table_6_as_printed():
    obs = gp.observations(IDS["clinker-cost.cemcap-2019.by-technology"])
    assert [o.value for o in obs] == [62.6, 107.4, 93.0, 104.9, 120.0, 105.8, 110.3]
    assert _by(obs, technology="reference").value == 62.6 and _by(obs, technology="oxyfuel").value == 93.0
    assert {(o.entity, o.period, o.status) for o in obs} == {("CEMCAP_REF", "2014", "final")}
    pct = gp.observations(IDS["green-premium.cemcap-2019.clinker"])
    assert (_by(pct, bound="low").value, _by(pct, bound="high").value) == (49.0, 92.0)


def test_a_misread_row_fails(cemcap_pages):
    p = IDS["clinker-cost.cemcap-2019.by-technology"]
    s = p.statements[0]
    swapped = (s.values[1], s.values[0], *s.values[2:])
    with pytest.raises(gp.GreenPremiumTextError, match="not the values in order"):
        gp.verify(cemcap_pages, replace(p, statements=(replace(s, values=swapped),)))


def test_a_number_not_in_the_text_fails(cemcap_pages):
    p = IDS["green-premium.cemcap-2019.clinker"]
    s = p.statements[0]
    wrong = (replace(s.values[0], printed="48"), s.values[1])
    with pytest.raises(gp.GreenPremiumTextError, match="is not stated by"):
        gp.verify(cemcap_pages, replace(p, statements=(replace(s, values=wrong),)))


def test_a_quote_on_the_wrong_page_fails(cemcap_pages):
    p = IDS["green-premium.cemcap-2019.clinker"]
    s = p.statements[0]
    moved = replace(s, parts=((9, s.parts[0][1]),))
    with pytest.raises(gp.GreenPremiumTextError, match="not found on PDF page 9"):
        gp.verify(cemcap_pages, replace(p, statements=(moved,)))


def test_a_range_must_run_low_to_high(cemcap_pages):
    p = IDS["green-premium.cemcap-2019.clinker"]
    s = p.statements[0]
    flipped = (replace(s.values[0], printed="92"), replace(s.values[1], printed="49"))
    with pytest.raises(gp.GreenPremiumTextError, match="above high end"):
        gp.verify(cemcap_pages, replace(p, statements=(replace(s, values=flipped),)))


def test_cemcap_runs_and_validates_on_the_fixture():
    path, meta = fixture("gardarsdottir-2019", "article-pdf")
    snap = snapshots.read_manifest(Paths.default(), meta["full_sha256"])
    assert snap is not None
    for pid in ("clinker-cost.cemcap-2019.by-technology", "green-premium.cemcap-2019.clinker"):
        t = next(t for t in gp.transforms(Paths.default()) if t.spec.id == pid)
        r = t.run({t.inputs[0].key: InputFile(path, snap)})
        validate(t, r.observations)
        assert r.published_value is not None and r.published_value.document == "gardarsdottir-2019"
        assert all(o.note and o.note.startswith(("Table 6", "Section 4.1")) for o in r.observations)


# --- IEA, on the snapshots ----------------------------------------------------------------------------------------


def _pages(source: str) -> list[str]:
    p = Paths.default()
    sha = snapshots.read_current(p)[f"{source}/report-pdf"]
    return textmatch.pdf_pages_text(snapshots.cache_path(p, sha).read_bytes())


@pytest.mark.snapshot
@pytest.mark.parametrize("source", [gp.ETP, gp.GHR, gp.EFUELS])
def test_iea_statements_are_on_their_pages(source):
    pages = _pages(source)
    for p in gp.PREMIUMS:
        if p.source == source:
            gp.verify(pages, p)


@pytest.mark.snapshot
def test_iea_values_as_printed():
    obs = gp.observations(IDS["green-premium.iea-etp-2026.steel"])
    assert [(o.dims["bound"], o.value) for o in obs] == [("low", 20.0), ("high", 145.0)]
    assert {(o.entity, o.period, o.status) for o in obs} == {("WLD", "2035", "projection")}
    usd = gp.observations(IDS["green-premium.iea-etp-2026.cement-usd"])
    assert [o.value for o in usd] == [50.0, 175.0]
    urea = gp.observations(IDS["green-premium.iea-etp-2026.urea"])
    assert (_by(urea, supply="domestic").value, _by(urea, supply="imported-ammonia").value) == (80.0, 55.0)
    nh3 = gp.observations(IDS["green-premium.iea-ghr-2025.ammonia"])
    assert _by(nh3, route="ccus", co2_cost="none").value == 25.0
    assert _by(nh3, route="electrolysis", co2_cost="usd-100", bound="high").value == 160.0
    meoh = gp.observations(IDS["green-premium.iea-ghr-2025.methanol"])
    assert {(o.entity, o.dims["route"], o.value) for o in meoh} == {
        ("IND", "electrolysis", 100.0),
        ("CHN", "ccus", 70.0),
        ("CHN", "electrolysis", 160.0),
    }
    (ship,) = gp.observations(IDS["green-premium.iea-efuels-2023.shipping"])
    assert (ship.value, ship.period) == (75.0, "2030")
