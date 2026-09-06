from __future__ import annotations

from typing import Any

from ..config import settings
from ..services.tiler import Tiler
from ..services.vectorizer import Vectorizer
from .base import PipelineStage
from .router import FeatureRouter

# Confidence below this marks a feature as needing analyst review.
_NEEDS_REVIEW_THRESHOLD = 0.75


class Pipeline:
    """Orchestrates the per-class inference pipeline for one orthophoto.

    Flow: tiling -> batched GPU detection (per class) -> vectorization -> features.

    When ML is disabled (ML_ENABLED=0) or the heavy deps are missing, the
    pipeline falls back to a deterministic mock feature generator so the
    frontend QC workflow is testable end-to-end.
    """

    def __init__(self, device: str | None = None) -> None:
        self.device = device or settings.ml_device
        self.router = FeatureRouter(self.device)
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

        self._set_stage(PipelineStage.TILING, "Building tile grid for batched inference", 12)
        if ml:
            features = self._run_real(tiler, orthophoto_id, bounds)
        else:
            features = self._run_mock(orthophoto_id, bounds)

        self._set_stage(PipelineStage.COMPLETE, "Features ready", 100)
        return features

    def _run_real(
        self, tiler: Tiler, orthophoto_id: int, bounds: list[list[float]]
    ) -> list[dict[str, Any]]:
        """Run models on a tile grid with GPU batch inference."""
        from ..services.geo import FEATURE_TYPES

        tile_size = settings.tile_size
        overlap = settings.tile_overlap
        batch_size = max(1, settings.ml_batch_size)

        tiles = list(tiler.iter_tiles(tile_size=tile_size, overlap=overlap))
        if not tiles:
            # Fallback: single central crop (legacy path for non-georeferenced rasters).
            return self._run_single_crop(tiler, orthophoto_id, bounds)

        all_features: list[dict[str, Any]] = []
        total_tiles = len(tiles)
        sem_types = ("buildings", "roads", "farms")

        for batch_idx in range(0, total_tiles, batch_size):
            batch = tiles[batch_idx : batch_idx + batch_size]
            batch_num = batch_idx // batch_size + 1
            total_batches = (total_tiles + batch_size - 1) // batch_size
            pct_base = 15 + int((batch_idx / max(1, total_tiles)) * 65)
            self._set_stage(
                PipelineStage.DETECTING,
                f"GPU batch {batch_num}/{total_batches} ({len(batch)} tiles)",
                pct_base,
            )

            images = [_to_pil(t["data"]) for t in batch]
            geo_transforms = [t["geo_t"] for t in batch]

            # One semantic GPU pass per tile batch; derive buildings/roads/farms.
            semantic_node = self.router._semantic
            if semantic_node is None:
                from .ultralytics_det import SemanticBuildingNode
                semantic_node = SemanticBuildingNode(self.device)
                self.router._semantic = semantic_node

            class_maps: list[Any] = []
            if semantic_node.check_available():
                try:
                    class_maps = semantic_node.semantic_masks_batch(images)
                except Exception:
                    class_maps = [None] * len(images)
            else:
                class_maps = [None] * len(images)

            for tile_i, class_map in enumerate(class_maps):
                geo_t = geo_transforms[tile_i]
                if class_map is not None:
                    for ftype in sem_types:
                        try:
                            detections = semantic_node.run_on_class_map(class_map, ftype)
                            self._append_detections(
                                all_features, detections, geo_t, ftype, orthophoto_id
                            )
                        except Exception:
                            continue

            # Trees use a separate model (DeepForest).
            try:
                tree_results = self.router.detect_batch(images, "trees")
                for tile_i, detections in enumerate(tree_results):
                    self._append_detections(
                        all_features,
                        detections,
                        geo_transforms[tile_i],
                        "trees",
                        orthophoto_id,
                    )
            except Exception:
                pass

            # Water bodies detection (Visible Water Index)
            try:
                water_results = self.router.detect_batch(images, "water")
                for tile_i, detections in enumerate(water_results):
                    self._append_detections(
                        all_features,
                        detections,
                        geo_transforms[tile_i],
                        "water",
                        orthophoto_id,
                    )
            except Exception:
                pass

        self._set_stage(PipelineStage.VECTORIZING, "Deduplicating overlapping detections", 88)
        all_features = _dedupe_features(all_features)

        if not all_features:
            return self._run_mock(orthophoto_id, bounds)
        return all_features

    def _append_detections(
        self,
        all_features: list[dict[str, Any]],
        detections: list[dict[str, Any]],
        geo_t: Any,
        ftype: str,
        orthophoto_id: int,
    ) -> None:
        for det in detections:
            feats = self._georef_detection(det, geo_t, ftype)
            for gf in feats:
                conf = float((gf.get("properties") or {}).get("confidence") or 0.5)
                props = gf.get("properties") or {}
                all_features.append(
                    {
                        "id": len(all_features) + 1,
                        "orthophoto_id": orthophoto_id,
                        "type": ftype,
                        "class_name": props.get("class") or ftype[:-1],
                        "confidence": conf,
                        "status": "needs_review"
                        if conf < _NEEDS_REVIEW_THRESHOLD
                        else "approved",
                        "geometry": gf.get("geometry") or {},
                        "created_at": "",
                    }
                )

    def _run_single_crop(
        self, tiler: Tiler, orthophoto_id: int, bounds: list[list[float]]
    ) -> list[dict[str, Any]]:
        """Legacy single-tile path when georeferencing is unavailable."""
        from ..services.geo import FEATURE_TYPES

        all_features: list[dict[str, Any]] = []
        [[south, west], [north, east]] = bounds
        center_lat = (south + north) / 2
        center_lon = (west + east) / 2

        geo_t, _ = tiler.crop_window_transform(center_lon, center_lat, settings.tile_size)
        crop_data, _ = tiler.crop_window(center_lon, center_lat, settings.tile_size)
        if crop_data is None or geo_t is None:
            return all_features

        img = _to_pil(crop_data)
        for ftype in FEATURE_TYPES:
            try:
                res = self.router.detect(img, ftype)
                for m in res:
                    feats = self._georef_detection(m, geo_t, ftype)
                    for gf in feats:
                        conf = float(
                            (gf.get("properties") or {}).get("confidence") or 0.5
                        )
                        all_features.append(
                            {
                                "id": len(all_features) + 1,
                                "orthophoto_id": orthophoto_id,
                                "type": ftype,
                                "class_name": (gf.get("properties") or {}).get("class")
                                or ftype[:-1],
                                "confidence": conf,
                                "status": "needs_review"
                                if conf < _NEEDS_REVIEW_THRESHOLD
                                else "approved",
                                "geometry": gf.get("geometry") or {},
                                "created_at": "",
                            }
                        )
            except Exception:
                continue
        return all_features

    def _georef_detection(
        self,
        det: dict[str, Any],
        geo_t: Any,
        feature_type: str,
    ) -> list[dict[str, Any]]:
        """Turn one detector result into geolocated polygons."""
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


def _dedupe_features(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop duplicate detections from overlapping tiles (centroid + type key)."""
    seen: set[tuple[str, int, int]] = set()
    kept: list[dict[str, Any]] = []
    for feat in features:
        key = _feature_dedupe_key(feat)
        if key is None or key in seen:
            continue
        seen.add(key)
        kept.append(feat)
    return kept


def _feature_dedupe_key(feat: dict[str, Any]) -> tuple[str, int, int] | None:
    """Hash feature type + centroid rounded to ~1 m precision."""
    geom = feat.get("geometry") or {}
    coords = geom.get("coordinates")
    if not coords:
        return None
    try:
        gtype = geom.get("type")
        if gtype == "Point":
            lon, lat = coords[0], coords[1]
        elif gtype == "LineString":
            mid = coords[len(coords) // 2]
            lon, lat = mid[0], mid[1]
        elif gtype == "Polygon":
            ring = coords[0]
            lon = sum(p[0] for p in ring) / len(ring)
            lat = sum(p[1] for p in ring) / len(ring)
        else:
            return None
        return (
            str(feat.get("type") or ""),
            int(round(float(lon) * 1e5)),
            int(round(float(lat) * 1e5)),
        )
    except (TypeError, IndexError, ValueError):
        return None


def _to_pil(crop_data: Any):
    import numpy as np
    from PIL import Image

    arr = np.asarray(crop_data)
    if arr.ndim == 3 and arr.shape[0] >= 3:
        arr = arr[:3]
        arr = np.transpose(arr, (1, 2, 0))
    elif arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)

    if arr.dtype != np.uint8:
        arr = arr.astype(np.uint8)

    arr = np.clip(arr, 0, 255)

    if arr.ndim == 2 or arr.shape[2] != 3:
        arr = np.stack([arr] * 3, axis=-1)

    return Image.fromarray(arr)
