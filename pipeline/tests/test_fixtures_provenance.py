from __future__ import annotations

import json

import pytest

from envdash import canonical
from envdash.paths import Paths
from envdash.registry import load_registry

from support import FIXTURES

SIDECARS = sorted(FIXTURES.glob("*/*.provenance.json"))


@pytest.mark.parametrize("side", SIDECARS, ids=lambda p: p.name)
def test_fixture_matches_its_sidecar(side):
    meta = json.loads(side.read_text())
    f = side.with_name(side.name.removesuffix(".provenance.json"))
    assert canonical.sha256_bytes(f.read_bytes()) == meta["fixture_sha256"]
    assert f.name.startswith(meta["full_sha256"][:12])
    assert f.parent.name == meta["source_id"]
    for k in ("url", "date_accessed", "rows_kept", "command", "full_bytes"):
        assert meta[k]
    src = load_registry(Paths.default()).sources[meta["source_id"]]
    assert src.licence_class == "open"


@pytest.mark.snapshot
@pytest.mark.parametrize("side", SIDECARS, ids=lambda p: p.name)
def test_fixture_is_an_exact_slice_of_the_snapshot(side):
    import sys

    sys.path.insert(0, str(FIXTURES))
    from make_fixture import cut

    meta = json.loads(side.read_text())
    raw = (Paths.default().cache / meta["full_sha256"]).read_bytes()
    assert canonical.sha256_bytes(raw) == meta["full_sha256"]
    args = meta["command"].split()
    first, last = int(args[args.index("--first") + 1]), int(args[args.index("--last") + 1])
    sliced, _ = cut(raw, first, last)
    assert canonical.sha256_bytes(sliced) == meta["fixture_sha256"]
