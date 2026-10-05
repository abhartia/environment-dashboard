"""The source registry (pipeline/sources/*.yaml) and quoted literature values (pipeline/literature/*.yaml).

Each file is validated on its own: one broken entry is reported against its id and never stops the others loading.
"""

from __future__ import annotations

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


def load_registry(paths: Paths) -> Registry:
    reg = Registry()
    for path in sorted(paths.sources.glob("*.yaml")):
        sid = path.stem
        try:
            raw = _coerce_nulls(_load_yaml(path))
            src = Source.model_validate(raw)
        except ValidationError as e:
            reg.source_errors[sid] = f"{path.name} is invalid: {_short(e)}"
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
