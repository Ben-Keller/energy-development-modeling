"""Postgres-backed implementation of the EventStore protocol.

Implements plan chapter 8 (Runtime Event Store & Live Progress Tracking).
High-frequency inserts into execution_events are indexed on
(execution_id, timestamp) for ordered polling by the UI (plan 8.5).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import ExecutionEventRecord
from ..runtime.stores import EventStore, RuntimeEvent

logger = logging.getLogger(__name__)


def _parse_ts(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.now(timezone.utc)


class PostgresEventStore(EventStore):
    """SQLAlchemy-backed EventStore. Plan 8.1."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def _session(self) -> Session:
        return self._session_factory()

    def append_event(self, event: RuntimeEvent) -> None:
        with self._session() as session:
            session.add(
                ExecutionEventRecord(
                    execution_id=event.execution_id,
                    run_id=event.run_id,
                    level=event.level,
                    stage=event.stage,
                    message=event.message,
                    payload=event.payload,
                    timestamp=_parse_ts(event.timestamp) if event.timestamp else datetime.now(timezone.utc),
                )
            )
            session.commit()

    def read_events(self, execution_id: str) -> list[RuntimeEvent]:
        with self._session() as session:
            stmt = (
                select(ExecutionEventRecord)
                .where(ExecutionEventRecord.execution_id == execution_id)
                .order_by(ExecutionEventRecord.timestamp.asc(), ExecutionEventRecord.event_id.asc())
            )
            recs = session.execute(stmt).scalars().all()
            return [
                RuntimeEvent(
                    execution_id=r.execution_id,
                    run_id=r.run_id,
                    level=r.level,
                    stage=r.stage,
                    message=r.message,
                    payload=r.payload,
                    timestamp=r.timestamp.isoformat() if r.timestamp else "",
                )
                for r in recs
            ]

    def import_event_log(self, execution_id: str, source_path: str) -> int:
        """Read a JSONL log file written by the worker and bulk-insert
        the events into Postgres. Returns the number of events imported.
        """
        path = Path(source_path)
        if not path.is_file():
            return 0
        events: list[ExecutionEventRecord] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            events.append(
                ExecutionEventRecord(
                    execution_id=execution_id,
                    run_id=payload.get("run_id"),
                    level=payload.get("level", "info"),
                    stage=payload.get("stage", ""),
                    message=payload.get("message", ""),
                    payload=payload.get("payload"),
                    timestamp=_parse_ts(payload.get("timestamp", "")),
                )
            )
        if not events:
            return 0
        with self._session() as session:
            session.add_all(events)
            session.commit()
        return len(events)
