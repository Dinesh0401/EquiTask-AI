from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import (
    AssignmentState,
    ConsentState,
    KnowledgeState,
    Preference,
    ProposalState,
    Role,
    SolverMode,
    SolverStatus,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth / users ----------

class UserRegister(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=200)
    role: Role
    display_name: str = Field(min_length=1, max_length=120)


class UserLogin(BaseModel):
    email: str
    password: str


class UserOut(ORMModel):
    id: str
    email: str
    role: Role
    display_name: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


# ---------- Domain profiles ----------

class VolunteerCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    timezone: str = "UTC"
    weekly_capacity_hours: float = Field(gt=0, le=80)
    country_code: str | None = Field(default=None, max_length=2)
    contact_permitted: bool = True


class VolunteerUpdate(BaseModel):
    display_name: str | None = None
    timezone: str | None = None
    weekly_capacity_hours: float | None = Field(default=None, gt=0, le=80)
    contact_permitted: bool | None = None


class VolunteerOut(ORMModel):
    id: str
    user_id: str
    display_name: str
    timezone: str
    weekly_capacity_hours: float
    country_code: str | None
    contact_permitted: bool


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    country_code: str | None = Field(default=None, max_length=2)
    evidence_ref: str | None = Field(default=None, max_length=500)


class OrganizationOut(ORMModel):
    id: str
    name: str
    country_code: str | None
    verification_status: str


class SkillFact(BaseModel):
    skill: str = Field(min_length=1, max_length=100)
    proficiency: int = Field(ge=0, le=100)
    state: KnowledgeState = KnowledgeState.UNKNOWN
    observed_at: datetime | None = None
    source: str = "self_report"


class SkillRequirement(BaseModel):
    skill: str = Field(min_length=1, max_length=100)
    min_proficiency: int = Field(ge=0, le=100)
    mandatory: bool = True


class ProjectCreate(BaseModel):
    organization_id: str
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=10_000)


class ProjectOut(ORMModel):
    id: str
    organization_id: str
    name: str
    description: str
    status: str


class TaskCreate(BaseModel):
    project_id: str
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=10_000)
    required_skills: list[SkillRequirement] = Field(default_factory=list)
    effort_hours: float = Field(gt=0, le=168)
    start_utc: datetime
    end_utc: datetime
    deadline_utc: datetime
    dependencies: list[str] = Field(default_factory=list)
    max_assignees: int = Field(default=1, ge=1, le=20)
    value: int = Field(default=100, ge=1, le=1000)
    acceptance_criteria_present: bool = True
    required_languages: list[str] = Field(default_factory=list)
    requires_approval: bool = False
    required: bool = True


class TaskOut(ORMModel):
    id: str
    project_id: str
    name: str
    status: str
    effort_hours: float
    deadline_utc: datetime


class SkillUpdate(BaseModel):
    skills: list[SkillFact]


class AvailabilityCreate(BaseModel):
    start_utc: datetime
    end_utc: datetime
    state: KnowledgeState = KnowledgeState.KNOWN_TRUE


class PreferenceUpdate(BaseModel):
    preferences: dict[str, str] = Field(default_factory=dict)


class SeedRequest(BaseModel):
    volunteers: int = Field(default=20, ge=1, le=200)
    tasks: int = Field(default=6, ge=1, le=200)
    seed: int = 7


# ---------- Allocation problem ----------

class VolunteerInput(BaseModel):
    id: str
    capacity_hours: float = Field(gt=0, le=168)
    committed_hours: float = Field(ge=0, le=168)
    skills: list[SkillFact] = Field(default_factory=list)
    availability_state: KnowledgeState = KnowledgeState.UNKNOWN
    languages: list[str] = Field(default_factory=list)
    preference_by_task: dict[str, Preference] = Field(default_factory=dict)
    consent_by_task: dict[str, ConsentState] = Field(default_factory=dict)
    contact_permitted: bool = True
    history_offers: int = Field(default=0, ge=0)
    history_hours: float = Field(default=0, ge=0)
    newcomer: bool = False
    timezone: str = "UTC"


class TaskInput(BaseModel):
    id: str
    organization_id: str
    required_skills: list[SkillRequirement] = Field(default_factory=list)
    effort_hours: float = Field(gt=0, le=168)
    start_utc: datetime
    end_utc: datetime
    deadline_utc: datetime
    dependencies: list[str] = Field(default_factory=list)
    max_assignees: int = Field(default=1, ge=1, le=20)
    value: int = Field(default=100, ge=1, le=1000)
    acceptance_criteria_present: bool = True
    organization_verified: bool = True
    required_languages: list[str] = Field(default_factory=list)
    requires_approval: bool = False
    required: bool = Field(default=True, description="If True, the task must be fully covered; if False, best-effort partial coverage is acceptable.")

    @model_validator(mode="after")
    def _check_times(self) -> "TaskInput":
        if self.end_utc < self.start_utc:
            raise ValueError("end_utc must not precede start_utc")
        if self.deadline_utc < self.start_utc:
            raise ValueError("deadline_utc must not precede start_utc")
        return self


class LambdaWeights(BaseModel):
    # Weights are applied after internal normalization; see MATHEMATICAL_FORMULATION.md.
    workload_unfairness: float = Field(default=1.0, ge=0, le=100)
    opportunity_unfairness: float = Field(default=1.0, ge=0, le=100)
    disruption: float = Field(default=5.0, ge=0, le=100)
    uncertainty_risk: float = Field(default=1.0, ge=0, le=100)
    coordination_overhead: float = Field(default=1.0, ge=0, le=100)


class AllocationPolicy(BaseModel):
    policy_version: str = "v0.1"
    lambdas: LambdaWeights = Field(default_factory=LambdaWeights)
    max_questions_per_round: int = Field(default=3, ge=0, le=20)
    solver_time_limit_seconds: float = Field(default=5.0, gt=0, le=120)
    stale_field_hours: int = Field(default=24 * 14, ge=1)
    fairness_normalization: int = Field(default=50, ge=1)


class AllocationProblem(BaseModel):
    volunteers: list[VolunteerInput]
    tasks: list[TaskInput]
    mode: SolverMode = SolverMode.FAIRNESS_AWARE
    policy: AllocationPolicy = Field(default_factory=AllocationPolicy)
    completed_task_ids: list[str] = Field(default_factory=list)
    locked_assignments: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_problem(self) -> "AllocationProblem":
        if len(self.volunteers) > 200 or len(self.tasks) > 200:
            raise ValueError("problem exceeds MVP caps of 200 volunteers and 200 tasks")
        vids = [v.id for v in self.volunteers]
        tids = [t.id for t in self.tasks]
        if len(vids) != len(set(vids)):
            raise ValueError("duplicate volunteer id")
        if len(tids) != len(set(tids)):
            raise ValueError("duplicate task id")
        task_ids = set(tids)
        for t in self.tasks:
            for dep in t.dependencies:
                if dep not in task_ids and dep not in self.completed_task_ids:
                    raise ValueError(f"task {t.id} references unknown dependency {dep}")
        return self


class ClarificationQuestion(BaseModel):
    volunteer_id: str
    field: str
    task_id: str | None = None
    reason: str
    burden: int = Field(ge=1, le=5)
    expected_value: float = Field(ge=0)


class ProposalOut(BaseModel):
    volunteer_id: str
    task_id: str
    fit_score: int
    risk_score: float
    reasons: list[str]


class AllocationMetrics(BaseModel):
    assigned_tasks: int
    candidates: int
    workload_unfairness: int
    opportunity_unfairness: int
    expected_contribution: int
    uncertainty_risk: int
    coordination_overhead: int
    objective_value: float | None
    optimality_gap: float | None
    solver_runtime_ms: float


class AllocationResult(BaseModel):
    status: SolverStatus
    proposals: list[ProposalOut] = Field(default_factory=list)
    questions: list[ClarificationQuestion] = Field(default_factory=list)
    metrics: AllocationMetrics | None = None
    reason_codes: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
    policy_version: str
    solver_version: str
    solver_status_raw: str | None = None


class AllocationRunRequest(BaseModel):
    project_id: str | None = None
    problem: AllocationProblem | None = None

    @model_validator(mode="after")
    def _one_of(self) -> "AllocationRunRequest":
        if not self.project_id and not self.problem:
            raise ValueError("provide project_id or problem")
        return self


class ConsentRequest(BaseModel):
    action: str = Field(pattern="^(accept|decline)$")
    reason: str | None = Field(default=None, max_length=500)


class DisruptionEventRequest(BaseModel):
    event_type: str = Field(pattern="^(WITHDRAWAL|DEADLINE_CHANGE|NEW_TASK)$")
    assignment_id: str | None = None
    task_id: str | None = None
    occurred_at: datetime
    note: str | None = Field(default=None, max_length=1000)


class AssignmentOut(ORMModel):
    id: str
    proposal_id: str
    state: AssignmentState
    version: int


class ProposalOutDb(ORMModel):
    id: str
    task_id: str
    volunteer_id: str
    state: ProposalState
    created_at: datetime
