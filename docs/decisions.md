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
