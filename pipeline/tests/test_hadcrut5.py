from __future__ import annotations

import pytest

from envdash.transforms.temperature.hadcrut5 import HadcrutFormatError, rebase, version_of

from support import fixture


def _rebase():
    a, _ = fixture("hadcrut5", "global-annual")
    m, _ = fixture("hadcrut5", "global-monthly")
    return rebase(a.read_bytes(), m.read_bytes())


def test_rebased_to_own_1850_1900_mean():
    obs, offset, _, _ = _rebase()
    by = {o.period: o for o in obs}
    # Regression values (our own computation, also reported by the research verifier): mean 1850-1900 = -0.359436.
    assert round(float(offset), 6) == -0.359436
    assert round(by["2024"].value, 3) == 1.547
    assert round(by["2025"].value, 3) == 1.433
    assert by["2025"].interval == "95ci" and by["2025"].lower < by["2025"].value < by["2025"].upper
    # Rebasing shifts the range, it does not re-estimate it.
    assert by["2025"].upper - by["2025"].lower == pytest.approx(1.1142058 - 1.0322274, abs=1e-12)


def test_partial_current_year_excluded():
    obs, _, excluded, months = _rebase()
    assert excluded == 2026 and months == 8
    assert "2026" not in {o.period for o in obs}


def test_version_read_from_url():
    _, meta = fixture("hadcrut5", "global-annual")
    assert version_of(meta["url"]) == "5.2.0.0"
    with pytest.raises(HadcrutFormatError):
        version_of(meta["url"].replace("HadCRUT.5.2.0.0.analysis", "HadCRUT.5.1.0.0.analysis"))


def test_refuses_two_partial_years():
    a, _ = fixture("hadcrut5", "global-annual")
    m, _ = fixture("hadcrut5", "global-monthly")
    # Drop December 2025 from the real monthly slice: 2025 becomes partial too, which the rule does not allow.
    monthly = b"".join(ln for ln in m.read_bytes().splitlines(keepends=True) if not ln.startswith(b"2025-12"))
    with pytest.raises(HadcrutFormatError, match="partial"):
        rebase(a.read_bytes(), monthly)
