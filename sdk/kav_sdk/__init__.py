"""KAV SDK — the five contracts as Pydantic models.

Mirrors contracts/*.schema.json (v0.1). The JSON Schemas are canonical;
these models are the Python projection (ADR-003).
"""
from kav_sdk.models import (
    ParamType, ResultStatus, FindingKind, SpecValidationError,
    validate_spec_against_project,
    ProjectManifest, Objective, Constraints, Budget, EvaluatorDecl,
    SearchSpace, Parameter, Domain,
    ExperimentSpec, Change, Reproducibility,
    ExperimentResult, Evidence, CostActual, ArtifactRef, ErrorInfo,
    ResearchFinding, Metrics,
)

__all__ = [
    "ProjectManifest", "Objective", "Constraints", "Budget", "EvaluatorDecl",
    "SearchSpace", "Parameter", "Domain",
    "ExperimentSpec", "Change", "Reproducibility",
    "ExperimentResult", "Evidence", "CostActual", "ArtifactRef", "ErrorInfo",
    "ResearchFinding", "Metrics",
]
__version__ = "0.1.0"
from kav_sdk.models import Budget as _B  # noqa: F401  (already exported above)
