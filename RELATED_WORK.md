# Related work matrix

Evidence collected 2026-11-23. "Relevance" is an analyst assessment, not a claim about the cited authors' intentions.

| ID | Source / date | Topic | Method known from source | Relevant to EquiTask dimension | Limitation / what we must verify |
|---|---|---|---|---|---|
| R1 | [UNV assignment criteria](https://explore.unv.org/ov-doa-criteria), accessed 2026-11-23 | Online volunteering operations | Assignment screening; task-based short assignments; nondiscrimination | Consent, task validation, eligibility | Operational rules, not an algorithm |
| R2 | [OSM Wiki Tasking Manager](https://wiki.openstreetmap.org/wiki/Tasking_Manager), 2025-09-03; [LearnOSM](https://learnosm.org/en/coordination/tasking-manager/) | Distributed mapping | Project/tile decomposition, locking, validation | Concurrency, work decomposition, progress | Self-selection domain; no general fairness optimizer described |
| R3 | Meng, Feng & Yu, 2025, [*Dynamic volunteer assignment*](https://www.sciencedirect.com/science/article/pii/S1366554525001097), TR-E 197 | Dynamic volunteer assignment | Skill diversity, task variability, preferences | Dynamic allocation, preferences, skills | Disaster context; need full text to compare constraints |
| R4 | Benadè, Halpern & Psomas, [NeurIPS 2022](https://doi.org/10.52202/068431-0268) / [*Operations Research* 73(4), 2025](https://doi.org/10.1287/opre.2023.0608) | Fair division with partial information | Envy-free, welfare guarantees with binary/limited signals | H1, uncertainty-aware clarification | Abstract item allocation; no human consent cycle |
| R5 | Dalla Vecchia et al., 2026, [*Information Systems* 139:102700](https://doi.org/10.1016/j.is.2026.102700) | Sequential task assignment | Multi-sided fairness | H2, fairness over time | Recommendation/sequencing context |
| R6 | Gao, Iravani & Sinclair, 2026, [arXiv:2606.19278](https://arxiv.org/abs/2606.19278) | Nonprofit sequential allocation and routing | Max-min objectives, threshold structure, CV-based routing | H2, fairness-efficiency tradeoff; metric caution | Preprint, divisible resource/routing |
| R7 | Lien, Iravani & Smilowitz, 2014, [*Operations Research* 62(2)](https://doi.org/10.1287/opre.2013.1244) | Nonprofit sequential allocation | Max-min expected fill rate | Fairness definition lineage | Different setting |
| R8 | Sinclair et al., 2023, [*Operations Research* 71(5)](https://doi.org/10.1287/opre.2022.2397) | Fair allocation under uncertainty | Exact envy-efficiency frontier | Tradeoff measurement | Mobile food pantry |
| R9 | [Google OR-Tools CP-SAT docs](https://developers.google.com/optimization/cp/cp_solver) | Constraint solving | Boolean/integer variables, OPTIMAL/FEASIBLE/INFEASIBLE/UNKNOWN statuses | Authoritative optimizer | Tool documentation, not research claim |
| R10 | [OWASP LLM01:2025 Prompt Injection](https://genai.owasp.org/llm-top-10/2025-archive/llm01-prompt-injection) | LLM security | Input segregation, output validation, least privilege, human approval | Agent safety | Security guidance; does not validate our architecture |
| R11 | [Temporal documentation](https://docs.temporal.io/) | Durable workflows | Durable execution, retries, idempotency patterns | Reliability design decision | Not currently integrated in this slice |

## Established vs proposed

**Established methods:** constrained optimization, bipartite matching, max-min/proportional/Nash welfare concepts, robust/scenario optimization, active information acquisition, idempotent event processing, typed outputs, least-privilege tool use.

**Proposed contribution to investigate:** the integrated mechanism and its measurement in the specific remote volunteer setting: explicit epistemic states + value-of-information clarification + consent-gated CP-SAT allocation + fairness over rounds + minimal-disruption repair + typed agent boundary. Integration is not proof of novelty; a systematic review remains required.
