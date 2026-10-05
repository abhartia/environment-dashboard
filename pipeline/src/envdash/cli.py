"""envdash: fetch, snapshot, build, validate and archive the data behind environmentdashboard.org."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from envdash import archive as archive_mod
from envdash import canonical, snapshots
from envdash import issues as issues_mod
from envdash import openapi as openapi_mod
from envdash import private as private_mod
from envdash.export import BuildReport, build_and_export
from envdash.fetch import SourceFetch, fetch_all, now_iso
from envdash.paths import Paths
from envdash.registry import Registry, load_registry
from envdash.status import read_status, update_status
from envdash.transform import discover
from envdash.validate import validate_all

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)
snapshot_app = typer.Typer(no_args_is_help=True, help="Record raw files.")
app.add_typer(snapshot_app, name="snapshot")
private_app = typer.Typer(no_args_is_help=True, help="Exports we may show but not redistribute (private R2 bucket).")
app.add_typer(private_app, name="private")

SourceOpt = Annotated[list[str] | None, typer.Option("--source", "-s", help="Only these source ids (repeatable).")]


def _paths() -> Paths:
    return Paths.default()


def _print_fetch(results: dict[str, SourceFetch]) -> None:
    for sid, r in sorted(results.items()):
        arts = ", ".join(f"{a.artifact_id}={a.outcome}" for a in r.artifacts)
        line = f"  {r.state:<9} {sid}"
        if r.terms:
            line += f" [terms {r.terms}]"
        if arts:
            line += f" ({arts})"
        typer.echo(line)
        if r.reason:
            typer.echo(f"            {r.reason}")


def _print_build(report: BuildReport) -> None:
    for o in report.outcomes:
        latest = ""
        if o.indicator is not None:
            lt = o.indicator.latest
            latest = f" latest {lt.entity} {lt.period} = {lt.value!r} ({lt.status}); vintage {o.indicator.vintage}"
        typer.echo(f"  {o.state:<8} {o.id}{latest}")
        if o.reason:
            typer.echo(f"           {o.reason}")
        for c in o.checks:
            typer.echo(f"           publisher check [{c.status}] {c.check.source_id} {c.check.vintage}: {c.detail}")
    for lid, err in report.literature_errors.items():
        typer.echo(f"  failed   literature/{lid}: {err}")


def _do_fetch(paths: Paths, reg: Registry, only: list[str] | None) -> dict[str, SourceFetch]:
    typer.echo("fetch")
    results = fetch_all(paths, reg, only=only)
    _print_fetch(results)
    return results


def _do_build(paths: Paths, reg: Registry, force: bool) -> BuildReport:
    typer.echo("build")
    report = build_and_export(paths, reg, discover(paths), force=force)
    _print_build(report)
    return report


@app.command()
def fetch(source: SourceOpt = None) -> None:
    """Re-check licence quotes and download every automatic source; snapshot new bytes."""
    paths = _paths()
    reg = load_registry(paths)
    results: dict[str, SourceFetch] = {}
    try:
        results = _do_fetch(paths, reg, source)
    finally:
        update_status(paths, reg, fetched=results)
    if any(r.state == "failed" for r in results.values()):
        raise typer.Exit(1)


@app.command()
def build(
    force: Annotated[bool, typer.Option(help="Re-run every transform even if its build key is unchanged.")] = False,
) -> None:
    """Run transforms, validate, cross-check and export to data/ and data-private/."""
    paths = _paths()
    reg = load_registry(paths)
    report: BuildReport | None = None
    try:
        report = _do_build(paths, reg, force)
    finally:
        update_status(paths, reg, built=report)
    if not report.ok:
        raise typer.Exit(1)


@app.command()
def validate(
    registry_only: Annotated[
        bool, typer.Option(help="Only check that every source and literature entry loads.")
    ] = False,
) -> None:
    """Check the registry, snapshot manifests and every published file."""
    paths = _paths()
    reg = load_registry(paths)
    problems = (
        [*reg.source_errors.values(), *reg.literature_errors.values()] if registry_only else validate_all(paths, reg)
    )
    for p in problems:
        typer.echo(f"  problem: {p}")
    typer.echo(f"validate: {len(problems)} problem(s)")
    if problems:
        raise typer.Exit(1)


@app.command()
def refresh(
    source: SourceOpt = None,
    force: Annotated[bool, typer.Option(help="Re-run every transform.")] = False,
) -> None:
    """fetch -> build -> validate -> status. Exits non-zero if any source failed, after writing what succeeded."""
    paths = _paths()
    reg = load_registry(paths)
    fetched: dict[str, SourceFetch] = {}
    report: BuildReport | None = None
    problems: list[str] = []
    try:
        fetched = _do_fetch(paths, reg, source)
        report = _do_build(paths, reg, force)
        typer.echo("validate")
        problems = validate_all(paths, reg)
        for p in problems:
            typer.echo(f"  problem: {p}")
        typer.echo(f"  {len(problems)} problem(s)")
    finally:
        status = update_status(paths, reg, fetched=fetched, built=report)
        typer.echo(f"status: {paths.rel(paths.status_file)} at {status.generated_at}")
    failed = [s for s, r in status.sources.items() if r.state == "failed" and (not source or s in source)]
    if failed or problems or report is None or not report.ok:
        if failed:
            typer.echo(f"failed sources: {', '.join(failed)}")
        raise typer.Exit(1)


@snapshot_app.command("add")
def snapshot_add(
    source: Annotated[str, typer.Option(help="Source id.")],
    artifact: Annotated[str, typer.Option(help="Artifact id within the source.")],
    file: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True, help="The downloaded file.")],
    note: Annotated[str, typer.Option(help="Who downloaded it, from where, how (e.g. after a licence click-through).")],
    url: Annotated[str | None, typer.Option(help="The page or link it was downloaded from, if any.")] = None,
    accessed: Annotated[str | None, typer.Option(help="Download date YYYY-MM-DD (default today).")] = None,
) -> None:
    """Record a file a person downloaded (manual acquisition) and make it the current snapshot of that artifact."""
    paths = _paths()
    reg = load_registry(paths)
    src = reg.sources.get(source)
    if src is None:
        typer.echo(reg.source_errors.get(source, f"unknown source {source!r}"), err=True)
        raise typer.Exit(2)
    art = next((a for a in src.artifacts if a.id == artifact), None)
    if art is None:
        typer.echo(f"{source} has no artifact {artifact!r} (has: {[a.id for a in src.artifacts]})", err=True)
        raise typer.Exit(2)
    data = file.read_bytes()
    if len(data) > art.max_bytes:
        typer.echo(f"{file} is {len(data):,} bytes, over the artifact's limit of {art.max_bytes:,}", err=True)
        raise typer.Exit(2)
    snap, new = snapshots.record(
        paths,
        data=data,
        source_id=source,
        artifact_id=artifact,
        url=url,
        acquisition="manual",
        today=date.fromisoformat(accessed) if accessed else date.today(),
        note=note,
    )
    snapshots.set_current(paths, {snapshots.key(source, artifact): snap.sha256})
    typer.echo(
        f"{'recorded' if new else 'already recorded'} {snap.sha256} ({snap.bytes:,} bytes) for {source}/{artifact}"
    )
    if src.acquisition == "manual":
        update_status(paths, reg, fetched={source: SourceFetch(source, "manual", now_iso())})


@app.command("archive")
def archive_cmd(
    source: SourceOpt = None,
    r2: Annotated[bool, typer.Option(help="Upload snapshots to R2.")] = True,
    wayback: Annotated[bool, typer.Option(help="Submit pages and open data files to the Wayback Machine.")] = True,
) -> None:
    """Upload raw snapshots to R2 (public or private bucket by licence) and request Wayback captures."""
    paths = _paths()
    reg = load_registry(paths)
    sources = {k: v for k, v in reg.sources.items() if not source or k in source}
    if r2:
        try:
            client = archive_mod.r2_client()
        except archive_mod.ArchiveConfigError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(1) from None
        failures = 0
        for snap in snapshots.all_manifests(paths):  # pragma: no cover - needs R2
            if snap.source_id not in sources:
                continue
            try:
                done = archive_mod.upload_snapshot(paths, client, snap, sources[snap.source_id])
                typer.echo(f"  r2 {done.r2_bucket}/{done.r2_key}")
            except Exception as e:
                failures += 1
                typer.echo(f"  r2 failed {snap.sha256}: {type(e).__name__}: {e}")
        if failures:
            raise typer.Exit(1)
    if wayback:
        for url, cap in archive_mod.wayback_all(paths, sources).items():
            typer.echo(f"  wayback {cap.status:<8} {url}" + (f" ({cap.reason})" if cap.reason else ""))


@app.command()
def status() -> None:
    """Show data/v1/status.json."""
    paths = _paths()
    st = read_status(paths)
    if st is None:
        typer.echo("no status yet (run envdash refresh)")
        raise typer.Exit(1)
    typer.echo(f"generated {st.generated_at}" + (f" by {st.run_url}" if st.run_url else ""))
    for sid, s in st.sources.items():
        extra = f" vintage {s.vintage}" if s.vintage else ""
        extra += f" terms {s.terms}" if s.terms else ""
        typer.echo(f"  {s.state:<9} {sid}{extra} (checked {s.checked_at}, last success {s.last_success})")
        if s.reason:
            typer.echo(f"            {s.reason}")


@app.command()
def openapi(
    stdout: Annotated[bool, typer.Option(help="Print the document instead of writing it (for drift checks).")] = False,
) -> None:
    """Write pipeline/schema/openapi.json from the models."""
    paths = _paths()
    if stdout:
        typer.echo(canonical.dump_bytes(openapi_mod.document()).decode(), nl=False)
        return
    changed = openapi_mod.write(paths)
    typer.echo(f"{paths.rel(paths.schema / 'openapi.json')} {'written' if changed else 'unchanged'}")


def _r2_or_exit():
    try:
        return archive_mod.r2_client()
    except archive_mod.ArchiveConfigError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from None


@private_app.command("push")
def private_push() -> None:
    """Upload every private export the catalogue lists to the private bucket (after a build)."""
    paths = _paths()
    try:
        done = private_mod.push(paths, _r2_or_exit())
    except private_mod.PrivateExportError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from None
    typer.echo(f"private push: {len(done)} export(s)")


@private_app.command("pull")
def private_pull() -> None:
    """Download every private export the catalogue lists, checking each against the catalogue hash."""
    paths = _paths()
    try:
        entries = private_mod.private_entries(paths)
        if not entries:
            typer.echo("private pull: the catalogue lists no private exports")
            return
        done = private_mod.pull(paths, _r2_or_exit())
    except private_mod.PrivateExportError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from None
    typer.echo(f"private pull: {len(done)} export(s) present and verified")


@app.command("report-issues")
def report_issues() -> None:
    """Open, update or close one GitHub issue per failed source, and file release-due issues."""
    paths = _paths()
    for p in issues_mod.apply(paths, load_registry(paths), date.today()):
        typer.echo(f"  {p.action:<7} {p.title}" + (f" (#{p.number})" if p.number else ""))


if __name__ == "__main__":  # pragma: no cover
    app()
