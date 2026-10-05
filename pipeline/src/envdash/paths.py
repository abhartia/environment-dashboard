"""Where everything lives. Commands take a Paths so tests can redirect outputs to a temporary directory."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Paths:
    repo: Path
    sources: Path
    literature: Path
    manifests: Path
    cache: Path
    data: Path
    private: Path
    schema: Path
    lock: Path

    @classmethod
    def default(cls, repo: Path = REPO_ROOT) -> Paths:
        pipeline = repo / "pipeline"
        return cls(
            repo=repo,
            sources=pipeline / "sources",
            literature=pipeline / "literature",
            manifests=pipeline / "manifests",
            cache=pipeline / ".snapshots",
            data=repo / "data",
            private=repo / "data-private",
            schema=pipeline / "schema",
            lock=pipeline / "uv.lock",
        )

    def with_(self, **changes: Path) -> Paths:
        return replace(self, **changes)

    # snapshot store
    @property
    def snapshot_manifests(self) -> Path:
        return self.manifests / "snapshots"

    @property
    def current(self) -> Path:
        """Which snapshot each (source, artifact) builds from: the newest complete fetch of its source."""
        return self.manifests / "current.json"

    @property
    def builds(self) -> Path:
        """Build keys of the last export of each indicator (what lets an unchanged indicator skip its transform)."""
        return self.manifests / "builds"

    @property
    def wayback(self) -> Path:
        return self.manifests / "wayback"

    # exports
    @property
    def public_indicators(self) -> Path:
        return self.data / "v1" / "indicators"

    @property
    def private_indicators(self) -> Path:
        return self.private / "v1" / "indicators"

    @property
    def status_file(self) -> Path:
        return self.data / "v1" / "status.json"

    def rel(self, path: Path) -> str:
        """Repo-relative POSIX path, as recorded in exports (absolute for a path outside the repo, e.g. in tests)."""
        try:
            return path.resolve().relative_to(self.repo.resolve()).as_posix()
        except ValueError:
            return path.resolve().as_posix()
