# Hypotheses and falsification criteria

All hypotheses are untested.

## H1 — Explicit missing information

**Claim:** Modeling `UNKNOWN`/`STALE` and asking targeted clarifications improves expected feasible contribution value and reduces unsafe assumptions versus treating missing values as neutral/false.

**Falsify if:** across ≥20 paired seeds, the clarification variant has no statistically significant improvement (paired bootstrap 95% CI includes 0) or increases user burden beyond the pre-registered limit.

## H2 — Fairness-aware allocation

**Claim:** Adding normalized workload and opportunity fairness terms reduces persistent imbalance and newcomer exclusion versus efficiency-only CP-SAT, with a measured and disclosed efficiency cost.

**Falsify if:** no reduction in Gini/max-min opportunity gap or repeated exclusion, or improvement is entirely explained by lower completion value.

## H3 — Stability-aware repair

**Claim:** After withdrawal/change, stability-aware repair reduces changed commitments and disturbance minutes versus full replanning while preserving hard constraints.

**Falsify if:** disruption is not lower, or hard-constraint violations/consent breaches occur.

## H4 — Constrained multi-agent architecture

**Claim:** Clarification + deterministic optimization + typed negotiation/recovery agents improves coordination quality versus (a) greedy matcher, (b) CP-SAT without agents, (c) LLM-only planner.

**Falsify if:** hybrid does not dominate on the primary composite metric, or fails more often under invalid-output/prompt-injection tests.

## Primary metric (pre-registered direction)

`coordination_quality = feasible_allocation_rate * expected_completion_value - fairness_penalty - disruption_penalty - clarification_burden`, with exact scaling defined in `MATHEMATICAL_FORMULATION.md`. No numeric improvement is claimed until simulations are run.

## Threats to validity

Simulated acceptance behavior may be misspecified; fairness surrogates may not match perceived fairness (see arXiv:2606.19278); self-reported skills may be noisy; solver time limits may confound comparisons; agent costs may be nondeterministic.
