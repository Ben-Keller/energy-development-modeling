from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DATASET_CONTAINER_ENV = "EDIM_BLOB_DATASET_CONTAINER"
DEFAULT_DATASET_CONTAINER = "stg-input-datasets"


def blob_enabled() -> bool:
    return bool(
        os.getenv("EDIM_AZURITE_CONNECTION_STRING", "").strip()
        or os.getenv("EDIM_BLOB_ACCOUNT_URL", "").strip()
    )


def mirror_dataset_version(*, user_id: str, dataset_id: str, version_id: str, filename: str, content: bytes) -> str:
    if not blob_enabled():
        return ""
    from .blob_artifact_storage import _blob_service_client_from_env

    container_name = os.getenv(DATASET_CONTAINER_ENV, "").strip() or DEFAULT_DATASET_CONTAINER
    suffix = Path(filename or "dataset.bin").suffix
    blob_name = f"{user_id}/{dataset_id}/{version_id}{suffix}"
    client = _blob_service_client_from_env()
    container = client.get_container_client(container_name)
    try:
        container.create_container()
    except Exception:
        pass
    container.upload_blob(name=blob_name, data=content, overwrite=True)
    logger.info("Mirrored dataset %s version %s to blob %s/%s", dataset_id, version_id, container_name, blob_name)
    return str(container.get_blob_client(blob_name).url)
