from __future__ import annotations

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Orthophoto(Base):
    """An uploaded orthophoto (GeoTIFF) and its georeferencing info."""

    __tablename__ = "orthophotos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(1024), nullable=False)
    # Original GeoTIFF file on disk (path relative to UPLOAD_DIR).
    path: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    crs: Mapped[str] = mapped_column(String(255), nullable=False, default="EPSG:32643")
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Bounds in lon/lat (EPSG:4326): [west, south, east, north].
    west: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    south: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    east: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    north: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    @property
    def bounds(self) -> list[list[float]]:
        # Returned as [[south, west], [north, east]] for the Leaflet frontend.
        return [[self.south, self.west], [self.north, self.east]]


class Feature(Base):
    """A vector feature detected from an orthophoto."""

    __tablename__ = "features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    orthophoto_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True, default=0
    )
    # One of: buildings | roads | water | trees | farms
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    class_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # pending | needs_review | approved | rejected
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True
    )
    # PostGIS geometry (EPSG:4326 by default).
    geometry: Mapped[Geometry] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# SQL statements run once at startup to enable required PostGIS capabilities.
ENABLE_POSTGIS = text("CREATE EXTENSION IF NOT EXISTS postgis")