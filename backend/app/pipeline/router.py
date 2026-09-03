from __future__ import annotations

from typing import Any

from .base import BaseNode, InferenceError
from .deepforest import DeepForestNode
from .langsam import LangSAMNode


class FeatureRouter:
    """Dispatch an orthophoto tile to the correct detector node per class.

    - buildings / roads / water / farms -> LangSAM (zero-shot segmentation)
    - trees                            -> DeepForest (crown detection)
    """

    def __init__(self, device: str = "auto") -> None:
        self.device = device
        self._langsam: LangSAMNode | None = None
        self._deepforest: DeepForestNode | None = None

    def _node_for(self, feature_type: str) -> BaseNode:
        if feature_type == "trees":
            if self._deepforest is None:
                self._deepforest = DeepForestNode(self.device)
            return self._deepforest
        if self._langsam is None:
            self._langsam = LangSAMNode(self.device)
        return self._langsam

    def detect(self, image: Any, feature_type: str) -> Any:
        node = self._node_for(feature_type)
        if not node.check_available():
            raise InferenceError(
                f"{node.name} is unavailable for '{feature_type}'. "
                "Install backend/requirements-ml.txt to enable ML."
            )
        return node.run(image, feature_type)

    def availability(self) -> dict[str, Any]:
        return {
            "langsam": self._langsam.check_available() if self._langsam else LangSAMNode(self.device).check_available(),
            "deepforest": self._deepforest.check_available()
            if self._deepforest
            else DeepForestNode(self.device).check_available(),
        }