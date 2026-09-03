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
        self._progress = None

    def _set_stage(self, stage: PipelineStage, message: str = "", pct: float | None = None) -> None:
        self.stage = stage
        if self._progress is not None:
            try:
                self._progress(stage.value, message, pct)
            except Exception:
                pass

    def run(
        self,
        orthophoto_path: str,
        orthophoto_id: int,
        progress: Any = None,
    ) -> list[dict[str, Any]]:
        self._progress = progress
        self._set_stage(PipelineStage.TILING, "Opening GeoTIFF and reading georeferencing", 5)
        self.router._reset_image()
        tiler = Tiler(orthophoto_path)
        info = tiler.info()
        bounds = info.get("bounds") or [[18.52 - 0.02, 73.77 - 0.02], [18.52 + 0.02, 73.77 + 0.02]]

        avail = self.router.availability()
        ml = settings.ml_enabled and (
            avail.get("ultralytics") or avail.get("deepforest")
        )

        self._set_stage(PipelineStage.TILING, "Cropping central tile for inference", 12)
        if ml:
            features = self._run_real(tiler, orthophoto_id, bounds)
        else:
            features = self._run_mock(orthophoto_id, bounds)

        self._set_stage(PipelineStage.COMPLETE, "Features ready", 100)
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

        # Georeferencing for this crop: pixel -> (lon, lat) affine.
        geo_t, crop_bounds = tiler.crop_window_transform(center_lon, center_lat, 1024)
        crop_data, _ = tiler.crop_window(center_lon, center_lat, 1024)
        if crop_data is None or geo_t is None:
            return all_features

        import numpy as np

        self._set_stage(PipelineStage.DETECTING, "Running semantic + tree models", 30)
        img = _to_pil(crop_data)

        for i, ftype in enumerate(FEATURE_TYPES):
            pct = 30 + int(i * 55 / max(1, len(FEATURE_TYPES)))
            self._set_stage(
                PipelineStage.DETECTING, f"Detecting {ftype}", pct
            )
            try:
                res = self.router.detect(img, ftype)
                for m in res:
                    feats = self._georef_detection(m, geo_t, ftype)
                    for gf in feats:
                        props = gf.get("properties") or {}
                        all_features.append(
                            {
                                "id": len(all_features) + 1,
                                "orthophoto_id": orthophoto_id,
                                "type": ftype,
                                "class_name": props.get("class") or ftype[:-1],
                                "confidence": float(props.get("confidence") or 0.5),
                                "status": "pending",
                                "geometry": gf.get("geometry") or {},
                                "created_at": "",
                            }
                        )
            except Exception:
                # Skip classes whose model cannot run this pass.
                continue

        self._set_stage(PipelineStage.VECTORIZING, "Georeferencing feature geometries", 88)

        # If nothing real came back for any class, fall back to demo features
        # so the QC workflow is still testable, but only when ML masked out all
        # classes (e.g. empty tile).
        if not all_features:
            return self._run_mock(orthophoto_id, bounds)
        return all_features

    def _georef_detection(
        self,
        det: dict[str, Any],
        geo_t: Any,
        feature_type: str,
    ) -> list[dict[str, Any]]:
        """Turn one detector result into geolocated polygons.

        Supports either a binary `mask` (ultralytics seg / langsam style) or a
        `box` (DeepForest / ultralytics box style). Both are mapped into EPSG:4326
        using the crop affine `geo_t`. A confidence of 0.5 is used as a floor for
        the "needs review" thresholding.
        """
        import numpy as np

        mask = det.get("mask")
        conf = float(det.get("score", det.get("confidence", 0.5)))
        class_name = det.get("class_name") or feature_type[:-1]
        if mask is not None:
            mask = np.asarray(mask, dtype=float)
            if mask.ndim == 3 and mask.shape[0] <= 3:
                mask = mask[0]
            if mask.ndim == 3:
                mask = mask[..., 0]
            return self.vectorizer.mask_to_geojson(
                mask,
                geo_transform=geo_t,
                class_name=class_name,
                confidence=conf,
                feature_type=feature_type,
            )
        box = det.get("box")
        if box is not None:
            return self.vectorizer.box_to_geojson(
                box,
                geo_transform=geo_t,
                class_name=class_name,
                confidence=conf,
                feature_type=feature_type,
            )
        line = det.get("line")
        if line is not None:
            return self.vectorizer.line_to_geojson(
                line,
                geo_transform=geo_t,
                class_name=class_name,
                confidence=conf,
                feature_type=feature_type,
            )
        return []

    def _run_mock(
        self, orthophoto_id: int, bounds: list[list[float]]
    ) -> list[dict[str, Any]]:
        """Deterministic demo features so the UI works without ML installed."""
        from ..mock import build_demo_features

        self._set_stage(PipelineStage.VECTORIZING, "Building demo feature geometries", 90)
        return build_demo_features(orthophoto_id, bounds)


def _to_pil(crop_data: Any):
    import numpy as np
    from PIL import Image

    arr = np.asarray(crop_data)
    # Handle multiband rasterio output: keep first 3 bands (RGB)
    if arr.ndim == 3 and arr.shape[0] >= 3:
        arr = arr[:3]  # keep only first 3 bands
        arr = np.transpose(arr, (1, 2, 0))  # (C,H,W) -> (H,W,C)
    elif arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)  # grayscale -> RGB
    
    # Ensure uint8 range [0,255]
    if arr.dtype != np.uint8:
        arr = arr.astype(np.uint8)
    
    # Clip to valid range
    arr = np.clip(arr, 0, 255)
    
    # If still not 3-channel, make it 3-channel
    if arr.ndim == 2 or arr.shape[2] != 3:
        arr = np.stack([arr] * 3, axis=-1)
    
    return Image.fromarray(arr)