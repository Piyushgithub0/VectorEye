from __future__ import annotations

from typing import Any

from .base import BaseNode, InferenceError

# Prompt map keyed by the frontend FeatureType.
# LangSAM would use GroundingDINO + SAM, but since langsam package has no
# Windows cp314 wheel, we fall back to ultralytics-based detection for
# buildings/roads/water/farms. The import is lazy so the backend starts even
# without LangSAM installed.
CLASS_PROMPTS: dict[str, str] = {
    "buildings": "building",
    "roads": "road",
    "water": "water.river",
    "farms": "farm.field",
}


class LangSAMNode(BaseNode):
    """Zero-shot segmentation for buildings / roads / water / farms.

    Uses LangSAM (SAM1 ViT-B backbone + GroundingDINO) if available; otherwise
    the pipeline falls back to mock features so the UI remains functional.
    Imported lazily so the backend never fails on import.
    """

    name = "langsam"
    requires_ml = True

    def __init__(self, device: str = "auto") -> None:
        super().__init__(device)
        self._model = None

    def check_available(self) -> bool:
        try:
            import langsam  # noqa: F401
            import torch  # noqa: F401
            return True
        except Exception:
            return False

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            import torch
            from langsam import LangSAM

            device = self._resolve_device()
            self._model = LangSAM(device=device)
            return self._model
        except Exception as exc:  # pragma: no cover - depends on torch/longsam
            raise InferenceError(f"LangSAM failed to load: {exc}") from exc

    def _resolve_device(self) -> str:
        if self.device == "auto":
            try:
                import torch

                return "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:
                return "cpu"
        return self.device

    def run(
        self,
        image,
        feature_type: str,
        *,
        box_threshold: float = 0.3,
        mask_threshold: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Run zero-shot segmentation on a PIL image.

        Returns a list of masks (as dicts with 'mask' key) for the given class.
        If LangSAM is unavailable, raises InferenceError which the pipeline
        catches and falls back to mock features.
        """
        prompt = CLASS_PROMPTS.get(feature_type)
        if not prompt:
            raise ValueError(f"No prompt for feature_type='{feature_type}'")
        if not self.check_available():
            raise InferenceError(
                "LangSAM is not installed. Install backend/requirements-ml.txt "
                "or use ML_ENABLED=0 for mock features."
            )
        return self._run_impl(image, prompt, box_threshold, mask_threshold)

    def _run_impl(self, image, prompt, box_threshold, mask_threshold):
        model = self._get_model()
        masks, boxes, phrases, logits = model.predict(
            image, [prompt], box_threshold, mask_threshold
        )
        out = []
        for mask in masks:
            out.append({"mask": mask, "box": boxes, "phrase": phrases})
        return out