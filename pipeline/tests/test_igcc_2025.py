"""IGCC 2025 transforms (envdash/transforms/climate/igcc_2025.py), on byte-exact slices of the IGCC-2025a files."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from envdash import snapshots
from envdash.models import Observation
from envdash.paths import Paths
from envdash.transform import InputFile, run_checks
from envdash.transforms.climate import igcc_2025 as igcc
from envdash.transforms.literature import verify_quote

FIXTURES = Path(__file__).parent / "fixtures"
RELEASE = igcc.RELEASES["IGCC-2025a"]


def fixture(source_id: str, artifact_id: str) -> tuple[Path, dict]:
    """The fixture file cut from (source, artifact) and its provenance sidecar (copied from tests/support.py)."""
    for side in sorted(FIXTURES.glob(f"{source_id}/*.provenance.json")):
        meta = json.loads(side.read_text())
        if meta["artifact_id"] == artifact_id:
            return side.with_name(side.name.removesuffix(".provenance.json")), meta
    raise LookupError(f"no fixture for {source_id}/{artifact_id}")


def raw(artifact_id: str) -> bytes:
    return fixture(igcc.SOURCE, artifact_id)[0].read_bytes()


def methods() -> list[tuple[bytes, str]]:
    return [(raw(i.artifact_id), i.artifact_id) for i in igcc.METHODS]


def transform(indicator_id: str):
    return next(t for t in igcc.transforms(Paths.default()) if t.spec.id == indicator_id)


# --- human-induced warming -----------------------------------------------------------------------------------------


def test_assessment_rule_reproduces_the_producers_rows():
    assessed = igcc.assess(methods())
    producer = igcc.producer_assessment(raw(igcc.HEADLINES.artifact_id))
    # The annual-mean rows of Assessment-Update-2025_GMST_headlines.csv (the "SR15 definition" rows are left out).
    assert producer == {
        "2017": (Decimal("0.9"), Decimal("1.14"), Decimal("1.4")),
        "2025": (Decimal("1.1"), Decimal("1.38"), Decimal("1.7")),
    }
    igcc.check_against_producer(assessed, producer)
    by = {a.period: a for a in assessed}
    assert (by["2025"].best, by["2025"].lower, by["2025"].upper) == (Decimal("1.38"), Decimal("1.1"), Decimal("1.7"))


def test_rule_on_early_and_recent_years():
    by = {a.period: a for a in igcc.assess(methods())}
    # The fixture keeps 1850-1852 and 2016-2025 of each method file.
    assert sorted(by) == ["1850", "1851", "1852", *[str(y) for y in range(2016, 2026)]]
    for a in by.values():
        assert a.lower <= a.best <= a.upper
        assert a.lower == a.lower.quantize(Decimal("0.1")) and a.upper == a.upper.quantize(Decimal("0.1"))
        assert a.best == a.best.quantize(Decimal("0.01"))
    assert (by["2024"].best, by["2024"].lower, by["2024"].upper) == (Decimal("1.36"), Decimal("1.1"), Decimal("1.8"))


def test_rule_with_two_methods_does_not_match_the_producer():
    # Leaving out one of the three methods changes the 2025 best estimate, which the producer check catches.
    two = methods()[:2]
    with pytest.raises(igcc.IgccFormatError, match="IGCC published"):
        igcc.check_against_producer(igcc.assess(two), igcc.producer_assessment(raw(igcc.HEADLINES.artifact_id)))


def test_method_files_must_cover_the_same_years():
    ms = methods()
    walsh = b"".join(ln for ln in ms[0][0].splitlines(keepends=True) if not ln.startswith(b"2020.5,"))
    with pytest.raises(igcc.IgccFormatError, match="covers years"):
        igcc.assess([(walsh, ms[0][1]), *ms[1:]])


def test_warming_publisher_check_quotes_the_file_row_and_passes():
    t = transform("warming.igcc-2025.human-induced")
    (check,) = t.checks
    assert check.quote.encode() + b"\n" in raw(igcc.HEADLINES.artifact_id)
    obs = [Observation(entity="WLD", period=a.period, value=float(a.best)) for a in igcc.assess(methods())]
    (outcome,) = run_checks(t, {igcc.SOURCE: "IGCC-2025a"}, obs)
    assert outcome.status == "pass"


# --- effective radiative forcing -----------------------------------------------------------------------------------


def _erf():
    return igcc.erf_by_agent(*(raw(i.artifact_id) for i in (igcc.ERF_BEST, igcc.ERF_P05, igcc.ERF_P95)))


def test_erf_by_agent_values_and_range():
    obs = _erf()
    assert len(obs) == 6 * len(igcc.AGENTS)
    by = {(o.period, o.dims["agent"]): o for o in obs}
    anthro = by[("2025", "anthropogenic")]
    assert (anthro.value, anthro.lower, anthro.upper, anthro.interval) == (
        3.103548614,
        2.346036019,
        3.834738326,
        "90ci",
    )
    assert by[("2025", "aerosol")].value == -0.961805093
    assert by[("2025", "co2")].value == 2.370924636
    assert by[("1750", "co2")].value == 0.0 and by[("1750", "volcanic")].value == 0.234943996
    assert {o.dims["agent"] for o in obs} == {d.id for d in igcc.AGENT_DIM.values}


def test_erf_publisher_checks_pass_on_the_real_values():
    t = transform("forcing.igcc-2025.erf-by-agent")
    outcomes = run_checks(t, {igcc.SOURCE: "IGCC-2025a"}, _erf())
    assert len(outcomes) == 10
    assert all(o.status == "pass" for o in outcomes), [o.detail for o in outcomes if o.status != "pass"]


def test_erf_column_meanings_are_checked_by_their_sums():
    # Same header, but the real "aerosol" and "anthro" values swapped in every row: a release whose columns meant
    # something else under the same names would look like this, and the header check alone would not see it.
    lines = raw(igcc.ERF_BEST.artifact_id).splitlines(keepends=True)
    cols = lines[0].decode().rstrip("\n").split(",")
    a, b = cols.index("aerosol"), cols.index("anthro")
    out = [lines[0]]
    for ln in lines[1:]:
        cells = ln.decode().rstrip("\n").split(",")
        cells[a], cells[b] = cells[b], cells[a]
        out.append((",".join(cells) + "\n").encode())
    with pytest.raises(igcc.IgccFormatError, match="is not the sum"):
        igcc.erf_by_agent(b"".join(out), raw(igcc.ERF_P05.artifact_id), raw(igcc.ERF_P95.artifact_id))


# --- remaining carbon budget ---------------------------------------------------------------------------------------


def test_budget_file_value_and_cross_check():
    path, meta = fixture(igcc.SOURCE, igcc.RCB.artifact_id)
    v = igcc.budget_from_file(path.read_bytes(), meta["url"])
    assert v == Decimal("134.22273736520202")
    igcc.cross_check_budget(v, Decimal(130))
    with pytest.raises(igcc.IgccFormatError, match="not describe the same estimate"):
        igcc.cross_check_budget(v, Decimal(140))


def test_budget_file_must_carry_table_8_assumptions():
    path, meta = fixture(igcc.SOURCE, igcc.RCB.artifact_id)
    with pytest.raises(igcc.IgccFormatError, match="Table 8 assumptions"):
        igcc.budget_from_file(path.read_bytes(), meta["url"].replace("hdT_1.24", "hdT_1.26"))


def test_budget_is_labelled_from_the_start_of_2026():
    t = transform("budget.igcc-2025.remaining-1p5")
    assert t.spec.kind == "published-value"
    assert "from the start of 2026" in t.spec.title and "from the start of 2026" in t.spec.description
    (o,) = igcc.BUDGET.observations
    assert (o.period, o.value) == ("2026-01-01", 130.0)
    assert igcc.BUDGET.value_text in igcc.BUDGET.quote


# --- release -------------------------------------------------------------------------------------------------------


def test_zip_member_and_release():
    _, meta = fixture(igcc.SOURCE, igcc.ERF_BEST.artifact_id)
    assert (
        igcc.zip_member(meta["url"], RELEASE)
        == "ClimateIndicator-data-0f2765d/data/base/effective_radiative_forcing/ERF_best_aggregates.csv"
    )
    with pytest.raises(igcc.IgccFormatError, match="not the release commit"):
        igcc.zip_member(meta["url"].replace(RELEASE.commit, "f" * 40), RELEASE)
    zip_url = next(str(a.url) for a in _registry_artifacts() if a.id == igcc.ZIP.artifact_id)
    assert igcc.release_of(zip_url) == ("IGCC-2025a", RELEASE)
    with pytest.raises(igcc.IgccFormatError, match="not in RELEASES"):
        igcc.release_of(zip_url.replace("IGCC-2025a", "IGCC-2026a"))


def _registry_artifacts():
    from envdash.registry import load_registry

    return load_registry(Paths.default()).sources[igcc.SOURCE].artifacts


def test_every_input_is_a_registered_artifact():
    ids = {a.id for a in _registry_artifacts()}
    for t in igcc.transforms(Paths.default()):
        assert {i.artifact_id for i in t.inputs} <= ids, t.spec.id


# --- full files (local snapshot cache) -----------------------------------------------------------------------------


def _current_files() -> dict[str, InputFile]:
    paths = Paths.default()
    current = snapshots.read_current(paths)
    out: dict[str, InputFile] = {}
    for a in _registry_artifacts():
        k = snapshots.key(igcc.SOURCE, a.id)
        snap = snapshots.read_manifest(paths, current[k])
        assert snap is not None
        out[k] = InputFile(snapshots.cache_path(paths, snap.sha256), snap)
    return out


@pytest.mark.snapshot
def test_quotes_are_in_the_paper():
    pdf = _current_files()[igcc.PAPER.key].path.read_bytes()
    verify_quote(pdf, igcc.BUDGET.pdf_page, igcc.BUDGET.quote)
    verify_quote(pdf, igcc.RCB_PAGE, igcc.RCB_CAPTION)
    for c in igcc.ERF_CHECKS:
        verify_quote(pdf, 11, c.quote)


@pytest.mark.snapshot
def test_full_transforms_on_the_snapshots():
    files = _current_files()
    for t in igcc.transforms(Paths.default()):
        result = t.run({i.key: files[i.key] for i in t.inputs})
        assert result.vintage == "IGCC-2025a"
        if t.spec.id == "warming.igcc-2025.human-induced":
            assert len(result.observations) == 176
        if t.spec.id == "forcing.igcc-2025.erf-by-agent":
            assert len(result.observations) == 276 * len(igcc.AGENTS)
