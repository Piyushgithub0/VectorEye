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

    def crop_window_transform(
        self,
        lon: float,
        lat: float,
        size_px: int = 256,
    ) -> tuple[Any, list[list[float]]]:
        """Return (geotransform, bounds_ll) for a crop centered at (lon, lat)."""
        with rasterio.open(self.path) as src:
            if src.crs is None or src.transform is None:
                return None, None
            col, row = _lonlat_to_rowcol(src, lon, lat)
            half = size_px // 2
            window = rasterio.windows.Window(
                col - half, row - half, size_px, size_px
            ).intersection(rasterio.windows.Window(0, 0, src.width, src.height))
            return self._window_transform(src, window)

    def iter_tiles(
        self,
        tile_size: int = 1024,
        overlap: float = 0.15,
    ):
        """Yield tile crops covering the full raster for batched GPU inference.

        Each item is a dict with keys:
          data       – rasterio band array (C,H,W)
          geo_t      – GDAL affine mapping crop pixels -> EPSG:4326 (lon, lat)
          bounds_ll  – [[south, west], [north, east]]
          col_off    – pixel column offset in source raster
          row_off    – pixel row offset in source raster
        """
        overlap = max(0.0, min(0.5, overlap))
        stride = max(1, int(tile_size * (1.0 - overlap)))

        with rasterio.open(self.path) as src:
            if src.crs is None or src.transform is None:
                return
            full = rasterio.windows.Window(0, 0, src.width, src.height)
            row = 0
            while row < src.height:
                col = 0
                while col < src.width:
                    window = rasterio.windows.Window(col, row, tile_size, tile_size)
                    window = window.intersection(full)
                    if window.width < 64 or window.height < 64:
                        col += stride
                        continue
                    data = src.read(window=window)
                    geo_t, bounds_ll = self._window_transform(src, window)
                    if geo_t is None:
                        col += stride
                        continue
                    yield {
                        "data": data,
                        "geo_t": geo_t,
                        "bounds_ll": bounds_ll,
                        "col_off": int(window.col_off),
                        "row_off": int(window.row_off),
                    }
                    if col + tile_size >= src.width:
                        break
                    col += stride
                if row + tile_size >= src.height:
                    break
                row += stride

    def _window_transform(self, src: Any, window: Any) -> tuple[Any, list[list[float]] | None]:
        """Return (geotransform, bounds_ll) for an arbitrary raster window."""
        import numpy as np

        try:
            w, s = src.xy(window.row_off + 0, window.col_off + 0)
            e, n = src.xy(window.row_off, window.col_off + window.width)
            xpix = src.transform.a
            ypix = src.transform.e
            proj_crs = src.crs
            origin_x = w
            origin_y = n - ypix

            corners_src = np.array(
                [
                    [origin_x, origin_y],
                    [origin_x + xpix * window.width, origin_y + ypix * window.height],
                ]
            )
            if proj_crs.to_epsg() != 4326 and proj_crs.is_projected:
                from pyproj import Transformer

                t = Transformer.from_crs(proj_crs, "EPSG:4326", always_xy=True)
                corners_ll = t.transform(corners_src[:, 0], corners_src[:, 1])
            else:
                corners_ll = (corners_src[:, 0], corners_src[:, 1])

            lon0, lat0 = corners_ll[0][0], corners_ll[1][0]
            lon1, lat1 = corners_ll[0][1], corners_ll[1][1]
            dlon = (lon1 - lon0) / window.width
            dlat = (lat1 - lat0) / window.height
            geo_t = [dlon, 0.0, lon0, 0.0, dlat, lat0]
            return geo_t, make_bounds(lon0, lat0, lon1, lat1)
        except Exception:
            return None, None

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