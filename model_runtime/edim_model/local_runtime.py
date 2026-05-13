from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]


def execute_bundle(
    bundle: Dict[str, Any],
    *,
    progress_callback: Callable[[str, float, str], None] | None = None,
) -> Tuple[str, dict, list[str]]:
    """Execute one model run bundle through the packaged runtime core.

    The public runtime process contract is black-box shaped: the backend writes
    a bundle and this package owns model execution. The implementation below
    imports the model core packaged under edim_model.core, not backend API code.
    """

    from edim_model.core.runner import run_model_synchronously  # noqa: WPS433
    from edim_model.core.schemas import RunRequest  # noqa: WPS433
    from edim_model.core.settings import Settings  # noqa: WPS433

    raw = bundle.get("runtime_settings") if isinstance(bundle.get("runtime_settings"), dict) else {}
    settings = Settings(
        calliope_root=_path(
            raw.get("calliope_root"),
            REPO_ROOT / "model_runtime" / "model_modules" / "calliope" / "Calliope-Africa-main",
        ),
        runs_dir=_path(raw.get("runs_dir"), REPO_ROOT / "outputs" / "runs"),
        config_dir=_path(raw.get("config_dir"), REPO_ROOT / "inputs"),
        dev_subset_start=str(raw.get("dev_subset_start", "2019-01-01")),
        dev_subset_end=str(raw.get("dev_subset_end", "2019-01-02")),
        analysis_subset_start=str(raw.get("analysis_subset_start", "2019-01-01")),
        analysis_subset_end=str(raw.get("analysis_subset_end", "2019-03-31")),
        dev_solver_time_limit_seconds=float(raw.get("dev_solver_time_limit_seconds", 3600.0)),
        analysis_solver_time_limit_seconds=float(raw.get("analysis_solver_time_limit_seconds", 14400.0)),
        allow_full_year=bool(raw.get("allow_full_year", True)),
        solver=str(raw.get("solver", "highs")),
        cors_allow_origins=list(raw.get("cors_allow_origins") or []),
        summary_max_generation_techs=int(raw.get("summary_max_generation_techs", 40)),
        summary_max_generation_timesteps=int(raw.get("summary_max_generation_timesteps", 240)),
        summary_max_category_rows=int(raw.get("summary_max_category_rows", 100)),
        summary_diagnostics_max_rows=int(raw.get("summary_diagnostics_max_rows", 200)),
        run_retention_days=int(raw.get("run_retention_days", 30)),
        run_max_dirs=int(raw.get("run_max_dirs", 200)),
        job_history_limit=int(raw.get("job_history_limit", 200)),
        job_dedupe_enabled=bool(raw.get("job_dedupe_enabled", True)),
        job_queue_capacity=int(raw.get("job_queue_capacity", 12)),
        development_engine=str(raw.get("development_engine", "mario")),
        mario_db_path=str(raw.get("mario_db_path", "")),
        mario_timeout_seconds=float(raw.get("mario_timeout_seconds", 120.0)),
        mario_fail_on_error=bool(raw.get("mario_fail_on_error", False)),
        frontend_dir=_optional_path(raw.get("frontend_dir")),
        runtime_config=dict(raw.get("runtime_config") or {}),
        model_runtime_mode=str(raw.get("model_runtime_mode", "subprocess")),
        model_manifest_path=_optional_path(raw.get("model_manifest_path")) or REPO_ROOT / "model_runtime" / "edim_model" / "model_manifest.json",
        dataset_manifest_path=_optional_path(raw.get("dataset_manifest_path")) or REPO_ROOT / "model_runtime" / "edim_model" / "dataset_manifest.json",
    )
    req = RunRequest(**(bundle.get("request") or {}))
    run_id, summary, warnings, _ = run_model_synchronously(
        settings,
        req,
        progress_callback=progress_callback,
        cancel_requested=None,
        request_bundle=bundle,
    )
    return run_id, summary, list(warnings or [])


def _optional_path(value: Any) -> Path | None:
    text = str(value or "").strip()
    return Path(text).expanduser().resolve() if text else None


def _path(value: Any, default: Path) -> Path:
    return _optional_path(value) or default.resolve()
