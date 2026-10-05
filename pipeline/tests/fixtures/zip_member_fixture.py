"""Cut a byte-exact fixture from one member of a zip snapshot: the whole member, or some of its lines.

    uv run python tests/fixtures/zip_member_fixture.py --source fao-fra-2025 --artifact bulk-download-world \
        --member FRA_Years_2026-10-05.csv --lines 1:25 --lines 523:528 --suffix .years
    uv run python tests/fixtures/zip_member_fixture.py --source iucn-red-list-gbif --artifact checklist-2026-1 \
        --member meta.xml --suffix .meta

make_fixture.py slices a text snapshot by line; re-zipping a slice of a zip would not give bytes that occur in the
snapshot, so the fixture is cut from the decompressed member instead: the whole member, or the lines START to END
(1-based, inclusive, line endings kept) of each --lines range, in the order given. The member's own sha256 and size go
in the sidecar next to the zip's. Only open-class sources whose terms allow re-hosting the raw file.

Fixtures live one level down (tests/fixtures/<source>/<artifact>/), because test_fixtures_provenance.py re-cuts every
tests/fixtures/*/*.provenance.json with make_fixture.cut, which cannot read a zip. The tests of each source re-run
the same two checks on these sidecars with cut() below (see tests/test_nature_fra_2025.py).
"""

from __future__ import annotations

import argparse
import io
import shlex
import sys
import zipfile
from pathlib import Path

from envdash import canonical, snapshots
from envdash.paths import Paths
from envdash.registry import load_registry

HERE = Path(__file__).resolve().parent


def cut(raw: bytes, member: str, ranges: list[tuple[int, int]]) -> tuple[bytes, dict]:
    """(fixture bytes, sidecar info) for the zip snapshot bytes `raw`."""
    data = zipfile.ZipFile(io.BytesIO(raw)).read(member)
    info: dict = {"member": member, "member_sha256": canonical.sha256_bytes(data), "member_bytes": len(data)}
    if not ranges:
        return data, {**info, "rows_kept": "whole member"}
    lines = data.splitlines(keepends=True)
    kept: list[bytes] = []
    for start, end in ranges:
        if not 1 <= start <= end <= len(lines):
            raise ValueError(f"lines {start}:{end} outside 1:{len(lines)}")
        kept += lines[start - 1 : end]
    shown = ", ".join(f"{s}-{e}" for s, e in ranges)
    return b"".join(kept), {**info, "member_lines": len(lines), "rows_kept": f"lines {shown} of {len(lines)}"}


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--member", required=True)
    ap.add_argument("--lines", action="append", default=[], help="START:END, 1-based inclusive (repeatable)")
    ap.add_argument("--suffix", default="", help="Inserted before the extension, e.g. .taxon")
    return ap


def parse_command(command: str) -> tuple[str, str, str, list[tuple[int, int]]]:
    """The (source, artifact, member, line ranges) a sidecar's command was run with."""
    args = _parser().parse_args(shlex.split(command)[4:])
    return args.source, args.artifact, args.member, [_range(x) for x in args.lines]


def _range(text: str) -> tuple[int, int]:
    a, b = text.split(":")
    return int(a), int(b)


def main(argv: list[str]) -> None:
    args = _parser().parse_args(argv)
    paths = Paths.default()
    src = load_registry(paths).sources[args.source]
    if src.licence_class != "open":
        raise SystemExit(f"{args.source} is {src.licence_class}: fixtures are cut only from open-class sources")
    if not src.obligations.mirror_raw:
        raise SystemExit(f"{args.source} does not allow re-hosting its raw files (mirror_raw false): no fixture")
    sha = snapshots.read_current(paths)[snapshots.key(args.source, args.artifact)]
    snap = snapshots.read_manifest(paths, sha)
    assert snap is not None
    raw = snapshots.cache_path(paths, sha).read_bytes()
    assert canonical.sha256_bytes(raw) == sha
    sliced, info = cut(raw, args.member, [_range(x) for x in args.lines])
    ext = Path(args.member).suffix.lstrip(".")
    out = HERE / args.source / args.artifact / f"{sha[:12]}{args.suffix}.{ext}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(sliced)
    sidecar = {
        "source_id": args.source,
        "artifact_id": args.artifact,
        "url": str(snap.url),
        "date_accessed": snap.date_accessed.isoformat(),
        "full_sha256": sha,
        "full_bytes": snap.bytes,
        "fixture_sha256": canonical.sha256_bytes(sliced),
        "fixture_bytes": len(sliced),
        **info,
        "command": "uv run python tests/fixtures/zip_member_fixture.py " + shlex.join(argv),
        "licence": src.licence.name,
    }
    out.with_name(out.name + ".provenance.json").write_bytes(canonical.dump_bytes(sidecar))
    print(f"{out.relative_to(HERE.parent.parent)}: {info['rows_kept']}")


if __name__ == "__main__":
    main(sys.argv[1:])
