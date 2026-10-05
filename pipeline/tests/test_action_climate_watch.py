"""Climate Watch NDC Tracker: 2025 NDC submission status and content (envdash/transforms/action/climate_watch_ndc.py).

Climate Watch's data are CC BY-NC 4.0, so no fixture is committed (fixtures are cut only from open-class sources);
the tests that read the response use the full snapshot from the local cache and are marked `snapshot`.
"""

from __future__ import annotations

import json

import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.transform import InputFile, validate
from envdash.transforms.action import climate_watch_ndc as cw


def test_dates_are_read_month_first():
    # As in 2025_date: "11/5/2025" is the EU's NDC, submitted on 5 November 2025.
    assert cw.submission_date("11/5/2025", "EUU") == "2025-11-05"
    assert cw.submission_date("9/8/2026", "X") == "2026-09-08"
    with pytest.raises(cw.ClimateWatchFormatError):
        cw.submission_date("2025-11-05", "EUU")


def test_eu_is_published_as_eu27():
    assert cw.entity("EUU") == "EU27"
    assert cw.entity("AGO") == "AGO"


def _current() -> InputFile:
    p = Paths.default()
    sha = snapshots.read_current(p)[cw.TRACKER.key]
    return InputFile(snapshots.cache_path(p, sha), snapshots.read_manifest(p, sha))


def _doc() -> dict:
    return json.loads(_current().path.read_bytes())


def _ind(doc: dict, slug: str) -> dict:
    (ind,) = [i for i in doc["indicators"] if i["slug"] == slug]
    return ind


@pytest.mark.snapshot
def test_status_and_content_of_the_real_response():
    (t,) = cw.transforms(Paths.default())
    result = t.run({cw.TRACKER.key: _current()})
    validate(t, result.observations)
    by = {(o.entity, o.dims["question"]): o for o in result.observations}
    submitted = [o for o in result.observations if o.dims["question"] == "submitted"]
    assert len(submitted) == 153
    assert sum(o.value == 1 for o in submitted) == 152
    usa = by[("USA", "submitted")]
    assert usa.value == 0 and "Withdrawn 2025 NDC" in (usa.note or "")
    eu = by[("EU27", "submitted")]
    assert eu.value == 1 and eu.period == "2025-11-05"
    assert sum(o.value == 1 for o in result.observations if o.dims["question"] == "ghg-target-2035") == 139


@pytest.mark.snapshot
def test_another_producers_indicator_is_refused():
    doc = _doc()
    _ind(doc, "2025_compare_1")["source"] = "Net Zero Tracker"
    with pytest.raises(cw.ClimateWatchFormatError, match="Net Zero Tracker"):
        cw.read_indicators(json.dumps(doc).encode())


@pytest.mark.snapshot
def test_an_unknown_label_is_refused():
    doc = _doc()
    _ind(doc, "2025_compare_3")["locations"]["AGO"][0]["value"] = "Partly"
    with pytest.raises(cw.ClimateWatchFormatError, match="Partly"):
        cw.observations(cw.read_indicators(json.dumps(doc).encode()))


@pytest.mark.snapshot
def test_a_label_that_answers_neither_way_is_published_as_missing():
    doc = _doc()
    _ind(doc, "2025_compare_3")["locations"]["AGO"][0]["value"] = "No Document Submitted"
    obs = cw.observations(cw.read_indicators(json.dumps(doc).encode()))
    (o,) = [o for o in obs if o.entity == "AGO" and o.dims["question"] == "strengthened-2030-target"]
    assert o.value is None and "No Document Submitted" in (o.missing_reason or "")
