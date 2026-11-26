from __future__ import annotations

import random
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .allocation import allocate, build_repair_plan
from .allocation.policy import version_metadata
from .health import overall_health
from .auth import create_token, current_user, hash_password, require_roles, verify_password
from .config import get_settings
from .db import get_db
from .domain.state_machine import InvalidTransition, transition_assignment, transition_proposal
from .enums import (
    AssignmentState,
    KnowledgeState,
    OrganizationVerification,
    Preference,
    ProposalState,
    Role,
    SolverMode,
    SolverStatus,
)
from .models import (
    AllocationProposal,
    AllocationRun,
    Assignment,
    AuditLog,
    AvailabilityWindow,
    ConsentEvent,
    Deliverable,
    Message,
    OrgMembership,
    Organization,
    Preference as PreferenceRow,
    Project,
    Skill,
    Task,
    TaskSkill,
    User,
    Volunteer,
    VolunteerSkill,
    WorkflowEvent,
    new_id,
    utcnow,
)
from .schemas import (
    AllocationMetrics,
    AllocationPolicy,
    AllocationProblem,
    AllocationResult,
    AllocationRunRequest,
    AssignmentOut,
    AvailabilityCreate,
    ConsentRequest,
    DisruptionEventRequest,
    OrganizationCreate,
    OrganizationOut,
    PreferenceUpdate,
    ProjectCreate,
    ProjectOut,
    ProposalOutDb,
    SeedRequest,
    SkillFact,
    SkillUpdate,
    TaskCreate,
    TaskInput,
    TaskOut,
    TokenOut,
    UserLogin,
    UserOut,
    UserRegister,
    VolunteerCreate,
    VolunteerInput,
    VolunteerOut,
    VolunteerUpdate,
)

router = APIRouter(prefix="/api/v1")


def _audit(
    db: Session,
    actor_id: str | None,
    action: str,
    target_type: str,
    target_id: str,
    reason: str | None = None,
) -> None:
    policy_version, _ = version_metadata()
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            policy_version=policy_version,
        )
    )


def _get_or_create_skill(db: Session, name: str) -> Skill:
    skill = db.scalar(select(Skill).where(Skill.name == name))
    if skill is None:
        skill = Skill(id=new_id("skl"), name=name)
        db.add(skill)
        db.flush()
    return skill


def _active_assignment_states() -> set[str]:
    return {"PENDING_APPROVAL", "ACTIVE", "SUBMITTED", "UNDER_REVIEW", "DISPUTED"}


def _build_problem_from_project(
    db: Session,
    project_id: str,
    mode: SolverMode = SolverMode.FAIRNESS_AWARE,
    policy: AllocationPolicy | None = None,
) -> AllocationProblem:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    organization = db.get(Organization, project.organization_id)
    if organization is None:
        raise HTTPException(404, "Organization not found")
    tasks_db = list(db.scalars(select(Task).where(Task.project_id == project_id)).all())
    task_inputs: list[TaskInput] = []
    for task in tasks_db:
        skill_rows = list(db.scalars(select(TaskSkill).where(TaskSkill.task_id == task.id)).all())
        requirements = []
        for row in skill_rows:
            skill = db.get(Skill, row.skill_id)
            if skill:
                requirements.append(
                    {
                        "skill": skill.name,
                        "min_proficiency": row.min_proficiency,
                        "mandatory": bool(row.mandatory),
                    }
                )
        task_inputs.append(
            TaskInput(
                id=task.id,
                organization_id=project.organization_id,
                required_skills=requirements,
                effort_hours=task.effort_hours,
                start_utc=task.start_utc,
                end_utc=task.end_utc,
                deadline_utc=task.deadline_utc,
                dependencies=list(task.dependencies_json or []),
                max_assignees=task.max_assignees,
                value=task.value,
                acceptance_criteria_present=bool(task.acceptance_criteria_present),
                organization_verified=organization.verification_status == OrganizationVerification.VERIFIED.value,
                required_languages=list(task.required_languages_json or []),
                requires_approval=bool(task.requires_approval),
                required=bool(task.required),
            )
        )

    task_ids = {t.id for t in tasks_db}
    volunteers_db = list(db.scalars(select(Volunteer)).all())
    volunteer_inputs: list[VolunteerInput] = []
    locked: list[dict] = []
    for volunteer in volunteers_db:
        skill_rows = list(db.scalars(select(VolunteerSkill).where(VolunteerSkill.volunteer_id == volunteer.id)).all())
        skills: list[SkillFact] = []
        for row in skill_rows:
            skill = db.get(Skill, row.skill_id)
            if skill:
                skills.append(
                    SkillFact(
                        skill=skill.name,
                        proficiency=row.proficiency,
                        state=KnowledgeState(row.epistemic_state),
                        observed_at=row.observed_at,
                        source=row.source,
                    )
                )
        availability_rows = list(
            db.scalars(select(AvailabilityWindow).where(AvailabilityWindow.volunteer_id == volunteer.id)).all()
        )
        if any(row.epistemic_state == KnowledgeState.KNOWN_TRUE.value for row in availability_rows):
            availability_state = KnowledgeState.KNOWN_TRUE
        elif any(row.epistemic_state == KnowledgeState.STALE.value for row in availability_rows):
            availability_state = KnowledgeState.STALE
        else:
            availability_state = KnowledgeState.UNKNOWN

        pref_rows = list(db.scalars(select(PreferenceRow).where(PreferenceRow.volunteer_id == volunteer.id)).all())
        languages: list[str] = []
        preferences: dict[str, Preference] = {}
        for row in pref_rows:
            if row.task_type.startswith("language:"):
                languages.append(row.task_type.split(":", 1)[1])
            elif row.task_type.startswith("task:"):
                try:
                    preferences[row.task_type[5:]] = Preference(row.value)
                except ValueError:
                    continue

        consent_by_task: dict[str, object] = {}
        proposals = list(
            db.scalars(
                select(AllocationProposal).where(
                    AllocationProposal.volunteer_id
                    == volunteer.id
                )
            ).all()
        )
        for proposal in proposals:
            if proposal.task_id not in task_ids:
                continue
            if proposal.state == ProposalState.DECLINED.value:
                consent_by_task[proposal.task_id] = "DECLINED"
            elif proposal.state in (ProposalState.ACCEPTED.value, ProposalState.PENDING_APPROVAL.value):
                consent_by_task[proposal.task_id] = "ACCEPTED"

        assignments = list(
            db.scalars(
                select(Assignment, AllocationProposal)
                .join(
                    AllocationProposal,
                    Assignment.proposal_id == AllocationProposal.id,
                )
                .where(
                    AllocationProposal.volunteer_id == volunteer.id,
                    Assignment.state.in_(_active_assignment_states()),
                )
            ).all()
        )
        committed = 0.0
        for assignment, _proposal in assignments:
            task = db.get(Task, _proposal.task_id)
            if task:
                committed += task.effort_hours
                locked.append(
                    {
                        "volunteer_id": volunteer.id,
                        "task_id": task.id,
                        "effort_hours": task.effort_hours,
                        "change_permitted": False,
                        "reconfirmation_recorded": False,
                    }
                )

        volunteer_inputs.append(
            VolunteerInput(
                id=volunteer.id,
                capacity_hours=volunteer.weekly_capacity_hours,
                committed_hours=committed,
                skills=skills,
                availability_state=availability_state,
                languages=languages,
                preference_by_task=preferences,
                consent_by_task=consent_by_task,  # type: ignore[arg-type]
                contact_permitted=bool(volunteer.contact_permitted),
                history_offers=len(proposals),
                history_hours=committed,
                newcomer=len(proposals) < 2,
                timezone=volunteer.timezone,
            )
        )

    return AllocationProblem(
        volunteers=volunteer_inputs,
        tasks=task_inputs,
        mode=mode,
        policy=policy or AllocationPolicy(),
    )


def _persist_result(db: Session, result: AllocationResult, project_id: str | None) -> str:
    run_id = new_id("run")
    db.add(
        AllocationRun(
            id=run_id,
            project_id=project_id,
            policy_version=result.policy_version,
            solver_version=result.solver_version,
            status=result.status.value,
            objective=result.metrics.objective_value if result.metrics else None,
            runtime_ms=result.metrics.solver_runtime_ms if result.metrics else None,
            reason_codes_json=result.reason_codes,
            result_json=result.model_dump(mode="json"),
        )
    )
    for proposal in result.proposals:
        db.add(
            AllocationProposal(
                id=new_id("pro"),
                run_id=run_id,
                task_id=proposal.task_id,
                volunteer_id=proposal.volunteer_id,
                state=ProposalState.OFFERED.value,
                fit_score=proposal.fit_score,
                risk_score=proposal.risk_score,
            )
        )
    db.flush()
    return run_id


@router.get("/health")
def health(db=Depends(get_db)) -> dict:  # type: ignore[valid-type]
    return overall_health(db)


_SELF_REGISTERABLE_ROLES = {Role.VOLUNTEER.value, Role.ORGANIZATION.value}


@router.post("/auth/register", response_model=UserOut)
def register(payload: UserRegister, db: Session = Depends(get_db)) -> User:
    if payload.role.value not in _SELF_REGISTERABLE_ROLES:
        raise HTTPException(
            403,
            f"Self-registration is limited to {', '.join(sorted(_SELF_REGISTERABLE_ROLES))}; "
            "ADMIN and COORDINATOR accounts must be created by an existing administrator.",
        )
    if db.scalar(select(User).where(User.email == payload.email.casefold())):
        raise HTTPException(409, "Email already registered")
    user = User(
        id=new_id("usr"),
        email=payload.email.casefold(),
        password_hash=hash_password(payload.password),
        role=payload.role.value,
        display_name=payload.display_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _audit(db, user.id, "USER_REGISTERED", "user", user.id)
    db.commit()
    return user


@router.post("/auth/login", response_model=TokenOut)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(User).where(User.email == payload.email.casefold()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    token, expires = create_token(user)
    return TokenOut(access_token=token, expires_at=expires)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user


@router.post("/volunteers", response_model=VolunteerOut)
def create_volunteer(
    payload: VolunteerCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VOLUNTEER, Role.ADMIN)),
) -> Volunteer:
    existing = db.scalar(select(Volunteer).where(Volunteer.user_id == user.id))
    if existing:
        raise HTTPException(409, "Volunteer profile already exists")
    volunteer = Volunteer(
        id=new_id("vol"),
        user_id=user.id,
        display_name=payload.display_name,
        timezone=payload.timezone,
        weekly_capacity_hours=payload.weekly_capacity_hours,
        country_code=payload.country_code,
        contact_permitted=int(payload.contact_permitted),
    )
    db.add(volunteer)
    db.commit()
    db.refresh(volunteer)
    _audit(db, user.id, "VOLUNTEER_CREATED", "volunteer", volunteer.id)
    db.commit()
    return volunteer


@router.get("/volunteers/me", response_model=VolunteerOut)
def get_my_volunteer(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VOLUNTEER, Role.ADMIN)),
) -> Volunteer:
    volunteer = db.scalar(select(Volunteer).where(Volunteer.user_id == user.id))
    if volunteer is None:
        raise HTTPException(404, "Volunteer profile not found")
    return volunteer


@router.patch("/volunteers/me", response_model=VolunteerOut)
def update_my_volunteer(
    payload: VolunteerUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VOLUNTEER, Role.ADMIN)),
) -> Volunteer:
    volunteer = db.scalar(select(Volunteer).where(Volunteer.user_id == user.id))
    if volunteer is None:
        raise HTTPException(404, "Volunteer profile not found")
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(volunteer, key, int(value) if key == "contact_permitted" and value is not None else value)
    db.commit()
    db.refresh(volunteer)
    _audit(db, user.id, "VOLUNTEER_UPDATED", "volunteer", volunteer.id)
    db.commit()
    return volunteer


@router.post("/volunteers/me/skills")
def update_skills(
    payload: SkillUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VOLUNTEER, Role.ADMIN)),
) -> dict:
    volunteer = db.scalar(select(Volunteer).where(Volunteer.user_id == user.id))
    if volunteer is None:
        raise HTTPException(404, "Volunteer profile not found")
    db.query(VolunteerSkill).filter(VolunteerSkill.volunteer_id == volunteer.id).delete()
    for fact in payload.skills:
        skill = _get_or_create_skill(db, fact.skill)
        db.add(
            VolunteerSkill(
                volunteer_id=volunteer.id,
                skill_id=skill.id,
                proficiency=fact.proficiency,
                epistemic_state=fact.state.value,
                observed_at=fact.observed_at,
                source=fact.source,
            )
        )
    db.commit()
    _audit(db, user.id, "SKILLS_UPDATED", "volunteer", volunteer.id)
    db.commit()
    return {"status": "updated", "count": len(payload.skills)}


@router.post("/volunteers/me/availability")
def add_availability(
    payload: AvailabilityCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VOLUNTEER, Role.ADMIN)),
) -> dict:
    volunteer = db.scalar(select(Volunteer).where(Volunteer.user_id == user.id))
    if volunteer is None:
        raise HTTPException(404, "Volunteer profile not found")
    if payload.end_utc < payload.start_utc:
        raise HTTPException(422, "end_utc must not precede start_utc")
    db.add(
        AvailabilityWindow(
            id=new_id("avl"),
            volunteer_id=volunteer.id,
            start_utc=payload.start_utc,
            end_utc=payload.end_utc,
            epistemic_state=payload.state.value,
        )
    )
    db.commit()
    _audit(db, user.id, "AVAILABILITY_ADDED", "volunteer", volunteer.id)
    db.commit()
    return {"status": "added"}


@router.post("/volunteers/me/preferences")
def update_preferences(
    payload: PreferenceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VOLUNTEER, Role.ADMIN)),
) -> dict:
    volunteer = db.scalar(select(Volunteer).where(Volunteer.user_id == user.id))
    if volunteer is None:
        raise HTTPException(404, "Volunteer profile not found")
    for key, value in payload.preferences.items():
        row = db.get(PreferenceRow, (volunteer.id, key))
        if row is None:
            row = PreferenceRow(volunteer_id=volunteer.id, task_type=key, value=value)
            db.add(row)
        else:
            row.value = value
    db.commit()
    _audit(db, user.id, "PREFERENCES_UPDATED", "volunteer", volunteer.id)
    db.commit()
    return {"status": "updated", "count": len(payload.preferences)}


@router.post("/organizations", response_model=OrganizationOut)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.ORGANIZATION, Role.COORDINATOR, Role.ADMIN)),
) -> Organization:
    org = Organization(
        id=new_id("org"),
        name=payload.name,
        country_code=payload.country_code,
        verification_evidence_ref=payload.evidence_ref,
        verification_status=OrganizationVerification.PENDING.value,
    )
    db.add(org)
    db.flush()
    db.add(OrgMembership(id=new_id("mem"), user_id=user.id, organization_id=org.id, role="COORDINATOR"))
    db.commit()
    db.refresh(org)
    _audit(db, user.id, "ORGANIZATION_CREATED", "organization", org.id, "Pending verification")
    db.commit()
    return org


@router.post("/admin/organizations/{organization_id}/verify", response_model=OrganizationOut)
def verify_organization(
    organization_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.ADMIN)),
) -> Organization:
    org = db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(404, "Organization not found")
    org.verification_status = OrganizationVerification.VERIFIED.value
    db.commit()
    db.refresh(org)
    _audit(db, user.id, "ORGANIZATION_VERIFIED", "organization", org.id, "Admin verification")
    db.commit()
    return org


@router.post("/projects", response_model=ProjectOut)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.ORGANIZATION, Role.COORDINATOR, Role.ADMIN)),
) -> Project:
    org = db.get(Organization, payload.organization_id)
    if org is None:
        raise HTTPException(404, "Organization not found")
    membership = db.scalar(
        select(OrgMembership).where(
            OrgMembership.organization_id == org.id,
            OrgMembership.user_id == user.id,
        )
    )
    if membership is None and user.role != Role.ADMIN.value:
        raise HTTPException(403, "Not a member of this organization")
    if org.verification_status != OrganizationVerification.VERIFIED.value:
        raise HTTPException(403, "Organization must be verified before creating projects")
    project = Project(
        id=new_id("prj"),
        organization_id=org.id,
        name=payload.name,
        description=payload.description,
        status="ACTIVE",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    _audit(db, user.id, "PROJECT_CREATED", "project", project.id)
    db.commit()
    return project


@router.post("/tasks", response_model=TaskOut)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.ORGANIZATION, Role.COORDINATOR, Role.ADMIN)),
) -> Task:
    project = db.get(Project, payload.project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    org = db.get(Organization, project.organization_id)
    if org is None or org.verification_status != OrganizationVerification.VERIFIED.value:
        raise HTTPException(403, "Organization must be verified")
    if user.role != Role.ADMIN.value:
        membership = db.scalar(
            select(OrgMembership).where(
                OrgMembership.organization_id == org.id,
                OrgMembership.user_id == user.id,
            )
        )
        if membership is None:
            raise HTTPException(403, "Not a member of this organization")
    task = Task(
        id=new_id("tsk"),
        project_id=project.id,
        name=payload.name,
        description=payload.description,
        status="DRAFT",
        effort_hours=payload.effort_hours,
        start_utc=payload.start_utc,
        end_utc=payload.end_utc,
        deadline_utc=payload.deadline_utc,
        dependencies_json=payload.dependencies,
        max_assignees=payload.max_assignees,
        value=payload.value,
        acceptance_criteria_present=int(payload.acceptance_criteria_present),
        required_languages_json=payload.required_languages,
        requires_approval=int(payload.requires_approval),
        required=bool(payload.required),
    )
    db.add(task)
    db.flush()
    for requirement in payload.required_skills:
        skill = _get_or_create_skill(db, requirement.skill)
        db.add(
            TaskSkill(
                task_id=task.id,
                skill_id=skill.id,
                min_proficiency=requirement.min_proficiency,
                mandatory=int(requirement.mandatory),
            )
        )
    db.commit()
    db.refresh(task)
    _audit(db, user.id, "TASK_CREATED_DRAFT", "task", task.id, "Requires validation before publication")
    db.commit()
    return task


def _check_org_membership(db: Session, user: User, organization_id: str) -> None:
    if user.role == Role.ADMIN.value:
        return
    membership = db.scalar(
        select(OrgMembership).where(
            OrgMembership.organization_id == organization_id,
            OrgMembership.user_id == user.id,
        )
    )
    if membership is None:
        raise HTTPException(403, f"Not a member of organization {organization_id}")


@router.post("/allocations/run", response_model=AllocationResult)
def run_allocation(
    payload: AllocationRunRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.COORDINATOR, Role.ORGANIZATION, Role.ADMIN)),
) -> AllocationResult:
    project_id = payload.project_id
    if payload.problem is not None:
        problem = payload.problem
        # Authorize against every organization referenced in the raw problem.
        org_ids = {t.organization_id for t in problem.tasks}
        for org_id in org_ids:
            org = db.get(Organization, org_id)
            if org is None:
                raise HTTPException(404, f"Organization {org_id} not found")
            if org.verification_status != OrganizationVerification.VERIFIED.value:
                raise HTTPException(403, f"Organization {org_id} is not verified")
            _check_org_membership(db, user, org_id)
    else:
        if project_id is None:
            raise HTTPException(400, "provide project_id or problem")
        problem = _build_problem_from_project(db, project_id)
        project = db.get(Project, project_id)
        if project is None:
            raise HTTPException(404, "Project not found")
        _check_org_membership(db, user, project.organization_id)
    result = allocate(problem)
    run_id = _persist_result(db, result, project_id)
    _audit(db, user.id, "ALLOCATION_RUN", "allocation_run", run_id, result.status.value)
    db.commit()
    return result


@router.get("/proposals", response_model=list[ProposalOutDb])
def list_my_proposals(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VOLUNTEER, Role.ADMIN)),
) -> list[object]:
    volunteer = db.scalar(select(Volunteer).where(Volunteer.user_id == user.id))
    if volunteer is None and user.role != Role.ADMIN.value:
        raise HTTPException(404, "Volunteer profile not found")
    query = select(AllocationProposal)
    if volunteer is not None:
        query = query.where(AllocationProposal.volunteer_id == volunteer.id)
    return list(db.scalars(query.order_by(AllocationProposal.created_at.desc()).limit(100)).all())


@router.get("/projects/{project_id}/proposals", response_model=list[ProposalOutDb])
def list_project_proposals(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.COORDINATOR, Role.ORGANIZATION, Role.ADMIN)),
) -> list[object]:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    if user.role != Role.ADMIN.value:
        membership = db.scalar(
            select(OrgMembership).where(
                OrgMembership.organization_id == project.organization_id,
                OrgMembership.user_id == user.id,
            )
        )
        if membership is None:
            raise HTTPException(403, "Not a member of this organization")
    rows = list(
        db.scalars(
            select(AllocationProposal)
            .join(Task, AllocationProposal.task_id == Task.id)
            .where(Task.project_id == project_id)
            .order_by(AllocationProposal.created_at.desc())
            .limit(200)
        ).all()
    )
    return rows


@router.get("/proposals/{proposal_id}", response_model=ProposalOutDb)
def get_proposal(
    proposal_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> object:
    from .models import AllocationProposal

    proposal = db.get(AllocationProposal, proposal_id)
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    volunteer = db.scalar(select(Volunteer).where(Volunteer.id == proposal.volunteer_id))
    if user.role == Role.ADMIN.value:
        return proposal
    if volunteer is None:
        raise HTTPException(403, "Not permitted to view this proposal")
    if volunteer.user_id == user.id:
        return proposal
    if user.role == Role.COORDINATOR.value:
        task = db.get(Task, proposal.task_id)
        if task is None:
            raise HTTPException(404, "Task not found")
        project = db.get(Project, task.project_id)
        org = db.get(Organization, project.organization_id) if project else None
        if org is None:
            raise HTTPException(404, "Organization not found")
        membership = db.scalar(
            select(OrgMembership).where(
                OrgMembership.organization_id == org.id,
                OrgMembership.user_id == user.id,
            )
        )
        if membership is None:
            raise HTTPException(403, "Not a member of this organization")
        return proposal
    raise HTTPException(403, "Not permitted to view this proposal")


AssignmentState_PENDING = "PENDING_APPROVAL"


@router.post("/proposals/{proposal_id}/respond")
def respond_to_proposal(
    proposal_id: str,
    payload: ConsentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VOLUNTEER, Role.ADMIN)),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=4, max_length=128),
) -> dict:
    from .models import AllocationProposal, AllocationRun

    existing = db.scalar(select(ConsentEvent).where(ConsentEvent.idempotency_key == idempotency_key))
    if existing:
        if str(existing.proposal_id) != proposal_id:
            raise HTTPException(409, f"Idempotency key already used for a different proposal ({existing.proposal_id})")
        if str(existing.actor_id) != str(user.id):
            raise HTTPException(409, f"Idempotency key already used by a different actor ({existing.actor_id})")
        if existing.action != payload.action:
            raise HTTPException(409, f"Idempotency key already used for a different action ({existing.action})")
        assignment = db.scalar(select(Assignment).where(Assignment.proposal_id == proposal_id))
        return {
            "status": "already_processed",
            "action": existing.action,
            "proposal_id": proposal_id,
            "assignment_id": assignment.id if assignment else None,
        }

    proposal = db.scalar(
        select(AllocationProposal).where(AllocationProposal.id == proposal_id).with_for_update()
    )
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    volunteer = db.scalar(
        select(Volunteer).where(Volunteer.id == proposal.volunteer_id).with_for_update()
    )
    if volunteer is None or (volunteer.user_id != user.id and user.role != Role.ADMIN.value):
        raise HTTPException(403, "Only the invited volunteer may respond")

    try:
        if payload.action == "accept":
            # Record the idempotency key before revalidation so that even a
            # failed accept is idempotent: replays return "already_processed"
            # instead of a confusing 409 on an already-expired proposal.
            db.add(
                ConsentEvent(
                    id=new_id("con"),
                    proposal_id=proposal.id,
                    action=payload.action,
                    actor_id=user.id,
                    reason=payload.reason,
                    idempotency_key=idempotency_key,
                    occurred_at=utcnow(),
                )
            )
            db.flush()

            transition_proposal(ProposalState(proposal.state), ProposalState.ACCEPTED)
            # Revalidate hard constraints at decision time.
            task = db.get(Task, proposal.task_id)
            project = db.get(Project, task.project_id) if task else None
            org = db.get(Organization, project.organization_id) if project else None
            if task is None or org is None:
                proposal.state = ProposalState.EXPIRED.value
                db.commit()
                raise HTTPException(409, "Task or organization no longer exists")
            if org.verification_status != OrganizationVerification.VERIFIED.value or not task.acceptance_criteria_present:
                proposal.state = ProposalState.EXPIRED.value
                db.commit()
                raise HTTPException(409, "Task is no longer publishable")
            availability_rows = list(
                db.scalars(select(AvailabilityWindow).where(AvailabilityWindow.volunteer_id == volunteer.id)).all()
            )
            if not any(row.epistemic_state == KnowledgeState.KNOWN_TRUE.value for row in availability_rows):
                proposal.state = ProposalState.EXPIRED.value
                db.commit()
                raise HTTPException(409, "Availability is not confirmed as known true")
            active_total = 0.0
            assignments = list(
                db.scalars(
                    select(Assignment, AllocationProposal)
                    .join(AllocationProposal, Assignment.proposal_id == AllocationProposal.id)
                    .where(
                        AllocationProposal.volunteer_id == volunteer.id,
                        Assignment.state.in_(_active_assignment_states()),
                    )
                    .with_for_update()
                ).all()
            )
            for assignment, other_proposal in assignments:
                other_task = db.get(Task, other_proposal.task_id)
                if other_task:
                    active_total += other_task.effort_hours
            if active_total + task.effort_hours > volunteer.weekly_capacity_hours:
                proposal.state = ProposalState.EXPIRED.value
                db.commit()
                raise HTTPException(409, "Acceptance would exceed agreed capacity")

            # Full revalidation of mandatory requirements before activation.
            skill_rows = list(db.scalars(select(TaskSkill).where(TaskSkill.task_id == task.id)).all())
            for row in skill_rows:
                skill = db.get(Skill, row.skill_id)
                if skill is None:
                    continue
                vs = list(
                    db.scalars(
                        select(VolunteerSkill).where(
                            VolunteerSkill.volunteer_id == volunteer.id,
                            VolunteerSkill.skill_id == skill.id,
                        )
                    )
                )
                if not vs:
                    proposal.state = ProposalState.EXPIRED.value
                    db.commit()
                    raise HTTPException(
                        409,
                        f"Volunteer does not report skill {skill.name} required by task {task.id}",
                    )
                vs_row = vs[0]
                if bool(row.mandatory):
                    # UNKNOWN or STALE mandatory skills cannot confirm eligibility.
                    # Only KNOWN_TRUE with sufficient proficiency is accepted.
                    if vs_row.epistemic_state != KnowledgeState.KNOWN_TRUE.value:
                        proposal.state = ProposalState.EXPIRED.value
                        db.commit()
                        raise HTTPException(
                            409,
                            f"Mandatory skill {skill.name} is {vs_row.epistemic_state}; "
                            "eligibility must be confirmed before acceptance.",
                        )
                    if vs_row.proficiency < row.min_proficiency:
                        proposal.state = ProposalState.EXPIRED.value
                        db.commit()
                        raise HTTPException(
                            409,
                            f"Skill {skill.name} proficiency {vs_row.proficiency} below required {row.min_proficiency}",
                        )

            # Required languages must be known.
            if task.required_languages_json:
                volunteer_languages: set[str] = set()
                pref_rows = list(
                    db.scalars(select(PreferenceRow).where(PreferenceRow.volunteer_id == volunteer.id)).all()
                )
                for row in pref_rows:
                    if row.task_type.startswith("language:"):
                        volunteer_languages.add(row.task_type.split(":", 1)[1])
                missing_languages = [
                    lang for lang in task.required_languages_json if lang not in volunteer_languages
                ]
                if missing_languages:
                    proposal.state = ProposalState.EXPIRED.value
                    db.commit()
                    raise HTTPException(
                        409,
                        f"Volunteer lacks required language(s): {', '.join(missing_languages)}",
                    )

            # Time-window compatibility: deadline must not precede window end.
            if task.deadline_utc < task.end_utc:
                proposal.state = ProposalState.EXPIRED.value
                db.commit()
                raise HTTPException(409, "Task deadline precedes its work window end")

            # No overlapping active assignments for the same volunteer.
            overlapping = list(
                db.scalars(
                    select(Assignment, AllocationProposal, Task)
                    .join(AllocationProposal, Assignment.proposal_id == AllocationProposal.id)
                    .join(Task, AllocationProposal.task_id == Task.id)
                    .where(
                        AllocationProposal.volunteer_id == volunteer.id,
                        Assignment.state.in_(_active_assignment_states()),
                        AllocationProposal.id != proposal.id,
                    )
                ).all()
            )
            for other_assignment, other_proposal, other_task in overlapping:
                if (
                    task.start_utc < other_task.end_utc
                    and other_task.start_utc < task.end_utc
                ):
                    proposal.state = ProposalState.EXPIRED.value
                    db.commit()
                    raise HTTPException(
                        409,
                        f"Task {task.id} overlaps with existing assignment to task {other_task.id}",
                    )

            proposal.state = ProposalState.ACCEPTED.value
            assignment = Assignment(
                id=new_id("asg"),
                proposal_id=proposal.id,
                state=(
                    AssignmentState_PENDING if task.requires_approval else "ACTIVE"
                ),
                started_utc=utcnow(),
            )
            db.add(assignment)
            db.flush()
            assignment_id = assignment.id
        else:
            transition_proposal(ProposalState(proposal.state), ProposalState.DECLINED)
            proposal.state = ProposalState.DECLINED.value
            assignment_id = None
            db.add(
                ConsentEvent(
                    id=new_id("con"),
                    proposal_id=proposal.id,
                    action=payload.action,
                    actor_id=user.id,
                    reason=payload.reason,
                    idempotency_key=idempotency_key,
                    occurred_at=utcnow(),
                )
            )

        db.add(
            WorkflowEvent(
                id=new_id("wfe"),
                event_type=f"PROPOSAL_{payload.action.upper()}",
                aggregate_id=proposal.id,
                payload_json={"proposal_id": proposal.id, "actor_id": user.id},
                idempotency_key=f"consent-{idempotency_key}",
            )
        )
        _audit(db, user.id, f"PROPOSAL_{payload.action.upper()}", "proposal", proposal.id, payload.reason)
        db.commit()
        return {
            "status": "processed",
            "action": payload.action,
            "proposal_id": proposal.id,
            "assignment_id": assignment_id,
            "proposal_state": proposal.state,
        }
    except InvalidTransition as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc


AssignmentState_PENDING = "PENDING_APPROVAL"


@router.post("/events")
def record_event(
    payload: DisruptionEventRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.COORDINATOR, Role.ADMIN)),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=4, max_length=128),
) -> dict:
    from .models import AllocationProposal, AllocationRun

    existing = db.scalar(select(WorkflowEvent).where(WorkflowEvent.idempotency_key == idempotency_key))
    if existing:
        if str(existing.aggregate_id) != str(payload.assignment_id):
            raise HTTPException(409, f"Idempotency key already used for a different aggregate ({existing.aggregate_id})")
        if str(existing.payload_json.get("actor_id", "")) != str(user.id):
            raise HTTPException(409, f"Idempotency key already used by a different actor")
        return {"status": "already_processed", "event_type": existing.event_type}

    if payload.event_type != "WITHDRAWAL" or not payload.assignment_id:
        raise HTTPException(422, "Only WITHDRAWAL with assignment_id is implemented in this slice")

    assignment = db.get(Assignment, payload.assignment_id)
    if assignment is None:
        raise HTTPException(404, "Assignment not found")
    try:
        transition_assignment(AssignmentState(assignment.state), AssignmentState.WITHDRAWN)
    except (InvalidTransition, ValueError) as exc:
        raise HTTPException(409, f"Cannot withdraw assignment in state {assignment.state}") from exc
    assignment.state = "WITHDRAWN"
    assignment.version += 1
    assignment.ended_utc = payload.occurred_at

    proposal = db.get(AllocationProposal, assignment.proposal_id)
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    task = db.get(Task, proposal.task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    project = db.get(Project, task.project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    if user.role != Role.ADMIN.value:
        membership = db.scalar(
            select(OrgMembership).where(
                OrgMembership.organization_id == project.organization_id,
                OrgMembership.user_id == user.id,
            )
        )
        if membership is None:
            raise HTTPException(403, "Not a member of this organization")

    problem = _build_problem_from_project(db, project.id, mode=SolverMode.REPAIR)
    plan = build_repair_plan(problem, proposal.volunteer_id, task.id)
    if plan.proposals:
        run_id = _persist_result(db, plan.proposals, project.id)
    else:
        run_id = None

    db.add(
        WorkflowEvent(
            id=new_id("wfe"),
            event_type=payload.event_type,
            aggregate_id=assignment.id,
            payload_json={
                "assignment_id": assignment.id,
                "task_id": task.id,
                "volunteer_id": proposal.volunteer_id,
                "note": payload.note,
            },
            idempotency_key=idempotency_key,
        )
    )
    _audit(
        db,
        user.id,
        "ASSIGNMENT_WITHDRAWN",
        "assignment",
        assignment.id,
        payload.note or "Repair plan generated; other commitments unchanged.",
    )
    db.commit()
    return {
        "status": "processed",
        "assignment_id": assignment.id,
        "new_assignment_state": assignment.state,
        "repair_run_id": run_id,
        "repair_status": plan.proposals.status.value if plan.proposals else None,
        "kept_commitments": plan.kept,
        "released_commitments": plan.released,
        "new_proposals": len(plan.proposals.proposals) if plan.proposals else 0,
        "note": plan.note,
    }


@router.get("/audit")
def list_audit(
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.ADMIN)),
) -> list[dict]:
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 200))).all()
    return [
        {
            "id": row.id,
            "actor_id": row.actor_id,
            "action": row.action,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "reason": row.reason,
            "policy_version": row.policy_version,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.post("/demo/seed")
def seed_demo(
    payload: SeedRequest,
    db: Session = Depends(get_db),
) -> dict:
    settings = get_settings()
    if not settings.enable_demo_seed:
        raise HTTPException(403, "Demo seeding is disabled")
    if db.scalar(select(User).where(User.email == "demo-org@example.test")):
        raise HTTPException(409, "Demo data already exists; use a fresh database")

    rng = random.Random(payload.seed)
    skills = ["translation", "web", "accessibility", "education", "mapping"]
    org_user = User(
        id=new_id("usr"),
        email="demo-org@example.test",
        password_hash=hash_password("DemoPass123!"),
        role=Role.COORDINATOR.value,
        display_name="Demo Coordinator",
    )
    admin_user = User(
        id=new_id("usr"),
        email="demo-admin@example.test",
        password_hash=hash_password("DemoPass123!"),
        role=Role.ADMIN.value,
        display_name="Demo Admin",
    )
    db.add_all([org_user, admin_user])
    db.flush()
    org = Organization(
        id=new_id("org"),
        name="Demo Community nonprofit",
        country_code="IN",
        verification_status=OrganizationVerification.VERIFIED.value,
    )
    db.add(org)
    db.flush()
    db.add(OrgMembership(id=new_id("mem"), user_id=org_user.id, organization_id=org.id, role="COORDINATOR"))
    project = Project(id=new_id("prj"), organization_id=org.id, name="Global skills sprint", status="ACTIVE")
    db.add(project)
    db.flush()

    now = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=2)
    for index in range(payload.tasks):
        skill = skills[index % len(skills)]
        skill_row = _get_or_create_skill(db, skill)
        task = Task(
            id=new_id("tsk"),
            project_id=project.id,
            name=f"{skill.title()} task {index + 1}",
            description=f"Produce a {skill} deliverable with clear acceptance criteria.",
            status="VALIDATED",
            effort_hours=rng.choice([2, 4, 6]),
            start_utc=now,
            end_utc=now + timedelta(days=3),
            deadline_utc=now + timedelta(days=4),
            dependencies_json=[],
            max_assignees=1,
            value=rng.randint(60, 200),
            acceptance_criteria_present=1,
            required_languages_json=[] if index % 3 else ["en"],
            requires_approval=0,
        )
        db.add(task)
        db.flush()
        db.add(
            TaskSkill(
                task_id=task.id,
                skill_id=skill_row.id,
                min_proficiency=rng.choice([40, 50, 60]),
                mandatory=1,
            )
        )

    for index in range(payload.volunteers):
        email = f"demo-v{index + 1}@example.test"
        user = User(
            id=new_id("usr"),
            email=email,
            password_hash=hash_password("DemoPass123!"),
            role=Role.VOLUNTEER.value,
            display_name=f"Demo Volunteer {index + 1}",
        )
        db.add(user)
        db.flush()
        volunteer = Volunteer(
            id=new_id("vol"),
            user_id=user.id,
            display_name=user.display_name,
            timezone="UTC",
            weekly_capacity_hours=rng.choice([4, 8, 12]),
            country_code="US",
            contact_permitted=1,
        )
        db.add(volunteer)
        db.flush()
        db.add(
            AvailabilityWindow(
                id=new_id("avl"),
                volunteer_id=volunteer.id,
                start_utc=now,
                end_utc=now + timedelta(days=5),
                epistemic_state=(
                    KnowledgeState.UNKNOWN.value if index % 5 == 0 else KnowledgeState.KNOWN_TRUE.value
                ),
            )
        )
        for skill in rng.sample(skills, k=2):
            skill_row = _get_or_create_skill(db, skill)
            db.add(
                VolunteerSkill(
                    volunteer_id=volunteer.id,
                    skill_id=skill_row.id,
                    proficiency=rng.randint(30, 95),
                    epistemic_state=(
                        KnowledgeState.UNKNOWN.value if index % 7 == 0 else KnowledgeState.KNOWN_TRUE.value
                    ),
                    observed_at=utcnow(),
                    source="self_report",
                )
            )

    db.commit()
    _audit(db, admin_user.id, "DEMO_SEEDED", "system", "demo", f"{payload.volunteers} volunteers, {payload.tasks} tasks")
    db.commit()
    return {
        "status": "seeded",
        "project_id": project.id,
        "coordinator": {"email": org_user.email, "password": "DemoPass123!"},
        "admin": {"email": admin_user.email, "password": "DemoPass123!"},
        "volunteer": {"email": "demo-v1@example.test", "password": "DemoPass123!"},
        "counts": {"volunteers": payload.volunteers, "tasks": payload.tasks, "seed": payload.seed},
    }
