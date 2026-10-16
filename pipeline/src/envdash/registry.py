"""The source registry (pipeline/sources/*.yaml) and quoted literature values (pipeline/literature/*.yaml).

Each file is validated on its own: one broken entry is reported against its id and never stops the others loading.

A source file may declare `artifact_grids:` beside `artifacts:`, for a producer that serves one file per combination
of a few values (a variable, a period, a scenario, a statistic). Each grid is an artifact whose `id`, `url` and
`description` are templates, plus `values`: placeholder name -> an ordered mapping of value -> label. The grid
expands into one ordinary artifact per combination of the values (in the order written, first name outermost),
filling `{name}` with the value and `{name_label}` with its label; every other field (format, access, max_bytes …) is
copied as written. Expansion happens here, before the entry is validated, so models.Source and data/v1/sources.json
see only ordinary artifacts. A template naming an undeclared placeholder, a declared name the id or url does not use,
or an expanded id or url that another artifact of the source already has, is an error for that source.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml
from pydantic import ValidationError

from envdash.models import REDISTRIBUTABLE, LiteratureValue, Source
from envdash.paths import Paths

PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
PLACEHOLDERS = frozenset({"version", "date_accessed", "date_accessed_long", "year"})
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def long_date(d: date) -> str:
    """'D Month YYYY' in English, whatever the locale: date(2026, 10, 4) -> '4 October 2026'."""
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


@dataclass
class Registry:
    sources: dict[str, Source] = field(default_factory=dict)
    literature: dict[str, LiteratureValue] = field(default_factory=dict)
    source_files: dict[str, Path] = field(default_factory=dict)
    literature_files: dict[str, Path] = field(default_factory=dict)
    source_errors: dict[str, str] = field(default_factory=dict)
    """Source id (the file stem) -> why its file did not load."""
    literature_errors: dict[str, str] = field(default_factory=dict)


def _short(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}" for err in e.errors())


def _load_yaml(path: Path) -> object:
    with path.open("r", encoding="utf-8") as f:
        # BaseLoader keeps every scalar a string (no YAML 1.1 surprises such as `no` -> False or 2026-10 -> int);
        # pydantic does the typing.
        return yaml.load(f, Loader=yaml.BaseLoader)


def _coerce_nulls(v: object) -> object:
    """BaseLoader reads `null` and `~` as strings; turn them back into None, recursively."""
    if isinstance(v, dict):
        return {k: _coerce_nulls(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_coerce_nulls(x) for x in v]
    if v in ("null", "~", "Null", "NULL"):
        return None
    return v


class GridError(ValueError):
    """An artifact_grids entry that cannot expand into distinct, fully named artifacts."""


GRID_TEMPLATES = ("id", "url", "description")


def _grid_values(grid: dict, n: int) -> dict[str, dict[str, str]]:
    values = grid.get("values")
    if not isinstance(values, dict) or not values:
        raise GridError(f"artifact_grids[{n}]: values must map each placeholder to its values")
    for name, options in values.items():
        if not re.fullmatch(r"[a-z]+", name):
            raise GridError(f"artifact_grids[{n}]: placeholder name {name!r} must be lower-case letters only")
        if not isinstance(options, dict) or not options:
            raise GridError(f"artifact_grids[{n}]: values.{name} must map each value to its label")
        for value, label in options.items():
            if not isinstance(label, str) or not label.strip():
                raise GridError(f"artifact_grids[{n}]: values.{name}.{value} needs a label")
    return values


def _expand_grid(grid: object, n: int) -> list[dict]:
    if not isinstance(grid, dict):
        raise GridError(f"artifact_grids[{n}] is not a mapping")
    missing = [k for k in GRID_TEMPLATES if not isinstance(grid.get(k), str)]
    if missing:
        raise GridError(f"artifact_grids[{n}]: {missing} must be given as templates")
    values = _grid_values(grid, n)
    known = set(values) | {f"{name}_label" for name in values}
    for key in GRID_TEMPLATES:
        unknown = set(PLACEHOLDER.findall(grid[key])) - known
        if unknown:
            raise GridError(
                f"artifact_grids[{n}].{key}: unknown placeholders {sorted(unknown)} (declared: {sorted(known)})"
            )
    for key in ("id", "url"):
        unused = set(values) - set(PLACEHOLDER.findall(grid[key]))
        if unused:
            raise GridError(f"artifact_grids[{n}].{key} does not use {sorted(unused)}, so its artifacts would repeat")
    rest = {k: v for k, v in grid.items() if k not in (*GRID_TEMPLATES, "values")}
    out: list[dict] = []
    for combo in itertools.product(*(list(options.items()) for options in values.values())):
        fill: dict[str, str] = {}
        for name, (value, label) in zip(values, combo, strict=True):
            fill[name], fill[f"{name}_label"] = value, label
        out.append({**{k: _fill(grid[k], fill) for k in GRID_TEMPLATES}, **rest})
    return out


def _fill(template: str, fill: dict[str, str]) -> str:
    return PLACEHOLDER.sub(lambda m: fill[m.group(1)], template)


def expand_artifact_grids(raw: object) -> object:
    """The source entry with each `artifact_grids` entry replaced by the artifacts it expands into, appended to
    `artifacts` after those written out. Raises GridError on a malformed grid or a repeated id or url."""
    if not isinstance(raw, dict) or "artifact_grids" not in raw:
        return raw
    grids = raw["artifact_grids"]
    if not isinstance(grids, list) or not grids:
        raise GridError("artifact_grids must be a non-empty list")
    artifacts = raw.get("artifacts") or []
    if not isinstance(artifacts, list):
        return raw  # reported by validation
    expanded = [a for n, g in enumerate(grids) for a in _expand_grid(g, n)]
    for key in ("id", "url"):
        seen: set[str] = set()
        for a in [*artifacts, *expanded]:
            v = a.get(key) if isinstance(a, dict) else None
            if v is None:
                continue
            if v in seen:
                raise GridError(f"artifact {key} {v!r} appears twice once artifact_grids are expanded")
            seen.add(v)
    return {**{k: v for k, v in raw.items() if k != "artifact_grids"}, "artifacts": [*artifacts, *expanded]}


def load_registry(paths: Paths) -> Registry:
    reg = Registry()
    for path in sorted(paths.sources.glob("*.yaml")):
        sid = path.stem
        try:
            raw = expand_artifact_grids(_coerce_nulls(_load_yaml(path)))
            src = Source.model_validate(raw)
        except ValidationError as e:
            reg.source_errors[sid] = f"{path.name} is invalid: {_short(e)}"
            continue
        except GridError as e:
            reg.source_errors[sid] = f"{path.name}: {e}"
            continue
        except (yaml.YAMLError, OSError) as e:
            reg.source_errors[sid] = f"{path.name} could not be read: {e}"
            continue
        if src.id != sid:
            reg.source_errors[sid] = f"{path.name}: id {src.id!r} does not match the file name"
            continue
        bad = _bad_placeholders(src)
        if bad:
            reg.source_errors[sid] = (
                f"{path.name}: unknown placeholders {sorted(bad)} (allowed: {sorted(PLACEHOLDERS)})"
            )
            continue
        reg.sources[sid] = src
        reg.source_files[sid] = path
    for path in sorted(paths.literature.glob("*.yaml")) if paths.literature.exists() else []:
        lid = path.stem
        try:
            lit = LiteratureValue.model_validate(_coerce_nulls(_load_yaml(path)))
        except ValidationError as e:
            reg.literature_errors[lid] = f"literature/{path.name} is invalid: {_short(e)}"
            continue
        except (yaml.YAMLError, OSError) as e:
            reg.literature_errors[lid] = f"literature/{path.name} could not be read: {e}"
            continue
        if lit.id != lid:
            reg.literature_errors[lid] = f"literature/{path.name}: id {lit.id!r} does not match the file name"
            continue
        locator = _literature_locator_problem(reg, lit)
        if locator:
            reg.literature_errors[lid] = f"literature/{path.name}: {locator}"
            continue
        leak = _literature_leak_problem(reg, lit)
        if leak:
            reg.literature_errors[lid] = f"literature/{path.name}: {leak}"
            continue
        reg.literature[lid] = lit
        reg.literature_files[lid] = path
    return reg


QUOTABLE_TEXT_FORMATS = frozenset({"html", "json", "xml", "txt"})


def _literature_locator_problem(reg: Registry, lit: LiteratureValue) -> str | None:
    """A PDF artifact needs pdf_page; an html, json, xml or txt artifact is searched whole and takes none."""
    src = reg.sources.get(lit.source_id)
    if src is None:
        return None  # reported against the source; the build fails the indicator for it
    art = next((a for a in src.artifacts if a.id == lit.artifact_id), None)
    if art is None:
        return f"source {lit.source_id} has no artifact {lit.artifact_id!r}"
    if art.format == "pdf" and lit.pdf_page is None:
        return f"{lit.source_id}/{lit.artifact_id} is a PDF: pdf_page is required"
    if art.format != "pdf" and lit.pdf_page is not None:
        return f"{lit.source_id}/{lit.artifact_id} is {art.format}, not a PDF: pdf_page must be null"
    if art.format != "pdf" and art.format not in QUOTABLE_TEXT_FORMATS:
        return f"{lit.source_id}/{lit.artifact_id} is {art.format}: quotes are checked in pdf, html, json, xml or txt"
    return None


def _value_strings(value: float) -> list[str]:
    """How a value could be written in prose: 77, 967, 1,670,000, 3.6."""
    if float(value).is_integer():
        n = int(value)
        return sorted({str(n), f"{n:,}"})
    return [repr(float(value)).rstrip("0").rstrip(".")]


def _literature_leak_problem(reg: Registry, lit: LiteratureValue) -> str | None:
    """A no-derivatives or display-only value may be shown only on server-rendered pages, so the text that reaches
    the public catalogue (title, description, scope and the reading of the value) must not state it. The quote, which
    does, stays in the private export."""
    src = reg.sources.get(lit.source_id)
    if src is None or src.licence_class in REDISTRIBUTABLE:
        return None
    texts = {
        "title": lit.title,
        "description": lit.description,
        "scope.geography": lit.scope.geography,
        "scope.baseline": lit.scope.baseline,
        "scope.basis": lit.scope.basis,
        "value_reading": lit.value_reading,
    }
    needles = [lit.value_text] + [v for o in lit.observations for v in _value_strings(o.value)]
    for name, text in texts.items():
        if not text:
            continue
        for needle in needles:
            if re.search(rf"(?<![\d.,]){re.escape(needle)}(?![\d])", text, flags=re.IGNORECASE):
                return (
                    f"{name} states the value ({needle!r}), but class {src.licence_class} values stay out of the "
                    "public catalogue; describe it without the number"
                )
    return None


def _bad_placeholders(src: Source) -> set[str]:
    texts = [
        src.obligations.attribution,
        src.obligations.attribution_modified,
        src.obligations.notice,
        src.obligations.derived_disclaimer,
        src.obligations.on_motif,
        src.citation.text,
        src.citation.version,
    ]
    found = {m for t in texts if t for m in PLACEHOLDER.findall(t)}
    return found - PLACEHOLDERS


def render(template: str, *, version: str | None, date_accessed: date | None, year: str | None) -> str:
    """Fill {version}, {date_accessed} (ISO date, 2026-10-04), {date_accessed_long} (the same day as 'D Month YYYY',
    4 October 2026, for producers whose citation format asks for it) and {year}. A placeholder with no value is an
    error, never blank."""
    values = {
        "version": version,
        "date_accessed": date_accessed.isoformat() if date_accessed else None,
        "date_accessed_long": long_date(date_accessed) if date_accessed else None,
        "year": year,
    }

    def sub(m: re.Match[str]) -> str:
        name = m.group(1)
        if name not in values:
            raise ValueError(f"unknown placeholder {{{name}}} in {template!r}")
        v = values[name]
        if v is None:
            raise ValueError(f"placeholder {{{name}}} has no value for {template!r}")
        return v

    return PLACEHOLDER.sub(sub, template)
