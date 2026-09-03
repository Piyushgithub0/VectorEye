from __future__ import annotations

from typing import Any

from ..config import settings
from ..services.tiler import Tiler
from ..services.vectorizer import Vectorizer
from .base import PipelineStage
from .router import FeatureRouter


class Pipeline:
    """Orchestrates the per-class inference pipeline for one orthophoto.

    Flow: tiling -> detection (per class) -> vectorization -> feature records.

    When ML is disabled (ML_ENABLED=0) or the heavy deps are missing, the
    pipeline falls back to a deterministic mock feature generator so the
    frontend QC workflow is testable end-to-end.
    """

    def __init__(self, device: str = "auto") -> None:
        self.device = device
        self.router = FeatureRouter(device)
        self.vectorizer = Vectorizer()
        self.stage = PipelineStage.IDLE

    def _set_stage(self, stage: PipelineStage) -> None:
        self.stage = stage

    def run(self, orthophoto_path: str, orthophoto_id: int) -> list[dict[str, Any]]:
        self._set_stage(PipelineStage.TILING)
        tiler = Tiler(orthophoto_path)
        info = tiler.info()
        bounds = info.get("bounds") or [[18.52 - 0.02, 73.77 - 0.02], [18.52 + 0.02, 73.77 + 0.02]]

        avail = self.router.availability()
        ml = settings.ml_enabled and (avail.get("langsam") or avail.get("deepforest"))

        self._set_stage(PipelineStage.DETECTING)
        if ml:
            features = self._run_real(tiler, orthophoto_id, bounds)
        else:
            features = self._run_mock(orthophoto_id, bounds)

        self._set_stage(PipelineStage.COMPLETE)
        return features

    def _run_real(
        self, tiler: Tiler, orthophoto_id: int, bounds: list[list[float]]
    ) -> list[dict[str, Any]]:
        """Run the real models on the orthophoto's tiles."""
        from ..services.geo import FEATURE_TYPES

        all_features: list[dict[str, Any]] = []
        [[south, west], [north, east]] = bounds
        center_lat = (south + north) / 2
        center_lon = (west + east) / 2
        crop_data, crop_bounds = tiler.crop_window(center_lon, center_lat, 1024)
        if crop_data is None:
            return all_features

        import numpy as np

        self._set_stage(PipelineStage.DETECTING)
        from PIL import Image

        img = _to_pil(crop_data)

        for ftype in FEATURE_TYPES:
            try:
                res = self.router.detect(img, ftype)
                for m in res:
                    mask = m.get("mask")
                    if mask is None:
                        continue
                    mask = np.asarray(mask)
                    conf = float(np.sum(mask > 0.5) / max(mask.size, 1)) if mask.size else 0.5
                    # Simplified: use identity transform mapping to bounds.
                    feats = self.vectorizer.mask_to_geojson(
                        mask,
                        geo_transform=None,
                        class_name=ftype[:-1],
                        confidence=conf,
                        feature_type=ftype,
                    )
                    for f in feats:
                        f["properties"]["id"] = len(all_features) + 1
                        f["properties"]["orthophoto_id"] = orthophoto_id
                        all_features.append(f)
            except Exception:
                # Skip classes whose model cannot run this pass.
                continue
        return all_features

    def _run_mock(
        self, orthophoto_id: int, bounds: list[list[float]]
    ) -> list[dict[str, Any]]:
        """Deterministic demo features so the UI works without ML installed."""
        from ..mock import build_demo_features

        self._set_stage(PipelineStage.VECTORIZING)
        return build_demo_features(orthophoto_id, bounds)


def _to_pil(crop_data: Any):
    import numpy as np

    arr = np.asarray(crop_data)
    if arr.ndim == 3:
        arr = np.transpose(arr[:3], (1, 2, 0))
    else:
        arr = arr[0]
    from PIL import Image

    arr = arr.astype(np.uint8)
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)
    return Image.fromarray(arr)