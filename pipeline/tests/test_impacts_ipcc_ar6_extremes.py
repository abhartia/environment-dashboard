"""IPCC AR6 WGI Figure SPM.6 and SPM.3 data on CEDA (envdash/transforms/impacts/ipcc_ar6_spm6.py and ipcc_ar6_spm3.py),
on whole-file fixtures of the real CEDA files (each a few hundred bytes to 5 KB, so nothing is sliced)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from envdash import snapshots, textmatch
from envdash.models import Snapshot
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transform import Input, InputFile, run_checks, validate
from envdash.transforms.impacts import ipcc_ar6_spm3 as spm3
from envdash.transforms.impacts import ipcc_ar6_spm6 as spm6

from support import fixture


def _file(i: Input) -> InputFile:
    path, meta = fixture(i.source_id, i.artifact_id)
    snap = Snapshot(
        sha256=meta["fixture_sha256"],
        bytes=meta["fixture_bytes"],
        source_id=i.source_id,
        artifact_id=i.artifact_id,
        url=meta["url"],
        date_accessed=date.fromisoformat(meta["date_accessed"]),
        acquisition="automatic",
    )
    return InputFile(path, snap)


def _files(t) -> dict[str, InputFile]:
    return {i.key: _file(i) for i in t.inputs}


def _transform(module):
    (t,) = module.transforms(Paths.default())
    return t


def _raw(i: Input) -> bytes:
    return fixture(i.source_id, i.artifact_id)[0].read_bytes()


# --- SPM.6: frequency by warming level -----------------------------------------------------------------------------


def _rows() -> dict[str, dict[str, spm6.Row]]:
    return {e.dim: {r.level: r for r in spm6.read_frequency(_raw(e.input), e.path)} for e in spm6.EXTREMES}


def test_spm6_frequency_files_read_as_printed():
    rows = _rows()
    # panel_a/TXx_freq_change_10_year_event.csv: "1.0,2.78,2.24,3.05,1.81,3.22," and "4.0,9.39,8.57,9.52,8.25,9.63,".
    r = rows["hot-10yr"]["1.0"]
    assert (r.p50, r.p17, r.p83, r.p05, r.p95) == tuple(Decimal(x) for x in ("2.78", "2.24", "3.05", "1.81", "3.22"))
    assert rows["hot-10yr"]["4.0"].p50 == Decimal("9.39")
    # panel_b 50-year event at 4 °C, panel_c rain at 1 °C, panel_d drought at 1 °C (no trailing comma in that file).
    assert (rows["hot-50yr"]["4.0"].p50, rows["hot-50yr"]["4.0"].p05) == (Decimal("39.19"), Decimal("27.03"))
    assert (rows["rain-10yr"]["1.0"].p50, rows["rain-10yr"]["1.0"].p95) == (Decimal("1.32"), Decimal("1.42"))
    d = rows["drought-10yr"]["1.0"]
    assert (d.p50, d.p05, d.p95) == (Decimal("1.70"), Decimal("0.68"), Decimal("4.08"))
    assert all(list(v) == [lv for lv, _ in spm6.LEVELS] for v in rows.values())


def test_spm6_header_levels_and_percentile_order_are_checked():
    raw = _raw(spm6.EXTREMES[0].input)
    with pytest.raises(spm6.Spm6FormatError, match="header"):
        spm6.read_frequency(raw.replace(b"83th", b"83rd"), "x")
    no_3c = b"".join(ln for ln in raw.splitlines(keepends=True) if not ln.startswith(b"3.0,"))
    with pytest.raises(spm6.Spm6FormatError, match="warming levels"):
        spm6.read_frequency(no_3c, "x")
    # The real 1 °C row with its 5th and 95th percentiles swapped.
    with pytest.raises(spm6.Spm6FormatError, match="out of order"):
        spm6.read_frequency(raw.replace(b"1.0,2.78,2.24,3.05,1.81,3.22", b"1.0,2.78,2.24,3.05,3.22,1.81"), "x")


def test_spm6_metadata_lists_17_drying_regions_and_leaves_out_the_caribbean():
    raw = _raw(spm6.METADATA)
    regions = spm6.check_metadata(raw)
    assert len(regions) == 17 and "Caribbean" in regions and "Mediterranean" in regions
    with pytest.raises(spm6.Spm6FormatError, match="16 drying regions"):
        spm6.check_metadata(raw.replace(b"Madagascar, ", b""))
    with pytest.raises(spm6.Spm6FormatError, match="does not list"):
        spm6.check_metadata(raw.replace(b"panel_d/drought_freq", b"panel_c/drought_freq"))
    with pytest.raises(spm6.Spm6FormatError, match="base periods"):
        spm6.check_metadata(raw.replace(b"1851-1900 for hot extremes", b"1850-1900 for hot extremes"))


def test_spm6_caption_must_leave_out_3c_for_the_label_to_say_so():
    raw = _raw(spm6.METADATA)
    shown = "global warming levels of 1°C, 1.5°C, 2°C, and 4°C".encode()
    assert shown in raw
    with pytest.raises(spm6.Spm6FormatError, match="no longer shows exactly the levels"):
        spm6.check_metadata(raw.replace(shown, "global warming levels of 1°C, 1.5°C, 2°C, 3°C, and 4°C".encode()))
    with pytest.raises(spm6.Spm6FormatError, match="no longer shows exactly the levels"):
        spm6.check_metadata(raw.replace(shown, "global warming levels of 1°C, 2°C, and 4°C".encode()))
    assert "not in the published figure" in dict(spm6.LEVELS)[spm6.NOT_IN_FIGURE]


def test_spm6_printed_ranges_are_the_5th_and_95th_percentiles():
    rows = _rows()
    spm6.check_printed_ranges(rows)
    # Drawing the 17th-83rd percentiles as the range instead would not match the figure.
    likely = {
        e: {lv: spm6.Row(r.level, r.p50, r.p17, r.p83, r.p17, r.p83) for lv, r in v.items()} for e, v in rows.items()
    }
    with pytest.raises(spm6.Spm6FormatError, match="the figure prints the range"):
        spm6.check_printed_ranges(likely)
    assert spm6.read_printed("Once now likely occurs 2.8 times (1.8–3.2)") == ("2.8", Decimal("1.8"), Decimal("3.2"))
    assert {(p.extreme, p.level) for p in spm6.PRINTED} == {
        (e.dim, lv) for e in spm6.EXTREMES for lv, _ in spm6.LEVELS if lv != spm6.NOT_IN_FIGURE
    }


def test_spm6_transform_on_the_files_and_its_publisher_checks():
    t = _transform(spm6)
    result = t.run(_files(t))
    validate(t, result.observations)
    assert result.vintage == "v20210809" and result.date_published == "2021-08-09"
    obs = {(o.dims["extreme"], o.dims["level"]): o for o in result.observations}
    assert len(obs) == 20
    head = obs[("hot-10yr", "1.0")]
    assert (head.period, head.value, head.lower, head.upper, head.interval, head.status) == (
        "2021",
        2.78,
        1.81,
        3.22,
        "very-likely",
        "projection",
    )
    assert obs[("drought-10yr", "4.0")].value == 4.08
    # No note of ours on any value: the 3.0 °C label says it is not in the figure, grounded in the caption.
    assert not any(o.note for o in obs.values())
    assert "17 drying regions" in result.steps[2] and "cover 16" in result.steps[2]
    outcomes = run_checks(t, {spm6.SOURCE: result.vintage}, result.observations)
    assert len(outcomes) == 16
    assert all(o.status == "pass" for o in outcomes), [o.detail for o in outcomes if o.status != "pass"]


def test_spm6_files_must_be_the_panels_they_claim():
    t = _transform(spm6)
    files = _files(t)
    a, b = spm6.EXTREMES[2].input.key, spm6.EXTREMES[3].input.key
    files[a], files[b] = files[b], files[a]
    with pytest.raises(spm6.Spm6FormatError, match="not panel_c/Rx1day"):
        t.run(files)


def test_spm6_spec_says_modelled_and_not_today():
    t = _transform(spm6)
    s = t.spec
    assert s.id == "extremes.ipcc-ar6.frequency-by-warming-level" and s.kind == "series"
    assert "modelled" in s.title and "Modelled" in s.description
    assert "not today's warming" in s.description and "not counts of observed events" in s.description
    assert "3 °C level is in the data but not in the published figure" in s.description
    assert "lists 17" in s.scope.geography and "so 16" in s.scope.geography
    # web/src/lib/dash/people-tree.ts writes "Times as often as in <baseline>, by level of warming".
    assert s.scope.baseline == "1851–1900 (heat and rain) or 1850–1900 (drought)"
    assert s.unit.label == "times as often as in the second half of the 19th century"
    assert s.headline_dims == (("extreme", "hot-10yr"), ("level", "1.0"))
    assert [v.id for v in spm6.LEVEL_DIM.values] == ["1.0", "1.5", "2.0", "3.0", "4.0"]
    # Intensity files are registered but not read this round.
    assert {i.artifact_id for i in t.inputs} == {e.input.artifact_id for e in spm6.EXTREMES} | {"metadata"}


# --- SPM.3: observed change by region ------------------------------------------------------------------------------


def _panels() -> dict[str, spm3.PanelData]:
    return {p.dim: spm3.read_badc(_raw(p.input), p.file) for p in spm3.PANELS}


def test_spm3_reads_45_regions_per_panel():
    panels = _panels()
    for d in panels.values():
        assert len(d.rows) == 45 and set(d.rows) == d.listed and d.span == ("1950", "2021")
    hot = panels["hot"].rows
    # SPM3_panel_a.csv: "NWN,Increase,High", "CNA,Low agreement in type of change,...", "NZ,Increase,Low due to ...".
    assert hot["NWN"] == ("increase", "high")
    assert hot["CNA"] == ("low-agreement", "low-agreement")
    assert hot["NZ"] == ("increase", "low-agreement")
    assert hot["SSA"] == ("limited-data", "low-evidence")
    assert panels["drought"].rows["NAU"] == ("decrease", "low-agreement")
    assert "Low agreement in type of change" in panels["hot"].labels
    assert "Low agreement in the type of change" in panels["heavy-rain"].labels


def test_spm3_counts_match_the_figure_and_split_the_increases():
    panels = _panels()
    keys = [d for d, _, _ in spm3.ASSESSMENTS]
    got = {p: [spm3.counts(panels[p])[k] for k in keys] for p in panels}
    # increase, increase-high, increase-medium, increase-low, decrease, low-agreement, limited-data
    assert got == {
        "hot": [41, 23, 16, 2, 0, 2, 2],
        "heavy-rain": [19, 1, 1, 17, 0, 8, 18],
        "drought": [12, 0, 2, 10, 1, 28, 4],
    }


def test_spm3_transform_on_the_files_and_its_publisher_checks():
    t = _transform(spm3)
    result = t.run(_files(t))
    validate(t, result.observations)
    assert result.vintage == "v20221116" and result.changes
    assert {o.period for o in result.observations} == {"1950/2021"}
    by = {(o.dims["extreme"], o.dims["assessment"]): o.value for o in result.observations}
    assert by[("hot", "increase")] == 41.0 and by[("drought", "decrease")] == 1.0
    assert "NAU (Low due to limited agreement)" in result.steps[2]
    outcomes = run_checks(t, {spm3.SOURCE: result.vintage}, result.observations)
    assert len(outcomes) == 12
    assert all(o.status == "pass" for o in outcomes), [o.detail for o in outcomes if o.status != "pass"]


def test_spm3_unexpected_pairings_labels_and_spans_stop_the_build(tmp_path):
    raw = _raw(spm3.PANELS[0].input)
    with pytest.raises(spm3.Spm3FormatError, match="pairs 'Increase' with 'Low due to limited evidence'"):
        spm3.read_badc(raw.replace(b"NWN,Increase,High", b"NWN,Increase,Low due to limited evidence"), "x")
    with pytest.raises(spm3.Spm3FormatError, match="unknown categories"):
        spm3.read_badc(raw.replace(b"NWN,Increase,High", b"NWN,Increased,High"), "x")
    with pytest.raises(spm3.Spm3FormatError, match="appears twice"):
        spm3.read_badc(raw.replace(b"NEN,Increase,High", b"NWN,Increase,High"), "x")
    # The real panel b with its span changed: it reads on its own, but no longer matches panels a and c.
    t = _transform(spm3)
    files = _files(t)
    b = spm3.PANELS[1].input.key
    shifted = files[b].path.read_bytes().replace(b"years 1950 to 2021", b"years 1950 to 2020")
    assert spm3.read_badc(shifted, "x").span == ("1950", "2020")
    path = tmp_path / spm3.PANELS[1].file
    path.write_bytes(shifted)
    files[b] = InputFile(path, files[b].snapshot)
    with pytest.raises(spm3.Spm3FormatError, match="differ in span"):
        spm3.read_panels(files)
    # All three changed alike: they agree, but no longer with the span the words state.
    for p in spm3.PANELS:
        k = p.input.key
        path = tmp_path / f"all-{p.file}"
        path.write_bytes(_raw(p.input).replace(b"years 1950 to 2021", b"years 1950 to 2023"))
        files[k] = InputFile(path, files[k].snapshot)
    with pytest.raises(spm3.Spm3FormatError, match="but the words say"):
        spm3.read_panels(files)


def test_spm3_printed_tallies_parse():
    assert spm3.read_printed(spm3.PANELS[2].printed) == {
        "increase": 12,
        "decrease": 1,
        "low-agreement": 28,
        "limited-data": 4,
    }
    with pytest.raises(spm3.Spm3FormatError, match="one tally"):
        spm3.read_printed("Increase (41) Decrease (0)")


def test_spm3_spec_is_derived_counts_of_regions():
    s = _transform(spm3).spec
    assert s.id == "extremes.ipcc-ar6.observed-regions" and s.kind == "derived"
    assert s.unit.code == "regions" and s.display.decimals == 0
    assert "Calculated by counting" in s.description and "not that nothing changed" in s.description
    assert s.headline_dims == (("extreme", "hot"), ("assessment", "increase"))
    # web/src/lib/dash/people-tree.ts writes "of the world's <geography> saw ... increase".
    assert s.scope.geography == "45 inhabited IPCC AR6 regions"
    assert s.unit.label == "of the 45 inhabited IPCC AR6 regions"
    assert "1950s to 2021" in s.description and "years 1950 to 2021" in (s.scope.basis or "")
    assert {c.period for c in _transform(spm3).checks} == {"1950/2021"}


# --- registry ------------------------------------------------------------------------------------------------------


def test_every_input_is_a_registered_artifact_of_an_open_source():
    reg = load_registry(Paths.default())
    for module in (spm6, spm3):
        t = _transform(module)
        src = reg.sources[module.SOURCE]
        assert src.licence_class == "open" and src.obligations.mirror_raw
        assert {i.artifact_id for i in t.inputs} <= {a.id for a in src.artifacts}


# --- full files and the published figures (local snapshot cache) --------------------------------------------------


def _current(i: Input) -> InputFile:
    paths = Paths.default()
    snap = snapshots.read_manifest(paths, snapshots.read_current(paths)[i.key])
    assert snap is not None
    return InputFile(snapshots.cache_path(paths, snap.sha256), snap)


@pytest.mark.snapshot
def test_printed_labels_are_on_the_spm_pages():
    # The same test as verify_quote, with the PDF's text extracted once for all nineteen labels.
    pages = textmatch.pdf_pages_text(_current(Input("ipcc-ar6-wg1-spm", "spm-pdf")).path.read_bytes())
    for p in spm6.PRINTED:
        assert textmatch.contains(pages[spm6.SPM_PAGE - 1], p.quote), p.quote
    for panel in spm3.PANELS:
        assert textmatch.contains(pages[spm3.SPM_PAGE - 1], panel.printed), panel.printed
    assert not textmatch.contains(pages[spm6.SPM_PAGE - 1], spm6.PRINTED[0].quote.replace("2.8", "2.9"))
    assert not textmatch.contains(pages[spm3.SPM_PAGE - 1], spm3.PANELS[0].printed.replace("(41)", "(39)"))


@pytest.mark.snapshot
def test_full_transforms_on_the_snapshots():
    for module, rows in ((spm6, 20), (spm3, 21)):
        t = _transform(module)
        result = t.run({i.key: _current(i) for i in t.inputs})
        validate(t, result.observations)
        assert len(result.observations) == rows
        assert all(o.status == "pass" for o in run_checks(t, {module.SOURCE: result.vintage}, result.observations))
