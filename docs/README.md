# KAV Documentation

Living documentation for **KAV** (*Knowledge through Adaptive Validation*).

## Start here

| Document | Purpose |
|----------|---------|
| [architecture.md](architecture.md) | Public architecture overview |
| [five-laws.md](five-laws.md) | Project constitution |
| [decisions.md](decisions.md) | Lightweight decision log |
| [adr/](adr/) | Architecture Decision Records |

## Structure

- **`adr/`** — Architecture Decision Records. Each ADR captures context,
  decision, and consequences. Accepted ADRs are immutable; supersede, do not edit.
- **`research/`** — Method notes on KAV itself (domain vocabulary, contract
  validation exercises). Not host-project findings.
- **`decisions.md`** — Running log of decisions; significant entries are
  promoted to ADRs.

## Process rules

1. **Document before implementing.** No significant code without a preceding
   decision or ADR entry.
2. **Contracts before code.** The five JSON Schemas in `contracts/` are agreed
   in docs before SDK changes land.
3. **The evaluator is sovereign.** Designs that let KAV touch its own evaluator
   are rejected by default.

## ADR index

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](adr/ADR-001-langgraph-vs-deepagents.md) | Control plane: LangGraph vs Deep Agents harness | Accepted |
| [ADR-002](adr/ADR-002-project-local-memory-and-single-hypothesis.md) | Project-local memory; one hypothesis per experiment | Accepted |
| [ADR-003](adr/ADR-003-schema-first-adapter-contract.md) | Schema-first adapter contract | Accepted |
| [ADR-004](adr/ADR-004-research-loop-policies.md) | Research loop policies | Accepted |

## Research notes

| Note | Description |
|------|-------------|
| [five-nouns.md](research/five-nouns.md) | Domain vocabulary (Project, Hypothesis, Experiment, Evidence, Finding) |
| [numerai-paper-exercise.md](research/numerai-paper-exercise.md) | Contract stress test against a synthetic domain example |
