# ADR-001: Control Plane Foundation — Raw LangGraph vs Deep Agents Harness

**Status:** Accepted · **Date:** 2026-08-25

## Context
KAV's Control Plane (reasoning, hypothesis generation, experiment design, memory,
strategy) needs an agent foundation. Two candidates from the LangChain ecosystem:

**Option A — Raw LangGraph.**
Full control of the graph, state schema, and transitions. We build sub-agents,
context management, and human-in-the-loop ourselves. Master doc's original stance.

**Option B — Deep Agents harness (`langchain-ai/deepagents`).**
Opinionated harness on LangGraph: sub-agents with isolated context, pluggable
filesystem backends, context summarization/offloading, persistent memory,
human-in-the-loop approvals, skills, model-agnostic. Extensible — any piece can
be overridden or replaced without forking.

## Decision
**Option B — build on Deep Agents**, with strict customization:

1. **Tools are restricted to KAV's own contract-shaped tools** (manifest, search
   space, spec issuance, result ingestion). No host-code mutation tools; no shell
   access to the host in V1. Law 5 enforced by tool whitelist.
2. **Filesystem backend points at KAV's own artifact store**, never the host's
   repository. The evaluator remains untouched (Law 1).
3. **Human-in-the-loop approvals gate promotion proposals** (principle 8.10) —
   deepagents' permission system maps directly.
4. **Sub-agents = logical roles**: Hypothesizer, Experiment Designer, Result
   Analyst, Strategy Director. Isolated contexts prevent cross-contamination of
   reasoning stages.
5. **Memory/store backend = project-local** (ADR-001 five-nouns decision).

Escape hatch: because deepagents is a thin layer over LangGraph, any component
can be replaced with raw graph nodes later without a rewrite.

## Consequences
- (+) Sub-agents, context management, HITL, memory: free on day one.
- (+) Production features inherited: streaming, checkpointing, LangSmith tracing.
- (−) Inherited opinions must be actively constrained (tool whitelist, backend config).
- (−) One more dependency layer; mitigated by the escape hatch.

## Laws check
L1 ✓ evaluator untouched · L2 ✓ tools bounded · L3 ✓ LangSmith tracing + lineage ·
L4 ✓ project-local store · L5 ✓ attachment via contracts only.
