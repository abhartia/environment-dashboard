"""Finding the current file of an artifact whose name changes on a schedule (models.Discover).

Some producers put the date of the latest data in the file name and keep only the newest file (NOAAGlobalTemp
"...v6.1.0.202608.asc", the NH snow cover CDR "nhsce_v01r01_19661004_20260831.nc"), upload each month's file to a new
folder (the C3S Climate Bulletin), or publish one file per day (OISST). For those, the registry gives a listing and a
pattern instead of a URL, and every fetch resolves the URL afresh:

1. Read `listing_url` and collect its links: every href, HTML entities decoded, resolved against the page URL,
   fragment dropped, duplicates removed.
2. With `sublisting_pattern`: keep the links matching it in full, order them by key, newest first, and read them one
   by one (at most `max_sublistings`); the first whose links include a `link_pattern` match is where the file is.
3. Keep the links matching `link_pattern` in full and take the one with the largest key.

Keys are compared as text and must all have the same length; two different URLs with the same largest key, keys of
different lengths, or no match at all stop the fetch with the reason. Nothing is guessed or built from a template.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urldefrag, urljoin

from envdash.models import Discover, SnapshotDiscovery, discover_key

_HREF = re.compile(r"""(?is)<a\b[^>]*?\bhref\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""")


class DiscoveryError(Exception):
    pass


@dataclass(frozen=True)
class Resolved:
    url: str
    record: SnapshotDiscovery


def links(page: str, base_url: str) -> list[str]:
    """Absolute URLs of the <a href> links on a page, in page order, without fragments or duplicates."""
    out: list[str] = []
    seen: set[str] = set()
    for m in _HREF.finditer(page):
        href = html.unescape(next(g for g in m.groups() if g is not None)).strip()
        if not href or href.lower().startswith(("javascript:", "mailto:")):
            continue
        url = urldefrag(urljoin(base_url, href)).url
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _matches(urls: list[str], pattern: str, where: str) -> list[tuple[str, str]]:
    rx = re.compile(pattern)
    found: list[tuple[str, str]] = []
    for u in urls:
        m = rx.fullmatch(u)
        if m:
            try:
                found.append((discover_key(m), u))
            except ValueError as e:
                raise DiscoveryError(f"{where}: link {u}: {e}") from None
    lengths = {len(k) for k, _ in found}
    if len(lengths) > 1:
        raise DiscoveryError(
            f"{where}: keys of different lengths {sorted({k for k, _ in found})} cannot be ordered as text"
        )
    return found


def _largest(found: list[tuple[str, str]], where: str) -> tuple[str, str]:
    best = max(k for k, _ in found)
    urls = sorted({u for k, u in found if k == best})
    if len(urls) > 1:
        raise DiscoveryError(f"{where}: {len(urls)} different links share the largest key {best!r}: {urls}")
    return best, urls[0]


def _as_directory(url: str, listing_is_index: bool) -> str:
    # Apache/nginx directory indexes link subdirectories without a trailing slash ("202610"); read them as
    # directories so that their own relative links resolve inside them.
    if listing_is_index and not url.endswith("/") and "?" not in url:
        return url + "/"
    return url


def resolve(d: Discover, get_text: Callable[[str], str]) -> Resolved:
    """Resolve a Discover to one URL. `get_text(url)` returns the listing page's text (fetch.download decoded)."""
    listing = str(d.listing_url)
    page = get_text(listing)
    found_links = links(page, listing)
    if d.sublisting_pattern is None:
        found = _matches(found_links, d.link_pattern, listing)
        if not found:
            raise DiscoveryError(f"no link on {listing} matches {d.link_pattern!r}")
        key, url = _largest(found, listing)
        return Resolved(url, SnapshotDiscovery(listing_url=listing, sublisting_url=None, key=key))

    index = bool(re.search(r"(?i)<title>\s*Index of\b", page))
    subs = _matches([_as_directory(u, index) for u in found_links], d.sublisting_pattern, listing)
    if not subs:
        raise DiscoveryError(f"no link on {listing} matches the sublisting pattern {d.sublisting_pattern!r}")
    ordered = sorted(subs, reverse=True)
    for i in range(len(ordered) - 1):
        if ordered[i][0] == ordered[i + 1][0] and ordered[i][1] != ordered[i + 1][1]:
            raise DiscoveryError(f"{listing}: two sublistings share the key {ordered[i][0]!r}")
    read: list[str] = []
    for _, sub in ordered[: d.max_sublistings]:
        read.append(sub)
        found = _matches(links(get_text(sub), sub), d.link_pattern, sub)
        if found:
            key, url = _largest(found, sub)
            return Resolved(url, SnapshotDiscovery(listing_url=listing, sublisting_url=sub, key=key))
    raise DiscoveryError(f"no link matching {d.link_pattern!r} on the newest {len(read)} sublisting(s): {read}")
