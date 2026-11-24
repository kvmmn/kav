"""Tests for the five KAV contracts as Pydantic models."""
import pytest
from pydantic import ValidationError

from kav_sdk import (
    Budget, Change, Constraints, Domain, EvaluatorDecl, ExperimentResult,
    ExperimentSpec, FindingKind, Objective, Parameter, PolicyDecl,
    ProjectManifest, Reproducibility, ResearchFinding, ResultStatus,
    SearchSpace, validate_spec_against_project, SpecValidationError,
)


def manifest(**kw):
    d = dict(
        project_id="numerai-demo", schema_version="0.1", name="Numerai Demo",
        objective=Objective(metric="correlation", direction="maximize"),
        constraints=Constraints(
            max_budget_per_experiment=Budget(max_compute_hours=2),
            forbidden_actions=["touch_validation_set"],
        ),
        evaluator=EvaluatorDecl(owned_by="host"),
    )
    d.update(kw)
    return ProjectManifest(**d)


def space():
    return SearchSpace(
        project_id="numerai-demo",
        parameters=[
            Parameter(name="model.learning_rate", type="number",
                      domain=Domain(kind="range", min=0.0001, max=0.1, scale="log")),
            Parameter(name="features.set", type="categorical",
                      domain=Domain(kind="set", values=["small", "medium"])),
        ],
        defaults={"model.learning_rate": 0.01, "features.set": "medium"},
    )


def spec(**kw):
    d = dict(
        experiment_id="exp-abc123", project_id="numerai-demo",
        hypothesis_id="hyp-xyz789",
        changes=[Change(parameter="model.learning_rate", value=0.005)],
        budget=Budget(max_compute_hours=1),
        reproducibility=Reproducibility(seed=42),
    )
    d.update(kw)
    return ExperimentSpec(**d)


# ---- Law 1: evaluator sovereignty
def test_evaluator_owned_by_host_is_const():
    with pytest.raises(ValidationError):
        manifest(evaluator={"owned_by": "kav"})


def test_completed_result_requires_metric():
    with pytest.raises(ValidationError, match="Law 1"):
        ExperimentResult(experiment_id="exp-abc123", status="completed")


def test_failed_result_requires_error():
    with pytest.raises(ValidationError, match="error"):
        ExperimentResult(experiment_id="exp-abc123", status="failed")


# ---- Law 2: bounded autonomy
def test_manifest_without_any_budget_limit_rejected():
    with pytest.raises(ValidationError, match="Law 2"):
        manifest(constraints=Constraints(max_budget_per_experiment=Budget()))


def test_unbounded_range_domain_rejected():
    with pytest.raises(ValidationError, match="Law 2"):
        Domain(kind="range", min=0.0)  # no max


def test_spec_budget_exceeding_manifest_rejected():
    s = spec(budget=Budget(max_compute_hours=5))
    with pytest.raises(SpecValidationError, match="Law 2"):
        validate_spec_against_project(s, space(), manifest())


def test_change_outside_domain_rejected():
    s = spec(changes=[Change(parameter="model.learning_rate", value=99)])
    with pytest.raises(SpecValidationError):
        validate_spec_against_project(s, space(), manifest())


def test_frozen_parameter_rejected():
    sp = space()
    sp.parameters[0].mutable = False
    with pytest.raises(SpecValidationError, match="frozen"):
        validate_spec_against_project(spec(), sp, manifest())


# ---- happy paths
def test_valid_spec_passes_cross_validation():
    validate_spec_against_project(spec(), space(), manifest())


def test_result_roundtrip():
    r = ExperimentResult(
        experiment_id="exp-abc123", status="completed",
        evidence={"metric_value": 0.023},
    )
    assert r.status is ResultStatus.completed


def test_finding_kinds_include_failures():
    f = ResearchFinding(
        finding_id="fnd-a1b2c3", project_id="numerai-demo",
        experiment_id="exp-abc123", kind="refuted",
        statement="Raising learning rate to 0.05 degraded correlation.",
        confidence=0.4,
    )
    assert f.kind is FindingKind.refuted


def test_budget_covers_logic():
    big = Budget(max_compute_hours=2)
    small = Budget(max_compute_hours=1)
    unlimited = Budget()
    assert big.covers(small)
    assert not small.covers(big)
    assert not unlimited.covers(small)  # None cannot cover a concrete limit


# ---- graduated autonomy via manifest (D-032)
def test_omitted_policy_is_manual():
    m = manifest()
    assert m.policy is None
    assert m.promotion_mode() == "manual"


def test_policy_promotion_auto_guarded():
    m = manifest(policy=PolicyDecl(promotion="auto_guarded"))
    assert m.promotion_mode() == "auto_guarded"


def test_empty_policy_object_defaults_manual():
    m = manifest(policy=PolicyDecl())
    assert m.promotion_mode() == "manual"


def test_unknown_promotion_mode_rejected():
    with pytest.raises(ValidationError):
        manifest(policy={"promotion": "full_auto"})


def test_policy_thresholds_optional():
    m = manifest(policy=PolicyDecl(
        promotion="auto_guarded", min_delta=0.05, confirmations=4,
    ))
    assert m.promotion_min_delta() == 0.05
    assert m.promotion_confirmations() == 4


def test_omitted_thresholds_are_none():
    m = manifest(policy=PolicyDecl(promotion="auto_guarded"))
    assert m.promotion_min_delta() is None
    assert m.promotion_confirmations() is None
    m2 = manifest()
    assert m2.promotion_min_delta() is None
    assert m2.promotion_confirmations() is None


def test_zero_min_delta_is_declared():
    m = manifest(policy=PolicyDecl(min_delta=0))
    assert m.promotion_min_delta() == 0


def test_negative_min_delta_rejected():
    with pytest.raises(ValidationError):
        manifest(policy={"min_delta": -0.01})


def test_confirmations_below_one_rejected():
    with pytest.raises(ValidationError):
        manifest(policy={"confirmations": 0})


# ---- desk mode via manifest (D-034)
def test_omitted_desk_is_none():
    m = manifest()
    assert m.desk_mode() is None
    m2 = manifest(policy=PolicyDecl(promotion="auto_guarded"))
    assert m2.desk_mode() is None


def test_policy_desk_rich_digest():
    m = manifest(policy=PolicyDecl(desk="rich_digest"))
    assert m.desk_mode() == "rich_digest"


def test_policy_desk_minimal():
    m = manifest(policy=PolicyDecl(desk="minimal"))
    assert m.desk_mode() == "minimal"


def test_unknown_desk_mode_rejected():
    with pytest.raises(ValidationError):
        manifest(policy={"desk": "verbose"})


# ---- max_inflight via manifest (D-035)
def test_omitted_max_inflight_is_none():
    m = manifest()
    assert m.execution_max_inflight() is None
    m2 = manifest(policy=PolicyDecl(promotion="auto_guarded"))
    assert m2.execution_max_inflight() is None


def test_policy_max_inflight_declared():
    m = manifest(policy=PolicyDecl(max_inflight=4))
    assert m.execution_max_inflight() == 4


def test_max_inflight_below_one_rejected():
    with pytest.raises(ValidationError):
        manifest(policy={"max_inflight": 0})


# ---- desk tunables via manifest (D-036)
def test_omitted_desk_tunables_are_none():
    m = manifest()
    assert m.desk_k() is None
    assert m.desk_rejuvenation_every() is None
    assert m.desk_plateau_window() is None
    m2 = manifest(policy=PolicyDecl(promotion="auto_guarded"))
    assert m2.desk_k() is None
    assert m2.desk_rejuvenation_every() is None
    assert m2.desk_plateau_window() is None


def test_policy_desk_tunables_declared():
    m = manifest(policy=PolicyDecl(k=5, rejuvenation_every=3, plateau_window=4))
    assert m.desk_k() == 5
    assert m.desk_rejuvenation_every() == 3
    assert m.desk_plateau_window() == 4


def test_desk_k_below_one_rejected():
    with pytest.raises(ValidationError):
        manifest(policy={"k": 0})


def test_rejuvenation_every_below_one_rejected():
    with pytest.raises(ValidationError):
        manifest(policy={"rejuvenation_every": 0})


def test_plateau_window_below_one_rejected():
    with pytest.raises(ValidationError):
        manifest(policy={"plateau_window": 0})
