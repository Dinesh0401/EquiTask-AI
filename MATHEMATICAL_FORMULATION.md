# Mathematical formulation — EquiTask AI

Version 0.1 (implemented in `backend/app/allocation/`). This is a design specification, not a novelty claim.

## 1. Sets and indices

| Symbol | Meaning |
|---|---|
| `V` | volunteers, indexed `v` |
| `T` | tasks awaiting allocation, indexed `t`, `t'` |
| `O` | verified organizations, indexed `o` |
| `K` | skills, indexed `k` |
| `R` | allocation rounds, indexed `r` |
| `E` | events (withdrawal, deadline change, new task), indexed `e` |

## 2. State and parameters

For volunteer `v`:

- `capacity_hours[v] > 0`: agreed weekly capacity.
- `committed_hours[v] ≥ 0`: hours in active, consented assignments.
- `skill[v,k] ∈ {0,…,100}`: self-reported/decayed proficiency estimate.
- `skill_state[v,k] ∈ {KNOWN_TRUE, KNOWN_FALSE, UNKNOWN, STALE}`: epistemic state.
- `availability_state[v] ∈ {KNOWN_TRUE, KNOWN_FALSE, UNKNOWN, STALE}`.
- `languages[v]`: set of language/state pairs.
- `preference[v,t] ∈ {INTERESTED, NEUTRAL, AVOID, UNKNOWN}`.
- `consent[v,t] ∈ {NONE, OFFERED, ACCEPTED, DECLINED, WITHDRAWN}`.
- `contact_permitted[v] ∈ {0,1}`.
- `history_offers[v]`, `history_accepted[v]`, `history_hours[v]`: prior-round record.
- `newcomer[v] ∈ {0,1}`: fewer than `n_min` prior completed assignments.

For task `t` owned by `o`:

- `required_skill[t] = (k, min_proficiency)`; multiple rows allowed.
- `effort_hours[t] > 0` (integer-scaled to tenths in the solver).
- `window[t] = [start_utc, end_utc]`.
- `deadline_utc[t]`.
- `dependencies[t]`: prerequisite task IDs.
- `max_assignees[t]` (usually 1 for this MVP).
- `value[t] ∈ {1,…,1000}`: organization-declared priority, normalized by policy.
- `org_verified[t] ∈ {0,1}`.
- `acceptance_criteria_present[t] ∈ {0,1}`.

Derived:
- `overlap[t,t'] = 1` if windows overlap incompatibly (same volunteer cannot do both).
- `reliability[v,t] ∈ [0,1]`: minimum reliability of decisive fields; stale fields decay with elapsed time (policy parameter).
- `risk[v,t] = (1 - reliability[v,t]) * severity(unknown_field)` for fields that affect eligibility.
- `fit[v,t] ∈ [0,100]`: deterministic function of verified skill proficiency, language match and stated preference. Unknown fields contribute 0, never a guessed positive.

## 3. Decision variables

- `x[v,t] ∈ {0,1}`: **proposal** to volunteer `v` for task `t`. This is not a committed assignment.
- `u_v ∈ ℤ≥0`: scaled utilization of volunteer `v`.
- `d_v ∈ ℤ≥0`: absolute workload deviation.
- `a_v ∈ ℤ≥0`: opportunity count deviation.
- `z[a] ∈ {0,1}` (repair mode only): existing accepted assignment `a` is proposed for change.

All solver arithmetic uses integers; fractional quantities are multiplied by `SCALE = 1000` and rounded after validation (CP-SAT integer requirement per [Google OR-Tools documentation](https://developers.google.com/optimization/cp/cp_solver)).

## 4. Hard constraints

A solution violating any of these is invalid.

| ID | Constraint | Meaning |
|---|---|---|
| H1 | `x[v,t] ≤ can_propose[v,t]` | No KNOWN_FALSE mandatory skill/availability, no org permission failure, no declined/withdrawn consent, no missing acceptance criteria, verified organization. |
| H2 | `Σ_t effort[t] * x[v,t] ≤ remaining_capacity[v]` | Never exceed agreed capacity. |
| H3 | `Σ_v x[v,t] = max_assignees[t]` for open tasks (or `≤` for optional tasks) | Required tasks are covered exactly once in this MVP. |
| H4 | `x[v,t] + x[v,t'] ≤ 1` whenever `overlap[t,t']` | No incompatible simultaneous commitment. |
| H5 | `x[v,t] ≤ completed_or_selected[dep]` for each dependency `dep` | Dependency respect; cycle detection precedes solving. |
| H6 | `x[v,t] = 0` if `consent[v,t] ∈ {DECLINED, WITHDRAWN}` or preference `AVOID` | Explicit refusal is binding. |
| H7 | Protected characteristics are excluded from `fit`, `can_propose` and all objective terms | Demographic audits are separate, consented and privacy-preserving. |
| H8 | Solver failure/timeout returns `NO_FEASIBLE_PROPOSAL` or `UNKNOWN`, never an assignment | Fail closed. |
| H9 | Repair mode freezes accepted assignments unless `change_permitted[a]` and a reconfirmation event exist | No silent modification. |

Activation is a separate state-machine transition: `OFFERED → ACCEPTED → ACTIVE` only after a typed, recorded consent event and any required organizational approval.

## 5. Objective

```
maximize  S = contribution
            - λ1 * workload_unfairness
            - λ2 * opportunity_unfairness
            - λ3 * disruption
            - λ4 * uncertainty_risk
            - λ5 * coordination_overhead
```

Exact integer definitions:

1. `contribution = Σ_v Σ_t value[t] * fit[v,t] * x[v,t]`.
2. `util_scaled[v] = SCALE * (committed_hours[v] + Σ_t effort[t] * x[v,t]) / capacity_hours[v]`, represented exactly via multiplication by `capacity_hours[v]`.
3. `mean_util_scaled = (1/|V|) Σ_v util_scaled[v]`; enforce `N*d_v ≥ N*util_scaled[v] − Σ_v util_scaled[v]` and `N*d_v ≥ Σ_v util_scaled[v] − N*util_scaled[v]`, where `N=|V|`. `workload_unfairness = Σ_v d_v`.
4. `opp_scaled[v] = SCALE * (history_offers[v] + Σ_t x[v,t]) / expected_opportunity_denominator[v]`, where the denominator is the number of tasks for which `v` was eligible in the current round plus a fixed prior denominator. `opportunity_unfairness` uses the same absolute-deviation construction.
5. `disruption = Σ_a break_cost[a] * z[a]`.
6. `uncertainty_risk = SCALE * Σ_v Σ_t risk[v,t] * x[v,t]`.
7. `coordination_overhead = q_count * Σ_v Σ_t clarification_needed[v,t] * x[v,t]`.

`λ` values are policy-versioned, scale-dependent and **not** assumed universal. Default in this slice: `λ1=1, λ2=1, λ3=5, λ4=1, λ5=1` after each term is normalized to comparable integer ranges. Sensitivity analysis is required.

Lexicographic alternative: (i) satisfy H1–H9; (ii) maximize contribution; (iii) minimize unfairness subject to contribution ≥ optimal − ε; (iv) minimize disruption. This is preferred when rights/safety or minimum service levels are at stake; weighted sums are an approximation and can trade incomparable quantities.

## 6. Fairness definitions considered

- **Max-min:** maximize the worst normalized utilization/opportunity; strong protection, can waste value when eligibility sets differ.
- **Nash social welfare:** maximize product/sum of log utilities; elegant but nonlinear and hard to explain; not used in the first implementation.
- **Proportional fairness:** maximize Σ log(utilization); related to Nash, requires careful handling of zero.
- **Envy-related metrics:** compare allocated value per eligible volunteer; useful audit metric, not a hard constraint here.
- **Fairness over time:** history-adjusted opportunity and workload; needed to detect repeated newcomer exclusion.

Equality of task counts is explicitly **not** fairness: capacities, eligibility and preferences differ. A mathematical fairness guarantee may be infeasible when hard constraints exclude volunteers from tasks; the system must report that rather than relax safety constraints.

## 7. Missing information model

`EpistemicField(value?, state, source, observed_at, confidence)`.

State semantics:
- `KNOWN_TRUE`: value asserted by the person or authoritative record and not stale.
- `KNOWN_FALSE`: explicitly false; acts as a hard exclusion.
- `UNKNOWN`: never reported. Never treated as neutral.
- `STALE`: reported previously but older than policy threshold; can be used only with a risk penalty or after re-confirmation.

Policy actions: `ASK`, `OFFER_TENTATIVE`, `HUMAN_REVIEW`, `DEFER`, `EXPLAIN_INFEASIBLE`. Expected decision value is estimated from sensitivity of the objective to the field; user burden is capped. Probability estimates inform risk and question selection only—never consent.

## 8. Dynamic replanning

On event `e`:
1. Persist event with idempotency key.
2. Freeze accepted/active assignments.
3. Recompute residual capacity and task demand.
4. Solve residual problem with disruption term.
5. If infeasible, search bounded modification set where `change_permitted` and consent reconfirmation exist.
6. Present a diff; apply only after approvals.
7. Log policy version, solver status and reason.

## 9. Known limitations

- Integer scaling can introduce small rounding artifacts.
- `fit` is a transparent heuristic, not a calibrated predictor.
- Fairness denominators depend on eligibility sets and may be gamed if eligibility is manipulated.
- The weighted objective has no axiomatic fairness guarantee.
- CP-SAT solutions are only as valid as input facts; stale data remains the central risk.
