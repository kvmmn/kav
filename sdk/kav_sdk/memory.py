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
    started_at TEXT,
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
CREATE TABLE IF NOT EXISTS strategy_halt (
    project_id TEXT PRIMARY KEY,
    halted INTEGER NOT NULL DEFAULT 0,
    signature TEXT,
    experiment_id TEXT,
    finding_id TEXT,
    reason TEXT,
    halted_at TEXT
);
CREATE TABLE IF NOT EXISTS promotion_policy (
    project_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL DEFAULT 'manual',
    min_delta REAL NOT NULL DEFAULT 0,
    confirmations INTEGER NOT NULL DEFAULT 2
);
CREATE TABLE IF NOT EXISTS desk_policy (
    project_id TEXT PRIMARY KEY,
    k INTEGER NOT NULL DEFAULT 10,
    rejuvenation_every INTEGER NOT NULL DEFAULT 8,
    plateau_window INTEGER NOT NULL DEFAULT 5,
    mode TEXT NOT NULL DEFAULT 'minimal'
);
CREATE TABLE IF NOT EXISTS rejuvenation_desk (
    project_id TEXT NOT NULL,
    finding_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    placed_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (project_id, finding_id)
);
CREATE TABLE IF NOT EXISTS rejuvenation_state (
    project_id TEXT PRIMARY KEY,
    last_reason TEXT,
    last_at_completed INTEGER,
    last_finding_id TEXT
);
CREATE TABLE IF NOT EXISTS execution_policy (
    project_id TEXT PRIMARY KEY,
    max_inflight INTEGER NOT NULL DEFAULT 2
);
CREATE TABLE IF NOT EXISTS wake_events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    experiment_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    consumed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_FAIL_STATUSES = frozenset({"failed", "timeout", "rejected"})
CIRCUIT_BREAKER_THRESHOLD = 3
PROMOTION_MANUAL = "manual"
PROMOTION_AUTO_GUARDED = "auto_guarded"
_PROMOTION_MODES = frozenset({PROMOTION_MANUAL, PROMOTION_AUTO_GUARDED})
DEFAULT_MIN_DELTA = 0.0
DEFAULT_CONFIRMATIONS = 2
DEFAULT_DESK_K = 10
DEFAULT_REJUVENATION_EVERY = 8
DEFAULT_PLATEAU_WINDOW = 5
DEFAULT_DIGEST_CAP = 30
DESK_MINIMAL = "minimal"
DESK_RICH_DIGEST = "rich_digest"
_DESK_MODES = frozenset({DESK_MINIMAL, DESK_RICH_DIGEST})
DEFAULT_MAX_INFLIGHT = 2
WAKE_RESULT_INGESTED = "result_ingested"


class ProjectMemory:
    """The filing cabinet for exactly one project."""

    def __init__(self, root: str | Path, project_id: str):
        self.project_id = project_id
        self.path = Path(root) / f"{project_id}.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self._migrate_experiments_started_at()
        self._migrate_desk_policy_mode()
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
        self.apply_manifest_policy(m)

    def apply_manifest_policy(self, m: ProjectManifest) -> None:
        """Seed promotion, desk, and execution policy from the host (D-032–D-035).

        Manifest is the source of truth on attach. Omitted `policy` is `manual`.
        Declared `min_delta` / `confirmations` seed local tunables; omitted
        fields keep the current project-local values (defaults 0 and 2).
        Declared `desk` seeds `desk_policy.mode`; omitted keeps local
        (default `minimal`). k / rejuvenation_every / plateau_window stay local.
        Declared `max_inflight` seeds `execution_policy`; omitted keeps local
        (default 2).
        """
        current = self.get_promotion_policy()
        min_delta = m.promotion_min_delta()
        confirmations = m.promotion_confirmations()
        self.set_promotion_policy(
            mode=m.promotion_mode(),
            min_delta=current["min_delta"] if min_delta is None else min_delta,
            confirmations=(
                current["confirmations"] if confirmations is None else confirmations
            ),
        )
        desk_mode = m.desk_mode()
        if desk_mode is not None:
            desk = self.get_desk_policy()
            self.set_desk_policy(
                k=desk["k"],
                rejuvenation_every=desk["rejuvenation_every"],
                plateau_window=desk["plateau_window"],
                mode=desk_mode,
            )
        max_inflight = m.execution_max_inflight()
        if max_inflight is not None:
            self.set_execution_policy(max_inflight=max_inflight)

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
        self.record_wake(result.experiment_id, WAKE_RESULT_INGESTED)
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

    def pending_specs(self) -> list[ExperimentSpec]:
        """Issued specs not yet started, oldest first (FIFO). In-flight are excluded."""
        rows = self.conn.execute(
            "SELECT spec FROM experiments WHERE project_id=? AND result IS NULL "
            "AND started_at IS NULL ORDER BY seq ASC",
            (self.project_id,),
        ).fetchall()
        return [ExperimentSpec.model_validate_json(r["spec"]) for r in rows]

    def inflight_specs(self) -> list[ExperimentSpec]:
        """Started specs whose result is still NULL, oldest first."""
        rows = self.conn.execute(
            "SELECT spec FROM experiments WHERE project_id=? AND result IS NULL "
            "AND started_at IS NOT NULL ORDER BY seq ASC",
            (self.project_id,),
        ).fetchall()
        return [ExperimentSpec.model_validate_json(r["spec"]) for r in rows]

    def mark_started(self, experiment_id: str) -> None:
        """Mark a queued spec as in-flight (D-030). No-op if already started or done."""
        if not self._experiment_exists(experiment_id):
            raise KeyError(f"unknown experiment: {experiment_id}")
        self.conn.execute(
            "UPDATE experiments SET started_at=datetime('now') "
            "WHERE experiment_id=? AND result IS NULL AND started_at IS NULL",
            (experiment_id,),
        )
        self.conn.commit()

    def get_execution_policy(self) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT max_inflight FROM execution_policy WHERE project_id=?",
            (self.project_id,),
        ).fetchone()
        if row is None:
            return {"max_inflight": DEFAULT_MAX_INFLIGHT}
        return {"max_inflight": int(row["max_inflight"])}

    def set_execution_policy(self, max_inflight: int = DEFAULT_MAX_INFLIGHT) -> None:
        if max_inflight < 1:
            raise ValueError("max_inflight must be >= 1")
        self.conn.execute(
            "INSERT OR REPLACE INTO execution_policy (project_id, max_inflight) "
            "VALUES (?, ?)",
            (self.project_id, max_inflight),
        )
        self.conn.commit()

    def record_wake(self, experiment_id: str, kind: str = WAKE_RESULT_INGESTED) -> None:
        """Queue an event-driven wake (ADR-004 Q2 / D-030). Caller commits."""
        self.conn.execute(
            "INSERT INTO wake_events (project_id, experiment_id, kind) VALUES (?, ?, ?)",
            (self.project_id, experiment_id, kind),
        )

    def unconsumed_wakes(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT seq, experiment_id, kind, created_at FROM wake_events "
            "WHERE project_id=? AND consumed=0 ORDER BY seq ASC",
            (self.project_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def consume_wakes(self) -> list[dict[str, Any]]:
        """Return and mark unconsumed wakes (OBSERVE delivery)."""
        wakes = self.unconsumed_wakes()
        if not wakes:
            return []
        ids = [w["seq"] for w in wakes]
        self.conn.execute(
            f"UPDATE wake_events SET consumed=1 WHERE seq IN ({','.join('?' * len(ids))})",
            ids,
        )
        self.conn.commit()
        return wakes

    def consecutive_failures(self) -> int:
        """Length of the current failure streak (any failed/timeout/rejected)."""
        rows = self.conn.execute(
            "SELECT status FROM experiments WHERE project_id=? "
            "AND status IS NOT NULL ORDER BY seq DESC LIMIT 10",
            (self.project_id,),
        ).fetchall()
        n = 0
        for r in rows:
            if r["status"] in _FAIL_STATUSES:
                n += 1
            else:
                break
        return n

    @staticmethod
    def spec_signature(spec: ExperimentSpec) -> str:
        """Structural identity: sorted unique changed parameter names (ADR-004 Q3)."""
        return ",".join(sorted({c.parameter for c in spec.changes}))

    def consecutive_similar_failures(self) -> int:
        """Failure streak sharing the most recent failure's spec signature."""
        rows = self.conn.execute(
            "SELECT status, spec FROM experiments WHERE project_id=? "
            "AND status IS NOT NULL ORDER BY seq DESC LIMIT 20",
            (self.project_id,),
        ).fetchall()
        if not rows or rows[0]["status"] not in _FAIL_STATUSES:
            return 0
        signature = self.spec_signature(ExperimentSpec.model_validate_json(rows[0]["spec"]))
        n = 0
        for r in rows:
            if r["status"] not in _FAIL_STATUSES:
                break
            if self.spec_signature(ExperimentSpec.model_validate_json(r["spec"])) != signature:
                break
            n += 1
        return n

    def is_halted(self) -> bool:
        row = self.conn.execute(
            "SELECT halted FROM strategy_halt WHERE project_id=?", (self.project_id,)
        ).fetchone()
        return bool(row and row["halted"])

    def halt_state(self) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM strategy_halt WHERE project_id=?", (self.project_id,)
        ).fetchone()
        return dict(row) if row else None

    def evaluate_circuit_breaker(self, result: ExperimentResult) -> bool:
        """Halt + operational alert when 3 similar consecutive failures land (D-027).

        Returns True when the strategy is (now, or already) halted.
        """
        if self.is_halted():
            return True
        if result.status.value not in _FAIL_STATUSES:
            return False
        if self.consecutive_similar_failures() < CIRCUIT_BREAKER_THRESHOLD:
            return False
        row = self.get_experiment(result.experiment_id)
        if row is None:
            raise KeyError(f"unknown experiment: {result.experiment_id}")
        spec = ExperimentSpec.model_validate_json(row["spec"])
        signature = self.spec_signature(spec)
        suffix = result.experiment_id.removeprefix("exp-")
        finding = ResearchFinding(
            finding_id=f"fnd-halt-{suffix}"[:68],
            project_id=self.project_id,
            experiment_id=result.experiment_id,
            hypothesis_id=spec.hypothesis_id,
            kind="operational",
            statement=(
                f"Circuit breaker halted the current strategy after "
                f"{CIRCUIT_BREAKER_THRESHOLD} consecutive similar failures "
                f"on parameters [{signature or 'none'}]."
            ),
            confidence=0.9,
            tags=list(dict.fromkeys(
                ["circuit-breaker", "halt", *[p for p in signature.split(",") if p][:8]]
            )),
            conditions={"config_snapshot": {"signature": signature, "status": result.status.value}},
        )
        self.save_finding(finding)
        self.conn.execute(
            "INSERT OR REPLACE INTO strategy_halt "
            "(project_id, halted, signature, experiment_id, finding_id, reason, halted_at) "
            "VALUES (?, 1, ?, ?, ?, ?, datetime('now'))",
            (
                self.project_id,
                signature,
                result.experiment_id,
                finding.finding_id,
                finding.statement,
            ),
        )
        self.conn.commit()
        return True

    def clear_halt(self) -> None:
        """Human resume of a halted strategy (does not delete the alert finding)."""
        if not self.is_halted():
            return
        self.conn.execute(
            "UPDATE strategy_halt SET halted=0 WHERE project_id=?",
            (self.project_id,),
        )
        self.conn.commit()

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

    # -------------------------------------------------------- promotion policy
    def get_promotion_policy(self) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT mode, min_delta, confirmations FROM promotion_policy WHERE project_id=?",
            (self.project_id,),
        ).fetchone()
        if row is None:
            return {
                "mode": PROMOTION_MANUAL,
                "min_delta": DEFAULT_MIN_DELTA,
                "confirmations": DEFAULT_CONFIRMATIONS,
            }
        return {
            "mode": row["mode"],
            "min_delta": float(row["min_delta"]),
            "confirmations": int(row["confirmations"]),
        }

    def set_promotion_policy(
        self,
        mode: str = PROMOTION_MANUAL,
        min_delta: float = DEFAULT_MIN_DELTA,
        confirmations: int = DEFAULT_CONFIRMATIONS,
    ) -> None:
        if mode not in _PROMOTION_MODES:
            raise ValueError(f"unknown promotion mode: {mode}")
        if confirmations < 1:
            raise ValueError("confirmations must be >= 1")
        if min_delta < 0:
            raise ValueError("min_delta must be >= 0")
        self.conn.execute(
            "INSERT OR REPLACE INTO promotion_policy "
            "(project_id, mode, min_delta, confirmations) VALUES (?, ?, ?, ?)",
            (self.project_id, mode, min_delta, confirmations),
        )
        self.conn.commit()

    # -------------------------------------------------------------- desk (Q1)
    def get_desk_policy(self) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT k, rejuvenation_every, plateau_window, mode FROM desk_policy "
            "WHERE project_id=?",
            (self.project_id,),
        ).fetchone()
        if row is None:
            return {
                "k": DEFAULT_DESK_K,
                "rejuvenation_every": DEFAULT_REJUVENATION_EVERY,
                "plateau_window": DEFAULT_PLATEAU_WINDOW,
                "mode": DESK_MINIMAL,
            }
        stored_mode = row["mode"] if "mode" in row.keys() and row["mode"] else DESK_MINIMAL
        return {
            "k": int(row["k"]),
            "rejuvenation_every": int(row["rejuvenation_every"]),
            "plateau_window": int(row["plateau_window"]),
            "mode": stored_mode,
        }

    def set_desk_policy(
        self,
        k: int = DEFAULT_DESK_K,
        rejuvenation_every: int = DEFAULT_REJUVENATION_EVERY,
        plateau_window: int = DEFAULT_PLATEAU_WINDOW,
        mode: str | None = None,
    ) -> None:
        if k < 1:
            raise ValueError("k must be >= 1")
        if rejuvenation_every < 1:
            raise ValueError("rejuvenation_every must be >= 1")
        if plateau_window < 1:
            raise ValueError("plateau_window must be >= 1")
        if mode is None:
            mode = self.get_desk_policy()["mode"]
        if mode not in _DESK_MODES:
            raise ValueError(f"unknown desk mode: {mode}")
        self.conn.execute(
            "INSERT OR REPLACE INTO desk_policy "
            "(project_id, k, rejuvenation_every, plateau_window, mode) "
            "VALUES (?, ?, ?, ?, ?)",
            (self.project_id, k, rejuvenation_every, plateau_window, mode),
        )
        self.conn.commit()

    def desk(self) -> dict[str, Any]:
        """OBSERVE graph state: champion + top-k + rejuvenated (D-029).

        `mode=minimal` (default) keeps graph state small. `mode=rich_digest`
        is the same retrieval plus a compact off-desk history digest (D-031).
        """
        policy = self.get_desk_policy()
        k = policy["k"]
        mode = policy["mode"]
        active = self.active_findings(limit=k)
        rejuvenated = self.rejuvenated_findings()
        active_ids = {f.finding_id for f in active}
        extra = [f for f in rejuvenated if f.finding_id not in active_ids]
        payload: dict[str, Any] = {
            "champion": self.get_champion(),
            "findings": [f.model_dump(mode="json") for f in active],
            "rejuvenated": [f.model_dump(mode="json") for f in extra],
            "k": k,
            "mode": mode,
        }
        if mode == DESK_RICH_DIGEST:
            payload["digest"] = self.history_digest(exclude_ids=active_ids)
        return payload

    def history_digest(self, exclude_ids: set[str] | None = None) -> dict[str, Any]:
        """Compact off-desk history for rich_digest mode (D-031). No schema change."""
        exclude = exclude_ids or set()
        rows = self.conn.execute(
            "SELECT data, superseded_by, kind FROM findings WHERE project_id=?",
            (self.project_id,),
        ).fetchall()
        by_kind: dict[str, int] = {}
        superseded = 0
        off: list[dict[str, Any]] = []
        for r in rows:
            finding = ResearchFinding.model_validate_json(r["data"])
            kind = finding.kind.value
            by_kind[kind] = by_kind.get(kind, 0) + 1
            if r["superseded_by"]:
                superseded += 1
            if finding.finding_id in exclude:
                continue
            off.append({
                "finding_id": finding.finding_id,
                "kind": kind,
                "statement": finding.statement,
                "confidence": finding.confidence,
                "tags": list(finding.tags),
                "superseded": bool(r["superseded_by"]),
            })
        off.sort(key=lambda item: item["confidence"], reverse=True)
        cap = max(self.get_desk_policy()["k"] * 3, DEFAULT_DIGEST_CAP)
        return {
            "total_findings": len(rows),
            "by_kind": by_kind,
            "superseded": superseded,
            "off_desk": off[:cap],
            "off_desk_truncated": max(0, len(off) - cap),
        }

    def discarded_findings(self, limit: int | None = None) -> list[ResearchFinding]:
        """Superseded findings, plus refuted findings that fell off the desk."""
        policy = self.get_desk_policy()
        cap = policy["k"] if limit is None else limit
        desk_ids = {f.finding_id for f in self.active_findings(limit=policy["k"])}
        rows = self.conn.execute(
            "SELECT data, superseded_by, kind FROM findings WHERE project_id=?",
            (self.project_id,),
        ).fetchall()
        out: list[ResearchFinding] = []
        for r in rows:
            finding = ResearchFinding.model_validate_json(r["data"])
            if r["superseded_by"]:
                out.append(finding)
            elif r["kind"] == "refuted" and finding.finding_id not in desk_ids:
                out.append(finding)
        out.sort(key=lambda item: item.confidence, reverse=True)
        return out[:cap]

    def rejuvenated_findings(self) -> list[ResearchFinding]:
        rows = self.conn.execute(
            "SELECT r.finding_id, f.data FROM rejuvenation_desk r "
            "JOIN findings f ON f.finding_id = r.finding_id "
            "WHERE r.project_id=? ORDER BY r.placed_at DESC",
            (self.project_id,),
        ).fetchall()
        return [ResearchFinding.model_validate_json(r["data"]) for r in rows]

    def completed_count(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM experiments WHERE project_id=? AND status='completed'",
            (self.project_id,),
        ).fetchone()
        return int(row["n"]) if row else 0

    def is_plateau(self) -> bool:
        """True when the last plateau_window completed runs do not beat the champion."""
        policy = self.get_desk_policy()
        window = policy["plateau_window"]
        champion = self.get_champion()
        manifest = self.get_manifest()
        if champion is None or manifest is None:
            return False
        rows = self.conn.execute(
            "SELECT metric_value, status FROM experiments WHERE project_id=? "
            "AND status IS NOT NULL ORDER BY seq DESC LIMIT ?",
            (self.project_id, window),
        ).fetchall()
        if len(rows) < window:
            return False
        champ_metric = float(champion["metric_value"])
        direction = manifest.objective.direction
        for r in rows:
            if r["status"] != "completed" or r["metric_value"] is None:
                return False
            if self._beats_champion(float(r["metric_value"]), champ_metric, direction, 0.0):
                return False
        return True

    def conditions_changed(self) -> bool:
        """True when the search space has a parameter unknown to discarded findings."""
        space = self.get_search_space()
        if space is None:
            return False
        params = {p.name for p in space.parameters}
        if not params:
            return False
        discarded = self.discarded_findings()
        if not discarded:
            return False
        known: set[str] = set()
        for finding in discarded:
            snap = finding.conditions.get("config_snapshot") if finding.conditions else None
            if isinstance(snap, dict):
                known.update(snap.keys())
            known.update(finding.tags)
        return bool(params - known)

    def evaluate_rejuvenation(self, force: bool = False) -> bool:
        """Re-surface discarded approaches onto the desk; write an operational notice.

        Triggers: plateau, periodic (every N completed runs), search-space change,
        or a human `rejuvenate` force. Returns True when the desk was updated.
        """
        policy = self.get_desk_policy()
        discarded = self.discarded_findings(limit=policy["k"])
        if not discarded:
            return False
        completed = self.completed_count()
        reasons: list[str] = []
        if force:
            reasons.append("manual")
        if self.is_plateau():
            reasons.append("plateau")
        every = policy["rejuvenation_every"]
        if every > 0 and completed >= every and completed % every == 0:
            reasons.append("periodic")
        if self.conditions_changed():
            reasons.append("conditions_changed")
        if not reasons:
            return False
        state = self.conn.execute(
            "SELECT last_at_completed FROM rejuvenation_state WHERE project_id=?",
            (self.project_id,),
        ).fetchone()
        if not force and state is not None and int(state["last_at_completed"]) == completed:
            return False
        last = self.conn.execute(
            "SELECT experiment_id, spec FROM experiments WHERE project_id=? "
            "AND status IS NOT NULL ORDER BY seq DESC LIMIT 1",
            (self.project_id,),
        ).fetchone()
        if last is None:
            return False
        experiment_id = last["experiment_id"]
        spec = ExperimentSpec.model_validate_json(last["spec"])
        reason = ",".join(reasons)
        self.conn.execute(
            "DELETE FROM rejuvenation_desk WHERE project_id=?", (self.project_id,)
        )
        for finding in discarded:
            self.conn.execute(
                "INSERT INTO rejuvenation_desk (project_id, finding_id, reason) "
                "VALUES (?, ?, ?)",
                (self.project_id, finding.finding_id, reason),
            )
        suffix = f"{completed:04d}-{experiment_id.removeprefix('exp-')}"
        notice = ResearchFinding(
            finding_id=f"fnd-reju-{suffix}"[:68],
            project_id=self.project_id,
            experiment_id=experiment_id,
            hypothesis_id=spec.hypothesis_id,
            kind="operational",
            statement=(
                f"Rejuvenation placed {len(discarded)} discarded approach(es) "
                f"back on the desk ({reason})."
            ),
            confidence=0.7,
            tags=list(dict.fromkeys(["rejuvenation", "desk", *reasons])),
            conditions={
                "config_snapshot": {
                    "reason": reason,
                    "finding_ids": [f.finding_id for f in discarded],
                    "completed": completed,
                }
            },
        )
        self.save_finding(notice)
        self.conn.execute(
            "INSERT OR REPLACE INTO rejuvenation_state "
            "(project_id, last_reason, last_at_completed, last_finding_id) "
            "VALUES (?, ?, ?, ?)",
            (self.project_id, reason, completed, notice.finding_id),
        )
        self.conn.commit()
        return True

    def reconstructed_config(self, spec: ExperimentSpec) -> dict[str, Any]:
        """Defaults + current champion overlay + this spec's changes (D-028)."""
        import json

        base: dict[str, Any] = {}
        space = self.get_search_space()
        if space is not None:
            base.update(space.defaults)
        champ = self.get_champion()
        if champ and champ.get("config"):
            cfg = champ["config"]
            if isinstance(cfg, str):
                cfg = json.loads(cfg)
            if isinstance(cfg, dict):
                base.update(cfg)
        for change in spec.changes:
            base[change.parameter] = change.value
        return base

    def evaluate_auto_guarded(self, finding: ResearchFinding) -> bool:
        """Promote when auto_guarded gates pass; write an operational notice (D-028).

        Returns True when a champion update was applied for this finding.
        """
        import json

        policy = self.get_promotion_policy()
        if policy["mode"] != PROMOTION_AUTO_GUARDED:
            return False
        if self.is_halted():
            return False
        if finding.kind.value != "confirmed":
            return False
        champion = self.get_champion()
        if champion is None:
            return False
        manifest = self.get_manifest()
        if manifest is None:
            return False
        row = self.get_experiment(finding.experiment_id)
        if row is None or row["status"] != "completed" or row["metric_value"] is None:
            return False
        spec = ExperimentSpec.model_validate_json(row["spec"])
        candidate = self.reconstructed_config(spec)
        identity = json.dumps(candidate, sort_keys=True, default=str)
        direction = manifest.objective.direction
        champ_metric = float(champion["metric_value"])
        min_delta = float(policy["min_delta"])
        needed = int(policy["confirmations"])

        confirmations: list[dict[str, Any]] = []
        seen_eids: set[str] = set()
        seen_seeds: set[int] = set()
        for f in self.active_findings(kinds=["confirmed"]):
            exp = self.get_experiment(f.experiment_id)
            if exp is None or exp["status"] != "completed" or exp["metric_value"] is None:
                continue
            if f.experiment_id in seen_eids:
                continue
            exp_spec = ExperimentSpec.model_validate_json(exp["spec"])
            cfg_id = json.dumps(
                self.reconstructed_config(exp_spec), sort_keys=True, default=str
            )
            if cfg_id != identity:
                continue
            if not self._beats_champion(
                float(exp["metric_value"]), champ_metric, direction, min_delta
            ):
                continue
            seed = exp_spec.reproducibility.seed
            if seed in seen_seeds:
                continue
            seen_eids.add(f.experiment_id)
            seen_seeds.add(seed)
            confirmations.append({
                "experiment_id": f.experiment_id,
                "metric_value": float(exp["metric_value"]),
                "config": self.reconstructed_config(exp_spec),
            })

        if len(confirmations) < needed:
            return False
        for conf in confirmations:
            if self._has_harmful_for_experiment(conf["experiment_id"]):
                return False

        best = confirmations[0]
        for conf in confirmations[1:]:
            if direction == "minimize":
                if conf["metric_value"] < best["metric_value"]:
                    best = conf
            elif conf["metric_value"] > best["metric_value"]:
                best = conf

        self.set_champion(best["config"], best["metric_value"], best["experiment_id"])
        suffix = finding.experiment_id.removeprefix("exp-")
        notice = ResearchFinding(
            finding_id=f"fnd-promo-{suffix}"[:68],
            project_id=self.project_id,
            experiment_id=best["experiment_id"],
            hypothesis_id=spec.hypothesis_id,
            kind="operational",
            statement=(
                f"Auto-guarded promotion: {needed} independent confirmations "
                f"beat the champion by more than min_delta={min_delta} "
                f"with no harmful findings."
            ),
            confidence=0.9,
            tags=["promotion", "auto-guarded"],
            conditions={
                "config_snapshot": best["config"],
                "confirmations": [c["experiment_id"] for c in confirmations],
                "min_delta": min_delta,
            },
        )
        self.save_finding(notice)
        return True

    @staticmethod
    def _beats_champion(
        metric: float, champion_metric: float, direction: str, min_delta: float
    ) -> bool:
        delta = champion_metric - metric if direction == "minimize" else metric - champion_metric
        return delta > min_delta

    def _has_harmful_for_experiment(self, experiment_id: str) -> bool:
        return any(
            f.experiment_id == experiment_id
            for f in self.active_findings(kinds=["harmful"])
        )

    # ----------------------------------------------------------------- internal
    def _assert_project(self, pid: str) -> None:
        if pid != self.project_id:
            raise ValueError(f"Law 4: record belongs to '{pid}', memory is '{self.project_id}'")

    def _migrate_experiments_started_at(self) -> None:
        cols = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(experiments)").fetchall()
        }
        if "started_at" not in cols:
            self.conn.execute("ALTER TABLE experiments ADD COLUMN started_at TEXT")

    def _migrate_desk_policy_mode(self) -> None:
        cols = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(desk_policy)").fetchall()
        }
        if cols and "mode" not in cols:
            self.conn.execute(
                "ALTER TABLE desk_policy ADD COLUMN mode TEXT NOT NULL DEFAULT 'minimal'"
            )

    def _experiment_exists(self, eid: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM experiments WHERE experiment_id=?", (eid,)
        ).fetchone() is not None

    def _finding_exists(self, fid: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM findings WHERE finding_id=?", (fid,)
        ).fetchone() is not None
