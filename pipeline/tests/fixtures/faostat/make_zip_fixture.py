"""Cut a byte-exact fixture from a FAOSTAT snapshot: rows of one CSV member of a bulk zip, or a whole file.

    uv run python tests/fixtures/faostat/make_zip_fixture.py --artifact emissions-totals \
        --member "Emissions_Totals_E_All_Data_(Normalized).csv" --area-code 5000 \
        --item-element 6518:723113 --item-element 6825:723113 --item-element 5085:7225

make_fixture.py slices a text snapshot by line; a FAOSTAT bulk file is a zip, and re-zipping a slice would not give
bytes that occur in the snapshot. So the fixture is cut from the decompressed member instead: its header line
unchanged, then every data line (unchanged, CRLF kept) whose Area Code is --area-code and whose (Item Code, Element
Code) is one of the --item-element pairs, in file order. Without --area-code the whole member is kept; without
--member the whole snapshot file is kept. The member's own sha256 and size go in the sidecar next to the zip's.

Fixtures live one level down (tests/fixtures/faostat/<artifact>/), because test_fixtures_provenance.py re-cuts every
tests/fixtures/*/*.provenance.json with make_fixture.cut, which cannot read a zip. test_faostat_emissions.py runs the
same two checks on these sidecars with cut() below.
"""

from __future__ import annotations

import argparse
import csv
import io
import shlex
import sys
import zipfile
from pathlib import Path

from envdash import canonical, snapshots
from envdash.paths import Paths
from envdash.registry import load_registry

HERE = Path(__file__).resolve().parent
SOURCE = "faostat"


def _fields(line: bytes) -> list[str]:
    return next(csv.reader(io.StringIO(line.decode("latin-1"))))


def cut(raw: bytes, member: str | None, area_code: str | None, pairs: list[tuple[str, str]]) -> tuple[bytes, dict]:
    """(fixture bytes, sidecar info) for the snapshot bytes `raw`."""
    if member is None:
        return raw, {"rows_kept": "whole file"}
    data = zipfile.ZipFile(io.BytesIO(raw)).read(member)
    info: dict = {"member": member, "member_sha256": canonical.sha256_bytes(data), "member_bytes": len(data)}
    if area_code is None:
        return data, {**info, "rows_kept": "whole member"}
    lines = data.splitlines(keepends=True)
    header, rows = lines[0], lines[1:]
    cols = _fields(header)
    ia, ii, ie = cols.index("Area Code"), cols.index("Item Code"), cols.index("Element Code")
    want = set(pairs)
    kept = []
    for ln in rows:
        f = _fields(ln)
        if f[ia] == area_code and (f[ii], f[ie]) in want:
            kept.append(ln)
    shown = ", ".join(f"{i}:{e}" for i, e in pairs)
    return b"".join([header, *kept]), {
        **info,
        "header_lines": 1,
        "data_rows_total": len(rows),
        "rows_kept": f"{len(kept)} of {len(rows)} data rows: Area Code {area_code}, "
        f"(Item Code:Element Code) in {shown}",
    }


def parse_command(command: str) -> tuple[str, str | None, str | None, list[tuple[str, str]]]:
    """The (artifact, member, area code, pairs) a sidecar's command was run with."""
    args = _parser().parse_args(shlex.split(command)[4:])
    return args.artifact, args.member, args.area_code, [tuple(p.split(":")) for p in args.item_element]


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--member")
    ap.add_argument("--area-code")
    ap.add_argument("--item-element", action="append", default=[], help="Item Code:Element Code")
    ap.add_argument("--suffix", default="", help="Inserted before the extension, e.g. .flags")
    return ap


def main(argv: list[str]) -> None:
    args = _parser().parse_args(argv)
    paths = Paths.default()
    src = load_registry(paths).sources[SOURCE]
    if src.licence_class != "open":
        raise SystemExit(f"{SOURCE} is {src.licence_class}: fixtures are cut only from open-class sources")
    art = next(a for a in src.artifacts if a.id == args.artifact)
    sha = snapshots.read_current(paths)[snapshots.key(SOURCE, args.artifact)]
    snap = snapshots.read_manifest(paths, sha)
    assert snap is not None
    raw = snapshots.cache_path(paths, sha).read_bytes()
    assert canonical.sha256_bytes(raw) == sha
    pairs = [tuple(p.split(":")) for p in args.item_element]
    sliced, info = cut(raw, args.member, args.area_code, pairs)  # type: ignore[arg-type]
    ext = Path(args.member).suffix.lstrip(".") if args.member else art.format
    out = HERE / args.artifact / f"{sha[:12]}{args.suffix}.{ext}"
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
        "command": "uv run python tests/fixtures/faostat/make_zip_fixture.py " + shlex.join(argv),
        "licence": src.licence.name,
    }
    out.with_name(out.name + ".provenance.json").write_bytes(canonical.dump_bytes(sidecar))
    print(f"{out.relative_to(HERE.parent.parent.parent)}: {info['rows_kept']}")


if __name__ == "__main__":
    main(sys.argv[1:])
