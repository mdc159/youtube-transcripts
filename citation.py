"""Citation token extraction and validation (spec §6)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Set


_SEG = re.compile(r"seg#(\d+)")
_FRAME_FULL = re.compile(r"frame_\d{3}_t-\d{2}-\d{2}")
_FRAME_SHORT = re.compile(r"\bframe_(\d{3})\b(?!_t)")
_CLUSTER = re.compile(r"cluster_id=([a-zA-Z0-9_]+)")
_TIMESTAMP = re.compile(r"\bt=\d{2}:\d{2}(?:[–-]\d{2}:\d{2})?")
# repo:path/to/file#L10-L40@SHA — line range optional, SHA 7-40 hex chars.
_REPO = re.compile(r"repo:([\w][\w./-]*?)(?:#L(\d+)(?:-L(\d+))?)?@([0-9a-fA-F]{7,40})")


@dataclass
class Citation:
    kind: str  # segment | frame | cluster | timestamp | repo
    value: str
    raw: str


@dataclass
class ResolutionContext:
    segment_ids: Set[int]
    frame_ids: Set[str]
    cluster_ids: Set[str]
    # "path@fullsha" for every file present in a pinned repo snapshot index.
    repo_refs: Set[str] = field(default_factory=set)


@dataclass
class ValidationResult:
    citations: list[Citation]
    unresolved: list[Citation]


def extract_citations(text: str) -> list[Citation]:
    out: list[Citation] = []
    for m in _SEG.finditer(text):
        out.append(Citation(kind="segment", value=m.group(1), raw=m.group(0)))
    for m in _FRAME_FULL.finditer(text):
        out.append(Citation(kind="frame", value=m.group(0), raw=m.group(0)))
    for m in _FRAME_SHORT.finditer(text):
        out.append(Citation(kind="frame", value=m.group(0), raw=m.group(0)))
    for m in _CLUSTER.finditer(text):
        out.append(Citation(kind="cluster", value=m.group(1), raw=m.group(0)))
    for m in _TIMESTAMP.finditer(text):
        out.append(Citation(kind="timestamp", value=m.group(0), raw=m.group(0)))
    for m in _REPO.finditer(text):
        out.append(Citation(kind="repo", value=f"{m.group(1)}@{m.group(4)}", raw=m.group(0)))
    return out


def _repo_resolves(value: str, repo_refs: Set[str]) -> bool:
    """`path@sha` resolves if a snapshot index entry has the same path and a
    full SHA that starts with the cited (possibly short) SHA."""
    path, _, sha = value.rpartition("@")
    sha = sha.lower()
    for ref in repo_refs:
        ref_path, _, ref_sha = ref.rpartition("@")
        if ref_path == path and ref_sha.lower().startswith(sha):
            return True
    return False


def validate_citations(text: str, ctx: ResolutionContext) -> ValidationResult:
    cits = extract_citations(text)
    unresolved: list[Citation] = []
    for c in cits:
        if c.kind == "segment" and int(c.value) not in ctx.segment_ids:
            unresolved.append(c)
        elif c.kind == "frame":
            # Match either full or short form: short form `frame_NNN` resolves
            # if any frame_id starts with `frame_NNN_`.
            if c.value not in ctx.frame_ids and not any(fid.startswith(c.value + "_") for fid in ctx.frame_ids):
                unresolved.append(c)
        elif c.kind == "cluster" and c.value not in ctx.cluster_ids:
            unresolved.append(c)
        elif c.kind == "repo" and not _repo_resolves(c.value, ctx.repo_refs):
            unresolved.append(c)
        # timestamps are always resolvable (informational only)
    return ValidationResult(citations=cits, unresolved=unresolved)
