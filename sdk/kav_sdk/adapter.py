"""Host Adapter v0.1 — in-process projection of the four adapter operations.

The JSON Schemas in contracts/ remain canonical (ADR-003, D-008, D-009).
This module is the Python library transport: attach a host, drain issued
specs, ingest host-reported results. HTTP/OpenAPI lives in `kav_sdk.http`
(D-026). Event-driven dispatch (D-030) starts host runs without blocking
the control plane.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor, wait
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
        self._futures: dict[str, Future[Any]] = {}
        self._pool: ThreadPoolExecutor | None = None

    def attach(self) -> None:
        """Copy host declarations into project memory (adapter's job, not the agent's).

        `save_manifest` also seeds promotion_policy and desk_policy.mode from
        optional `manifest.policy` (D-032 / D-033 / D-034). Omitted policy is
        manual; omitted `min_delta` / `confirmations` / `desk` keep
        project-local tunables.
        """
        self.memory.save_manifest(self.adapter.manifest())
        self.memory.save_search_space(self.adapter.search_space())

    def dispatch_pending(self) -> int:
        """Start queued specs up to max_inflight without waiting (D-030).

        Returns how many host runs were started. The agent may issue more
        specs while these execute. Ingest happens in `collect_finished`.
        Halted strategies start nothing.
        """
        if self.memory.is_halted():
            return 0
        room = self.memory.get_execution_policy()["max_inflight"] - len(
            self.memory.inflight_specs()
        )
        started = 0
        for spec in self.memory.pending_specs():
            if room <= 0 or self.memory.is_halted():
                break
            self.memory.mark_started(spec.experiment_id)
            self._futures[spec.experiment_id] = self._executor().submit(
                self._run_one, spec
            )
            started += 1
            room -= 1
        return started

    def collect_finished(self, timeout: float | None = 0) -> int:
        """Ingest completed host runs on the control-plane thread. Returns count.

        `timeout=0` polls already-done futures. `timeout=None` waits for every
        in-flight future. A positive timeout waits that many seconds then
        ingests whatever finished. Halt still blocks further dispatch; already
        started runs are ingested as they complete.
        """
        if not self._futures:
            return 0
        if timeout is None:
            wait(list(self._futures.values()))
        elif timeout > 0:
            wait(list(self._futures.values()), timeout=timeout)
        n = 0
        for eid, fut in list(self._futures.items()):
            if not fut.done():
                continue
            reported = fut.result()
            del self._futures[eid]
            self._ingest(reported.model_dump_json())
            n += 1
        return n

    def drain_pending(self) -> int:
        """Run pending specs FIFO; ingest each host-reported result. Returns count.

        Sequential path (D-025): used by walkthrough/live convenience and halt
        tests. Stops without running further specs once the circuit breaker has
        halted the strategy (D-027). Already-ingested results stay recorded.
        Also waits for any async in-flight runs started via `dispatch_pending`.
        """
        n = self.collect_finished(timeout=None)
        for spec in self.memory.pending_specs():
            if self.memory.is_halted():
                break
            raw = self.adapter.run_experiment(spec)
            reported = self.adapter.report_result(raw)
            self._ingest(reported.model_dump_json())
            n += 1
        return n

    def close(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=False)
            self._pool = None

    def _executor(self) -> ThreadPoolExecutor:
        if self._pool is None:
            workers = self.memory.get_execution_policy()["max_inflight"]
            self._pool = ThreadPoolExecutor(
                max_workers=workers, thread_name_prefix="kav-host"
            )
        return self._pool

    def _run_one(self, spec: ExperimentSpec) -> ExperimentResult:
        raw = self.adapter.run_experiment(spec)
        return self.adapter.report_result(raw)
