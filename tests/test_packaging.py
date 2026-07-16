"""The project installs as a src-layout package; vendor stays importable."""
import importlib


def test_yt_distill_package_importable():
    for mod in (
        "yt_distill",
        "yt_distill.core",
        "yt_distill.stages",
        "yt_distill.pipeline",
        "yt_distill.output",
    ):
        importlib.import_module(mod)


def test_vendor_still_importable():
    importlib.import_module("vendor.claude_video.scripts")
