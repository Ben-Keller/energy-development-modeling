from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return max(parsed, minimum)


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        parsed = float(raw)
    except ValueError:
        return default
    return max(parsed, minimum)


def _env_csv(name: str, default: List[str]) -> List[str]:
    raw = os.getenv(name)
    if raw is None:
        return default
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or default


@dataclass(frozen=True)
class Settings:
    calliope_root: Path
    runs_dir: Path
    config_dir: Path

    dev_subset_start: str
    dev_subset_end: str
    analysis_subset_start: str
    analysis_subset_end: str
    dev_solver_time_limit_seconds: float
    analysis_solver_time_limit_seconds: float
    allow_full_year: bool
    solver: str

    cors_allow_origins: List[str]

    summary_max_generation_techs: int
    summary_max_generation_timesteps: int
    summary_max_category_rows: int
    summary_diagnostics_max_rows: int

    run_retention_days: int
    run_max_dirs: int

    job_history_limit: int
    job_dedupe_enabled: bool
    job_queue_capacity: int

    development_engine: str
    mario_db_path: str
    mario_timeout_seconds: float
    mario_fail_on_error: bool


def get_settings() -> Settings:
    env_calliope_root = os.getenv("EDIM_CALLIOPE_ROOT")
    if env_calliope_root:
        calliope_root = Path(env_calliope_root).resolve()
    else:
        candidates = [
            Path("./Calliope-Africa-main"),
            Path("../Calliope-Africa-main"),
            Path("./calliope-africa"),
            Path("../calliope-africa"),
        ]
        existing = next((p for p in candidates if p.exists()), candidates[0])
        calliope_root = existing.resolve()

    env_runs_dir = os.getenv("EDIM_RUNS_DIR")
    if env_runs_dir:
        runs_dir = Path(env_runs_dir).resolve()
    else:
        runs_dir = Path("../outputs/runs").resolve()

    env_config_dir = os.getenv("EDIM_CONFIG_DIR")
    if env_config_dir:
        config_dir = Path(env_config_dir).resolve()
    else:
        config_dir = Path("../inputs").resolve()
    solver = (os.getenv("EDIM_SOLVER", "highs") or "highs").strip() or "highs"

    cors_allow_origins = _env_csv(
        "EDIM_CORS_ALLOW_ORIGINS",
        ["http://localhost:8000", "http://127.0.0.1:8000"],
    )

    return Settings(
        calliope_root=calliope_root,
        runs_dir=runs_dir,
        config_dir=config_dir,
        dev_subset_start=os.getenv("EDIM_DEV_SUBSET_START", "2019-01-01"),
        dev_subset_end=os.getenv("EDIM_DEV_SUBSET_END", "2019-01-02"),
        analysis_subset_start=os.getenv("EDIM_ANALYSIS_SUBSET_START", "2019-01-01"),
        analysis_subset_end=os.getenv("EDIM_ANALYSIS_SUBSET_END", "2019-03-31"),
        dev_solver_time_limit_seconds=_env_float("EDIM_DEV_SOLVER_TIME_LIMIT_SECONDS", 3600.0, minimum=1.0),
        analysis_solver_time_limit_seconds=_env_float("EDIM_ANALYSIS_SOLVER_TIME_LIMIT_SECONDS", 14400.0, minimum=1.0),
        allow_full_year=_env_bool("EDIM_ALLOW_FULL_YEAR", True),
        solver=solver,
        cors_allow_origins=cors_allow_origins,
        summary_max_generation_techs=_env_int("EDIM_SUMMARY_MAX_GENERATION_TECHS", 40),
        summary_max_generation_timesteps=_env_int("EDIM_SUMMARY_MAX_GENERATION_TIMESTEPS", 240),
        summary_max_category_rows=_env_int("EDIM_SUMMARY_MAX_CATEGORY_ROWS", 100),
        summary_diagnostics_max_rows=_env_int("EDIM_SUMMARY_DIAGNOSTICS_MAX_ROWS", 200),
        run_retention_days=_env_int("EDIM_RUN_RETENTION_DAYS", 30, minimum=0),
        run_max_dirs=_env_int("EDIM_RUN_MAX_DIRS", 200, minimum=0),
        job_history_limit=_env_int("EDIM_JOB_HISTORY_LIMIT", 200),
        job_dedupe_enabled=_env_bool("EDIM_JOB_DEDUPE_ENABLED", True),
        job_queue_capacity=_env_int("EDIM_JOB_QUEUE_CAPACITY", 200),
        development_engine=(os.getenv("EDIM_DEVELOPMENT_ENGINE", "mario") or "mario").strip().lower(),
        mario_db_path=(os.getenv("EDIM_MARIO_DB_PATH", "") or "").strip(),
        mario_timeout_seconds=_env_float("EDIM_MARIO_TIMEOUT_SECONDS", 120.0, minimum=1.0),
        mario_fail_on_error=_env_bool("EDIM_MARIO_FAIL_ON_ERROR", False),
    )
