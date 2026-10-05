from __future__ import annotations

import pytest

from envdash.transforms.air.noaa_co2 import NoaaFormatError, parse_annual_global, parse_monthly

from support import fixture


def _monthly():
    path, _ = fixture("noaa-gml-trends", "co2-mm-mlo")
    return parse_monthly(path.read_text())


def test_monthly_vintage_from_file_creation():
    _, created = _monthly()
    assert f"{created:%Y-%m}" == "2026-09"


def test_monthly_values_and_publisher_figure():
    obs, _ = _monthly()
    by = {o.period: o for o in obs}
    assert obs[0].period == "1958-03" and obs[0].value == 315.71
    # NOAA's trends page, vintage 2026-09: "August 2026: 427.55 ppm"
    assert by["2026-08"].value == 427.55
    assert all(o.entity == "MLO" and o.lower is None for o in obs)


def test_monthly_sentinels_become_notes_not_values():
    obs, _ = _monthly()
    by = {o.period: o for o in obs}
    assert "Scripps" in by["1974-04"].note
    assert by["1974-05"].note is None
    assert "No measurement days" in by["1975-12"].note and by["1975-12"].value == 330.77
    assert "Maunakea" in by["2023-01"].note
    assert "until 4 July 2023" in by["2023-07"].note
    assert by["2023-08"].note is None and by["2022-11"].note is None


def test_monthly_refuses_file_without_its_stated_rules():
    path, _ = fixture("noaa-gml-trends", "co2-mm-mlo")
    raw = path.read_text().replace("# Missing months have been interpolated", "# Missing months")
    with pytest.raises(NoaaFormatError, match="re-read"):
        parse_monthly(raw)


def test_annual_global_one_sigma_bounds_and_preliminary_last_year():
    path, _ = fixture("noaa-gml-trends", "co2-annmean-gl")
    obs, created = parse_annual_global(path.read_text())
    last = obs[-1]
    assert (last.period, last.value, last.lower, last.upper) == ("2025", 425.62, 425.57, 425.67)
    assert last.interval == "1sigma" and last.status == "preliminary"
    assert {o.status for o in obs[:-1]} == {"final"}
    assert obs[0].period == "1979" and obs[0].value == 336.85
    assert f"{created:%Y-%m}" == "2026-09"
