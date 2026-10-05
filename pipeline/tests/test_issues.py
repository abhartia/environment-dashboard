from __future__ import annotations

from datetime import date

from envdash.fetch import SourceFetch
from envdash.issues import failure_title, plan, release_title
from envdash.registry import load_registry
from envdash.status import update_status


def test_one_issue_per_failed_source_updated_then_closed(tmp_paths):
    reg = load_registry(tmp_paths)
    update_status(
        tmp_paths,
        reg,
        fetched={
            "hadcrut5": SourceFetch("hadcrut5", "failed", "2026-10-05T04:17:00Z", reason="HTTP 503 from Met Office"),
            "noaa-gml-trends": SourceFetch("noaa-gml-trends", "ok", "2026-10-05T04:17:01Z"),
        },
    )
    early = date(2026, 10, 1)  # before noaa-gml-trends' expected release, so only the failure matters

    first = plan(tmp_paths, reg, open_failures={}, known_release=set(), today=early)
    assert [(p.action, p.source_id) for p in first] == [("open", "hadcrut5")]
    assert "HTTP 503 from Met Office" in first[0].body

    # Still failing next week: the existing issue is updated, not duplicated.
    again = plan(tmp_paths, reg, open_failures={failure_title("hadcrut5"): 7}, known_release=set(), today=early)
    assert [(p.action, p.number) for p in again] == [("update", 7)]

    # Recovered: the issue is closed.
    update_status(tmp_paths, reg, fetched={"hadcrut5": SourceFetch("hadcrut5", "ok", "2026-10-12T04:17:00Z")})
    done = plan(tmp_paths, reg, open_failures={failure_title("hadcrut5"): 7}, known_release=set(), today=early)
    assert [(p.action, p.number) for p in done] == [("close", 7)]


def test_release_due_filed_once(tmp_paths):
    reg = load_registry(tmp_paths)
    update_status(tmp_paths, reg)
    expected = reg.sources["noaa-gml-trends"].next_release.expected
    due = plan(tmp_paths, reg, open_failures={}, known_release=set(), today=expected)
    assert ("release", "noaa-gml-trends") in [(p.action, p.source_id) for p in due]
    filed = plan(tmp_paths, reg, open_failures={}, known_release={release_title("noaa-gml-trends")}, today=expected)
    assert "noaa-gml-trends" not in [p.source_id for p in filed]
