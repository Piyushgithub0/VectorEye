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
            # DeepForest 2.x loads pretrained weights from Hugging Face via
            # load_model (use_release/use_gpu were removed in 2.x).
            model.load_model(model_name="weecology/deepforest-tree", revision="main")
            self._model = model
            return model
        except Exception as exc:  # pragma: no cover - depends on deepforest
            raise InferenceError(f"DeepForest failed to load: {exc}") from exc

    def run(self, image: Any, feature_type: str = "trees") -> list[dict[str, Any]]:
        """Detect tree crowns.

        image: a Pillow image or numpy RGB array of the tile/crop.
        Returns a list of dicts each with a 'box' (x1,y1,x2,y2) and 'score'.
        """
        if not self.check_available():
            raise InferenceError(
                "DeepForest is not installed. Install backend/requirements-ml.txt."
            )
        model = self._get_model()
        img = _to_numpy(image)
        # predict_image expects a float32, channels-last (H,W,3) uint8-range array.
        if img.dtype != "float32":
            img = img.astype("float32")
        df = model.predict_image(image=img)
        out: list[dict[str, Any]] = []
        if df is None:
            return out
        for _, row in df.iterrows():
            x1 = float(row["xmin"])
            y1 = float(row["ymin"])
            x2 = float(row["xmax"])
            y2 = float(row["ymax"])
            score = float(row.get("score", 0.5))
            out.append({"box": [x1, y1, x2, y2], "score": score})
        return out


def _to_numpy(image: Any) -> np.ndarray:
    if isinstance(image, np.ndarray):
        return image
    try:
        return np.asarray(image)
    except Exception:
        return np.asarray(image)