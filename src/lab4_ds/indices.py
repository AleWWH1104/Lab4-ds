"""Vectorized implementation of the Sentinel Hub CyanoLakes script."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.floating]


def normalized_difference(a: FloatArray, b: FloatArray) -> FloatArray:
    """Return (a - b) / (a + b), using NaN where the denominator is zero."""
    denominator = a + b
    return np.divide(
        a - b,
        denominator,
        out=np.full(np.broadcast_shapes(a.shape, b.shape), np.nan, dtype=np.float32),
        where=denominator != 0,
    )


def ndvi(red: FloatArray, nir: FloatArray) -> FloatArray:
    return normalized_difference(nir, red)


def ndwi(green: FloatArray, nir: FloatArray) -> FloatArray:
    return normalized_difference(green, nir)


def ndci(red: FloatArray, red_edge: FloatArray) -> FloatArray:
    return normalized_difference(red_edge, red)


def chlorophyll_from_ndci(value: FloatArray) -> FloatArray:
    """Cyanobacteria chlorophyll-a proxy from the official script (simulated model)."""
    return 826.57 * value**3 - 176.43 * value**2 + 19 * value + 4.071


def fai(red: FloatArray, red_edge_783: FloatArray, narrow_nir: FloatArray) -> FloatArray:
    return red_edge_783 - red - (narrow_nir - red) * (783 - 665) / (865 - 665)


def water_body_mask(
    red: FloatArray,
    green: FloatArray,
    blue: FloatArray,
    nir: FloatArray,
    swir1: FloatArray,
    swir2: FloatArray,
) -> NDArray[np.bool_]:
    """Faithful vector form of the WBI branch used by the CyanoLakes script."""
    vegetation = ndvi(red, nir)
    mndwi = normalized_difference(green, swir1)
    water_ndwi = ndwi(green, nir)
    ndwi_leaves = normalized_difference(nir, swir1)
    aweish = blue + 2.5 * green - 1.5 * (nir + swir1) - 0.25 * swir2
    aweinsh = 4 * (green - swir1) - (0.25 * nir + 2.75 * swir1)
    dbsi = normalized_difference(swir1, green) - vegetation
    water = (
        (mndwi > 0.42)
        | (water_ndwi > 0.4)
        | (aweinsh > 0.1879)
        | (aweish > 0.1112)
        | (vegetation < -0.2)
        | (ndwi_leaves > 1)
    )
    return water & ~((aweinsh <= -0.03) | (dbsi > 0))


def clear_data_mask(data_mask: FloatArray, scl: FloatArray) -> NDArray[np.bool_]:
    """Exclude no-data, defective, shadow, cloud, cirrus, and snow SCL classes."""
    excluded = np.isin(scl.astype(np.int16), [0, 1, 3, 8, 9, 10, 11])
    return (data_mask == 1) & ~excluded


def calculate_layers(bands: dict[str, FloatArray]) -> dict[str, FloatArray]:
    """Calculate aligned analytical layers without converting display colors to values."""
    valid = clear_data_mask(bands["dataMask"], bands["SCL"])
    water = water_body_mask(
        bands["B04"], bands["B03"], bands["B02"], bands["B08"], bands["B11"], bands["B12"]
    )
    analysis_mask = valid & water
    surface_bloom = analysis_mask & (fai(bands["B04"], bands["B07"], bands["B8A"]) > 0.08)
    chlorophyll = chlorophyll_from_ndci(ndci(bands["B04"], bands["B05"])).astype(np.float32)
    chlorophyll[~analysis_mask | surface_bloom] = np.nan
    vegetation = ndvi(bands["B04"], bands["B08"]).astype(np.float32)
    water_index = ndwi(bands["B03"], bands["B08"]).astype(np.float32)
    vegetation[~analysis_mask] = np.nan
    water_index[~analysis_mask] = np.nan
    return {
        "chlorophyll_proxy": chlorophyll,
        "surface_bloom": surface_bloom.astype(np.float32),
        "ndvi": vegetation,
        "ndwi": water_index,
        "valid": valid.astype(np.float32),
        "water": water.astype(np.float32),
    }
