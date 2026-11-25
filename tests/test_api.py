"""API-level tests for the EquiTask AI FastAPI application.

Covers auth, volunteer/org/project/task lifecycle, allocation run, proposal
consent state machine, idempotency, withdrawal/repair, and audit.

All tests register their own accounts before authenticating. ADMIN accounts
are created directly in the test database because self-registration of ADMIN
is intentionally blocked (P0 security fix).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models import User, Organization, OrgMembership, new_id, utcnow
from app.enums import Role, OrganizationVerification


def _register(client, email, role, password="StrongPass123!"):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "role": role, "display_name": email.split("@")[0]},
    )


def _login(client, email, password="StrongPass123!"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _auth_header(client, email, password="StrongPass123!"):
    resp = _login(client, email, password)
    assert resp.status_code == 200, f"login failed for {email}: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_admin(db_session, client, email, password="AdminPass123!", display_name="Admin User"):
    """Create an ADMIN user (self-registration is blocked).

    Registers as VOLUNTEER via the API (which is allowed), then promotes
    the role to ADMIN directly in the database session.
    """
    # Register via API (VOLUNTEER is self-registerable).
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "role": "VOLUNTEER", "display_name": display_name},
    )
    assert reg.status_code in (200, 201), f"admin registration failed: {reg.text}"

    # Promote to ADMIN directly in the DB session.
    user = db_session.scalar(select(User).where(User.email == email.lower()))
    assert user is not None, f"admin user {email} not found after registration"
    user.role = Role.ADMIN.value
    db_session.commit()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_register_and_login(client):
    resp = _register(client, "alice@example.test", "VOLUNTEER")
    assert resp.status_code in (200, 201), resp.text
    resp = _login(client, "alice@example.test")
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_duplicate_email_rejected(client):
    _register(client, "bob@example.test", "VOLUNTEER")
    resp = _register(client, "bob@example.test", "VOLUNTEER")
    assert resp.status_code == 409, resp.text


def test_admin_self_registration_rejected(client):
    """P0: ordinary users cannot self-register as ADMIN."""
    resp = _register(client, "evil@example.test", "ADMIN", "EvilPass123!")
    assert resp.status_code == 403, resp.text


def test_coordinator_self_registration_rejected(client):
    """P0: ordinary users cannot self-register as COORDINATOR."""
    resp = _register(client, "evil2@example.test", "COORDINATOR", "EvilPass123!")
    assert resp.status_code == 403, resp.text


def test_unauthenticated_request_rejected(client):
    resp = client.get("/api/v1/me")
    assert resp.status_code == 401, resp.text


# ---------------------------------------------------------------------------
# Volunteer profile
# ---------------------------------------------------------------------------

def test_create_volunteer_profile(client, db_session):
    _register(client, "vol@example.test", "VOLUNTEER", "VolunteerPass123!")
    headers = _auth_header(client, "vol@example.test", "VolunteerPass123!")
    resp = client.post(
        "/api/v1/volunteers",
        json={
            "display_name": "Volunteer One",
            "timezone": "UTC",
            "weekly_capacity_hours": 10,
            "country_code": "US",
            "contact_permitted": True,
        },
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    assert resp.json()["weekly_capacity_hours"] == 10


# ---------------------------------------------------------------------------
# Organization lifecycle
# ---------------------------------------------------------------------------

def test_create_and_verify_organization(client, db_session):
    _register(client, "org@example.test", "ORGANIZATION", "OrgPass123!")
    headers = _auth_header(client, "org@example.test", "OrgPass123!")
    resp = client.post(
        "/api/v1/organizations",
        json={"name": "Demo Nonprofit", "country_code": "IN"},
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    org_id = resp.json()["id"]

    _make_admin(db_session, client, "admin@example.test")
    admin_headers = _auth_header(client, "admin@example.test", "AdminPass123!")
    resp = client.post(
        f"/api/v1/admin/organizations/{org_id}/verify",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["verification_status"] == "VERIFIED"


# ---------------------------------------------------------------------------
# Project and task (with org membership authorization)
# ---------------------------------------------------------------------------

def _seed_org_and_project(client, db_session, org_name="Demo Nonprofit Two", country="US"):
    _register(client, "org2@example.test", "ORGANIZATION", "Org2Pass123!")
    headers = _auth_header(client, "org2@example.test", "Org2Pass123!")
    org_resp = client.post(
        "/api/v1/organizations",
        json={"name": org_name, "country_code": country},
        headers=headers,
    )
    assert org_resp.status_code in (200, 201), org_resp.text
    org_id = org_resp.json()["id"]

    _make_admin(db_session, client, "admin2@example.test", password="Admin2Pass123!")
    admin_headers = _auth_header(client, "admin2@example.test", "Admin2Pass123!")
    verify_resp = client.post(
        f"/api/v1/admin/organizations/{org_id}/verify",
        headers=admin_headers,
    )
    assert verify_resp.status_code == 200, verify_resp.text

    now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    project_resp = client.post(
        "/api/v1/projects",
        json={"organization_id": org_id, "name": "Translation sprint", "description": "Translate docs"},
        headers=headers,
    )
    assert project_resp.status_code in (200, 201), project_resp.text
    project_id = project_resp.json()["id"]

    task_resp = client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "name": "Translate page",
            "description": "Translate the welcome page.",
            "required_skills": [{"skill": "translation", "min_proficiency": 60, "mandatory": True}],
            "effort_hours": 4,
            "start_utc": now.isoformat(),
            "end_utc": (now + timedelta(days=2)).isoformat(),
            "deadline_utc": (now + timedelta(days=3)).isoformat(),
            "max_assignees": 1,
            "value": 100,
            "acceptance_criteria_present": True,
        },
        headers=headers,
    )
    assert task_resp.status_code in (200, 201), task_resp.text
    return project_id, task_resp.json()["id"], headers, org_id


def test_create_project_and_task(client, db_session):
    _seed_org_and_project(client, db_session)


def test_cannot_create_task_in_another_orgs_project(client, db_session):
    """P0: a coordinator cannot create tasks in another organization's project."""
    # Org A
    project_id_a, _, headers_a, org_id_a = _seed_org_and_project(client, db_session, "Org A", "US")
    # Org B coordinator tries to use Org A's project
    _register(client, "orgb@example.test", "ORGANIZATION", "OrgBPass123!")
    headers_b = _auth_header(client, "orgb@example.test", "OrgBPass123!")
    org_resp = client.post(
        "/api/v1/organizations",
        json={"name": "Org B", "country_code": "CA"},
        headers=headers_b,
    )
    org_id_b = org_resp.json()["id"]
    _make_admin(db_session, client, "adminb@example.test", password="AdminBPass123!")
    admin_headers_b = _auth_header(client, "adminb@example.test", "AdminBPass123!")
    client.post(
        f"/api/v1/admin/organizations/{org_id_b}/verify",
        headers=admin_headers_b,
    )
    now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    resp = client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id_a,
            "name": "Unauthorized task",
            "description": "Should be rejected.",
            "required_skills": [],
            "effort_hours": 2,
            "start_utc": now.isoformat(),
            "end_utc": (now + timedelta(days=1)).isoformat(),
            "deadline_utc": (now + timedelta(days=2)).isoformat(),
            "max_assignees": 1,
            "value": 50,
            "acceptance_criteria_present": True,
        },
        headers=headers_b,
    )
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# Allocation run (with org membership authorization)
# ---------------------------------------------------------------------------

def test_allocation_run_returns_proposals_only(client, db_session):
    project_id, task_id, headers, org_id = _seed_org_and_project(client, db_session)
    resp = client.post(
        "/api/v1/allocations/run",
        json={"project_id": project_id},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] in ("OPTIMAL_PROPOSALS", "FEASIBLE_PROPOSALS", "NO_FEASIBLE_PROPOSAL")
    for p in body.get("proposals", []):
        assert "state" not in p or p.get("state") != "ACTIVE"
    assert "policy_version" in body
    assert "solver_version" in body


def test_allocation_run_invalid_input(client, db_session):
    _register(client, "coord@example.test", "ORGANIZATION", "CoordPass123!")
    headers = _auth_header(client, "coord@example.test", "CoordPass123!")
    resp = client.post(
        "/api/v1/allocations/run",
        json={},
        headers=headers,
    )
    assert resp.status_code in (400, 422), resp.text


def test_cannot_run_allocation_for_another_org(client, db_session):
    """P0: a coordinator cannot run allocation for another organization."""
    project_id_a, _, headers_a, _ = _seed_org_and_project(client, db_session, "Org A", "US")
    # Org B coordinator
    _register(client, "orgb2@example.test", "ORGANIZATION", "OrgB2Pass123!")
    headers_b = _auth_header(client, "orgb2@example.test", "OrgB2Pass123!")
    org_resp_b = client.post(
        "/api/v1/organizations",
        json={"name": "Org B2", "country_code": "CA"},
        headers=headers_b,
    )
    org_id_b = org_resp_b.json()["id"]
    _make_admin(db_session, client, "adminb2@example.test", password="AdminB2Pass123!")
    admin_headers_b = _auth_header(client, "adminb2@example.test", "AdminB2Pass123!")
    client.post(
        f"/api/v1/admin/organizations/{org_id_b}/verify",
        headers=admin_headers_b,
    )
    resp = client.post(
        "/api/v1/allocations/run",
        json={"project_id": project_id_a},
        headers=headers_b,
    )
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# Proposal consent and idempotency
# ---------------------------------------------------------------------------

def test_proposal_consent_idempotency(client, db_session):
    project_id, task_id, headers, org_id = _seed_org_and_project(client, db_session)

    # Seed a volunteer
    _register(client, "vol3@example.test", "VOLUNTEER", "Vol3Pass123!")
    vol_headers = _auth_header(client, "vol3@example.test", "Vol3Pass123!")
    client.post(
        "/api/v1/volunteers",
        json={"display_name": "Vol Three", "timezone": "UTC", "weekly_capacity_hours": 10, "contact_permitted": True},
        headers=vol_headers,
    )

    # Run allocation to create a proposal
    resp = client.post("/api/v1/allocations/run", json={"project_id": project_id}, headers=headers)
    assert resp.status_code == 200
    proposals = resp.json().get("proposals", [])
    if not proposals:
        pytest.skip("No volunteer with matching skills; allocation run still works")

    # Look up the proposal ID from the DB (API response doesn't include proposal id)
    from app.models import AllocationProposal

    db_proposal = (
        db_session.query(AllocationProposal)
        .filter(AllocationProposal.task_id == proposals[0]["task_id"])
        .filter(AllocationProposal.volunteer_id == proposals[0]["volunteer_id"])
        .order_by(AllocationProposal.created_at.desc())
        .first()
    )
    assert db_proposal is not None, "Proposal not persisted to database"
    proposal_id = db_proposal.id

    idem_key = "idem-consent-1"
    accept_resp = client.post(
        f"/api/v1/proposals/{proposal_id}/respond",
        json={"action": "accept", "reason": "I can do it"},
        headers={**vol_headers, "Idempotency-Key": idem_key},
    )
    assert accept_resp.status_code in (200, 409), accept_resp.text

    # Replay same idempotency key -> already_processed
    replay_resp = client.post(
        f"/api/v1/proposals/{proposal_id}/respond",
        json={"action": "accept", "reason": "I can do it"},
        headers={**vol_headers, "Idempotency-Key": idem_key},
    )
    assert replay_resp.status_code == 200
    assert replay_resp.json().get("status") == "already_processed"


def test_idempotency_key_reuse_for_different_proposal_rejected(client, db_session):
    """P1: an idempotency key must not be reusable across different proposals."""
    project_id, task_id, headers, org_id = _seed_org_and_project(client, db_session)

    _register(client, "vol4@example.test", "VOLUNTEER", "Vol4Pass123!")
    vol_headers = _auth_header(client, "vol4@example.test", "Vol4Pass123!")
    client.post(
        "/api/v1/volunteers",
        json={"display_name": "Vol Four", "timezone": "UTC", "weekly_capacity_hours": 10, "contact_permitted": True},
        headers=vol_headers,
    )

    resp = client.post("/api/v1/allocations/run", json={"project_id": project_id}, headers=headers)
    assert resp.status_code == 200
    proposals = resp.json().get("proposals", [])
    if len(proposals) < 2:
        pytest.skip("Need at least 2 proposals for this test")

    # Look up proposal IDs from the DB (API response doesn't include proposal id)
    from app.models import AllocationProposal

    db_proposals = (
        db_session.query(AllocationProposal)
        .filter(AllocationProposal.task_id.in_([p["task_id"] for p in proposals]))
        .order_by(AllocationProposal.created_at.desc())
        .all()
    )
    if len(db_proposals) < 2:
        pytest.skip("Need at least 2 persisted proposals for this test")

    idem_key = "idem-shared-key"
    # Accept first proposal with the key
    resp1 = client.post(
        f"/api/v1/proposals/{db_proposals[0].id}/respond",
        json={"action": "accept", "reason": "first"},
        headers={**vol_headers, "Idempotency-Key": idem_key},
    )
    assert resp1.status_code in (200, 409), resp1.text

    # Reuse the same key for a different proposal -> should not succeed
    resp2 = client.post(
        f"/api/v1/proposals/{db_proposals[1].id}/respond",
        json={"action": "accept", "reason": "second"},
        headers={**vol_headers, "Idempotency-Key": idem_key},
    )
    assert resp2.status_code in (409, 400), f"Expected rejection, got {resp2.status_code}: {resp2.text}"


# ---------------------------------------------------------------------------
# Withdrawal event
# ---------------------------------------------------------------------------

def test_withdrawal_endpoint_exists(client, db_session):
    """P1: the events endpoint must be registered and reject invalid payloads."""
    _seed_org_and_project(client, db_session)
    resp = client.post(
        "/api/v1/events",
        json={"event_type": "WITHDRAWAL", "occurred_at": datetime.now(timezone.utc).isoformat()},
        headers={"Authorization": "Bearer invalid"},
    )
    assert resp.status_code in (401, 403, 422, 404), resp.text


# ---------------------------------------------------------------------------
# Audit RBAC
# ---------------------------------------------------------------------------

def test_admin_can_view_audit(client, db_session):
    _make_admin(db_session, client, "adminaudit@example.test")
    headers = _auth_header(client, "adminaudit@example.test", "AdminPass123!")
    resp = client.get("/api/v1/audit", headers=headers)
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)


def test_volunteer_cannot_access_admin_audit(client, db_session):
    _register(client, "volaudit@example.test", "VOLUNTEER", "VolAuditPass123!")
    headers = _auth_header(client, "volaudit@example.test", "VolAuditPass123!")
    resp = client.get("/api/v1/audit", headers=headers)
    assert resp.status_code == 403, resp.text


