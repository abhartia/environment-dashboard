"""Documents generated from the registry (`envdash docs ...`), so they cannot drift from pipeline/sources/*.yaml.

docs/licensing.md: one row per registered source (id, publisher, licence, class, whether the raw file may be
re-hosted, acquisition, when and how the terms were checked), ordered by class from the most open (models.CLASS_ORDER),
then by publisher and id, with a count per class at the end.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from envdash import canonical
from envdash.models import CLASS_ORDER, Source
from envdash.paths import Paths
from envdash.registry import Registry

LICENSING_INTRO = (
    "Generated from `pipeline/sources/*.yaml` by `uv run envdash docs licensing` (run it after any registry change). "
    "The class decides what the site may do with the data; see `docs/sources.md`. Each source's page under "
    "`/sources` quotes the terms verbatim."
)


def licensing_path(paths: Paths) -> Path:
    return paths.repo / "docs" / "licensing.md"


def _cell(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().replace("|", "\\|")


def _row(s: Source) -> str:
    cells = [
        f"`{s.id}`",
        _cell(s.publisher),
        _cell(s.licence.name),
        s.licence_class,
        "yes" if s.obligations.mirror_raw else "no",
        s.acquisition,
        f"{s.evidence.checked_on.isoformat()} ({s.evidence.terms_check})",
    ]
    return "| " + " | ".join(cells) + " |"


def licensing_markdown(reg: Registry) -> str:
    sources = sorted(reg.sources.values(), key=lambda s: (CLASS_ORDER.index(s.licence_class), s.publisher, s.id))
    counts = Counter(s.licence_class for s in sources)
    tally = ", ".join(f"{counts[c]} {c}" for c in CLASS_ORDER if counts[c])
    lines = [
        "# Licensing: every registered source and its class",
        "",
        LICENSING_INTRO,
        "",
        "| Source | Publisher | Licence | Class | Raw mirror | Acquisition | Terms checked |",
        "|---|---|---|---|---|---|---|",
        *(_row(s) for s in sources),
        "",
        f"{len(sources)} sources: {tally}.",
        "",
    ]
    return "\n".join(lines)


def write_licensing(paths: Paths, reg: Registry) -> bool:
    return canonical.write_if_changed(licensing_path(paths), licensing_markdown(reg).encode("utf-8"))
