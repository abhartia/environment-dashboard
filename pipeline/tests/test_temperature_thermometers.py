"""The "thermometers agree" set: GISTEMP v4, NOAAGlobalTemp v6.1, C3S ERA5 (Bulletin and Climate Pulse) and HadSST4,
each on its own stated baseline. Fixtures are byte-exact slices of real snapshots (tests/fixtures/<source>/); the
tests marked snapshot read the full cached files instead."""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal

import pytest

from envdash import snapshots
from envdash.models import Snapshot
from envdash.paths import Paths
from envdash.transform import InputFile, Transform, run_checks, validate
from envdash.transforms.temperature import c3s_climate_pulse as pulse
from envdash.transforms.temperature import c3s_era5_bulletin as bulletin
from envdash.transforms.temperature import gistemp, hadsst4, noaaglobaltemp

from support import fixture


def _fixture_input(source_id: str, artifact_id: str) -> InputFile:
    path, meta = fixture(source_id, artifact_id)
    snap = Snapshot(
        sha256=meta["fixture_sha256"],
        bytes=meta["fixture_bytes"],
        source_id=source_id,
        artifact_id=artifact_id,
        url=meta["url"],
        date_accessed=date.fromisoformat(meta["date_accessed"]),
        acquisition="automatic",
    )
    return InputFile(path=path, snapshot=snap)


def _only(module) -> Transform:
    (t,) = module.transforms(Paths.default())
    return t


def _by_id(module, indicator_id: str) -> Transform:
    return next(t for t in module.transforms(Paths.default()) if t.spec.id == indicator_id)


def _run_on_fixtures(t: Transform):
    return t.run({i.key: _fixture_input(i.source_id, i.artifact_id) for i in t.inputs})


# --- GISTEMP v4 ---------------------------------------------------------------------------------------------------


def _gistemp_raw() -> bytes:
    # Fixture rows: the title line, the header line, 1880-1899, and 2024-2026 (make_fixture counts the header line
    # as data row 1 because GISS puts a title line above it).
    return fixture("gistemp-v4", "glb-monthly")[0].read_bytes()


def test_gistemp_rebased_to_own_1880_1899_mean():
    obs, offset, partial, last_month = gistemp.rebase(_gistemp_raw())
    by = {o.period: o for o in obs}
    # Mean of the 20 printed J-D values 1880-1899 (our own computation).
    assert offset == Decimal("-0.2305")
    # 2025 J-D is 1.19 relative to 1951-1980; 2024 is 1.29.
    assert by["2025"].value == pytest.approx(1.4205, abs=1e-12)
    assert by["2024"].value == pytest.approx(1.5205, abs=1e-12)
    assert partial == {2026: 8} and last_month == "2026-08"
    assert "2026" not in by and obs[0].period == "1880"


def test_gistemp_result_labels_baseline_and_partial_year():
    r = _run_on_fixtures(_only(gistemp))
    assert r.vintage == "v4 2026-08"
    assert "1880–1899" in r.changes and "2026 left out" in r.changes
    assert any("not 1850–1900" in s for s in r.steps)
    assert _only(gistemp).spec.scope.baseline.startswith("1880–1899 mean of this dataset")


def test_gistemp_refuses_annual_mean_without_twelve_months():
    # December 2025 removed from the real row while its J-D value stays.
    raw = _gistemp_raw().replace(b",1.21,1.06,1.19,", b",1.21,***,1.19,")
    with pytest.raises(gistemp.GistempFormatError, match="months present"):
        gistemp.rebase(raw)


# --- NOAAGlobalTemp v6.1 ------------------------------------------------------------------------------------------


def _noaa_urls() -> dict[str, str]:
    url = fixture("noaaglobaltemp-v6", "global-annual")[1]["url"]
    return {
        "global-annual": url,
        "global-monthly": fixture("noaaglobaltemp-v6", "global-monthly")[1]["url"],
        # The arctic file is not sliced into a fixture; its real URL differs from the global one only in the region.
        "arctic-annual": url.replace(".90S.90N.", ".60N.90N."),
    }


def test_noaa_three_files_share_one_release():
    assert noaaglobaltemp.release_of(_noaa_urls()) == ("6.1.0", "202608")
    mixed = _noaa_urls() | {"arctic-annual": _noaa_urls()["arctic-annual"].replace("202608", "202609")}
    with pytest.raises(noaaglobaltemp.NoaaGlobalTempFormatError, match="different releases"):
        noaaglobaltemp.release_of(mixed)


def test_noaa_rebased_to_own_1850_1900_mean_without_partial_year():
    a = fixture("noaaglobaltemp-v6", "global-annual")[0].read_bytes()
    m = fixture("noaaglobaltemp-v6", "global-monthly")[0].read_bytes()
    obs, offset, excluded, months = noaaglobaltemp.rebase(a, m, "202608")
    by = {o.period: o for o in obs}
    # Mean of the 51 annual anomalies 1850-1900 (K relative to 1991-2020), our own computation.
    assert round(float(offset), 6) == -0.776881
    assert by["2025"].value == pytest.approx(0.514181 - float(offset), abs=1e-12)
    assert excluded == 2026 and months == 8 and "2026" not in by
    assert len(obs) == 176 and obs[0].period == "1850"


def test_noaa_refuses_monthly_file_of_another_release():
    a = fixture("noaaglobaltemp-v6", "global-annual")[0].read_bytes()
    m = fixture("noaaglobaltemp-v6", "global-monthly")[0].read_bytes()
    with pytest.raises(noaaglobaltemp.NoaaGlobalTempFormatError, match="ends at 202608"):
        noaaglobaltemp.rebase(a, m, "202607")


def test_noaa_readme_must_state_the_1991_2020_baseline():
    text = fixture("noaaglobaltemp-v6", "timeseries-readme")[0].read_text()
    noaaglobaltemp.check_readme(text)
    with pytest.raises(noaaglobaltemp.NoaaGlobalTempFormatError, match="re-read"):
        noaaglobaltemp.check_readme(text.replace("from 1991 to 2020", "from 1901 to 2000"))


# --- C3S Climate Bulletin (ERA5 monthly) --------------------------------------------------------------------------


def _bulletin_raw() -> str:
    return fixture("c3s-era5-bulletin", "global-allmonths")[0].read_text()


def test_bulletin_publishes_producers_ano_pi_unchanged():
    obs, offsets = bulletin.parse(_bulletin_raw())
    by = {o.period: o for o in obs}
    assert by["1940-01"].value == 0.0145
    assert by["2026-08"].value == 1.6457
    assert offsets["01"] == [Decimal("0.9600")] and offsets["08"] == [Decimal("0.8000")]
    assert bulletin.last_updated(_bulletin_raw()) == date(2026, 9, 3)


def test_bulletin_result_and_publisher_check():
    t = _only(bulletin)
    r = _run_on_fixtures(t)
    assert (r.vintage, r.year, r.date_published) == ("2026-08", "2026", "2026-09-03")
    assert r.changes is None
    (outcome,) = run_checks(t, {"c3s-era5-bulletin": r.vintage}, r.observations)
    assert outcome.status == "pass"


def test_bulletin_refuses_row_whose_ano_pi_is_not_the_sum():
    raw = _bulletin_raw().replace("0.8457,0.8000,1.6457", "0.8457,0.8000,1.6500")
    with pytest.raises(bulletin.BulletinFormatError, match="is not ano_91-20"):
        bulletin.parse(raw)


# --- C3S Climate Pulse (ERA5 daily) -------------------------------------------------------------------------------


def test_pulse_air_temperature_keeps_preliminary_status():
    raw = fixture("c3s-climate-pulse", "air-temperature-daily")[0].read_text()
    obs, preliminary = pulse.parse(raw, pulse.VARIABLES[pulse.AIR.key])
    by = {o.period: o for o in obs}
    assert obs[0].period == "1940-01-01" and obs[0].value == -0.762
    assert by["2026-10-03"].value == 0.683 and by["2026-10-03"].status == "preliminary"
    assert by["2026-10-02"].value == 0.683 and by["2026-10-02"].status == "final"
    assert preliminary == 1
    assert pulse.last_updated(raw) == date(2026, 10, 5)


def test_pulse_sea_surface_temperature():
    t = _by_id(pulse, "sst.c3s-climate-pulse.daily-60s-60n-1991-2020")
    r = _run_on_fixtures(t)
    assert r.vintage == "2026-10-05" and r.year == "2026"
    assert r.observations[0].period == "1979-01-01" and r.observations[0].value == -0.154
    assert r.observations[-1].period == "2026-10-03" and r.observations[-1].value == 0.728
    assert {o.status for o in r.observations} == {"final"}


def test_pulse_refuses_unknown_status_and_wrong_variable():
    raw = fixture("c3s-climate-pulse", "air-temperature-daily")[0].read_text()
    with pytest.raises(pulse.PulseFormatError, match="neither FINAL nor PRELIMINARY"):
        pulse.parse(raw.replace(",PRELIMINARY", ",PROVISIONAL"), pulse.VARIABLES[pulse.AIR.key])
    with pytest.raises(pulse.PulseFormatError, match="re-read"):
        pulse.parse(raw, pulse.VARIABLES[pulse.SST.key])


# --- HadSST4 ------------------------------------------------------------------------------------------------------


def test_hadsst_one_sigma_range_from_total_uncertainty():
    a = fixture("hadsst4", "global-annual")[0].read_bytes()
    m = fixture("hadsst4", "global-monthly")[0].read_bytes()
    obs = hadsst4.parse(a, m)
    by = {o.period: o for o in obs}
    # 2025 row: anomaly 0.839189, total_uncertainty 0.030009.
    assert (by["2025"].value, by["2025"].lower, by["2025"].upper) == (0.839189, 0.80918, 0.869198)
    assert by["2025"].interval == "1sigma"
    assert by["1850"].value == -0.291787


def test_hadsst_acknowledgement_fields():
    r = _run_on_fixtures(_only(hadsst4))
    assert (r.vintage, r.year) == ("4.2.0.0", "2025")
    _, meta = fixture("hadsst4", "global-annual")
    assert hadsst4.version_of(meta["url"]) == "4.2.0.0"


def test_hadsst_refuses_annual_year_without_twelve_months():
    a = fixture("hadsst4", "global-annual")[0].read_bytes()
    m = fixture("hadsst4", "global-monthly")[0].read_bytes()
    dropped = b"".join(ln for ln in m.splitlines(keepends=True) if not ln.startswith(b"2025,12,"))
    with pytest.raises(hadsst4.HadsstFormatError, match="11 of its months"):
        hadsst4.parse(a, dropped)


# --- full snapshots (data-refresh only) ---------------------------------------------------------------------------


def _current_input(paths: Paths, source_id: str, artifact_id: str) -> InputFile:
    sha = snapshots.read_current(paths)[snapshots.key(source_id, artifact_id)]
    snap = snapshots.read_manifest(paths, sha)
    assert snap is not None
    return InputFile(path=snapshots.cache_path(paths, sha), snapshot=snap)


ALL = [
    (gistemp, "temp.gistemp-v4.annual-1880-1899"),
    (noaaglobaltemp, "temp.noaaglobaltemp-v6.annual-1850-1900"),
    (bulletin, "temp.c3s-era5-bulletin.monthly-1850-1900"),
    (pulse, "temp.c3s-climate-pulse.daily-1991-2020"),
    (pulse, "sst.c3s-climate-pulse.daily-60s-60n-1991-2020"),
    (hadsst4, "sst.hadsst4.annual-1961-1990"),
]


@pytest.mark.snapshot
@pytest.mark.parametrize(("module", "indicator_id"), ALL, ids=[i for _, i in ALL])
def test_full_snapshot_builds_and_validates(module, indicator_id):
    paths = Paths.default()
    t = _by_id(module, indicator_id)
    r = t.run({i.key: _current_input(paths, i.source_id, i.artifact_id) for i in t.inputs})
    validate(t, r.observations)
    vintages = {i.source_id: r.vintage for i in t.inputs}
    assert all(c.status != "fail" for c in run_checks(t, vintages, r.observations))


@pytest.mark.snapshot
def test_hadsst_annual_file_matches_the_download_page_checksum():
    # https://www.metoffice.gov.uk/hadobs/hadsst4/data/download.html (Last updated 15/09/2026):
    # "HadSST.4.2.0.0_annual_GLOBE.csv (14K) - md5sum checksum = 73f8fd76d949004cd5082bb681e06d9f"
    f = _current_input(Paths.default(), "hadsst4", "global-annual")
    if f.snapshot.last_modified != "Tue, 15 Sep 2026 09:14:09 GMT":
        pytest.skip("a newer HadSST file than the one the quoted checksum describes")
    assert hashlib.md5(f.path.read_bytes()).hexdigest() == "73f8fd76d949004cd5082bb681e06d9f"
