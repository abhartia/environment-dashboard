"""Checking that a quote appears in a document (licence terms pages and API responses, report PDFs, web pages).

Extraction differs between formats (HTML tags, PDF line breaks and hyphenation, '#' comment prefixes in CSV
headers, escaped characters in JSON), so both the quote and the document are reduced to a match key first: Unicode
NFKC (so CO₂ -> CO2 and ⁻¹ -> −1), every dash or minus sign treated alike, curly and low quotation marks read as
straight ones, and all whitespace and dashes removed. What is left — the sequence of letters, digits and punctuation —
must match exactly, in order.

The text of a document, by format:
- PDF: the text pypdf extracts, page by page.
- HTML: the visible text: <head>, scripts, styles, <noscript>, <template> and comments removed, tags replaced by
  spaces, entities decoded.
- JSON: the body as served, then every string value decoded (escapes resolved, any HTML inside reduced to text), so a
  quote of the raw form ('"license":"CC-BY-4.0"') and of a value's words both match.
- XML: the body as served, then the same body with its tags removed (a quote that runs across inline markup matches).
- Anything else (CSV, plain text): the text with leading '#' comment markers removed from each line.
"""

from __future__ import annotations

import html
import io
import json
import logging
import re
import unicodedata

_DASHES = re.compile(r"[-­‐‑‒–—―−﹣－]")
_SPACE_AND_DASH = re.compile(r"[\s-]+")
_QUOTES = str.maketrans({"“": '"', "”": '"', "„": '"', "‟": '"', "‘": "'", "’": "'", "‚": "'", "‛": "'"})


def match_key(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    t = _DASHES.sub("-", t)
    t = t.translate(_QUOTES)
    return _SPACE_AND_DASH.sub("", t)


def contains(document_text: str, quote: str) -> bool:
    k = match_key(quote)
    if not k:
        raise ValueError("empty quote")
    return k in match_key(document_text)


def html_to_text(raw: str) -> str:
    """Markup removed: scripts, styles, <noscript>, <template> and comments dropped, every tag replaced by a space."""
    t = re.sub(r"(?is)<(script|style|noscript|template)\b.*?</\1\s*>", " ", raw)
    t = re.sub(r"(?s)<!--.*?-->", " ", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return html.unescape(t)


def html_visible_text(raw: str) -> str:
    """The text a reader sees: html_to_text without the document <head> (title, meta tags)."""
    return html_to_text(re.sub(r"(?is)<head\b.*?</head\s*>", " ", raw))


def json_text(raw: str) -> str | None:
    """The body followed by every string value of the parsed JSON (keys excluded), or None if it is not JSON."""
    try:
        obj = json.loads(raw)
    except ValueError:
        return None
    values: list[str] = []

    def walk(o: object) -> None:
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            values.append(html_to_text(o))

    walk(obj)
    return raw + "\n" + "\n".join(values)


def pdf_pages_text(data: bytes) -> list[str]:
    from pypdf import PdfReader

    # pypdf logs font-encoding warnings for these InDesign PDFs; the text we check is unaffected.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = PdfReader(io.BytesIO(data))
    return [page.extract_text() or "" for page in reader.pages]


def _kind(ctype: str, url: str, text: str) -> str:
    """html, json, xml or text: by the declared content type first, then by the URL, then by the first characters."""
    for kind in ("html", "json", "xml"):
        if kind in ctype:
            return kind
    head = text[:2000].lstrip("\ufeff \t\r\n")
    if url.endswith((".html", ".htm", ".php", "/")) or re.search(r"(?i)<html\b", head):
        return "html"
    if url.endswith(".json") or head[:1] in ("{", "["):
        return "json"
    if url.endswith(".xml") or head.startswith("<?xml"):
        return "xml"
    return "text"


def document_text(data: bytes, content_type: str | None, url: str | None = None) -> str:
    """Plain text of a terms page, API response or file (see the module docstring for each format)."""
    ctype = (content_type or "").split(";")[0].split(",")[0].strip().lower()
    if ctype == "application/pdf" or data[:5] == b"%PDF-":
        return "\n".join(pdf_pages_text(data))
    text = data.decode("utf-8", errors="replace")
    kind = _kind(ctype, (url or "").split("?")[0].lower(), text)
    if kind == "html":
        return html_visible_text(text)
    if kind == "json":
        decoded = json_text(text)
        if decoded is not None:
            return decoded
    if kind == "xml":
        return text + "\n" + html_to_text(text)
    return re.sub(r"(?m)^\s*#+", " ", text)
