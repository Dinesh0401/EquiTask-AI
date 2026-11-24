# Research gaps (to verify, not claims of novelty)

## Gap 1 — Consent as a formal hard constraint in dynamic volunteer allocation

Dynamic assignment literature includes preferences, but our mechanism treats explicit acceptance as a state-transition precondition: a proposal is never an assignment, and withdrawal must not silently alter another commitment. Need to verify whether existing volunteerassignment work models this identically.

## Gap 2 — Epistemic state and value-of-information clarification

Unreported preference is not neutral. We model `KNOWN_TRUE`, `KNOWN_FALSE`, `UNKNOWN`, `STALE`; clarification questions are selected by expected decision value and user burden. Compare with partial-information fair division (Benadè et al.) and active preference elicitation literature.

## Gap 3 — Fairness over repeated rounds with newcomer protection

Most one-shot matching evaluations cannot detect persistent exclusion. We require metrics for normalized workload, opportunity among eligible/interested volunteers, preference satisfaction, and repeat exclusion across seeds and rounds.

## Gap 4 — Minimal-disruption repair

After withdrawal, deadline change or new tasks, repair should preserve accepted commitments unless modification is necessary, permitted and reconfirmed. Need to compare against local-search repair and rolling-horizon replanning literature.

## Gap 5 — Agent authority boundary

LLM agents propose structured drafts and explanations; CP-SAT and policy engine decide feasibility. Need evaluation of whether this hybrid beats simple matcher and LLM-only baselines under injection attempts and invalid outputs.

## Gap 6 — Honest measurement under realistic data shift

Nonrandom missingness, inaccurate self-reports, DST/time-zone changes and correlated withdrawals are underrepresented in illustrative demos. Our simulation must include them and must publish negative results.

## Validation tasks before any novelty claim

1. Systematic literature search (ACM DL, IEEE Xplore, Scopus/WoS, OpenAlex, Semantic Scholar) with recorded query strings and inclusion criteria.
2. Full-text comparison of Meng et al. 2025, Dalla Vecchia et al. 2026, Benadè et al. 2022/2025 and arXiv:2606.19278.
3. Patent/product scan of volunteer coordination platforms.
4. Written differentiation statement reviewed by an independent researcher.
