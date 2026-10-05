from __future__ import annotations

from pathlib import Path

import pytest

from envdash.paths import Paths

from support import make_tmp_paths


@pytest.fixture
def tmp_paths(tmp_path: Path) -> Paths:
    """Real registry, transforms and uv.lock; snapshot store and outputs in a temporary directory."""
    return make_tmp_paths(tmp_path)
