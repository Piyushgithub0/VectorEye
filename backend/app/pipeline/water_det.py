from __future__ import annotations

from typing import Any
import numpy as np

try:
    from skimage.measure import label, regionprops
    from skimage.morphology import disk, opening
except ImportError:
    label = None
    regionprops = None
    disk = None
    opening = None


class WaterDetectionNode:
    """Spectral and morphological detector for genuine water bodies (rivers, lakes, canals, reservoirs)
    from visible RGB aerial orthophoto imagery using Visible Water Index (VWI).
    """

    name = "water_detector"
    requires_ml = False

    def __init__(self, min_area: int = 2500) -> None:
        self.min_area = min_area

    def check_available(self) -> bool:
        return label is not None

    def run(self, image: Any) -> list[dict[str, Any]]:
        """Run water body detection on an RGB image crop."""
        if not self.check_available():
            return []

        img = np.asarray(image)
        if img.ndim == 3 and img.shape[0] <= 3 and img.shape[0] != img.shape[-1]:
            img = np.transpose(img, (1, 2, 0))
        img = np.clip(img, 0, 255).astype(np.uint8)
        if img.ndim != 3 or img.shape[-1] < 3:
            return []

        r = img[..., 0].astype(float)
        g = img[..., 1].astype(float)
        b = img[..., 2].astype(float)

        # Visible Water Index: water strongly absorbs red light while reflecting green/blue.
        vwi = (g + b - 2.0 * r) / (g + b + 2.0 * r + 1e-6)
        brightness = (r + g + b) / 3.0

        # Stringent optical water criteria:
        # 1. Strong water index (VWI > 0.12)
        # 2. Blue exceeds Red (b > r + 2)
        # 3. Moderate to low brightness (15 to 125) to reject bright concrete, roads, and clouds
        raw_mask = (
            (vwi > 0.12)
            & (b > (r + 2))
            & (brightness > 15)
            & (brightness < 125)
        )

        if raw_mask.sum() < self.min_area:
            return []

        try:
            clean_mask = opening(raw_mask, disk(3))
            labeled = label(clean_mask, connectivity=2)
        except Exception:
            return []

        out: list[dict[str, Any]] = []
        total_px = float(img.shape[0] * img.shape[1])

        for reg in regionprops(labeled):
            if reg.area < self.min_area:
                continue
            if reg.area / total_px > 0.85:
                continue

            comp_mask = np.zeros(clean_mask.shape, dtype=bool)
            comp_mask[reg.coords[:, 0], reg.coords[:, 1]] = True

            mean_vwi = float(vwi[comp_mask].mean())
            score = float(np.clip(0.68 + (mean_vwi - 0.12) * 0.8, 0.60, 0.95))

            out.append({
                "mask": comp_mask,
                "score": score,
                "class_name": "water body",
            })

        return out
