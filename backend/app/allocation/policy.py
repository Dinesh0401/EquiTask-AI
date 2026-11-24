from __future__ import annotations

from ortools.sat.python import cp_model

from .. import __version__

SOLVER_VERSION = "ortools-cpsat-dynamic"
POLICY_VERSION = "v0.1"


def configure_solver(problem_time_limit: float) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = problem_time_limit
    solver.parameters.num_search_workers = 1  # deterministic output for research comparisons
    solver.parameters.random_seed = 1
    return solver


def version_metadata() -> tuple[str, str]:
    return POLICY_VERSION, f"{SOLVER_VERSION}/{__version__}"
