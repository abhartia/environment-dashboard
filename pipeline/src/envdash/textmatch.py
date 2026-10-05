"""Checking that a quote appears in a document (licence terms pages, report PDFs).

Extraction differs between formats (HTML tags, PDF line breaks and hyphenation, '#' comment prefixes in CSV
headers), so both the quote and the document are reduced to a match key first: Unicode NFKC (so CO₂ -> CO2 and
⁻¹ -> −1), every dash or minus sign treated alike, and all whitespace and dashes removed. What is left — the
sequence of letters, digits and punctuation — must match exactly, in order.
"""

from __future__ import annotations

import html
import io
import logging
import re
import unicodedata

_DASHES = re.compile(r"[-­‐‑‒–—―−﹣－]")
_SPACE_AND_DASH = re.compile(r"[\s-]+")


def match_key(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    t = _DASHES.sub("-", t)
    t = t.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    return _SPACE_AND_DASH.sub("", t)


def contains(document_text: str, quote: str) -> bool:
    k = match_key(quote)
    if not k:
        raise ValueError("empty quote")
    return k in match_key(document_text)


def html_to_text(raw: str) -> str:
    t = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", raw)
    t = re.sub(r"(?s)<!--.*?-->", " ", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return html.unescape(t)


def pdf_pages_text(data: bytes) -> list[str]:
    from pypdf import PdfReader

    # pypdf logs font-encoding warnings for these InDesign PDFs; the text we check is unaffected.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = PdfReader(io.BytesIO(data))
    return [page.extract_text() or "" for page in reader.pages]


def document_text(data: bytes, content_type: str | None, url: str | None = None) -> str:
    """Plain text of a terms page or file: PDF text, HTML without markup, or the text with '#' prefixes removed."""
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype == "application/pdf" or data[:5] == b"%PDF-":
        return "\n".join(pdf_pages_text(data))
    text = data.decode("utf-8", errors="replace")
    if "html" in ctype or (url or "").endswith((".html", "/")) or re.search(r"(?i)<html\b", text[:2000]):
        return html_to_text(text)
    return re.sub(r"(?m)^\s*#+", " ", text)
