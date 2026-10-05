"""The transform framework.

A transform module (envdash/transforms/<domain>/<name>.py) exposes `transforms(paths) -> list[Transform]`. Each
Transform declares the indicator it produces (metadata), the (source, artifact) files it reads, a function from those
files' cached bytes to observations, the validations the result must pass, and publisher cross-checks.

A publisher cross-check compares one of our values with a number the publisher itself states, for one specific
(source, vintage): the verbatim quote, the URL it is on, and the value as printed. The tolerance is half the last
stated digit (427.55 -> ±0.005). A check for another vintage is reported as not applicable, never silently passed.
Self-computed expectations (for example a re-based anomaly) are regression tests in pipeline/tests, not checks here.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal

from envdash.models import Dimension, Display, Observation, PublishedValueRef, Scope, Snapshot, TimeBasis, Unit
from envdash.paths import Paths


@dataclass(frozen=True)
class Input:
    source_id: str
    artifact_id: str

    @property
    def key(self) -> str:
        return f"{self.source_id}/{self.artifact_id}"


@dataclass(frozen=True)
class InputFile:
    path: Path
    """The cached raw bytes (pipeline/.snapshots/<sha256>)."""
    snapshot: Snapshot


@dataclass(frozen=True)
class Spec:
    """Indicator metadata, as published."""

    id: str
    title: str
    description: str
    kind: Literal["series", "published-value", "derived"]
    unit: Unit
    display: Display
    scope: Scope
    geo_coverage: Literal["global-only", "country", "mixed"]
    headline_entity: str
    dimensions: tuple[Dimension, ...] = ()
    headline_dims: tuple[tuple[str, str], ...] = ()
    time_basis: TimeBasis = "calendar"
    """calendar (ISO periods) or years-before-1950 (observations carry age_bp and no period); see models.TimeBasis."""


@dataclass(frozen=True)
class Validation:
    min_rows: int
    value_range: tuple[float, float]
    """Inclusive bounds every non-null value (and lower/upper) must fall in: a unit or parsing error trips it."""
    monotonic_periods: bool = True
    """Time strictly advances within each (entity, dims) series, in file order: periods increase (calendar), or ages
    before 1950 decrease, oldest first (years-before-1950)."""


@dataclass(frozen=True)
class PublisherCheck:
    source_id: str
    vintage: str
    entity: str
    period: str | None
    """The observation's ISO period; None for an indicator dated in years before 1950 (then set age_bp)."""
    stated: str
    """The value exactly as the publisher prints it, e.g. "427.55"."""
    quote: str
    url: str
    dims: tuple[tuple[str, str], ...] = ()
    age_bp: float | None = None
    """For a years-before-1950 indicator: the observation's age as published."""

    @property
    def tolerance(self) -> float:
        exp = Decimal(self.stated).as_tuple().exponent
        assert isinstance(exp, int)
        return float(Decimal(5) * Decimal(10) ** (exp - 1))


@dataclass(frozen=True)
class OriginMeta:
    """Facts about one input file that differ from the rest of the result: a paper published on another day than
    the data release, with its own DOI. Unset fields fall back to Result.date_published and the source's DOI."""

    date_published: str | None = None
    doi: str | None = None


@dataclass
class Result:
    observations: list[Observation]
    vintage: str
    steps: list[str]
    """Plain-words descriptions of each processing step, in order."""
    year: str | None = None
    """Fills {year} in the source's credit line, when the source's terms ask for one."""
    date_published: str | None = None
    changes: str | None = None
    """Set when values were changed (re-based, converted): selects attribution_modified and adds a Changes line."""
    published_value: PublishedValueRef | None = None
    origin_meta: dict[str, OriginMeta] = field(default_factory=dict)
    """Per input ("<source>/<artifact>"): date_published and doi of that origin, when they are not the result's."""


@dataclass(frozen=True)
class Transform:
    spec: Spec
    inputs: tuple[Input, ...]
    run: Callable[[dict[str, InputFile]], Result]
    """Gets {"<source>/<artifact>": InputFile} for every declared input."""
    module_file: Path
    validation: Validation
    checks: tuple[PublisherCheck, ...] = ()
    key_files: tuple[Path, ...] = field(default=())
    """Other files whose content decides the output (e.g. a literature YAML); hashed into the build key."""


class ValidationFailed(Exception):
    pass


def validate(t: Transform, obs: list[Observation]) -> None:
    v = t.validation
    paleo = t.spec.time_basis == "years-before-1950"
    problems: list[str] = []
    if len(obs) < v.min_rows:
        problems.append(f"{len(obs)} rows, fewer than the minimum {v.min_rows}")
    lo, hi = v.value_range
    for o in obs:
        if paleo and (o.period is not None or o.age_bp is None):
            problems.append(f"{o.entity} {o.when}: time_basis years-before-1950 needs age_bp and no period")
        if not paleo and o.period is None:
            problems.append(f"{o.entity} {o.when}: time_basis calendar needs a period")
        for name, x in (("value", o.value), ("lower", o.lower), ("upper", o.upper)):
            if x is not None and not (lo <= x <= hi):
                problems.append(f"{o.entity} {o.when} {name} {x!r} outside the expected range [{lo}, {hi}]")
        if o.lower is not None and o.value is not None and not (o.lower <= o.value <= o.upper):  # type: ignore[operator]
            problems.append(f"{o.entity} {o.when}: value {o.value!r} not within [{o.lower!r}, {o.upper!r}]")
    seen: set[tuple] = set()
    last: dict[tuple, Observation] = {}
    for o in obs:
        series = (o.entity, tuple(sorted(o.dims.items())))
        k = (*series, o.period, o.age_bp)
        if k in seen:
            problems.append(f"duplicate observation {k}")
        seen.add(k)
        if v.monotonic_periods and series in last and not _after(o, last[series]):
            problems.append(f"{o.entity} {o.when} does not follow {last[series].when}")
        last[series] = o
    if problems:
        shown = problems[:10] + ([f"... and {len(problems) - 10} more"] if len(problems) > 10 else [])
        raise ValidationFailed(f"{t.spec.id}: " + "; ".join(shown))


def _after(o: Observation, prev: Observation) -> bool:
    """o comes later in time than prev: a later ISO period, or a younger age (fewer years before 1950)."""
    if o.age_bp is not None and prev.age_bp is not None:
        return o.age_bp < prev.age_bp
    if o.period is not None and prev.period is not None:
        return _period_after(o.period, prev.period)
    return False


def _period_after(p: str, q: str) -> bool:
    # ISO periods of the same shape compare correctly as strings; mixed shapes are an error in themselves.
    if len(p) != len(q):
        return False
    return p > q


@dataclass(frozen=True)
class CheckOutcome:
    check: PublisherCheck
    status: Literal["pass", "fail", "not-applicable"]
    ours: float | None
    detail: str


def run_checks(t: Transform, vintages: dict[str, str], obs: list[Observation]) -> list[CheckOutcome]:
    """vintages: source_id -> the vintage this build used."""
    out: list[CheckOutcome] = []
    for c in t.checks:
        used = vintages.get(c.source_id)
        if used != c.vintage:
            out.append(CheckOutcome(c, "not-applicable", None, f"check is for vintage {c.vintage}; built {used}"))
            continue
        match = [
            o
            for o in obs
            if o.entity == c.entity and o.period == c.period and o.age_bp == c.age_bp and o.dims == dict(c.dims)
        ]
        if len(match) != 1 or match[0].value is None:
            when = c.period if c.period is not None else f"{c.age_bp!r} yr BP"
            out.append(CheckOutcome(c, "fail", None, f"no value for {c.entity} {when}"))
            continue
        ours = match[0].value
        diff = abs(ours - float(c.stated))
        ok = diff <= c.tolerance + 1e-12
        out.append(
            CheckOutcome(
                c,
                "pass" if ok else "fail",
                ours,
                f"ours {ours!r} vs stated {c.stated} (tolerance ±{c.tolerance:g}, difference {diff:.6g})",
            )
        )
    return out


def discover(paths: Paths) -> list[Transform]:
    """Every Transform from every module under envdash.transforms, sorted by indicator id. Ids must be unique."""
    import envdash.transforms as pkg

    found: list[Transform] = []
    for mod in pkgutil.walk_packages(pkg.__path__, prefix=pkg.__name__ + "."):
        if mod.ispkg:
            continue
        m = importlib.import_module(mod.name)
        factory = getattr(m, "transforms", None)
        if factory is None:
            raise RuntimeError(f"{mod.name} has no transforms(paths) function")
        found.extend(factory(paths))
    ids = [t.spec.id for t in found]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise RuntimeError(f"indicator ids declared more than once: {sorted(dupes)}")
    return sorted(found, key=lambda t: t.spec.id)
