"""Read one member of a remote zip with HTTP Range requests, without downloading the zip (models.Artifact.zip_member).

Some producers publish only very large zips whose one useful file is small: each Climate TRACE subsector zip on
Zenodo is up to 4.9 GB, while the country-level CSV inside it is about half a megabyte. For an artifact with
`zip_member`, the fetch asks for the first byte (to learn the size), reads the end of the zip (the
end-of-central-directory record, its Zip64 locator and record, and usually the whole central directory) in one
request, then the member's local header and compressed bytes in one more. Python's zipfile parses both and checks
the member's CRC-32 and size, so the bytes recorded are exactly the member's bytes as the producer zipped them. The
snapshot is those member bytes; its manifest records the zip's URL and the member's name, and the zip's ETag and
Last-Modified when the server sends them (Zenodo sends neither; a file of a published Zenodo version cannot change).

Every response must be 206 Partial Content for the bytes asked for, and every response must carry the same total
size and the same ETag (and Last-Modified) as the first, so a zip replaced on the server between two requests is a
failure, never a member stitched from two files. A server that answers 200 (ignoring Range) is a permanent failure:
it would be sending the whole zip.
"""

from __future__ import annotations

import io
import re
import time
import zipfile
from dataclasses import dataclass

import httpx

TAIL_BYTES = 1 << 20
"""The first request reads the last MiB: the end records and, for zips of a few thousand members, the whole
central directory."""
MIN_BLOCK = 1 << 16
ATTEMPTS = 4
BACKOFF_SECONDS = (5.0, 20.0, 60.0)
RETRY_AFTER_MAX = 120.0
MIN_INTERVAL_SECONDS = 0.5
"""At most two range requests a second, under Zenodo's 133 requests a minute for anonymous clients."""
_last_request = [0.0]
CONTENT_RANGE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")


class ZipMemberError(Exception):
    """Will not get better by retrying."""


class ZipMemberRetryable(Exception):
    pass


@dataclass(frozen=True)
class Member:
    data: bytes
    zip_bytes: int
    """The size of the whole zip on the server."""
    etag: str | None
    last_modified: str | None
    requests: int


class RemoteZip(io.RawIOBase):
    """A read-only, seekable view of a remote file that fetches only the byte ranges read, and keeps them."""

    def __init__(self, client: httpx.Client, url: str, headers: dict[str, str] | None = None) -> None:
        super().__init__()
        self.client = client
        self.url = url
        self.headers = dict(headers or {})
        self.size: int | None = None
        self.etag: str | None = None
        self.last_modified: str | None = None
        self.requests = 0
        self._segments: list[tuple[int, bytes]] = []
        self._pos = 0
        self._fetch_tail()

    # --- HTTP -----------------------------------------------------------------------------------------------------

    def _get(self, range_header: str) -> tuple[int, bytes, int]:
        """(start, bytes, total size) of one 206 response, with retries on transport errors, 429 and 5xx."""
        last: Exception | None = None
        for attempt in range(ATTEMPTS):
            try:
                wait = _last_request[0] + MIN_INTERVAL_SECONDS - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                _last_request[0] = time.monotonic()
                r = self.client.get(self.url, headers={**self.headers, "Range": range_header})
                self.requests += 1
                if r.status_code == 429 or r.status_code >= 500:
                    raise ZipMemberRetryable(f"HTTP {r.status_code} from {self.url}", _retry_after(r))
                if r.status_code == 200:
                    raise ZipMemberError(
                        f"{self.url} answered 200 to a Range request: the server does not serve byte ranges, so one "
                        "member cannot be read without the whole zip"
                    )
                if r.status_code != 206:
                    raise ZipMemberError(f"HTTP {r.status_code} from {self.url}")
                m = CONTENT_RANGE.match(r.headers.get("content-range", ""))
                if not m:
                    raise ZipMemberError(
                        f"{self.url}: 206 without a usable Content-Range ({r.headers.get('content-range')!r})"
                    )
                start, end, total = (int(x) for x in m.groups())
                if len(r.content) != end - start + 1:
                    raise ZipMemberRetryable(f"{self.url}: {len(r.content)} bytes for range {start}-{end}", None)
                self._same_file(total, r.headers.get("etag"), r.headers.get("last-modified"))
                return start, r.content, total
            except ZipMemberError:
                raise
            except (httpx.TransportError, ZipMemberRetryable) as e:
                last = e
                if attempt < ATTEMPTS - 1:
                    wait = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                    if isinstance(e, ZipMemberRetryable) and e.args[1] is not None:
                        wait = max(wait, e.args[1])
                    time.sleep(wait)
        raise ZipMemberRetryable(f"{self.url}: {last} (after {ATTEMPTS} attempts)", None)

    def _same_file(self, total: int, etag: str | None, last_modified: str | None) -> None:
        if self.size is None:
            self.size, self.etag, self.last_modified = total, etag, last_modified
            return
        if (total, etag, last_modified) != (self.size, self.etag, self.last_modified):
            raise ZipMemberError(
                f"{self.url} changed between two range requests (size {self.size} -> {total}, ETag {self.etag!r} -> "
                f"{etag!r}, Last-Modified {self.last_modified!r} -> {last_modified!r})"
            )

    def _fetch_tail(self) -> None:
        # The size first, from the Content-Range of a one-byte request: Zenodo answers a suffix range longer than
        # the file ("bytes=-N", N > size) with a body it never sends, so the tail is asked for by explicit offsets.
        start, data, total = self._get("bytes=0-0")
        self._segments.append((start, data))
        first = max(0, total - TAIL_BYTES)
        start, data, _ = self._get(f"bytes={first}-{total - 1}")
        if start != first or start + len(data) != total:
            raise ZipMemberError(f"{self.url}: the tail request did not return bytes {first}-{total - 1}")
        self._segments.append((start, data))

    def prefetch(self, start: int, length: int) -> None:
        """Make sure bytes [start, start + length) are held, with one request for whatever is missing."""
        assert self.size is not None
        end = min(start + length, self.size)
        missing = self._first_missing(start, end)
        if missing is None:
            return
        got_start, data, _ = self._get(f"bytes={missing}-{end - 1}")
        if got_start != missing:
            raise ZipMemberError(f"{self.url}: asked for bytes from {missing}, got from {got_start}")
        self._segments.append((got_start, data))

    def _first_missing(self, start: int, end: int) -> int | None:
        pos = start
        while pos < end:
            seg = self._segment_at(pos)
            if seg is None:
                return pos
            pos = seg[0] + len(seg[1])
        return None

    def _segment_at(self, pos: int) -> tuple[int, bytes] | None:
        for s, d in self._segments:
            if s <= pos < s + len(d):
                return s, d
        return None

    # --- file interface (what zipfile needs) -----------------------------------------------------------------------

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        assert self.size is not None
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._pos, io.SEEK_END: self.size}[whence]
        self._pos = max(0, base + offset)
        return self._pos

    def readinto(self, b) -> int:  # type: ignore[no-untyped-def]
        assert self.size is not None
        n = min(len(b), self.size - self._pos)
        if n <= 0:
            return 0
        if self._first_missing(self._pos, self._pos + n) is not None:
            self.prefetch(self._pos, max(n, MIN_BLOCK))
        done = 0
        while done < n:  # a full read, across held segments (zipfile treats a short header read as corrupt)
            seg = self._segment_at(self._pos)
            assert seg is not None
            s, d = seg
            k = min(n - done, s + len(d) - self._pos)
            b[done : done + k] = d[self._pos - s : self._pos - s + k]
            self._pos += k
            done += k
        return done


def _retry_after(r: httpx.Response) -> float | None:
    v = r.headers.get("retry-after", "")
    return min(float(v), RETRY_AFTER_MAX) if v.isdigit() else None


def open_zip(remote: RemoteZip) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(remote)
    except zipfile.BadZipFile as e:
        raise ZipMemberError(f"{remote.url}: not a zip file ({e})") from None


def read_member(remote: RemoteZip, z: zipfile.ZipFile, member: str, *, max_bytes: int) -> Member:
    """The bytes of one member (CRC-32 and size checked by zipfile)."""
    try:
        info = z.getinfo(member)
    except KeyError:
        names = [i.filename for i in z.infolist()][:20]
        raise ZipMemberError(f"{remote.url} has no member {member!r} (first members: {names})") from None
    if info.file_size > max_bytes:
        raise ZipMemberError(f"{member} in {remote.url} is {info.file_size:,} bytes, over the {max_bytes:,}-byte limit")
    # Local header (30 bytes, then the name and an extra field whose length can differ from the central directory's;
    # 64 KiB covers any extra field) and the compressed bytes, in one request.
    remote.prefetch(info.header_offset, 30 + len(info.filename.encode()) + 65_536 + info.compress_size)
    try:
        data = z.read(info)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, NotImplementedError) as e:
        raise ZipMemberError(f"{member} in {remote.url}: {e}") from None
    assert remote.size is not None
    return Member(data, remote.size, remote.etag, remote.last_modified, remote.requests)
