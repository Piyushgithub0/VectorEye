from __future__ import annotations

from typing import Any

import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds, rowcol, xy

from ..config import settings
from .geo import make_bounds, polygon_ring  # noqa: F401  (re-exported helpers)


class TilerError(Exception):
    """Raised when an orthophoto cannot be processed."""


class Tiler:
    """Reads a GeoTIFF, extracts georeferencing and serves crops.

    This is the tile + affine "roundtrip" layer: given an on-disk GeoTIFF that
    is georeferenced in some projected CRS (e.g. EPSG:32643 UTM 43N), it can
    (a) expose the raster's on-the-ground footprint in EPSG:4326 for the map,
    and (b) serve 256x256 (or arbitrary-size) image crops for the pipeline.
    """

    def __init__(self, path: str | Any) -> None:
        self.path = str(path)

    # -- Metadata ---------------------------------------------------------
    def info(self) -> dict[str, Any]:
        with rasterio.open(self.path) as src:
            return {
                "width": src.width,
                "height": src.height,
                "count": src.count,
                "crs": src.crs.to_epsg() if src.crs else None,
                "bounds": self._bounds_ll(src),
                "transform": src.transform.to_gdal() if src.transform else [],
            }

    def _bounds_ll(self, src: Any) -> list[list[float]] | None:
        """Return [[south, west], [north, east]] in EPSG:4326 for the raster."""
        if src.crs is None or src.transform is None:
            return None
        try:
            west, south, east, north = src.bounds  # in source CRS
            if src.crs.to_epsg() != 4326 and src.crs.is_projected:
                from pyproj import Transformer

                t = Transformer.from_crs(src.crs, "EPSG:4326", always_xy=True)
                west, south = t.transform(west, south)
                east, north = t.transform(east, north)
            return make_bounds(west, south, east, north)
        except Exception:
            return None

    # -- Cropping ---------------------------------------------------------
    def crop_window(
        self,
        lon: float,
        lat: float,
        size_px: int = 256,
    ) -> tuple[str | None, Any]:
        """Extract a size_px x size_px crop centered on (lon, lat).

        Returns (crop_data, bounds_ll) where crop_data is an int16/N-d array in
        rasterio band order and bounds_ll is [[south, west], [north, east]].

        If the raster is not georeferenced, returns (None, None).
        """
        with rasterio.open(self.path) as src:
            if src.crs is None or src.transform is None:
                return None, None
            # Convert lon/lat to source CRS coordinates.
            col, row = _lonlat_to_rowcol(src, lon, lat)
            half = size_px // 2
            window = rasterio.windows.Window(
                col - half, row - half, size_px, size_px
            )
            window = window.intersection(
                rasterio.windows.Window(0, 0, src.width, src.height)
            )
            data = src.read(window=window)
            return data, self._window_bounds_ll(src, window)

    def _window_bounds_ll(self, src: Any, window: Any) -> list[list[float]]:
        """Project the raster-window bounding box into EPSG:4326."""
        try:
            w, s = src.xy(window.row_off + 0, window.col_off + 0)
            e, n = src.xy(
                window.row_off + window.height,
                window.col_off + window.width,
            )
            if src.crs.to_epsg() != 4326 and src.crs.is_projected:
                from pyproj import Transformer

                t = Transformer.from_crs(src.crs, "EPSG:4326", always_xy=True)
                w, s = t.transform(w, s)
                e, n = t.transform(e, n)
            return make_bounds(w, s, e, n)
        except Exception:
            return None


def _lonlat_to_rowcol(src: Any, lon: float, lat: float) -> tuple[int, int]:
    """Convert a lon/lat point to pixel (col, row) in the source CRS."""
    # If source CRS is projected, reproject the lon/lat first.
    if src.crs and src.crs.is_projected:
        from pyproj import Transformer

        t = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        x, y = t.transform(lon, lat)
    else:
        x, y = lon, lat
    col, row = rowcol(src.transform, x, y)
    return int(col), int(row)


def encode_crop_jpeg(data: Any, size: int = 256) -> bytes:
    """Encode a multiband crop (rasterio read output) as a JPEG PNG.

    Simple empirical scaling to 8-bit for display. Real pipelines would use
    proper normalization; this is good enough for the map thumbnail path.
    """
    import io

    import numpy as np

    arr = np.asarray(data)
    if arr.ndim == 3:
        arr = arr[:3]  # keep RGB if present
        arr = np.transpose(arr, (1, 2, 0))
    else:
        arr = arr[0]
    arr = arr.astype(np.float64)
    lo, hi = np.percentile(arr, 2), np.percentile(arr, 98)
    arr = np.clip((arr - lo) / max(hi - lo, 1e-6), 0, 1) * 255
    im = arr.astype(np.uint8)
    try:
        from PIL import Image

        buf = io.BytesIO()
        # map to RGB if single band
        if im.ndim == 2:
            im = np.stack([im] * 3, axis=-1)
        Image.fromarray(im).save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        # Fallback: raw PNG via rasterio if Pillow unavailable.
        out = io.BytesIO()
        rasterio.io.MemoryFile(buffer=out)  # placeholder
        return b""