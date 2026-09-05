from __future__ import annotations

from typing import Any

from .base import BaseNode, InferenceError
from .deepforest import DeepForestNode
from .ultralytics_det import SemanticBuildingNode
from .water_det import WaterDetectionNode

# Feature classes serviced by the Cityscapes semantic segmenter (yolo26n-sem.pt),
# which maps each per-pixel class to a feature type. Roads/water/farms come from
# the same single inference so no extra model is needed.
_SEM_FEATURE_TYPES = ("buildings", "roads", "farms")


class FeatureRouter:
    """Dispatch an orthophoto tile to the correct detector node per class.

    - buildings/roads/farms -> Ultralytics semantic segmenter (yolo*-sem)
    - trees                 -> DeepForest (crown detection)
    - water                 -> WaterDetectionNode (VWI spectral water detection)
    """

    def __init__(self, device: str = "auto") -> None:
        self.device = device
        self._semantic: SemanticBuildingNode | None = None
        self._deepforest: DeepForestNode | None = None
        self._water: WaterDetectionNode | None = None

    def _reset_image(self) -> None:
        """Clear per-image caches (semantic class map) between uploads."""
        if self._semantic is not None:
            self._semantic.reset()

    def detect(self, image: Any, feature_type: str) -> list[dict[str, Any]]:
        if feature_type == "water":
            node = self._water or WaterDetectionNode()
            self._water = node
            return node.run(image)

        if feature_type == "trees":
            node = self._deepforest or DeepForestNode(self.device)
            self._deepforest = node
            if not node.check_available():
                raise InferenceError(
                    f"{node.name} is unavailable for '{feature_type}'. "
                    "Install backend/requirements-ml.txt to enable ML."
                )
            return node.run(image, feature_type)

        if feature_type not in _SEM_FEATURE_TYPES:
            return []

        node = self._semantic or SemanticBuildingNode(self.device)
        self._semantic = node
        if not node.check_available():
            raise InferenceError(
                f"{node.name} is unavailable for '{feature_type}'. "
                "Install backend/requirements-ml.txt to enable ML."
            )
        return node.run(image, feature_type)

    def detect_batch(
        self, images: list[Any], feature_type: str
    ) -> list[list[dict[str, Any]]]:
        """Run detection on a batch of images; returns one result list per image."""
        if not images:
            return []

        if feature_type == "water":
            node = self._water or WaterDetectionNode()
            self._water = node
            return [node.run(img) for img in images]

        if feature_type == "trees":
            node = self._deepforest or DeepForestNode(self.device)
            self._deepforest = node
            if not node.check_available():
                return [[] for _ in images]
            return [node.run(img, feature_type) for img in images]

        if feature_type not in _SEM_FEATURE_TYPES:
            return [[] for _ in images]

        node = self._semantic or SemanticBuildingNode(self.device)
        self._semantic = node
        if not node.check_available():
            return [[] for _ in images]

        class_maps = node.semantic_masks_batch(images)
        return [
            node.run_on_class_map(cm, feature_type) if cm is not None else []
            for cm in class_maps
        ]

    def availability(self) -> dict[str, Any]:
        return {
            "ultralytics": (
                self._semantic.check_available()
                if self._semantic
                else SemanticBuildingNode(self.device).check_available()
            ),
            "deepforest": (
                self._deepforest.check_available()
                if self._deepforest
                else DeepForestNode(self.device).check_available()
            ),
            "water": (
                self._water.check_available()
                if self._water
                else WaterDetectionNode().check_available()
            ),
        }