"""`envdash report-issues`: turn the run's status into GitHub issues, one per problem, never one per run.

- A failed source has exactly one open issue titled "[source] <id>" with the label `source-failure`. Its body is
  replaced with the latest reason each run (no weekly comment noise); it is closed with a comment when the source
  recovers.
- A source whose `next_release.expected` date has passed gets one issue titled "[release due] <id>" with the label
  `release-due`, for the data-steward routine to pick up. It is never re-opened by this command.

Uses the GitHub CLI (`gh`) with GH_TOKEN, as in the workflow. Prints what it did; raises if gh is unavailable.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date

from envdash.paths import Paths
from envdash.registry import Registry
from envdash.status import read_status

FAILURE_LABEL = "source-failure"
RELEASE_LABEL = "release-due"


@dataclass(frozen=True)
class Planned:
    action: str  # open | update | close | release
    source_id: str
    title: str
    body: str
    number: int | None = None


def failure_title(source_id: str) -> str:
    return f"[source] {source_id}"


def release_title(source_id: str) -> str:
    return f"[release due] {source_id}"


def plan(
    paths: Paths,
    registry: Registry,
    open_failures: dict[str, int],
    known_release: set[str],
    today: date,
) -> list[Planned]:
    """What to do, given the open failure issues (title -> number) and every release-due title ever filed."""
    status = read_status(paths)
    if status is None:
        raise RuntimeError("no data/v1/status.json; run envdash refresh first")
    out: list[Planned] = []
    run = f"\n\nRun: {status.run_url}" if status.run_url else ""
    for sid, s in status.sources.items():
        title = failure_title(sid)
        if s.state == "failed":
            body = (
                f"`{sid}` failed on {s.checked_at}.\n\n> {s.reason}\n\n"
                f"The site keeps showing its last validated vintage ({s.vintage or 'none yet'}); /status says so."
                f"{run}"
            )
            out.append(
                Planned("update" if title in open_failures else "open", sid, title, body, open_failures.get(title))
            )
        elif title in open_failures:
            out.append(
                Planned(
                    "close",
                    sid,
                    title,
                    f"Recovered: `{sid}` is {s.state} as of {s.checked_at}.{run}",
                    open_failures[title],
                )
            )
    for sid, src in registry.sources.items():
        nr = src.next_release
        if nr and nr.expected <= today and release_title(sid) not in known_release:
            body = (
                f"`{sid}` expected a new release on {nr.expected}: {nr.note}"
                + (f"\n\n{nr.url}" if nr.url else "")
                + "\n\nCheck for the new vintage, snapshot it, add the producer's newly stated values as publisher "
                "cross-checks, and update `next_release` in the source entry."
            )
            out.append(Planned("release", sid, release_title(sid), body))
    return out


def _gh(*args: str) -> str:  # pragma: no cover - needs gh and a token
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def apply(paths: Paths, registry: Registry, today: date) -> list[Planned]:  # pragma: no cover - needs gh
    if shutil.which("gh") is None:
        raise RuntimeError("the GitHub CLI (gh) is not installed")
    for label, colour in ((FAILURE_LABEL, "d73a4a"), (RELEASE_LABEL, "0e8a16")):
        subprocess.run(["gh", "label", "create", label, "--color", colour, "--force"], check=True, capture_output=True)
    open_failures = {
        i["title"]: i["number"]
        for i in json.loads(
            _gh(
                "issue", "list", "--label", FAILURE_LABEL, "--state", "open", "--limit", "500", "--json", "title,number"
            )
        )
    }
    known_release = {
        i["title"]
        for i in json.loads(
            _gh("issue", "list", "--label", RELEASE_LABEL, "--state", "all", "--limit", "1000", "--json", "title")
        )
    }
    planned = plan(paths, registry, open_failures, known_release, today)
    for p in planned:
        if p.action == "open":
            _gh("issue", "create", "--title", p.title, "--label", FAILURE_LABEL, "--body", p.body)
        elif p.action == "update":
            _gh("issue", "edit", str(p.number), "--body", p.body)
        elif p.action == "close":
            _gh("issue", "close", str(p.number), "--comment", p.body)
        elif p.action == "release":
            _gh("issue", "create", "--title", p.title, "--label", RELEASE_LABEL, "--body", p.body)
    return planned
