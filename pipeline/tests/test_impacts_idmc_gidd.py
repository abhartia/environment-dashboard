"""IDMC GIDD weather-related displacement by hazard (envdash/transforms/impacts/idmc_gidd.py).

No fixture: idmc-gidd is noncommercial (CC BY-NC-SA 3.0 IGO), so no slice of the event export is committed. The tests
that read it use the file the owner downloaded on 2026-10-12 and recorded with envdash snapshot add, from the
snapshot cache, and are marked `snapshot` (run with `uv run pytest -m snapshot`); the others check the registry, the
recorded manifest and the module's declarations. Refusals are tested on real rows of that file with one cell edited.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, run_checks, validate
from envdash.transforms.impacts import idmc_gidd as gidd

OWNERS_FILE = "25c78f150cffef0fac7b2c860d07738cf4a52da9bfe1bb1cc6a976c41ad0d2d3"
NINE_TYPES = [
    "Flood",
    "Storm",
    "Wildfire",
    "Mass Movement",
    "Drought",
    "Erosion",
    "Extreme Temperature",
    "Wave action",
    "Sea level Rise",
]


# --- no raw data needed -------------------------------------------------------------------------------------------


def test_registry_entry_keeps_the_noncommercial_share_alike_terms():
    src = load_registry(Paths.default()).sources[gidd.SOURCE]
    assert src.licence_class == "noncommercial" and src.acquisition == "manual"
    assert src.licence.spdx == "CC-BY-NC-SA-3.0-IGO"
    assert src.obligations.no_logo and src.obligations.no_endorsement
    assert "shared under the same licence" in (src.obligations.notice or "")
    assert src.evidence.checked_on == date(2026, 10, 12)
    art = next(a for a in src.artifacts if a.id == gidd.EVENTS.artifact_id)
    assert art.format == "xlsx"
    assert "sets Cause to Disaster" in art.description and "no button" not in art.description


def test_current_snapshot_is_the_owners_download():
    p = Paths.default()
    assert snapshots.read_current(p)[gidd.EVENTS.key] == OWNERS_FILE
    snap = snapshots.read_manifest(p, OWNERS_FILE)
    assert snap is not None
    assert (snap.acquisition, snap.bytes, snap.date_accessed) == ("manual", 2_968_931, date(2026, 10, 12))
    assert "Cause: Disaster, Excel" in (snap.note or "")


def test_hazards_are_idmcs_nine_weather_related_types():
    assert gidd.WEATHER == "Weather related"
    assert [t for t, *_ in gidd.HAZARDS] == NINE_TYPES
    ids = [h for _, h, _, _ in gidd.HAZARDS]
    assert len(set(ids)) == len(ids) and gidd.ALL[0] not in ids
    assert set(gidd.OTHER_CATEGORIES) == {"Geophysical", "Mixed disasters"}
    assert "Earthquake" in gidd.OTHER_CATEGORIES["Geophysical"]
    # Mass Movement is a type in both categories; only the weather-related one (wet mass movement) is summed.
    subs = {t: s for t, _, _, s in gidd.HAZARDS}
    assert subs["Mass Movement"] == {"Landslide/Wet mass movement", "Avalanche"}
    assert subs["Extreme Temperature"] == {"Cold wave", "Heat wave"}


def test_spec_is_one_derived_world_series_with_no_publisher_check():
    (t,) = gidd.transforms(Paths.default())
    s = t.spec
    assert s.id == gidd.INDICATOR == "displacement.idmc-gidd.weather-by-hazard"
    assert s.kind == "derived" and s.unit.code == "displacements" and "estimated" in s.title
    assert (s.headline_entity, s.geo_coverage, s.headline_dims) == ("WLD", "global-only", (("hazard", "all"),))
    assert [v.id for v in s.dimensions[0].values] == ["all", *(h for _, h, _, _ in gidd.HAZARDS)]
    assert [i.key for i in t.inputs] == ["idmc-gidd/gidd-disaster-events"]
    assert t.checks == ()
    for phrase in (
        "movements, not people",
        "pre-emptive evacuations are included",
        "not evidence that disasters are becoming more frequent",
        "not attributed to climate change",
        "1,044 weather-related event rows for 2008 and 7,064 for 2025",
        "701 weather-related event rows in this release have no reported figure",
        "For 2008 and 2010–2016, IDMC gives China's displacement as one figure a year that is not split by hazard",
        "Global Report on Internal Displacement are built differently",
    ):
        assert phrase in s.description, phrase


# --- the owner's download (snapshot cache) ------------------------------------------------------------------------


def _file() -> InputFile:
    p = Paths.default()
    snap = snapshots.read_manifest(p, snapshots.read_current(p)[gidd.EVENTS.key])
    assert snap is not None
    return InputFile(snapshots.cache_path(p, snap.sha256), snap)


@pytest.fixture(scope="module")
def sheets() -> tuple[list[str], tuple, list[tuple]]:
    lines, header, rows = gidd.read_sheets(_file().path.read_bytes())
    return lines, header, list(rows)


@pytest.mark.snapshot
def test_builds_from_the_owners_file():
    (t,) = gidd.transforms(Paths.default())
    r = t.run({gidd.EVENTS.key: _file()})
    validate(t, r.observations)
    assert run_checks(t, {gidd.SOURCE: r.vintage}, r.observations) == []
    assert r.vintage == "GIDD disaster export, last update 2026-08-31" and r.date_published == "2026-08-31"
    got = {(o.period, o.dims["hazard"]): o for o in r.observations}
    assert {p for p, _ in got} == {str(y) for y in range(2008, 2026)}
    # Weather-related raw sums for the world.
    assert got[("2008", "all")].value == 29_709_695
    assert got[("2024", "all")].value == 45_509_095
    assert got[("2025", "all")].value == 26_933_321
    assert got[("2010", "flood")].value == 33_251_287
    assert got[("2024", "storm")].value == 25_785_689
    assert got[("2025", "storm")].value == 18_003_987
    assert got[("2025", "wildfire")].value == 694_094
    assert got[("2017", "drought")].value == 1_278_832
    # Each year's total is the sum of its types.
    for y in range(2008, 2026):
        parts = sum(o.value for (p, h), o in got.items() if p == str(y) and h != "all" and o.value is not None)
        assert parts == got[(str(y), "all")].value
    # A type with no row in a year has no value; rows without a figure are counted in a note, never as zero.
    assert ("2009", "sea-level-rise") not in got and ("2025", "wave-action") not in got
    assert got[("2017", "all")].note is None
    assert got[("2008", "all")].note == (
        "Also not in this sum: 26,822,000 displacements in 1 row IDMC files for 2008 under 'Mixed disasters', not "
        "assigned to one hazard (the largest: China, 26,822,000)."
    )
    assert got[("2021", "all")].note == (
        "368 of the 1,544 weather-related event rows IDMC lists for 2021 have no reported figure and are not in this "
        "sum."
    )
    assert got[("2009", "flood")].note == (
        "1 of the 276 flood event rows IDMC lists for 2009 has no reported figure and is not in this sum."
    )
    assert all(o.value is not None and o.status == "final" for o in r.observations)
    assert "701 weather-related rows with no reported figure" in r.steps[3]


@pytest.mark.snapshot
def test_geophysical_and_mixed_rows_are_left_out(sheets):
    lines, header, rows = sheets
    readme = gidd.read_readme(lines)
    assert (readme.last_update, readme.extracted) == (date(2026, 8, 31), date(2026, 10, 5))
    events = gidd.parse_events(header, rows, readme)
    assert len(events) == 44_335
    by: dict[tuple[int, str], int] = defaultdict(int)
    for e in events:
        if e.raw is not None:
            by[(e.year, e.category)] += e.raw
    obs = {(o.period, o.dims["hazard"]): o.value for o in gidd.observations(gidd.tally(events))}
    for y in (2008, 2010, 2023, 2025):
        assert by[(y, "Geophysical")] > 0
        assert obs[(str(y), "all")] == by[(y, "Weather related")]
        assert obs[(str(y), "all")] < by[(y, "Weather related")] + by[(y, "Geophysical")] + by[(y, "Mixed disasters")]
    # 2008: all disasters add up to 56,727,649, of which 26,822,000 is China's one 'Mixed disasters' row and 195,954
    # is geophysical; 29,709,695 is weather-related.
    assert sum(v for (y, _), v in by.items() if y == 2008) == 56_727_649
    assert (by[(2008, "Mixed disasters")], by[(2008, "Geophysical")]) == (26_822_000, 195_954)
    # Geophysical (dry) mass movement is not in the weather-related mass movement series.
    geo_mm = [e.raw for e in events if (e.year, e.category, e.hazard_type) == (2014, "Geophysical", "Mass Movement")]
    assert sum(v for v in geo_mm if v is not None) > 0 and obs[("2014", "mass-movement")] == 170_433


def _edited(rows: list[tuple], header: tuple, match, column: str, value) -> list[tuple]:
    """A copy of the real rows with one cell changed: `column` of the first row that `match` accepts."""
    i = header.index(column)
    n = next(k for k, r in enumerate(rows) if match(r))
    out = list(rows)
    out[n] = (*rows[n][:i], value, *rows[n][i + 1 :])
    return out


@pytest.mark.snapshot
def test_a_changed_vocabulary_or_figure_stops_the_build(sheets):
    lines, header, rows = sheets
    readme = gidd.read_readme(lines)
    col = {c: i for i, c in enumerate(header)}

    def weather(r):
        return r[col["Hazard Category"]] == "Weather related" and r[col["Disaster Internal Displacements (Raw)"]]

    cases = [
        ((*header[:-1], "Displacement Occurred"), rows, "columns"),
        (header, _edited(rows, header, weather, "Hazard Category", "Weather-related"), "Hazard Category"),
        (header, _edited(rows, header, weather, "Hazard Type", "Glacial lake outburst"), "Hazard Type"),
        (header, _edited(rows, header, weather, "Hazard Sub Type", "Heat dome"), "Sub Type"),
        (header, _edited(rows, header, weather, "Disaster Internal Displacements (Raw)", None), "present together"),
        (header, _edited(rows, header, weather, "Disaster Internal Displacements (Raw)", -5), "non-negative"),
        (header, _edited(rows, header, weather, "Year", 2026), "outside 2008–2025"),
    ]
    for h, rs, message in cases:
        with pytest.raises(gidd.IdmcFormatError, match=message):
            gidd.parse_events(h, rs, readme)


@pytest.mark.snapshot
def test_the_description_counts_and_licence_line_are_checked(sheets):
    lines, header, rows = sheets
    readme = gidd.read_readme(lines)
    events = gidd.parse_events(header, rows, readme)
    gidd.check_stated(gidd.tally(events))
    no_figure = next(k for k, e in enumerate(events) if e.category == gidd.WEATHER and e.raw is None)
    with pytest.raises(gidd.IdmcFormatError, match="700 weather-related rows have no figure, not 701"):
        gidd.check_stated(gidd.tally(events[:no_figure] + events[no_figure + 1 :]))
    first_2025 = next(k for k, e in enumerate(events) if e.category == gidd.WEATHER and e.year == 2025)
    with pytest.raises(gidd.IdmcFormatError, match="2025 has 7063 weather-related rows, not 7064"):
        gidd.check_stated(gidd.tally(events[:first_2025] + events[first_2025 + 1 :]))
    china_2008 = next(k for k, e in enumerate(events) if (e.iso3, e.year, e.category) == ("CHN", 2008, gidd.MIXED))
    with pytest.raises(gidd.IdmcFormatError, match="China's 'Mixed disasters' rows with a figure are in"):
        gidd.check_stated(gidd.tally(events[:china_2008] + events[china_2008 + 1 :]))
    licence = next(k for k, line in enumerate(lines) if line.startswith(gidd.LICENCE_LINE))
    changed = [*lines[:licence], "USE LICENSE: This content is licensed under CC BY-NC-ND.", *lines[licence + 1 :]]
    with pytest.raises(gidd.IdmcFormatError, match="licence statement changed"):
        gidd.read_readme(changed)
