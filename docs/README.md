# KAV Knowledge Base

Living documentation for the KAV project (**Knowledge through Adaptive Validation** — *Think. Test. Learn.*).

Master reference: [KAV_Product_and_Architecture_Master_Document.md](../KAV_Product_and_Architecture_Master_Document.md)

## Structure

- `adr/` — Architecture Decision Records. Every significant architectural decision gets a numbered ADR (context → decision → consequences). Immutable once accepted; superseded, never edited.
- `research/` — Research journal: prior-art findings, competitive analysis, design explorations.
- `decisions.md` — Lightweight running decision log (quick entries; promoted to ADRs when significant).

## Rules of the process

1. **Every step forward is documented.** No implementation without a decision or journal entry preceding it.
2. **Contracts before code.** Data contracts (ProjectManifest, SearchSpace, ExperimentSpec, ExperimentResult, ResearchFinding) are agreed in docs before implementation.
3. **The evaluator is sovereign.** Any design that lets KAV touch its own evaluator is rejected by default.

## Index

### ADRs
_(none yet — first ADRs to be drafted during architecture alignment)_

### Research
- [History Archive Findings](research/history-archive-findings.md) — relevant prior work from Claude history (Numerai guides, AutoML, stats foundations)
