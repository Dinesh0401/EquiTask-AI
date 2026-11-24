from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("usr"))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(500))
    role: Mapped[str] = mapped_column(String(32), index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Volunteer(Base):
    __tablename__ = "volunteers"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("vol"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    weekly_capacity_hours: Mapped[float] = mapped_column(Float, default=10.0)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    contact_permitted: Mapped[bool] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Skill(Base):
    __tablename__ = "skills"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("skl"))
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)


class VolunteerSkill(Base):
    __tablename__ = "volunteer_skills"
    __table_args__ = (UniqueConstraint("volunteer_id", "skill_id", name="uq_volunteer_skill"),)
    volunteer_id: Mapped[str] = mapped_column(ForeignKey("volunteers.id"), primary_key=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"), primary_key=True)
    proficiency: Mapped[int] = mapped_column(Integer, default=0)
    epistemic_state: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="self_report")


class AvailabilityWindow(Base):
    __tablename__ = "availability_windows"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("avl"))
    volunteer_id: Mapped[str] = mapped_column(ForeignKey("volunteers.id"), index=True)
    start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    epistemic_state: Mapped[str] = mapped_column(String(32), default="KNOWN_TRUE")


class Preference(Base):
    __tablename__ = "preferences"
    volunteer_id: Mapped[str] = mapped_column(ForeignKey("volunteers.id"), primary_key=True)
    task_type: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(String(64))
    epistemic_state: Mapped[str] = mapped_column(String(32), default="KNOWN_TRUE")


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("org"))
    name: Mapped[str] = mapped_column(String(200))
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    verification_evidence_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OrgMembership(Base):
    __tablename__ = "org_memberships"
    __table_args__ = (UniqueConstraint("user_id", "organization_id", name="uq_org_membership"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("mem"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="COORDINATOR")


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("prj"))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("tsk"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    effort_hours: Mapped[float] = mapped_column(Float)
    start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deadline_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    dependencies_json: Mapped[list] = mapped_column(JSON, default=list)
    max_assignees: Mapped[int] = mapped_column(Integer, default=1)
    value: Mapped[int] = mapped_column(Integer, default=100)
    acceptance_criteria_present: Mapped[bool] = mapped_column(Integer, default=1)
    required_languages_json: Mapped[list] = mapped_column(JSON, default=list)
    requires_approval: Mapped[bool] = mapped_column(Integer, default=0)


class TaskSkill(Base):
    __tablename__ = "task_skills"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), primary_key=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"), primary_key=True)
    min_proficiency: Mapped[int] = mapped_column(Integer, default=0)
    mandatory: Mapped[bool] = mapped_column(Integer, default=1)


class AllocationRun(Base):
    __tablename__ = "allocation_runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("run"))
    project_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    policy_version: Mapped[str] = mapped_column(String(32))
    solver_version: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(64), index=True)
    objective: Mapped[float | None] = mapped_column(Float, nullable=True)
    runtime_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason_codes_json: Mapped[list] = mapped_column(JSON, default=list)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConstraintEvaluation(Base):
    __tablename__ = "constraint_evaluations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("cev"))
    run_id: Mapped[str] = mapped_column(ForeignKey("allocation_runs.id"), index=True)
    subject_type: Mapped[str] = mapped_column(String(32))
    subject_id: Mapped[str] = mapped_column(String(64))
    reason_code: Mapped[str] = mapped_column(String(64))
    passed: Mapped[bool] = mapped_column(Integer)


class AllocationProposal(Base):
    __tablename__ = "allocation_proposals"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("pro"))
    run_id: Mapped[str] = mapped_column(ForeignKey("allocation_runs.id"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    volunteer_id: Mapped[str] = mapped_column(ForeignKey("volunteers.id"), index=True)
    state: Mapped[str] = mapped_column(String(32), default="OFFERED", index=True)
    fit_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConsentEvent(Base):
    __tablename__ = "consent_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("con"))
    proposal_id: Mapped[str] = mapped_column(ForeignKey("allocation_proposals.id"), index=True)
    action: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Assignment(Base):
    __tablename__ = "assignments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("asg"))
    proposal_id: Mapped[str] = mapped_column(ForeignKey("allocation_proposals.id"), unique=True, index=True)
    state: Mapped[str] = mapped_column(String(32), default="PENDING_APPROVAL", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    started_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowEvent(Base):
    __tablename__ = "workflow_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("wfe"))
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    aggregate_id: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("msg"))
    sender_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    recipient_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    proposal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Deliverable(Base):
    __tablename__ = "deliverables"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("del"))
    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id"), index=True)
    object_key: Mapped[str] = mapped_column(String(500))
    checksum: Mapped[str] = mapped_column(String(128))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("rev"))
    deliverable_id: Mapped[str] = mapped_column(ForeignKey("deliverables.id"), index=True)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(32))
    feedback: Mapped[str] = mapped_column(Text, default="")


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("agn"))
    agent_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32))
    input_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    output_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    policy_version: Mapped[str] = mapped_column(String(32), default="v0.1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("aud"))
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    target_type: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_version: Mapped[str] = mapped_column(String(32), default="v0.1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ResearchExperiment(Base):
    __tablename__ = "research_experiments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("exp"))
    name: Mapped[str] = mapped_column(String(200))
    seed: Mapped[int] = mapped_column(Integer)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
