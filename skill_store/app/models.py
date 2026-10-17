"""Wire types. The plan is both the shopping cart and the executable program."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Step(BaseModel):
    skill_id: str
    hand: str | None = None
    """The hand the scheduler assigned."""
    planned_hand: str | None = None
    """The hand the compiler planned, if any. Decides which hand episode the step
    belongs to when one hand holds a thing while the other works on it."""
    params: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""


class MissingSkill(BaseModel):
    """A skill the task needs that the catalog does not have. This is demand signal."""
    proposed_id: str
    name: str
    description: str
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    why_needed: str = ""
    insert_after: int = -1
    """Index of the step this belongs after; -1 means before the first step."""
    dataset_id: str = ""
    """An open dataset that covers this motion, if the compiler found one."""
    dataset_name: str = ""
    hand: str | None = None
    """The hand the compiler planned for this motion, if any."""


class PlanObject(BaseModel):
    """A thing the request involves, classified before any skill is chosen."""
    name: str
    kind: str
    size_cm: float | None = None
    """Approximate largest dimension, judged with the whole request in view (a
    toy's parts are toy-sized). None on plans compiled before sizes existed."""


class CompiledPlan(BaseModel):
    """Exactly what the model is constrained to return."""
    summary: str
    combo_name: str = ""
    steps: list[Step]
    missing: list[MissingSkill] = Field(default_factory=list)
    objects: list[PlanObject] = Field(default_factory=list)
    goal: str = ""

    def kinds(self) -> dict[str, str]:
        return {o.name: o.kind for o in self.objects}


class ValidationIssue(BaseModel):
    step_index: int | None
    kind: Literal["unknown_skill", "unmet_precondition", "embodiment_mismatch",
                  "not_executable", "empty_plan", "loose_end",
                  "wrong_object", "wrong_flow", "pointless_move"]
    detail: str


class PricedStep(Step):
    """A step with everything the storefront needs to render a line item."""
    name: str = ""
    title: str = ""
    vendor: str = ""
    category: str = ""
    thumbnail: str = ""
    price_eur: float = 0.0
    """What this line bills: the list price the first time a skill appears, 0 after."""
    list_price_eur: float = 0.0
    repeat_of: int | None = None
    """Index of the step that already bought this skill, when this is a repeat."""
    status: str = "catalog"
    success_rate: float | None = None
    n_trials: int = 0
    executable: bool = False
    hands_required: int = 0
    availability: str = "none"
    """skill_and_data | data_only | none"""
    dataset_name: str = ""
    dataset_id: str = ""
    dataset_count: int = 0
    """How many open datasets cover this skill, the primary one included."""
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)


class PlanResponse(BaseModel):
    plan_id: int
    prompt: str
    robot_model: str
    summary: str
    combo_name: str = ""
    steps: list[PricedStep]
    graph: list[dict[str, Any]] = Field(default_factory=list)
    hands: list[str | None] = Field(default_factory=list)
    depth: int = 0
    max_parallel: int = 1
    missing: list[MissingSkill]
    objects: list[PlanObject] = Field(default_factory=list)
    """The plan's objects, sizes already fitted so nothing put onto or into
    another thing is bigger than it (app/props.py: fit_sizes)."""
    issues: list[ValidationIssue]
    valid: bool
    installable: bool = False
    """valid, no gaps, and every step has a trained checkpoint."""
    install_blockers: list[str] = Field(default_factory=list)
    total_price_eur: float
    executable_steps: int
    cached: bool = False


class RunReport(BaseModel):
    plan_id: int
    step_index: int
    skill_id: str
    robot_model: str
    success: bool
    duration_s: float | None = None
    notes: str = ""
