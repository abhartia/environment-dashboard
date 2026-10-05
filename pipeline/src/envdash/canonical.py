"""Canonical serialisation: the same data always produces the same bytes.

JSON: UTF-8, keys sorted, two-space indent, LF line endings, a trailing newline, floats in Python's shortest
round-trip form (repr), no NaN or Infinity. A list element that is a flat record (a dict with no list values and
only flat dicts inside) is written on one line, so an observation is one line and diffs stay readable.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def format_float(x: float) -> str:
    if not math.isfinite(x):
        raise ValueError(f"non-finite float {x!r} cannot be published")
    if x == 0:
        return "0.0"  # never "-0.0"
    return repr(float(x))


def _scalar(v: Any) -> str:
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return format_float(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    raise TypeError(f"cannot serialise {type(v).__name__}")


def _is_flat(v: Any) -> bool:
    if isinstance(v, dict):
        return all(not isinstance(x, list) and (not isinstance(x, dict) or _is_flat(x)) for x in v.values())
    return not isinstance(v, list)


def _compact(v: Any) -> str:
    if isinstance(v, dict):
        return "{" + ", ".join(f"{_scalar(str(k))}: {_compact(v[k])}" for k in sorted(v)) + "}"
    if isinstance(v, list):
        return "[" + ", ".join(_compact(x) for x in v) + "]"
    return _scalar(v)


def _render(v: Any, indent: int, in_list: bool) -> str:
    pad = "  " * (indent + 1)
    end = "  " * indent
    if isinstance(v, dict):
        if not v or (in_list and _is_flat(v)):
            return _compact(v)
        items = [f"{pad}{_scalar(str(k))}: {_render(v[k], indent + 1, False)}" for k in sorted(v)]
        return "{\n" + ",\n".join(items) + "\n" + end + "}"
    if isinstance(v, list):
        if not v:
            return "[]"
        if all(not isinstance(x, dict | list) for x in v):
            return _compact(v)
        return "[\n" + ",\n".join(pad + _render(x, indent + 1, True) for x in v) + "\n" + end + "]"
    return _scalar(v)


def dumps(obj: Any) -> str:
    if isinstance(obj, BaseModel):
        obj = to_plain(obj)
    return _render(obj, 0, False) + "\n"


def dump_bytes(obj: Any) -> bytes:
    return dumps(obj).encode("utf-8")


def to_plain(model: BaseModel) -> Any:
    """A model as JSON-compatible Python, by alias, every field present (defaults and nulls included)."""
    return model.model_dump(mode="json", by_alias=True)


def write_if_changed(path: Path, data: bytes) -> bool:
    """Write bytes (LF, as given) unless the file already holds exactly them. Returns True when written."""
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return True
