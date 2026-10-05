"""Cut a byte-exact fixture from a Naturvårdsverket statistics page snapshot: only the bytes of the chart's data.csv.

    uv run python tests/fixtures/naturvardsverket-consumption-footprint/make_payload_fixture.py \
        --artifact per-person-page

The series of the page lives in the page model (<script id="__model_data">) as content.highChartsOptions, a JSON
string of the Highcharts options, whose data.csv is the table. In the page bytes that CSV is escaped twice (a quote
inside it reads \\\\\\u0022, a line break \\\\n). The fixture is the contiguous run of page bytes that holds that value:
from just after the unique '\\u0022csv\\u0022:\\u0022' to the first '\\u0022' that is not preceded by a backslash.
Every byte of the fixture occurs, in order and unbroken, in the snapshot.

Why only the payload. The source is open (Naturvårdsverket open data; the statistics are SCB's, under CC0), but its
registry entry has mirror_raw false: the open terms cover the statistics, not the page's own prose, and the page lists
its photographs and illustrations as copyright-protected. So the page itself is never committed; only the data
values, which the site publishes anyway, are. Before writing, the cut is checked: decode() of the fixture must equal
the data.csv that envdash.transforms.footprints.naturvardsverket reads from the whole page, or nothing is written.

Fixtures live one level down (tests/fixtures/<source>/<artifact>/), because test_fixtures_provenance.py re-cuts every
tests/fixtures/*/*.provenance.json with make_fixture.cut (and requires mirror_raw). The source's own tests run the
sidecar checks with cut() below (tests/test_footprints.py).
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
SOURCE = "naturvardsverket-consumption-footprint"
START = b"\\u0022csv\\u0022:\\u0022"
QUOTE = b"\\u0022"


def cut(raw: bytes) -> tuple[bytes, dict]:
    """(fixture bytes, sidecar info) for the page snapshot bytes `raw`."""
    if raw.count(START) != 1:
        raise ValueError(f"expected one data.csv start marker, found {raw.count(START)}")
    start = raw.index(START) + len(START)
    end = start
    while True:
        end = raw.index(QUOTE, end)
        if raw[end - 1 : end] != b"\\":
            break
        end += len(QUOTE)
    return raw[start:end], {
        "byte_range": [start, end],
        "rows_kept": f"bytes {start}-{end} of {len(raw)}: the chart's data.csv value as escaped in the page model, "
        "no page text",
    }


def decode(fragment: bytes) -> str:
    """The CSV text a fixture holds: undo the page model's JSON string escaping, then the chart options'."""
    options_level = json.loads(b'"' + fragment + b'"')
    return json.loads('"' + options_level + '"')


def parse_command(command: str) -> str:
    """The artifact a sidecar's command was run with."""
    return _parser().parse_args(shlex.split(command)[4:]).artifact


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", required=True)
    return ap


def main(argv: list[str]) -> None:
    from envdash.transforms.footprints import naturvardsverket as nv

    args = _parser().parse_args(argv)
    paths = Paths.default()
    src = load_registry(paths).sources[SOURCE]
    if src.licence_class != "open":
        raise SystemExit(f"{SOURCE} is {src.licence_class}: fixtures are cut only from open-class sources")
    sha = snapshots.read_current(paths)[snapshots.key(SOURCE, args.artifact)]
    snap = snapshots.read_manifest(paths, sha)
    assert snap is not None
    raw = snapshots.cache_path(paths, sha).read_bytes()
    assert canonical.sha256_bytes(raw) == sha
    sliced, info = cut(raw)
    if decode(sliced) != nv.chart(nv.page_model(raw)).csv:
        raise SystemExit("the cut does not decode to the page's data.csv: not written")
    out = HERE / args.artifact / f"{sha[:12]}.csv-payload.txt"
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
        "command": "uv run python tests/fixtures/naturvardsverket-consumption-footprint/make_payload_fixture.py "
        + shlex.join(argv),
        "licence": src.licence.name,
    }
    out.with_name(out.name + ".provenance.json").write_bytes(canonical.dump_bytes(sidecar))
    print(f"{out.relative_to(HERE.parent.parent.parent)}: {info['rows_kept']}")


if __name__ == "__main__":
    main(sys.argv[1:])
