"""OECD government R&D budgets for energy, USD PPP at constant 2020 prices (envdash/transforms/energy/oecd_gbard.py).

The fixture is data rows 1-40 and 1299-1388 of the SDMX-CSV of 8 October 2026: the first economies in the file's own
order, then the rows the OECD sorts last, which carry the provisional, estimated, break and definition flags (United
States 2025, Japan 2021 and 2024-2025) and Germany's rows with the auxiliary flag S2.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.transform import InputFile, validate
from envdash.transforms.energy import oecd_gbard as og

from support import fixture


def _file() -> InputFile:
    path, meta = fixture(og.SOURCE, og.CSV.artifact_id)
    snap = snapshots.read_manifest(Paths.default(), meta["full_sha256"])
    assert snap is not None
    return InputFile(path, snap)


def test_values_and_flags_as_published():
    rows = og.read_rows(_file().path.read_bytes())
    obs = og.observations(rows)
    by = {(o.entity, o.period): o for o in obs}
    usa = by[("USA", "2025")]
    assert usa.value == 4912.175869 and usa.status == "preliminary"
    assert usa.note == "OECD flag E: Estimated value; OECD flag P: Provisional value."
    jpn = by[("JPN", "2021")]
    assert jpn.value == 6438.458581 and jpn.status == "preliminary"
    assert (
        jpn.note == "OECD flag B: Time series break; OECD flag D: Definition differs; OECD flag P: Provisional value."
    )
    assert by[("JPN", "2024")].value == 10621.6162 and by[("JPN", "2024")].status == "final"
    deu = by[("DEU", "2014")]
    assert deu.value == 2069.798739 and deu.status == "final"
    assert deu.note == "OECD flag S2: Unrevised breakdown not adding to the revised total."
    assert by[("EST", "2017")].note is None
    # Sorted by economy, then year, whatever the file's order.
    keys = [(o.entity, o.period) for o in obs]
    assert keys == sorted(keys)


def test_the_transform_validates_on_the_fixture():
    (t,) = og.transforms(Paths.default())
    rows = og.read_rows(_file().path.read_bytes())
    obs = og.observations(rows)
    assert len(obs) == 130
    validate(replace(t, validation=replace(t.validation, min_rows=len(obs))), obs)


def test_another_unit_stops_the_build():
    raw = _file().path.read_bytes()
    changed = raw.replace(b"USD_PPP,", b"XDC,", 1)
    assert changed != raw
    with pytest.raises(og.OecdFormatError, match="UNIT_MEASURE"):
        og.read_rows(changed)
