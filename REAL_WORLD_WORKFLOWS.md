# Real-world workflows and prior systems

Accessed 2026-11-23. Dates below are publication/documentation dates where available.

## 1. UNV Online Volunteering service

Sources:
- [Online Volunteer assignment criteria and overall platform rules](https://explore.unv.org/ov-doa-criteria) (UNV Explore; accessed 2026-11-23).
- [Become an Online Volunteer](https://unv.org/become-online-volunteer) (accessed via search result; direct fetch returned 403, so the 20 h/week figure below is marked as search-snippet evidence, not independently fetched text).
- [Recruitment and Selection Policy for UN Volunteers (PDF, Dec 2023)](https://explore.unv.org/sites/default/files/2023-12/Recruitment%20and%20Selection%20Policy%20for%20UN%20Volunteers_0.pdf).

Observed workflow:
1. Organization submits an assignment description.
2. UNV screens the description before publication.
3. Assignment must be online-only, support the submitting organization, be short-term (≤12 weeks), task-based, and have a clear deliverable.
4. Volunteers apply; selection is based on skills, knowledge and experience, free from discrimination on protected characteristics.
5. Assignments may be published for two weeks; UNV reserves the right to hold publishing if applications are not adequately handled.

What transfers to EquiTask AI:
- Required validation before publication.
- Explicit deliverables and acceptance criteria.
- Nondiscrimination and skills-based selection.
- Time-bounded, task-based work.

What does not transfer automatically:
- Selection still depends on organization review of applications; we need a machine-checkable consent and constraint layer.
- No public evidence from these documents of a cross-assignment fairness optimizer or minimal-disruption withdrawal repair.

## 2. HOT Tasking Manager / OpenStreetMap

Sources:
- [OSM Wiki: Tasking Manager](https://wiki.openstreetmap.org/wiki/Tasking_Manager) (last edited 2025-09-03).
- [LearnOSM: Tasking Manager](https://learnosm.org/en/coordination/tasking-manager/) (reviewed 2015-08-26; still linked as official learning material).
- [HOT Tasking Manager source](https://github.com/hotosm/tasking-manager).

Observed workflow:
1. Administrator selects an area, checks imagery, defines instructions/priority, publishes a project.
2. Mapper selects a tile; starting work locks the tile and starts a countdown; releasing unlocks it.
3. Mapper marks complete; a second mapper validates; progress is visible in project statistics.
4. Instructions support different difficulty levels and multi-language collaboration.

What transfers:
- Decomposition into independently executable work units.
- Locking to avoid conflicting simultaneous work.
- Separation of completion from validation.
- Transparent progress and activity history.

What does not transfer automatically:
- Volunteers mostly self-select tiles; our setting includes heterogeneous skills, capacity, preferences, negotiation and cross-task constraint satisfaction.
- Tile locking is a short-lived concurrency control, not a fairness or recovery mechanism.

## 3. Academic and operational prior art

| Source | Date | Contribution relevant to us | Limitation for our problem |
|---|---|---|---|
| [Dynamic volunteer assignment: Integrating skill diversity, task variability and volunteer preferences](https://www.sciencedirect.com/science/article/pii/S1366554525001097), Meng, Feng & Yu, *Transportation Research Part E*, vol. 197 | 2025-05 | Dynamic assignment with skill diversity, task variability and preferences | Disaster-response framing; our remote, consent-first, repeated-round setting differs |
| [Dynamic Fair Division with Partial Information](https://doi.org/10.1287/opre.2023.0608), Benadè, Halpern & Psomas, *Operations Research* 73(4), 1876–1896 | 2022 conference version; 2025 journal version | Fair/efficient online allocation with limited valuation information | Assumes item/valuation structure not equivalent to volunteer hard constraints and consent |
| [Multi-sided fairness in sequential task assignment](https://doi.org/10.1016/j.is.2026.102700), Dalla Vecchia, Migliorini, Quintarelli & Stefanidis, *Information Systems* 139, 102700 | 2026-07 | Multiple fairness sides in sequential assignment | Not a volunteer consent/recovery system |
| [Sequential Fair Allocation and Routing in Nonprofit Operations](https://arxiv.org/abs/2606.19278), Gao, Iravani & Sinclair | 2026-06-17 preprint | Max-min fairness under uncertain demand; warns that surrogate objectives may not improve actual fairness metrics | Divisible resource and routing, not binary constrained volunteer assignments; not peer-reviewed at time of writing |
| [Sequential Resource Allocation for Nonprofit Operations](https://doi.org/10.1287/opre.2013.1244), Lien, Iravani & Smilowitz, *Operations Research* 62(2), 301–317 | 2014 | Equitable fill-rate objective in nonprofit setting | Different domain; foundational analogy only |
| [Sequential Fair Allocation: Achieving the Optimal Envy-Efficiency Trade-off Curve](https://doi.org/10.1287/opre.2022.2397), Sinclair et al., *Operations Research* 71(5), 1689–1705 | 2023 | Exact envy/efficiency tradeoff characterization | Food pantry setting; does not model volunteer autonomy |

## 4. Differentiation hypothesis (not a novelty claim)

EquiTask AI investigates the **combination** of:
1. explicit epistemic states and value-of-information clarification;
2. deterministic hard-constraint satisfaction with consent as a first-class constraint;
3. fairness measured over repeated rounds, including newcomer exclusion;
4. minimal-disruption repair after withdrawal/change;
5. typed agents that propose but never authorize.

Novelty must be established by a systematic review and comparison against the systems above and additional literature before any claim is made.
