from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List


_DOTENV_LOADED = False


def load_local_env(repo_root: Path | None = None) -> None:
    """Load local .env values without adding a dependency or overriding the process env."""
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    root = repo_root or Path(__file__).resolve().parents[2]
    env_path = root / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = raw_value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _load_runtime_config(repo_root: Path) -> dict:
    load_local_env(repo_root)
    raw_path = os.getenv("EDIM_RUNTIME_CONFIG", "").strip()
    config_path = Path(raw_path).expanduser().resolve() if raw_path else repo_root / "inputs" / "runtime_config.json"
    if not config_path.exists():
        return {}
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _cfg(config: dict, path: list[str], default: Any = None) -> Any:
    node: Any = config
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def _resolve_path(repo_root: Path, value: str | Path | None, default: Path) -> Path:
    if not value:
        return default.resolve()
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


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


def _config_list(value: Any, default: List[str]) -> List[str]:
    if isinstance(value, list):
        values = [str(item).strip() for item in value if str(item).strip()]
        return values or default
    if isinstance(value, str):
        values = [item.strip() for item in value.split(",") if item.strip()]
        return values or default
    return default


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
    frontend_dir: Path | None = None
    runtime_config: dict | None = None


def get_settings() -> Settings:
    repo_root = Path(__file__).resolve().parents[2]
    runtime_config = _load_runtime_config(repo_root)

    candidates = [
        repo_root / "Calliope-Africa-main",
        repo_root.parent / "Calliope-Africa-main",
        repo_root / "calliope-africa",
        repo_root.parent / "calliope-africa",
    ]
    existing_calliope = next((p for p in candidates if p.exists()), candidates[0])
    calliope_root = _resolve_path(
        repo_root,
        os.getenv("EDIM_CALLIOPE_ROOT") or _cfg(runtime_config, ["paths", "calliope_root"]),
        existing_calliope,
    )
    runs_dir = _resolve_path(
        repo_root,
        os.getenv("EDIM_RUNS_DIR") or _cfg(runtime_config, ["paths", "runs_dir"]),
        repo_root / "outputs" / "runs",
    )
    config_dir = _resolve_path(
        repo_root,
        os.getenv("EDIM_CONFIG_DIR") or _cfg(runtime_config, ["paths", "config_dir"]),
        repo_root / "inputs",
    )
    frontend_dir = _resolve_path(
        repo_root,
        os.getenv("EDIM_FRONTEND_DIR") or _cfg(runtime_config, ["paths", "frontend_dir"]),
        repo_root / "frontend",
    )
    solver = (
        os.getenv("EDIM_SOLVER")
        or str(_cfg(runtime_config, ["runtime", "solver"], "highs"))
        or "highs"
    ).strip() or "highs"

    cors_allow_origins_default = _config_list(
        _cfg(runtime_config, ["runtime", "cors_allow_origins"]),
        ["http://localhost:8000", "http://127.0.0.1:8000"],
    )
    cors_allow_origins = _env_csv("EDIM_CORS_ALLOW_ORIGINS", cors_allow_origins_default)

    return Settings(
        calliope_root=calliope_root,
        runs_dir=runs_dir,
        config_dir=config_dir,
        dev_subset_start=os.getenv("EDIM_DEV_SUBSET_START", str(_cfg(runtime_config, ["runtime", "dev_subset_start"], "2019-01-01"))),
        dev_subset_end=os.getenv("EDIM_DEV_SUBSET_END", str(_cfg(runtime_config, ["runtime", "dev_subset_end"], "2019-01-02"))),
        analysis_subset_start=os.getenv("EDIM_ANALYSIS_SUBSET_START", str(_cfg(runtime_config, ["runtime", "analysis_subset_start"], "2019-01-01"))),
        analysis_subset_end=os.getenv("EDIM_ANALYSIS_SUBSET_END", str(_cfg(runtime_config, ["runtime", "analysis_subset_end"], "2019-03-31"))),
        dev_solver_time_limit_seconds=_env_float("EDIM_DEV_SOLVER_TIME_LIMIT_SECONDS", float(_cfg(runtime_config, ["runtime", "dev_solver_time_limit_seconds"], 3600.0)), minimum=1.0),
        analysis_solver_time_limit_seconds=_env_float("EDIM_ANALYSIS_SOLVER_TIME_LIMIT_SECONDS", float(_cfg(runtime_config, ["runtime", "analysis_solver_time_limit_seconds"], 14400.0)), minimum=1.0),
        allow_full_year=_env_bool("EDIM_ALLOW_FULL_YEAR", bool(_cfg(runtime_config, ["runtime", "allow_full_year"], True))),
        solver=solver,
        cors_allow_origins=cors_allow_origins,
        summary_max_generation_techs=_env_int("EDIM_SUMMARY_MAX_GENERATION_TECHS", int(_cfg(runtime_config, ["summary", "max_generation_techs"], 40))),
        summary_max_generation_timesteps=_env_int("EDIM_SUMMARY_MAX_GENERATION_TIMESTEPS", int(_cfg(runtime_config, ["summary", "max_generation_timesteps"], 240))),
        summary_max_category_rows=_env_int("EDIM_SUMMARY_MAX_CATEGORY_ROWS", int(_cfg(runtime_config, ["summary", "max_category_rows"], 100))),
        summary_diagnostics_max_rows=_env_int("EDIM_SUMMARY_DIAGNOSTICS_MAX_ROWS", int(_cfg(runtime_config, ["summary", "diagnostics_max_rows"], 200))),
        run_retention_days=_env_int("EDIM_RUN_RETENTION_DAYS", int(_cfg(runtime_config, ["runs", "retention_days"], 30)), minimum=0),
        run_max_dirs=_env_int("EDIM_RUN_MAX_DIRS", int(_cfg(runtime_config, ["runs", "max_dirs"], 200)), minimum=0),
        job_history_limit=_env_int("EDIM_JOB_HISTORY_LIMIT", int(_cfg(runtime_config, ["jobs", "history_limit"], 200))),
        job_dedupe_enabled=_env_bool("EDIM_JOB_DEDUPE_ENABLED", bool(_cfg(runtime_config, ["jobs", "dedupe_enabled"], True))),
        job_queue_capacity=_env_int("EDIM_JOB_QUEUE_CAPACITY", int(_cfg(runtime_config, ["jobs", "queue_capacity"], 200))),
        development_engine=(os.getenv("EDIM_DEVELOPMENT_ENGINE", str(_cfg(runtime_config, ["development_engine", "engine"], "mario"))) or "mario").strip().lower(),
        mario_db_path=(os.getenv("EDIM_MARIO_DB_PATH", str(_cfg(runtime_config, ["development_engine", "mario_db_path"], ""))) or "").strip(),
        mario_timeout_seconds=_env_float("EDIM_MARIO_TIMEOUT_SECONDS", float(_cfg(runtime_config, ["development_engine", "mario_timeout_seconds"], 120.0)), minimum=1.0),
        mario_fail_on_error=_env_bool("EDIM_MARIO_FAIL_ON_ERROR", bool(_cfg(runtime_config, ["development_engine", "mario_fail_on_error"], False))),
        frontend_dir=frontend_dir,
        runtime_config=runtime_config,
    )
