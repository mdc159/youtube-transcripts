"""Build multimodal LLM payload (OpenAI SDK shape)."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Sequence

from yt_distill.stages.frame_select import Selected
from yt_distill.core.models import Profile


class PayloadBuildError(RuntimeError):
    pass


def _frame_id(rel_path: str) -> str:
    return Path(rel_path).stem


def build_payload(
    *,
    profile: Profile,
    system_prompt: str,
    style: str,
    enriched_transcript: str,
    selected: Sequence[Selected],
    frames_root: Path,
) -> list[dict]:
    """Return the `content` list to pass as messages[0]['content']."""
    # Visual evidence index goes in the text block so frame IDs are restated
    # (some providers strip text adjacent to image blocks).
    if profile.vision and selected:
        index_lines = ["", "Visual evidence index (citable):"]
        for s in selected:
            index_lines.append(f"- {_frame_id(s.path)} (class={s.frame_class.value}, reason={s.reason})")
        index = "\n".join(index_lines)
    else:
        index = ""

    text = f"{system_prompt}\n\n{style}\n\n---\n\n# Transcript (OCR-enriched, citation-tagged)\n\n{enriched_transcript}{index}"
    msg: list[dict] = [{"type": "text", "text": text}]

    if not profile.vision:
        return msg

    # Cap images and respect per-image byte limit.
    cap = min(profile.max_images, len(selected))
    for s in list(selected)[:cap]:
        path = frames_root / s.path
        if not path.is_file():
            raise PayloadBuildError(f"missing frame file {path}")
        data = path.read_bytes()
        if len(data) > profile.max_image_bytes:
            raise PayloadBuildError(f"frame {path} exceeds max_image_bytes ({len(data)} > {profile.max_image_bytes})")
        b64 = base64.b64encode(data).decode()
        msg.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    return msg
