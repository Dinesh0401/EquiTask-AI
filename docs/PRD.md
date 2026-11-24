# Product requirements document — EquiTask AI

## Product identity

EquiTask AI is an independent, fair, consent-based volunteer coordination and recovery platform. Not affiliated with UNV, HOT, OSM or any cited organization.

## Users and permissions

| Role | Can do | Cannot do |
|---|---|---|
| Volunteer | manage own profile/skills/availability/preferences; view opportunities; accept/decline/postpone/withdraw; submit deliverables; export/delete own data | view other volunteers' private data; change allocations; approve own work |
| Organization member (verified) | create projects/tasks; view recommendations and conflicts; approve assignments; review deliverables; request clarification/reassignment; view aggregate metrics | see other organizations' private data; bypass consent |
| Coordinator | above for own organization | global admin actions |
| Administrator | org verification, access control, moderation, audit, policy/feature versions, overrides with reasons | alter history without audit; view private data without logged purpose |

## Functional requirements (MVP slice 1–3)

1. Volunteer registration and profile with skills, languages, capacity, timezone-aware availability and preferences.
2. Organization registration plus verification workflow state; only verified organizations may publish tasks.
3. Project/task creation with deliverable, acceptance criteria, effort, skill requirements, deadline, dependencies and value/priority.
4. Epistemic audit producing `UNKNOWN`/`STALE` fields and clarification questions.
5. Deterministic eligibility and CP-SAT allocation producing **proposals only**.
6. Infeasibility explanation with reason codes.
7. Proposal consent state machine with idempotent accept/decline/withdraw.
8. Required approval before activation where configured.
9. Assignment lifecycle through deliverable submission and review.
10. Event-driven repair producing a diff; no silent modification of accepted work.
11. Audit log for all consequential decisions with policy/solver version.
12. Aggregate fairness/coordination metrics.

## Non-functional requirements

- Accessibility: WCAG 2.2 AA target, keyboard navigation, semantic HTML, screen-reader labels, plain language.
- UTC-backed times with IANA timezone display; DST tests.
- Low-bandwidth: small static assets, honest loading/error states.
- Security: RBAC, tenant isolation, server-side validation, rate limiting, least-privilege agent tools.
- Privacy: data minimization, consent records, retention policy, export/delete flows.
- Reliability: idempotency keys, transactional transitions, retries with backoff, dead-letter queue later, no false exactly-once claims.
- Observability: structured logs, OpenTelemetry-compatible spans, metrics.

## Out of scope for initial pilot

Emergency dispatch, high-risk field decisions, minors without reviewed safeguarding, sensitive beneficiary data, monetary payment, automated coercion, real-user deployment without consent.

## Acceptance criteria

See `docs/EXECUTIVE_SUMMARY.md` section I and `tests/`.
