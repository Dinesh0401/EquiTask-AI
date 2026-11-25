"""Experiment runner for Phase 2 simulation experiments.

Executes multi-seed comparisons of allocation baselines under identical
scenarios, records metrics, and reports paired comparisons. No algorithmic
novelty or superiority is claimed; output is purely descriptive.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from typing import Any

from .generator import ScenarioConfig, generate_scenario, scenario_to_allocation_problem
from .metrics import Metrics, compute_run_metrics, aggregate_metrics
from .baselines import BaselineRunner


def _git_commit_hash() -> str | None:
    """Best-effort code commit hash for reproducibility tracking."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


class ExperimentRunner:
    """Runs paired multi-seed experiments comparing allocation baselines."""

    def __init__(
        self,
        seeds: list[int] | None = None,
        num_volunteers: int = 100,
        num_tasks: int = 60,
        num_organizations: int = 5,
        baselines: list[str] | None = None,
    ):
        self.seeds = seeds or [7, 42, 123, 2026, 999]
        self.num_volunteers = num_volunteers
        self.num_tasks = num_tasks
        self.num_organizations = num_organizations
        self.baselines = baselines or [
            "random_feasible",
            "greedy_skill_match",
            "cp_sat_efficiency",
            "cp_sat_fairness",
            "proposed_uncertainty_aware",
        ]
        self.commit_hash = _git_commit_hash()

    def _make_config(self, seed: int) -> ScenarioConfig:
        return ScenarioConfig(
            seed=seed,
            num_volunteers=self.num_volunteers,
            num_tasks=self.num_tasks,
            num_organizations=self.num_organizations,
        )

    def run_single(
        self,
        baseline_name: str,
        seed: int,
        demand_profile: str = "balanced",
        skill_distribution: str = "uniform",
        missingness_rate: float = 0.2,
    ) -> dict[str, Any]:
        """Run one baseline on one seeded scenario."""
        config = self._make_config(seed)
        config.demand_profile = demand_profile
        config.skill_distribution = skill_distribution
        config.missingness_rate = missingness_rate

        scenario = generate_scenario(config)
        problem_dict = scenario_to_allocation_problem(scenario)

        from app.schemas import AllocationProblem

        problem = AllocationProblem(**problem_dict)

        runner = BaselineRunner(baseline_name)
        result = runner.run(problem)

        metrics = compute_run_metrics(result, scenario.volunteers, scenario.tasks)

        return {
            "baseline": baseline_name,
            "seed": seed,
            "config": {
                "demand_profile": demand_profile,
                "skill_distribution": skill_distribution,
                "missingness_rate": missingness_rate,
                "num_volunteers": self.num_volunteers,
                "num_tasks": self.num_tasks,
            },
            "metrics": metrics.to_dict(),
        }

    def run_suite(
        self,
        demand_profile: str = "balanced",
        skill_distribution: str = "uniform",
        missingness_rate: float = 0.2,
    ) -> dict[str, Any]:
        """Run all baselines across all seeds. Returns aggregated results."""
        results: list[dict[str, Any]] = []

        for baseline_name in self.baselines:
            baseline_results: list[dict[str, Any]] = []
            for seed in self.seeds:
                run = self.run_single(
                    baseline_name,
                    seed,
                    demand_profile=demand_profile,
                    skill_distribution=skill_distribution,
                    missingness_rate=missingness_rate,
                )
                baseline_results.append(run)
                results.append(run)

            # Aggregate per baseline.
            from .metrics import Metrics

            run_metrics = []
            for r in baseline_results:
                m = Metrics(**r["metrics"])
                run_metrics.append(m)
            aggregate = aggregate_metrics(run_metrics)

            # Store aggregate alongside per-run results.
            for r in baseline_results:
                r["aggregate"] = aggregate

        return {
            "commit_hash": self.commit_hash,
            "config": {
                "demand_profile": demand_profile,
                "skill_distribution": skill_distribution,
                "missingness_rate": missingness_rate,
                "num_volunteers": self.num_volunteers,
                "num_tasks": self.num_tasks,
                "num_organizations": self.num_organizations,
                "seeds": self.seeds,
                "baselines": self.baselines,
            },
            "results": results,
        }

    def save(self, results: dict[str, Any], path: str) -> None:
        """Write experiment results to a JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
