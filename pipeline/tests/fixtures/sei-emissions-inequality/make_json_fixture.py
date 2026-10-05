"""Cut a byte-exact fixture from an SEI Emissions Inequality API snapshot: the records of some years.

    uv run python tests/fixtures/sei-emissions-inequality/make_json_fixture.py --artifact global-percentile-shares \
        --year 1990 --year 2023

make_fixture.py slices a text snapshot by line; an SEI API response is a single line of JSON, {"records":[...]}. So
the fixture is cut by record instead: the snapshot's opening bytes '{"records":[' unchanged, then every record object
(its bytes unchanged) whose "Year" is one of the --year values, in file order, joined by the ',' that separates
records in the snapshot, then the closing ']}'. Every byte of the fixture occurs in the snapshot, and the result is
itself valid JSON of the same shape.

Before cutting, the snapshot is split at the '},{' between records and each piece is checked to parse as one record,
with the pieces equal in number and content to the parsed records; anything else is refused.

Fixtures live one level down (tests/fixtures/sei-emissions-inequality/<artifact>/), because test_fixtures_provenance.py
re-cuts every tests/fixtures/*/*.provenance.json with make_fixture.cut, which cannot cut JSON by record.
test_emissions_sei_inequality.py runs the same two checks on these sidecars with cut() below.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

from envdash import canonical, snapshots
from envdash.paths import Paths
from envdash.registry import load_registry

HERE = Path(__file__).resolve().parent
SOURCE = "sei-emissions-inequality"
OPEN, SEP, CLOSE = b'{"records":[', b",", b"]}"


def records(raw: bytes) -> list[bytes]:
    """The bytes of each record object of the snapshot, in order, after checking the split is exact."""
    if not (raw.startswith(OPEN) and raw.endswith(CLOSE)):
        raise ValueError('the snapshot is not one {"records":[...]} object without whitespace')
    body = raw[len(OPEN) : -len(CLOSE)]
    pieces = body.split(b"},{")
    out = [(b"" if i == 0 else b"{") + p + (b"" if i == len(pieces) - 1 else b"}") for i, p in enumerate(pieces)]
    if SEP.join(out) != body:
        raise ValueError("records are not separated by single commas")
    parsed = json.loads(raw)["records"]
    if len(out) != len(parsed) or any(json.loads(p) != r for p, r in zip(out, parsed, strict=True)):
        raise ValueError("splitting at '},{' does not give the records one by one")
    return out


def cut(raw: bytes, years: list[str]) -> tuple[bytes, dict]:
    """(fixture bytes, sidecar info) for the snapshot bytes `raw`."""
    recs = records(raw)
    want = set(years)
    kept = [r for r in recs if json.loads(r)["Year"] in want]
    return OPEN + SEP.join(kept) + CLOSE, {
        "data_rows_total": len(recs),
        "rows_kept": f"{len(kept)} of {len(recs)} records: Year in {', '.join(years)}",
    }


def parse_command(command: str) -> tuple[str, list[str]]:
    """The (artifact, years) a sidecar's command was run with."""
    args = _parser().parse_args(shlex.split(command)[4:])
    return args.artifact, args.year


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--year", action="append", required=True, help="a Year value to keep (repeatable)")
    return ap


def main(argv: list[str]) -> None:
    args = _parser().parse_args(argv)
    paths = Paths.default()
    src = load_registry(paths).sources[SOURCE]
    if src.licence_class != "open":
        raise SystemExit(f"{SOURCE} is {src.licence_class}: fixtures are cut only from open-class sources")
    if not src.obligations.mirror_raw:
        raise SystemExit(f"{SOURCE} does not allow re-hosting its raw files (mirror_raw false): no fixture")
    art = next(a for a in src.artifacts if a.id == args.artifact)
    sha = snapshots.read_current(paths)[snapshots.key(SOURCE, args.artifact)]
    snap = snapshots.read_manifest(paths, sha)
    assert snap is not None
    raw = snapshots.cache_path(paths, sha).read_bytes()
    assert canonical.sha256_bytes(raw) == sha
    sliced, info = cut(raw, args.year)
    out = HERE / args.artifact / f"{sha[:12]}.{art.format}"
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
        "command": "uv run python tests/fixtures/sei-emissions-inequality/make_json_fixture.py " + shlex.join(argv),
        "licence": src.licence.name,
    }
    out.with_name(out.name + ".provenance.json").write_bytes(canonical.dump_bytes(sidecar))
    print(f"{out.relative_to(HERE.parent.parent.parent)}: {info['rows_kept']}")


if __name__ == "__main__":
    main(sys.argv[1:])
