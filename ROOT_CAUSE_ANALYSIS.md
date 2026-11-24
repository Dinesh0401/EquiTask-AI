# Root cause analysis

## 1. 5 Whys

**Problem:** A qualified volunteer wants to contribute, but the organization cannot allocate work fairly and reliably.

1. **Why?** The allocator cannot determine which volunteer can take which task without violating constraints.
2. **Why?** Skill levels, availability, time zones, preferences and capacity are incomplete, stale or expressed in incompatible forms.
3. **Why?** Those attributes are collected once, in free text, and are not updated when circumstances change; multiple tasks also compete for the same volunteers.
4. **Why?** Existing workflows treat acceptance as the end of allocation and use manual coordination when someone withdraws or a deadline changes.
5. **Why?** There is no durable state machine, no history-aware fairness measure and no bounded repair policy that protects existing commitments.

Root cause statement: **coordination decisions are made from under-specified, unversioned human state, then repaired manually without historical or stability accounting.**

## 2. Symptoms versus causes

| Observable symptom | Underlying cause |
|---|---|
| Task stays unfilled despite willing volunteers | Required skill/availability state is unknown; no clarification loop |
| Same volunteers always get work | No opportunity history; visibility bias; efficiency-only ranking |
| Volunteer overloaded | No capacity constraint across simultaneous tasks |
| Withdrawal breaks project | No disruption model; no bounded repair proposal |
| Coordinator disputes | Priorities implicit; no recorded reason/version |
| "AI assigned someone without asking" | Consent not represented as a hard precondition |
| Duplicate commitments after retry | Missing idempotency keys and transactional transitions |

## 3. Systems thinking — feedback loops

- **Reinforcing imbalance:** visible volunteer → selected often → gains experience → becomes more visible → selected again.
- **Erosion of trust:** missed availability → failed assignment → coordinator avoids that volunteer → fewer opportunities → lower retention.
- **Repair cascade:** withdrawal → urgent reassignment → another volunteer overloaded → second withdrawal.

Countermeasures: opportunity history in the objective; explicit uncertainty states and clarification; stability-aware repair with consent gates; auditable policy versions.

## 4. Reasoning by analogy

| Domain | Concept that transfers | Does not transfer |
|---|---|---|
| Hospital scheduling/triage | Hard constraints and priority classes; triage is explicit | Human health urgency must not be equated with volunteer task urgency |
| Distributed systems | Idempotency, retries, dead letters, partial failure, leases | Exactly-once claims without infrastructure support; people are not processes to kill/restart |
| Economics/mechanism design | Preference elicitation, incentive awareness, auction/assignment logic | Monetary incentives cannot be assumed for volunteers |
| Control theory | Feedback from realized outcomes to future plans | No single scalar controller can represent human consent |
| Information theory | Ask high-information, low-burden questions | Information gain cannot override a person's right not to answer |
| HCI | Explanation, accessibility, clear consent, non-coercive UX | Dark patterns to accelerate acceptance |

## 5. Feynman check

Explain the system to a volunteer: "We do not decide that you must work. We ask what you can do and when. If something is unclear, we ask rather than guess. We only offer work that fits your stated limits. You accept or decline. If plans change, we ask before changing anyone else's commitment, and we record why."

If this explanation fails for a feature, the feature violates the non-negotiable rules.
