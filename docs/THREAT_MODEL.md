# Threat model and privacy notes

## Assets

Volunteer identity/contact data, skills and availability, consent records, organization verification evidence, deliverables, allocation history, audit logs, research metrics.

## Adversaries

Malicious organization applicant; compromised coordinator account; malicious volunteer; untrusted task text; compromised LLM output; insider with DB access.

## STRIDE summary

| Threat | Example | Mitigation |
|---|---|---|
| Spoofing | fake organization | verification workflow, RBAC, MFA later |
| Tampering | forged consent event | signed actor context, transactional event log, idempotency, audit |
| Repudiation | coordinator overrides allocation silently | mandatory reason + actor + policy version |
| Information disclosure | explanation reveals another volunteer's preferences | explanation allowlist; per-tenant queries |
| Denial of service | huge solver instance | input caps, timeouts, rate limits |
| Elevation of privilege | agent calls admin API | least-privilege tool tokens; policy gate |

## Prompt injection

Follow [OWASP LLM01:2025](https://genai.owasp.org/llm-top-10/2025-archive/llm01-prompt-injection): segregate external content, validate typed outputs, least privilege, human approval for high-risk actions, adversarial tests. RAG/fine-tuning are not sufficient defenses.

## Data protection

- GDPR considerations: lawful basis, data minimization, purpose limitation, access/portability/erasure workflows, DPIA for automated decisions, records of processing. This is **not** a legal compliance claim; consult qualified counsel before EU pilot.
- Adults-only initial pilot unless a reviewed safeguarding framework exists.
- Do not collect sensitive beneficiary information.
- Do not use protected characteristics as decision features; any demographic fairness audit must be consented, aggregated and privacy-preserving.
- Retention draft: active account data for account lifetime + 30 days; audit logs 24 months; deliverables per organization agreement; deletion requests honored subject to legal holds. These are draft policy values requiring legal review.
- Backups encrypted; restore tested before pilot.
- Secrets via environment/secret manager; never in repository.

## Secure development

Server-side validation, parameterized SQL via SQLAlchemy, CSP for UI, secure upload scanning/quarantine later, dependency scanning in CI, security review before real users.
