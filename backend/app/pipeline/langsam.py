from __future__ import annotations

from typing import Any

from .base import BaseNode, InferenceError

# Prompt map keyed by the frontend FeatureType. LangSAM takes a free-text
# groundingDINO prompt per image; we re-infer per class so each mask is clean.
CLASS_PROMPTS: dict[str, str] = {
    "buildings": "building",
    "roads": "road",
    "water": "water.river",
    "farms": "farm.field",
}


class LangSAMNode(BaseNode):
    """Zero-shot segmentation for buildings / roads / water / farms.

    Uses LangSAM (SAM1 ViT-B backbone + GroundingDINO) for 8GB VRAM safety.
    Imported lazily so importing this module never pulls in torch.
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
        except Exception as exc:  # pragma: no cover - depends on torch
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
        """
        prompt = CLASS_PROMPTS.get(feature_type)
        if not prompt:
            raise ValueError(f"No prompt for feature_type='{feature_type}'")
        if not self.check_available():
            raise InferenceError(
                "LangSAM is not installed. Install backend/requirements-ml.txt."
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