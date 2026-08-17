"""Offline temporal, spatial, correlation, and comparative analysis."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import pandas as pd
from numpy.typing import NDArray

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .raster import PRODUCT_BANDS, read_named_raster, write_geotiff

MAX_CALIBRATED_CHLOROPHYLL = 500.0


def lake_name(value: str) -> str:
    return {"atitlan": "Atitlán", "amatitlan": "Amatitlán"}.get(value, value.title())


def valid_chlorophyll_mask(chlorophyll: NDArray[np.floating]) -> NDArray[np.bool_]:
    """Select physically possible values within the CyanoLakes training range."""
    return (
        np.isfinite(chlorophyll) & (chlorophyll >= 0) & (chlorophyll < MAX_CALIBRATED_CHLOROPHYLL)
    )


def high_value_mask(
    chlorophyll: NDArray[np.floating],
    surface_bloom: NDArray[np.floating],
    threshold: float,
) -> NDArray[np.bool_]:
    """Classify high pixels while always retaining official FAI surface blooms."""
    return (surface_bloom == 1) | (np.isfinite(chlorophyll) & (chlorophyll >= threshold))


def summarize_scene(layers: dict[str, NDArray], threshold: float) -> dict[str, float | int]:
    valid = layers["valid"] == 1
    water = layers["water"] == 1
    analytical = valid & water
    chlorophyll = layers["chlorophyll_proxy"]
    finite_chl = analytical & np.isfinite(chlorophyll)
    valid_chl = analytical & valid_chlorophyll_mask(chlorophyll)
    negative = finite_chl & (chlorophyll < 0)
    above_calibration = finite_chl & (chlorophyll >= MAX_CALIBRATED_CHLOROPHYLL)
    high = analytical & high_value_mask(chlorophyll, layers["surface_bloom"], threshold)
    denominator = int(analytical.sum())

    def percentage(mask: NDArray[np.bool_]) -> float:
        return float(mask.sum() / denominator * 100) if denominator else float("nan")

    values = chlorophyll[valid_chl]
    unestimated = analytical & ~finite_chl
    return {
        "total_pixels": int(valid.size),
        "valid_pixels": int(valid.sum()),
        "water_pixels": denominator,
        "valid_fraction": float(valid.mean()),
        "chlorophyll_valid_pixels": int(valid_chl.sum()),
        "chlorophyll_coverage_percent": percentage(valid_chl),
        "negative_proxy_pixels": int(negative.sum()),
        "negative_proxy_percent": percentage(negative),
        "above_calibration_pixels": int(above_calibration.sum()),
        "above_calibration_percent": percentage(above_calibration),
        "unestimated_proxy_pixels": int(unestimated.sum()),
        "mean_chlorophyll_proxy": float(np.mean(values)) if values.size else float("nan"),
        "median_chlorophyll_proxy": float(np.median(values)) if values.size else float("nan"),
        "p90_chlorophyll_proxy": float(np.percentile(values, 90)) if values.size else float("nan"),
        "surface_bloom_percent": percentage(analytical & (layers["surface_bloom"] == 1)),
        "high_value_percent": percentage(high),
    }


def pearson_pair(x: NDArray, y: NDArray) -> tuple[int, float]:
    mask = np.isfinite(x) & np.isfinite(y)
    count = int(mask.sum())
    if count < 3 or np.std(x[mask]) == 0 or np.std(y[mask]) == 0:
        return count, float("nan")
    return count, float(np.corrcoef(x[mask], y[mask])[0, 1])


def persistent_hotspots(
    scenes: list[dict[str, NDArray]], threshold: float, persistent_fraction: float
) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    if not scenes:
        raise ValueError("At least one scene is required")
    observations = np.zeros_like(scenes[0]["valid"], dtype=np.float32)
    high_count = np.zeros_like(observations)
    for scene in scenes:
        analytical = (scene["valid"] == 1) & (scene["water"] == 1)
        observations += analytical
        high_count += analytical & high_value_mask(
            scene["chlorophyll_proxy"], scene["surface_bloom"], threshold
        )
    frequency = np.divide(
        high_count,
        observations,
        out=np.full_like(observations, np.nan),
        where=observations > 0,
    )
    persistent = ((observations >= 2) & (frequency >= persistent_fraction)).astype(np.float32)
    persistent[observations < 2] = np.nan
    return frequency, persistent


def _scene_paths(config: dict[str, Any], root: Path) -> list[tuple[str, dict, Path]]:
    paths = []
    for lake_key, lake in config["lakes"].items():
        for acquisition in lake["acquisitions"]:
            path = root / lake_key / f"{acquisition['date']}.tif"
            if path.exists():
                paths.append((lake_key, acquisition, path))
    return paths


def run_analysis(
    config: dict[str, Any],
    processed_root: Path = Path("data/processed"),
    table_root: Path = Path("outputs/tables"),
    figure_root: Path = Path("outputs/figures"),
) -> pd.DataFrame:
    paths = _scene_paths(config, processed_root)
    if not paths:
        raise RuntimeError("No processed rasters found. Run acquisition before analysis.")
    table_root.mkdir(parents=True, exist_ok=True)
    figure_root.mkdir(parents=True, exist_ok=True)
    threshold = float(config["analysis"]["high_chlorophyll_threshold"])
    summaries: list[dict] = []
    correlations: list[dict] = []
    sensitivity: list[dict] = []
    distributions: list[dict] = []
    zone_observations: list[dict] = []
    by_lake: dict[str, list[tuple[str, dict, dict]]] = defaultdict(list)

    for lake_key, acquisition, path in paths:
        layers, profile = read_named_raster(path, PRODUCT_BANDS)
        date = acquisition["date"]
        summary = summarize_scene(layers, threshold)
        summaries.append({"lake": lake_key, "date": date, **summary})
        by_lake[lake_key].append((date, layers, profile))
        for index_name in ("ndvi", "ndwi"):
            chlorophyll = np.where(
                valid_chlorophyll_mask(layers["chlorophyll_proxy"]),
                layers["chlorophyll_proxy"],
                np.nan,
            )
            count, coefficient = pearson_pair(chlorophyll, layers[index_name])
            correlations.append(
                {
                    "lake": lake_key,
                    "date": date,
                    "index": index_name,
                    "n": count,
                    "pearson_r": coefficient,
                }
            )
        analytical_count = int(((layers["valid"] == 1) & (layers["water"] == 1)).sum())
        for candidate in config["analysis"]["sensitivity_thresholds"]:
            high = high_value_mask(layers["chlorophyll_proxy"], layers["surface_bloom"], candidate)
            percent = (
                float(high.sum() / analytical_count * 100) if analytical_count else float("nan")
            )
            sensitivity.append(
                {
                    "lake": lake_key,
                    "date": date,
                    "threshold": candidate,
                    "high_value_percent": percent,
                }
            )
        values = layers["chlorophyll_proxy"][valid_chlorophyll_mask(layers["chlorophyll_proxy"])]
        for value in values[:: max(1, values.size // 5000)]:
            distributions.append(
                {"lake": lake_key, "date": date, "chlorophyll_proxy": float(value)}
            )
        zone_observations.extend(_summarize_zones(lake_key, date, layers, profile, threshold))

    summary_frame = pd.DataFrame(summaries).sort_values(["lake", "date"])
    correlation_frame = pd.DataFrame(correlations)
    for lake_key, scenes in by_lake.items():
        for index_name in ("ndvi", "ndwi"):
            x = np.concatenate(
                [
                    np.where(
                        valid_chlorophyll_mask(scene[1]["chlorophyll_proxy"]),
                        scene[1]["chlorophyll_proxy"],
                        np.nan,
                    ).ravel()
                    for scene in scenes
                ]
            )
            y = np.concatenate([scene[1][index_name].ravel() for scene in scenes])
            count, coefficient = pearson_pair(x, y)
            correlations.append(
                {
                    "lake": lake_key,
                    "date": "all",
                    "index": index_name,
                    "n": count,
                    "pearson_r": coefficient,
                }
            )
    correlation_frame = pd.DataFrame(correlations)
    summary_frame.to_csv(table_root / "temporal_summary.csv", index=False)
    peaks = summary_frame.loc[
        summary_frame.groupby("lake")["high_value_percent"].idxmax()
    ].reset_index(drop=True)
    peaks.to_csv(table_root / "critical_dates.csv", index=False)
    bloom_area = float(config["analysis"]["bloom_date_area_percent"])
    comparison = summary_frame.groupby("lake", as_index=False).agg(
        observations=("date", "count"),
        mean_chlorophyll_proxy=("mean_chlorophyll_proxy", "mean"),
        maximum_chlorophyll_proxy=("mean_chlorophyll_proxy", "max"),
        mean_high_value_percent=("high_value_percent", "mean"),
        maximum_high_value_percent=("high_value_percent", "max"),
    )
    frequencies = (
        summary_frame.assign(bloom_date=summary_frame["high_value_percent"] >= bloom_area)
        .groupby("lake")["bloom_date"]
        .mean()
        .mul(100)
        .rename("bloom_date_frequency_percent")
    )
    comparison = comparison.merge(frequencies, on="lake")
    comparison.to_csv(table_root / "lake_comparison.csv", index=False)
    correlation_frame.to_csv(table_root / "pixel_correlations.csv", index=False)
    pd.DataFrame(sensitivity).to_csv(table_root / "threshold_sensitivity.csv", index=False)
    pd.DataFrame(distributions).to_csv(table_root / "pixel_distribution_sample.csv", index=False)

    seasonal = summary_frame.copy()
    seasonal["month"] = pd.to_datetime(seasonal["date"]).dt.month
    seasonal["season"] = seasonal["month"].map(
        lambda month: "seca" if month in {11, 12, 1, 2, 3, 4} else "lluviosa"
    )
    seasonal.groupby(["lake", "season"], as_index=False).agg(
        observations=("date", "count"),
        mean_proxy=("mean_chlorophyll_proxy", "mean"),
        mean_high_percent=("high_value_percent", "mean"),
    ).to_csv(table_root / "exploratory_seasonality.csv", index=False)

    _plot_temporal(summary_frame, figure_root / "temporal_evolution.png")
    _plot_distributions(pd.DataFrame(distributions), figure_root / "distributions.png")
    for lake_key, scenes in by_lake.items():
        scenes.sort(key=lambda item: item[0])
        _plot_spatial_grid(lake_key, scenes, figure_root / f"spatial_{lake_key}.png")
        _plot_difference(lake_key, scenes, threshold, figure_root / f"difference_{lake_key}.png")
        frequency, persistent = persistent_hotspots(
            [item[1] for item in scenes], threshold, config["analysis"]["persistent_fraction"]
        )
        profile = scenes[0][2]
        write_geotiff(
            table_root / f"hotspots_{lake_key}.tif",
            np.stack([frequency, persistent]),
            profile["transform"],
            str(profile["crs"]),
            ["high_frequency", "persistent_hotspot"],
            {"threshold": str(threshold), "minimum_observations": "2"},
        )
        _plot_hotspots(lake_key, frequency, figure_root / f"hotspots_{lake_key}.png")
        _write_spatial_zone_summary(
            lake_key,
            persistent,
            zone_observations,
            table_root / "spatial_zones.csv",
        )
    return summary_frame


def _zone_masks(shape: tuple[int, int]) -> dict[str, NDArray[np.bool_]]:
    rows, columns = np.indices(shape)
    middle_row = shape[0] // 2
    middle_column = shape[1] // 2
    return {
        "noroeste": (rows < middle_row) & (columns < middle_column),
        "noreste": (rows < middle_row) & (columns >= middle_column),
        "suroeste": (rows >= middle_row) & (columns < middle_column),
        "sureste": (rows >= middle_row) & (columns >= middle_column),
    }


def _summarize_zones(
    lake: str,
    date: str,
    layers: dict[str, NDArray],
    profile: dict,
    threshold: float,
) -> list[dict]:
    analytical = (layers["valid"] == 1) & (layers["water"] == 1)
    chlorophyll = layers["chlorophyll_proxy"]
    valid_chl = analytical & valid_chlorophyll_mask(chlorophyll)
    high = analytical & high_value_mask(chlorophyll, layers["surface_bloom"], threshold)
    transform = profile["transform"]
    height, width = chlorophyll.shape
    bounds = {
        "west": transform.c,
        "east": transform.c + transform.a * width,
        "north": transform.f,
        "south": transform.f + transform.e * height,
    }
    middle_longitude = (bounds["west"] + bounds["east"]) / 2
    middle_latitude = (bounds["south"] + bounds["north"]) / 2
    results = []
    for zone, zone_mask in _zone_masks(chlorophyll.shape).items():
        water = analytical & zone_mask
        concentration = valid_chl & zone_mask
        water_count = int(water.sum())
        values = chlorophyll[concentration]
        west = bounds["west"] if "oeste" in zone else middle_longitude
        east = middle_longitude if "oeste" in zone else bounds["east"]
        south = middle_latitude if zone.startswith("n") else bounds["south"]
        north = bounds["north"] if zone.startswith("n") else middle_latitude
        results.append(
            {
                "lake": lake,
                "date": date,
                "zone": zone,
                "west": west,
                "east": east,
                "south": south,
                "north": north,
                "water_pixels": water_count,
                "chlorophyll_valid_pixels": int(concentration.sum()),
                "mean_chlorophyll_proxy": float(values.mean()) if values.size else float("nan"),
                "high_value_percent": (
                    float((high & zone_mask).sum() / water_count * 100)
                    if water_count
                    else float("nan")
                ),
            }
        )
    return results


def _write_spatial_zone_summary(
    lake: str,
    persistent: NDArray,
    observations: list[dict],
    path: Path,
) -> None:
    lake_rows = pd.DataFrame(row for row in observations if row["lake"] == lake)
    rows = []
    for zone, group in lake_rows.groupby("zone"):
        first = group.sort_values("date").iloc[0]
        last = group.sort_values("date").iloc[-1]
        peak = group.loc[group["high_value_percent"].idxmax()]
        zone_mask = _zone_masks(persistent.shape)[zone]
        evaluable = zone_mask & np.isfinite(persistent)
        persistent_zone = evaluable & (persistent == 1)
        valid_pixels = int(group["chlorophyll_valid_pixels"].sum())
        estimable = group["chlorophyll_valid_pixels"] > 0
        weighted_mean = (
            float(
                np.average(
                    group.loc[estimable, "mean_chlorophyll_proxy"],
                    weights=group.loc[estimable, "chlorophyll_valid_pixels"],
                )
            )
            if valid_pixels
            else float("nan")
        )
        rows.append(
            {
                "lake": lake,
                "zone": zone,
                "west": first["west"],
                "east": first["east"],
                "south": first["south"],
                "north": first["north"],
                "observations": len(group),
                "water_pixel_observations": int(group["water_pixels"].sum()),
                "chlorophyll_valid_pixel_observations": valid_pixels,
                "chlorophyll_coverage_percent": float(
                    group["chlorophyll_valid_pixels"].sum() / group["water_pixels"].sum() * 100
                ),
                "mean_chlorophyll_proxy": weighted_mean,
                "mean_high_value_percent": float(group["high_value_percent"].mean()),
                "peak_high_value_percent": float(peak["high_value_percent"]),
                "peak_date": peak["date"],
                "first_high_value_percent": float(first["high_value_percent"]),
                "last_high_value_percent": float(last["high_value_percent"]),
                "change_first_last_pp": float(
                    last["high_value_percent"] - first["high_value_percent"]
                ),
                "persistent_area_percent": (
                    float(persistent_zone.sum() / evaluable.sum() * 100)
                    if evaluable.any()
                    else float("nan")
                ),
            }
        )
    existing = pd.read_csv(path) if path.exists() else pd.DataFrame(rows).iloc[0:0]
    combined = pd.concat(
        [existing[existing["lake"] != lake], pd.DataFrame(rows)], ignore_index=True
    )
    combined.sort_values(["lake", "zone"]).to_csv(path, index=False)


def _plot_temporal(frame: pd.DataFrame, path: Path) -> None:
    figure, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    for lake, group in frame.groupby("lake"):
        dates = pd.to_datetime(group["date"])
        axes[0].plot(dates, group["mean_chlorophyll_proxy"], marker="o", label=lake_name(lake))
        axes[1].plot(dates, group["high_value_percent"], marker="o", label=lake_name(lake))
    axes[0].set_ylabel("Proxy de clorofila-a")
    axes[1].set_ylabel("Área con valores altos (%)")
    axes[1].set_xlabel("Fecha")
    axes[0].legend()
    figure.autofmt_xdate()
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _plot_spatial_grid(lake: str, scenes: list[tuple[str, dict, dict]], path: Path) -> None:
    figure, axes = plt.subplots(3, 4, figsize=(14, 10), constrained_layout=True)
    image = None
    for axis, (date, layers, _) in zip(axes.flat, scenes, strict=False):
        chlorophyll = np.where(
            valid_chlorophyll_mask(layers["chlorophyll_proxy"]),
            layers["chlorophyll_proxy"],
            np.nan,
        )
        image = axis.imshow(chlorophyll, cmap="viridis", vmin=0, vmax=50)
        bloom = np.ma.masked_where(layers["surface_bloom"] != 1, layers["surface_bloom"])
        axis.imshow(bloom, cmap="Reds", vmin=0, vmax=1, alpha=0.9)
        axis.set_title(date)
        axis.axis("off")
    for axis in axes.flat[len(scenes) :]:
        axis.axis("off")
    figure.suptitle(f"Proxy de clorofila-a y floración superficial: {lake_name(lake)}")
    if image is not None:
        figure.colorbar(image, ax=axes, shrink=0.7, label="Proxy de clorofila-a")
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _plot_difference(
    lake: str, scenes: list[tuple[str, dict, dict]], threshold: float, path: Path
) -> None:
    first_date, first, _ = scenes[0]
    last_date, last, _ = scenes[-1]
    first_high = high_value_mask(first["chlorophyll_proxy"], first["surface_bloom"], threshold)
    last_high = high_value_mask(last["chlorophyll_proxy"], last["surface_bloom"], threshold)
    difference = last_high.astype(np.int8) - first_high.astype(np.int8)
    figure, axis = plt.subplots(figsize=(7, 5))
    image = axis.imshow(difference, cmap="bwr", vmin=-1, vmax=1)
    axis.set_title(f"Cambio de clasificación alta: {lake_name(lake)} ({first_date} a {last_date})")
    axis.axis("off")
    figure.colorbar(image, ax=axis, ticks=[-1, 0, 1], label="Desaparece / igual / aparece")
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _plot_distributions(frame: pd.DataFrame, path: Path) -> None:
    if frame.empty:
        return
    lakes = sorted(frame["lake"].unique())
    figure, axes = plt.subplots(1, len(lakes), figsize=(14, 6), squeeze=False)
    for axis, lake in zip(axes.flat, lakes, strict=True):
        subset = frame[frame["lake"] == lake]
        dates = sorted(subset["date"].unique())
        data = [subset.loc[subset["date"] == date, "chlorophyll_proxy"] for date in dates]
        axis.boxplot(data, tick_labels=dates, showfliers=False)
        axis.tick_params(axis="x", rotation=90)
        axis.set_title(lake_name(lake))
        axis.set_ylabel("Proxy de clorofila-a")
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _plot_hotspots(lake: str, frequency: NDArray, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(7, 5))
    image = axis.imshow(frequency * 100, cmap="magma", vmin=0, vmax=100)
    axis.set_title(f"Frecuencia de valores altos: {lake_name(lake)}")
    axis.axis("off")
    figure.colorbar(image, ax=axis, label="Observaciones altas (%)")
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)
