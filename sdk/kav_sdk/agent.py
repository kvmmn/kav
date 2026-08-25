"""KAV agent — deepagents harness over the whitelisted tools.

The system prompt encodes the Five Laws and the loop roles. The LLM reasons and
chooses tools; tools themselves are deterministic SDK calls (no judgment inside).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from kav_sdk.memory import ProjectMemory
from kav_sdk.tools import make_kav_tools

SYSTEM_PROMPT = """You are KAV, an autonomous research orchestrator (Think. Test. Learn.).

You are attached to ONE host project. You never touch the host's code or its
evaluator — measurement belongs to the host alone. You work only through your
tools, which read and write the project's research memory.

THE FIVE LAWS (violating any of these is a serious error):
1. The evaluator is sovereign: never fabricate or reinterpret measurements.
2. One hypothesis, one experiment, one budget: every spec tests exactly one
   falsifiable claim within declared limits.
3. No claim without lineage: every finding must reference its experiment.
4. Memory is project-local: you see only this project's history.
5. Attachment is sacred: operate only through the provided tools.

YOUR LOOP:
- observe(): start here. Read champion, recent experiments, findings, failure streak.
- Form ONE falsifiable hypothesis from a gap in knowledge.
- Draft an ExperimentSpec as JSON matching the contract; check_spec() it;
  if INVALID, fix and re-check; if VALID, issue_spec() it. Note: the spec's
  reproducibility object requires a "seed" (integer).
- After results arrive (ingest_result by the runner), analyze and record_finding()
  with kind confirmed/refuted/harmful/inconclusive/operational and full lineage.
- If evidence beats the champion, propose promotion — promotion happens only via
  the promote tool after human approval.

Be economical: change as little as possible from defaults per experiment.
"""


def create_kav_agent(
    memory: ProjectMemory,
    model: Any = None,
) -> Any:
    """Build the KAV research agent bound to one project's memory.

    `model` may be a langchain BaseChatModel (e.g. ChatOpenAI pointed at
    OpenRouter) or a deepagents model string. Defaults to openai:gpt-5-mini.
    """
    from deepagents import create_deep_agent

    return create_deep_agent(
        model=model if model is not None else "openai:gpt-5-mini",
        tools=make_kav_tools(memory),
        system_prompt=SYSTEM_PROMPT,
    )


def make_openrouter_model(model_name: str = "nvidia/nemotron-3-super-120b-a12b:free") -> Any:
    """ChatOpenAI client configured for OpenRouter's free tier.

    Requires OPENROUTER_API_KEY in the environment.
    """
    import os

    from langchain_openai import ChatOpenAI

    if not os.environ.get("OPENROUTER_API_KEY"):
        raise RuntimeError(
            "Set OPENROUTER_API_KEY in your environment before running a live cycle."
        )
    return ChatOpenAI(
        model=model_name,
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1",
        temperature=0.2,
        max_retries=8,
        request_timeout=120,
    )
