"""KAV Memory — project-local persistence for the research loop.

One SQLite file per project (Law 4: memory never crosses projects).
Stores the five contracts; findings are immutable, superseded only (Law 3).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from kav_sdk.models import (
    ExperimentResult, ExperimentSpec, ProjectManifest, ResearchFinding,
    SearchSpace,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS manifests (
    project_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS search_spaces (
    project_id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experiments (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL,
    hypothesis_id TEXT NOT NULL,
    spec TEXT NOT NULL,
    result TEXT,
    status TEXT,
    metric_value REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS findings (
    finding_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    experiment_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    statement TEXT NOT NULL,
    confidence REAL NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    data TEXT NOT NULL,
    superseded_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_findings_kind ON findings(project_id, kind);
CREATE TABLE IF NOT EXISTS champion (
    project_id TEXT PRIMARY KEY,
    config TEXT NOT NULL,
    metric_value REAL NOT NULL,
    experiment_id TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class ProjectMemory:
    """The filing cabinet for exactly one project."""

    def __init__(self, root: str | Path, project_id: str):
        self.project_id = project_id
        self.path = Path(root) / f"{project_id}.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------- manifest
    def save_manifest(self, m: ProjectManifest) -> None:
        self._assert_project(m.project_id)
        self.conn.execute(
            "INSERT OR REPLACE INTO manifests (project_id, data) VALUES (?, ?)",
            (m.project_id, m.model_dump_json()),
        )
        self.conn.commit()

    def get_manifest(self) -> ProjectManifest | None:
        row = self.conn.execute(
            "SELECT data FROM manifests WHERE project_id=?", (self.project_id,)
        ).fetchone()
        return ProjectManifest.model_validate_json(row["data"]) if row else None

    # ---------------------------------------------------------- search space
    def save_search_space(self, s: SearchSpace) -> None:
        self._assert_project(s.project_id)
        self.conn.execute(
            "INSERT OR REPLACE INTO search_spaces (project_id, data) VALUES (?, ?)",
            (s.project_id, s.model_dump_json()),
        )
        self.conn.commit()

    def get_search_space(self) -> SearchSpace | None:
        row = self.conn.execute(
            "SELECT data FROM search_spaces WHERE project_id=?", (self.project_id,)
        ).fetchone()
        return SearchSpace.model_validate_json(row["data"]) if row else None

    # ------------------------------------------------------------ experiments
    def save_spec(self, spec: ExperimentSpec) -> None:
        self._assert_project(spec.project_id)
        self.conn.execute(
            "INSERT OR REPLACE INTO experiments (experiment_id, project_id, hypothesis_id, spec)"
            " VALUES (?, ?, ?, ?)",
            (spec.experiment_id, spec.project_id, spec.hypothesis_id, spec.model_dump_json()),
        )
        self.conn.commit()

    def save_result(self, result: ExperimentResult) -> None:
        if not self._experiment_exists(result.experiment_id):
            raise KeyError(f"unknown experiment: {result.experiment_id}")
        self.conn.execute(
            "UPDATE experiments SET result=?, status=?, metric_value=? WHERE experiment_id=?",
            (
                result.model_dump_json(),
                result.status.value,
                result.evidence.metric_value,
                result.experiment_id,
            ),
        )
        self.conn.commit()

    def get_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM experiments WHERE experiment_id=?", (experiment_id,)
        ).fetchone()
        return dict(row) if row else None

    def recent_experiments(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM experiments WHERE project_id=? ORDER BY seq DESC LIMIT ?",
            (self.project_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def consecutive_failures(self) -> int:
        """Circuit-breaker input (ADR-004): length of the current failure streak."""
        rows = self.conn.execute(
            "SELECT status FROM experiments WHERE project_id=? "
            "ORDER BY seq DESC LIMIT 10",
            (self.project_id,),
        ).fetchall()
        n = 0
        for r in rows:
            if r["status"] in ("failed", "timeout", "rejected"):
                n += 1
            else:
                break
        return n

    # --------------------------------------------------------------- findings
    def save_finding(self, f: ResearchFinding) -> None:
        """Findings are immutable once written (Law 3). Supersede instead of delete."""
        import json

        if self._finding_exists(f.finding_id):
            raise ValueError(f"finding {f.finding_id} already exists — findings are immutable")
        self._assert_project(f.project_id)
        self.conn.execute(
            "INSERT INTO findings (finding_id, project_id, experiment_id, kind, statement,"
            " confidence, tags, data) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f.finding_id, f.project_id, f.experiment_id, f.kind.value,
                f.statement, f.confidence, json.dumps(f.tags), f.model_dump_json(),
            ),
        )
        self.conn.commit()

    def supersede_finding(self, old_id: str, new_finding: ResearchFinding) -> None:
        self.save_finding(new_finding)
        self.conn.execute(
            "UPDATE findings SET superseded_by=? WHERE finding_id=?", (new_finding.finding_id, old_id)
        )
        self.conn.commit()

    def active_findings(self, kinds: list[str] | None = None, limit: int = 50) -> list[ResearchFinding]:
        """Non-superseded findings — the top-k context source (ADR-004 Q1)."""
        q = ("SELECT data FROM findings WHERE project_id=? AND superseded_by IS NULL")
        args: list[Any] = [self.project_id]
        if kinds:
            q += f" AND kind IN ({','.join('?' * len(kinds))})"
            args.extend(kinds)
        q += " ORDER BY confidence DESC LIMIT ?"
        args.append(limit)
        return [ResearchFinding.model_validate_json(r["data"])
                for r in self.conn.execute(q, args).fetchall()]

    # ---------------------------------------------------------------- champion
    def get_champion(self) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM champion WHERE project_id=?", (self.project_id,)
        ).fetchone()
        return dict(row) if row else None

    def set_champion(self, config: dict[str, Any], metric_value: float, experiment_id: str) -> None:
        import json

        self.conn.execute(
            "INSERT OR REPLACE INTO champion (project_id, config, metric_value, experiment_id)"
            " VALUES (?, ?, ?, ?)",
            (self.project_id, json.dumps(config), metric_value, experiment_id),
        )
        self.conn.commit()

    # ----------------------------------------------------------------- internal
    def _assert_project(self, pid: str) -> None:
        if pid != self.project_id:
            raise ValueError(f"Law 4: record belongs to '{pid}', memory is '{self.project_id}'")

    def _experiment_exists(self, eid: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM experiments WHERE experiment_id=?", (eid,)
        ).fetchone() is not None

    def _finding_exists(self, fid: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM findings WHERE finding_id=?", (fid,)
        ).fetchone() is not None
