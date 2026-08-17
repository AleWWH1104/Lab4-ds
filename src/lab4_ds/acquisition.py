"""Deterministic, aligned Sentinel Hub acquisition."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv
from rasterio.transform import from_bounds
from sentinelhub import (
    CRS,
    BBox,
    DataCollection,
    MimeType,
    MosaickingOrder,
    SentinelHubRequest,
    SHConfig,
    bbox_to_dimensions,
)

from .indices import calculate_layers
from .raster import PRODUCT_BANDS, RAW_BANDS, read_named_raster, write_geotiff

EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: [{
      bands: ["B02", "B03", "B04", "B05", "B07", "B08", "B8A", "B11", "B12", "SCL", "dataMask"],
      units: ["REFLECTANCE", "REFLECTANCE", "REFLECTANCE", "REFLECTANCE", "REFLECTANCE",
              "REFLECTANCE", "REFLECTANCE", "REFLECTANCE", "REFLECTANCE", "DN", "DN"]
    }],
    output: { bands: 11, sampleType: "FLOAT32" }
  };
}
function evaluatePixel(s) {
  return [s.B02, s.B03, s.B04, s.B05, s.B07, s.B08, s.B8A, s.B11, s.B12, s.SCL, s.dataMask];
}
""".strip()


def sentinel_config() -> SHConfig:
    load_dotenv()
    missing = [name for name in ("SH_CLIENT_ID", "SH_CLIENT_SECRET") if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Missing Sentinel Hub credentials: {', '.join(missing)}")
    config = SHConfig()
    config.sh_client_id = os.environ["SH_CLIENT_ID"]
    config.sh_client_secret = os.environ["SH_CLIENT_SECRET"]
    config.sh_base_url = "https://sh.dataspace.copernicus.eu"
    config.sh_token_url = (
        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    )
    return config


def process_raw_raster(raw_path: Path, product_path: Path) -> None:
    bands, profile = read_named_raster(raw_path, RAW_BANDS)
    layers = calculate_layers(bands)
    stack = np.stack([layers[name] for name in PRODUCT_BANDS])
    tags = profile.get("tags", {}) | {
        "product": "analytical_indices",
        "surface_bloom_semantics": "1 = FAI > 0.08; chlorophyll proxy is NaN for these pixels",
    }
    write_geotiff(
        product_path, stack, profile["transform"], str(profile["crs"]), PRODUCT_BANDS, tags
    )


def acquire_scene(
    lake_key: str,
    lake: dict[str, Any],
    acquisition: dict[str, Any],
    resolution: int,
    raw_root: Path,
    processed_root: Path,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    scene_date = acquisition["date"]
    raw_path = raw_root / lake_key / f"{scene_date}.tif"
    product_path = processed_root / lake_key / f"{scene_date}.tif"
    if raw_path.exists() and product_path.exists() and not overwrite:
        return raw_path, product_path

    config = sentinel_config()
    collection = DataCollection.SENTINEL2_L2A.define_from(
        "s2l2a_cdse_lab4", service_url=config.sh_base_url
    )
    bbox = BBox(lake["bbox"], crs=CRS.WGS84)
    width, height = bbox_to_dimensions(bbox, resolution=resolution)
    start = date.fromisoformat(scene_date)
    interval = (start.isoformat(), (start + timedelta(days=1)).isoformat())
    request = SentinelHubRequest(
        evalscript=EVALSCRIPT,
        input_data=[
            SentinelHubRequest.input_data(
                data_collection=collection,
                time_interval=interval,
                mosaicking_order=MosaickingOrder.LEAST_CC,
                other_args={"processing": {"upsampling": "NEAREST", "downsampling": "NEAREST"}},
            )
        ],
        responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
        bbox=bbox,
        size=(width, height),
        config=config,
    )
    result = np.asarray(request.get_data()[0], dtype=np.float32)
    if result.shape != (height, width, len(RAW_BANDS)):
        raise RuntimeError(f"Unexpected response shape for {lake_key} {scene_date}: {result.shape}")
    transform = from_bounds(*lake["bbox"], width, height)
    tags = {
        "lake": lake_key,
        "date": scene_date,
        "official_satellite": acquisition["satellite"],
        "official_cloud_percent": str(acquisition["cloud_percent"]),
        "collection": "Sentinel-2 L2A",
        "units": "reflectance for B*; DN for SCL and dataMask",
        "mosaicking_order": "leastCC",
        "evalscript_sha256": hashlib.sha256(EVALSCRIPT.encode()).hexdigest(),
    }
    write_geotiff(raw_path, np.moveaxis(result, -1, 0), transform, "EPSG:4326", RAW_BANDS, tags)
    process_raw_raster(raw_path, product_path)
    metadata = raw_path.with_suffix(".json")
    metadata.write_text(
        json.dumps(
            {
                **tags,
                "bbox": lake["bbox"],
                "resolution_m": resolution,
                "shape": [height, width],
                "time_interval": interval,
                "request_payload": request.payload,
                "note": (
                    "Official metadata is from the handout; verify the selected catalog item "
                    "independently."
                ),
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return raw_path, product_path
