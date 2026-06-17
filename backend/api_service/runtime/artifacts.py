from __future__ import annotations

import csv
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here.parents[3], Path.cwd()):
        if (candidate / "inputs" / "runtime_config.json").exists():
            return candidate
    return here.parents[3]


def _default_artifact_manifest() -> Dict[str, Dict[str, Any]]:
    path = _repo_root() / "inputs" / "runtime_config.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    manifest = ((payload.get("artifacts") or {}).get("manifest") or {}) if isinstance(payload, dict) else {}
    if isinstance(manifest, dict) and manifest:
        return {str(key): dict(value) for key, value in manifest.items() if isinstance(value, dict)}
    return {
        "request_bundle_json": {"path": "inputs/request_bundle.json", "producer_stage": "scenario_prepare", "kind": "input_snapshot"},
        "runtime_events_jsonl": {"path": "logs/runtime_events.jsonl", "producer_stage": "runtime", "kind": "log"},
        "summary_json": {"path": "artifacts/final/summary.json", "producer_stage": "build_integrated", "kind": "final", "required_for_report": True},
        "integrated_results_json": {"path": "artifacts/final/integrated_results.json", "producer_stage": "build_integrated", "kind": "final", "required_for_report": True},
        "development_impacts_json": {"path": "artifacts/final/development_impacts.json", "producer_stage": "development", "kind": "final", "required_for_report": True},
        "results_csv": {"path": "artifacts/final/results.csv", "producer_stage": "write_artifacts", "kind": "final", "required_for_report": True},
        "report_markdown": {"path": "exports/report.md", "producer_stage": "build_integrated", "kind": "export"},
        "exchange_bundle_zip": {"path": "exports/exchange_bundle.zip", "producer_stage": "build_integrated", "kind": "export"},
    }


@dataclass(frozen=True)
class ArtifactManifestEntry:
    artifact_id: str
    path: str
    producer_stage: str
    kind: str
    retain_on_success: bool = True
    retain_on_failure: bool = True
    embed_in_final_results: bool = False
    embed_in_summary: bool = False
    include_in_project_bundle: bool = True
    expose_download: bool = True
    required_for_report: bool = False
    drop_after_consumed_by: str = ""


@dataclass(frozen=True)
class ArtifactDescriptorRecord:
    artifact_id: str
    label: str
    kind: str
    producer_stage: str
    path: str
    download_url: str
    include_in_project_bundle: bool
    expose_download: bool
    embed_in_summary: bool
    embed_in_final_results: bool
    required_for_report: bool
    size_bytes: int | None = None
    media_type: str = "application/octet-stream"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "label": self.label,
            "kind": self.kind,
            "producer_stage": self.producer_stage,
            "path": self.path,
            "download_url": self.download_url,
            "include_in_project_bundle": self.include_in_project_bundle,
            "expose_download": self.expose_download,
            "embed_in_summary": self.embed_in_summary,
            "embed_in_final_results": self.embed_in_final_results,
            "required_for_report": self.required_for_report,
            "size_bytes": self.size_bytes,
            "media_type": self.media_type,
        }


@dataclass(frozen=True)
class RunLayout:
    run_dir: Path
    inputs_dir: Path
    work_dir: Path
    artifacts_dir: Path
    logs_dir: Path
    exports_dir: Path


def build_run_layout(run_dir: Path) -> RunLayout:
    run_dir = run_dir.resolve()
    paths = {
        "inputs_dir": run_dir / "inputs",
        "work_dir": run_dir / "work",
        "artifacts_dir": run_dir / "artifacts",
        "logs_dir": run_dir / "logs",
        "exports_dir": run_dir / "exports",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return RunLayout(run_dir=run_dir, **paths)


def _artifact_overrides(config_or_policy: Dict[str, Any] | None) -> Dict[str, Any]:
    cfg = config_or_policy if isinstance(config_or_policy, dict) else {}
    if isinstance(cfg.get("manifest"), dict):
        return cfg["manifest"]
    artifacts = cfg.get("artifacts") if isinstance(cfg.get("artifacts"), dict) else {}
    manifest = artifacts.get("manifest") if isinstance(artifacts, dict) else {}
    return manifest if isinstance(manifest, dict) else {}


def load_artifact_manifest(config_or_policy: Dict[str, Any] | None) -> Dict[str, ArtifactManifestEntry]:
    merged = _default_artifact_manifest()
    for artifact_id, override in _artifact_overrides(config_or_policy).items():
        base = dict(merged.get(str(artifact_id), {}))
        if isinstance(override, dict):
            base.update(override)
        merged[str(artifact_id)] = base

    manifest: Dict[str, ArtifactManifestEntry] = {}
    for artifact_id, raw in merged.items():
        if not isinstance(raw, dict):
            continue
        manifest[artifact_id] = ArtifactManifestEntry(
            artifact_id=artifact_id,
            path=str(raw.get("path", "")).strip(),
            producer_stage=str(raw.get("producer_stage", "")).strip(),
            kind=str(raw.get("kind", "intermediate")).strip(),
            retain_on_success=bool(raw.get("retain_on_success", True)),
            retain_on_failure=bool(raw.get("retain_on_failure", True)),
            embed_in_final_results=bool(raw.get("embed_in_final_results", False)),
            embed_in_summary=bool(raw.get("embed_in_summary", False)),
            include_in_project_bundle=bool(raw.get("include_in_project_bundle", True)),
            expose_download=bool(raw.get("expose_download", True)),
            required_for_report=bool(raw.get("required_for_report", False)),
            drop_after_consumed_by=str(raw.get("drop_after_consumed_by", "")).strip(),
        )
    return manifest


def _label_from_artifact_id(artifact_id: str) -> str:
    return artifact_id.replace("_", " ").strip().title()


class ArtifactRegistry:
    def __init__(self, run_id: str, run_dir: Path, runtime_config: Dict[str, Any] | None = None):
        self.run_id = run_id
        self.layout = build_run_layout(run_dir)
        self.manifest = load_artifact_manifest(runtime_config)
        self._records: Dict[str, ArtifactDescriptorRecord] = {}

    @property
    def run_dir(self) -> Path:
        return self.layout.run_dir

    def path_for(self, artifact_id: str) -> Path:
        entry = self.manifest[artifact_id]
        path = (self.run_dir / entry.path).resolve()
        if self.run_dir.resolve() not in path.parents and path != self.run_dir.resolve():
            raise ValueError(f"Artifact path escapes run directory for '{artifact_id}'.")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def register_existing(self, artifact_id: str, path: Path | None = None) -> ArtifactDescriptorRecord:
        entry = self.manifest[artifact_id]
        target = path.resolve() if path is not None else self.path_for(artifact_id)
        media_type, _ = mimetypes.guess_type(target.name)
        record = ArtifactDescriptorRecord(
            artifact_id=artifact_id,
            label=_label_from_artifact_id(artifact_id),
            kind=entry.kind,
            producer_stage=entry.producer_stage,
            path=str(target.relative_to(self.run_dir)),
            download_url=f"/api/runs/{self.run_id}/artifacts/{artifact_id}",
            include_in_project_bundle=entry.include_in_project_bundle,
            expose_download=entry.expose_download,
            embed_in_summary=entry.embed_in_summary,
            embed_in_final_results=entry.embed_in_final_results,
            required_for_report=entry.required_for_report,
            size_bytes=target.stat().st_size if target.exists() and target.is_file() else None,
            media_type=media_type or "application/octet-stream",
        )
        self._records[artifact_id] = record
        return record

    def write_json(self, artifact_id: str, payload: Any, *, dumps) -> ArtifactDescriptorRecord:
        path = self.path_for(artifact_id)
        path.write_text(dumps(payload), encoding="utf-8")
        return self.register_existing(artifact_id, path=path)

    def write_text(self, artifact_id: str, text: str) -> ArtifactDescriptorRecord:
        path = self.path_for(artifact_id)
        path.write_text(text, encoding="utf-8")
        return self.register_existing(artifact_id, path=path)

    def write_csv_rows(self, artifact_id: str, rows: Iterable[Dict[str, Any]], fieldnames: List[str]) -> ArtifactDescriptorRecord:
        path = self.path_for(artifact_id)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in fieldnames})
        return self.register_existing(artifact_id, path=path)

    def all_descriptors(self) -> List[Dict[str, Any]]:
        return [self._records[key].to_dict() for key in sorted(self._records.keys())]

    def exposed_descriptors(self) -> List[Dict[str, Any]]:
        return [self._records[key].to_dict() for key in sorted(self._records.keys()) if self._records[key].expose_download]

    def prune_for_outcome(self, success: bool) -> None:
        for artifact_id, entry in self.manifest.items():
            keep = entry.retain_on_success if success else entry.retain_on_failure
            if keep:
                continue
            path = self.path_for(artifact_id)
            if path.exists() and path.is_file():
                try:
                    path.unlink()
                except OSError:
                    continue
            self._records.pop(artifact_id, None)

    def prune_consumed_by(self, stage: str) -> None:
        stage = str(stage or "").strip()
        if not stage:
            return
        for artifact_id, entry in self.manifest.items():
            if entry.drop_after_consumed_by != stage:
                continue
            path = self.path_for(artifact_id)
            if path.exists() and path.is_file():
                try:
                    path.unlink()
                except OSError:
                    continue
            self._records.pop(artifact_id, None)

    def bundle_candidates(self) -> List[Path]:
        paths: List[Path] = []
        for artifact_id, row in self._records.items():
            if not row.include_in_project_bundle:
                continue
            path = self.path_for(artifact_id)
            if path.exists() and path.is_file():
                paths.append(path)
        return sorted(paths)
