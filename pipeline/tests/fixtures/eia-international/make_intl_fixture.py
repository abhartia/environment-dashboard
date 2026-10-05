"""Cut a byte-exact fixture from an EIA INTL.zip snapshot: the lines of its member INTL.txt for chosen series.

    uv run python tests/fixtures/eia-international/make_intl_fixture.py \
        --products 44-2,4411-2,4413-2,4415-2,4417-2,4418-2,33-12,37-12,116-12,35-12,117-12,27-12 \
        --regions WORL,USA,CHN,DEU,LAO,XKS,SUN,EU27,WP18

make_fixture.py slices a text snapshot by line; INTL.zip is a zip, and re-zipping a slice would not give bytes that
occur in the snapshot. So the fixture is cut from the decompressed member INTL.txt instead (one JSON object per line):
every line, unchanged and in file order, whose series_id is INTL.<product>-<activity>-<region>-<unit>.A with
<product>-<activity> in --products, <region> in --regions and <unit> QBTU or BKWH. Category lines are not kept. The
member's own sha256 and size go in the sidecar next to the zip's.

Fixtures live one level down (tests/fixtures/eia-international/intl-bulk/), because test_fixtures_provenance.py
re-cuts every tests/fixtures/*/*.provenance.json with make_fixture.cut, which cannot read a zip.
test_energy_eia_international.py runs the same two checks on these sidecars with cut() below.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import shlex
import sys
import zipfile
from pathlib import Path

from envdash import canonical, snapshots
from envdash.paths import Paths
from envdash.registry import load_registry

HERE = Path(__file__).resolve().parent
SOURCE = "eia-international"
ARTIFACT = "intl-bulk"
MEMBER = "INTL.txt"
SERIES = re.compile(r"^INTL\.(\d+-\d+)-([A-Z0-9]+)-(QBTU|BKWH)\.A$")


def cut(raw: bytes, products: list[str], regions: list[str]) -> tuple[bytes, dict]:
    """(fixture bytes, sidecar info) for the zip snapshot bytes `raw`."""
    data = zipfile.ZipFile(io.BytesIO(raw)).read(MEMBER)
    lines = data.splitlines(keepends=True)
    want_p, want_r = set(products), set(regions)
    kept = []
    for ln in lines:
        sid = json.loads(ln).get("series_id")
        m = SERIES.match(sid or "")
        if m and m.group(1) in want_p and m.group(2) in want_r:
            kept.append(ln)
    return b"".join(kept), {
        "member": MEMBER,
        "member_sha256": canonical.sha256_bytes(data),
        "member_bytes": len(data),
        "data_rows_total": len(lines),
        "rows_kept": f"{len(kept)} of {len(lines)} lines: annual QBTU and BKWH series of products {','.join(products)} "
        f"for regions {','.join(regions)}",
    }


def parse_command(command: str) -> tuple[list[str], list[str]]:
    args = _parser().parse_args(shlex.split(command)[4:])
    return args.products.split(","), args.regions.split(",")


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--products", required=True, help="comma-separated <product>-<activity>, e.g. 44-2,4411-2")
    ap.add_argument("--regions", required=True, help="comma-separated region codes from the series ids, e.g. WORL")
    return ap


def main(argv: list[str]) -> None:
    args = _parser().parse_args(argv)
    paths = Paths.default()
    src = load_registry(paths).sources[SOURCE]
    if src.licence_class != "open" or not src.obligations.mirror_raw:
        raise SystemExit(f"{SOURCE}: fixtures are cut only from open-class sources whose raw files may be re-hosted")
    sha = snapshots.read_current(paths)[snapshots.key(SOURCE, ARTIFACT)]
    snap = snapshots.read_manifest(paths, sha)
    assert snap is not None
    raw = snapshots.cache_path(paths, sha).read_bytes()
    assert canonical.sha256_bytes(raw) == sha
    sliced, info = cut(raw, args.products.split(","), args.regions.split(","))
    out = HERE / ARTIFACT / f"{sha[:12]}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(sliced)
    sidecar = {
        "source_id": SOURCE,
        "artifact_id": ARTIFACT,
        "url": str(snap.url),
        "date_accessed": snap.date_accessed.isoformat(),
        "full_sha256": sha,
        "full_bytes": snap.bytes,
        "fixture_sha256": canonical.sha256_bytes(sliced),
        "fixture_bytes": len(sliced),
        **info,
        "command": "uv run python tests/fixtures/eia-international/make_intl_fixture.py " + shlex.join(argv),
        "licence": src.licence.name,
    }
    out.with_name(out.name + ".provenance.json").write_bytes(canonical.dump_bytes(sidecar))
    print(f"{out.relative_to(HERE.parent.parent.parent)}: {info['rows_kept']}")


if __name__ == "__main__":
    main(sys.argv[1:])
