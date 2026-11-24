# Pseudocode (corresponding working implementation in `backend/app/allocation/`)

```text
function allocate(problem, policy):
    validate_typed_input(problem)                 # Pydantic; reject on invalid
    reject_dependency_cycles(problem.tasks)
    candidates = []
    for v in problem.volunteers:
        for t in problem.tasks:
            if not contact_permitted(v): continue
            if consent(v,t) in {DECLINED, WITHDRAWN}: continue
            if preference(v,t) == AVOID: continue
            if any mandatory skill state == KNOWN_FALSE: continue
            if availability_state(v) == KNOWN_FALSE: continue
            if t.required_org_verified and not org.verified: continue
            if not t.acceptance_criteria_present: continue
            candidates.append((v,t,fit(v,t),risk(v,t)))

    epistemic_audit = collect_unknown_or_stale(candidates)
    questions = select_questions(epistemic_audit, max_questions=policy.max_questions)

    model = CPModel()
    x[v,t] = BoolVar for each candidate
    for each task t: sum_v x[v,t] == t.max_assignees
    for each volunteer v: sum_t effort[t]*x[v,t] <= remaining_capacity[v]
    for each overlapping pair: x[v,t] + x[v,t'] <= 1
    for each dependency: x[v,t] <= selected_or_completed[dep]
    add_scaled_objective(model, x, policy.lambdas)

    status = solve(model, time_limit=policy.solver_time_limit)
    if status in {INFEASIBLE, UNKNOWN}:
        return typed_failure(diagnose_infeasibility(problem), status)
    proposals = decode_true_variables(x)
    return AllocationResult(proposals, explanations(allowed_evidence), solver_metadata)

function accept_proposal(proposal_id, consent_event, idempotency_key):
    begin transaction
    insert event if idempotency_key unseen else return existing result
    require event.actor == proposal.volunteer
    require proposal.state == OFFERED
    revalidate hard constraints at current time
    if invalid: transition proposal to EXPIRED_INFEASIBLE and explain
    else: proposal -> ACCEPTED; create assignment state PENDING_APPROVAL or ACTIVE
    commit
    emit domain event

function repair(event, current_state):
    freeze all ACCEPTED/ACTIVE assignments
    remove capacity of withdrawn assignment
    solve residual with disruption objective
    return diff; do not mutate other assignments
```

Invariant assertions are executable in `tests/test_invariants.py`; they are not comments.
