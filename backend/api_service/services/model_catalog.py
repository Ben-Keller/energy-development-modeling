from __future__ import annotations

"""Model-owned catalog boundary for scenarios and architecture metadata.

The API exposes model selectors and graph layouts, but those concepts belong to
the packaged model runtime. This provider lets local development read the
runtime catalog through the runtime CLI while Azure deployments can replace the
implementation with a cached model-catalog service or object-storage backed
catalog without changing routers or frontend contracts.
"""

import json
import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Protocol

from ..settings import Settings


class ModelCatalogProvider(Protocol):
    def full_catalog(self, *, settings: Settings, manifest: Dict[str, Any]) -> Dict[str, Any]: ...
    def scenario_catalog(self, *, settings: Settings, manifest: Dict[str, Any]) -> Dict[str, Any]: ...
    def architecture_catalog(self, *, settings: Settings, manifest: Dict[str, Any]) -> Dict[str, Any]: ...


class RuntimeCliModelCatalogProvider(ModelCatalogProvider):
    """Read model-owned catalogs from the packaged runtime CLI."""

    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}

    def full_catalog(self, *, settings: Settings, manifest: Dict[str, Any]) -> Dict[str, Any]:
        entrypoint = [str(item) for item in (manifest.get("catalog_entrypoint") or []) if str(item)]
        if entrypoint:
            cache_key = self._catalog_cache_key(settings=settings, manifest=manifest, entrypoint=entrypoint)
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached
            payload = self._run_catalog_entrypoint(settings=settings, manifest=manifest, entrypoint=entrypoint)
            self._cache = {cache_key: payload}
            return payload
        raise RuntimeError("Model manifest must declare catalog_entrypoint for black-box catalog loading.")

    def scenario_catalog(self, *, settings: Settings, manifest: Dict[str, Any]) -> Dict[str, Any]:
        payload = self.full_catalog(settings=settings, manifest=manifest)
        catalog = payload.get("scenario_catalog")
        return catalog if isinstance(catalog, dict) else {}

    def architecture_catalog(self, *, settings: Settings, manifest: Dict[str, Any]) -> Dict[str, Any]:
        # Architecture graph metadata is a static catalog referenced by the
        # runtime manifest. Do not force scenario parsing here; model-runtime
        # catalogs can be requested independently by the UI.
        return self._load_architecture_catalog(settings=settings, manifest=manifest)

    def _run_catalog_entrypoint(
        self,
        *,
        settings: Settings,
        manifest: Dict[str, Any],
        entrypoint: list[str],
    ) -> Dict[str, Any]:
        command = list(entrypoint)
        if command and command[0] in {"python", "python3"}:
            command[0] = sys.executable
        manifest_path = Path(str(manifest.get("manifest_path") or getattr(settings, "model_manifest_path", "") or "")).expanduser()
        architecture_path = self._architecture_catalog_path(settings=settings, manifest=manifest)
        command.extend(
            [
                "--config-dir",
                str(settings.config_dir),
                "--calliope-root",
                str(settings.calliope_root),
                "--manifest",
                str(manifest_path),
            ]
        )
        if architecture_path:
            command.extend(["--architecture-catalog", str(architecture_path)])
        completed = subprocess.run(
            command,
            cwd=str(self._repo_root(settings=settings, manifest=manifest)),
            env=self._safe_env(),
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Model catalog entrypoint failed: "
                + (completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}")
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Model catalog entrypoint did not return JSON.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Model catalog entrypoint returned a non-object JSON payload.")
        return payload

    def _load_architecture_catalog(self, *, settings: Settings, manifest: Dict[str, Any]) -> Dict[str, Any]:
        path = self._architecture_catalog_path(settings=settings, manifest=manifest)
        if path and path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        architectures = [str(value) for value in (manifest.get("supported_model_architectures") or [])]
        return {
            "schemaVersion": "edim_model_architecture_catalog",
            "defaultArchitectureId": architectures[0] if architectures else "",
            "architectures": [{"id": value, "label": value.replace("-", " ").title()} for value in architectures],
        }

    def _architecture_catalog_path(self, *, settings: Settings, manifest: Dict[str, Any]) -> Path | None:
        raw = str(manifest.get("architecture_catalog_path") or "").strip()
        if raw:
            path = Path(raw).expanduser()
            if not path.is_absolute():
                path = self._repo_root(settings=settings, manifest=manifest) / path
            return path.resolve()
        return None

    def _repo_root(self, *, settings: Settings, manifest: Dict[str, Any]) -> Path:
        raw_manifest_path = str(manifest.get("manifest_path") or getattr(settings, "model_manifest_path", "") or "").strip()
        if raw_manifest_path:
            path = Path(raw_manifest_path).expanduser()
            if path.exists():
                # model_runtime/edim_model/model_manifest.json -> repo root
                return path.resolve().parents[2]
        return settings.config_dir.resolve().parent

    def _catalog_cache_key(self, *, settings: Settings, manifest: Dict[str, Any], entrypoint: list[str]) -> str:
        architecture_path = self._architecture_catalog_path(settings=settings, manifest=manifest)
        manifest_path = Path(str(manifest.get("manifest_path") or getattr(settings, "model_manifest_path", "") or "")).expanduser()
        report_json_path = settings.config_dir.resolve() / "generated" / "scenario_report_scenarios.json"
        report_csv_path = settings.config_dir.resolve() / "mario_inputs" / "scenario_report_scenarios.csv"
        payload = {
            "entrypoint": entrypoint,
            "config_dir": str(settings.config_dir.resolve()),
            "calliope_root": str(settings.calliope_root.resolve()),
            "manifest_sha256": self._file_sha256(manifest_path),
            "architecture_sha256": self._file_sha256(architecture_path),
            "scenario_report_json_sha256": self._file_sha256(report_json_path),
            "scenario_report_csv_sha256": self._file_sha256(report_csv_path),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    @staticmethod
    def _file_sha256(path: Path | None) -> str:
        if path is None:
            return ""
        path = path.expanduser()
        if not path.exists() or not path.is_file():
            return ""
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _safe_env(self) -> Dict[str, str]:
        allowed = {
            "PATH",
            "PYTHONPATH",
            "VIRTUAL_ENV",
            "HOME",
            "TMPDIR",
            "LANG",
            "LC_ALL",
            "SYSTEMROOT",
            "WINDIR",
        }
        return {key: value for key, value in os.environ.items() if key in allowed}
