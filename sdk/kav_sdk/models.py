"""KAV contracts as Pydantic models — Python projection of contracts/*.schema.json v0.1."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_ID = r"^[a-z][a-z0-9-]{2,63}$"
_EXP = r"^exp-[a-z0-9-]{6,64}$"
_HYP = r"^hyp-[a-z0-9-]{6,64}$"
_FND = r"^fnd-[a-z0-9-]{6,64}$"

SCHEMA_VERSION = "0.1"


def _strict(model: type[BaseModel]) -> type[BaseModel]:
    """additionalProperties: false for every contract model."""
    model.model_config = ConfigDict(extra="forbid")
    return model


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- Budget
@_strict
class Budget(BaseModel):
    max_wall_time_seconds: int | None = Field(default=None, ge=1)
    max_cost_units: float | None = Field(default=None, gt=0)
    max_compute_hours: float | None = Field(default=None, gt=0)

    def covers(self, other: "Budget") -> bool:
        """True if every limit in `other` is within this budget (Law 2)."""
        for f in ("max_wall_time_seconds", "max_cost_units", "max_compute_hours"):
            a, b = getattr(self, f), getattr(other, f)
            if b is not None and (a is None or b > a):
                return False
        return True


# ------------------------------------------------------- ProjectManifest
@_strict
class Objective(BaseModel):
    metric: str = Field(min_length=1)
    direction: Literal["maximize", "minimize"]
    baseline: float | None = None


@_strict
class EvaluatorDecl(BaseModel):
    # Law 1 made structural: only the host can own the evaluator.
    owned_by: Literal["host"]
    description: str | None = Field(default=None, max_length=2000)


@_strict
class Constraints(BaseModel):
    max_budget_per_experiment: Budget
    forbidden_actions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _at_least_one_limit(self) -> "Constraints":
        b = self.max_budget_per_experiment
        if not any(getattr(b, f) is not None
                   for f in ("max_wall_time_seconds", "max_cost_units", "max_compute_hours")):
            raise ValueError("Law 2: manifest must declare at least one budget limit")
        return self


@_strict
class ProjectManifest(BaseModel):
    project_id: str = Field(pattern=_ID)
    schema_version: str = SCHEMA_VERSION
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    objective: Objective
    constraints: Constraints
    evaluator: EvaluatorDecl


# ------------------------------------------------------------ SearchSpace
class ParamType(str, Enum):
    number = "number"
    integer = "integer"
    categorical = "categorical"
    boolean = "boolean"


@_strict
class Domain(BaseModel):
    kind: Literal["range", "set"]
    min: float | None = None
    max: float | None = None
    scale: Literal["linear", "log"] = "linear"
    values: list[Union[str, int, float, bool]] | None = None

    @model_validator(mode="after")
    def _finite(self) -> "Domain":
        # Law 2 structural: every domain must be bounded.
        if self.kind == "range":
            if self.min is None or self.max is None:
                raise ValueError("Law 2: range domain requires min and max (no unbounded spaces)")
            if not self.min < self.max:
                raise ValueError("range domain requires min < max")
        else:
            if not self.values or len(set(map(str, self.values))) < 2:
                raise ValueError("set domain requires at least 2 unique values")
        return self

    def contains(self, value: Any) -> bool:
        if self.kind == "range":
            return self.min <= value <= self.max  # type: ignore[operator]
        return any(value == v for v in (self.values or []))


@_strict
class Parameter(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_.]{0,63}$")
    type: ParamType
    domain: Domain
    mutable: bool = True
    cost_hint: float | None = Field(default=None, gt=0)
    description: str | None = None


@_strict
class SearchSpace(BaseModel):
    project_id: str = Field(pattern=_ID)
    schema_version: str = SCHEMA_VERSION
    parameters: list[Parameter] = Field(min_length=1)
    defaults: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _defaults_in_domain(self) -> "SearchSpace":
        by_name = {p.name: p for p in self.parameters}
        for k, v in self.defaults.items():
            if k not in by_name:
                raise ValueError(f"default '{k}' has no matching parameter")
            if not by_name[k].domain.contains(v):
                raise ValueError(f"default value {v!r} for '{k}' outside declared domain")
        return self

    def param(self, name: str) -> Parameter:
        for p in self.parameters:
            if p.name == name:
                return p
        raise KeyError(f"unknown parameter: {name}")


# --------------------------------------------------------- ExperimentSpec
@_strict
class Change(BaseModel):
    parameter: str
    value: Any


@_strict
class Reproducibility(BaseModel):
    seed: int
    dataset_ref: str | None = None
    environment_ref: str | None = None
    notes: str | None = None


@_strict
class ExperimentSpec(BaseModel):
    experiment_id: str = Field(pattern=_EXP)
    project_id: str = Field(pattern=_ID)
    hypothesis_id: str = Field(pattern=_HYP)
    changes: list[Change] = Field(min_length=1)
    budget: Budget = Field(default_factory=Budget)
    reproducibility: Reproducibility
    created_at: datetime = Field(default_factory=utcnow)
    notes: str | None = Field(default=None, max_length=2000)


class SpecValidationError(ValueError):
    """Raised when a spec violates its SearchSpace or manifest constraints."""


def validate_spec_against_project(
    spec: ExperimentSpec,
    space: SearchSpace,
    manifest: ProjectManifest,
) -> None:
    """Cross-contract validation KAV performs before issuing a spec (Law 2)."""
    if spec.project_id != space.project_id or spec.project_id != manifest.project_id:
        raise SpecValidationError("project_id mismatch across spec/space/manifest")

    seen: set[str] = set()
    for ch in spec.changes:
        p = space.param(ch.parameter)  # raises on unknown parameter
        if not p.mutable:
            raise SpecValidationError(f"parameter '{ch.parameter}' is frozen (mutable=false)")
        if not p.domain.contains(ch.value):
            raise SpecValidationError(f"value {ch.value!r} outside domain of '{ch.parameter}'")
        if ch.parameter in seen:
            raise SpecValidationError(f"duplicate change for '{ch.parameter}'")
        seen.add(ch.parameter)

    if not spec.budget.covers(spec.budget):  # pragma: no cover - trivially true
        pass
    if not manifest.constraints.max_budget_per_experiment.covers(spec.budget):
        raise SpecValidationError("Law 2: spec budget exceeds manifest limits")


# ------------------------------------------------------- ExperimentResult
class ResultStatus(str, Enum):
    completed = "completed"
    failed = "failed"
    timeout = "timeout"
    rejected = "rejected"


@_strict
class CostActual(BaseModel):
    wall_time_seconds: int | None = Field(default=None, ge=0)
    cost_units: float | None = Field(default=None, ge=0)
    compute_hours: float | None = Field(default=None, ge=0)


@_strict
class ArtifactRef(BaseModel):
    ref: str
    kind: str | None = None


@_strict
class Evidence(BaseModel):
    metric_value: float | None = None
    cost_actual: CostActual | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)


@_strict
class ErrorInfo(BaseModel):
    code: str
    message: str


@_strict
class ExperimentResult(BaseModel):
    experiment_id: str = Field(pattern=_EXP)
    schema_version: str = SCHEMA_VERSION
    status: ResultStatus
    evidence: Evidence = Field(default_factory=Evidence)
    error: ErrorInfo | None = None
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def _coherence(self) -> "ExperimentResult":
        if self.status is ResultStatus.completed and self.evidence.metric_value is None:
            raise ValueError("Law 1: completed result must carry the measured metric_value")
        if self.status is not ResultStatus.completed and self.error is None:
            raise ValueError("non-completed results must include an error explanation")
        return self


# -------------------------------------------------------- ResearchFinding
class FindingKind(str, Enum):
    confirmed = "confirmed"
    refuted = "refuted"
    harmful = "harmful"
    inconclusive = "inconclusive"
    operational = "operational"


@_strict
class Metrics(BaseModel):
    value: float | None = None
    baseline_value: float | None = None
    delta: float | None = None
    cost_units: float | None = None


@_strict
class ResearchFinding(BaseModel):
    finding_id: str = Field(pattern=_FND)
    project_id: str = Field(pattern=_ID)
    experiment_id: str = Field(pattern=_EXP)
    hypothesis_id: str | None = Field(default=None, pattern=_HYP)
    kind: FindingKind
    statement: str = Field(min_length=10, max_length=1000)
    conditions: dict[str, Any] = Field(default_factory=dict)
    metrics: Metrics = Field(default_factory=Metrics)
    confidence: float = Field(ge=0, le=1)
    tags: list[str] = Field(default_factory=list)
    superseded_by: str | None = Field(default=None, pattern=_FND)
    created_at: datetime = Field(default_factory=utcnow)
