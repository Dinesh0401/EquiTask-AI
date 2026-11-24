# Research validation plan

## 1. Simulation before humans

`simulations/generator.py` will produce reproducible instances with:
- 100 volunteers, 12 countries, 5 organizations (illustrative target; smaller smoke tests first);
- skill distributions: uniform, skewed, scarce-skill;
- demand: balanced, overloaded, bursty;
- time zones and DST transitions;
- missingness: MCAR and nonrandom (e.g., low-confidence volunteers omit availability);
- acceptance models: deterministic, noisy, preference-correlated;
- events: withdrawal, deadline change, new task, connectivity loss.

Every run records seed, generator version, policy version, solver version and code commit hash where available.

## 2. Metrics (definitions)

Research:
- feasible allocation rate = instances with valid proposals / instances.
- completion rate = verified deliverables / accepted assignments (simulated until pilot).
- expected vs realized completion = calibration gap.
- workload imbalance = scaled mean absolute deviation of normalized utilization (from formulation).
- opportunity fairness = same over offers among eligible volunteers.
- preference satisfaction = accepted proposals with preference INTERESTED / accepted proposals.
- clarifying questions = count per solved task; burden cap.
- reassignment disruption = changed accepted assignments + disturbance hours.
- recovery latency = event time → approved diff time (simulated).
- constraint violations = count from invariant checker (must be 0).
- solver runtime = wall clock ms.
- agent cost = tokens/inference where applicable (not applicable to current deterministic slice).

Product:
- time to first useful opportunity, time to confirmed assignment, milestone success, retention, organization satisfaction, human intervention load, accessibility/usability, recovery from failed workflows.

## 3. Statistical analysis

- ≥30 paired seeds for primary comparisons; 20 for smoke.
- Paired bootstrap 95% CIs; report effect sizes, not only p-values.
- Sensitivity: λ grid, risk severity, staleness threshold, time limits.
- Ablations: clarification, fairness term, stability term, history, uncertainty model, agents.
- Distribution shift: unseen skill distribution, higher missingness, correlated withdrawals.
- Scalability: 10/50/100/200 volunteers and tasks.

## 4. Validity threats

Surrogate fairness may diverge from perceived fairness ([arXiv:2606.19278](https://arxiv.org/abs/2606.19278)); simulated acceptance may be unrealistic; agent nondeterminism; solver gap; nonstationarity. Mitigations: preregistered metrics, fixed seeds, paired comparisons, negative-result reporting, human pilot only after simulation.

## 5. Status

No experiment results are claimed. The benchmark harness is scaffolded in `benchmarks/`; executing and recording results is the next dependency after the first-slice tests pass.
