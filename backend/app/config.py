from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "EquiTask AI"
    database_url: str = "sqlite:///./equitask.db"
    secret_key: str = "dev-only-change-me-before-any-real-deployment"
    token_ttl_minutes: int = 60 * 12
    password_iterations: int = 210_000
    stale_field_hours: int = 24 * 14
    max_questions_per_round: int = 3
    solver_time_limit_seconds: float = 5.0
    max_problem_volunteers: int = 200
    max_problem_tasks: int = 200
    request_rate_limit: int = 120
    enable_demo_seed: bool = True

    model_config = SettingsConfigDict(env_prefix="EQUITASK_", env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
