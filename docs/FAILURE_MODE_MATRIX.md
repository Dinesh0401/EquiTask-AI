# Failure mode matrix

Severity: S1 critical (rights/safety), S2 major, S3 minor.

| ID | Trigger | Detection | Severity | Automatic response | Human escalation | Recovery | Audit | Test |
|---|---|---|---|---|---|---|---|---|
| A1 | No eligible volunteer | solver INFEASIBLE + diagnostics | S2 | return reason codes; no proposal | coordinator after N rounds | ask clarification or extend deadline | result + reason codes | `test_no_feasible_volunteer` |
| A2 | Insufficient skills | candidate count by skill | S2 | report skill bottleneck | coordinator | recruit/retrain | reason | `test_skill_bottleneck` |
| A3 | Incompatible availability | KNOWN_FALSE/overlap check | S2 | exclude; explain | if many cases | clarification | reason | `test_availability_conflict` |
| A4 | Conflicting deadlines | dependency/window validation | S2 | reject model input | project owner | reschedule | validation error | `test_conflicting_deadlines` |
| A5 | Unsatisfiable fairness requirement | deviation infeasible | S2 | report infeasible; never relax hard rights | admin/policy owner | adjust policy version | policy version | `test_fairness_infeasible` |
| A6 | Multiple valid solutions | multiple optimal solutions | S3 | deterministic tie-break by proposal ID | none | disclose tie-break | solver seed | `test_determinism` |
| A7 | Solver timeout | status UNKNOWN | S2 | safe no-op | SRE if repeated | increase limit after review | status/runtime | `test_solver_timeout_safe` |
| A8 | Stale/invalid input | observed_at age / schema fail | S2 | mark STALE; require re-confirm | volunteer/coordinator | clarification | epistemic audit | `test_stale_field` |
| H1 | Volunteer declines | consent event | S3 | proposal DECLINED | none | re-solve residual | consent event | `test_decline` |
| H2 | Withdrawal after acceptance | withdrawal event | S1 | freeze other assignments; generate repair diff | coordinator if no feasible repair | consented repair | event + diff | `test_withdrawal_repair` |
| H3 | No response | timeout | S3 | proposal EXPIRED | coordinator after threshold | re-offer once | timeout event | `test_expiry` |
| H4 | Organization fails review | review SLA breach | S2 | reminder | coordinator | escalate | audit | later slice |
| H5 | Assignment dispute | dispute event | S1 | pause completion | admin/moderator | human resolution | audit | later slice |
| H6 | Repeated exclusion | opportunity metric threshold | S2 | flag fairness alert | admin | policy review | metric snapshot | `test_opportunity_fairness` |
| H7 | Excessive workload request | capacity check | S1 | reject proposal | coordinator | reduce load | reason | `test_capacity_invariant` |
| H8 | Coordinator priority disagreement | conflicting org events | S2 | last-write-wins rejected; require version | org owners | explicit decision | event version | later slice |
| D1 | DB outage | connection error | S2 | fail closed; retry backoff | SRE | restore from backup | error log | integration later |
| D2 | Worker crash | missing heartbeat | S2 | job retried idempotently | SRE if repeated | resume from event log | job attempts | later slice |
| D3 | Duplicate event | idempotency key hit | S2 | return stored result | none | no-op | key | `test_idempotent_accept` |
| D4 | Repeated API request | same key/method | S3 | idempotent response | none | no-op | key | `test_idempotent_accept` |
| D5 | Network timeout | client retry | S3 | retry with backoff | none | reconcile by key | request ID | later slice |
| D6 | Messaging failure | send error | S2 | dead-letter + retry | coordinator if critical | manual notification | attempt log | later slice |
| D7 | Out-of-order event | event sequence < last seen | S2 | buffer/reject | SRE if gap | reorder | sequence | later slice |
| D8 | Concurrent reassignment race | version mismatch | S1 | optimistic concurrency rejection | coordinator | reload + re-decide | version | `test_concurrency_version` |
| D9 | Lost acknowledgment | retry with same key | S2 | deduplicate | none | reconcile | key | `test_idempotent_accept` |
| D10 | Partial transaction failure | SQL error mid-transaction | S1 | rollback | SRE if persistent | retry whole transaction | rollback log | `test_transaction_rollback` |
| I1 | Hallucinated requirement | output not in source spans | S1 | schema/policy reject | reviewer | re-run | AgentRun INVALID | `test_agent_invalid_output` |
| I2 | Incorrect availability interpretation | typed field mismatch | S1 | reject; ask clarification | volunteer | re-confirm | epistemic audit | `test_unknown_not_neutral` |
| I3 | Invalid structured output | Pydantic failure | S2 | reject; retry once | developer if repeated | fallback deterministic | error | `test_agent_invalid_output` |
| I4 | Prompt injection | instruction-like untrusted content | S1 | treat as data; reject tool call | security | red-team review | security log | `test_prompt_injection` |
| I5 | Unauthorized tool use | permission scope mismatch | S1 | deny | security | revoke token | audit | `test_agent_permissions` |
| I6 | Unjustified confidence | confidence > evidence threshold | S2 | downgrade; human review | reviewer | gather evidence | AgentRun | later slice |
| I7 | Contradictory agents | conflicting drafts | S2 | policy engine chooses; no mutation | coordinator | human decision | both outputs | later slice |
| I8 | Excessive token/compute | budget exceeded | S2 | cancel run | developer | reduce scope | usage metrics | later slice |

## General rules

- No exactly-once claim: event delivery is at-least-once; side effects are idempotent.
- Solver failure never falls back to an unsafe assignment.
- Accepted commitments are frozen during repair unless explicitly reconfirmed.
- All S1 events require an audit record with actor, reason, policy version and timestamp.
