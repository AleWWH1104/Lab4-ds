import numpy as np
import pandas as pd
import pytest
from rasterio.transform import from_bounds

from lab4_ds.analysis import (
    high_value_mask,
    pearson_pair,
    persistent_hotspots,
    run_analysis,
    summarize_scene,
)
from lab4_ds.raster import PRODUCT_BANDS, write_geotiff


def scene(chlorophyll, bloom=None):
    chlorophyll = np.asarray(chlorophyll, dtype=np.float32)
    return {
        "chlorophyll_proxy": chlorophyll,
        "surface_bloom": np.zeros_like(chlorophyll) if bloom is None else np.asarray(bloom),
        "ndvi": chlorophyll / 100,
        "ndwi": -chlorophyll / 100,
        "valid": np.ones_like(chlorophyll),
        "water": np.ones_like(chlorophyll),
    }


def test_threshold_includes_surface_bloom_and_summary_denominator() -> None:
    layers = scene([[5, 25], [np.nan, 10]], [[0, 0], [1, 0]])
    high = high_value_mask(layers["chlorophyll_proxy"], layers["surface_bloom"], 20)
    np.testing.assert_array_equal(high, [[False, True], [True, False]])
    summary = summarize_scene(layers, 20)
    assert summary["mean_chlorophyll_proxy"] == pytest.approx(40 / 3)
    assert summary["surface_bloom_percent"] == 25
    assert summary["high_value_percent"] == 50


def test_summary_excludes_invalid_proxy_without_changing_extent_denominator() -> None:
    layers = scene([[-10, 25], [500, np.nan]], [[0, 0], [0, 1]])
    summary = summarize_scene(layers, 20)
    assert summary["water_pixels"] == 4
    assert summary["chlorophyll_valid_pixels"] == 1
    assert summary["chlorophyll_coverage_percent"] == 25
    assert summary["negative_proxy_pixels"] == 1
    assert summary["above_calibration_pixels"] == 1
    assert summary["unestimated_proxy_pixels"] == 1
    assert summary["mean_chlorophyll_proxy"] == 25
    assert summary["high_value_percent"] == 75


def test_correlations_use_only_finite_pairs() -> None:
    count, positive = pearson_pair(np.array([1, 2, 3, np.nan]), np.array([2, 4, 6, 8]))
    assert count == 3
    assert positive == 1


def test_persistent_hotspots_require_two_observations() -> None:
    first = scene([[30, 5], [30, 5]])
    second = scene([[25, 5], [5, 5]])
    second["valid"][1, 0] = 0
    frequency, persistent = persistent_hotspots([first, second], 20, 0.5)
    assert frequency[0, 0] == 1
    assert persistent[0, 0] == 1
    assert np.isnan(persistent[1, 0])


def test_offline_analysis_writes_all_evidence_products(tmp_path) -> None:
    processed = tmp_path / "processed"
    tables = tmp_path / "tables"
    figures = tmp_path / "figures"
    acquisitions = [{"date": "2025-01-01"}, {"date": "2025-02-01"}]
    config = {
        "analysis": {
            "high_chlorophyll_threshold": 20,
            "sensitivity_thresholds": [10, 20, 50],
            "bloom_date_area_percent": 5,
            "persistent_fraction": 0.5,
        },
        "lakes": {
            "atitlan": {"acquisitions": acquisitions},
            "amatitlan": {"acquisitions": acquisitions},
        },
    }
    transform = from_bounds(-91, 14, -90, 15, 2, 2)
    for lake in config["lakes"]:
        for index, acquisition in enumerate(acquisitions):
            layers = scene([[5 + index, 25], [30, 10]], [[0, 0], [0, index]])
            stack = np.stack([layers[name] for name in PRODUCT_BANDS])
            write_geotiff(
                processed / lake / f"{acquisition['date']}.tif",
                stack,
                transform,
                "EPSG:4326",
                PRODUCT_BANDS,
            )
    result = run_analysis(config, processed, tables, figures)
    assert len(result) == 4
    assert (tables / "lake_comparison.csv").exists()
    assert (tables / "critical_dates.csv").exists()
    assert (tables / "spatial_zones.csv").exists()
    assert (tables / "hotspots_atitlan.tif").exists()
    assert (figures / "temporal_evolution.png").exists()
    assert (figures / "difference_amatitlan.png").exists()
    zones = pd.read_csv(tables / "spatial_zones.csv")
    assert len(zones) == 8
    assert set(zones["zone"]) == {"noroeste", "noreste", "suroeste", "sureste"}
    assert "persistent_area_percent" in zones
