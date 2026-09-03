from __future__ import annotations

import enum
from typing import Any


class PipelineStage(str, enum.Enum):
    IDLE = "idle"
    TILING = "tiling"
    DETECTING = "detecting"
    VECTORIZING = "vectorizing"
    COMPLETE = "complete"


class InferenceError(RuntimeError):
    """Raised when an inference model cannot be loaded or run."""


class BaseNode:
    """Base class for a single pipeline node (tiler/detector/vectorizer)."""

    name = "base"
    requires_ml = False

    def __init__(self, device: str = "auto") -> None:
        self.device = device

    def check_available(self) -> bool:
        """Return True if this node can run given installed dependencies."""
        return True

    def run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.check_available(),
            "requires_ml": self.requires_ml,
        }