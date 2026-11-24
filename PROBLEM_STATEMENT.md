# Problem statement — EquiTask AI

## 1. Observable coordination failure

A qualified volunteer wants to contribute remotely. A verified nonprofit has a real task. Weeks later the task is still unfilled, a different volunteer is overloaded, and two coordinators have manually reassigned the same work.

This is not primarily a "matching" failure. It is a coordination failure under uncertainty.

## 2. Problem definition

Given volunteers `V`, tasks `T`, organizations `O`, skills `S`, availability/capacity `A`, preferences/consent `P`, deadlines/dependencies `D`, and history `H`, choose allocation proposals `x[v,t] ∈ {0,1}` such that all hard constraints hold, consent is explicit, information gaps are visible, fairness over time is measurable, and disruption after change is minimized.

Research question: **Can multi-agent systems distribute work fairly when participants have conflicting constraints and incomplete information?**

## 3. Why this matters now

- International remote volunteering is established practice. UNV publishes assignment criteria requiring online-only, task-based, short-term, clearly delimited work with nondiscriminatory selection based on skills, knowledge and experience ([UNV assignment criteria](https://explore.unv.org/ov-doa-criteria), accessed 2026-11-23).
- HOT Tasking Manager coordinates distributed mapping by decomposing work into tiles, allowing volunteers to select tasks, locking tiles during work, and validating completed tiles ([OSM Wiki](https://wiki.openstreetmap.org/wiki/Tasking_Manager), last edited 2025-09-03; [LearnOSM guide](https://learnosm.org/en/coordination/tasking-manager/)).
- Recent research explicitly studies dynamic volunteer assignment with skill diversity, task variability and preferences (Meng, Feng & Yu, 2025), multi-sided fairness in sequential task assignment (Dalla Vecchia et al., 2026), and fair division with partial information (Benadè, Halpern & Psomas, 2022; Operations Research version 2025).

Therefore, a generic "AI volunteer matcher" is not a defensible contribution. The investigable object is the **joint mechanism**: consent preservation + epistemic clarification + fairness over repeated rounds + minimal-disruption recovery, governed by deterministic optimization.

## 4. 5 Whys (summary; full analysis in `ROOT_CAUSE_ANALYSIS.md`)

1. Why was work not allocated fairly/reliably? Because the allocator lacked usable current information.
2. Why was information unusable? Availability, skill confidence and preferences were missing, stale or conflicting.
3. Why were conflicts not resolved? Multiple tasks competed for the same people across time zones and deadlines.
4. Why did conflicts persist? Acceptances were treated as commitments even when later circumstances changed; repair was manual.
5. Why did repair concentrate harm? Historical opportunity and workload were not tracked, so the same visible volunteers were reused.

## 5. Scope boundary

Included: translations, accessibility testing, educational resources, nonprofit technical assistance, community mapping coordination.

Excluded from initial scope: emergency dispatch, unsupervised high-risk humanitarian decisions, sensitive physical deployments, minors without an approved safeguarding framework, sensitive beneficiary data.

## 6. Positioning and non-affiliation

EquiTask AI is an independent research prototype. It is **not affiliated with** United Nations Volunteers, HOT, OpenStreetMap, or any cited organization.

## 7. What would count as evidence

A simulated environment with documented seeds and configurations; paired comparisons against baselines; confidence intervals; ablations; distribution-shift tests; explicit negative results; and—only later—a consented pilot with real organizations. No such evidence is claimed in this document.
