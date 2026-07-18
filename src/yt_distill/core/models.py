"""Model profile resolution + capability validation (doctor)."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from openai import OpenAI

REPO_ROOT = Path(__file__).resolve().parents[3]


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
    reasoning_effort: str | None = None  # minimal|low|medium|high; None = model default


@dataclass
class DoctorResult:
    ok: bool
    text_probe: bool = False
    image_probe: Optional[bool] = None  # None means skipped
    reasoning_probe: Optional[bool] = None
    failure_reason: str = ""


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


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
        reasoning_effort=p.get("reasoning_effort"),
    )


def _cache_dir() -> Path:
    d = Path.home() / ".cache" / "youtube-transcripts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_key(profile: Profile) -> str:
    digest = hashlib.sha1((profile.base_url + profile.model).encode()).hexdigest()[:8]
    return f"model_doctor_{profile.name}_{digest}.json"


def _save_doctor(cache_path: Path, result: DoctorResult) -> DoctorResult:
    cache_path.write_text(json.dumps({"timestamp": time.time(), "result": result.__dict__}), encoding="utf-8")
    return result


def doctor(
    profile: Profile,
    *,
    models_yaml: Path,
    probe_image: bool = True,
    fixture_image: Optional[Path] = None,
    cache_ttl_seconds: int = 3600,
) -> DoctorResult:
    """Run capability probes. Cached for `cache_ttl_seconds` (default 1h)."""
    cache_path = _cache_dir() / _cache_key(profile)
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if time.time() - cached["timestamp"] < cache_ttl_seconds:
                return DoctorResult(**cached["result"])
        except Exception:  # noqa: BLE001
            pass

    api_key = os.environ.get(profile.api_key_env, "")
    if not api_key:
        return DoctorResult(
            ok=False,
            failure_reason=f"environment variable {profile.api_key_env} not set (api key missing)",
        )

    client = OpenAI(base_url=profile.base_url, api_key=api_key)

    # 1. Text probe
    try:
        client.chat.completions.create(
            model=profile.model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
    except Exception as e:  # noqa: BLE001
        return _save_doctor(
            cache_path,
            DoctorResult(ok=False, text_probe=False, failure_reason=f"text probe: {e}"),
        )

    # 2. Image probe (if profile claims vision and probe_image)
    image_ok: Optional[bool] = None
    if profile.vision and probe_image:
        img_path = fixture_image or (
            REPO_ROOT / "tests/fixtures/tiny_image.jpg"
        )
        try:
            b64 = base64.b64encode(img_path.read_bytes()).decode()
            client.chat.completions.create(
                model=profile.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "describe in one word"},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                            },
                        ],
                    }
                ],
                max_tokens=10,
            )
            image_ok = True
        except Exception as e:  # noqa: BLE001
            return _save_doctor(
                cache_path,
                DoctorResult(
                    ok=False,
                    text_probe=True,
                    image_probe=False,
                    failure_reason=f"image probe: {e}",
                ),
            )

    # 3. Reasoning probe
    reasoning_ok: Optional[bool] = None
    if profile.reasoning:
        try:
            client.chat.completions.create(
                model=profile.model,
                messages=[{"role": "user", "content": "1+1"}],
                max_tokens=5,
                extra_body={"reasoning": {"enabled": True}},
            )
            reasoning_ok = True
        except Exception as e:  # noqa: BLE001
            return _save_doctor(
                cache_path,
                DoctorResult(
                    ok=False,
                    text_probe=True,
                    image_probe=image_ok,
                    reasoning_probe=False,
                    failure_reason=f"reasoning probe: {e}",
                ),
            )

    return _save_doctor(
        cache_path,
        DoctorResult(
            ok=True,
            text_probe=True,
            image_probe=image_ok,
            reasoning_probe=reasoning_ok,
        ),
    )


def main(argv=None):
    import argparse

    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("doctor")
    d.add_argument("--profile", required=True)
    d.add_argument("--no-image-probe", action="store_true")
    args = p.parse_args(argv)
    if args.cmd == "doctor":
        models_yaml = REPO_ROOT / "models.yaml"
        prof = resolve(cli=args.profile, models_yaml=models_yaml)
        res = doctor(
            prof,
            models_yaml=models_yaml,
            probe_image=not args.no_image_probe,
        )
        print(
            f"profile={prof.name} ok={res.ok} text={res.text_probe} "
            f"image={res.image_probe} reasoning={res.reasoning_probe}"
        )
        if not res.ok:
            print(f"failure: {res.failure_reason}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
