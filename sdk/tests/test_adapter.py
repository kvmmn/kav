"""Tests for Host Adapter v0.1 (D-025) and event-driven dispatch (D-030)."""
import threading

import pytest

from kav_sdk import (
    Budget, Change, Constraints, Domain, EvaluatorDecl, ExperimentResult,
    ExperimentSpec, Evidence, Objective, Parameter, PolicyDecl, ProjectManifest,
    SearchSpace,
)
from kav_sdk.adapter import HostAdapter, HostRunner, SimulatedHost
from kav_sdk.memory import (
    DESK_MINIMAL, DESK_RICH_DIGEST, PROMOTION_AUTO_GUARDED, PROMOTION_MANUAL,
    ProjectMemory,
)
from kav_sdk.tools import make_kav_tools


@pytest.fixture()
def mem(tmp_path):
    m = ProjectMemory(tmp_path, "numerai-demo")
    yield m
    m.close()


def manifest():
    return ProjectManifest(
        project_id="numerai-demo", name="Demo",
        objective=Objective(metric="correlation", direction="maximize", baseline=0.021),
        constraints=Constraints(max_budget_per_experiment=Budget(max_compute_hours=2)),
        evaluator=EvaluatorDecl(owned_by="host"),
    )


def space():
    return SearchSpace(
        project_id="numerai-demo",
        parameters=[Parameter(name="lr", type="number",
                              domain=Domain(kind="range", min=0.001, max=0.1))],
        defaults={"lr": 0.01},
    )


def spec(eid="exp-ada001", lr=0.02):
    return ExperimentSpec(
        experiment_id=eid, project_id="numerai-demo", hypothesis_id="hyp-ada001",
        changes=[Change(parameter="lr", value=lr)],
        reproducibility={"seed": 42},
    )


def true_metric(params):
    lr = params["lr"]
    return 0.021 + 0.9 * lr - 15.0 * (lr - 0.03) ** 2


def test_simulated_host_satisfies_protocol():
    host = SimulatedHost(manifest(), space(), true_metric)
    assert isinstance(host, HostAdapter)


def test_attach_writes_manifest_and_space(mem):
    runner = HostRunner(mem, SimulatedHost(manifest(), space(), true_metric))
    assert mem.get_manifest() is None
    runner.attach()
    assert mem.get_manifest().name == "Demo"
    assert mem.get_search_space().defaults == {"lr": 0.01}
    assert mem.get_promotion_policy()["mode"] == PROMOTION_MANUAL


def test_attach_seeds_auto_guarded_from_manifest(mem):
    host = SimulatedHost(
        manifest().model_copy(update={"policy": PolicyDecl(promotion="auto_guarded")}),
        space(),
        true_metric,
    )
    runner = HostRunner(mem, host)
    runner.attach()
    assert mem.get_manifest().promotion_mode() == PROMOTION_AUTO_GUARDED
    assert mem.get_promotion_policy()["mode"] == PROMOTION_AUTO_GUARDED


def test_attach_seeds_declared_thresholds(mem):
    host = SimulatedHost(
        manifest().model_copy(update={"policy": PolicyDecl(
            promotion="auto_guarded", min_delta=0.05, confirmations=4,
        )}),
        space(),
        true_metric,
    )
    runner = HostRunner(mem, host)
    runner.attach()
    policy = mem.get_promotion_policy()
    assert policy["mode"] == PROMOTION_AUTO_GUARDED
    assert policy["min_delta"] == 0.05
    assert policy["confirmations"] == 4


def test_attach_seeds_declared_desk(mem):
    mem.set_desk_policy(k=4, mode=DESK_MINIMAL)
    host = SimulatedHost(
        manifest().model_copy(update={"policy": PolicyDecl(desk="rich_digest")}),
        space(),
        true_metric,
    )
    runner = HostRunner(mem, host)
    runner.attach()
    desk = mem.get_desk_policy()
    assert desk["mode"] == DESK_RICH_DIGEST
    assert desk["k"] == 4


def test_attach_omitted_desk_keeps_local(mem):
    mem.set_desk_policy(k=4, mode=DESK_RICH_DIGEST)
    host = SimulatedHost(
        manifest().model_copy(update={"policy": PolicyDecl(promotion="auto_guarded")}),
        space(),
        true_metric,
    )
    runner = HostRunner(mem, host)
    runner.attach()
    desk = mem.get_desk_policy()
    assert desk["mode"] == DESK_RICH_DIGEST
    assert desk["k"] == 4
    assert mem.get_promotion_policy()["mode"] == PROMOTION_AUTO_GUARDED


def test_attach_seeds_declared_max_inflight(mem):
    mem.set_execution_policy(max_inflight=3)
    host = SimulatedHost(
        manifest().model_copy(update={"policy": PolicyDecl(max_inflight=4)}),
        space(),
        true_metric,
    )
    runner = HostRunner(mem, host)
    runner.attach()
    assert mem.get_execution_policy()["max_inflight"] == 4


def test_attach_omitted_max_inflight_keeps_local(mem):
    mem.set_execution_policy(max_inflight=3)
    host = SimulatedHost(
        manifest().model_copy(update={"policy": PolicyDecl(promotion="auto_guarded")}),
        space(),
        true_metric,
    )
    runner = HostRunner(mem, host)
    runner.attach()
    assert mem.get_execution_policy()["max_inflight"] == 3
    assert mem.get_promotion_policy()["mode"] == PROMOTION_AUTO_GUARDED


def test_attach_seeds_declared_desk_tunables(mem):
    mem.set_desk_policy(k=4, rejuvenation_every=3, plateau_window=6, mode=DESK_RICH_DIGEST)
    host = SimulatedHost(
        manifest().model_copy(update={
            "policy": PolicyDecl(k=5, rejuvenation_every=2, plateau_window=4),
        }),
        space(),
        true_metric,
    )
    runner = HostRunner(mem, host)
    runner.attach()
    desk = mem.get_desk_policy()
    assert desk["k"] == 5
    assert desk["rejuvenation_every"] == 2
    assert desk["plateau_window"] == 4
    assert desk["mode"] == DESK_RICH_DIGEST


def test_attach_seeds_declared_circuit_breaker(mem):
    mem.set_circuit_policy(threshold=4)
    host = SimulatedHost(
        manifest().model_copy(update={"policy": PolicyDecl(circuit_breaker=2)}),
        space(),
        true_metric,
    )
    runner = HostRunner(mem, host)
    runner.attach()
    assert mem.get_circuit_policy()["threshold"] == 2


def test_attach_omitted_circuit_breaker_keeps_local(mem):
    mem.set_circuit_policy(threshold=4)
    host = SimulatedHost(
        manifest().model_copy(update={"policy": PolicyDecl(promotion="auto_guarded")}),
        space(),
        true_metric,
    )
    runner = HostRunner(mem, host)
    runner.attach()
    assert mem.get_circuit_policy()["threshold"] == 4
    assert mem.get_promotion_policy()["mode"] == PROMOTION_AUTO_GUARDED


def test_attach_omitted_desk_tunables_keeps_local(mem):
    mem.set_desk_policy(k=4, rejuvenation_every=3, plateau_window=6, mode=DESK_RICH_DIGEST)
    host = SimulatedHost(
        manifest().model_copy(update={"policy": PolicyDecl(promotion="auto_guarded")}),
        space(),
        true_metric,
    )
    runner = HostRunner(mem, host)
    runner.attach()
    desk = mem.get_desk_policy()
    assert desk["k"] == 4
    assert desk["rejuvenation_every"] == 3
    assert desk["plateau_window"] == 6
    assert desk["mode"] == DESK_RICH_DIGEST
    assert mem.get_promotion_policy()["mode"] == PROMOTION_AUTO_GUARDED


def test_drain_pending_is_noop_when_empty(mem):
    runner = HostRunner(mem, SimulatedHost(manifest(), space(), true_metric))
    runner.attach()
    assert runner.drain_pending() == 0


def test_drain_pending_fifo_and_ingest(mem):
    runner = HostRunner(mem, SimulatedHost(manifest(), space(), true_metric))
    runner.attach()
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    first = spec("exp-ada010", lr=0.02)
    second = spec("exp-ada011", lr=0.04)
    assert tools["issue_spec"](first.model_dump_json()).startswith("ISSUED")
    assert tools["issue_spec"](second.model_dump_json()).startswith("ISSUED")
    pending = mem.pending_specs()
    assert [s.experiment_id for s in pending] == ["exp-ada010", "exp-ada011"]
    assert runner.drain_pending() == 2
    assert mem.pending_specs() == []
    row = mem.get_experiment("exp-ada010")
    assert row["status"] == "completed"
    assert row["metric_value"] == pytest.approx(true_metric({"lr": 0.02}))
    later = mem.get_experiment("exp-ada011")
    assert later["metric_value"] == pytest.approx(true_metric({"lr": 0.04}))
    assert runner.drain_pending() == 0


def test_drain_pending_stops_after_circuit_breaker_halt(mem):
    def boom(_params):
        raise RuntimeError("evaluator crashed")

    runner = HostRunner(mem, SimulatedHost(manifest(), space(), boom))
    runner.attach()
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    for i, eid in enumerate(["exp-ada101", "exp-ada102", "exp-ada103", "exp-ada104"]):
        tools["issue_spec"](spec(eid).model_dump_json())
    assert runner.drain_pending() == 3
    assert mem.is_halted()
    assert mem.get_experiment("exp-ada104")["result"] is None
    assert [s.experiment_id for s in mem.pending_specs()] == ["exp-ada104"]


def test_failed_host_run_is_ingested(mem):
    def boom(_params):
        raise RuntimeError("evaluator crashed")

    runner = HostRunner(mem, SimulatedHost(manifest(), space(), boom))
    runner.attach()
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    tools["issue_spec"](spec().model_dump_json())
    assert runner.drain_pending() == 1
    row = mem.get_experiment("exp-ada001")
    assert row["status"] == "failed"
    assert mem.pending_specs() == []


def test_evaluate_may_return_full_result(mem):
    def as_result(params):
        return ExperimentResult(
            experiment_id="exp-ada001", status="completed",
            evidence=Evidence(metric_value=0.5),
        )

    runner = HostRunner(mem, SimulatedHost(manifest(), space(), as_result))
    runner.attach()
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    tools["issue_spec"](spec().model_dump_json())
    runner.drain_pending()
    assert mem.get_experiment("exp-ada001")["metric_value"] == 0.5


def test_mismatched_result_id_rejected(mem):
    def wrong(_params):
        return ExperimentResult(
            experiment_id="exp-other1", status="completed",
            evidence=Evidence(metric_value=0.1),
        )

    host = SimulatedHost(manifest(), space(), wrong)
    with pytest.raises(ValueError, match="experiment_id"):
        host.run_experiment(spec())


def test_dispatch_allows_issue_while_host_runs(mem):
    started = threading.Event()
    release = threading.Event()

    def slow(params):
        started.set()
        assert release.wait(timeout=5)
        return true_metric(params)

    runner = HostRunner(mem, SimulatedHost(manifest(), space(), slow))
    runner.attach()
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    assert tools["issue_spec"](spec("exp-ada201", lr=0.02).model_dump_json()).startswith(
        "ISSUED"
    )
    assert runner.dispatch_pending() == 1
    assert started.wait(timeout=5)
    assert [s.experiment_id for s in mem.inflight_specs()] == ["exp-ada201"]
    assert tools["issue_spec"](spec("exp-ada202", lr=0.04).model_dump_json()).startswith(
        "ISSUED"
    )
    assert [s.experiment_id for s in mem.pending_specs()] == ["exp-ada202"]
    release.set()
    assert runner.collect_finished(timeout=5) == 1
    assert mem.get_experiment("exp-ada201")["status"] == "completed"
    assert mem.unconsumed_wakes()[0]["experiment_id"] == "exp-ada201"
    assert runner.dispatch_pending() == 1
    assert runner.collect_finished(timeout=5) == 1
    assert mem.get_experiment("exp-ada202")["status"] == "completed"
    runner.close()


def test_dispatch_respects_max_inflight(mem):
    started = threading.Event()
    release = threading.Event()
    running = {"n": 0}
    lock = threading.Lock()

    def slow(params):
        with lock:
            running["n"] += 1
            if running["n"] == 1:
                started.set()
        assert release.wait(timeout=5)
        return true_metric(params)

    mem.set_execution_policy(max_inflight=1)
    runner = HostRunner(mem, SimulatedHost(manifest(), space(), slow))
    runner.attach()
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    tools["issue_spec"](spec("exp-ada301", lr=0.02).model_dump_json())
    tools["issue_spec"](spec("exp-ada302", lr=0.04).model_dump_json())
    assert runner.dispatch_pending() == 1
    assert started.wait(timeout=5)
    assert runner.dispatch_pending() == 0
    assert [s.experiment_id for s in mem.pending_specs()] == ["exp-ada302"]
    release.set()
    assert runner.collect_finished(timeout=5) == 1
    assert runner.dispatch_pending() == 1
    assert runner.collect_finished(timeout=5) == 1
    runner.close()


def test_dispatch_is_noop_when_halted(mem):
    def boom(_params):
        raise RuntimeError("evaluator crashed")

    runner = HostRunner(mem, SimulatedHost(manifest(), space(), boom))
    runner.attach()
    tools = {t.__name__: t for t in make_kav_tools(mem)}
    for eid in ["exp-ada401", "exp-ada402", "exp-ada403", "exp-ada404"]:
        tools["issue_spec"](spec(eid).model_dump_json())
    assert runner.drain_pending() == 3
    assert mem.is_halted()
    assert [s.experiment_id for s in mem.pending_specs()] == ["exp-ada404"]
    assert runner.dispatch_pending() == 0
    assert [s.experiment_id for s in mem.pending_specs()] == ["exp-ada404"]
    runner.close()
