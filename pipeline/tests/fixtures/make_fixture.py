"""Cut a byte-exact fixture from a real snapshot: the header block plus the first and last N data rows, or one
contiguous range of lines (for a web page).

    uv run python tests/fixtures/make_fixture.py --source noaa-gml-trends --artifact co2-mm-mlo --first 220 --last 48
    uv run python tests/fixtures/make_fixture.py --source noaa-crw --artifact global-bleaching-status --lines 290:345
    uv run python tests/fixtures/make_fixture.py --source natural-earth --artifact admin-0-tiny-countries-50m --whole

Reads the artifact's current snapshot (pipeline/manifests/current.json -> pipeline/.snapshots/<sha256>). With --first
and --last it keeps every leading '#' comment line and the column header line unchanged, then the chosen data lines
unchanged; with --lines START:END it keeps lines START to END (1-based, inclusive) unchanged; with --whole it keeps
the whole file (small files only, such as a zip that cannot be cut). It writes
tests/fixtures/<source>/<sha12>.<format> with a <sha12>.<format>.provenance.json sidecar. Only open-class sources
whose terms allow re-hosting the raw file (obligations.mirror_raw), because fixtures are committed to a public
repository.
"""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from envdash import canonical, snapshots
from envdash.paths import Paths
from envdash.registry import load_registry

HERE = Path(__file__).resolve().parent


def cut(raw: bytes, first: int, last: int) -> tuple[bytes, dict]:
    lines = raw.splitlines(keepends=True)
    i = 0
    while i < len(lines) and lines[i].startswith(b"#"):
        i += 1
    header, data = lines[: i + 1], lines[i + 1 :]
    if first + last >= len(data):
        kept, rows = data, f"all {len(data)} data rows"
    else:
        kept = data[:first] + data[len(data) - last :]
        rows = f"data rows 1-{first} and {len(data) - last + 1}-{len(data)} of {len(data)}"
    return b"".join(header + kept), {"header_lines": len(header), "rows_kept": rows, "data_rows_total": len(data)}


def cut_lines(raw: bytes, start: int, end: int) -> tuple[bytes, dict]:
    lines = raw.splitlines(keepends=True)
    if not 1 <= start <= end <= len(lines):
        raise ValueError(f"lines {start}:{end} outside 1:{len(lines)}")
    return b"".join(lines[start - 1 : end]), {"rows_kept": f"lines {start}-{end} of {len(lines)}"}


def cut_from_command(raw: bytes, command: str) -> bytes:
    """Re-run the slicing recorded in a sidecar's command."""
    args = command.split()
    if "--whole" in args:
        return raw
    if "--lines" in args:
        start, end = (int(x) for x in args[args.index("--lines") + 1].split(":"))
        return cut_lines(raw, start, end)[0]
    first, last = int(args[args.index("--first") + 1]), int(args[args.index("--last") + 1])
    return cut(raw, first, last)[0]


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--first", type=int)
    ap.add_argument("--last", type=int)
    ap.add_argument("--lines", help="START:END, 1-based inclusive")
    ap.add_argument("--whole", action="store_true", help="keep the whole file")
    args = ap.parse_args(argv)
    modes = [args.first is not None and args.last is not None, args.lines is not None, args.whole]
    if sum(modes) != 1:
        raise SystemExit("give one of: --first and --last, --lines START:END, --whole")
    paths = Paths.default()
    src = load_registry(paths).sources[args.source]
    if src.licence_class != "open":
        raise SystemExit(f"{args.source} is {src.licence_class}: fixtures are cut only from open-class sources")
    if not src.obligations.mirror_raw:
        raise SystemExit(f"{args.source} does not allow re-hosting its raw files (mirror_raw false): no fixture")
    art = next(a for a in src.artifacts if a.id == args.artifact)
    sha = snapshots.read_current(paths)[snapshots.key(args.source, args.artifact)]
    snap = snapshots.read_manifest(paths, sha)
    assert snap is not None
    raw = snapshots.cache_path(paths, sha).read_bytes()
    assert canonical.sha256_bytes(raw) == sha
    if args.whole:
        if len(raw) > 100_000:
            raise SystemExit(f"{len(raw):,} bytes is too large for a whole-file fixture (limit 100,000)")
        sliced, info = raw, {"rows_kept": f"the whole file ({len(raw):,} bytes)"}
    elif args.lines:
        start, end = (int(x) for x in args.lines.split(":"))
        sliced, info = cut_lines(raw, start, end)
    else:
        sliced, info = cut(raw, args.first, args.last)
    out = HERE / args.source / f"{sha[:12]}.{art.format}"
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
        "command": "uv run python tests/fixtures/make_fixture.py " + shlex.join(argv),
        "licence": src.licence.name,
    }
    out.with_name(out.name + ".provenance.json").write_bytes(canonical.dump_bytes(sidecar))
    print(f"{out.relative_to(HERE.parent.parent)}: {info['rows_kept']}")


if __name__ == "__main__":
    main(sys.argv[1:])
