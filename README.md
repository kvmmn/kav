# KAV — Knowledge through Adaptive Validation

> **Think. Test. Learn.**

KAV is an autonomous research orchestrator, delivered as a **service**. Any host
product can attach KAV via API and hand it a bounded research problem; KAV converts
curiosity into knowledge through an evidence-gated loop:

```
Hypothesis → Bounded Experiment → Trusted Evidence → Memory → Better Hypothesis
```

## The Five Laws (constitution)

Every design decision and every line of code is checked against these:

1. **The evaluator is sovereign.** The host owns evaluation. KAV never grades itself.
2. **One hypothesis, one experiment, one budget.** No compound bets.
3. **No claim without lineage.** Every finding traces to evidence.
4. **Memory is project-local.** Findings never cross project boundaries in V1.
5. **Attachment is sacred.** The adapter contract is minimal, stable, and versioned.

Full text: [docs/five-laws.md](docs/five-laws.md)

## Repository layout

| Path | What it is |
|---|---|
| `contracts/` | JSON Schemas — the canonical interface (v0.1): manifest, search-space, experiment-spec, experiment-result, research-finding |
| `sdk/` | `kav_sdk` — Pydantic models mirroring the contracts, ProjectMemory (SQLite), whitelisted tools, deepagents control plane |
| `examples/` | Runnable proofs: Numerai paper exercise, one full deterministic research cycle |
| `docs/` | Knowledge base: ADRs, decision log, research notes |
| `KAV_Product_and_Architecture_Master_Document.md` | Original vision document (source of truth) |

## Quick start

```bash
cd sdk
pip install -e .
python3 -m pytest tests/ -q          # 21 tests
cd ..
python3 examples/walkthrough_one_cycle.py   # full deterministic cycle
```

## How we work

Docs-first: decisions are recorded as ADRs and entries in [docs/decisions.md](docs/decisions.md)
*before* code lands. Simple concepts first, then contracts, then implementation.

## Status

Foundation complete: Laws · Nouns · Contracts · SDK · Memory · Control-plane skeleton ·
end-to-end deterministic cycle. Next: real LLM wiring, first live loop, host adapters.
