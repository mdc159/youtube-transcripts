"""yt-distill — single console entry point.

Thin dispatcher: each subcommand forwards argv verbatim to the owning
module's existing `main(argv)` so every historical flag keeps working.
"""
from __future__ import annotations

import importlib
import sys

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
    module = importlib.import_module(module_name)
    rc = getattr(module, attr)(prefix + rest)
    return 0 if rc is None else int(rc)


if __name__ == "__main__":
    raise SystemExit(main())
