"""Fetch every automatic source: re-check its licence quote, download each artifact, snapshot the bytes.

An artifact with `discover` has its URL resolved from a listing at every fetch (envdash/discovery.py); the snapshot
manifest records the resolved URL and the listing. An artifact with a `content_key` keeps its current snapshot when
the new download's content fingerprint is unchanged (envdash/contentkey.py). Credentials (auth earthdata, api-key)
come from the environment variable the artifact names and are never written to a manifest, a status file or a
message; a request carrying an api key does not follow redirects.

One source failing never stops the others. A source whose licence quote no longer appears on its terms page is
frozen (state failed) and its artifacts are not fetched: it keeps building from its last snapshots until a person
re-checks the terms. A source's current pointers move only when all of its artifacts fetched cleanly, so a build
never mixes files from two releases.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from urllib.parse import urlencode

import httpx

from envdash import canonical, contentkey, discovery, snapshots, textmatch
from envdash.models import Artifact, SnapshotDiscovery, Source, SourceState
from envdash.paths import Paths
from envdash.registry import Registry

USER_AGENT = (
    "EnvironmentDashboard-pipeline/0.1 (+https://environmentdashboard.org; "
    "https://github.com/abhartia/environment-dashboard)"
)
TERMS_MAX_BYTES = 20_000_000
ATTEMPTS = 3
BACKOFF_SECONDS = (2.0, 6.0)


class FetchError(Exception):
    pass


class PermanentFetchError(FetchError):
    """Will not get better by retrying (4xx, too large, missing credential)."""


@dataclass
class ArtifactFetch:
    artifact_id: str
    outcome: str  # "new" | "same" | "not-modified" | "failed"
    sha256: str | None = None
    reason: str | None = None
    resolved_url: str | None = None
    """For artifacts with discover: the URL the listing resolved to."""


@dataclass
class SourceFetch:
    source_id: str
    state: SourceState
    checked_at: str
    reason: str | None = None
    terms: str | None = None  # unchanged | changed | unverifiable | manual
    artifacts: list[ArtifactFetch] = field(default_factory=list)


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(60.0, connect=15.0),
        follow_redirects=True,
        transport=transport,
    )


@dataclass
class Downloaded:
    status: int
    content: bytes
    etag: str | None
    last_modified: str | None
    content_type: str | None
    url: str


def download(
    client: httpx.Client,
    url: str,
    *,
    max_bytes: int,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    follow_redirects: bool = True,
) -> Downloaded:
    """GET with a size cap and retries on transport errors, 429 and 5xx. 304 returns empty content.

    `params` are added to the query string but never to the returned or reported URL (they may hold a key). With
    follow_redirects=False a redirect is a permanent failure that names the target without its query string."""
    # Appended to the URL's own query string as written (httpx's params= would replace it, and re-encoding it could
    # change the request the registry pins).
    target = url + ("&" if "?" in url else "?") + urlencode(params) if params else url
    last: Exception | None = None
    for attempt in range(ATTEMPTS):
        try:
            with client.stream("GET", target, headers=headers or {}, follow_redirects=follow_redirects) as r:
                shown = url if params else str(r.url)
                if r.status_code == 304:
                    return Downloaded(304, b"", r.headers.get("etag"), r.headers.get("last-modified"), None, shown)
                if r.is_redirect:
                    target = r.headers.get("location", "").split("?")[0]
                    raise PermanentFetchError(
                        f"HTTP {r.status_code} from {url} to {target}; a request carrying a credential does not "
                        "follow redirects (update the registry URL)"
                    )
                if r.status_code == 429 or r.status_code >= 500:
                    raise FetchError(f"HTTP {r.status_code} from {url}")
                if r.status_code != 200:
                    # 4xx other than 429 will not get better by retrying.
                    raise PermanentFetchError(f"HTTP {r.status_code} from {url}")
                declared = r.headers.get("content-length")
                if declared is not None and declared.isdigit() and int(declared) > max_bytes:
                    raise PermanentFetchError(f"{url} is {int(declared):,} bytes, over the {max_bytes:,}-byte limit")
                buf = bytearray()
                for chunk in r.iter_bytes():
                    buf += chunk
                    if len(buf) > max_bytes:
                        raise PermanentFetchError(f"{url} exceeded the {max_bytes:,}-byte limit while downloading")
                return Downloaded(
                    200,
                    bytes(buf),
                    r.headers.get("etag"),
                    r.headers.get("last-modified"),
                    r.headers.get("content-type"),
                    shown,
                )
        except PermanentFetchError:
            raise
        except (httpx.TransportError, FetchError) as e:
            last = e
            if attempt < ATTEMPTS - 1:
                time.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
    raise FetchError(f"{url}: {last} (after {ATTEMPTS} attempts)")


def check_terms(client: httpx.Client, src: Source) -> tuple[str, str | None]:
    """Returns (terms state, reason). States: unchanged, changed, unverifiable, manual.

    page, pdf and api are the same check: the licence quote must appear in the normalised text of the body served at
    terms_url (textmatch.document_text: visible text of HTML, text of a PDF, a JSON or XML response's text)."""
    ev = src.evidence
    if ev.terms_check == "manual":
        return "manual", None
    try:
        d = download(client, str(ev.terms_url), max_bytes=TERMS_MAX_BYTES)
    except FetchError as e:
        return "unverifiable", f"terms page not reachable: {e}"
    text = textmatch.document_text(d.content, d.content_type, d.url)
    if textmatch.contains(text, ev.licence_quote):
        return "unchanged", None
    return "changed", (
        f"licence_quote no longer appears at {ev.terms_url} (last checked {ev.checked_on}); the source is frozen "
        "until a person re-reads the terms and updates its registry entry"
    )


def _auth(art: Artifact) -> tuple[dict[str, str], dict[str, str]]:
    """(headers, query parameters) carrying the artifact's credential."""
    acc = art.access
    if acc.auth == "none":
        return {}, {}
    if acc.auth == "cmems":
        raise PermanentFetchError(
            f"artifact {art.id} needs auth cmems (Copernicus Marine Service login), which fetch.py does not implement"
        )
    if acc.auth == "api-key" and not (acc.key_header or acc.key_query):
        raise PermanentFetchError(
            f"artifact {art.id} needs auth api-key but names neither access.key_header nor access.key_query"
        )
    if not acc.auth_env:
        raise PermanentFetchError(f"artifact {art.id} needs auth {acc.auth} but names no auth_env")
    token = os.environ.get(acc.auth_env)
    if not token:
        raise PermanentFetchError(f"artifact {art.id} needs the credential in ${acc.auth_env}, which is not set")
    if acc.auth == "earthdata":
        return {"Authorization": f"Bearer {token}"}, {}
    if acc.key_header:
        return {acc.key_header: token}, {}
    assert acc.key_query is not None
    return {}, {acc.key_query: token}


def _auth_headers(art: Artifact) -> dict[str, str]:
    """Header credentials only (kept for callers of the earlier API); _auth also returns query credentials."""
    return _auth(art)[0]


def resolve_url(client: httpx.Client, art: Artifact) -> tuple[str, SnapshotDiscovery | None]:
    """The URL to download now: the registry URL, or the one the artifact's discover listing resolves to."""
    if art.discover is None:
        if art.url is None:
            raise PermanentFetchError(f"artifact {art.id} has neither a url nor discover")
        return str(art.url), None

    def get_text(u: str) -> str:
        return download(client, u, max_bytes=TERMS_MAX_BYTES).content.decode("utf-8", errors="replace")

    try:
        r = discovery.resolve(art.discover, get_text)
    except discovery.DiscoveryError as e:
        raise PermanentFetchError(f"discover: {e}") from None
    return r.url, r.record


def manual_fetch(src: Source, checked_at: str) -> SourceFetch:
    """The fetch result of a manual source. Nothing is requested: a person downloads its files and records them with
    envdash snapshot add, so the result is known from the registry entry alone, whenever it is asked for."""
    if src.acquisition != "manual":
        raise ValueError(f"{src.id} is fetched automatically, not by hand")
    return SourceFetch(src.id, "manual", checked_at, terms="manual" if src.evidence.terms_check == "manual" else None)


def fetch_source(
    client: httpx.Client, paths: Paths, src: Source, *, today: date, current: dict[str, str]
) -> SourceFetch:
    checked_at = now_iso()
    if src.acquisition == "manual":
        return manual_fetch(src, checked_at)

    terms, terms_reason = check_terms(client, src)
    if terms == "changed":
        return SourceFetch(src.id, "failed", checked_at, reason=terms_reason, terms=terms)

    results: list[ArtifactFetch] = []
    new_pointers: dict[str, str] = {}
    visited_cookie_urls: set[str] = set()
    for art in src.artifacts:
        k = snapshots.key(src.id, art.id)
        resolved: str | None = None
        try:
            headers, params = _auth(art)
            if art.access.cookie_accept_url and str(art.access.cookie_accept_url) not in visited_cookie_urls:
                download(client, str(art.access.cookie_accept_url), max_bytes=TERMS_MAX_BYTES)
                visited_cookie_urls.add(str(art.access.cookie_accept_url))
            url, found = resolve_url(client, art)
            resolved = url if found else None
            cur_sha = current.get(k)
            cur = snapshots.read_manifest(paths, cur_sha) if cur_sha else None
            cached = cur is not None and snapshots.cache_path(paths, cur.sha256).exists()
            # Conditional headers only when we still hold the bytes they refer to, and they came from this same URL;
            # otherwise a 304 would leave the build with nothing to read, or answer for another file.
            if art.access.conditional and cur is not None and cached and str(cur.url) == url:
                if cur.etag:
                    headers["If-None-Match"] = cur.etag
                if cur.last_modified:
                    headers["If-Modified-Since"] = cur.last_modified
            d = download(
                client,
                url,
                max_bytes=art.max_bytes,
                headers=headers,
                params=params or None,
                follow_redirects=art.access.auth != "api-key",
            )
            if d.status == 304:
                assert cur_sha is not None
                results.append(ArtifactFetch(art.id, "not-modified", cur_sha, resolved_url=resolved))
                new_pointers[k] = cur_sha
                continue
            content = contentkey.content_sha256(art, d.content)
            if content is not None and cur is not None and cached:
                assert cur_sha is not None
                cur_content = cur.content_sha256 or contentkey.content_sha256(
                    art, snapshots.cache_path(paths, cur.sha256).read_bytes()
                )
                if cur_content == content:
                    results.append(
                        ArtifactFetch(
                            art.id,
                            "same",
                            cur_sha,
                            reason=f"content unchanged ({art.content_key} {content[:12]}); the new download "
                            f"({canonical.sha256_bytes(d.content)[:12]}) is not recorded",
                            resolved_url=resolved,
                        )
                    )
                    new_pointers[k] = cur_sha
                    continue
            snap, _ = snapshots.record(
                paths,
                data=d.content,
                source_id=src.id,
                artifact_id=art.id,
                url=url,
                acquisition="automatic",
                today=today,
                etag=d.etag,
                last_modified=d.last_modified,
                content_type=d.content_type,
                discovery=found,
                content_key=art.content_key,
                content_sha256=content,
            )
            results.append(
                ArtifactFetch(art.id, "same" if snap.sha256 == cur_sha else "new", snap.sha256, resolved_url=resolved)
            )
            new_pointers[k] = snap.sha256
        except FetchError as e:
            results.append(ArtifactFetch(art.id, "failed", reason=str(e), resolved_url=resolved))
        except Exception as e:  # isolation: a bug or odd response in one artifact fails only its source
            results.append(ArtifactFetch(art.id, "failed", reason=f"{type(e).__name__}: {e}", resolved_url=resolved))

    failed = [r for r in results if r.outcome == "failed"]
    if failed:
        reason = "; ".join(f"{r.artifact_id}: {r.reason}" for r in failed)
        return SourceFetch(src.id, "failed", checked_at, reason=reason, terms=terms, artifacts=results)
    snapshots.set_current(paths, new_pointers)
    current.update(new_pointers)
    state: SourceState = "ok" if any(r.outcome == "new" for r in results) else "unchanged"
    return SourceFetch(src.id, state, checked_at, reason=terms_reason, terms=terms, artifacts=results)


def fetch_all(
    paths: Paths,
    registry: Registry,
    *,
    only: Iterable[str] | None = None,
    today: date | None = None,
    client: httpx.Client | None = None,
) -> dict[str, SourceFetch]:
    wanted = set(only) if only else None
    today = today or date.today()
    out: dict[str, SourceFetch] = {}
    for sid, err in registry.source_errors.items():
        if wanted and sid not in wanted:
            continue
        out[sid] = SourceFetch(sid, "failed", now_iso(), reason=err)
    current = snapshots.read_current(paths)
    own_client = client is None
    client = client or make_client()
    try:
        for sid, src in sorted(registry.sources.items()):
            if wanted and sid not in wanted:
                continue
            try:
                out[sid] = fetch_source(client, paths, src, today=today, current=current)
            except Exception as e:  # never let one source stop the rest
                out[sid] = SourceFetch(sid, "failed", now_iso(), reason=f"{type(e).__name__}: {e}")
    finally:
        if own_client:
            client.close()
    return out
