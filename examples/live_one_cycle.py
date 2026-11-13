"""KAV's FIRST LIVE CYCLE — a real LLM drives the research loop.

The agent (LLM) does all thinking: observe → hypothesize → spec → analyze →
finding → promotion proposal. The host side is a SimulatedHost whose
evaluator honestly reports metric = f(config). HostRunner drains issued
specs and ingests results, exactly as a real adapter would.

Run:
    export OPENROUTER_API_KEY=sk-or-...
    python3 examples/live_one_cycle.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk"))

from kav_sdk import (
    Budget, Constraints, Domain, EvaluatorDecl, Objective, Parameter,
    ProjectManifest, SearchSpace,
)
from kav_sdk.adapter import HostRunner, SimulatedHost
from kav_sdk.agent import create_kav_agent, make_openrouter_model
from kav_sdk.memory import ProjectMemory
from kav_sdk.tools import make_kav_tools

MAX_EXPERIMENTS = 3
MISSION = (
    f"You have a budget of at most {MAX_EXPERIMENTS} experiments this session. "
    "Improve the champion correlation if you can. Follow your loop: observe, "
    "hypothesize ONE change, check_spec, issue_spec, then WAIT for the result "
    "(the host runner will ingest it). After each result arrives, observe again, "
    "record a finding with lineage, and decide whether to propose promotion "
    "(promote tool = human-approved gate; you may call it when evidence clearly "
    "beats the champion). When done or out of budget, summarize what was learned."
)


def true_metric(params: dict) -> float:
    # Hidden landscape: optimum near lr=0.03.
    lr = params["lr"]
    return round(0.021 + 0.9 * lr - 15.0 * (lr - 0.03) ** 2, 6)


root = Path(tempfile.mkdtemp(prefix="kav_live_"))
mem = ProjectMemory(root, "numerai-demo")
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
    evaluate=true_metric,
)
runner = HostRunner(mem, host)
runner.attach()
mem.set_champion({"lr": 0.01}, 0.021, "exp-baseline")

tools = {t.__name__: t for t in make_kav_tools(mem)}

# --- Build the live agent -----------------------------------------------------
model = make_openrouter_model()  # deepseek free tier via OpenRouter
agent = create_kav_agent(mem, model=model)

print(f"KAV LIVE CYCLE — memory at {root}")
print(f"Mission: {MISSION}\n")

config = {"recursion_limit": 150}
messages = [{"role": "user", "content": MISSION}]

# Multi-turn loop: agent thinks/issues → host executes honestly → agent continues.
for turn in range(4):
    state = agent.invoke({"messages": messages}, config=config)
    messages = state["messages"]
    pending = runner.drain_pending()
    if not pending:
        break
    print(f"[host] executed {pending} issued experiment(s); results ingested.")
    messages = messages + [{"role": "user", "content":
        "The host has executed the issued experiment(s) and ingested their "
        "results into memory. Continue your loop: observe, distill findings "
        "with lineage, propose promotion if warranted, or conclude."}]

print("\n--- TRANSCRIPT ---")
for m in state["messages"]:
    role = getattr(m, "type", "?")
    content = m.content if isinstance(m.content, str) else str(m.content)[:400]
    print(f"[{role}] {content[:600]}")

print("\n--- FINAL MEMORY STATE ---")
final = json.loads(tools["observe"]())
print(json.dumps(final, indent=2)[:2000])
