import base64
from pathlib import Path
import pytest
from yt_distill.core.payload import build_payload, PayloadBuildError
from yt_distill.stages.frame_select import Selected
from yt_distill.stages.frame_ocr import FrameClass
from yt_distill.core.models import Profile


def _profile(vision=True):
    return Profile(name="t", base_url="http://x", model="m", vision=vision, reasoning=False, api_key_env="X", max_images=4, max_image_bytes=5_000_000)


def test_payload_text_only_when_no_vision():
    p = _profile(vision=False)
    msg = build_payload(profile=p, system_prompt="contract", style="style", enriched_transcript="t", selected=[], frames_root=Path("."))
    assert isinstance(msg, list)
    assert msg[0]["type"] == "text"
    assert all(m["type"] != "image_url" for m in msg)


def test_payload_includes_image_blocks(tmp_path):
    img = tmp_path / "frame_001_t-00-05.jpg"
    img.write_bytes(b"\xff\xd8\xff" + b"x" * 200 + b"\xff\xd9")  # minimal JPEG-ish
    sel = [Selected(path="frame_001_t-00-05.jpg", timestamp_seconds=5.0, frame_class=FrameClass.SLIDE_TEXT, reason="r")]
    p = _profile()
    msg = build_payload(profile=p, system_prompt="c", style="s", enriched_transcript="t", selected=sel, frames_root=tmp_path)
    image_blocks = [m for m in msg if m["type"] == "image_url"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_payload_caps_at_profile_max_images(tmp_path):
    sels = []
    for i in range(10):
        img = tmp_path / f"frame_{i:03d}_t-00-{i:02d}.jpg"
        img.write_bytes(b"\xff\xd8\xff" + b"x" * 100 + b"\xff\xd9")
        sels.append(Selected(path=img.name, timestamp_seconds=float(i), frame_class=FrameClass.SLIDE_TEXT, reason="r"))
    p = _profile()  # max_images=4
    msg = build_payload(profile=p, system_prompt="c", style="s", enriched_transcript="t", selected=sels, frames_root=tmp_path)
    assert len([m for m in msg if m["type"] == "image_url"]) == 4
