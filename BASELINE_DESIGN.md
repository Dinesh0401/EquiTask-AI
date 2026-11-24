# Baseline design

All baselines consume the same typed `AllocationProblem` and are checked by the same invariant suite. A baseline that violates hard constraints is marked invalid; its score is not reported as a valid result.

| # | Baseline | Implementation status | Purpose |
|---|---|---|---|
| B1 | Random feasible | planned in `simulations/` | Lower bound, exposes constraint density |
| B2 | First-come-first-served | planned | Current manual practice analogue |
| B3 | Greedy skill match | implemented in `baselines.py` | Common "AI matcher" analogue |
| B4 | Maximum-weight bipartite matching | planned (min-cost flow / CP-SAT restriction) | Classical optimization reference |
| B5 | CP-SAT efficiency-only | implemented via solver mode | Isolates fairness contribution |
| B6 | CP-SAT fairness-aware | implemented as proposed mechanism core | H2 |
| B7 | Dynamic periodic replanning | planned | H3 comparator |
| B8 | Stability-aware repair | implemented in `repair.py` | H3 |
| B9 | Controlled LLM-only planner | deferred | H4; must be wrapped in hard-constraint validator and budget caps |

## Fair comparison rules

- Same seeds, same task/volunteer instances, same solver time limit.
- Report solver status and infeasibility counts, not just mean scores.
- Report mean with 95% paired bootstrap CI across seeds.
- Report runtime, constraint violations and disruption separately.
- If the proposed mechanism loses, report the loss and investigate.
