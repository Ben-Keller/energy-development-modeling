from __future__ import annotations

import csv
import json
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List


DEFAULT_ARTIFACT_MANIFEST: Dict[str, Dict[str, Any]] = {
    "request_bundle_json": {
        "path": "inputs/request_bundle.json",
        "producer_stage": "scenario_prepare",
        "kind": "input_snapshot",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": False,
    },
    "model_manifest_json": {
        "path": "inputs/model_manifest.json",
        "producer_stage": "scenario_prepare",
        "kind": "input_snapshot",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": False,
    },
    "dataset_manifest_json": {
        "path": "inputs/dataset_manifest.json",
        "producer_stage": "scenario_prepare",
        "kind": "input_snapshot",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": False,
    },
    "artifact_policy_json": {
        "path": "inputs/artifact_policy.json",
        "producer_stage": "scenario_prepare",
        "kind": "input_snapshot",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": False,
    },
    "runtime_events_jsonl": {
        "path": "logs/runtime_events.jsonl",
        "producer_stage": "runtime",
        "kind": "log",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": False,
    },
    "artifact_index_json": {
        "path": "artifacts/artifact_index.json",
        "producer_stage": "runtime",
        "kind": "final",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": False,
    },
    "scenario_package_json": {
        "path": "inputs/scenario_package.json",
        "producer_stage": "scenario_prepare",
        "kind": "input_snapshot",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": True,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": True,
    },
    "energy_input_manifest_json": {
        "path": "inputs/scenario/energy_input_manifest.json",
        "producer_stage": "scenario_prepare",
        "kind": "input_snapshot",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": False,
    },
    "report_scenario_reference_json": {
        "path": "inputs/scenario/report_scenario_reference.json",
        "producer_stage": "scenario_prepare",
        "kind": "input_snapshot",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": False,
    },
    "geography_alignment_json": {
        "path": "inputs/scenario/geography_alignment.json",
        "producer_stage": "scenario_prepare",
        "kind": "input_snapshot",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": False,
    },
    "mrio_direct_inputs_json": {
        "path": "artifacts/intermediate/scenario/mrio_direct_inputs.json",
        "producer_stage": "mrio_direct_prepare",
        "kind": "intermediate",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": False,
    },
    "mrio_direct_shocks_csv": {
        "path": "artifacts/intermediate/scenario/mrio_direct_shocks.csv",
        "producer_stage": "mrio_direct_prepare",
        "kind": "intermediate",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": False,
    },
    "ui_override_patch_yaml": {
        "path": "inputs/runtime/ui_override_patch.yaml",
        "producer_stage": "energy_input_prepare",
        "kind": "input_snapshot",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": False,
    },
    "results_csv": {
        "path": "artifacts/final/results.csv",
        "producer_stage": "write_artifacts",
        "kind": "final",
        "retain_on_success": True,
        "retain_on_failure": False,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": True,
    },
    "summary_json": {
        "path": "artifacts/final/summary.json",
        "producer_stage": "build_integrated",
        "kind": "final",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": True,
    },
    "development_impacts_json": {
        "path": "artifacts/final/development_impacts.json",
        "producer_stage": "development",
        "kind": "final",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": True,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": True,
    },
    "coupling_manifest_json": {
        "path": "artifacts/final/coupling_manifest.json",
        "producer_stage": "development",
        "kind": "final",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": True,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": True,
    },
    "integrated_results_json": {
        "path": "artifacts/final/integrated_results.json",
        "producer_stage": "build_integrated",
        "kind": "final",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": True,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": True,
    },
    "energy_service_balance_csv": {
        "path": "artifacts/intermediate/exchange/energy_service_balance.csv",
        "producer_stage": "bridge_prepare",
        "kind": "intermediate",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": False,
    },
    "calliope_component_activity_csv": {
        "path": "artifacts/intermediate/exchange/calliope_component_activity.csv",
        "producer_stage": "bridge_prepare",
        "kind": "intermediate",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": False,
    },
    "investment_shocks_csv": {
        "path": "artifacts/intermediate/exchange/investment_shocks.csv",
        "producer_stage": "bridge_prepare",
        "kind": "intermediate",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": False,
    },
    "operating_shocks_csv": {
        "path": "artifacts/intermediate/exchange/operating_shocks.csv",
        "producer_stage": "bridge_prepare",
        "kind": "intermediate",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": False,
    },
    "prices_and_taxes_csv": {
        "path": "artifacts/intermediate/exchange/prices_and_taxes.csv",
        "producer_stage": "bridge_prepare",
        "kind": "intermediate",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": False,
    },
    "exchange_metadata_json": {
        "path": "artifacts/intermediate/exchange/metadata.json",
        "producer_stage": "bridge_prepare",
        "kind": "intermediate",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": False,
        "expose_download": False,
        "required_for_report": False,
    },
    "mario_runner_log": {
        "path": "logs/mario_runner.log",
        "producer_stage": "development",
        "kind": "log",
        "retain_on_success": True,
        "retain_on_failure": True,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": False,
    },
    "report_markdown": {
        "path": "exports/report.md",
        "producer_stage": "build_integrated",
        "kind": "export",
        "retain_on_success": True,
        "retain_on_failure": False,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": True,
        "expose_download": True,
        "required_for_report": False,
    },
    "exchange_bundle_zip": {
        "path": "exports/exchange_bundle.zip",
        "producer_stage": "build_integrated",
        "kind": "export",
        "retain_on_success": True,
        "retain_on_failure": False,
        "embed_in_summary": False,
        "embed_in_final_results": False,
        "include_in_project_bundle": False,
        "expose_download": True,
        "required_for_report": False,
    },
}

@dataclass(frozen=True)
class RuntimeSettings:
    runs_dir: Path
    config_dir: Path
    runtime_config: Dict[str, Any] = field(default_factory=dict)
    artifact_policy: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeEvent:
    type: str
    stage: str = ""
    progress: float | None = None
    message: str = ""
    level: str = "info"
    run_id: str = ""
    execution_id: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_json_line(self) -> str:
        data: Dict[str, Any] = {
            "schema_version": "runtime_event_v1",
            "type": self.type,
            "level": self.level,
        }
        if self.stage:
            data["stage"] = self.stage
        if self.progress is not None:
            data["progress"] = max(0.0, min(1.0, float(self.progress)))
        if self.message:
            data["message"] = self.message
        if self.run_id:
            data["run_id"] = self.run_id
        if self.execution_id:
            data["execution_id"] = self.execution_id
        if self.payload:
            data["payload"] = self.payload
        return json.dumps(data, sort_keys=True, separators=(",", ":"))


def runtime_settings_from_bundle(bundle: Dict[str, Any], repo_root: Path) -> RuntimeSettings:
    raw = bundle.get("runtime_settings") if isinstance(bundle.get("runtime_settings"), dict) else {}
    runs_dir = _path(raw.get("runs_dir"), repo_root / "outputs" / "runs")
    config_dir = _path(raw.get("config_dir"), repo_root / "inputs")
    runtime_config = raw.get("runtime_config") if isinstance(raw.get("runtime_config"), dict) else {}
    artifact_policy = bundle.get("artifact_policy") if isinstance(bundle.get("artifact_policy"), dict) else {}
    return RuntimeSettings(
        runs_dir=runs_dir,
        config_dir=config_dir,
        runtime_config=runtime_config,
        artifact_policy=artifact_policy,
    )


def _path(value: Any, default: Path) -> Path:
    text = str(value or "").strip()
    if not text:
        return default.resolve()
    return Path(text).expanduser().resolve()


@dataclass(frozen=True)
class ArtifactManifestEntry:
    artifact_id: str
    path: str
    producer_stage: str
    kind: str
    retain_on_success: bool
    retain_on_failure: bool
    embed_in_final_results: bool
    embed_in_summary: bool
    include_in_project_bundle: bool
    expose_download: bool
    required_for_report: bool
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
    inputs_dir = run_dir / "inputs"
    work_dir = run_dir / "work"
    artifacts_dir = run_dir / "artifacts"
    logs_dir = run_dir / "logs"
    exports_dir = run_dir / "exports"
    for path in (inputs_dir, work_dir, artifacts_dir, logs_dir, exports_dir):
        path.mkdir(parents=True, exist_ok=True)
    return RunLayout(
        run_dir=run_dir,
        inputs_dir=inputs_dir,
        work_dir=work_dir,
        artifacts_dir=artifacts_dir,
        logs_dir=logs_dir,
        exports_dir=exports_dir,
    )


def _label_from_artifact_id(artifact_id: str) -> str:
    return artifact_id.replace("_", " ").strip().title()


def _artifact_overrides(config_or_policy: Dict[str, Any] | None) -> Dict[str, Any]:
    cfg = config_or_policy if isinstance(config_or_policy, dict) else {}
    if isinstance(cfg.get("manifest"), dict):
        return cfg["manifest"]
    artifacts = cfg.get("artifacts") if isinstance(cfg.get("artifacts"), dict) else {}
    manifest = artifacts.get("manifest") if isinstance(artifacts, dict) else {}
    return manifest if isinstance(manifest, dict) else {}


def load_artifact_manifest(config_or_policy: Dict[str, Any] | None) -> Dict[str, ArtifactManifestEntry]:
    overrides = _artifact_overrides(config_or_policy)
    manifest: Dict[str, ArtifactManifestEntry] = {}
    merged = {**DEFAULT_ARTIFACT_MANIFEST}
    for artifact_id, override in overrides.items():
        base = dict(merged.get(artifact_id, {}))
        if isinstance(override, dict):
            base.update(override)
        merged[artifact_id] = base
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
        rows = []
        for key in sorted(self._records.keys()):
            row = self._records[key]
            if row.expose_download:
                rows.append(row.to_dict())
        return rows

    def prune_for_outcome(self, success: bool) -> None:
        for artifact_id, entry in self.manifest.items():
            keep = entry.retain_on_success if success else entry.retain_on_failure
            if keep:
                continue
            path = self.path_for(artifact_id)
            if path.exists():
                try:
                    if path.is_file():
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
