"""KAV Control Plane — whitelisted tools over ProjectMemory.

The agent can ONLY act through these tools. There is no tool that touches the
host's code, evaluator, or repository (Law 1, Law 5). Every tool is a thin,
deterministic wrapper around the SDK — no LLM judgment inside tools.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kav_sdk import (
    ExperimentResult, ExperimentSpec, ResearchFinding,
    validate_spec_against_project,
)
from kav_sdk.memory import ProjectMemory


def make_kav_tools(memory: ProjectMemory) -> list[Any]:
    """Build the tool whitelist bound to one project's memory."""

    def observe() -> str:
        """OBSERVE node input: champion config, recent experiments, active findings."""
        return json.dumps({
            "champion": memory.get_champion(),
            "recent_experiments": memory.recent_experiments(limit=10),
            "active_findings": [f.model_dump(mode="json") for f in memory.active_findings(limit=10)],
            "failure_streak": memory.consecutive_failures(),
        })

    def check_spec(spec_json: str) -> str:
        """VALIDATE node: schema + cross-contract validation of an ExperimentSpec."""
        try:
            spec = ExperimentSpec.model_validate_json(spec_json)
            space = memory.get_search_space()
            manifest = memory.get_manifest()
            if space is None or manifest is None:
                return "ERROR: project not initialized (missing manifest/search space)"
            validate_spec_against_project(spec, space, manifest)
            return "VALID"
        except Exception as e:
            return f"INVALID: {e}"

    def issue_spec(spec_json: str) -> str:
        """DESIGN→AWAIT_EXECUTION: persist a validated spec; host picks it up."""
        verdict = check_spec(spec_json)
        if verdict != "VALID":
            return verdict
        spec = ExperimentSpec.model_validate_json(spec_json)
        memory.save_spec(spec)
        return f"ISSUED {spec.experiment_id}"

    def ingest_result(result_json: str) -> str:
        """INGEST node: record the host's honest report. Values stored as-is (Law 1)."""
        result = ExperimentResult.model_validate_json(result_json)
        memory.save_result(result)
        return f"RECORDED {result.experiment_id} status={result.status.value}"

    def record_finding(finding_json: str) -> str:
        """DISTILL node: write an immutable finding with lineage."""
        f = ResearchFinding.model_validate_json(finding_json)
        memory.save_finding(f)
        return f"RECORDED {f.finding_id}"

    def promote(config: dict[str, Any], metric_value: float, experiment_id: str) -> str:
        """PROMOTE_GATE (manual mode): human-approved champion update."""
        memory.set_champion(config, metric_value, experiment_id)
        return f"PROMOTED (champion metric={metric_value})"

    return [observe, check_spec, issue_spec, ingest_result, record_finding, promote]
