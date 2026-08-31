# KAV — Knowledge through Adaptive Validation

**KAV** is a domain-agnostic research orchestrator that connects to host systems
through a minimal, schema-first adapter contract. It generates testable hypotheses,
issues bounded experiment specifications, ingests trusted evidence from the host
evaluator, and accumulates project-local memory to improve subsequent research
policy.

> **Think. Test. Learn.**

**Author:** [Kaveh Momeni](https://github.com/kvmmn)  
**Status:** v0.1 foundation — contracts, SDK, memory layer, and deterministic
research cycle are implemented; live LLM-driven cycles are experimental.

---

## Who KAV is for

KAV is intended for researchers and engineers who operate measurable systems and
want a **repeatable, auditable loop** for structured experimentation:

- Host systems with a declared objective, bounded search space, and trusted evaluator
- Teams that need **evidence-gated** promotion rather than ad-hoc tuning
- Integrators building adapters in any language (contracts are JSON Schema first)

KAV does **not** replace the host evaluator, mutate host code, or claim success
without lineage. The host remains sovereign over measurement.

---

## Research loop

KAV implements a closed loop with explicit gates at each transition:

```
Hypothesis → Bounded Experiment → Trusted Evidence → Memory → Better Hypothesis
```

| Stage | Actor | Output |
|-------|-------|--------|
| Observe | KAV | Champion config, active findings, circuit-breaker state |
| Hypothesize | KAV | One falsifiable claim within the search space |
| Design | KAV | `ExperimentSpec` — single change, fixed budget, reproducible seed |
| Execute | Host (adapter) | Runs experiment; KAV never touches the evaluator |
| Ingest | Host → KAV | `ExperimentResult` — measurement as reported, failures included |
| Distill | KAV | `ResearchFinding` — durable knowledge with lineage |
| Promote | Human (V1 default) | Champion update only after explicit approval |

See [docs/architecture.md](docs/architecture.md) for control-plane vs.
execution-plane separation and adapter operations.

---

## The Five Laws (constitution)

Every design decision, contract field, and SDK validation rule is checkable
against these laws. Amendments require an explicit ADR.

1. **The evaluator is sovereign.** The host owns evaluation. KAV never grades itself.
2. **One hypothesis, one experiment, one budget.** No compound bets.
3. **No claim without lineage.** Every finding traces to evidence.
4. **Memory is project-local.** Findings never cross project boundaries in v0.1.
5. **Attachment is sacred.** The adapter contract is minimal, stable, and versioned.

Full text: [docs/five-laws.md](docs/five-laws.md)

---

## Adapter contract (v0.1)

KAV attaches to a host through four operations defined in [contracts/](contracts/):

| Operation | Schema | Purpose |
|-----------|--------|---------|
| Register manifest | `project-manifest.schema.json` | Objective, constraints, evaluator ownership |
| Declare search space | `search-space.schema.json` | Bounded, typed parameters and defaults |
| Issue experiment | `experiment-spec.schema.json` | Single-change, budgeted, reproducible spec |
| Report result | `experiment-result.schema.json` | Host-reported measurement and artifacts |

Findings (`research-finding.schema.json`) are KAV-owned records distilled from
results. Python bindings live in [sdk/kav_sdk/](sdk/kav_sdk/) (ADR-003:
schema-first, language bindings second).

---

## Repository layout

| Path | Description |
|------|-------------|
| [contracts/](contracts/) | Canonical JSON Schemas (v0.1) |
| [sdk/](sdk/) | `kav-sdk` — Pydantic models, project-local SQLite memory, whitelisted tools |
| [examples/](examples/) | Deterministic walkthrough and contract stress tests |
| [docs/](docs/) | Architecture, ADRs, decision log, method notes |
| [docs/adr/](docs/adr/) | Architecture Decision Records (immutable once accepted) |

---

## Quick start

Requirements: Python 3.11+

```bash
# Install the SDK
cd sdk
pip install -e .
python3 -m pytest tests/ -q

# Run the deterministic one-cycle walkthrough (no LLM, no API keys)
cd ..
python3 examples/walkthrough_one_cycle.py
```

The walkthrough simulates the full loop — observe → hypothesize → validate →
issue → ingest → distill → promote — using in-memory tools and a temporary
SQLite store.

Optional: `examples/live_one_cycle.py` runs an LLM-driven cycle when
`OPENROUTER_API_KEY` is set. This path is experimental and not required to
validate the foundation.

---

## Documentation and governance

KAV follows a **docs-first** process: significant decisions are recorded before
implementation lands.

- [docs/architecture.md](docs/architecture.md) — public architecture overview
- [docs/decisions.md](docs/decisions.md) — lightweight decision log
- [docs/adr/](docs/adr/) — architecture decision records
- [docs/research/](docs/research/) — method notes on the tool itself (contract
  validation, domain vocabulary)

Self-improvement material in this repository covers **KAV's research craft**
(search strategies, hypothesis methods, ADRs). Host-project experiment results
and findings do not belong in this repository.

---

## Citation

If you use KAV in academic or technical work, please cite:

```bibtex
@software{momeni2026kav,
  author       = {Momeni, Kaveh},
  title        = {KAV: Knowledge through Adaptive Validation},
  year         = {2026},
  url          = {https://github.com/kvmmn/kav},
  note         = {Autonomous research orchestrator with schema-first host attachment}
}
```

A [CITATION.cff](CITATION.cff) file is also provided for GitHub's citation widget.

---

## License

MIT License — see [LICENSE](LICENSE).
