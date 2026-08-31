# KAV Architecture

This page is the public architecture reference for KAV v0.1. It describes the
tool itself — not any particular host project.

---

## Problem statement

Many measurable systems (forecasting pipelines, retrieval stacks, simulation
environments, pricing engines) benefit from iterative experimentation, but ad-hoc
tuning lacks auditability, budget discipline, and causal attribution. KAV
provides a **research operating layer** that:

1. Reads a host-declared manifest and search space
2. Proposes one hypothesis at a time within declared bounds
3. Issues machine-readable experiment specifications
4. Waits for the host evaluator to report trusted evidence
5. Distills findings into project-local memory
6. Uses memory to inform the next hypothesis

KAV's output in v0.1 is **configuration and experiment specification**, not
direct modification of host source code.

---

## Two-plane model

```
┌─────────────────────────────────────────────────────────────┐
│                     KAV Control Plane                       │
│  Observe · Hypothesize · Design · Distill · Strategy        │
│  (LLM + whitelisted tools + project-local memory)           │
└──────────────────────────┬──────────────────────────────────┘
                           │ adapter contract (JSON Schema v0.1)
┌──────────────────────────▼──────────────────────────────────┐
│                   Host Execution Plane                      │
│  Run experiment · Evaluate · Report result · Store artifacts│
│  (owned entirely by the host; evaluator is sovereign)       │
└─────────────────────────────────────────────────────────────┘
```

**Control plane** (KAV): reasoning, spec validation, memory, promotion gating.  
**Execution plane** (host): training, simulation, backtest, scoring — whatever
the host's evaluator implements.

Law 1 enforces the boundary: KAV schemas contain **declarations** about the
evaluator, never credentials or access paths into it.

---

## Domain vocabulary

Five nouns form the conceptual model ([research/five-nouns.md](research/five-nouns.md)):

| Noun | Role |
|------|------|
| **Project** | Host system with objective, search space, and evaluator |
| **Hypothesis** | Falsifiable claim about a single change |
| **Experiment** | One bounded attempt to test one hypothesis |
| **Evidence** | Trusted measurement from the host evaluator |
| **Finding** | Durable, lineage-traced knowledge distilled from evidence |

---

## Research loop (detailed)

```text
                    ┌──────────────┐
                    │   OBSERVE    │◀────────────────────────┐
                    │ champion +   │                         │
                    │ top-k finds  │                         │
                    └──────┬───────┘                         │
                           │                                 │
                    ┌──────▼───────┐                         │
                    │  HYPOTHESIZE │                         │
                    │ one claim    │                         │
                    └──────┬───────┘                         │
                           │                                 │
                    ┌──────▼───────┐    invalid              │
                    │    DESIGN    │──────── retry ────────┤
                    │ ExperimentSpec│                        │
                    └──────┬───────┘                         │
                           │ valid                           │
                    ┌──────▼───────┐                         │
                    │    ISSUE     │                         │
                    │ to host      │                         │
                    └──────┬───────┘                         │
                           │ async                           │
                    ┌──────▼───────┐                         │
                    │   EXECUTE    │  (host)                 │
                    └──────┬───────┘                         │
                           │                                 │
                    ┌──────▼───────┐                         │
                    │   INGEST     │                         │
                    │ result       │                         │
                    └──────┬───────┘                         │
                           │                                 │
                    ┌──────▼───────┐                         │
                    │   DISTILL    │                         │
                    │ finding      │                         │
                    └──────┬───────┘                         │
                           │                                 │
                    ┌──────▼───────┐                         │
                    │ PROMOTE GATE │── approved champion ─────┘
                    │ (human V1)   │
                    └──────────────┘
```

Loop policies (parallel execution, failure handling, rejuvenation) are specified
in [adr/ADR-004-research-loop-policies.md](adr/ADR-004-research-loop-policies.md).

---

## Adapter contract

The adapter surface is fixed at four host-facing operations (decision D-009):

1. **Manifest** — objective, budget ceiling, forbidden actions, evaluator ownership
2. **Search space** — finite typed domains per parameter; defaults for deltas
3. **Run experiment** — host receives a validated `ExperimentSpec`
4. **Report result** — host returns `ExperimentResult` (including failures)

Schemas in [../contracts/](../contracts/) are canonical; SDK models are
projections (ADR-003). Transports (HTTP, gRPC, in-process library) are
implementation choices left to adapters.

### Attachment principles (Law 5)

- Minimal surface: four operations, five schema types
- No invasive host refactors required
- Versioned contracts (`schema_version: "0.1"`)
- Host language agnostic

---

## Memory model

Each project receives an isolated SQLite store (Law 4, ADR-002):

- Findings are **immutable**; supersession uses `superseded_by`
- A **champion** table tracks the current best config and metric
- **Consecutive failure** tracking feeds a circuit breaker (ADR-004)
- No cross-project reads or writes in v0.1

The data model is tagged for a future optional shared-prior layer, but sharing
requires a new ADR — never an implicit shortcut.

---

## Control plane implementation (v0.1)

| Component | Location | Notes |
|-----------|----------|-------|
| Contract models | `sdk/kav_sdk/models.py` | Pydantic; enforces Laws 1–3 in validation |
| Project memory | `sdk/kav_sdk/memory.py` | SQLite per project |
| Whitelisted tools | `sdk/kav_sdk/tools.py` | Six deterministic tools wrapping SDK + memory |
| Agent harness | `sdk/kav_sdk/agent.py` | Deep Agents on LangGraph (ADR-001); raw-graph escape hatch preserved |

Tools are restricted to contract-shaped operations. Shell access, host filesystem
mutation, and evaluator invocation are excluded from the whitelist.

---

## Self-improvement scope

KAV may improve **its own research craft** — hypothesis generation strategies,
search-space exploration policies, contract ergonomics, validation methods.
Material appropriate for this repository includes:

- ADRs and the decision log
- Contract stress-test notes ([research/numerai-paper-exercise.md](research/numerai-paper-exercise.md))
- Evaluations of orchestration or memory policies

Host-project experiment results, production findings, and client-specific
investigations belong with the host, not in this repository.

---

## Related documents

- [five-laws.md](five-laws.md) — constitution
- [decisions.md](decisions.md) — decision log
- [adr/](adr/) — architecture decision records
- [research/five-nouns.md](research/five-nouns.md) — domain vocabulary
