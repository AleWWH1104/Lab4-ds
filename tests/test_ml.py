from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from rasterio.transform import from_bounds

from lab4_ds.ml import (
    PREDICTORS,
    add_spatial_blocks,
    binary_metrics,
    build_ml_dataset,
    chronological_split_indices,
    spatial_group_splits,
    spatial_nested_splits,
    temporal_tuning_splits,
    validate_predictors,
)
from lab4_ds.raster import PRODUCT_BANDS, RAW_BANDS, write_geotiff


def _write_scene(root: Path) -> tuple[Path, Path]:
    raw_root = root / "raw"
    processed_root = root / "processed"
    shape = (2, 3)
    raw_values = {
        "B02": 0.05,
        "B03": 0.10,
        "B04": 0.02,
        "B05": 0.06,
        "B07": 0.05,
        "B08": 0.02,
        "B8A": 0.03,
        "B11": 0.01,
        "B12": 0.005,
        "SCL": 6,
        "dataMask": 1,
    }
    raw = np.stack([np.full(shape, raw_values[name], dtype=np.float32) for name in RAW_BANDS])
    raw[RAW_BANDS.index("dataMask"), 0, 0] = 0
    raw[RAW_BANDS.index("SCL"), 0, 1] = 9
    product = np.stack(
        [
            np.full(shape, 25, dtype=np.float32),
            np.zeros(shape, dtype=np.float32),
            np.full(shape, -0.2, dtype=np.float32),
            np.full(shape, 0.5, dtype=np.float32),
            np.ones(shape, dtype=np.float32),
            np.ones(shape, dtype=np.float32),
        ]
    )
    transform = from_bounds(-91.2, 14.5, -91.1, 14.6, shape[1], shape[0])
    write_geotiff(raw_root / "atitlan" / "2025-01-01.tif", raw, transform, "EPSG:4326", RAW_BANDS)
    write_geotiff(
        processed_root / "atitlan" / "2025-01-01.tif",
        product,
        transform,
        "EPSG:4326",
        PRODUCT_BANDS,
    )
    return raw_root, processed_root


def test_dataset_keeps_only_clear_valid_water_and_binary_target(tmp_path: Path) -> None:
    raw_root, processed_root = _write_scene(tmp_path)
    bundle = build_ml_dataset(raw_root, processed_root, maximum_per_scene_class=10)
    assert len(bundle.sample) == 4
    assert set(bundle.sample["target"]) == {1}
    assert bundle.population.loc[0, "eligible_pixels"] == 4
    assert bundle.sample[list(PREDICTORS)].notna().all().all()


def test_leakage_guard_rejects_target_sources_and_derived_indices() -> None:
    validate_predictors(list(PREDICTORS))
    for leaking in ("B04", "B05", "B07", "B8A", "ndci", "ndvi", "target"):
        with pytest.raises(ValueError, match="leak"):
            validate_predictors([*PREDICTORS, leaking])


def test_spatial_blocks_use_projected_kilometre_cells() -> None:
    data = pd.DataFrame(
        {
            "longitude": [-91.2, -91.2001, -90.6],
            "latitude": [14.6, 14.6001, 14.4],
            "lake": ["atitlan", "atitlan", "amatitlan"],
        }
    )
    blocked = add_spatial_blocks(data)
    assert blocked.loc[0, "spatial_block"] == blocked.loc[1, "spatial_block"]
    assert blocked.loc[0, "spatial_block"] != blocked.loc[2, "spatial_block"]
    assert blocked["x_utm"].between(650_000, 800_000).all()


def test_temporal_split_never_trains_on_future() -> None:
    data = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01"]),
            "target": [0, 1, 0, 1],
        }
    )
    train, test, cutoff = chronological_split_indices(data)
    assert data.iloc[train]["date"].max() == cutoff
    assert data.iloc[train]["date"].max() < data.iloc[test]["date"].min()


def test_spatial_split_never_breaks_a_block_between_train_and_test() -> None:
    data = pd.DataFrame(
        {
            "spatial_block": ["a", "a", "b", "b", "c", "c"],
            "target": [0, 1, 0, 1, 0, 1],
        }
    )
    for train, test in spatial_group_splits(data, n_splits=3):
        train_groups = set(data.iloc[train]["spatial_block"])
        test_groups = set(data.iloc[test]["spatial_block"])
        assert train_groups.isdisjoint(test_groups)


def test_spatial_tuning_indices_never_intersect_outer_test() -> None:
    data = pd.DataFrame(
        {
            "spatial_block": np.repeat(["a", "b", "c", "d", "e", "f"], 2),
            "target": [0, 1] * 6,
        }
    )
    for plan in spatial_nested_splits(data, outer_splits=3, inner_splits=2):
        outer_train = set(plan.outer_train)
        outer_test = set(plan.outer_test)
        for inner_train, inner_validation in plan.inner_splits:
            assert set(inner_train).issubset(outer_train)
            assert set(inner_validation).issubset(outer_train)
            assert set(inner_train).isdisjoint(outer_test)
            assert set(inner_validation).isdisjoint(outer_test)
            train_groups = set(data.iloc[inner_train]["spatial_block"])
            validation_groups = set(data.iloc[inner_validation]["spatial_block"])
            assert train_groups.isdisjoint(validation_groups)


def test_temporal_tuning_uses_only_past_and_respects_chronology() -> None:
    data = pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2025-01-01",
                    "2025-01-01",
                    "2025-02-01",
                    "2025-02-01",
                    "2025-03-01",
                    "2025-03-01",
                    "2025-04-01",
                    "2025-04-01",
                    "2025-05-01",
                    "2025-05-01",
                ]
            ),
            "target": [0, 1] * 5,
        }
    )
    outer_train, outer_test, cutoff = chronological_split_indices(data, train_fraction=0.70)
    for inner_train, inner_validation in temporal_tuning_splits(data, outer_train, n_splits=3):
        assert set(inner_train).isdisjoint(outer_test)
        assert set(inner_validation).isdisjoint(outer_test)
        assert data.iloc[inner_train]["date"].max() < data.iloc[inner_validation]["date"].min()
        assert data.iloc[inner_validation]["date"].max() <= cutoff


def test_metrics_do_not_invent_auc_for_single_class() -> None:
    metrics = binary_metrics(np.array([1, 1]), np.array([0.8, 0.9]))
    assert np.isnan(metrics["roc_auc"])
    assert metrics["recall"] == 1
