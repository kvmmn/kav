# KAV Decision Log

Lightweight record of project decisions. Significant entries are promoted to
ADRs in [adr/](adr/).

| # | Date | Decision | Status |
|---|------|----------|--------|
| D-001 | 2026-08-25 | Docs-first process: knowledge base in `docs/` before any code | Accepted |
| D-002 | 2026-08-25 | KAV is a **service** accessed via API, attachable to any host product to run its R&D | Accepted |
| D-003 | 2026-08-25 | Stack: LangChain / LangGraph / LangSmith; deepagents under evaluation as harness | Accepted (→ ADR-001) |
| D-004 | 2026-08-25 | **Modularity and ease of attachment** is the top prioritized quality attribute | Accepted |
| D-005 | 2026-08-25 | Memory is project-local in v0.1; shared priors deferred (→ ADR-002) | Accepted |
| D-006 | 2026-08-25 | Strictly one hypothesis per experiment (→ ADR-002) | Accepted |
| D-007 | 2026-08-25 | Five Laws ratified as project constitution (`docs/five-laws.md`) | Accepted |
| D-008 | 2026-08-25 | Adapter contract is schema-first, Python bindings second (→ ADR-003) | Accepted |
| D-009 | 2026-08-25 | Adapter surface fixed at 4 operations: Manifest, SearchSpace, RunExperiment, ReportResult | Accepted |
| D-010 | 2026-08-25 | ProjectManifest v0.1 schema drafted; declarations only, no evaluator access paths | Accepted |
| D-011 | 2026-08-25 | SearchSpace v0.1: typed bounded parameters only; all domains finite | Accepted |
| D-012 | 2026-08-25 | ExperimentSpec v0.1: deltas-from-defaults, per-experiment budget ≤ manifest budget, mandatory seed | Accepted |
| D-013 | 2026-08-25 | ExperimentResult v0.1: host reports measurement as-is; failures/timeouts first-class | Accepted |
| D-014 | 2026-08-25 | Control plane on Deep Agents harness over LangGraph; raw-LangGraph escape hatch preserved (→ ADR-001) | Accepted |
| D-015 | 2026-08-25 | Minimal-desk context (champion + top-k findings) with deliberate rejuvenation | Accepted |
| D-016 | 2026-08-25 | Async parallel experiment execution; pluggable promotion policy (manual default) | Accepted |
| D-017 | 2026-08-25 | Failures always become findings; circuit-breaker after 3 similar consecutive failures | Accepted |
| D-018 | 2026-08-25 | ResearchFinding v0.1: five first-class kinds; immutable + superseded_by | Accepted |
| D-019 | 2026-08-25 | kav-sdk v0.1.0: Pydantic models for all five contracts; Laws enforced in validation | Accepted |
| D-020 | 2026-08-25 | Contract paper exercise passed: zero hard failures; see `research/numerai-paper-exercise.md` | Accepted |
| D-021 | 2026-08-25 | Memory layer: one SQLite file per project; champion table; circuit-breaker support | Accepted |
| D-022 | 2026-08-25 | Control plane skeleton: whitelisted tools + agent harness; deterministic walkthrough passing | Accepted |
| D-023 | 2026-08-25 | Repository scaffolding: README, `.gitignore`, ADR numbering fixed; 21/21 tests green | Accepted |
| D-024 | 2026-08-25 | First live LLM cycle: Laws held through spec self-correction; multi-turn host-runner loop added | Accepted |
| D-025 | 2026-11-13 | Host Adapter v0.1: Python in-process projection of the four operations (`HostAdapter` + `SimulatedHost` + `HostRunner`); `pending_specs()` FIFO for `result IS NULL`; live and walkthrough cycles use the runner instead of wrapping `issue_spec` | Accepted |
| D-026 | 2026-11-14 | HTTP/OpenAPI v0.1 projection of the four adapter operations: stdlib server wrapping any `HostAdapter`, `HttpHostAdapter` client, OpenAPI 3.0 in `contracts/adapter-http.openapi.json`. Payload JSON Schemas remain canonical (ADR-003). No extra runtime dependency. | Accepted |
| D-027 | 2026-11-15 | Circuit-breaker **halt** (ADR-004 Q3 / D-017): three consecutive failures (`failed` / `timeout` / `rejected`) of structurally similar specs — same sorted set of changed parameter names — halt the current strategy. Ingest writes one `operational` finding as the human alert (existing finding kind; no schema change). `issue_spec` and `HostRunner.drain_pending` refuse further work until a human `resume_strategy`. The streak counter already existed; halt + alert did not. V1 promotion stays `manual`. | Accepted |
| D-028 | 2026-11-16 | `auto_guarded` promotion policy (ADR-004 Q2 / D-016): pluggable V1 modes `manual` (default; human `promote` tool) and `auto_guarded`. Auto-promote only when a `confirmed` finding lands, improvement vs the current champion exceeds `min_delta` (default 0) on N independent confirmations (default 2; distinct experiment ids and seeds, same reconstructed config), and no active `harmful` finding exists for that config (forbidden-action / Law 3 gate). Writes one `operational` finding as the human notification. No contract schema change. Halt still blocks. The `promote` tool remains a human override in both modes. | Accepted |
| D-029 | 2026-11-17 | Minimal desk + rejuvenation (ADR-004 Q1 / D-015): OBSERVE graph state is champion + top-k active findings (default k=10). Discarded approaches (superseded findings, and refuted findings that fell off the desk) re-enter via a rejuvenation slot when the last `plateau_window` completed runs do not beat the champion, every `rejuvenation_every` completed runs, the search space gains a parameter unknown to those findings, or a human `rejuvenate` tool forces it. Writes one `operational` finding as the notice. No contract schema change. Rich-history digest remains a later config change. | Accepted |
