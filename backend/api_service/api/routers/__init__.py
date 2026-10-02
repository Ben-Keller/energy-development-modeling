from .datasets import router as datasets_router
from .platform import router as platform_router
from .runs import router as runs_router
from .scenarios import router as scenarios_router
from .system import router as system_router

__all__ = [
    "datasets_router",
    "platform_router",
    "runs_router",
    "scenarios_router",
    "system_router",
]
