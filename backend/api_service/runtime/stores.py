from __future__ import annotations

import queue
from pathlib import Path
from typing import Any, Dict, Protocol

from .contracts import ExecutionQueueMessage
from .artifacts import ArtifactRegistry
from .events import RuntimeEvent, RuntimeEventLog


class RunStore(Protocol):
    def run_dir(self, run_id: str) -> Path: ...
    def queued_dir(self, execution_id: str) -> Path: ...


class ArtifactStore(Protocol):
    def artifact_path(self, run_id: str, artifact_id: str) -> Path: ...


class EventStore(Protocol):
    def event_log_path(self, execution_id: str) -> Path: ...
    def append_event(self, execution_id: str, event: RuntimeEvent | Dict[str, Any]) -> None: ...
    def read_events(self, execution_id: str) -> list[Dict[str, Any]]: ...
    def import_event_log(self, execution_id: str, source_path: Path) -> None: ...


class ExecutionQueue(Protocol):
    def put(self, message: ExecutionQueueMessage | Dict[str, Any] | str) -> None: ...
    def get(self) -> ExecutionQueueMessage | Dict[str, Any] | str: ...
    def task_done(self) -> None: ...
    def qsize(self) -> int: ...


class RunRepository(Protocol):
    def create_run_record(
        self,
        *,
        project_id: str,
        request_payload: Dict[str, Any],
        run_id: str,
        execution_id: str,
        status: str,
        dataset_snapshot: Dict[str, Any],
        user_id: str,
    ) -> Dict[str, Any]: ...

    def update_run_record(self, run_id: str, updates: Dict[str, Any], *, user_id: str) -> Dict[str, Any]: ...


class LocalRunStore:
    def __init__(self, runs_dir: Path):
        self.runs_dir = runs_dir
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def queued_dir(self, execution_id: str) -> Path:
        path = self.runs_dir / "_queued" / execution_id
        path.mkdir(parents=True, exist_ok=True)
        return path


class LocalEventStore:
    def __init__(self, runs_dir: Path):
        self.runs_dir = runs_dir

    def event_log_path(self, execution_id: str) -> Path:
        path = self.runs_dir / "_queued" / execution_id / "logs" / "runtime_events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def append_event(self, execution_id: str, event: RuntimeEvent | Dict[str, Any]) -> None:
        RuntimeEventLog(self.event_log_path(execution_id)).append(event)

    def read_events(self, execution_id: str) -> list[Dict[str, Any]]:
        return RuntimeEventLog(self.event_log_path(execution_id)).read()

    def import_event_log(self, execution_id: str, source_path: Path) -> None:
        target = self.event_log_path(execution_id)
        if not source_path.exists() or not source_path.is_file():
            return
        if source_path.resolve() == target.resolve():
            return
        target.write_text(source_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")


class LocalArtifactStore:
    def __init__(self, runs_dir: Path):
        self.runs_dir = runs_dir

    def artifact_path(self, run_id: str, artifact_id: str) -> Path:
        return ArtifactRegistry(run_id=run_id, run_dir=self.runs_dir / run_id).path_for(artifact_id)


class LocalExecutionQueue:
    def __init__(self):
        self._queue: queue.Queue[ExecutionQueueMessage | Dict[str, Any] | str] = queue.Queue()

    def put(self, message: ExecutionQueueMessage | Dict[str, Any] | str) -> None:
        self._queue.put(message)

    def get(self) -> ExecutionQueueMessage | Dict[str, Any] | str:
        return self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    def qsize(self) -> int:
        return self._queue.qsize()
