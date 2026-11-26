from __future__ import annotations

from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from . import __version__
from .config import get_settings
from .db import get_db

router = APIRouter(tags=["health"])

_BACKEND_DIR = Path(__file__).resolve().parent.parent
ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"

# Migration states that are considered healthy: the database is either at a
# head revision, or (during local development with plain create_all) the
# alembic_version table simply does not exist yet.
_HEALTHY_MIGRATION_STATUSES = {"ok", "current", "not_applicable"}


def _db_status(db: Session) -> dict[str, Any]:
    """Check database connectivity with a trivial query."""
    try:
        db.execute(text("select 1"))
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001 - report any DB failure as a health check
        return {"status": "error", "error": type(exc).__name__}


def _solver_status() -> dict[str, Any]:
    """Check that the OR-Tools CP-SAT solver can be instantiated."""
    try:
        from ortools.sat.python import cp_model  # type: ignore[import-not-found]

        solver = cp_model.CpSolver()
        return {
            "status": "ok",
            "engine": "ortools-cpsat",
            "search_workers": solver.parameters.num_search_workers,
        }
    except Exception as exc:  # noqa: BLE001 - report any solver failure as a health check
        return {"status": "error", "error": type(exc).__name__}


def _migration_status(db: Session) -> dict[str, Any]:
    """Compare the database alembic_version with the migration heads on disk."""
    try:
        engine = db.bind
        if engine is None or not inspect(engine).has_table("alembic_version"):
            return {"status": "not_applicable"}

        config = Config(str(ALEMBIC_INI))
        config.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
        script = ScriptDirectory.from_config(config)
        heads = set(script.get_heads())

        current = db.execute(text("select version_num from alembic_version limit 1")).scalar()
        if current is None:
            return {"status": "empty", "heads": sorted(heads)}
        return {
            "status": "current" if current in heads else "behind",
            "current": current,
            "heads": sorted(heads),
        }
    except Exception as exc:  # noqa: BLE001 - report any migration-check failure as a health check
        return {"status": "error", "error": type(exc).__name__}


def overall_health(db: Session) -> dict[str, Any]:
    """Aggregate every health check into a single status document."""
    checks: dict[str, dict[str, Any]] = {
        "database": _db_status(db),
        "solver": _solver_status(),
        "migrations": _migration_status(db),
    }

    degraded = any(
        check.get("status") not in _HEALTHY_MIGRATION_STATUSES for check in checks.values()
    )

    settings = get_settings()
    return {
        "status": "degraded" if degraded else "ok",
        "service": "equitask",
        "version": __version__,
        "database_url_kind": "sqlite" if settings.database_url.startswith("sqlite") else "postgresql",
        "checks": checks,
    }


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Liveness/readiness probe used by load balancers and container orchestrators.

    Returns HTTP 200 when the service is reachable; inspect the ``status`` and
    per-check fields for degradation details. Container health checks should
    treat any non-200 response as unhealthy.
    """
    return overall_health(db)
