"""Content fingerprints for files that are rebuilt on every request (models.Artifact.content_key).

A zip generated per download (FAO FRA bulk download, Zenodo's files-archive) has a new sha256 every time even when
its data are unchanged, because the zip records the time each member was written. Snapshots stay keyed by the raw
sha256, but for these artifacts the fetch also computes a content fingerprint and keeps the current snapshot when the
fingerprint is unchanged, so an unchanged download never becomes a new vintage.

zip-members: sha256 of the compact UTF-8 JSON array [[name, sha256 of the member's bytes], ...] sorted by name, over
every file member (directory entries skipped). Zip timestamps, member order, compression and comments do not enter
it. With member_name_ignore, every match of that regex is removed from each name first (FAO stamps the download date
into every member name); two members whose names become equal is an error.

xlsx-members: the same fingerprint of a workbook (an xlsx is a zip), without its docProps/core.xml: the core document
properties, where a workbook built per request records the time it was built (CCKP's API stamps dcterms:created and
dcterms:modified with the request time; every other member of two downloads 80 s apart was byte-identical). The
sheets, shared strings, styles and the other properties all enter it.
"""

from __future__ import annotations

import io
import json
import re
import zipfile

from envdash import canonical
from envdash.models import Artifact


class ContentKeyError(ValueError):
    pass


# The workbook member that records when it was built (Office Open XML core properties).
XLSX_CORE_PROPERTIES = "docProps/core.xml"


def zip_members_sha256(
    data: bytes, member_name_ignore: str | None = None, *, leave_out: frozenset[str] = frozenset()
) -> str:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ContentKeyError(f"not a zip file: {e}") from None
    rx = re.compile(member_name_ignore) if member_name_ignore else None
    members: dict[str, str] = {}
    with z:
        names = {info.filename for info in z.infolist()}
        missing = sorted(leave_out - names)
        if missing:
            raise ContentKeyError(f"the zip has no member {missing}, which this content key leaves out by name")
        for info in z.infolist():
            if info.is_dir() or info.filename in leave_out:
                continue
            name = rx.sub("", info.filename) if rx else info.filename
            if name in members:
                raise ContentKeyError(f"two members are named {name!r} once {member_name_ignore!r} is removed")
            members[name] = canonical.sha256_bytes(z.read(info))
    if not members:
        raise ContentKeyError("the zip has no file members")
    listing = json.dumps(sorted([n, h] for n, h in members.items()), ensure_ascii=False, separators=(",", ":"))
    return canonical.sha256_bytes(listing.encode("utf-8"))


def content_sha256(art: Artifact, data: bytes) -> str | None:
    """The artifact's content fingerprint of these bytes, or None when it declares no content_key."""
    if art.content_key is None:
        return None
    if art.content_key == "zip-members":
        return zip_members_sha256(data, art.member_name_ignore)
    if art.content_key == "xlsx-members":
        return zip_members_sha256(data, art.member_name_ignore, leave_out=frozenset({XLSX_CORE_PROPERTIES}))
    raise ContentKeyError(f"unknown content_key {art.content_key!r}")
