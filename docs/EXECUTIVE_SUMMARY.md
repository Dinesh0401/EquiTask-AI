# EquiTask AI — Executive summary (strict output contract A–J)

Status: research and first vertical slice. No deployment, no users, no novelty claim, no experimental result is asserted here.

## A. The exact problem we are solving

How can a distributed coordination system allocate remote, skills-based volunteer work **fairly and reliably** when availability, preferences, capabilities, consent and commitments are incomplete, conflicting or continuously changing?

Formal research question: **Can multi-agent systems distribute work fairly when participants have conflicting constraints and incomplete information?**

## B. Who experiences it and why existing approaches are insufficient

Volunteers, nonprofit coordinators and project leads experience the failure when a willing qualified person cannot be matched because the organization does not know real availability, several tasks compete for the same person, time zones/deadlines conflict, profile data is stale, people withdraw after accepting, manual reassignment disrupts partial work, and repeated matching concentrates opportunities on already-visible volunteers. UNV's online service provides screened, task-based, short-term assignments with nondiscrimination rules; HOT Tasking Manager provides self-selection of map tiles, locking, validation and progress tracking. Neither is presented here as a general consent-aware, uncertainty-aware, multi-objective allocator with minimal-disruption repair; that is a **gap to investigate**, not a proven novelty claim.

## C. Research hypotheses

- **H1:** Explicitly representing `UNKNOWN`/`STALE` information improves allocation quality compared with treating unreported preferences as neutral.
- **H2:** Fairness-aware allocation reduces persistent workload/opportunity imbalance versus efficiency-only assignment.
- **H3:** Stability-aware replanning reduces unnecessary reassignment disruption after withdrawal or resource change.
- **H4:** A constrained architecture combining clarification, negotiation and deterministic optimization outperforms a simple matcher and an LLM-only agent system on coordination quality.

These are falsifiable hypotheses, not findings.

## D. Mathematically defensible solution direction

Binary decision variables `x[v,t]`; hard constraints for consent, eligibility, qualifications, capacity, availability, deadlines, dependencies, permissions and non-overlap; authoritative CP-SAT solver; explicit objective with contribution value and penalties for workload unfairness, opportunity inequality, disruption, uncertainty risk and coordination overhead. Safety/rights constraints are lexicographic and are never traded against efficiency. Missing information uses explicit epistemic states and clarification; probabilities never substitute for consent.

## E. Comparison with existing approaches

| Approach | What it does well | Gap investigated here |
|---|---|---|
| UNV Online Volunteering | screened assignments, deliverables, nondiscrimination, short tasks | cross-task constrained optimization, dynamic repair, measurable fairness over rounds |
| HOT Tasking Manager | tile decomposition, self-selection, locking, validation | heterogeneous skills/preferences, consent negotiation, uncertainty-aware clarification |
| Greedy / matching baselines | simple, fast | fairness, stability, incomplete information |
| Academic dynamic volunteer assignment (Meng et al. 2025) | skill diversity, task variability, preferences | consent-preserving repair and epistemic clarification in our specific setting |
| Fair division with partial information (Benadè et al. 2022/2025) | fair online allocation with limited valuation data | hard volunteer constraints and human acceptance cycle |

## F. End-to-end user journey

Organization verification → project creation → task intake/validation → missing-information detection → clarification → hard-constraint evaluation → solver generates proposals with explanations → volunteers accept/decline/postpone → approvals → active assignments → collaboration and deliverables → organization review → feedback to historical metrics → disruption detection and bounded repair → audit.

## G. Proposed system architecture

Modular monolith: Next.js/TypeScript frontend (later slices; this slice ships an accessible static UI), Python FastAPI + Pydantic API, SQLAlchemy/PostgreSQL persistence (SQLite for local tests), OR-Tools CP-SAT optimizer, policy engine, typed agent contracts with no authority to mutate allocation state, Redis/durable jobs later, Docker/CI/OpenTelemetry. Diagrams are in `docs/ARCHITECTURE.md`.

## H. Main engineering risks

False novelty claims; solver infeasibility misread as volunteer refusal; consent bypass; stale/duplicate events creating double assignments; concurrent reassignment races; LLM prompt injection; privacy leakage in explanations; unfairness hidden by aggregate metrics; unverified "production ready" claims.

## I. MVP acceptance criteria

1. Runnable API and local UI.
2. Typed solver input; hard constraints enforced in CP-SAT.
3. Proposals are never active assignments; activation requires recorded consent and required approvals.
4. Explicit infeasibility reasons.
5. Minimal-disruption repair after withdrawal.
6. Executable invariant tests: no hard-constraint violation, no activation without consent, no capacity/overlap breach, no duplicate assignment from replayed events, no unsafe fallback on solver failure.
7. Reproducible benchmark harness with real measured output only.

## J. Ordered implementation plan

Problem validation → scientific foundation → architecture → vertical slice (domain, API, solver, consent state machine) → tests → optional typed agents → simulations/baselines → security/privacy controls → controlled pilot. This repository currently contains completed steps 1–4 and part of 5, with later steps scaffolded but not claimed complete.
