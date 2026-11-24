# Database design

SQLAlchemy models in `backend/app/models.py`; Alembic configuration in `backend/alembic.ini`.

## Entities and key fields

| Table | Key fields | Notes |
|---|---|---|
| `users` | id, email unique, password_hash, role, created_at | role enum |
| `volunteers` | id, user_id unique, display_name, timezone, weekly_capacity_hours, country_code, contact_permitted | no protected characteristics |
| `skills` | id, name unique | seed data |
| `volunteer_skills` | volunteer_id, skill_id, proficiency, epistemic_state, observed_at | composite PK |
| `availability_windows` | id, volunteer_id, start_utc, end_utc, epistemic_state | UTC |
| `preferences` | volunteer_id, task_type, value, epistemic_state | composite PK |
| `organizations` | id, name, country_code, verification_status, verification_evidence_ref | PENDING/VERIFIED/REJECTED |
| `org_memberships` | user_id, organization_id, role | tenant link |
| `projects` | id, organization_id, status, description | tenant scoped |
| `tasks` | id, project_id, status, effort_hours, deadline_utc, value, acceptance_criteria, dependencies_json | UTC |
| `task_skills` | task_id, skill_id, min_proficiency | composite PK |
| `allocation_runs` | id, policy_version, solver_version, status, objective, runtime_ms, seed | research evidence |
| `constraint_evaluations` | id, run_id, subject_type, subject_id, reason_code, passed | diagnostics |
| `allocation_proposals` | id, run_id, task_id, volunteer_id, state, idempotency_key unique | proposal ≠ assignment |
| `consent_events` | id, proposal_id, action, actor_id, occurred_at, idempotency_key unique | append-only |
| `assignments` | id, proposal_id unique, state, version, started_utc, ended_utc | optimistic lock |
| `workflow_events` | id, event_type, aggregate_id, payload_json, sequence, idempotency_key unique | event log |
| `messages` | id, sender_id, recipient_id, body, proposal_id | moderation later |
| `deliverables` | id, assignment_id, object_key, checksum, submitted_at | file bytes external |
| `reviews` | id, deliverable_id, reviewer_id, decision, feedback | one per deliverable |
| `agent_runs` | id, agent_type, input_ref, output_ref, status, tokens, cost, policy_version | traceability |
| `audit_logs` | id, actor_id, action, target_type, target_id, reason, policy_version, created_at | append-only |
| `research_experiments` | id, name, seed, config_json, status | reproducibility |

## Isolation

Every task/project query joins through `org_memberships` and checks `organization_id`. Volunteers see only their own proposals/assignments. Admin access writes an audit record with reason.

## Retention and migration

- Draft policy in `docs/THREAT_MODEL.md`.
- Alembic migrations generated from model metadata; no destructive migration without reviewed backup.
- Soft deletion for account data with hard-delete export flow; append-only audit retained separately.
