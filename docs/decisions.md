# KAV Decision Log

| # | Date | Decision | Status |
|---|------|----------|--------|
| D-001 | 2026-08-25 | Docs-first process: knowledge base in `docs/` before any code | Accepted |
| D-002 | 2026-08-25 | KAV is a **service** accessed via API, attachable to any host product to run its R&D | Accepted |
| D-003 | 2026-08-25 | Stack: LangChain / LangGraph / LangSmith; deepagents under evaluation as harness | Under study (→ ADR-001) |
| D-004 | 2026-08-25 | **Modularity & ease of attachment is the top prioritized quality attribute** — drives adapter design, API surface, and packaging | Accepted |

## Pending ADRs
- ADR-001: Raw LangGraph vs deepagents harness for Control Plane
| D-005 | 2026-08-25 | Memory is project-local in V1 (ADR-001); shared priors deferred, data model designed for future sharing | Accepted |
| D-006 | 2026-08-25 | Strictly one hypothesis per experiment (ADR-002); combinations only as typed combination hypotheses + ablation | Accepted |
| D-007 | 2026-08-25 | Five Laws ratified as project constitution (`docs/five-laws.md`) | Accepted |
| D-008 | 2026-08-25 | Adapter Contract is schema-first (JSON Schema canonical), Python bindings second (ADR-003) | Accepted |
| D-009 | 2026-08-25 | Adapter surface fixed at 4 operations: Manifest, SearchSpace, RunExperiment, ReportResult | Accepted |
| D-010 | 2026-08-25 | ProjectManifest v0.1 schema drafted (`contracts/project-manifest.schema.json`); declarations only, no access paths (Law 1 structural) | Accepted pending review |
| D-011 | 2026-08-25 | SearchSpace v0.1 drafted (`contracts/search-space.schema.json`): typed bounded parameters only — no expressions, no code (Law 5); all domains finite (Law 2) | Accepted pending review |
| D-012 | 2026-08-25 | ExperimentSpec v0.1 drafted: deltas-from-defaults, per-experiment budget <= manifest budget, mandatory seed (Law 2 + 8.9) | Accepted pending review |
| D-013 | 2026-08-25 | ExperimentResult v0.1 drafted: host reports measurement as-is; failures/timeouts are first-class results (Law 1 + 8.12); artifacts by reference only | Accepted pending review |
| D-014 | 2026-08-25 | Control Plane built on deepagents harness over LangGraph, with tool whitelist + KAV-owned backends; raw-LangGraph escape hatch preserved (ADR-004 file ADR-001-langgraph-vs-deepagents.md) | Accepted |
| D-015 | 2026-08-25 | Minimal-desk context (champion + top-k findings) with deliberate rejuvenation of discarded approaches | Accepted |
| D-016 | 2026-08-25 | Async parallel experiment execution; promotion policy pluggable: manual (V1 default) / auto_guarded; graduated autonomy long-run | Accepted |
| D-017 | 2026-08-25 | Failures always become findings + circuit-breaker (3 similar consecutive failures → halt & alert) | Accepted |
| D-018 | 2026-08-25 | ResearchFinding v0.1 drafted: 5 first-class kinds incl. failure kinds; immutable + superseded_by; conditions block enables rejuvenation | Accepted pending review |
| D-019 | 2026-08-25 | kav-sdk v0.1.0: Pydantic models for all 5 contracts; Laws enforced in code (evaluator const, budget coverage, finite domains, result coherence); 12 tests passing | Accepted |
| D-020 | 2026-08-25 | Paper exercise passed: 0 hard failures. Deferred: parameter coupling constraints (learn via findings first) and multi-metric evidence (artifacts for now). See research/numerai-paper-exercise.md | Accepted |
| D-021 | 2026-08-25 | Memory layer: one SQLite file per project (Law 4 structural); findings immutable + superseded_by; champion table; consecutive_failures() feeds circuit-breaker; 21 tests passing | Accepted |
| D-022 | 2026-08-25 | Control Plane skeleton: kav_sdk/tools.py (6 whitelisted tools, deterministic SDK wrappers) + agent.py (deepagents harness, Five Laws in system prompt); full manual cycle walkthrough passing (examples/walkthrough_one_cycle.py) | Accepted |
