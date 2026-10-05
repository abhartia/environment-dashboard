"""Cut a byte-exact fixture from a real snapshot: the header block plus the first and last N data rows.

    uv run python tests/fixtures/make_fixture.py --source noaa-gml-trends --artifact co2-mm-mlo --first 220 --last 48

Reads the artifact's current snapshot (pipeline/manifests/current.json -> pipeline/.snapshots/<sha256>), keeps every
leading '#' comment line and the column header line unchanged, then the chosen data lines unchanged, and writes
tests/fixtures/<source>/<sha12>.<format> with a <sha12>.<format>.provenance.json sidecar. Only open-class sources.
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


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--first", type=int, required=True)
    ap.add_argument("--last", type=int, required=True)
    args = ap.parse_args(argv)
    paths = Paths.default()
    src = load_registry(paths).sources[args.source]
    if src.licence_class != "open":
        raise SystemExit(f"{args.source} is {src.licence_class}: fixtures are cut only from open-class sources")
    art = next(a for a in src.artifacts if a.id == args.artifact)
    sha = snapshots.read_current(paths)[snapshots.key(args.source, args.artifact)]
    snap = snapshots.read_manifest(paths, sha)
    assert snap is not None
    raw = snapshots.cache_path(paths, sha).read_bytes()
    assert canonical.sha256_bytes(raw) == sha
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
