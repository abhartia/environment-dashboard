"""Eurostat electricity share of final energy (nrg_ind_fecf) and GBARD for energy (gba_nabsfin07)
(envdash/transforms/energy/eurostat.py).

The fixtures are the whole API responses of 8 October 2026 and the whole glossary page listing the candidate
countries, so the transforms run on them unchanged.
"""

from __future__ import annotations

import json

import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.transform import Input, InputFile, validate
from envdash.transforms.energy import eurostat as es

from support import fixture


def _file(inp: Input) -> InputFile:
    path, meta = fixture(inp.source_id, inp.artifact_id)
    snap = snapshots.read_manifest(Paths.default(), meta["full_sha256"])
    assert snap is not None
    return InputFile(path, snap)


def _files() -> dict[str, InputFile]:
    return {i.key: _file(i) for i in (es.FECF, es.GBARD, es.CANDIDATES)}


def _by(obs) -> dict:
    return {(o.entity, o.period): o for o in obs}


def test_electricity_share_is_eurostats_ratio_as_published():
    t, _ = es.transforms(Paths.default())
    result = t.run(_files())
    validate(t, result.observations)
    by = _by(result.observations)
    # nrg_ind_fecf, E7000, FC_E, PC, updated 2026-07-16.
    assert by[("EU27", "2024")].value == 23.45
    assert by[("EU27", "2023")].value == 23.09
    assert by[("EU27", "1990")].value == 17.9
    assert result.vintage == "nrg_ind_fecf updated 2026-07-16"
    entities = {o.entity for o in result.observations}
    assert len(entities) == 39 and {"GRC", "NOR", "UKR", "TUR"} <= entities
    assert not entities & {"GBR", "KOS", "USA"}


def test_rd_budget_keeps_eurostats_flags():
    _, t = es.transforms(Paths.default())
    result = t.run(_files())
    validate(t, result.observations)
    by = _by(result.observations)
    # gba_nabsfin07, NABS05, MIO_EUR, updated 2026-09-25.
    assert by[("EU27", "2024")].value == 6362.909 and by[("EU27", "2024")].note is None
    p2025 = by[("EU27", "2025")]
    assert p2025.value == 5584.292 and p2025.status == "preliminary" and p2025.note == "Eurostat flag 'p': provisional."
    e2018 = by[("EU27", "2018")]
    assert e2018.value == 4311.114 and e2018.status == "final" and "estimated" in (e2018.note or "")
    alb = by[("ALB", "2022")]
    assert alb.value is None and "confidential" in (alb.missing_reason or "")


def test_a_country_outside_the_reuse_permission_stops_the_build():
    raw = _files()[es.FECF.key].path.read_bytes()
    doc = json.loads(raw)
    cat = doc["dimension"]["geo"]["category"]
    cat["index"] = {("UK" if k == "IS" else k): v for k, v in cat["index"].items()}
    with pytest.raises(es.EurostatFormatError, match="UK"):
        es.read_jsonstat(json.dumps(doc).encode(), "nrg_ind_fecf", es.FECF_FIXED)


def test_a_changed_candidate_list_stops_the_build():
    raw = _files()[es.CANDIDATES.key].path.read_bytes()
    es.check_candidates(raw)
    changed = raw.replace(b"nine official", b"ten official")
    assert changed != raw
    with pytest.raises(es.EurostatFormatError, match="candidate"):
        es.check_candidates(changed)


def test_an_unexpected_filter_stops_the_build():
    raw = _files()[es.GBARD.key].path.read_bytes()
    with pytest.raises(es.EurostatFormatError, match="MIO_PPS"):
        es.read_jsonstat(raw, "gba_nabsfin07", {**es.GBARD_FIXED, "unit": "MIO_PPS"})
