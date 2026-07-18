"""yt-distill — single console entry point.

Thin dispatcher: each subcommand forwards argv verbatim to the owning
module's existing `main(argv)` so every historical flag keeps working.
"""
from __future__ import annotations

import importlib
import os
import re
import sys
from pathlib import Path

from yt_distill.core.errors import YtDistillError

# subcommand -> (module, attr, argv prefix to prepend)
_COMMANDS: dict[str, tuple[str, str, list[str]]] = {
    "extract": ("yt_distill.pipeline.extract", "main", []),
    "refs": ("yt_distill.stages.references", "main", []),
    "distill": ("yt_distill.pipeline.distill", "main", []),
    "review": ("yt_distill.pipeline.review", "main", []),
    "run": ("yt_distill.pipeline.run", "main", []),
    "enrich": ("yt_distill.stages.visual", "main", []),
    "clean": ("yt_distill.clean", "main", []),
    "doctor": ("yt_distill.core.models", "main", ["doctor"]),
}

_USAGE = (
    "usage: yt-distill <command> [args]\n\n"
    "commands:\n"
    + "\n".join(f"  {name}" for name in _COMMANDS)
    + "\n\nRun `yt-distill <command> --help` for command-specific flags.\n"
)

_URL_SHAPE = re.compile(r"^https?://|^youtu\.be/|youtube\.com/")


def _validate_inputs(cmd: str, args: list[str]) -> None:
    if not args or any(arg in ("-h", "--help") for arg in args):
        return
    value = next((arg for arg in args if not arg.startswith("-")), None)
    if value is None:
        return

    if cmd in ("extract", "run"):
        if not Path(value).is_file() and not _URL_SHAPE.search(value):
            raise YtDistillError(
                f"source not found and not a URL: {value} — pass an existing file or a http(s)/YouTube URL")
    elif cmd in ("distill", "review", "refs", "enrich"):
        candidate = Path(value)
        if not candidate.is_absolute():
            base = Path(os.environ.get("YT_GENERATED_DATA_DIR") or "Generated_Data")
            candidate = (base / candidate).resolve()
        if not (candidate / "artifact_manifest.json").is_file():
            raise YtDistillError(
                f"no artifact_manifest.json in {candidate} — run 'yt-distill extract' first")


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252; artifact text is UTF-8 (⚠, —, etc.).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help"):
        print(_USAGE, end="")
        return 0
    if not argv:
        print(_USAGE, end="", file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    entry = _COMMANDS.get(cmd)
    if entry is None:
        print(f"yt-distill: unknown command: {cmd}\n\n{_USAGE}", end="", file=sys.stderr)
        return 2
    module_name, attr, prefix = entry
    try:
        _validate_inputs(cmd, rest)
        module = importlib.import_module(module_name)
        rc = getattr(module, attr)(prefix + rest)
    except YtDistillError as exc:
        print(f"yt-distill {cmd}: {exc}", file=sys.stderr)
        return 1
    return 0 if rc is None else int(rc)


if __name__ == "__main__":
    raise SystemExit(main())
