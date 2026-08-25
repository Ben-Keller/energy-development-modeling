"""Azure Blob Storage implementation of the ArtifactStorageService protocol.

Provides blob-backed artifact persistence for docker-compose-dev (using the
Azure Storage emulator), staging, and production.  The same code path runs
against all three environments — only the connection string (or managed
identity in production) differs.

Intended injection point: ``main.py`` / ``create_app(artifact_storage=...)``.
"""

from __future__ import annotations

import json
import logging
import mimetypes
from io import BytesIO
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlencode

from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse

from ..runtime import ArtifactRegistry

try:
    from azure.core.exceptions import ResourceNotFoundError
    from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
    _BLOB_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover
    _BLOB_SDK_AVAILABLE = False

from ..settings import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants matching the existing local service for handoff compatibility
# ---------------------------------------------------------------------------
RUNTIME_ARTIFACT_PUBLICATION_SCHEMA_VERSION = "runtime_artifact_publication_v1"
STORAGE_REF_SCHEMA_VERSION = "edim_storage_ref_v1"
BLOB_STORAGE_PROVIDER = "azure_blob_storage"

# Default container used for run artifacts when no explicit container is
# configured.  Staging / production can override via EDIM_BLOB_ARTIFACT_CONTAINER.
_DEFAULT_ARTIFACT_CONTAINER = "edim-artifacts"


def _blob_service_client_from_env() -> BlobServiceClient:
    """Build a BlobServiceClient from the standard EDIM environment variables.

    Dev uses ``EDIM_AZURITE_CONNECTION_STRING`` (Azure Storage emulator).
    Staging / production use ``EDIM_BLOB_ACCOUNT_URL`` + Managed Identity
    (via ``DefaultAzureCredential``).
    """
    if not _BLOB_SDK_AVAILABLE:
        raise RuntimeError(
            "azure-storage-blob is not installed. "
            "Add it to requirements to use BlobArtifactStorageService."
        )
    import os

    conn_str = os.getenv("EDIM_AZURITE_CONNECTION_STRING", "").strip()
    if conn_str:
        return BlobServiceClient.from_connection_string(conn_str)

    account_url = os.getenv("EDIM_BLOB_ACCOUNT_URL", "").strip()
    if account_url:
        from azure.identity import DefaultAzureCredential
        return BlobServiceClient(account_url=account_url, credential=DefaultAzureCredential())

    raise RuntimeError(
        "Set EDIM_AZURITE_CONNECTION_STRING (dev emulator) or "
        "EDIM_BLOB_ACCOUNT_URL (staging/production Managed Identity)."
    )


def _artifact_container_name() -> str:
    import os
    return os.getenv("EDIM_BLOB_ARTIFACT_CONTAINER", _DEFAULT_ARTIFACT_CONTAINER).strip()


def _blob_name(run_id: str, artifact_id: str) -> str:
    """Blob path matching the worker upload convention.

    The worker uploads the model run directory relative to ``<run_id>/``
    (e.g. ``<run_id>/artifacts/final/results.csv``).  The API uses artifact
    IDs like ``results_csv`` which are mapped here to the model's layout.
    """
    # Map common artifact IDs to the relative paths used by the model runtime
    # (see the model's artifact_index.json / artifact policy manifest).
    _id_to_file: dict[str, str] = {
        "summary_json": "summary.json",
        "results_csv": "artifacts/final/results.csv",
        "operating_shocks_csv": "artifacts/intermediate/exchange/operating_shocks.csv",
        "investment_shocks_csv": "artifacts/intermediate/exchange/investment_shocks.csv",
        "integrated_results_json": "artifacts/final/integrated_results.json",
        "coupling_manifest_json": "artifacts/final/coupling_manifest.json",
        "development_impacts_json": "artifacts/final/development_impacts.json",
        "report_md": "exports/report.md",
        "report_markdown": "exports/report.md",
        "artifact_index_json": "artifacts/artifact_index.json",
        "exchange_bundle_zip": "exports/exchange_bundle.zip",
        "calliope_component_activity_csv": "artifacts/intermediate/exchange/calliope_component_activity.csv",
        "energy_service_balance_csv": "artifacts/intermediate/exchange/energy_service_balance.csv",
        "prices_and_taxes_csv": "artifacts/intermediate/exchange/prices_and_taxes.csv",
    }
    file_name = _id_to_file.get(artifact_id, artifact_id)
    return f"{run_id}/{file_name}"


# ---------------------------------------------------------------------------
# Public service
# ---------------------------------------------------------------------------


class BlobArtifactStorageService:
    """Azure Blob Storage implementation of ``ArtifactStorageService``.

    Construction reads connection credentials from the environment
    (``EDIM_AZURITE_CONNECTION_STRING`` or ``EDIM_BLOB_ACCOUNT_URL``) so
    callers only need to instantiate and inject — no explicit config wiring.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._blob_service: BlobServiceClient | None = None
        self._container_name = _artifact_container_name()

    # ------------------------------------------------------------------
    # Protocol: ArtifactStorageService
    # ------------------------------------------------------------------

    def publish_run_artifacts(
        self,
        *,
        run_id: str,
        run_dir: Path,
        artifact_catalog: list[Dict[str, Any]],
        handoff_mode: str,
    ) -> Dict[str, Any]:
        """Upload declared run artifacts to Azure Blob Storage.

        After a model run completes, the runtime writes artifacts to the
        shared filesystem.  This method uploads each downloadable artifact
        to blob storage and returns a publication receipt with blob-level
        object references that downstream download endpoints can resolve.
        """
        mode = (handoff_mode or "").strip().lower()
        artifacts = [dict(row) for row in artifact_catalog if isinstance(row, dict)]
        downloadable = [row for row in artifacts if row.get("expose_download")]

        if mode == "shared_filesystem":
            # Local development: artifacts are available in-place.  We still
            # upload to blob so that the same download code path is exercised.
            pass

        client = self._get_blob_service()
        container_client = client.get_container_client(self._container_name)
        if not container_client.exists():
            container_client.create_container()

        published_refs: list[Dict[str, Any]] = []
        for artifact in downloadable:
            artifact_id = str(artifact.get("artifact_id") or "")
            if not artifact_id:
                continue
            local_path = run_dir / artifact_id
            if not local_path.exists() or not local_path.is_file():
                logger.warning("Artifact %s not found at %s; skipping upload.", artifact_id, local_path)
                continue
            blob_name = _blob_name(run_id, artifact_id)
            blob_client = client.get_blob_client(container=self._container_name, blob=blob_name)
            with open(local_path, "rb") as fh:
                blob_client.upload_blob(fh, overwrite=True)
            published_refs.append(
                {
                    "artifact_id": artifact_id,
                    "storage_provider": BLOB_STORAGE_PROVIDER,
                    "container": self._container_name,
                    "blob_name": blob_name,
                }
            )

        return {
            "schema_version": RUNTIME_ARTIFACT_PUBLICATION_SCHEMA_VERSION,
            "run_id": run_id,
            "handoff_mode": mode,
            "storage_provider": BLOB_STORAGE_PROVIDER,
            "storage_scope": "run",
            "object_prefix": f"runs/{run_id}",
            "status": "published",
            "published": True,
            "artifact_count": len(artifacts),
            "downloadable_artifact_count": len(published_refs),
            "published_refs": published_refs,
            "message": f"Uploaded {len(published_refs)} artifacts to Azure Blob Storage.",
        }

    def read_json_artifact(self, run_id: str, artifact_id: str) -> dict:
        """Read a JSON artifact directly from blob storage."""
        client = self._get_blob_service()
        blob_name = _blob_name(run_id, artifact_id)
        blob_client = client.get_blob_client(container=self._container_name, blob=blob_name)
        try:
            stream = blob_client.download_blob()
            raw = stream.readall()
        except ResourceNotFoundError:
            raise HTTPException(status_code=404, detail="Artifact not found in blob storage.")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=503, detail="Run artifact is not valid JSON yet. Please retry.") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=503, detail="Run artifact JSON must be an object.")
        return payload

    def download_response_for_artifact(self, run_id: str, artifact_id: str) -> Response:
        """Return a streaming download response for a run artifact."""
        client = self._get_blob_service()
        blob_name = _blob_name(run_id, artifact_id)
        blob_client = client.get_blob_client(container=self._container_name, blob=blob_name)
        try:
            props = blob_client.get_blob_properties()
        except ResourceNotFoundError:
            raise HTTPException(status_code=404, detail="Artifact not found in blob storage.")

        media_type = (props.content_settings and props.content_settings.content_type) or ""
        if not media_type:
            media_type, _ = mimetypes.guess_type(artifact_id)
        media_type = media_type or "application/octet-stream"
        file_name = artifact_id.rsplit("/", 1)[-1] if "/" in artifact_id else artifact_id

        stream = blob_client.download_blob()
        return StreamingResponse(
            stream.chunks(),
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{file_name}"',
                "Content-Length": str(props.size or 0),
            },
        )

    def download_response_for_ref(
        self,
        storage_ref: Dict[str, Any] | None,
        *,
        filename: str,
        default_media_type: str,
    ) -> Response:
        """Resolve a storage reference and stream the blob."""
        if not isinstance(storage_ref, dict):
            raise HTTPException(status_code=404, detail="Storage reference not found.")

        provider = str(storage_ref.get("storage_provider") or "")
        if provider and provider != BLOB_STORAGE_PROVIDER:
            raise HTTPException(status_code=501, detail=f"Unsupported storage provider: {provider}")

        container = str(storage_ref.get("container") or self._container_name)
        blob_name = str(storage_ref.get("blob_name") or storage_ref.get("object_key") or "")
        if not blob_name:
            raise HTTPException(status_code=404, detail="Storage reference missing blob key.")

        client = self._get_blob_service()
        blob_client = client.get_blob_client(container=container, blob=blob_name)
        try:
            props = blob_client.get_blob_properties()
        except ResourceNotFoundError:
            raise HTTPException(status_code=404, detail="Blob not found.")

        media_type = (props.content_settings and props.content_settings.content_type) or ""
        if not media_type:
            media_type, _ = mimetypes.guess_type(blob_name)
        media_type = media_type or default_media_type or "application/octet-stream"

        response_filename = filename or blob_name.rsplit("/", 1)[-1]
        stream = blob_client.download_blob()
        return StreamingResponse(
            stream.chunks(),
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{response_filename}"',
                "Content-Length": str(props.size or 0),
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_blob_service(self) -> BlobServiceClient:
        if self._blob_service is None:
            self._blob_service = _blob_service_client_from_env()
        return self._blob_service
