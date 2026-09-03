from __future__ import annotations

from typing import Any

import numpy as np

from .base import BaseNode, InferenceError

import logging

_log = logging.getLogger(__name__)

# COCO class names for YOLO instance-segmentation models (index -> name).
_COCO_NAMES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag",
    "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana",
    "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza",
    "donut", "cake", "chair", "couch", "potted plant", "bed", "dining table",
    "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock",
    "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
]


class UltralyticsNode(BaseNode):
    """YOLO instance segmentation via the `ultralytics` package.

    Detects generic objects (and, with an aerial-tuned weights file, features
    like buildings/water) on an orthophoto crop. Returns masks + boxes + scores.

    Imported lazily so this module never pulls in torch at import time.
    """

    name = "ultralytics"
    requires_ml = True

    def __init__(self, device: str = "auto", weights: str | None = None) -> None:
        super().__init__(device)
        self.weights = weights or "yolo11n-seg.pt"
        self._model = None

    def check_available(self) -> bool:
        try:
            from ultralytics import YOLO  # noqa: F401
            return True
        except Exception:
            return False

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from ultralytics import YOLO

            model = YOLO(self.weights)
            self._model = model
            return model
        except Exception as exc:  # pragma: no cover - depends on ultralytics
            raise InferenceError(f"Ultralytics failed to load: {exc}") from exc

    def _device_id(self) -> str:
        if self.device == "auto":
            try:
                import torch

                return "0" if torch.cuda.is_available() else "cpu"
            except Exception:
                return "cpu"
        if self.device in ("cuda", "gpu"):
            return "0"
        return "cpu"

    def predict_seg(self, image: Any) -> dict[str, Any]:
        """Return {'masks': Nx(H)x(W) bool, 'boxes': Nx4, 'scores': N, 'cls': N}."""
        if not self.check_available():
            raise InferenceError(
                "Ultralytics is not installed. Install backend/requirements-ml.txt."
            )
        model = self._get_model()

        img = np.asarray(image)
        if img.ndim == 3 and img.shape[0] <= 3 and img.shape[0] != img.shape[-1]:
            img = np.transpose(img, (1, 2, 0))  # (C,H,W) -> (H,W,C)
        img = np.clip(img, 0, 255).astype(np.uint8)

        results = model.predict(
            source=img,
            device=self._device_id(),
            verbose=False,
            retina_masks=False,
        )
        result = results[0]
        masks = result.masks
        boxes = result.boxes
        out: dict[str, Any] = {"masks": [], "boxes": [], "scores": [], "cls": []}
        if masks is None or boxes is None:
            return out
        mask_arr = masks.data.cpu().numpy()  # (N, H, W) float
        xyxy = boxes.xyxy.cpu().numpy()  # (N, 4)
        conf = boxes.conf.cpu().numpy()  # (N,)
        cls = boxes.cls.cpu().numpy().astype(int)  # (N,)
        for i in range(len(xyxy)):
            out["masks"].append(mask_arr[i] > 0.5)
            out["boxes"].append(xyxy[i])
            out["scores"].append(float(conf[i]))
            out["cls"].append(int(cls[i]))
        return out

    def run(self, image: Any, feature_type: str) -> list[dict[str, Any]]:
        """Detect and return segmentation masks for structures.

        Returns a mask-based detection list. The router is responsible for
        de-duplicating across feature types and tagging each mask with the
        requested feature type + a real confidence score.
        """
        pred = self.predict_seg(image)
        n = len(pred["masks"])
        out: list[dict[str, Any]] = []
        for i in range(n):
            out.append(
                {
                    "mask": pred["masks"][i],
                    "score": pred["scores"][i],
                    "class_name": _COCO_NAMES[pred["cls"][i]]
                    if pred["cls"][i] < len(_COCO_NAMES)
                    else "unknown",
                }
            )
        return out


# Cityscapes semantic class indices used by the yolo*-sem models.
_SEM_BUILDING_IDX = 2
_SEM_ROAD_IDX = 0
_SEM_FARM_IDX = 9  # terrain
# Components larger than this fraction of the image are almost certainly the
# ambiguous "not-the-tile" background contaminate, so drop them as noise.
_SEM_MAX_FRAC = 0.35
_SEM_MIN_COMPONENT_AREA = 40
_SEM_MIN_POINTS = 6


class SemanticBuildingNode(BaseNode):
    """Semantic segmentation node for buildings / roads / farms (yolo*-sem).

    Runs a single Cityscapes-trained semantic segmenter (`yolo26n-sem.pt`) per
    image and reuses its per-pixel class map to detach multiple feature classes:

    - buildings -> 'building' class (index 2), voiced as per-component masks
    - roads     -> 'road' class (index 0), voiced as skeletonized LineStrings
    - farms     -> 'terrain' class (index 9), voiced as component masks

    The Cityscapes label set has no dedicated water class (driving imagery), so
    `water` intentionally yields no output — it is left to a future aerial
    model. Returning nothing (rather than mock/demo data) keeps the UI honest.

    A tiny amount of post-processing is applied per class so the masks/polylines
    are clean enough to georeference and vectorize:
      - buildings: split touching roofs, drop the giant merged blob + specks
      - roads:     remove small flecks, skeletonize, split into branch polylines
      - farms:     connected components, drop specks
    """

    name = "ultralytics-sem"
    requires_ml = True

    def __init__(self, device: str = "auto", weights: str | None = None) -> None:
        super().__init__(device)
        self.weights = weights or "yolo26n-sem.pt"
        self._model = None
        self._class_map: np.ndarray | None = None

    def check_available(self) -> bool:
        try:
            from ultralytics import YOLO  # noqa: F401
            return True
        except Exception:
            return False

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from ultralytics import YOLO

            model = YOLO(self.weights)
            self._model = model
            return model
        except Exception as exc:  # pragma: no cover - depends on ultralytics
            raise InferenceError(f"Ultralytics semantic failed to load: {exc}") from exc

    def _device_id(self) -> str:
        if self.device == "auto":
            try:
                import torch

                return "0" if torch.cuda.is_available() else "cpu"
            except Exception:
                return "cpu"
        if self.device in ("cuda", "gpu"):
            return "0"
        return "cpu"

    def reset(self) -> None:
        """Clear the cached per-image class map (called once per new image)."""
        self._class_map = None

    def _semantic_mask(self, image: Any) -> np.ndarray | None:
        """Return (and cache) the per-pixel (H,W) uint8 class-id map, or None."""
        if self._class_map is not None:
            return self._class_map
        model = self._get_model()
        img = np.asarray(image)
        if img.ndim == 3 and img.shape[0] <= 3 and img.shape[0] != img.shape[-1]:
            img = np.transpose(img, (1, 2, 0))  # (C,H,W) -> (H,W,C)
        img = np.clip(img, 0, 255).astype(np.uint8)
        results = model.predict(source=img, device=self._device_id(), verbose=False)
        sm = results[0].semantic_mask
        if sm is None:
            return None
        try:
            self._class_map = np.asarray(sm.data.cpu())
            return self._class_map
        except Exception:  # pragma: no cover - device/type nuances
            _log.exception("semantic mask coercion failed")
            return None

    def run(self, image: Any, feature_type: str) -> list[dict[str, Any]]:
        """Return real detections for one feature class from the semantic map."""
        if not self.check_available():
            raise InferenceError(
                "Ultralytics is not installed. Install backend/requirements-ml.txt."
            )
        class_map = self._semantic_mask(image)
        if class_map is None:
            return []

        if feature_type == "buildings":
            return _building_instances(class_map)
        if feature_type == "roads":
            return _road_lines(class_map)
        if feature_type == "farms":
            return _terrain_instances(class_map)
        # water (and anything else) has no Cityscapes class -> no output.
        return []


def _building_instances(class_map: np.ndarray) -> list[dict[str, Any]]:
    """Split the building class into individual roof footprints.

    Post-processing: opening removes thin bridges between touching roofs so they
    split into separate components; the giant merged "everything" blob (which is
    really the dominant band of the photo, not one roof) is dropped.
    """
    try:
        from skimage.measure import label, regionprops
        from skimage.morphology import binary_opening, disk
    except ImportError:
        return []

    binary = (class_map == _SEM_BUILDING_IDX).astype(np.uint8)
    if binary.sum() < _SEM_MIN_COMPONENT_AREA:
        return []
    binary = binary_opening(binary, disk(3)).astype(np.uint8)

    labeled = label(binary, connectivity=2)
    out: list[dict[str, Any]] = []
    total = float(binary.size)
    for region in regionprops(labeled):
        # Drop specks and the giant merged blob.
        if region.area < _SEM_MIN_COMPONENT_AREA or region.coords.shape[0] < 3:
            continue
        if region.area / total > _SEM_MAX_FRAC:
            continue
        mask = np.zeros_like(binary, dtype=bool)
        mask[region.coords[:, 0], region.coords[:, 1]] = True
        # Confidence: compact, moderate-area roofs score higher.
        compactness = _compactness(region)
        score = float(np.clip(0.55 + compactness * 0.35 - (region.area / total), 0.5, 0.97))
        out.append({"mask": mask, "score": score, "class_name": "building"})
    return out


def _road_lines(class_map: np.ndarray) -> list[dict[str, Any]]:
    """Extract road center-lines from the road class mask.

    The road pixels are skeletonized to 1px-thick curves, then split into
    branch polylines so each becomes a `line` key georeferenced by the router.
    """
    try:
        from skimage.measure import label, regionprops
        from skimage.morphology import binary_opening, disk, skeletonize
    except ImportError:
        return []

    binary = (class_map == _SEM_ROAD_IDX).astype(np.uint8)
    if binary.sum() < 200:
        return []
    binary = binary_opening(binary, disk(2)).astype(np.uint8)

    # Skeletonize per connected road component to keep branches separate-ish.
    labeled = label(binary, connectivity=2)
    out: list[dict[str, Any]] = []
    total = float(binary.size)
    for region in regionprops(labeled):
        if region.area < 120 or region.coords.shape[0] < 8:
            continue
        comp = np.zeros_like(binary, dtype=bool)
        comp[region.coords[:, 0], region.coords[:, 1]] = True
        skel = skeletonize(comp)
        pts = _skeleton_points(skel)
        if len(pts) < 4:
            continue
        ratio = region.area / total
        score = float(np.clip(0.6 + ratio * 2.0, 0.5, 0.95))
        out.append({"line": pts, "score": score, "class_name": "road"})
    return out


def _skeleton_points(skel: np.ndarray) -> list[list[float]]:
    """Greedily chain skeleton pixels (row,col) into an ordered polyline."""
    ys, xs = np.nonzero(skel)
    if len(xs) == 0:
        return []
    points = {(int(x), int(y)) for x, y in zip(xs, ys)}
    start = (int(xs[0]), int(ys[0]))
    used = {start}
    chain = [start]
    cur = start

    while True:
        x, y = cur
        neighbor: tuple[tuple[int, int], float] | None = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nxt = (x + dx, y + dy)
                if nxt == cur or nxt in used or nxt not in points:
                    continue
                d = (dx * dx + dy * dy) ** 0.5
                if neighbor is None or d < neighbor[1]:
                    neighbor = (nxt, d)
        if neighbor is None:
            break
        nxt = neighbor[0]
        used.add(nxt)
        chain.append(nxt)
        cur = nxt

    if len(chain) < 3:
        return []
    step = max(1, len(chain) // 120)
    coords = []
    for i in range(0, len(chain), step):
        coords.append([float(chain[i][0]), float(chain[i][1])])
    if coords and coords[-1] != coords[0]:
        coords.append([float(coords[0][0]), float(coords[0][1])])
    return coords


def _terrain_instances(class_map: np.ndarray) -> list[dict[str, Any]]:
    """Farms/fields from the 'terrain' class mask (connected components)."""
    try:
        from skimage.measure import label, regionprops
        from skimage.morphology import binary_opening, disk
    except ImportError:
        return []

    binary = (class_map == _SEM_FARM_IDX).astype(np.uint8)
    if binary.sum() < _SEM_MIN_COMPONENT_AREA:
        return []
    binary = binary_opening(binary, disk(2)).astype(np.uint8)

    labeled = label(binary, connectivity=2)
    out: list[dict[str, Any]] = []
    total = float(binary.size)
    for region in regionprops(labeled):
        if region.area < 300 or region.coords.shape[0] < 8:
            continue
        if region.area / total > _SEM_MAX_FRAC:
            continue
        mask = np.zeros_like(binary, dtype=bool)
        mask[region.coords[:, 0], region.coords[:, 1]] = True
        score = float(np.clip(0.55 + region.area / total, 0.5, 0.9))
        out.append({"mask": mask, "score": score, "class_name": "farm"})
    return out


def _instances_from_mask(binary: np.ndarray) -> list[dict[str, Any]]:
    """Generic connected-component -> mask list (kept for compatibility)."""
    try:
        from skimage.measure import label, regionprops
    except ImportError:
        return []

    labeled = label(binary > 0, connectivity=2)
    out: list[dict[str, Any]] = []
    total = float(binary.size)
    for region in regionprops(labeled):
        if region.area < _SEM_MIN_COMPONENT_AREA or region.coords.shape[0] < 3:
            continue
        mask = np.zeros_like(binary, dtype=bool)
        mask[region.coords[:, 0], region.coords[:, 1]] = True
        ratio = region.area / total
        score = float(np.clip(0.5 + ratio * 10.0, 0.5, 0.97))
        out.append({"mask": mask, "score": score, "class_name": "building"})
    return out


def _compactness(region: Any) -> float:
    """0..1 haralick-like compactness (1 = perfect circle, 0 = very spread)."""
    try:
        return float(region.perimeter / max(region.area**0.5, 1e-6)) if region.perimeter else 0.5
    except Exception:
        return 0.5