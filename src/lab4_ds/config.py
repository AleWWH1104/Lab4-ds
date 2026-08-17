"""Configuration loading and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = Path("config/lakes.json")


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if set(config["lakes"]) != {"atitlan", "amatitlan"}:
        raise ValueError("Configuration must contain exactly Atitlan and Amatitlan")
    for lake, details in config["lakes"].items():
        if len(details["bbox"]) != 4 or details["bbox"][0] >= details["bbox"][2]:
            raise ValueError(f"Invalid bounding box for {lake}")
        dates = [item["date"] for item in details["acquisitions"]]
        if len(dates) != 11 or len(set(dates)) != 11:
            raise ValueError(f"{lake} must contain 11 unique official dates")
    return config
