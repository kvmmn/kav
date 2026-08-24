# ADR-002: Project-Local Memory in V1 & One Hypothesis Per Experiment

**Status:** Accepted · **Date:** 2026-08-25

## Context
KAV will eventually serve many host projects. Findings learned in one project could
inform another (master doc Level 5, "Multi-Project Research Network"). We must decide
now whether memory is shared or isolated.

## Decision
**V1 memory is strictly project-local.** No Finding crosses project boundaries.
However, the data model must be designed so a shared-prior layer can be added later
without migration pain (findings carry domain tags and structured semantics).

## Consequences
- (+) Simpler V1; no cross-contamination of lessons; clear isolation guarantees.
- (+) Future sharing is additive, not a rewrite.
- (−) Repeated discovery of the same lesson across projects until Level 5 ships.

---

# Part B: One Hypothesis Per Experiment

**Status:** Accepted · **Date:** 2026-08-25

## Context
Combination experiments cover search space faster but confound attribution:
if two changes are made together and the metric improves, causality is unknown.

## Decision
**Strictly one hypothesis per experiment.** Combinations are permitted only as an
explicitly-typed *combination hypothesis* — itself a single falsifiable claim,
always paired with ablation follow-ups before any promotion.

## Consequences
- (+) Clean causal attribution; every improvement is explainable.
- (+) Aligns with "Every Claim Needs Evidence" principle.
- (−) Slower coverage of large search spaces; mitigated by strategy-level batching
  of parallel single-hypothesis experiments.
