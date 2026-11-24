# EquiTask AI

**Fair, consent-based, failure-resilient volunteer coordination — a research prototype.**

> Independent research prototype. Not affiliated with United Nations Volunteers (UNV), HOT, OpenStreetMap, or any cited organization. No deployment, no users, no novelty claim, no experimental result is asserted here.

## Research question

**Can multi-agent systems distribute work fairly when participants have conflicting constraints and incomplete information?**

## What this repository contains

- `research/` — Phase 0 evidence base: problem statement, real-world workflows, root cause analysis, related work, research gaps, hypotheses.
- `docs/` — Phase 1 design: mathematical formulation, algorithm design, pseudocode, baseline design, research validation plan, plus PRD, architecture (10 Mermaid diagrams), agent contracts, failure matrix, threat model, API, database, ADRs.
- `backend/` — Runnable first vertical slice: FastAPI + Pydantic + SQLAlchemy + OR-Tools CP-SAT allocation engine, typed allocation problem, consent-aware proposal state machine, idempotent proposal transitions, withdrawal/repair, baselines, static UI.
- `tests/` — Executable invariant, API, and baseline tests.

## Non-negotiables (preserved throughout)

- Prior-art research before novelty claims.
- Deterministic optimization for hard constraints (OR-Tools CP-SAT).
- Explicit consent: a proposal is never an assignment; activation requires recorded consent.
- No invented missing data: `UNKNOWN`/`STALE` epistemic states, never treated as neutral.
- No fake results, citations, or users.
- Working code and executable tests.

## Quick start

```powershell
# Create and activate a virtual environment (recommended)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install backend dependencies
cd backend
pip install -r pyproject.toml   # or: pip install fastapi uvicorn pydantic pydantic-settings SQLAlchemy alembic ortools httpx

# Run the API locally
cd ..
$env:PYTHONPATH="backend"; python -m uvicorn app.main:app --reload

# Open the local console
# http://localhost:8000/  (static UI served by FastAPI)
# http://localhost:8000/docs  (interactive API docs)
```

Demo credentials are seeded via `POST /api/v1/demo/seed` (coordinator `demo-org@example.test` / `DemoPass123!`).

## Run the tests

```powershell
$env:PYTHONPATH="backend"; python -m pytest tests/ -v
```

> Tests use PBKDF2 password hashing (210k iterations) and may take a minute or more.

## Repository structure

```
EquiTask-AI/
├── PROBLEM_STATEMENT.md
├── REAL_WORLD_WORKFLOWS.md
├── ROOT_CAUSE_ANALYSIS.md
├── RELATED_WORK.md
├── RESEARCH_GAPS.md
├── HYPOTHESES.md
├── MATHEMATICAL_FORMULATION.md
├── ALGORITHM_DESIGN.md
├── PSEUDOCODE.md
├── BASELINE_DESIGN.md
├── RESEARCH_VALIDATION_PLAN.md
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md      (10 Mermaid diagrams)
│   ├── AGENT_CONTRACTS.md
│   ├── FAILURE_MODE_MATRIX.md
│   ├── THREAT_MODEL.md
│   ├── API.md
│   ├── DATABASE.md
│   └── ADR.md
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py
│   │   ├── api.py
│   │   ├── config.py
│   │   ├── auth.py
│   │   ├── db.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── enums.py
│   │   ├── domain/state_machine.py
│   │   ├── allocation/engine.py
│   │   ├── allocation/candidate.py
│   │   ├── allocation/diagnostics.py
│   │   ├── allocation/metrics.py
│   │   ├── allocation/explanations.py
│   │   ├── allocation/policy.py
│   │   ├── allocation/repair.py
│   │   └── allocation/baselines.py
│   └── static/              (accessible local UI)
├── tests/
│   ├── conftest.py
│   ├── test_invariants.py
│   ├── test_api.py
│   └── test_baselines.py
├── .gitignore
└── README.md
```

## Current status

- Phase 0 research documents: complete (verified sources, explicit access dates).
- Phase 1 design documents: complete.
- Architecture: complete (Mermaid diagrams, domain entities, trust boundaries, failure modes, agent contracts, ADRs).
- First vertical slice: implemented and tested (CP-SAT engine, consent state machine, idempotent transitions, withdrawal/repair, baselines).
- Tests: executable invariant, API, and baseline suites present; run with `pytest`.

## Hypotheses (untested)

H1–H4 are documented in `HYPOTHESES.md` with falsification criteria. No numeric improvement is claimed until simulations are run and results recorded.

## License / acknowledgment

Research prototype. Sources accessed 2026-11-23 (dates shown in each document). See `RELATED_WORK.md` for the full source matrix.
