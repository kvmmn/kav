# Numerai Adapter — Paper Exercise Findings
_Date: 2026-08-25 · Script: `examples/numerai/paper_exercise.py`_

## Result: contracts held. 0 hard failures, 2 design observations.

### What worked cleanly
- Manifest: composite metric (`corr_plus_tc`), forbidden actions, host-owned evaluator.
- SearchSpace: 5 realistic parameters across all 4 types (categorical/number/integer/boolean), mixed domains (log-range, int-range, sets).
- Spec flow: single-change hypothesis validated end-to-end against manifest + space.
- Results: artifacts-by-reference handles prediction files naturally.

### Observation 1 — Conditional dependencies between parameters
Real hosts have coupled parameters (xgb's useful learning-rate range differs from lgbm's).
V0.1 domains are per-parameter only; a combined-change spec is accepted as long as each
value is in its own domain.

**Decision (for now):** acceptable for V1 — the ANALYZE/DISTILL layer will learn coupling
as findings ("lr>0.1 harmful when model=xgb"). If coupling constraints become necessary,
the extension path is an optional `requires` field on Parameter (declarative, still no code).
Not adding it now: YAGNI + keep schema minimal.

### Observation 2 — Multi-metric results
Numerai reports corr, tc, and composite scores. ExperimentResult v0.1 has a single
`metric_value`. The manifest declares ONE trusted metric (Law 1 spirit: one sovereign
measure), so extra metrics currently have no home in evidence.

**Decision (for now):** keep single-metric contract; hosts may attach additional metrics
as artifacts (references). Revisit if strategy quality suffers from missing side-metrics.

## Conclusion
Contracts survive first contact with a real domain. Proceed to Control Plane skeleton / memory layer.
