"""Cut a byte-exact fixture from a WGMS AMCE release zip snapshot: one member of the zip, whole.

    uv run python tests/fixtures/wgms-amce/make_zip_fixture.py --artifact amce-2026-02-10 --member global.csv
    uv run python tests/fixtures/wgms-amce/make_zip_fixture.py --artifact amce-2026-02-10 --member README.md

The release zip is 53.6 MB and re-zipping a part of it would not give bytes that occur in the snapshot, so the fixture
is one decompressed member, unchanged. It is written to tests/fixtures/wgms-amce/<artifact>/<sha12>.<member> with a
sidecar giving the zip's sha256 and size and the member's. Fixtures live one level down from make_fixture.py's,
because test_fixtures_provenance.py re-cuts every tests/fixtures/*/*.provenance.json by line; test_ice_wgms_amce.py
runs the same two checks on these sidecars with cut() below. Only for open-class sources whose raw files may be
re-hosted (the fixtures are public).
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
SOURCE = "wgms-amce"
MAX_BYTES = 100_000


def cut(raw: bytes, member: str) -> tuple[bytes, dict]:
    """(fixture bytes, sidecar info) for the snapshot bytes `raw`."""
    data = zipfile.ZipFile(io.BytesIO(raw)).read(member)
    return data, {"member": member, "rows_kept": f"the whole member {member} ({len(data):,} bytes)"}


def parse_command(command: str) -> tuple[str, str]:
    """The (artifact, member) a sidecar's command was run with."""
    args = _parser().parse_args(shlex.split(command)[4:])
    return args.artifact, args.member


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--member", required=True)
    return ap


def main(argv: list[str]) -> None:
    args = _parser().parse_args(argv)
    paths = Paths.default()
    src = load_registry(paths).sources[SOURCE]
    if src.licence_class != "open" or not src.obligations.mirror_raw:
        raise SystemExit(f"{SOURCE} is {src.licence_class} (mirror_raw {src.obligations.mirror_raw}): no fixture")
    sha = snapshots.read_current(paths)[snapshots.key(SOURCE, args.artifact)]
    snap = snapshots.read_manifest(paths, sha)
    assert snap is not None
    raw = snapshots.cache_path(paths, sha).read_bytes()
    assert canonical.sha256_bytes(raw) == sha
    sliced, info = cut(raw, args.member)
    if len(sliced) > MAX_BYTES:
        raise SystemExit(f"{len(sliced):,} bytes is too large for a fixture (limit {MAX_BYTES:,})")
    out = HERE / args.artifact / f"{sha[:12]}.{args.member.replace('/', '_')}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(sliced)
    sidecar = {
        "source_id": SOURCE,
        "artifact_id": args.artifact,
        "url": str(snap.url),
        "date_accessed": snap.date_accessed.isoformat(),
        "full_sha256": sha,
        "full_bytes": snap.bytes,
        "fixture_sha256": canonical.sha256_bytes(sliced),
        "fixture_bytes": len(sliced),
        **info,
        "command": "uv run python tests/fixtures/wgms-amce/make_zip_fixture.py " + shlex.join(argv),
        "licence": src.licence.name,
    }
    out.with_name(out.name + ".provenance.json").write_bytes(canonical.dump_bytes(sidecar))
    print(f"{out.relative_to(HERE.parent.parent.parent)}: {info['rows_kept']}")


if __name__ == "__main__":
    main(sys.argv[1:])
