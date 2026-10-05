"""HOT Station ALOHA surface pH and pCO2 transforms (envdash/transforms/ocean/hot_aloha_co2.py).

Fixture (tests/fixtures/hot-aloha/, with its .provenance.json sidecar): the whole HOT_surface_CO2.txt as fetched on
2026-10-05 (last updated 1 January 2026, cruises 1-355). The readme PDF (573,080 bytes) is too large for a committed
whole-file fixture and a PDF cannot be cut by lines, so the readme checks read the real snapshot from the cache and
are marked `snapshot` (run with `uv run pytest -m snapshot`).
"""

from __future__ import annotations

from datetime import date

import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, validate
from envdash.transforms.ocean import hot_aloha_co2 as hot
from envdash.transforms.ocean.hot_aloha_co2 import HotFormatError, check_readme, last_updated, read_cruises, series

from support import fixture

SOURCE = "hot-aloha"
IDS = {"ph.hot-aloha.surface-insitu": "pHcalc_insitu", "pco2.hot-aloha.surface-insitu": "pCO2calc_insitu"}


def _raw() -> str:
    path, _ = fixture(SOURCE, "hot-surface-co2")
    return path.read_bytes().decode("utf-8")


def _replace_line(raw: str, starts: str, old: str, new: str) -> str:
    """The real file with one cell changed in the one line starting with `starts`."""
    lines = raw.split("\r\n")
    hits = [i for i, ln in enumerate(lines) if ln.startswith(starts)]
    assert len(hits) == 1
    assert lines[hits[0]].count(old) == 1
    lines[hits[0]] = lines[hits[0]].replace(old, new)
    return "\r\n".join(lines)


def test_transforms_declare_registered_inputs_and_notice():
    paths = Paths.default()
    ts = {t.spec.id: t for t in hot.transforms(paths)}
    assert set(ts) == set(IDS)
    src = load_registry(paths).sources[SOURCE]
    assert {a.id for a in src.artifacts} == {"hot-surface-co2", "readme"}
    for t in ts.values():
        assert [i.key for i in t.inputs] == [f"{SOURCE}/hot-surface-co2", f"{SOURCE}/readme"]
        assert t.spec.headline_entity == "ALOHA"
    # The HOT data policy asks for the NSF award acknowledgement wherever the data are used.
    assert src.obligations.notice and "National Science Foundation under Award #2241005" in src.obligations.notice


def test_vintage_is_the_last_updated_line():
    assert last_updated(_raw()) == date(2026, 1, 1)


def test_every_cruise_as_published():
    cruises = read_cruises(_raw())
    assert len(cruises) == 355 and cruises[0].cruise == 1 and cruises[-1].cruise == 355
    ph = series(cruises, "pHcalc_insitu")
    pco2 = series(cruises, "pCO2calc_insitu")
    # First row: cruise 1, days 30, 31-Oct-88, pHcalc_insitu 8.1097, pCO2calc_insitu 330.9, notes abc.
    assert (ph[0].entity, ph[0].period, ph[0].value) == ("ALOHA", "1988-10-31", 8.1097)
    assert pco2[0].value == 330.9
    # Last row: cruise 355, days 13229, 20-Dec-24, 8.0550 and 389.9, no notes.
    assert (ph[-1].period, ph[-1].value, ph[-1].note) == ("2024-12-20", 8.055, None)
    assert pco2[-1].value == 389.9
    assert all(o.lower is None and o.status == "final" for o in ph + pco2)


def test_notes_in_the_readmes_words_without_ph_sample_codes():
    ph = series(read_cruises(_raw()), "pHcalc_insitu")
    first = ph[0].note
    assert first is not None
    assert "No HOT DIC data; used Keeling DIC (code a)." in first
    assert "No HOT TA data; used Keeling TA (code b)." in first
    assert "pH samples" not in first  # code c concerns measured pH only
    by = {o.period: o for o in ph}
    # Cruise 3 (8-Jan-89) is noted only c.
    assert by["1989-01-08"].note is None


def test_missing_values_are_null_with_reasons():
    cruises = read_cruises(_raw())
    for column in IDS.values():
        nulls = [o for o in series(cruises, column) if o.value is None]
        assert [o.period for o in nulls] == [
            "1990-11-19",
            "1993-07-26",
            "2007-06-10",
            "2008-12-15",
            "2010-02-15",
            "2011-01-09",
            "2015-09-26",
            "2018-01-18",
            "2018-12-11",
        ]
        assert all("-999" in (o.missing_reason or "") for o in nulls)
        # Their notes are k ("No sampling occurred"), o or p ("No DIC, TA or pH sampling occurred ...").
        assert all("sampling occurred" in (o.note or "") for o in nulls)


def test_refuses_unknown_code_bad_date_and_value_on_unsampled_cruise():
    raw = _raw()
    with pytest.raises(HotFormatError, match="not defined"):
        read_cruises(_replace_line(raw, "3\t99\t", "\tc", "\tz"))
    with pytest.raises(HotFormatError, match="days after"):
        read_cruises(_replace_line(raw, "3\t99\t", "8-Jan-89", "9-Jan-89"))
    # Cruise 2 noted k (no sampling) while it has values: the file would contradict itself.
    with pytest.raises(HotFormatError, match="not sampled"):
        series(read_cruises(_replace_line(raw, "2\t62\t", "\tbc", "\tbk")), "pHcalc_insitu")
    with pytest.raises(HotFormatError, match="columns"):
        read_cruises(raw.replace("pHcalc_insitu", "pH_insitu", 1))


# --- the real readme (snapshot cache) -----------------------------------------------------------------------------


def _current(artifact_id: str) -> InputFile:
    p = Paths.default()
    sha = snapshots.read_current(p)[f"{SOURCE}/{artifact_id}"]
    snap = snapshots.read_manifest(p, sha)
    assert snap is not None
    return InputFile(path=snapshots.cache_path(p, sha), snapshot=snap)


@pytest.mark.snapshot
def test_readme_still_defines_what_is_read():
    pdf = _current("readme").path.read_bytes()
    check_readme(pdf, date(2026, 1, 1))
    with pytest.raises(HotFormatError, match="Last updated 2 January 2026"):
        check_readme(pdf, date(2026, 1, 2))


@pytest.mark.snapshot
def test_full_transforms_build_and_validate():
    files = {f"{SOURCE}/{a}": _current(a) for a in ("hot-surface-co2", "readme")}
    for t in hot.transforms(Paths.default()):
        r = t.run(files)
        validate(t, r.observations)
        assert r.vintage == "2026-01-01" and len(r.observations) == 355
