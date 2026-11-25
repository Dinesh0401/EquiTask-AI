"""Pytest fixtures for EquiTask AI tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.main import app
from app.db import SessionLocal, engine as app_engine, Base
from app.config import get_settings


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session", autouse=True)
def create_test_schema() -> None:
    """Create all tables in the test database once per session."""
    Base.metadata.create_all(bind=app_engine)
    yield
    Base.metadata.drop_all(bind=app_engine)


@pytest.fixture()
def db_session() -> Session:
    """Provide a transactional SQLite session for each test."""
    connection = app_engine.connect()
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
