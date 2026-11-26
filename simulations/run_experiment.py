"""CLI entry point for Phase 2 simulation experiments.

Usage:
    python -m simulations.run_experiment \
        --seeds 7 42 123 --baselines random_feasible greedy_skill_match \
        --output results.json
"""

from __future__ import annotations

import argparse
import sys

from .experiment import ExperimentRunner


def main() -> int:
    parser = argparse.ArgumentParser(description="Run EquiTask AI simulation experiments")
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=[7, 42, 123, 2026, 999],
        help="Random seeds for paired experiments",
    )
    parser.add_argument(
        "--baselines",
        type=str,
        nargs="+",
        default=[
            "random_feasible",
            "greedy_skill_match",
            "cp_sat_efficiency",
            "cp_sat_fairness",
            "proposed_uncertainty_aware",
        ],
        help="Baselines to compare",
    )
    parser.add_argument(
        "--num-volunteers",
        type=int,
        default=100,
        help="Number of volunteers per scenario",
    )
    parser.add_argument(
        "--num-tasks",
        type=int,
        default=60,
        help="Number of tasks per scenario",
    )
    parser.add_argument(
        "--num-organizations",
        type=int,
        default=5,
        help="Number of organizations",
    )
    parser.add_argument(
        "--demand-profile",
        type=str,
        default="balanced",
        choices=["balanced", "overloaded", "bursty"],
    )
    parser.add_argument(
        "--skill-distribution",
        type=str,
        default="uniform",
        choices=["uniform", "skewed", "scarce"],
    )
    parser.add_argument(
        "--missingness-rate",
        type=float,
        default=0.2,
        help="Fraction of fields left UNKNOWN",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="simulations/results.json",
        help="Output JSON file path",
    )

    args = parser.parse_args()

    runner = ExperimentRunner(
        seeds=args.seeds,
        num_volunteers=args.num_volunteers,
        num_tasks=args.num_tasks,
        num_organizations=args.num_organizations,
        baselines=args.baselines,
    )

    results = runner.run_suite(
        demand_profile=args.demand_profile,
        skill_distribution=args.skill_distribution,
        missingness_rate=args.missingness_rate,
    )

    runner.save(results, args.output)
    print(f"Experiment complete. Results saved to {args.output}")
    print(f"Commit hash: {results.get('commit_hash')}")
    print(f"Baselines: {results['config']['baselines']}")
    print(f"Seeds: {results['config']['seeds']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
