# KAV — The Five Nouns (Domain Vocabulary)

> Step 2 of architecture alignment. Plain-language definitions, no technology.
> These five concepts are the atoms of everything KAV does.

---

## 1. Project

A **host system** that has a question worth answering, a bounded space of things that may be tried, and a trusted way to measure whether an answer is good.
*(Examples: a forecasting model, a RAG pipeline, a pricing engine.)*

## 2. Hypothesis

A **testable guess** about what change, within the project's allowed space, might improve its metric — specific enough that an experiment could prove it wrong.

## 3. Experiment

**One bounded attempt** to test exactly one hypothesis: fixed budget, fixed scope, fully specified before it runs, reproducible after it runs.

## 4. Evidence

The **trusted measurement** an experiment produced — produced by the project's own evaluator, never by KAV. Evidence is the only thing allowed to change KAV's beliefs.

## 5. Finding

**Durable knowledge** extracted from evidence: what was tried, what happened, what it means, and what to try next (or never again). Findings accumulate into memory across experiments.

---

## How they connect

```text
Project ──provides──▶ Hypothesis ──becomes──▶ Experiment
                                                  │
                    Finding ◀──distilled from── Evidence
                       │                          (from evaluator)
                       └────informs next────▶ Hypothesis
```

## Design rules these imply

1. A Project defines its own evaluator → KAV never measures for itself (**the evaluator is sovereign**).
2. A Hypothesis must be falsifiable within the SearchSpace → no vague guesses.
3. An Experiment is the unit of work → one hypothesis per experiment, always budgeted.
4. Evidence flows only from evaluator → KAV → memory; never the reverse direction of trust.
5. Findings are first-class data → negative results are findings too.

---
---
## Locked decisions (2026-08-25)

- **ADR-001:** Memory is project-local in V1. Findings never cross projects; the data model is designed so shared priors can be added later.
- **ADR-002:** Strictly one hypothesis per experiment. Combinations exist only as explicitly-typed combination hypotheses, always followed by ablation.

_Status: **Accepted** — this vocabulary is the foundation for all contracts and code._
