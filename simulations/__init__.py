"""EquiTask AI Phase 2 simulation package.

Reproducible experiments for comparing volunteer allocation methods under
conflicting constraints and incomplete information.
"""

from .generator import Scenario, generate_scenario
from .metrics import Metrics
from .baselines import BaselineRunner
from .experiment import ExperimentRunner

__all__ = [
    "Scenario",
    "generate_scenario",
    "Metrics",
    "BaselineRunner",
    "ExperimentRunner",
]
