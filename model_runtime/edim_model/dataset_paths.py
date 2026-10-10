from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

_DATASET_PATHS: Dict[str, str] = {}


def set_dataset_manifest(manifest: Any) -> None:
    _DATASET_PATHS.clear()
    datasets = manifest.get("datasets") if isinstance(manifest, dict) else None
    if not isinstance(datasets, list):
        return
    for row in datasets:
        if not isinstance(row, dict):
            continue
        dataset_id = str(row.get("id") or "").strip()
        path = str(row.get("path") or "").strip()
        if dataset_id and path:
            _DATASET_PATHS[dataset_id] = path


def dataset_path_override(dataset_id: str) -> Optional[Path]:
    override = _DATASET_PATHS.get(str(dataset_id or "").strip())
    if not override:
        return None
    candidate = Path(override)
    return candidate if candidate.exists() else None


def dataset_path(dataset_id: str, fallback: Path) -> Path:
    return dataset_path_override(dataset_id) or Path(fallback)
