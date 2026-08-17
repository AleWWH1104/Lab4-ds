"""Validation of configuration and persisted raster evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import rasterio

from .raster import PRODUCT_BANDS, RAW_BANDS


def validate_repository(
    config: dict[str, Any],
    raw_root: Path = Path("data/raw"),
    processed_root: Path = Path("data/processed"),
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    checked = 0
    expected = sum(len(lake["acquisitions"]) for lake in config["lakes"].values())
    minimum_valid = float(config["analysis"]["minimum_valid_fraction"])
    for lake_key, lake in config["lakes"].items():
        for acquisition in lake["acquisitions"]:
            date = acquisition["date"]
            raw_path = raw_root / lake_key / f"{date}.tif"
            product_path = processed_root / lake_key / f"{date}.tif"
            metadata_path = raw_path.with_suffix(".json")
            for path in (raw_path, product_path, metadata_path):
                if not path.exists():
                    errors.append(f"Missing required artifact: {path}")
            if not raw_path.exists() or not product_path.exists():
                continue
            checked += 1
            try:
                with rasterio.open(raw_path) as raw, rasterio.open(product_path) as product:
                    if list(raw.descriptions) != RAW_BANDS:
                        errors.append(f"Unexpected raw bands: {raw_path}")
                    if list(product.descriptions) != PRODUCT_BANDS:
                        errors.append(f"Unexpected product bands: {product_path}")
                    if raw.crs is None or product.crs is None or raw.transform.is_identity:
                        errors.append(f"Missing georeferencing: {raw_path}")
                    if (raw.width, raw.height, raw.transform) != (
                        product.width,
                        product.height,
                        product.transform,
                    ):
                        errors.append(f"Raw/product grids are not aligned: {product_path}")
                    valid_fraction = float(
                        np.mean(product.read(PRODUCT_BANDS.index("valid") + 1) == 1)
                    )
                    water_pixels = int(
                        np.sum(
                            (product.read(PRODUCT_BANDS.index("valid") + 1) == 1)
                            & (product.read(PRODUCT_BANDS.index("water") + 1) == 1)
                        )
                    )
                    if valid_fraction < minimum_valid:
                        warnings.append(
                            f"Low valid coverage ({valid_fraction:.1%}): {lake_key} {date}"
                        )
                    if water_pixels == 0:
                        errors.append(f"No valid water pixels: {product_path}")
            except rasterio.errors.RasterioError as error:
                errors.append(f"Unreadable raster {raw_path}: {error}")
            if metadata_path.exists():
                try:
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                    if metadata.get("date") != date or metadata.get("lake") != lake_key:
                        errors.append(f"Metadata identity mismatch: {metadata_path}")
                except (json.JSONDecodeError, OSError) as error:
                    errors.append(f"Unreadable metadata {metadata_path}: {error}")
    return {
        "status": "valid" if not errors else "invalid",
        "expected_scenes": expected,
        "checked_scenes": checked,
        "errors": errors,
        "warnings": warnings,
    }
