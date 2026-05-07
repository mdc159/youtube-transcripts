import pytest
import extract


def test_parse_args_minimal():
    ns = extract._parse_args(["https://x"])
    assert ns.source == "https://x"
    assert ns.no_frames is False
    assert ns.force is False


def test_parse_args_clip_range():
    ns = extract._parse_args(["video.mp4", "--start", "10", "--end", "30"])
    assert ns.start == 10.0
    assert ns.end == 30.0


def test_parse_args_force_flags():
    ns = extract._parse_args(["x", "--force", "--force-ocr", "--keep-video", "--no-frames"])
    assert ns.force is True
    assert ns.force_ocr is True
    assert ns.keep_video is True
    assert ns.no_frames is True
