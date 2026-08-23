"""Reproducible tabular modelling utilities for Laboratory 4 Part 2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pyproj import Transformer
from rasterio.transform import xy
from sklearn.base import BaseEstimator, clone
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    fbeta_score,
    make_scorer,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import (
    GridSearchCV,
    GroupKFold,
    StratifiedKFold,
    TimeSeriesSplit,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight

from .analysis import MAX_CALIBRATED_CHLOROPHYLL
from .indices import chlorophyll_from_ndci, ndci
from .raster import PRODUCT_BANDS, RAW_BANDS, read_named_raster

TARGET_THRESHOLD = 20.0
TARGET_SOURCE_BANDS = frozenset({"B04", "B05", "B07", "B8A"})
PREDICTORS = ("B02", "B03", "B08", "B11", "B12")
REQUIRED_SAMPLE_COLUMNS = (
    "longitude",
    "latitude",
    "date",
    "lake",
    *RAW_BANDS[:9],
    "ndvi",
    "ndwi",
    "ndci",
    "cyanobacteria_proxy",
    "surface_bloom",
    "target",
)


@dataclass(frozen=True)
class DatasetBundle:
    """A bounded modelling sample plus full-population scene statistics."""

    sample: pd.DataFrame
    population: pd.DataFrame


@dataclass(frozen=True)
class NestedSpatialFold:
    """Observable outer and inner indices for leakage-safe spatial validation."""

    outer_train: np.ndarray
    outer_test: np.ndarray
    inner_splits: tuple[tuple[np.ndarray, np.ndarray], ...]


def _scene_pairs(raw_root: Path, processed_root: Path) -> list[tuple[str, str, Path, Path]]:
    pairs: list[tuple[str, str, Path, Path]] = []
    for raw_path in sorted(raw_root.glob("*/*.tif")):
        lake = raw_path.parent.name
        product_path = processed_root / lake / raw_path.name
        if not product_path.exists():
            raise FileNotFoundError(f"Missing processed counterpart: {product_path}")
        pairs.append((lake, raw_path.stem, raw_path, product_path))
    if not pairs:
        raise FileNotFoundError(f"No local GeoTIFF scenes found under {raw_root}")
    return pairs


def _target_and_eligibility(
    raw: dict[str, np.ndarray], product: dict[str, np.ndarray], threshold: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    cyanobacteria_ndci = ndci(raw["B04"], raw["B05"]).astype(np.float32)
    proxy = chlorophyll_from_ndci(cyanobacteria_ndci).astype(np.float32)
    surface_bloom = product["surface_bloom"] == 1
    analytical = (
        (product["valid"] == 1)
        & (product["water"] == 1)
        & (raw["dataMask"] == 1)
        & ~np.isin(raw["SCL"].astype(np.int16), [0, 1, 3, 8, 9, 10, 11])
    )
    finite_features = np.logical_and.reduce(
        [np.isfinite(raw[name]) for name in RAW_BANDS[:9]]
        + [np.isfinite(product["ndvi"]), np.isfinite(product["ndwi"]), np.isfinite(proxy)]
    )
    calibrated_or_bloom = ((proxy >= 0) & (proxy < MAX_CALIBRATED_CHLOROPHYLL)) | surface_bloom
    eligible = analytical & finite_features & calibrated_or_bloom
    target = (surface_bloom | (proxy >= threshold)).astype(np.int8)
    return target, eligible, cyanobacteria_ndci, proxy


def _sample_indices(
    target: np.ndarray,
    eligible: np.ndarray,
    maximum_per_class: int,
    rng: np.random.Generator,
) -> np.ndarray:
    selected: list[np.ndarray] = []
    flattened_target = target.ravel()
    flattened_eligible = eligible.ravel()
    for class_value in (0, 1):
        candidates = np.flatnonzero(flattened_eligible & (flattened_target == class_value))
        if candidates.size > maximum_per_class:
            candidates = np.sort(rng.choice(candidates, maximum_per_class, replace=False))
        selected.append(candidates)
    return np.sort(np.concatenate(selected))


def build_ml_dataset(
    raw_root: Path = Path("data/raw"),
    processed_root: Path = Path("data/processed"),
    maximum_per_scene_class: int = 500,
    random_state: int = 42,
    threshold: float = TARGET_THRESHOLD,
) -> DatasetBundle:
    """Build a deterministic stratified sample without materializing invalid raster pixels."""
    if maximum_per_scene_class < 1:
        raise ValueError("maximum_per_scene_class must be positive")
    rng = np.random.default_rng(random_state)
    samples: list[pd.DataFrame] = []
    population_rows: list[dict[str, Any]] = []

    for lake, date, raw_path, product_path in _scene_pairs(raw_root, processed_root):
        raw, raw_profile = read_named_raster(raw_path, RAW_BANDS)
        product, product_profile = read_named_raster(product_path, PRODUCT_BANDS)
        if raw["B02"].shape != product["valid"].shape:
            raise ValueError(f"Raw and processed grids differ: {raw_path}")
        if raw_profile["transform"] != product_profile["transform"]:
            raise ValueError(f"Raw and processed transforms differ: {raw_path}")

        target, eligible, cyanobacteria_ndci, proxy = _target_and_eligibility(
            raw, product, threshold
        )
        selected = _sample_indices(target, eligible, maximum_per_scene_class, rng)
        rows, columns = np.unravel_index(selected, eligible.shape)
        longitudes, latitudes = xy(raw_profile["transform"], rows, columns, offset="center")
        scene_data: dict[str, Any] = {
            "longitude": np.asarray(longitudes),
            "latitude": np.asarray(latitudes),
            "date": pd.Timestamp(date),
            "lake": lake,
        }
        for name in RAW_BANDS[:9]:
            scene_data[name] = raw[name].ravel()[selected].astype(np.float32)
        scene_data.update(
            {
                "ndvi": product["ndvi"].ravel()[selected].astype(np.float32),
                "ndwi": product["ndwi"].ravel()[selected].astype(np.float32),
                "ndci": cyanobacteria_ndci.ravel()[selected],
                "cyanobacteria_proxy": proxy.ravel()[selected],
                "surface_bloom": product["surface_bloom"].ravel()[selected].astype(np.int8),
                "target": target.ravel()[selected],
            }
        )
        samples.append(pd.DataFrame(scene_data, columns=REQUIRED_SAMPLE_COLUMNS))
        valid_water = (product["valid"] == 1) & (product["water"] == 1)
        population_rows.append(
            {
                "lake": lake,
                "date": pd.Timestamp(date),
                "raster_pixels": int(eligible.size),
                "valid_water_pixels": int(valid_water.sum()),
                "eligible_pixels": int(eligible.sum()),
                "class_0": int((eligible & (target == 0)).sum()),
                "class_1": int((eligible & (target == 1)).sum()),
                "sampled_pixels": int(selected.size),
            }
        )

    sample = pd.concat(samples, ignore_index=True)
    population = pd.DataFrame(population_rows).sort_values(["lake", "date"], ignore_index=True)
    if sample.empty or not set(sample["target"].unique()).issubset({0, 1}):
        raise ValueError("The modelling sample must contain a binary target")
    return DatasetBundle(sample=sample, population=population)


def validate_predictors(predictors: tuple[str, ...] | list[str]) -> None:
    """Reject target artifacts and every band used by NDCI or FAI."""
    forbidden = TARGET_SOURCE_BANDS | {
        "target",
        "surface_bloom",
        "ndci",
        "cyanobacteria_proxy",
        "chlorophyll_proxy",
        "ndvi",
    }
    overlap = forbidden.intersection(predictors)
    if overlap:
        raise ValueError(f"Predictors leak target information: {sorted(overlap)}")


def add_spatial_blocks(data: pd.DataFrame, block_size_m: float = 1_000.0) -> pd.DataFrame:
    """Project WGS84 coordinates to UTM 15N and assign regular metric blocks by lake."""
    if block_size_m <= 0:
        raise ValueError("block_size_m must be positive")
    transformed = data.copy()
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32615", always_xy=True)
    x_utm, y_utm = transformer.transform(
        transformed["longitude"].to_numpy(), transformed["latitude"].to_numpy()
    )
    transformed["x_utm"] = x_utm
    transformed["y_utm"] = y_utm
    transformed["block_x"] = np.floor(transformed["x_utm"] / block_size_m).astype(int)
    transformed["block_y"] = np.floor(transformed["y_utm"] / block_size_m).astype(int)
    transformed["spatial_block"] = (
        transformed["lake"].astype(str)
        + "_"
        + transformed["block_x"].astype(str)
        + "_"
        + transformed["block_y"].astype(str)
    )
    return transformed


def random_split_indices(
    data: pd.DataFrame, random_state: int = 42
) -> tuple[np.ndarray, np.ndarray]:
    """Return one common 70/30 stratified split for every model."""
    indices = np.arange(len(data))
    return train_test_split(
        indices,
        test_size=0.30,
        random_state=random_state,
        stratify=data["target"],
    )


def chronological_split_indices(
    data: pd.DataFrame, train_fraction: float = 0.70
) -> tuple[np.ndarray, np.ndarray, pd.Timestamp]:
    """Split on globally ordered acquisition dates so training never sees the future."""
    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between zero and one")
    dates = np.sort(pd.to_datetime(data["date"]).unique())
    if len(dates) < 2:
        raise ValueError("At least two dates are required for temporal validation")
    train_date_count = min(len(dates) - 1, max(1, int(np.floor(len(dates) * train_fraction))))
    cutoff = pd.Timestamp(dates[train_date_count - 1])
    train = np.flatnonzero(pd.to_datetime(data["date"]).to_numpy() <= cutoff.to_datetime64())
    test = np.flatnonzero(pd.to_datetime(data["date"]).to_numpy() > cutoff.to_datetime64())
    return train, test, cutoff


def _model_searches(random_state: int) -> dict[str, tuple[Pipeline, dict[str, list[Any]]]]:
    return {
        "Logistic regression": (
            Pipeline(
                [
                    ("scale", StandardScaler()),
                    (
                        "classifier",
                        LogisticRegression(
                            class_weight="balanced", max_iter=2_000, random_state=random_state
                        ),
                    ),
                ]
            ),
            {"classifier__C": [0.3, 1.0, 3.0]},
        ),
        "Random forest": (
            Pipeline(
                [
                    ("scale", "passthrough"),
                    (
                        "classifier",
                        RandomForestClassifier(
                            n_estimators=120,
                            class_weight="balanced_subsample",
                            n_jobs=-1,
                            random_state=random_state,
                        ),
                    ),
                ]
            ),
            {"classifier__max_depth": [8, None], "classifier__min_samples_leaf": [2, 10]},
        ),
        "Gradient boosting": (
            Pipeline(
                [
                    ("scale", "passthrough"),
                    (
                        "classifier",
                        GradientBoostingClassifier(
                            n_estimators=80, max_depth=2, random_state=random_state
                        ),
                    ),
                ]
            ),
            {"classifier__learning_rate": [0.05, 0.1]},
        ),
    }


def tune_models(
    data: pd.DataFrame,
    train_indices: np.ndarray,
    predictors: tuple[str, ...] = PREDICTORS,
    random_state: int = 42,
) -> tuple[dict[str, BaseEstimator], pd.DataFrame]:
    """Tune compact grids only on training data using an F2 environmental criterion."""
    validate_predictors(list(predictors))
    x_train = data.iloc[train_indices].loc[:, predictors]
    y_train = data.iloc[train_indices]["target"].astype(int)
    weights = compute_sample_weight(class_weight="balanced", y=y_train)
    cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=random_state)
    scorer = make_scorer(fbeta_score, beta=2, zero_division=0)
    fitted: dict[str, BaseEstimator] = {}
    rows: list[dict[str, Any]] = []
    for name, (pipeline, grid) in _model_searches(random_state).items():
        search = GridSearchCV(pipeline, grid, scoring=scorer, cv=cv, n_jobs=1, refit=True)
        search.fit(x_train, y_train, classifier__sample_weight=weights)
        fitted[name] = search.best_estimator_
        rows.append(
            {"model": name, "best_cv_f2": search.best_score_, "best_params": search.best_params_}
        )
    return fitted, pd.DataFrame(rows)


def binary_metrics(y_true: pd.Series | np.ndarray, probability: np.ndarray) -> dict[str, Any]:
    """Compute required metrics, leaving AUC undefined when only one class is observed."""
    truth = np.asarray(y_true, dtype=int)
    predicted = (np.asarray(probability) >= 0.5).astype(int)
    auc = float(roc_auc_score(truth, probability)) if np.unique(truth).size == 2 else float("nan")
    return {
        "accuracy": accuracy_score(truth, predicted),
        "precision": precision_score(truth, predicted, zero_division=0),
        "recall": recall_score(truth, predicted, zero_division=0),
        "f1": f1_score(truth, predicted, zero_division=0),
        "roc_auc": auc,
        "tn": int(confusion_matrix(truth, predicted, labels=[0, 1])[0, 0]),
        "fp": int(confusion_matrix(truth, predicted, labels=[0, 1])[0, 1]),
        "fn": int(confusion_matrix(truth, predicted, labels=[0, 1])[1, 0]),
        "tp": int(confusion_matrix(truth, predicted, labels=[0, 1])[1, 1]),
    }


def evaluate_models(
    models: dict[str, BaseEstimator],
    data: pd.DataFrame,
    test_indices: np.ndarray,
    predictors: tuple[str, ...] = PREDICTORS,
    strategy: str = "random",
) -> pd.DataFrame:
    x_test = data.iloc[test_indices].loc[:, predictors]
    y_test = data.iloc[test_indices]["target"].astype(int)
    rows = []
    for name, model in models.items():
        probability = model.predict_proba(x_test)[:, 1]
        rows.append(
            {
                "strategy": strategy,
                "model": name,
                "n_test": len(y_test),
                **binary_metrics(y_test, probability),
            }
        )
    return pd.DataFrame(rows)


def _fit_clone(model: BaseEstimator, x_train: pd.DataFrame, y_train: pd.Series) -> BaseEstimator:
    fitted = clone(model)
    weights = compute_sample_weight(class_weight="balanced", y=y_train)
    return fitted.fit(x_train, y_train, classifier__sample_weight=weights)


def spatial_nested_splits(
    data: pd.DataFrame, outer_splits: int = 5, inner_splits: int = 3
) -> list[NestedSpatialFold]:
    """Build nested group-aware folds with globally observable row indices."""
    plans: list[NestedSpatialFold] = []
    for outer_train, outer_test in spatial_group_splits(data, n_splits=outer_splits):
        outer_data = data.iloc[outer_train]
        group_count = outer_data["spatial_block"].nunique()
        if group_count < 2:
            raise ValueError("Each outer training fold needs at least two spatial blocks")
        inner_splitter = GroupKFold(n_splits=min(inner_splits, group_count))
        nested: list[tuple[np.ndarray, np.ndarray]] = []
        for inner_train_local, inner_validation_local in inner_splitter.split(
            outer_data, outer_data["target"], outer_data["spatial_block"]
        ):
            nested.append((outer_train[inner_train_local], outer_train[inner_validation_local]))
        plans.append(
            NestedSpatialFold(
                outer_train=outer_train,
                outer_test=outer_test,
                inner_splits=tuple(nested),
            )
        )
    return plans


def temporal_tuning_splits(
    data: pd.DataFrame, train_indices: np.ndarray, n_splits: int = 3
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Create expanding-window tuning folds using only external past-training rows."""
    train_dates = pd.to_datetime(data.iloc[train_indices]["date"])
    unique_dates = np.sort(train_dates.unique())
    if len(unique_dates) < 2:
        raise ValueError("Temporal tuning requires at least two past dates")
    splitter = TimeSeriesSplit(n_splits=min(n_splits, len(unique_dates) - 1))
    splits: list[tuple[np.ndarray, np.ndarray]] = []
    for train_date_positions, validation_date_positions in splitter.split(unique_dates):
        inner_train_dates = unique_dates[train_date_positions]
        inner_validation_dates = unique_dates[validation_date_positions]
        inner_train = train_indices[train_dates.isin(inner_train_dates).to_numpy()]
        inner_validation = train_indices[train_dates.isin(inner_validation_dates).to_numpy()]
        splits.append((inner_train, inner_validation))
    return splits


def _tune_with_global_splits(
    data: pd.DataFrame,
    train_indices: np.ndarray,
    global_splits: list[tuple[np.ndarray, np.ndarray]] | tuple[tuple[np.ndarray, np.ndarray], ...],
    predictors: tuple[str, ...],
    random_state: int,
) -> tuple[dict[str, BaseEstimator], pd.DataFrame]:
    """Tune on an explicit subset; split indices remain observable to callers and tests."""
    validate_predictors(list(predictors))
    x_train = data.iloc[train_indices].loc[:, predictors]
    y_train = data.iloc[train_indices]["target"].astype(int)
    weights = compute_sample_weight(class_weight="balanced", y=y_train)
    global_to_local = {global_index: local for local, global_index in enumerate(train_indices)}
    local_splits = [
        (
            np.asarray([global_to_local[index] for index in split_train]),
            np.asarray([global_to_local[index] for index in split_validation]),
        )
        for split_train, split_validation in global_splits
    ]
    scorer = make_scorer(fbeta_score, beta=2, zero_division=0)
    fitted: dict[str, BaseEstimator] = {}
    rows: list[dict[str, Any]] = []
    for name, (pipeline, grid) in _model_searches(random_state).items():
        search = GridSearchCV(
            pipeline,
            grid,
            scoring=scorer,
            cv=local_splits,
            n_jobs=1,
            refit=True,
        )
        search.fit(x_train, y_train, classifier__sample_weight=weights)
        fitted[name] = search.best_estimator_
        rows.append(
            {"model": name, "best_inner_f2": search.best_score_, "best_params": search.best_params_}
        )
    return fitted, pd.DataFrame(rows)


def evaluate_spatial_cv(
    data: pd.DataFrame,
    predictors: tuple[str, ...] = PREDICTORS,
    n_splits: int = 5,
    inner_splits: int = 3,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Nested spatial CV: group-aware tuning occurs inside every outer training fold."""
    rows: list[dict[str, Any]] = []
    tuning_rows: list[pd.DataFrame] = []
    x = data.loc[:, predictors]
    y = data["target"].astype(int)
    plans = spatial_nested_splits(data, outer_splits=n_splits, inner_splits=inner_splits)
    for fold, plan in enumerate(plans, start=1):
        train = plan.outer_train
        test = plan.outer_test
        models, tuning = _tune_with_global_splits(
            data, train, plan.inner_splits, predictors, random_state + fold
        )
        tuning["outer_fold"] = fold
        tuning["outer_train_n"] = len(train)
        tuning["outer_test_n"] = len(test)
        tuning["outer_test_tuning_overlap"] = len(
            set(test).intersection(
                index for split in plan.inner_splits for indices in split for index in indices
            )
        )
        tuning["maximum_inner_group_overlap"] = max(
            len(
                set(data.iloc[inner_train]["spatial_block"]).intersection(
                    data.iloc[inner_validation]["spatial_block"]
                )
            )
            for inner_train, inner_validation in plan.inner_splits
        )
        tuning_rows.append(tuning)
        for name, model in models.items():
            if y.iloc[train].nunique() < 2:
                rows.append(
                    {
                        "strategy": "spatial",
                        "fold": fold,
                        "model": name,
                        "n_test": len(test),
                        "status": "skipped: training fold has one class",
                    }
                )
                continue
            fitted = _fit_clone(model, x.iloc[train], y.iloc[train])
            probability = fitted.predict_proba(x.iloc[test])[:, 1]
            rows.append(
                {
                    "strategy": "spatial",
                    "fold": fold,
                    "model": name,
                    "n_test": len(test),
                    "test_classes": y.iloc[test].nunique(),
                    "status": "ok",
                    **binary_metrics(y.iloc[test], probability),
                }
            )
    return pd.DataFrame(rows), pd.concat(tuning_rows, ignore_index=True)


def spatial_group_splits(
    data: pd.DataFrame, n_splits: int = 5
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Return GroupKFold indices while guaranteeing at least two spatial groups."""
    unique_groups = data["spatial_block"].nunique()
    if unique_groups < 2:
        raise ValueError("At least two spatial blocks are required")
    splitter = GroupKFold(n_splits=min(n_splits, unique_groups))
    return list(splitter.split(data, data["target"], data["spatial_block"]))


def evaluate_temporal_holdout(
    data: pd.DataFrame,
    train_indices: np.ndarray,
    test_indices: np.ndarray,
    predictors: tuple[str, ...] = PREDICTORS,
    inner_splits: int = 3,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Tune with expanding past-only folds, refit on all past, and test once on future."""
    x = data.loc[:, predictors]
    y = data["target"].astype(int)
    tuning_splits = temporal_tuning_splits(data, train_indices, n_splits=inner_splits)
    models, tuning = _tune_with_global_splits(
        data, train_indices, tuning_splits, predictors, random_state
    )
    tuning["past_train_n"] = len(train_indices)
    tuning["future_test_n"] = len(test_indices)
    tuning["future_test_tuning_overlap"] = len(
        set(test_indices).intersection(
            index for split in tuning_splits for indices in split for index in indices
        )
    )
    tuning["latest_tuning_date"] = max(
        pd.to_datetime(data.iloc[indices]["date"]).max()
        for split in tuning_splits
        for indices in split
    )
    tuning["earliest_future_test_date"] = pd.to_datetime(data.iloc[test_indices]["date"]).min()
    rows = []
    for name, model in models.items():
        probability = model.predict_proba(x.iloc[test_indices])[:, 1]
        rows.append(
            {
                "strategy": "temporal",
                "model": name,
                "n_test": len(test_indices),
                **binary_metrics(y.iloc[test_indices], probability),
            }
        )
    return pd.DataFrame(rows), tuning
