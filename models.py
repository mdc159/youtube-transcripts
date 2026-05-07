"""Model profile resolution + capability validation (doctor)."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class Profile:
    name: str
    base_url: str
    model: str
    vision: bool
    reasoning: bool
    api_key_env: str
    max_images: int
    max_image_bytes: int


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(Path(path).read_text())


def resolve(cli: Optional[str], models_yaml: Path) -> Profile:
    cfg = _load_yaml(models_yaml)
    name = cli or os.environ.get("DISTILL_MODEL") or cfg.get("default")
    if not name:
        raise SystemExit("models.yaml has no `default` and no profile was specified")
    profiles = cfg.get("profiles", {})
    if name not in profiles:
        raise SystemExit(f"profile {name!r} not found. Available: {sorted(profiles)}")
    p = profiles[name]
    return Profile(
        name=name,
        base_url=p["base_url"],
        model=p["model"],
        vision=bool(p.get("vision", False)),
        reasoning=bool(p.get("reasoning", False)),
        api_key_env=p["api_key_env"],
        max_images=int(p.get("max_images", 16)),
        max_image_bytes=int(p.get("max_image_bytes", 5_242_880)),
    )
