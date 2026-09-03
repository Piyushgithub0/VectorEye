from __future__ import annotations

from typing import Any

import numpy as np

from .base import BaseNode, InferenceError


class DeepForestNode(BaseNode):
    """Tree crown segmentation using DeepForest's pretrained TIFF model.

    DeepForest predicts crowns from a trained RetinaNet over an image array.
    Imported lazily so this module never pulls in torch at import time.
    """

    name = "deepforest"
    requires_ml = True

    def __init__(self, device: str = "auto") -> None:
        super().__init__(device)
        self._model = None

    def check_available(self) -> bool:
        try:
            import deepforest  # noqa: F401
            return True
        except Exception:
            return False

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from deepforest import main

            model = main.deepforest()
            model.use_release()
            if self.device != "cpu":
                try:
                    model.use_gpu()
                except Exception:
                    pass
            self._model = model
            return model
        except Exception as exc:  # pragma: no cover - depends on deepforest
            raise InferenceError(f"DeepForest failed to load: {exc}") from exc

    def run(self, image: Any) -> list[dict[str, Any]]:
        """Detect tree crowns.

        image: a Pillow image or numpy RGB array of the tile/crop.
        Returns a list of boxes (crown bounding boxes) that can be converted to
        polygons by the vectorizer/router.
        """
        if not self.check_available():
            raise InferenceError(
                "DeepForest is not installed. Install backend/requirements-ml.txt."
            )
        model = self._get_model()
        img = _to_numpy(image)
        boxes = model.predict_image(image=img, return_plot=False)
        # boxes is a pandas DataFrame with ['xmin','ymin','xmax','ymax'].
        return [{"box": row} for _, row in boxes.iterrows()]


def _to_numpy(image: Any) -> np.ndarray:
    if isinstance(image, np.ndarray):
        return image
    try:
        return np.asarray(image)
    except Exception:
        return np.asarray(image)