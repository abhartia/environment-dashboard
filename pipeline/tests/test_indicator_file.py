"""The published indicator file: observations as columns (models.IndicatorFile), on the committed exports."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from envdash import canonical
from envdash.build import load_export
from envdash.export import export_bytes
from envdash.models import TABLE_OPTIONAL_COLUMNS, IndicatorFile
from envdash.paths import Paths

INDICATORS = Paths.default().public_indicators
# Every optional column but age_bp, three dimensions and interned notes; and an indicator dated in years before 1950.
FULL = INDICATORS / "action.ivanova-2020.options.json"
PALEO = INDICATORS / "co2.bereiter-2015.800k.json"


def _raw(path) -> dict:
    return json.loads(path.read_text())


@pytest.mark.parametrize("path", sorted(INDICATORS.glob("*.json")), ids=lambda p: p.stem)
def test_every_committed_export_round_trips_to_the_same_bytes(path):
    assert export_bytes(load_export(path)) == path.read_bytes()


def test_columns_expand_to_the_observations_row_by_row():
    raw = _raw(FULL)
    ind = load_export(FULL)
    t = raw["table"]
    assert len(ind.observations) == len(t["entity"]) == len(t["value"]) == len(t["status"])
    assert raw["notes"] == sorted(set(raw["notes"])) and len(raw["notes"]) == len(
        {o.note for o in ind.observations} - {None}
    )
    for i, o in enumerate(ind.observations):
        assert (o.entity, o.period, o.value, o.status) == (
            t["entity"][i],
            t["period"][i],
            t["value"][i],
            t["status"][i],
        )
        assert (o.lower, o.upper, o.interval) == (t["lower"][i], t["upper"][i], t["interval"][i])
        assert o.missing_reason == t["missing_reason"][i]
        assert o.note == (None if t["note"][i] is None else raw["notes"][t["note"][i]])
        assert o.dims == {d: col[i] for d, col in t["dims"].items()}
    assert "age_bp" not in t and "observations" not in raw


def test_paleo_file_has_ages_and_no_periods():
    t = _raw(PALEO)["table"]
    assert "period" not in t and len(t["age_bp"]) == len(t["entity"])
    ind = load_export(PALEO)
    assert all(o.period is None and o.age_bp is not None for o in ind.observations)


def test_absent_columns_are_left_out_not_written_as_null():
    t = _raw(INDICATORS / "co2.law-dome.2k.json")["table"]
    assert set(t) == {"entity", "period", "value", "status", "dims"}
    assert set(TABLE_OPTIONAL_COLUMNS) - {"period"} == {
        "age_bp",
        "lower",
        "upper",
        "interval",
        "missing_reason",
        "note",
    }


def _broken(change) -> dict:
    raw = _raw(FULL)
    change(raw)
    return raw


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda r: r["table"]["value"].pop(), "has 38 rows"),
        (lambda r: r["table"]["dims"].pop("domain"), "table dims"),
        (lambda r: r["table"].update(age_bp=[0.0] * len(r["table"]["entity"])), "calendar needs the period column"),
        (lambda r: r["table"].update(lower=[None] * len(r["table"]["entity"])), "lower is all null"),
        (lambda r: r["notes"].reverse(), "distinct and sorted"),
        (lambda r: r["notes"].append("~ a note no row uses"), "every entry of notes"),
        (lambda r: r["table"]["note"].__setitem__(0, len(r["notes"])), "every entry of notes"),
    ],
)
def test_inconsistent_tables_are_refused(change, message):
    with pytest.raises(ValidationError, match=message):
        IndicatorFile.model_validate(_broken(change))


def test_export_bytes_are_canonical_json():
    data = FULL.read_bytes()
    assert canonical.dump_bytes(IndicatorFile.model_validate_json(data)) == data
    # A column of scalars is written on one line.
    assert any(line.startswith('    "entity": [') and line.endswith("],") for line in data.decode().splitlines())
