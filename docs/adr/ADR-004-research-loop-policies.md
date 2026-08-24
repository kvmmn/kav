# ADR-004: Research Loop Policies

**Status:** Accepted · **Date:** 2026-08-25

## Q1 — Context richness: Minimal desk (Option A), with deliberate re-exploration
Graph state carries only: champion config + top-k most relevant findings (k≈10).
BUT: the strategy layer may deliberately re-surface previously discarded approaches
("rejuvenation") — e.g., when conditions changed (new data, new features, plateau)
or periodically, so old failures can be rethought rather than permanently buried.
Retrieval mechanism designed so a rich-history digest mode is a config change later.

## Q2 — Pauses: parallel async execution; promotion policy is pluggable
- After DESIGN, KAV continues working on other hypotheses while the host executes
  asynchronously. The loop is event-driven (wakes on result ingestion).
- Promotion policy is a **pluggable component** with two V1 modes:
  - `manual` (default): every promotion requires human approval.
  - `auto_guarded`: auto-promote only when improvement exceeds threshold on N
    independent confirmations AND no forbidden-action violations; human notified.
  Long-run goal: graduated autonomy — the owner chooses per project via manifest/policy.

## Q3 — Failures: finding-always + circuit-breaker
- Every failed/timeout/rejected run routes through normal analysis and distills
  a finding (principle 8.12).
- Circuit breaker: 3 consecutive failures of structurally similar specs → halt
  the current strategy, raise a systemic-issue alert to the human.

## Laws check
L1 ✓ host still measures · L2 ✓ budgets unchanged · L3 ✓ every route produces
lineage-traced findings · L4 ✓ all memory project-local · L5 ✓ no new host demands.
