"""GeoTIFF persistence and product loading."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from numpy.typing import NDArray
from rasterio.transform import Affine

RAW_BANDS = ["B02", "B03", "B04", "B05", "B07", "B08", "B8A", "B11", "B12", "SCL", "dataMask"]
PRODUCT_BANDS = ["chlorophyll_proxy", "surface_bloom", "ndvi", "ndwi", "valid", "water"]


def write_geotiff(
    path: Path,
    data: NDArray[np.floating],
    transform: Affine,
    crs: str,
    descriptions: list[str],
    tags: dict[str, str] | None = None,
) -> None:
    """Write a band-first, compressed, georeferenced float product atomically."""
    if data.ndim != 3 or data.shape[0] != len(descriptions):
        raise ValueError("Data must be band-first and match descriptions")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.tif")
    with rasterio.open(
        temporary,
        "w",
        driver="GTiff",
        width=data.shape[2],
        height=data.shape[1],
        count=data.shape[0],
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=np.nan,
        compress="deflate",
        predictor=3,
        tiled=True,
    ) as destination:
        destination.write(data.astype(np.float32))
        destination.descriptions = tuple(descriptions)
        if tags:
            destination.update_tags(**tags)
    temporary.replace(path)


def read_named_raster(
    path: Path, expected: list[str] | None = None
) -> tuple[dict[str, NDArray], dict]:
    with rasterio.open(path) as source:
        names = list(source.descriptions)
        if not all(names):
            raise ValueError(f"Raster has missing band descriptions: {path}")
        if expected and names != expected:
            raise ValueError(f"Unexpected bands in {path}: {names}")
        arrays = {name: source.read(index + 1) for index, name in enumerate(names)}
        profile = source.profile.copy()
        profile["tags"] = source.tags()
    return arrays, profile
