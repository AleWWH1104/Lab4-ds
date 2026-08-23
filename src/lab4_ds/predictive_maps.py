"""Full-grid probability scoring and lake-level predictive maps for Exercise 9."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator

from .ml import PREDICTORS, TARGET_THRESHOLD, _scene_pairs, _target_and_eligibility
from .raster import PRODUCT_BANDS, RAW_BANDS, read_named_raster


def score_lake_scenes(
    model: BaseEstimator,
    raw_root: Path = Path("data/raw"),
    processed_root: Path = Path("data/processed"),
    predictors: tuple[str, ...] = PREDICTORS,
    threshold: float = TARGET_THRESHOLD,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Score every eligible pixel of every local scene with a fitted classifier."""
    scored: dict[tuple[str, str], dict[str, Any]] = {}
    for lake, date, raw_path, product_path in _scene_pairs(raw_root, processed_root):
        raw, raw_profile = read_named_raster(raw_path, RAW_BANDS)
        product, _ = read_named_raster(product_path, PRODUCT_BANDS)
        target, eligible, _, _ = _target_and_eligibility(raw, product, threshold)
        probability = np.full(eligible.shape, np.nan, dtype=np.float32)
        rows, columns = np.where(eligible)
        if rows.size:
            features = pd.DataFrame({name: raw[name][rows, columns] for name in predictors})
            probability[rows, columns] = model.predict_proba(features)[:, 1]
        scored[(lake, date)] = {
            "probability": probability,
            "target": np.where(eligible, target, np.nan).astype(np.float32),
            "eligible": eligible,
            "transform": raw_profile["transform"],
            "shape": eligible.shape,
        }
    return scored


def aggregate_lake_predictions(
    scored: dict[tuple[str, str], dict[str, Any]],
    lake: str,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """Average per-pixel probability and outcome across every scored scene of a lake."""
    entries = [value for (scene_lake, _), value in scored.items() if scene_lake == lake]
    if not entries:
        raise ValueError(f"No scored scenes found for lake '{lake}'")
    shapes = {entry["shape"] for entry in entries}
    if len(shapes) != 1:
        raise ValueError(f"Scenes for lake '{lake}' do not share a common grid shape: {shapes}")

    probability_stack = np.stack([entry["probability"] for entry in entries])
    target_stack = np.stack([entry["target"] for entry in entries])
    observation_count = np.sum(~np.isnan(probability_stack), axis=0)

    mean_probability = np.nanmean(probability_stack, axis=0)
    mean_target = np.nanmean(target_stack, axis=0)

    predicted_high = mean_probability >= threshold
    observed_high = mean_target >= threshold
    valid = observation_count > 0

    true_positive = valid & predicted_high & observed_high
    false_positive = valid & predicted_high & ~observed_high
    false_negative = valid & ~predicted_high & observed_high
    true_negative = valid & ~predicted_high & ~observed_high

    per_scene_mismatch = (probability_stack >= threshold) != (target_stack >= threshold)
    both_finite = ~np.isnan(probability_stack) & ~np.isnan(target_stack)
    error_rate = np.divide(
        np.sum(per_scene_mismatch & both_finite, axis=0),
        observation_count,
        out=np.full(observation_count.shape, np.nan, dtype=np.float32),
        where=observation_count > 0,
    )

    return {
        "mean_probability": mean_probability,
        "mean_target": mean_target,
        "observation_count": observation_count,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
        "error_rate": error_rate,
        "transform": entries[0]["transform"],
    }
