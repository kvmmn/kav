"""Tests for Host Adapter v0.1 (D-025)."""
import pytest

from kav_sdk import (
    Budget, Change, Constraints, Domain, EvaluatorDecl, ExperimentResult,
    ExperimentSpec, Evidence, Objective, Parameter, ProjectManifest, SearchSpace,
)
from kav_sdk.adapter import HostAdapter, HostRunner, SimulatedHost
from kav_sdk.memory import ProjectMemory
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
