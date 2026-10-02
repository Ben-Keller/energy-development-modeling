from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

RUNTIME_EVENT_SCHEMA_VERSION = "runtime_event_v1"


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass(frozen=True)
class RuntimeEvent:
    type: str
    stage: str = ""
    progress: float | None = None
    message: str = ""
    run_id: str = ""
    level: str = "info"
    timestamp: str = field(default_factory=utc_now_iso)
    payload: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = RUNTIME_EVENT_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "schema_version": self.schema_version,
            "type": self.type,
            "timestamp": self.timestamp,
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
        if self.payload:
            data["payload"] = self.payload
        return data

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class RuntimeEventLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: RuntimeEvent | Dict[str, Any]) -> None:
        payload = event.to_dict() if isinstance(event, RuntimeEvent) else dict(event)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
            handle.write("\n")

    def read(self) -> list[Dict[str, Any]]:
        if not self.path.exists():
            return []
        out: list[Dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                out.append({"schema_version": RUNTIME_EVENT_SCHEMA_VERSION, "type": "raw", "message": line})
        return out


def parse_runtime_event_lines(lines: Iterable[str]) -> Iterable[Dict[str, Any]]:
    for line in lines:
        raw = line.strip()
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            yield {"schema_version": RUNTIME_EVENT_SCHEMA_VERSION, "type": "stdout", "message": raw}
            continue
        if isinstance(event, dict):
            yield event
        else:
            yield {"schema_version": RUNTIME_EVENT_SCHEMA_VERSION, "type": "stdout", "message": raw}
