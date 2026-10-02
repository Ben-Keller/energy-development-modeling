from __future__ import annotations

"""Generic stage orchestration primitives for model runtimes.

This module intentionally has no EDIM, Calliope, MRIO, FastAPI, or filesystem
layout knowledge. It is the reusable execution shell that can run any model
pipeline expressed as ordered stages.
"""

from dataclasses import dataclass
from typing import Callable, Generic, Iterable, TypeVar


ContextT = TypeVar("ContextT")
ProgressEmitter = Callable[[str, float, str], None]
CancelChecker = Callable[[], None]
StageHandler = Callable[[ContextT], None]


@dataclass(frozen=True)
class ModelStage(Generic[ContextT]):
    """One executable stage in a model pipeline."""

    stage_id: str
    label: str
    handler: StageHandler[ContextT]
    start_progress: float | None = None
    start_message: str = ""
    end_progress: float | None = None
    end_message: str = ""


class StageOrchestrator(Generic[ContextT]):
    """Run model stages with consistent progress and cancellation semantics."""

    def __init__(
        self,
        *,
        emit_progress: ProgressEmitter,
        check_cancel: CancelChecker,
    ) -> None:
        self._emit_progress = emit_progress
        self._check_cancel = check_cancel

    def run(self, context: ContextT, stages: Iterable[ModelStage[ContextT]]) -> None:
        for stage in stages:
            self._check_cancel()
            if stage.start_progress is not None:
                self._emit_progress(
                    stage.stage_id,
                    stage.start_progress,
                    stage.start_message or stage.label,
                )
            stage.handler(context)
            self._check_cancel()
            if stage.end_progress is not None:
                self._emit_progress(
                    stage.stage_id,
                    stage.end_progress,
                    stage.end_message or f"{stage.label} complete",
                )
