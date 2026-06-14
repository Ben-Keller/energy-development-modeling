"""Isolated compute worker daemon for local development.

This is a scaffold that establishes the target runtime topology:
  - receives ExecutionQueueMessages from Azure Service Bus emulator
  - downloads the request bundle from Azurite (Azure Blob Storage emulator)
  - invokes the edim_model CLI
  - uploads artifacts to Azurite
  - persists terminal state to PostgreSQL

The durable-messaging plumbing is intentionally explicit so it can be hardened
into the production AzureServiceBusQueue implementation (plan chapter 6).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

# Azure SDKs are installed via worker/requirements.txt.
try:
    from azure.servicebus import ServiceBusClient, ServiceBusMessage
    from azure.storage.blob import BlobServiceClient
    import psycopg2
except ImportError as exc:  # pragma: no cover - defensive for missing optional SDKs
    ServiceBusClient = None  # type: ignore
    ServiceBusMessage = None  # type: ignore
    BlobServiceClient = None  # type: ignore
    psycopg2 = None  # type: ignore

logger = logging.getLogger("edim-worker")


class WorkerConfig:
    def __init__(self) -> None:
        self.worker_id = os.getenv("EDIM_WORKER_ID", f"edim-worker-{uuid.uuid4().hex[:8]}")
        self.mode = os.getenv("EDIM_WORKER_MODE", "directory")

        # Paths
        self.calliope_root = Path(os.getenv("EDIM_CALLIOPE_ROOT", "/app/calliope-africa"))
        self.runs_dir = Path(os.getenv("EDIM_RUNS_DIR", "/app/outputs/runs"))
        self.config_dir = Path(os.getenv("EDIM_CONFIG_DIR", "/app/inputs"))

        # PostgreSQL
        self.database_url = os.getenv("EDIM_DATABASE_URL", "")

        # Service Bus
        self.servicebus_connection_string = os.getenv("EDIM_SERVICEBUS_CONNECTION_STRING", "")
        self.servicebus_queue_name = os.getenv("EDIM_SERVICEBUS_QUEUE_NAME", "execution-queue-local")

        # Blob storage
        self.azurite_connection_string = os.getenv("EDIM_AZURITE_CONNECTION_STRING", "")

        # Inbox directory for local directory-mode testing.
        self.inbox_dir = Path(os.getenv("EDIM_WORKER_INBOX_DIR", str(self.runs_dir.parent / "worker-inbox")))
        self.polling_interval_seconds = float(os.getenv("EDIM_WORKER_POLL_INTERVAL", "5"))

    def azurite_blob_service(self) -> Any | None:
        if not self.azurite_connection_string or BlobServiceClient is None:
            return None
        return BlobServiceClient.from_connection_string(self.azurite_connection_string)

    def servicebus_client(self) -> Any | None:
        if not self.servicebus_connection_string or ServiceBusClient is None:
            return None
        return ServiceBusClient.from_connection_string(self.servicebus_connection_string)


def _run_cli(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    logger.info("Running CLI: %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _execute_bundle(config: WorkerConfig, bundle_path: Path) -> dict[str, Any]:
    """Run the model CLI against a local bundle file."""
    result = _run_cli([
        sys.executable,
        "-m",
        "edim_model.cli",
        "run",
        "--bundle",
        str(bundle_path),
    ])

    stdout_lines = result.stdout.strip().splitlines()
    last_json = None
    for line in reversed(stdout_lines):
        line = line.strip()
        if line.startswith("{"):
            try:
                last_json = json.loads(line)
                break
            except json.JSONDecodeError:
                continue

    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "cli_result": last_json,
    }


def _process_directory_mode(config: WorkerConfig) -> None:
    """Poll a local inbox directory for bundles; useful for CLI smoke tests."""
    config.inbox_dir.mkdir(parents=True, exist_ok=True)
    bundles = sorted(config.inbox_dir.glob("*.json"))
    if not bundles:
        logger.info("No bundles in %s; sleeping %ss", config.inbox_dir, config.polling_interval_seconds)
        return

    for bundle_path in bundles:
        logger.info("Processing bundle: %s", bundle_path.name)
        outcome = _execute_bundle(config, bundle_path)
        if outcome["exit_code"] == 0:
            logger.info("Bundle %s succeeded", bundle_path.name)
            bundle_path.rename(bundle_path.with_suffix(".done.json"))
        else:
            logger.error("Bundle %s failed with exit_code=%s", bundle_path.name, outcome["exit_code"])
            bundle_path.rename(bundle_path.with_suffix(".failed.json"))


def _process_servicebus_mode(config: WorkerConfig) -> None:
    """Receive a single message from Service Bus emulator and process it."""
    client = config.servicebus_client()
    if client is None:
        logger.warning("Service Bus SDK unavailable; falling back to directory mode")
        _process_directory_mode(config)
        return

    try:
        with client:
            receiver = client.get_queue_receiver(queue_name=config.servicebus_queue_name)
            with receiver:
                messages = receiver.receive_messages(max_message_count=1, max_wait_time=10)
                if not messages:
                    logger.info("No Service Bus messages; sleeping %ss", config.polling_interval_seconds)
                    return
                msg = messages[0]
                logger.info("Received message %s", msg.message_id)
                try:
                    raw_body = b"".join(msg.body)
                    body = json.loads(raw_body.decode("utf-8"))
                except (json.JSONDecodeError, AttributeError):
                    body = json.loads(str(msg))
                logger.info("Message body: %s", body)

                # In a full implementation: download bundle from Azurite, run CLI,
                # upload artifacts, update PostgreSQL, then complete the message.
                # For the scaffold we ack the message and log it.
                receiver.complete_message(msg)
                logger.info("Completed message %s", msg.message_id)
    except Exception:
        logger.exception("Service Bus receive loop failed")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = WorkerConfig()
    logger.info("Starting EDIM worker: id=%s mode=%s", config.worker_id, config.mode)
    logger.info("Runs dir: %s", config.runs_dir)
    logger.info("Inbox dir: %s", config.inbox_dir)

    # Smoke-test connectivity to emulators once at startup.
    try:
        blob_service = config.azurite_blob_service()
        if blob_service:
            props = blob_service.get_service_properties()
            logger.info("Azurite connectivity OK")
    except Exception as exc:
        logger.warning("Azurite not reachable yet: %s", exc)

    try:
        if config.database_url and psycopg2 is not None:
            conn = psycopg2.connect(config.database_url)
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            conn.close()
            logger.info("PostgreSQL connectivity OK")
    except Exception as exc:
        logger.warning("PostgreSQL not reachable yet: %s", exc)

    while True:
        try:
            if config.mode == "servicebus":
                _process_servicebus_mode(config)
            else:
                _process_directory_mode(config)
        except Exception:
            logger.exception("Worker loop error")
        time.sleep(config.polling_interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
