"""End-to-end walkthrough of one research cycle — no LLM required.

Simulates the loop deterministically: tools + memory only. This proves the
plumbing (observe → hypothesize → spec → result → finding → promote) before
we let an LLM drive it.
"""
import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk"))

from kav_sdk import (
    Budget, Change, Constraints, Domain, EvaluatorDecl, ExperimentResult,
    ExperimentSpec, Evidence, FindingKind, Objective, Parameter,
    ProjectManifest, ResearchFinding, SearchSpace,
)
from kav_sdk.memory import ProjectMemory
from kav_sdk.tools import make_kav_tools

root = Path(tempfile.mkdtemp(prefix="kav_walkthrough_"))
mem = ProjectMemory(root, "numerai-demo")
tools = {t.__name__: t for t in make_kav_tools(mem)}

# --- setup: host registers manifest + space (adapter's job, not the agent's)
mem.save_manifest(ProjectManifest(
    project_id="numerai-demo", name="Numerai Demo",
    objective=Objective(metric="correlation", direction="maximize", baseline=0.021),
    constraints=Constraints(max_budget_per_experiment=Budget(max_compute_hours=2)),
    evaluator=EvaluatorDecl(owned_by="host"),
))
mem.save_search_space(SearchSpace(
    project_id="numerai-demo",
    parameters=[Parameter(name="lr", type="number",
                          domain=Domain(kind="range", min=0.001, max=0.1))],
    defaults={"lr": 0.01},
))
mem.set_champion({"lr": 0.01}, 0.021, "exp-baseline")

print("1. OBSERVE")
state = __import__("json").loads(tools["observe"]())
print("   champion:", state["champion"]["metric_value"], "| findings:", len(state["active_findings"]))

print("2. HYPOTHESIZE: 'lr=0.02 improves correlation'")
spec = ExperimentSpec(
    experiment_id="exp-walk001", project_id="numerai-demo", hypothesis_id="hyp-lr-002",
    changes=[Change(parameter="lr", value=0.02)],
    reproducibility={"seed": 42},
)

print("3. VALIDATE:", tools["check_spec"](spec.model_dump_json()))

print("4. ISSUE:", tools["issue_spec"](spec.model_dump_json()))

print("5. HOST EXECUTES (simulated) -> result arrives")
result = ExperimentResult(
    experiment_id="exp-walk001", status="completed",
    evidence=Evidence(metric_value=0.024),
)
print("   INGEST:", tools["ingest_result"](result.model_dump_json()))

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

print("\n8. OBSERVE again — knowledge grew:")
state = __import__("json").loads(tools["observe"]())
print("   champion:", state["champion"]["metric_value"], "| findings:", len(state["active_findings"]))

assert state["champion"]["metric_value"] == 0.024
assert len(state["active_findings"]) == 1
print("\nFULL CYCLE COMPLETE ✓ — plumbing proven; ready for an LLM to drive it.")
