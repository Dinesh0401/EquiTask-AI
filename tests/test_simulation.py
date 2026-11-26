"""Tests for the Phase 2 simulation framework.

Tests reproducibility, determinism, and metric computation. No algorithmic
superiority is claimed; these tests verify the simulation instrument works.
"""

from __future__ import annotations

from simulations.generator import ScenarioConfig, generate_scenario, scenario_to_allocation_problem
from simulations.metrics import Metrics, compute_run_metrics, aggregate_metrics
from simulations.baselines import BaselineRunner
from simulations.experiment import ExperimentRunner

from app.schemas import AllocationProblem
from app.allocation.baselines import greedy_skill_match, random_feasible, cp_sat_efficiency, cp_sat_fairness
from app.allocation import allocate


def test_scenario_is_deterministic_given_seed():
    """Same seed produces identical scenario."""
    c1 = ScenarioConfig(seed=42, num_volunteers=20, num_tasks=6)
    c2 = ScenarioConfig(seed=42, num_volunteers=20, num_tasks=6)
    s1 = generate_scenario(c1)
    s2 = generate_scenario(c2)
    assert len(s1.volunteers) == len(s2.volunteers)
    assert len(s1.tasks) == len(s2.tasks)
    assert s1.volunteers[0].id == s2.volunteers[0].id
    assert s1.volunteers[0].skills == s2.volunteers[0].skills


def test_scenario_differs_by_seed():
    """Different seeds produce different scenarios."""
    s1 = generate_scenario(ScenarioConfig(seed=1, num_volunteers=10, num_tasks=4))
    s2 = generate_scenario(ScenarioConfig(seed=2, num_volunteers=10, num_tasks=4))
    assert s1.volunteers[0].capacity_hours != s2.volunteers[0].capacity_hours or \
           s1.volunteers[0].skills != s2.volunteers[0].skills


def test_scenario_to_allocation_problem():
    """Scenario converts to a valid AllocationProblem."""
    scenario = generate_scenario(ScenarioConfig(seed=7, num_volunteers=10, num_tasks=4))
    problem_dict = scenario_to_allocation_problem(scenario)
    problem = AllocationProblem(**problem_dict)
    assert len(problem.volunteers) == 10
    assert len(problem.tasks) == 4


def test_all_baselines_run_on_scenario():
    """All registered baselines execute without crashing on a small scenario."""
    scenario = generate_scenario(ScenarioConfig(seed=7, num_volunteers=10, num_tasks=4))
    problem_dict = scenario_to_allocation_problem(scenario)
    problem = AllocationProblem(**problem_dict)

    for name in ["random_feasible", "greedy_skill_match", "cp_sat_efficiency", "cp_sat_fairness", "proposed_uncertainty_aware"]:
        runner = BaselineRunner(name)
        result = runner.run(problem)
        assert result is not None
        assert hasattr(result, "status")
        assert hasattr(result, "proposals")


def test_baselines_produce_different_or_same_results():
    """Baselines may agree or disagree; both are valid outcomes."""
    scenario = generate_scenario(ScenarioConfig(seed=7, num_volunteers=10, num_tasks=4))
    problem_dict = scenario_to_allocation_problem(scenario)
    problem = AllocationProblem(**problem_dict)

    greedy = BaselineRunner("greedy_skill_match").run(problem)
    fair = BaselineRunner("cp_sat_fairness").run(problem)
    # Both should produce a status string.
    assert greedy.status in ("OPTIMAL_PROPOSALS", "FEASIBLE_PROPOSALS", "NO_FEASIBLE_PROPOSAL")
    assert fair.status in ("OPTIMAL_PROPOSALS", "FEASIBLE_PROPOSALS", "NO_FEASIBLE_PROPOSAL")


def test_metrics_aggregation():
    """aggregate_metrics handles empty and populated inputs."""
    empty = aggregate_metrics([])
    assert empty == {}

    m1 = Metrics(
        feasible_allocation_rate=1.0,
        expected_completion_value=100.0,
        workload_unfairness=10.0,
        solver_runtime_ms=50.0,
        solver_status="OPTIMAL_PROPOSALS",
    )
    m2 = Metrics(
        feasible_allocation_rate=1.0,
        expected_completion_value=120.0,
        workload_unfairness=5.0,
        solver_runtime_ms=80.0,
        solver_status="OPTIMAL_PROPOSALS",
    )
    agg = aggregate_metrics([m1, m2])
    assert agg["n_runs"] == 2
    assert agg["feasible_allocation_rate"]["mean"] == 1.0
    assert agg["expected_completion_value"]["mean"] == 110.0
    assert agg["workload_unfairness"]["mean"] == 7.5
    assert agg["solver_runtime_ms"]["min"] == 50.0
    assert agg["solver_runtime_ms"]["max"] == 80.0


def test_experiment_runner_init():
    """ExperimentRunner initializes with defaults."""
    runner = ExperimentRunner(seeds=[7, 42])
    assert runner.seeds == [7, 42]
    assert len(runner.baselines) == 5
    assert "proposed_uncertainty_aware" in runner.baselines


def test_experiment_run_suite_small():
    """Full experiment suite runs on a small configuration."""
    runner = ExperimentRunner(
        seeds=[7, 42],
        num_volunteers=20,
        num_tasks=6,
        num_organizations=3,
        baselines=["random_feasible", "greedy_skill_match", "cp_sat_fairness", "proposed_uncertainty_aware"],
    )
    results = runner.run_suite(
        demand_profile="balanced",
        skill_distribution="uniform",
        missingness_rate=0.2,
    )
    assert "commit_hash" in results
    assert "config" in results
    assert "results" in results
    assert results["config"]["seeds"] == [7, 42]
    # Each baseline should have 2 runs (one per seed).
    for baseline in runner.baselines:
        baseline_runs = [r for r in results["results"] if r["baseline"] == baseline]
        assert len(baseline_runs) == 2
