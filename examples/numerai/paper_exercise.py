"""Numerai Adapter paper exercise: stress the contracts against a real host.

Runs a realistic Numerai project through the SDK and prints every friction point.
"""
import sys
sys.path.insert(0, "sdk")

from kav_sdk import (
    Budget, Change, Constraints, Domain, EvaluatorDecl, ExperimentResult,
    ExperimentSpec, Evidence, Objective, Parameter, ProjectManifest,
    Reproducibility, SearchSpace, validate_spec_against_project,
)

frictions = []


def note(label, detail):
    frictions.append((label, detail))
    print(f"\n### FRICTION [{label}]\n{detail}")


# ---------------------------------------------------------------- 1. Manifest
print("== 1. ProjectManifest ==")
try:
    manifest = ProjectManifest(
        project_id="numerai-main",
        name="Numerai Tournament Model",
        description="Weekly Numerai tournament; predict era-weighted stock returns.",
        objective=Objective(
            metric="corr_plus_tc",  # Numerai's composite score
            direction="maximize",
            baseline=0.021,
        ),
        constraints=Constraints(
            max_budget_per_experiment=Budget(max_compute_hours=4),
            forbidden_actions=[
                "peek_validation_eras",
                "submit_without_stake_check",
            ],
        ),
        evaluator=EvaluatorDecl(
            owned_by="host",
            description="Numerai's official scoring on validation eras (corr + tc).",
        ),
    )
    print("manifest OK:", manifest.project_id)
except Exception as e:
    note("manifest", f"{type(e).__name__}: {e}")

# ---------------------------------------------------------------- 2. SearchSpace
print("\n== 2. SearchSpace ==")
try:
    space = SearchSpace(
        project_id="numerai-main",
        parameters=[
            Parameter(name="model.type", type="categorical",
                      domain=Domain(kind="set", values=["lgbm", "xgb", "et"])),
            Parameter(name="model.learning_rate", type="number",
                      domain=Domain(kind="range", min=0.005, max=0.3, scale="log")),
            Parameter(name="model.num_leaves", type="integer",
                      domain=Domain(kind="range", min=16, max=256)),
            Parameter(name="features.set", type="categorical",
                      domain=Domain(kind="set", values=["v4_small", "v4_medium", "v4_all"])),
            Parameter(name="ensemble.era_boosting", type="boolean",
                      domain=Domain(kind="set", values=[True, False])),
        ],
        defaults={
            "model.type": "lgbm",
            "model.learning_rate": 0.05,
            "model.num_leaves": 64,
            "features.set": "v4_medium",
            "ensemble.era_boosting": False,
        },
    )
    print("space OK:", len(space.parameters), "parameters")
except Exception as e:
    note("search-space", f"{type(e).__name__}: {e}")

# ------------------------------------------------- 3. Hypothesis -> Spec flow
print("\n== 3. Hypothesis -> ExperimentSpec ==")
try:
    spec = ExperimentSpec(
        experiment_id="exp-num001",
        project_id="numerai-main",
        hypothesis_id="hyp-xgboost-vs-lgbm",
        changes=[Change(parameter="model.type", value="xgb")],
        budget=Budget(max_compute_hours=3),
        reproducibility=Reproducibility(seed=42, dataset_ref="numerai-v4.3-round570"),
    )
    validate_spec_against_project(spec, space, manifest)
    print("spec validated:", spec.experiment_id)
except Exception as e:
    note("spec-flow", f"{type(e).__name__}: {e}")

# ------------------------------------------- 4. STRAIN TEST: real-world needs
print("\n== 4. Strain tests ==")

# 4a. Conditional dependency: xgb wants different learning-rate range than lgbm.
try:
    bad = ExperimentSpec(
        experiment_id="exp-num002", project_id="numerai-main",
        hypothesis_id="hyp-xgb-high-lr",
        changes=[
            Change(parameter="model.type", value="xgb"),
            Change(parameter="model.learning_rate", value=0.25),
        ],
        budget=Budget(max_compute_hours=3),
        reproducibility=Reproducibility(seed=42),
    )
    validate_spec_against_project(bad, space, manifest)
    print("4a combined-change spec accepted (per-parameter domains only)")
except Exception as e:
    note("conditional-deps", f"combined changes rejected: {e}")

# 4b. Multi-metric reality: Numerai reports corr AND tc AND corr_plus_tc.
try:
    res = ExperimentResult(
        experiment_id="exp-num001", status="completed",
        evidence=Evidence.model_validate({
            "metric_value": 0.024,
            "cost_actual": {"compute_hours": 2.6},
            # extra metrics have no home in v0.1:
            # "corr": 0.020, "tc": 0.008
        }),
    )
    print("4b result accepted with single metric_value only")
except Exception as e:
    note("multi-metric", f"{type(e).__name__}: {e}")

# 4c. Partial-run results (host returns per-era scores / prediction files).
res2 = ExperimentResult(
    experiment_id="exp-num001", status="completed",
    evidence=Evidence(
        metric_value=0.024,
        artifacts=[{"ref": "s3://kav-artifacts/exp-num001/predictions.parquet",
                    "kind": "predictions"}],
    ),
)
print("4c artifacts-by-reference OK:", res2.evidence.artifacts[0].ref)

# ---------------------------------------------------------------- report
print("\n" + "=" * 60)
print(f"PAPER EXERCISE COMPLETE — {len(frictions)} frictions found")
for label, d in frictions:
    print(f" - [{label}] {d[:100]}")
