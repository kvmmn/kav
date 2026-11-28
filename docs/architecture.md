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
4. Continues other hypotheses while the host evaluator runs; wakes on result ingest
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
                    │ desk: champ  │                         │
                    │ + top-k +    │                         │
                    │ rejuvenated  │                         │
                    │ (+ digest if │                         │
                    │  rich_digest)│                         │
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
                    │ manual /     │
                    │ auto_guarded │
                    └──────────────┘
```

Loop policies (parallel execution, failure handling, rejuvenation) are specified
in [adr/ADR-004-research-loop-policies.md](adr/ADR-004-research-loop-policies.md).

---

## Adapter contract

The adapter surface is fixed at four host-facing operations (decision D-009):

1. **Manifest** — objective, budget ceiling, forbidden actions, evaluator ownership, optional `policy.promotion` (`manual` default / `auto_guarded`; D-032) plus optional `min_delta` / `confirmations` (D-033), optional `policy.desk` (`minimal` / `rich_digest`; D-034), optional `policy.k` / `rejuvenation_every` / `plateau_window` (D-036), optional `policy.digest_cap` (≥ 1; D-038), optional `policy.max_inflight` (≥ 1; D-035), and optional `policy.circuit_breaker` (≥ 1; D-037)
2. **Search space** — finite typed domains per parameter; defaults for deltas
3. **Run experiment** — host receives a validated `ExperimentSpec`
4. **Report result** — host returns `ExperimentResult` (including failures)

Schemas in [../contracts/](../contracts/) are canonical; SDK models are
projections (ADR-003). v0.1 ships two transports of the same four operations:
in-process (`kav_sdk.adapter`) and HTTP/OpenAPI (`kav_sdk.http`,
[adapter-http.openapi.json](../contracts/adapter-http.openapi.json)). gRPC
remains a later choice.

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
- **Consecutive failure** tracking feeds a circuit breaker (ADR-004 / D-027 /
  D-037). N consecutive failures of structurally similar specs halt the
  strategy and write an `operational` finding as the human alert. The host
  chooses N per project via optional `policy.circuit_breaker` on the
  manifest; attach seeds project-local `circuit_policy.threshold`; omitted
  keeps the local value (default 3). Resume is human-gated.
- **Finding-always** on non-completed ingest (ADR-004 Q3 / D-040):
  `failed` / `timeout` / `rejected` write one `inconclusive` finding with
  experiment lineage. Completed results stay agent-distilled. KAV does not
  reinterpret a missing measurement as refuted (Law 1).
- **Promotion policy** is pluggable (ADR-004 Q2 / D-028 / D-032 / D-033): the
  host chooses per project via optional `policy.promotion` on the manifest
  (`manual` default if omitted, or `auto_guarded`) and optional
  `policy.min_delta` / `policy.confirmations`. Attach seeds project-local
  policy from those declarations; omitted tunables keep local values
  (defaults 0 and 2). `manual` requires the human `promote` tool;
  `auto_guarded` promotes when a `confirmed` finding has N independent
  confirmations beating the champion by `min_delta` with no active `harmful`
  finding, and writes an `operational` notice.
- **Desk** is the OBSERVE graph state (ADR-004 Q1 / D-029 / D-031 / D-034 / D-036):
  champion + top-k active findings. Mode is a config change: `minimal`
  (default) or `rich_digest` (compact off-desk history). The host chooses per
  project via optional `policy.desk` / `policy.k` / `policy.rejuvenation_every`
  / `policy.plateau_window` / `policy.digest_cap` on the manifest; attach seeds
  those `desk_policy` fields; omitted keeps local values (defaults `minimal`,
  10, 8, 5, 30). Discarded approaches re-enter the desk on plateau, a periodic cadence,
  a search-space condition change, or a human `rejuvenate`.
- **Execution** is event-driven (ADR-004 Q2 / D-030 / D-035 / D-039): queued vs
  in-flight specs, `max_inflight` (default 2), and `result_ingested` wakes
  delivered once on OBSERVE. The host chooses the cap per project via optional
  `policy.max_inflight` on the manifest; attach seeds project-local
  `execution_policy.max_inflight`; omitted keeps the local value. Sequential
  `drain_pending` remains for halt-safe convenience. Declared
  `max_wall_time_seconds` (spec budget, else manifest ceiling) is honored as
  `status=timeout`; omitted wall time stays unbounded.
- No cross-project reads or writes in v0.1

The data model is tagged for a future optional shared-prior layer, but sharing
requires a new ADR — never an implicit shortcut.

---

## Control plane implementation (v0.1)

| Component | Location | Notes |
|-----------|----------|-------|
| Contract models | `sdk/kav_sdk/models.py` | Pydantic; enforces Laws 1–3 in validation |
| Project memory | `sdk/kav_sdk/memory.py` | SQLite per project; `pending_specs()` FIFO; in-flight + wakes (D-030); finding-always on non-completed ingest (D-040) |
| Host adapter | `sdk/kav_sdk/adapter.py` | In-process projection of the four operations; `SimulatedHost` + `HostRunner` (D-025); `dispatch_pending` / `collect_finished` (D-030); declared wall-time timeout (D-039) |
| HTTP adapter | `sdk/kav_sdk/http.py` | OpenAPI 3.0 projection of the same four operations; stdlib server + `HttpHostAdapter` (D-026) |
| Whitelisted tools | `sdk/kav_sdk/tools.py` | Eight deterministic tools wrapping SDK + memory (`resume_strategy` and `rejuvenate` are human-gated; `promote` is the human override; ingest auto-distills non-completed runs, D-040) |
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
