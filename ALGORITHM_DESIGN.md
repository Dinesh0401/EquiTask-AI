# Algorithm design

## 1. Pipeline

```
unstructured intake
  → typed draft task
  → validation gate (human approval)
  → epistemic audit
  → clarification selection
  → candidate generation
  → CP-SAT allocation
  → explanation generation
  → proposal state machine
  → acceptance/approval
  → active assignment
  → event-driven repair
```

Only the CP-SAT step may decide feasibility. Language models may draft, ask, explain and negotiate.

## 2. Candidate generation

A pair `(v,t)` becomes a candidate if:
- organization is verified and task has acceptance criteria;
- no `KNOWN_FALSE` on a mandatory skill, availability or qualification;
- `consent[v,t]` is not `DECLINED`/`WITHDRAWN`;
- preference is not `AVOID`;
- contact is permitted;
- deadline/window passes an initial deterministic check.

`UNKNOWN`/`STALE` fields do not disqualify; they raise `risk[v,t]` and may trigger `ASK`.

## 3. Clarification policy (baseline implementation)

For each candidate, compute `impact = |best_objective_with_field − best_objective_without_field|` using a cheap local estimate; score `impact / burden`. Ask up to `max_questions_per_round` questions with score above threshold. Never invent a value; if unanswered, keep `UNKNOWN` and either offer tentatively (if safe) or defer.

## 4. Solver modes

| Mode | Behavior |
|---|---|
| `FEASIBILITY` | Find any hard-constraint-satisfying proposal set. |
| `EFFICIENCY` | Maximize contribution only. |
| `FAIRNESS_AWARE` | Default weighted objective from `MATHEMATICAL_FORMULATION.md`. |
| `REPAIR` | Freeze accepted assignments; minimize disruption; allow only consented changes. |

Solver statuses map to typed outcomes:
- `OPTIMAL` → `OPTIMAL_PROPOSALS`
- `FEASIBLE` → `FEASIBLE_PROPOSALS` with optimality gap disclosed
- `INFEASIBLE` → `NO_FEASIBLE_PROPOSAL` with blocking-constraint diagnostics
- `UNKNOWN`/timeout → `SOLVER_UNKNOWN` with safe no-op

## 5. Infeasibility diagnosis

Use deterministic subset checks in priority order: no candidate at all; insufficient remaining capacity; skill bottleneck; overlapping windows; dependency cycle; organization permission; conflicting deadlines; fairness denominator invalid. Each returns machine-readable reason codes and human-readable text; no LLM inference is required.

## 6. Minimal-disruption repair

```
locked = accepted ∪ active
residual_tasks = tasks affected by event
solve(residual_tasks, capacity_remaining_after(locked), disruption_weight high)
if infeasible:
  candidates = locked assignments with change_permitted
  solve(candidates ∪ residual_tasks, require_reconfirmation=True)
return proposal_diff (no mutation)
```

## 7. Agent placement

| Agent | Inputs | Output | Authority |
|---|---|---|---|
| Task Intake | unstructured text | `DraftTask` with missing fields | none; human approves |
| Clarification | epistemic audit | `QuestionList` | may send question only |
| Allocation Planning | typed problem | solver request | calls solver; no direct assignments |
| Negotiation | proposals + responses | messages | no state mutation |
| Recovery | events + state | repair diff | no state mutation |
| Audit/Explanation | solver output + permitted evidence | explanation text | read-only |

## 8. Complexity

Decision variables are `O(|V||T|)`. Hard constraints are sparse. CP-SAT is exponential in the worst case; time limits and problem-size caps are required. The MVP caps a single solve at 200 volunteers × 200 tasks by policy, with larger instances deferred to benchmark validation.
