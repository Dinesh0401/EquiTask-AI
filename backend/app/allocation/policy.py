from __future__ import annotations

from ortools.sat.python import cp_model

from .. import __version__

SOLVER_VERSION = "ortools-cpsat-dynamic"
POLICY_VERSION = "v0.1.1"

# Adaptive time limits based on problem size (volunteers * tasks).
# Larger problems get proportionally more time but are capped.
BASE_TIME_LIMIT = 5.0
TIME_PER_PROBLEM_UNIT = 0.001  # seconds per (volunteer * task) pair
MAX_TIME_LIMIT = 30.0
MIN_TIME_LIMIT = 1.0


def adaptive_time_limit(num_variables: int) -> float:
    """Compute an adaptive solver time limit based on problem size.

    Ensures small problems solve quickly while giving larger problems
    enough time without unbounded waits.
    """
    limit = BASE_TIME_LIMIT + num_variables * TIME_PER_PROBLEM_UNIT
    return max(MIN_TIME_LIMIT, min(MAX_TIME_LIMIT, limit))


def configure_solver(problem_time_limit: float) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = problem_time_limit
    solver.parameters.num_search_workers = 1  # deterministic output for research comparisons
    solver.parameters.random_seed = 1
    return solver


def version_metadata() -> tuple[str, str]:
    return POLICY_VERSION, f"{SOLVER_VERSION}/{__version__}"
