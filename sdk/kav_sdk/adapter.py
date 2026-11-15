"""Host Adapter v0.1 — in-process projection of the four adapter operations.

The JSON Schemas in contracts/ remain canonical (ADR-003, D-008, D-009).
This module is the Python library transport: attach a host, drain issued
specs, ingest host-reported results. HTTP/OpenAPI lives in `kav_sdk.http`
(D-026).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from kav_sdk.memory import ProjectMemory
from kav_sdk.models import (
    ErrorInfo,
    Evidence,
    ExperimentResult,
    ExperimentSpec,
    ProjectManifest,
    ResultStatus,
    SearchSpace,
)
from kav_sdk.tools import make_kav_tools


@runtime_checkable
class HostAdapter(Protocol):
    """Four host-facing operations (D-009)."""

    def manifest(self) -> ProjectManifest:
        """Register the project objective, budget ceiling, and evaluator ownership."""

    def search_space(self) -> SearchSpace:
        """Declare the bounded, typed parameter space and defaults."""

    def run_experiment(self, spec: ExperimentSpec) -> ExperimentResult:
        """Execute one validated spec. KAV never touches the evaluator (Law 1)."""

    def report_result(self, result: ExperimentResult) -> ExperimentResult:
        """Return the host's honest measurement as-is (failures included)."""


class SimulatedHost:
    """Deterministic in-process host for tests, walkthrough, and live demo.

    `evaluate` maps the resolved parameter dict (defaults + spec changes) to
    either a metric float or a full `ExperimentResult`. Exceptions become
    failed results with an error explanation.
    """

    def __init__(
        self,
        manifest: ProjectManifest,
        search_space: SearchSpace,
        evaluate: Callable[[Mapping[str, Any]], float | ExperimentResult],
    ) -> None:
        self._manifest = manifest
        self._search_space = search_space
        self._evaluate = evaluate

    def manifest(self) -> ProjectManifest:
        return self._manifest

    def search_space(self) -> SearchSpace:
        return self._search_space

    def run_experiment(self, spec: ExperimentSpec) -> ExperimentResult:
        params: dict[str, Any] = dict(self._search_space.defaults)
        for change in spec.changes:
            params[change.parameter] = change.value
        try:
            out = self._evaluate(params)
        except Exception as exc:
            return ExperimentResult(
                experiment_id=spec.experiment_id,
                status=ResultStatus.failed,
                error=ErrorInfo(code="host_error", message=str(exc)[:500]),
            )
        if isinstance(out, ExperimentResult):
            if out.experiment_id != spec.experiment_id:
                raise ValueError("host result experiment_id must match the spec")
            return out
        return ExperimentResult(
            experiment_id=spec.experiment_id,
            status=ResultStatus.completed,
            evidence=Evidence(metric_value=float(out)),
        )

    def report_result(self, result: ExperimentResult) -> ExperimentResult:
        return result


class HostRunner:
    """Attaches a HostAdapter and drains pending specs into memory."""

    def __init__(self, memory: ProjectMemory, adapter: HostAdapter) -> None:
        self.memory = memory
        self.adapter = adapter
        self._ingest = {t.__name__: t for t in make_kav_tools(memory)}["ingest_result"]

    def attach(self) -> None:
        """Copy host declarations into project memory (adapter's job, not the agent's)."""
        self.memory.save_manifest(self.adapter.manifest())
        self.memory.save_search_space(self.adapter.search_space())

    def drain_pending(self) -> int:
        """Run pending specs FIFO; ingest each host-reported result. Returns count.

        Stops without running further specs once the circuit breaker has halted
        the strategy (D-027). Already-ingested results stay recorded.
        """
        n = 0
        for spec in self.memory.pending_specs():
            if self.memory.is_halted():
                break
            raw = self.adapter.run_experiment(spec)
            reported = self.adapter.report_result(raw)
            self._ingest(reported.model_dump_json())
            n += 1
        return n
