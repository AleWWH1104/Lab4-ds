import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_bounds

from lab4_ds.acquisition import process_raw_raster
from lab4_ds.raster import PRODUCT_BANDS, RAW_BANDS, read_named_raster, write_geotiff
from lab4_ds.validation import validate_repository


def test_geotiff_round_trip_preserves_grid_bands_and_tags(tmp_path: Path) -> None:
    path = tmp_path / "product.tif"
    data = np.arange(24, dtype=np.float32).reshape(6, 2, 2)
    transform = from_bounds(-91, 14, -90, 15, 2, 2)
    write_geotiff(path, data, transform, "EPSG:4326", PRODUCT_BANDS, {"date": "2025-01-01"})
    layers, profile = read_named_raster(path, PRODUCT_BANDS)
    np.testing.assert_array_equal(layers["ndvi"], data[2])
    assert profile["crs"].to_string() == "EPSG:4326"
    assert profile["tags"]["date"] == "2025-01-01"


def test_validation_accepts_complete_aligned_scene(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    processed_root = tmp_path / "processed"
    raw_path = raw_root / "atitlan" / "2025-01-18.tif"
    product_path = processed_root / "atitlan" / "2025-01-18.tif"
    transform = from_bounds(-91, 14, -90, 15, 2, 2)
    write_geotiff(raw_path, np.ones((11, 2, 2)), transform, "EPSG:4326", RAW_BANDS)
    product = np.ones((6, 2, 2), dtype=np.float32)
    write_geotiff(product_path, product, transform, "EPSG:4326", PRODUCT_BANDS)
    raw_path.with_suffix(".json").write_text(
        json.dumps({"lake": "atitlan", "date": "2025-01-18"}), encoding="utf-8"
    )
    config = {
        "analysis": {"minimum_valid_fraction": 0.5},
        "lakes": {"atitlan": {"acquisitions": [{"date": "2025-01-18"}]}},
    }
    result = validate_repository(config, raw_root, processed_root)
    assert result["status"] == "valid"
    assert result["checked_scenes"] == 1
    with rasterio.open(product_path) as source:
        assert not source.transform.is_identity


def test_raw_raster_processing_retains_surface_bloom(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw.tif"
    product_path = tmp_path / "product.tif"
    shape = (1, 1)
    values = {
        "B02": 0.05,
        "B03": 0.10,
        "B04": 0.02,
        "B05": 0.06,
        "B07": 0.20,
        "B08": 0.02,
        "B8A": 0.02,
        "B11": 0.01,
        "B12": 0.005,
        "SCL": 6,
        "dataMask": 1,
    }
    stack = np.stack([np.full(shape, values[name]) for name in RAW_BANDS])
    transform = from_bounds(-91, 14, -90, 15, 1, 1)
    write_geotiff(raw_path, stack, transform, "EPSG:4326", RAW_BANDS)
    process_raw_raster(raw_path, product_path)
    layers, _ = read_named_raster(product_path, PRODUCT_BANDS)
    assert layers["surface_bloom"][0, 0] == 1
    assert np.isnan(layers["chlorophyll_proxy"][0, 0])
