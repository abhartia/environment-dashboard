from __future__ import annotations

import json

import pytest

from envdash import canonical
from envdash.transforms.air.noaa_co2 import parse_annual_global

from support import fixture


def _obs():
    path, _ = fixture("noaa-gml-trends", "co2-annmean-gl")
    obs, _ = parse_annual_global(path.read_text())
    return [o.model_dump(mode="json") for o in obs]


def test_same_input_same_bytes_regardless_of_key_order():
    obs = _obs()
    a = {"b": obs, "a": {"y": 1, "x": [1, 2]}}
    b = {"a": {"x": [1, 2], "y": 1}, "b": [dict(reversed(list(o.items()))) for o in obs]}
    assert canonical.dumps(a) == canonical.dumps(b)
    assert json.loads(canonical.dumps(a)) == a


def test_one_observation_per_line_lf_and_trailing_newline():
    obs = _obs()
    text = canonical.dumps({"observations": obs})
    assert "\r" not in text and text.endswith("}\n")
    lines = [ln for ln in text.splitlines() if '"period"' in ln]
    assert len(lines) == len(obs)


def test_floats_shortest_round_trip():
    assert canonical.format_float(425.62) == "425.62"
    assert canonical.format_float(0.1 + 0.2) == "0.30000000000000004"
    assert canonical.format_float(-0.0) == "0.0"
    assert canonical.format_float(50.0) == "50.0"
    with pytest.raises(ValueError):
        canonical.format_float(float("nan"))


def test_unicode_is_not_escaped():
    assert canonical.dumps({"u": "°C"}) == '{\n  "u": "°C"\n}\n'
