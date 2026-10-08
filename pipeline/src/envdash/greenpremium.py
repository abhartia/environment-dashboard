"""Shared pieces of the Green Premium indicators (envdash/transforms/green_premium/).

The Green Premium is the extra cost of doing something the zero-carbon way instead of the fossil way. No open-licence
producer publishes it for every activity, so each indicator comes from one study that publishes the cost of the
cleaner option AND the cost of the conventional option on the same basis (same study, region, year, unit and method).
Both costs are published exactly as the study prints them, side by side, distinguished by the dimension `side`; no
difference or ratio is computed here or on the site. Where a study's conventional value is a third party's number
rather than its own, the conventional side is published as a missing value that says so.

Values are read in one of two ways, both strict:
- From the text of a PDF (pypdf, page by page): a Passage is a sentence or table block copied verbatim from one page.
  It must be found on that page (textmatch rules: whitespace, line-break hyphens and dashes are ignored, except that a
  minus sign must match a minus sign), and every value taken from it must be printed inside it.
- From a table of the article's JATS XML (Europe PMC): the table is found by its label, its caption must match, and
  each value is addressed by its column header and its row label, both of which must be found exactly once.
A printed number is published as its digits (thousands separators removed): no rounding, no arithmetic.
"""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import Decimal

from envdash import textmatch
from envdash.models import Dimension, DimensionValue

MINUS = "−"
_MINUS_KEPT = ""  # a private-use character: survives textmatch.match_key, which treats every dash alike

SIDE = "side"
SIDES: dict[str, str] = {
    "conventional": "The conventional way",
    "conventional-with-capture": "The conventional way with carbon capture",
    "low-carbon": "The lower-carbon way",
}


class PrintedValueError(ValueError):
    pass


def side_dimension(labels: dict[str, str]) -> Dimension:
    """The `side` dimension, with the indicator's own wording for each side it uses (ids from SIDES only)."""
    unknown = set(labels) - set(SIDES)
    if unknown:
        raise ValueError(f"unknown side ids {sorted(unknown)}; use {sorted(SIDES)}")
    return Dimension(id=SIDE, label="Side", values=[DimensionValue(id=k, label=v) for k, v in labels.items()])


# --- printed numbers ----------------------------------------------------------------------------------------------

_NUMBER = re.compile(rf"[{MINUS}-]?(?:\d{{1,3}}(?:,\d{{3}})+|\d+)(?:\.\d+)?(?:E\d+)?")


def printed_number(printed: str, *, prefix: str = "") -> Decimal:
    """The number a cell or passage prints, e.g. "£15,640" (prefix "£"), "0.185", "2.13E4", "−1.9". Anything else
    (a range, a footnote mark, a missing prefix) is refused."""
    if not printed.startswith(prefix):
        raise PrintedValueError(f"{printed!r} does not start with {prefix!r}")
    body = printed[len(prefix) :]
    if not _NUMBER.fullmatch(body):
        raise PrintedValueError(f"{printed!r} is not one printed number")
    return Decimal(body.replace(",", "").replace(MINUS, "-"))


def number_in(printed: str, words: str) -> bool:
    """`printed` appears in `words` as a whole number (not as part of a longer one)."""
    return re.search(rf"(?<![\d.,{MINUS}-]){re.escape(printed)}(?![\d]|[.,]\d)", words) is not None


# --- PDF passages -------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Passage:
    page: int
    """1-based page of the PDF (not the printed page number)."""
    text: str
    """Copied verbatim from the page; a minus sign is U+2212."""
    locator: str
    """Where a reader finds it, e.g. "Section 4 (Summary & conclusions), p. 14"."""


def _key(text: str) -> str:
    """textmatch's match key, except that a minus sign survives, and the ring some PDFs use for a degree sign reads as
    a degree sign."""
    t = unicodedata.normalize("NFKC", text).replace(MINUS, _MINUS_KEPT).replace("◦", "°")
    return textmatch.match_key(t)


def check_passages(pages: list[str], passages: list[Passage]) -> None:
    """Every passage is on its page."""
    problems = []
    keys = [_key(p) for p in pages]
    for p in passages:
        if not 1 <= p.page <= len(pages):
            problems.append(f"{p.locator}: the PDF has {len(pages)} pages; page {p.page} does not exist")
        elif _key(p.text) not in keys[p.page - 1]:
            problems.append(f"{p.locator}: not found on PDF page {p.page}: {p.text[:80]!r}...")
    if problems:
        raise PrintedValueError("; ".join(problems))


def stated(passage: Passage, words: str, printed: str) -> Decimal:
    """The value `printed`, which must be inside `words`, which must be inside the passage."""
    if words not in passage.text:
        raise PrintedValueError(f"{passage.locator}: {words!r} is not part of the passage")
    if not number_in(printed, words):
        raise PrintedValueError(f"{passage.locator}: {printed!r} is not printed in {words!r}")
    return printed_number(printed)


# --- JATS XML tables ----------------------------------------------------------------------------------------------


def jats_root(raw: bytes) -> ET.Element:
    """The <article> element of a JATS XML file (the DOCTYPE's external DTD is not loaded)."""
    root = ET.fromstring(raw)
    if root.tag != "article":
        raise PrintedValueError(f"not a JATS article: root element {root.tag!r}")
    return root


def _text(el: ET.Element) -> str:
    """The text of an element as a reader sees it: a <break/> and the edges of a paragraph (<p>, <title>) are spaces,
    runs of whitespace are one space."""
    parts: list[str] = []

    def walk(e: ET.Element) -> None:
        spaced = e.tag in ("break", "p", "title")
        if spaced:
            parts.append(" ")
        if e.text:
            parts.append(e.text)
        for child in e:
            walk(child)
            if child.tail:
                parts.append(child.tail)
        if spaced:
            parts.append(" ")

    walk(el)
    return re.sub(r"\s+", " ", "".join(parts).replace("\xa0", " ")).strip()


def check_sentences(root: ET.Element, sentences: list[tuple[str, str]]) -> None:
    """Every (locator, sentence) is in the article's body text (textmatch rules, a minus sign kept)."""
    body = root.find("body")
    if body is None:
        raise PrintedValueError("the article has no <body>")
    text = _key(_text(body))
    missing = [f"{loc}: {s[:80]!r}..." for loc, s in sentences if _key(s) not in text]
    if missing:
        raise PrintedValueError("not found in the article's text: " + "; ".join(missing))


def jats_doi(root: ET.Element) -> str:
    ids = [e.text for e in root.iter("article-id") if e.get("pub-id-type") == "doi"]
    if len(ids) != 1 or not ids[0]:
        raise PrintedValueError(f"expected one DOI article-id, found {ids}")
    return ids[0]


def jats_licence(root: ET.Element) -> str:
    lic = list(root.iter("license"))
    if len(lic) != 1:
        raise PrintedValueError(f"expected one <license>, found {len(lic)}")
    return _text(lic[0])


@dataclass(frozen=True)
class JatsTable:
    label: str
    caption: str
    grid: tuple[tuple[str, ...], ...]
    """Every row (head and body) with row and column spans filled in, so each row has one cell per column."""

    def block(self, header: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
        """The rows under a header row (which must occur exactly once), up to the next row with an empty first cell,
        keyed by their first cell (each must be unique within the block)."""
        at = [i for i, r in enumerate(self.grid) if r == header]
        if len(at) != 1:
            raise PrintedValueError(f"{self.label}: header {header} found {len(at)} times")
        rows: dict[str, tuple[str, ...]] = {}
        for r in self.grid[at[0] + 1 :]:
            if r[0] == "":
                break
            if r[0] in rows:
                raise PrintedValueError(f"{self.label}: row {r[0]!r} occurs twice under {header}")
            rows[r[0]] = r
        return rows

    def cell(self, header: tuple[str, ...], row: str, column: str) -> str:
        rows = self.block(header)
        if row not in rows:
            raise PrintedValueError(f"{self.label}: no row {row!r} under {header} (rows {list(rows)})")
        if header.count(column) != 1:
            raise PrintedValueError(f"{self.label}: column {column!r} is not exactly once in {header}")
        return rows[row][header.index(column)]


def jats_table(root: ET.Element, label: str, caption: str) -> JatsTable:
    """The table whose <label> is `label` (a no-break space reads as a space), with its caption checked."""
    found = [tw for tw in root.iter("table-wrap") if (lab := tw.find("label")) is not None and _text(lab) == label]
    if len(found) != 1:
        raise PrintedValueError(f"expected one table labelled {label!r}, found {len(found)}")
    tw = found[0]
    cap = tw.find("caption")
    got = _text(cap) if cap is not None else ""
    if got != caption:
        raise PrintedValueError(f"{label}: caption {got!r} != {caption!r}")
    grid: list[list[str | None]] = []
    for r, tr in enumerate(tw.iter("tr")):
        while len(grid) <= r:
            grid.append([])
        c = 0
        for cell in (e for e in tr if e.tag in ("td", "th")):
            while c < len(grid[r]) and grid[r][c] is not None:
                c += 1
            text = _text(cell)
            for dr in range(int(cell.get("rowspan") or 1)):
                while len(grid) <= r + dr:
                    grid.append([])
                row = grid[r + dr]
                for dc in range(int(cell.get("colspan") or 1)):
                    while len(row) <= c + dc:
                        row.append(None)
                    row[c + dc] = text
            c += int(cell.get("colspan") or 1)
    if any(v is None for row in grid for v in row) or len({len(row) for row in grid}) != 1:
        raise PrintedValueError(f"{label}: rows do not form a rectangle once spans are filled in")
    return JatsTable(label, got, tuple(tuple(v or "" for v in row) for row in grid))
