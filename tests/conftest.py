"""Pytest fixtures for EquiTask AI tests.

Uses an isolated file-based SQLite database for all tests so that development
and production data are never touched, modified, or dropped.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.main import app
from app.db import Base, SessionLocal
from app.config import get_settings


# Isolated test database: file-based SQLite in the project root, never the
# development/production database (equitask.db).
TEST_DATABASE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tests", "test_equitask.db"))
TEST_DATABASE_URL = f"sqlite:///{TEST_DATABASE_PATH}"
_test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@pytest.fixture(scope="session", autouse=True)
def create_test_schema() -> None:
    """Create all tables in the isolated test database once per session."""
    # Remove any stale test database from a previous run.
    if os.path.exists(TEST_DATABASE_PATH):
        os.remove(TEST_DATABASE_PATH)
    Base.metadata.create_all(bind=_test_engine)
    yield
    Base.metadata.drop_all(bind=_test_engine)
    # Do not delete the file while connections may still be open on Windows.


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture()
def db_session() -> Session:
    """Provide a transactional session against the isolated test database."""
    connection = _test_engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db_session: Session) -> TestClient:
    """FastAPI TestClient with dependency override for the DB session."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[__import__("app.db", fromlist=["get_db"]).get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def make_task_input(task_id: str, effort_hours: float = 4.0, skill: str = "translation", proficiency: int = 50) -> dict:
    now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    return {
        "id": task_id,
        "organization_id": "o1",
        "required_skills": [{"skill": skill, "min_proficiency": proficiency, "mandatory": True}],
        "effort_hours": effort_hours,
        "start_utc": now.isoformat(),
        "end_utc": (now + timedelta(days=2)).isoformat(),
        "deadline_utc": (now + timedelta(days=3)).isoformat(),
        "max_assignees": 1,
        "value": 100,
        "acceptance_criteria_present": True,
        "organization_verified": True,
    }


def make_volunteer_input(volunteer_id: str, capacity_hours: float = 10.0, skills=None, availability_state="KNOWN_TRUE") -> dict:
    return {
        "id": volunteer_id,
        "capacity_hours": capacity_hours,
        "committed_hours": 0.0,
        "skills": skills or [{"skill": "translation", "proficiency": 80, "state": "KNOWN_TRUE"}],
        "availability_state": availability_state,
        "languages": ["en"],
        "preference_by_task": {},
        "consent_by_task": {},
        "contact_permitted": True,
    }
