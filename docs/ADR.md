# Architecture decision records

## ADR-001 — Modular monolith first

Decision: one FastAPI application with internal modules; no microservices yet.
Rationale: small team, shared domain model, easier transactional consistency and auditability.
Consequences: scale-out later may require extracting solver/worker; boundaries are kept explicit.

## ADR-002 — CP-SAT is authoritative for feasibility

Decision: OR-Tools CP-SAT enforces hard constraints; language models cannot override it.
Rationale: exact constraint satisfaction is a deterministic problem; LLM output is stochastic.
Consequences: solver timeouts fail closed; infeasibility needs explicit diagnostics.

## ADR-003 — Proposals are not assignments

Decision: separate `AllocationProposal` and `Assignment` entities and state machines.
Rationale: non-negotiable consent rule; withdrawal/retry safety.
Consequences: API never returns ACTIVE from allocation run; tests enforce.

## ADR-004 — Explicit epistemic states

Decision: `KNOWN_TRUE`, `KNOWN_FALSE`, `UNKNOWN`, `STALE` on decisive fields.
Rationale: treating missing data as neutral is an unstated assumption; H1 tests this.
Consequences: more fields to manage; clarification policy required.

## ADR-005 — At-least-once events with idempotency keys

Decision: no exactly-once claim; deduplicate side effects by key and transactional state checks.
Rationale: realistic distributed-system guarantee.
Consequences: every mutating endpoint requires an idempotency key.

## ADR-006 — Static accessible UI for first runnable slice

Decision: serve a small semantic HTML/CSS/JS UI from FastAPI; plan Next.js later.
Rationale: first milestone is allocation engine and state machine; avoid cosmetic frontend before deterministic core works.
Consequences: not the final product UI; localization/framework features deferred.

## ADR-007 — Policy-versioned fairness weights

Decision: weights and thresholds are versioned input, not hardcoded truth.
Rationale: fairness-efficiency tradeoff is empirical and context-dependent.
Consequences: every result records policy version; sensitivity analysis required.
