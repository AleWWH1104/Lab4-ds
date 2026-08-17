"""Command-line entry point for the laboratory workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .acquisition import acquire_scene, process_raw_raster
from .analysis import run_analysis
from .config import DEFAULT_CONFIG, load_config
from .report import generate_report
from .validation import validate_repository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sentinel-2 lake monitoring laboratory pipeline")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    subparsers = parser.add_subparsers(dest="command", required=True)

    acquire = subparsers.add_parser("acquire", help="Download and process official Sentinel scenes")
    acquire.add_argument("--lake", choices=["all", "atitlan", "amatitlan"], default="all")
    acquire.add_argument("--date", default="all", help="Official ISO date or all")
    acquire.add_argument("--overwrite", action="store_true")

    process = subparsers.add_parser("process", help="Rebuild analytical products from raw GeoTIFFs")
    process.add_argument("--overwrite", action="store_true")

    subparsers.add_parser("analyze", help="Generate offline tables, maps, and comparisons")
    subparsers.add_parser("validate", help="Validate all official persisted products")
    report = subparsers.add_parser("report", help="Build evidence-driven Spanish report")
    report.add_argument("--pdf", action="store_true", help="Also build PDF using pandoc/xelatex")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    if args.command == "acquire":
        selected_lakes = (
            config["lakes"] if args.lake == "all" else {args.lake: config["lakes"][args.lake]}
        )
        matched = 0
        for lake_key, lake in selected_lakes.items():
            for acquisition in lake["acquisitions"]:
                if args.date != "all" and acquisition["date"] != args.date:
                    continue
                raw_path, product_path = acquire_scene(
                    lake_key,
                    lake,
                    acquisition,
                    int(config["provenance"]["resolution_m"]),
                    Path("data/raw"),
                    Path("data/processed"),
                    args.overwrite,
                )
                matched += 1
                print(f"Acquired {lake_key} {acquisition['date']}: {raw_path} -> {product_path}")
        if not matched:
            raise SystemExit(f"No official acquisition matches date {args.date}")
    elif args.command == "process":
        processed = 0
        for lake_key, lake in config["lakes"].items():
            for acquisition in lake["acquisitions"]:
                raw_path = Path("data/raw") / lake_key / f"{acquisition['date']}.tif"
                product_path = Path("data/processed") / lake_key / f"{acquisition['date']}.tif"
                if raw_path.exists() and (args.overwrite or not product_path.exists()):
                    process_raw_raster(raw_path, product_path)
                    processed += 1
        print(f"Processed {processed} raw raster(s)")
    elif args.command == "analyze":
        frame = run_analysis(config)
        print(f"Analyzed {len(frame)} scene(s); outputs written under outputs/")
    elif args.command == "validate":
        result = validate_repository(config)
        print(json.dumps(result, indent=2))
        if result["status"] != "valid":
            raise SystemExit(1)
    elif args.command == "report":
        markdown, pdf = generate_report(config, build_pdf=args.pdf)
        print(f"Report source: {markdown}")
        if pdf:
            print(f"Report PDF: {pdf}")
