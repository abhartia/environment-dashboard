"""A reader for R's serialization format (the bytes of an .rds file), used by stechemesser_2024.

Why not pyreadr. pyreadr (librdata) reads data frames whose columns are atomic vectors. Policy_out.RDS in the
Stechemesser et al. replication deposit is a tibble whose list-columns hold data frames and fitted getspanel model
objects (closures, environments, formulas); pyreadr 0.5.7 refuses the whole file ("Invalid file, or file has
unsupported features"). This module reads every R object type the format defines, so a file is read to its last
byte or refused, never read in part.

Format: R Internals, section 1.8 "Serialization Formats", and src/main/serialize.c (R 4.x). Only the XDR (big-endian
binary, "X\\n") form, versions 2 and 3, gzip-compressed or not; anything else is refused. The reader keeps the values
of atomic vectors, lists, pairlists and attributes; closures, environments, language objects, byte code, external
pointers and S4 objects are read to advance through the stream and kept only as their type. Recognised ALTREP
classes (compact integer and real sequences, deferred strings, wrapper objects) are expanded to the vector R would
give; any other ALTREP class is refused.

transforms() returns no indicators: this is a helper module under the transforms package.
"""

from __future__ import annotations

import gzip
import math
import struct
import sys
from dataclasses import dataclass, field

from envdash.paths import Paths

NILSXP, SYMSXP, LISTSXP, CLOSXP, ENVSXP, PROMSXP, LANGSXP = 0, 1, 2, 3, 4, 5, 6
SPECIALSXP, BUILTINSXP, CHARSXP, LGLSXP, INTSXP, REALSXP, CPLXSXP = 7, 8, 9, 10, 13, 14, 15
STRSXP, DOTSXP, VECSXP, EXPRSXP, BCODESXP, EXTPTRSXP, WEAKREFSXP, RAWSXP, S4SXP = 16, 17, 19, 20, 21, 22, 23, 24, 25
REFSXP, NILVALUE_SXP, GLOBALENV_SXP, UNBOUNDVALUE_SXP, MISSINGARG_SXP, BASENAMESPACE_SXP = 255, 254, 253, 252, 251, 250
NAMESPACESXP, PACKAGESXP, PERSISTSXP, CLASSREFSXP, GENERICREFSXP, BCREPDEF, BCREPREF = 249, 248, 247, 246, 245, 244, 243
EMPTYENV_SXP, BASEENV_SXP, ATTRLANGSXP, ATTRLISTSXP, ALTREP_SXP = 242, 241, 240, 239, 238

NA_INTEGER = -(2**31)
NA_REAL_LOW_WORD = 1954
_PAIRLISTS = (LISTSXP, LANGSXP, CLOSXP, PROMSXP, DOTSXP)
_SINGLETONS = (
    NILVALUE_SXP,
    GLOBALENV_SXP,
    UNBOUNDVALUE_SXP,
    MISSINGARG_SXP,
    BASENAMESPACE_SXP,
    EMPTYENV_SXP,
    BASEENV_SXP,
)


class RdsError(ValueError):
    pass


@dataclass
class RObject:
    """One R object. `values` holds the elements of a vector or list (None for NA), the (tag, value) pairs of a
    pairlist, or the text of a symbol; other types keep only their type."""

    type: int
    values: list = field(default_factory=list)
    attributes: dict[str, RObject] = field(default_factory=dict)

    def attr(self, name: str) -> RObject | None:
        return self.attributes.get(name)

    def strings(self, name: str) -> list[str | None]:
        a = self.attributes.get(name)
        if a is None or a.type != STRSXP:
            raise RdsError(f"attribute {name!r} is not a character vector")
        return a.values

    @property
    def classes(self) -> list[str]:
        a = self.attributes.get("class")
        return [c for c in a.values if c is not None] if a is not None and a.type == STRSXP else []


NULL = RObject(NILSXP)


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0
        self.refs: list[RObject] = []

    def _take(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.data):
            raise RdsError(f"truncated stream: {n} bytes wanted at offset {self.pos} of {len(self.data)}")
        b = self.data[self.pos : self.pos + n]
        self.pos += n
        return b

    def int(self) -> int:
        return struct.unpack(">i", self._take(4))[0]

    def length(self) -> int:
        n = self.int()
        if n == -1:
            hi, lo = self.int(), self.int()
            n = (hi << 32) + lo
        if n < 0:
            raise RdsError(f"negative length {n} at offset {self.pos}")
        return n

    def header(self) -> None:
        if self._take(2) != b"X\n":
            raise RdsError("not R's XDR serialization format (expected 'X\\n')")
        version = self.int()
        self.int()  # R version that wrote the file
        self.int()  # oldest R version that can read it
        if version == 3:
            self._take(self.int())  # native encoding name
        elif version != 2:
            raise RdsError(f"serialization format version {version} is not 2 or 3")

    def strvec(self) -> list[str | None]:
        if self.int() != 0:
            raise RdsError("string vector of a persistent or namespace reference does not start with 0")
        return [self.item().values[0] for _ in range(self.int())]

    def attributes(self, pairlist: RObject) -> dict[str, RObject]:
        if pairlist.type == NILSXP:
            return {}
        if pairlist.type != LISTSXP:
            raise RdsError(f"attributes are type {pairlist.type}, not a pairlist")
        out: dict[str, RObject] = {}
        for tag, value in pairlist.values:
            if tag is None:
                raise RdsError("an attribute without a name")
            out[tag] = value
        return out

    def item(self) -> RObject:
        flags = self.int()
        t = flags & 0xFF
        levels = flags >> 12
        has_attr = bool(flags & (1 << 9))
        has_tag = bool(flags & (1 << 10))
        if t == REFSXP:
            i = flags >> 8 or self.int()
            if not 1 <= i <= len(self.refs):
                raise RdsError(f"reference {i} outside the {len(self.refs)} objects read so far")
            return self.refs[i - 1]
        if t in _SINGLETONS:
            return NULL if t == NILVALUE_SXP else RObject(t)
        if t in (PERSISTSXP, NAMESPACESXP, PACKAGESXP):
            o = RObject(t, list(self.strvec()))
            self.refs.append(o)
            return o
        if t == SYMSXP:
            o = RObject(SYMSXP)
            self.refs.append(o)
            o.values = [self.item().values[0]]
            return o
        if t == ENVSXP:
            o = RObject(ENVSXP)
            self.refs.append(o)
            self.int()  # locked
            for _ in range(3):  # enclosing environment, frame, hash table
                self.item()
            o.attributes = self.attributes(self.item())
            return o
        if t in _PAIRLISTS:
            return self.pairlist(t, has_attr, has_tag)
        if t == EXTPTRSXP:
            o = RObject(t)
            self.refs.append(o)
            self.item()  # protected value
            self.item()  # tag
        elif t == WEAKREFSXP:
            o = RObject(t)
            self.refs.append(o)
        elif t in (SPECIALSXP, BUILTINSXP):
            o = RObject(t, [self._take(self.int()).decode("ascii")])
        elif t == CHARSXP:
            n = self.int()
            if n == -1:
                return RObject(CHARSXP, [None])
            raw = self._take(n)
            # levels: LATIN1_MASK 1<<2, UTF8_MASK 1<<3, BYTES_MASK 1<<1, ASCII_MASK 1<<6
            if levels & (1 << 1):
                raise RdsError("a string marked as bytes, not text")
            return RObject(CHARSXP, [raw.decode("latin-1" if levels & (1 << 2) else "utf-8")])
        elif t in (LGLSXP, INTSXP):
            n = self.length()
            o = RObject(t, [None if v == NA_INTEGER else v for v in struct.unpack(f">{n}i", self._take(4 * n))])
        elif t == REALSXP:
            n = self.length()
            o = RObject(t, [_real(b) for b in _chunks(self._take(8 * n), 8)])
        elif t == CPLXSXP:
            n = self.length()
            parts = [_real(b) for b in _chunks(self._take(16 * n), 8)]
            o = RObject(t, list(zip(parts[0::2], parts[1::2], strict=True)))
        elif t == STRSXP:
            o = RObject(t, [self.item().values[0] for _ in range(self.length())])
        elif t in (VECSXP, EXPRSXP):
            o = RObject(t, [self.item() for _ in range(self.length())])
        elif t == BCODESXP:
            reps: list[RObject | None] = [None] * self.int()
            self.bytecode(reps)
            o = RObject(t)
        elif t == RAWSXP:
            o = RObject(t, list(self._take(self.length())))
        elif t == S4SXP:
            o = RObject(t)
        elif t == ALTREP_SXP:
            info, state, attr = self.item(), self.item(), self.item()
            o = _altrep(info, state)
            o.attributes = self.attributes(attr)
            return o
        else:
            raise RdsError(f"unknown object type {t} at offset {self.pos - 4}")
        if has_attr:
            o.attributes = self.attributes(self.item())
        return o

    def pairlist(self, t: int, has_attr: bool, has_tag: bool) -> RObject:
        """A pairlist-like chain, read without recursion along its CDRs (data frames can have long ones)."""
        o = RObject(t)
        attrs = None
        while True:
            if has_attr:
                a = self.item()
                attrs = attrs if attrs is not None else a
            tag = self.item() if has_tag else None
            car = self.item()
            o.values.append((tag.values[0] if tag is not None and tag.type == SYMSXP else None, car))
            flags = struct.unpack(">i", self.data[self.pos : self.pos + 4])[0] if self.pos + 4 <= len(self.data) else 0
            if flags & 0xFF == t == LISTSXP:
                self.pos += 4
                has_attr = bool(flags & (1 << 9))
                has_tag = bool(flags & (1 << 10))
                continue
            self.item()  # the final CDR (NULL for a proper list)
            break
        if attrs is not None:
            o.attributes = self.attributes(attrs)
        return o

    def bytecode(self, reps: list[RObject | None]) -> None:
        self.item()  # the code vector
        for _ in range(self.int()):
            kind = self.int()
            if kind == BCODESXP:
                self.bytecode(reps)
            elif kind in (LANGSXP, LISTSXP, BCREPDEF, BCREPREF, ATTRLANGSXP, ATTRLISTSXP):
                self.bclang(kind, reps)
            else:
                self.item()

    def bclang(self, kind: int, reps: list[RObject | None]) -> RObject:
        if kind == BCREPREF:
            i = self.int()
            if not 0 <= i < len(reps) or reps[i] is None:
                raise RdsError(f"byte-code reference {i} not defined")
            return reps[i]  # type: ignore[return-value]
        if kind not in (BCREPDEF, LANGSXP, LISTSXP, ATTRLANGSXP, ATTRLISTSXP):
            return self.item()
        pos = -1
        if kind == BCREPDEF:
            pos = self.int()
            kind = self.int()
        has_attr = kind in (ATTRLANGSXP, ATTRLISTSXP)
        o = RObject(LANGSXP if kind in (LANGSXP, ATTRLANGSXP) else LISTSXP)
        if pos >= 0:
            if pos >= len(reps):
                raise RdsError(f"byte-code reference {pos} outside {len(reps)}")
            reps[pos] = o
        if has_attr:
            self.item()
        self.item()  # tag
        self.bclang(self.int(), reps)  # CAR
        self.bclang(self.int(), reps)  # CDR
        return o


def _chunks(b: bytes, n: int) -> list[bytes]:
    return [b[i : i + n] for i in range(0, len(b), n)]


def _real(b: bytes) -> float | None:
    """A double, or None for R's NA_real_ (a NaN whose low word is 1954); other NaNs stay NaN."""
    v = struct.unpack(">d", b)[0]
    if math.isnan(v) and struct.unpack(">I", b[4:])[0] == NA_REAL_LOW_WORD:
        return None
    return v


def _altrep(info: RObject, state: RObject) -> RObject:
    """The vector an ALTREP object stands for, for the classes base R writes; others are refused."""
    if info.type != LISTSXP or not info.values or info.values[0][1].type != SYMSXP:
        raise RdsError("ALTREP class information is not a pairlist starting with a symbol")
    cls = info.values[0][1].values[0]
    if cls in ("compact_intseq", "compact_realseq"):
        if state.type != REALSXP or len(state.values) != 3:
            raise RdsError(f"{cls} state is not (length, start, step)")
        n, start, step = state.values
        seq = [start + i * step for i in range(int(n))]
        return RObject(INTSXP, [int(v) for v in seq]) if cls == "compact_intseq" else RObject(REALSXP, seq)
    if cls == "deferred_string":
        if state.type != LISTSXP or not state.values:
            raise RdsError("deferred_string state is not a pairlist")
        arg = state.values[0][1]
        if arg.type == INTSXP:
            return RObject(STRSXP, [None if v is None else str(v) for v in arg.values])
        if arg.type == REALSXP:
            raise RdsError("deferred_string of a double vector: R's formatting rules are not reproduced here")
        raise RdsError(f"deferred_string of type {arg.type}")
    if cls.startswith("wrap_"):
        if state.type != VECSXP or not state.values:
            raise RdsError(f"{cls} state is not a list")
        return state.values[0]
    raise RdsError(f"ALTREP class {cls!r} is not supported")


def read_rds(data: bytes) -> RObject:
    """The object serialized in an .rds file's bytes (gzip-compressed or not). Refuses anything left over."""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old, 20_000))
    try:
        r = _Reader(data)
        r.header()
        obj = r.item()
    finally:
        sys.setrecursionlimit(old)
    if r.pos != len(data):
        raise RdsError(f"{len(data) - r.pos} bytes left after the serialized object")
    return obj


def column(frame: RObject, name: str) -> list:
    """One column of a data frame or tibble as Python values; factors become their level labels."""
    names = frame.strings("names")
    if names.count(name) != 1:
        raise RdsError(f"data frame has {names.count(name)} columns named {name!r}")
    col = frame.values[names.index(name)]
    if "factor" in col.classes:
        levels = col.strings("levels")
        return [None if i is None else levels[i - 1] for i in col.values]
    if col.type not in (LGLSXP, INTSXP, REALSXP, STRSXP, VECSXP):
        raise RdsError(f"column {name!r} is R type {col.type}")
    return list(col.values)


def nrow(frame: RObject) -> int:
    """Rows of a data frame, from its row.names attribute (compact c(NA, -n) or explicit)."""
    if "data.frame" not in frame.classes:
        raise RdsError(f"not a data frame (class {frame.classes})")
    rn = frame.attr("row.names")
    if rn is None:
        raise RdsError("data frame without row.names")
    if rn.type == INTSXP and len(rn.values) == 2 and rn.values[0] is None:
        return abs(rn.values[1])
    return len(rn.values)


def transforms(paths: Paths) -> list:
    return []
