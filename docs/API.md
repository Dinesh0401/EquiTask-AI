# API specification (slice 1)

Base path `/api/v1`. Interactive docs at `/docs` when running locally.

| Method | Path | Purpose | Auth (current) |
|---|---|---|---|
| GET | `/health` | liveness | none |
| POST | `/auth/register` | create user | none |
| POST | `/auth/login` | bearer token | none |
| GET | `/me` | current user | bearer |
| POST | `/volunteers` | create volunteer profile | volunteer/admin |
| GET | `/volunteers/me` | own profile | volunteer/admin |
| PATCH | `/volunteers/me` | update own profile | volunteer/admin |
| POST | `/organizations` | create organization (PENDING_VERIFICATION) | any authenticated |
| POST | `/admin/organizations/{id}/verify` | verify organization | admin |
| POST | `/projects` | create project | verified org member/admin |
| POST | `/tasks` | create task with acceptance criteria | verified org member/admin |
| POST | `/allocations/run` | solve typed problem; returns proposals | coordinator/admin |
| GET | `/proposals/{id}` | view own/authorized proposal | participant |
| POST | `/proposals/{id}/respond` | accept/decline with idempotency key | volunteer |
| GET | `/assignments/{id}` | view assignment | participant |
| POST | `/events` | submit disruption event with idempotency key | coordinator/admin |
| GET | `/audit` | query audit events | admin |

All mutation endpoints accept header `Idempotency-Key`. Duplicate keys return the stored response with status `200`.

`POST /allocations/run` accepts either a full typed problem (for simulations) or `{project_id}` for database-backed solving. It never returns an `ACTIVE` assignment.

Example typed request (abbreviated):

```json
{
  "policy_version": "v0.1",
  "mode": "FAIRNESS_AWARE",
  "volunteers": [{"id": "v1", "capacity_hours": 10, "committed_hours": 2, "skills": [{"skill": "translation", "proficiency": 80, "state": "KNOWN_TRUE"}], "availability_state": "KNOWN_TRUE", "contact_permitted": true}],
  "tasks": [{"id": "t1", "organization_id": "o1", "required_skills": [{"skill": "translation", "min_proficiency": 60}], "effort_hours": 4, "start_utc": "2026-12-01T00:00:00Z", "end_utc": "2026-12-03T00:00:00Z", "deadline_utc": "2026-12-03T00:00:00Z", "max_assignees": 1, "value": 100, "acceptance_criteria_present": true, "organization_verified": true}]
}
```

Responses include `solver_status`, `status_code`, `objective_value`, `proposals`, `metrics`, `reason_codes`, `policy_version`, `solver_version`, and `runtime_ms`.
