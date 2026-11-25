"""End-to-end walkthrough of one research cycle — no LLM required.

Simulates the loop deterministically: tools + memory + HostRunner. This proves
the plumbing (observe → hypothesize → spec → host drain → finding → promote)
before we let an LLM drive it.
"""
import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk"))

from kav_sdk import (
    Budget, Change, Constraints, Domain, EvaluatorDecl, ExperimentSpec,
    FindingKind, Objective, Parameter, ProjectManifest, ResearchFinding,
    SearchSpace,
)
from kav_sdk.adapter import HostRunner, SimulatedHost
from kav_sdk.memory import ProjectMemory
from kav_sdk.tools import make_kav_tools

root = Path(tempfile.mkdtemp(prefix="kav_walkthrough_"))
mem = ProjectMemory(root, "numerai-demo")
tools = {t.__name__: t for t in make_kav_tools(mem)}

host = SimulatedHost(
    ProjectManifest(
        project_id="numerai-demo", name="Numerai Demo",
        objective=Objective(metric="correlation", direction="maximize", baseline=0.021),
        constraints=Constraints(max_budget_per_experiment=Budget(max_compute_hours=2)),
        evaluator=EvaluatorDecl(owned_by="host"),
    ),
    SearchSpace(
        project_id="numerai-demo",
        parameters=[Parameter(name="lr", type="number",
                              domain=Domain(kind="range", min=0.001, max=0.1))],
        defaults={"lr": 0.01},
    ),
    evaluate=lambda params: 0.024,
)
runner = HostRunner(mem, host)
runner.attach()
mem.set_champion({"lr": 0.01}, 0.021, "exp-baseline")

print("1. OBSERVE")
state = __import__("json").loads(tools["observe"]())
print("   champion:", state["champion"]["metric_value"], "| desk k:", state["desk"]["k"],
      "| mode:", state["desk"]["mode"],
      "| promotion:", state["promotion_policy"]["mode"],
      "| findings:", len(state["active_findings"]),
      "| rejuvenated:", len(state["desk"]["rejuvenated"]))

print("2. HYPOTHESIZE: 'lr=0.02 improves correlation'")
spec = ExperimentSpec(
    experiment_id="exp-walk001", project_id="numerai-demo", hypothesis_id="hyp-lr-002",
    changes=[Change(parameter="lr", value=0.02)],
    reproducibility={"seed": 42},
)

print("3. VALIDATE:", tools["check_spec"](spec.model_dump_json()))

print("4. ISSUE:", tools["issue_spec"](spec.model_dump_json()))

print("5. DISPATCH host run (async; agent continues other hypotheses)")
print("   STARTED:", runner.dispatch_pending(), "in-flight spec(s)")
second = ExperimentSpec(
    experiment_id="exp-walk002", project_id="numerai-demo", hypothesis_id="hyp-lr-003",
    changes=[Change(parameter="lr", value=0.03)],
    reproducibility={"seed": 43},
)
print("   ISSUE while in-flight:", tools["issue_spec"](second.model_dump_json()))
print("   pending:", [s.experiment_id for s in mem.pending_specs()],
      "| inflight:", [s.experiment_id for s in mem.inflight_specs()])
print("   COLLECTED:", runner.collect_finished(timeout=5), "result(s) → wakes queued")
print("   DRAIN remaining:", runner.drain_pending(), "spec(s)")

print("6. DISTILL finding")
finding = ResearchFinding(
    finding_id="fnd-walk001", project_id="numerai-demo", experiment_id="exp-walk001",
    hypothesis_id="hyp-lr-002", kind=FindingKind.confirmed,
    statement="Raising lr from 0.01 to 0.02 improved correlation 0.021 to 0.024.",
    confidence=0.5, tags=["lr"],
)
print("   ", tools["record_finding"](finding.model_dump_json()))

print("7. PROMOTE_GATE (human approves)")
print("   ", tools["promote"]({"lr": 0.02}, 0.024, "exp-walk001"))

print("\n8. OBSERVE again — knowledge grew + wakes delivered:")
state = __import__("json").loads(tools["observe"]())
print("   champion:", state["champion"]["metric_value"], "| desk k:", state["desk"]["k"],
      "| mode:", state["desk"]["mode"],
      "| findings:", len(state["active_findings"]),
      "| rejuvenated:", len(state["desk"]["rejuvenated"]),
      "| wakes:", [w["experiment_id"] for w in state["wakes"]],
      "| pending:", state["pending"], "| inflight:", state["inflight"])

assert state["champion"]["metric_value"] == 0.024
assert len(state["active_findings"]) == 1
assert state["desk"]["k"] == 10
assert state["desk"]["mode"] == "minimal"
assert state["desk_policy"]["k"] == 10
assert state["desk_policy"]["rejuvenation_every"] == 8
assert state["desk_policy"]["plateau_window"] == 5
assert "digest" not in state["desk"]
assert state["desk"]["rejuvenated"] == []
assert state["promotion_policy"]["mode"] == "manual"
assert state["promotion_policy"]["min_delta"] == 0
assert state["promotion_policy"]["confirmations"] == 2
assert state["execution_policy"]["max_inflight"] == 2
assert state["circuit_policy"]["threshold"] == 3
assert {w["experiment_id"] for w in state["wakes"]} == {"exp-walk001", "exp-walk002"}
assert state["pending"] == []
assert state["inflight"] == []
print("\nFULL CYCLE COMPLETE ✓ — plumbing proven; ready for an LLM to drive it.")
