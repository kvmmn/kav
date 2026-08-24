"""Tests for the project-local memory layer."""
import pytest

from kav_sdk import (
    Budget, Change, Constraints, Domain, EvaluatorDecl, ExperimentResult,
    ExperimentSpec, Evidence, FindingKind, Objective, Parameter,
    ProjectManifest, ResearchFinding, SearchSpace,
)
from kav_sdk.memory import ProjectMemory


@pytest.fixture()
def mem(tmp_path):
    m = ProjectMemory(tmp_path, "numerai-demo")
    yield m
    m.close()


def manifest():
    return ProjectManifest(
        project_id="numerai-demo", name="Demo",
        objective=Objective(metric="correlation", direction="maximize"),
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


def spec(eid="exp-aaa111"):
    return ExperimentSpec(
        experiment_id=eid, project_id="numerai-demo", hypothesis_id="hyp-bbb222",
        changes=[Change(parameter="lr", value=0.02)],
        reproducibility={"seed": 42},
    )


def result(eid="exp-aaa111", value=0.025):
    return ExperimentResult(experiment_id=eid, status="completed",
                            evidence=Evidence(metric_value=value))


def finding(fid="fnd-ccc333", kind="confirmed", conf=0.5):
    return ResearchFinding(
        finding_id=fid, project_id="numerai-demo", experiment_id="exp-aaa111",
        kind=kind, statement="Raising lr to 0.02 improved correlation.",
        confidence=conf, tags=["lr"],
    )


# ---- Law 4: project isolation
def test_memory_rejects_foreign_records(mem):
    foreign = manifest().model_copy(update={"project_id": "other-proj"})
    with pytest.raises(ValueError, match="Law 4"):
        mem.save_manifest(foreign)


# ---- roundtrips
def test_manifest_and_space_roundtrip(mem):
    mem.save_manifest(manifest())
    mem.save_search_space(space())
    assert mem.get_manifest().objective.metric == "correlation"
    assert mem.get_search_space().defaults == {"lr": 0.01}


def test_spec_result_flow(mem):
    mem.save_spec(spec())
    mem.save_result(result())
    row = mem.get_experiment("exp-aaa111")
    assert row["status"] == "completed"
    assert row["metric_value"] == 0.025


def test_result_requires_known_experiment(mem):
    with pytest.raises(KeyError):
        mem.save_result(result("exp-unknown"))


# ---- Law 3: findings immutable
def test_finding_immutable(mem):
    mem.save_finding(finding())
    with pytest.raises(ValueError, match="immutable"):
        mem.save_finding(finding())


def test_supersede_keeps_history(mem):
    old = finding()
    mem.save_finding(old)
    new = finding("fnd-ddd444", conf=0.9)
    mem.supersede_finding("fnd-ccc333", new)
    active = mem.active_findings()
    assert len(active) == 1
    assert active[0].finding_id == "fnd-ddd444"


def test_active_findings_filters_kinds(mem):
    mem.save_spec(spec())
    mem.save_finding(finding())
    mem.save_finding(finding("fnd-eee555", kind="refuted", conf=0.3))
    refuted = mem.active_findings(kinds=["refuted"])
    assert [f.finding_id for f in refuted] == ["fnd-eee555"]


# ---- champion + circuit breaker
def test_champion_roundtrip(mem):
    assert mem.get_champion() is None
    mem.set_champion({"lr": 0.01}, 0.021, "exp-aaa111")
    c = mem.get_champion()
    assert c["metric_value"] == 0.021


def test_consecutive_failures_streak(mem):
    for i, eid in enumerate(["exp-f01001", "exp-f01002", "exp-f01003"]):
        mem.save_spec(spec(eid))
        mem.save_result(ExperimentResult(
            experiment_id=eid, status="failed",
            error={"code": "crash", "message": "boom"}))
    assert mem.consecutive_failures() == 3
    mem.save_spec(spec("exp-ok0001"))
    mem.save_result(result("exp-ok0001", value=0.03))
    assert mem.consecutive_failures() == 0
