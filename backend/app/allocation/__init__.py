"""Deterministic allocation engine."""

from .engine import allocate
from .repair import build_repair_plan

__all__ = ["allocate", "build_repair_plan"]
