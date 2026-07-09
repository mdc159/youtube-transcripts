"""Phase 1.5: harvest reference URLs → classify → snapshot repos / fetch docs.

Standalone and idempotent, re-runnable off the cached artifact tree:

    uv run python reference_follower.py <title-dir> [--max-repo-mb 200] \
        [--max-fetches 10] [--no-comments] [--force]

Reads Generated_Data/<title>/ (manifest, transcript, ocr.json), harvests URLs
from the video description, pinned/top comments, transcript segments, and OCR'd
frames — recording where each was found — then:

  - github_repo   → shallow-clone, pin commit SHA, snapshot README + build/setup
                    files + files referenced in the tutorial, with provenance.
  - docs          → fetch → markdown, stored as auxiliary sources.
  - asset_download / other → recorded with provenance, never fetched.

Outputs references.json plus a refs/ tree under the video's artifact dir.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from enrichment import parse_formatted_transcript
from manifest import Manifest, MANIFEST_FILENAME

REFERENCES_FILENAME = "references.json"
REFS_DIRNAME = "refs"
SOURCE_META_FILENAME = "source_meta.json"
SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# URL harvesting
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://[^\s<>\"'\)\]\}]+", re.IGNORECASE)
_TRAILING_PUNCT = ".,;:!?…"

# Query params that identify a session/campaign, not a resource.
_TRACKING_PARAMS = {
    "si", "feature", "ref", "ref_", "fbclid", "gclid",
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
}

_DOC_HOST_HINTS = (
    "docs.", "documentation.", "developer.", "developers.", "learn.", "wiki.",
    ".readthedocs.io", "readthedocs.org", "devdocs.io",
    "dev.epicgames.com", "docs.unrealengine.com", "learn.microsoft.com",
    "developer.mozilla.org", "stackoverflow.com", "gist.github.com",
)
_DOC_PATH_HINTS = ("/docs/", "/documentation/", "/manual/", "/wiki/", "/learn/", "/guide/", "/guides/")

_ASSET_EXTS = (
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".fbx", ".obj", ".gltf", ".glb", ".blend",
    ".exr", ".hdr", ".hdri", ".uasset", ".unitypackage",
)
_ASSET_HOSTS = (
    "drive.google.com", "dropbox.com", "www.dropbox.com", "mega.nz",
    "gumroad.com", "fab.com", "www.fab.com", "quixel.com", "polyhaven.com",
    "sketchfab.com", "itch.io", "mediafire.com", "we.tl", "wetransfer.com",
)

# Snapshot selection: README + build/setup files (fnmatch patterns, lowercase).
_BUILD_SETUP_PATTERNS = (
    "readme*", "license*", "contributing*", "install*", "setup*", "changelog*",
    "pyproject.toml", "requirements*.txt", "setup.py", "setup.cfg", "uv.lock",
    "package.json", "package-lock.json", "yarn.lock", "bun.lock", "tsconfig.json",
    "cargo.toml", "go.mod", "gemfile", "pom.xml", "build.gradle*",
    "makefile", "cmakelists.txt", "dockerfile", "docker-compose*",
    ".env.example", "*.uproject", "*.uplugin", "*.sln", "*.code-workspace",
)


def harvest_urls(text: str) -> list[str]:
    """Extract candidate URLs from free text, trimming trailing punctuation."""
    found = []
    for m in _URL_RE.finditer(text or ""):
        url = m.group(0).rstrip(_TRAILING_PUNCT)
        # Strip a balanced-looking trailing paren from markdown "(url)" wrappers.
        while url.endswith(")") and url.count("(") < url.count(")"):
            url = url[:-1].rstrip(_TRAILING_PUNCT)
        if url:
            found.append(url)
    return found


def normalize_url(url: str) -> str:
    """Canonicalize for dedup: lowercase host, drop tracking params + fragment."""
    parsed = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if k.lower() not in _TRACKING_PARAMS]
    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path.rstrip("/") or "/",
        parsed.params,
        urlencode(query),
        "",  # fragment dropped
    ))


def classify_url(url: str) -> str:
    """github_repo | docs | asset_download | other."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()

    if host in ("github.com", "www.github.com"):
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2:
            return "github_repo"
        return "other"

    if any(path.endswith(ext) for ext in _ASSET_EXTS) or host in _ASSET_HOSTS:
        return "asset_download"

    if any(h in host for h in _DOC_HOST_HINTS) or any(h in path for h in _DOC_PATH_HINTS):
        return "docs"

    return "other"


def parse_github_repo(url: str) -> tuple[str, str, str | None]:
    """Return (owner, repo, referenced_path_or_None) from any github.com URL."""
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    referenced = None
    if len(parts) >= 4 and parts[2] in ("blob", "tree", "raw"):
        referenced = "/".join(parts[4:]) or None
    return owner, repo, referenced


# ---------------------------------------------------------------------------
# Source gathering (description / comments / transcript / OCR)
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch_source_meta(source_url: str, *, with_comments: bool, max_comments: int,
                       cookies_browser: str | None) -> dict:
    """One yt-dlp call for description (+ top comments when enabled)."""
    cmd = ["yt-dlp", "--no-warnings", "--skip-download", "--dump-single-json"]
    if with_comments:
        cmd += ["--write-comments", "--extractor-args",
                f"youtube:max_comments={max_comments},all,0,0;comment_sort=top"]
    if cookies_browser:
        cmd += ["--cookies-from-browser", cookies_browser]
    cmd.append(source_url)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp source-meta fetch failed: {r.stderr.strip()[:500]}")
    info = json.loads(r.stdout)
    comments = []
    for c in info.get("comments") or []:
        comments.append({
            "id": c.get("id"),
            "text": c.get("text") or "",
            "author_is_uploader": bool(c.get("author_is_uploader")),
            "is_pinned": bool(c.get("is_pinned")),
        })
    return {
        "fetched_at": _utc_now(),
        "description": info.get("description") or "",
        "upload_date": info.get("upload_date"),
        "channel": info.get("channel") or info.get("uploader"),
        "comments": comments,
    }


def _load_or_fetch_source_meta(out_dir: Path, source_url: str, *, with_comments: bool,
                               max_comments: int, cookies_browser: str | None,
                               force: bool) -> dict:
    meta_path = out_dir / REFS_DIRNAME / SOURCE_META_FILENAME
    if meta_path.exists() and not force:
        print("[refs] source_meta: reusing cached")
        return json.loads(meta_path.read_text())
    if not source_url.startswith(("http://", "https://")):
        print("[refs] source_meta: local source, no description/comments")
        meta = {"fetched_at": _utc_now(), "description": "", "upload_date": None,
                "channel": None, "comments": []}
    else:
        try:
            meta = _fetch_source_meta(source_url, with_comments=with_comments,
                                      max_comments=max_comments,
                                      cookies_browser=cookies_browser)
        except Exception as exc:  # noqa: BLE001 - degrade to transcript/OCR-only harvest
            print(f"[refs] source_meta fetch failed ({exc}); harvesting transcript/OCR only",
                  file=sys.stderr)
            meta = {"fetched_at": _utc_now(), "description": "", "upload_date": None,
                    "channel": None, "comments": [], "fetch_error": str(exc)[:500]}
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True))
    return meta


def collect_candidates(out_dir: Path, source_meta: dict) -> dict[str, dict]:
    """Harvest URLs from every evidence stream. Returns normalized_url → record."""
    candidates: dict[str, dict] = {}

    def _add(url: str, where: str, context: str) -> None:
        norm = normalize_url(url)
        rec = candidates.setdefault(norm, {
            "url": url,
            "normalized_url": norm,
            "kind": classify_url(url),
            "found_in": [],
        })
        entry = {"where": where, "context": context.strip()[:200]}
        if entry not in rec["found_in"]:
            rec["found_in"].append(entry)

    desc = source_meta.get("description") or ""
    for url in harvest_urls(desc):
        idx = desc.find(url)
        _add(url, "description", desc[max(0, idx - 60):idx + len(url) + 60])

    for c in source_meta.get("comments") or []:
        where = "pinned_comment" if c.get("is_pinned") else (
            "uploader_comment" if c.get("author_is_uploader") else "comment")
        for url in harvest_urls(c.get("text") or ""):
            _add(url, where, c.get("text") or "")

    transcript = out_dir / f"{out_dir.name}_formatted_transcript.txt"
    if transcript.exists():
        for seg in parse_formatted_transcript(transcript):
            for url in harvest_urls(seg.text):
                _add(url, f"seg#{seg.seg_id}", seg.text)

    ocr_path = out_dir / "ocr.json"
    if ocr_path.exists():
        from frame_ocr import read_ocr_json
        for frame in read_ocr_json(ocr_path):
            for url in harvest_urls(frame.ocr_text):
                _add(url, Path(frame.path).stem, frame.ocr_text)

    return candidates


# ---------------------------------------------------------------------------
# github_repo snapshot
# ---------------------------------------------------------------------------

def _dir_size_bytes(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _tutorial_tokens(out_dir: Path) -> set[str]:
    """Lowercased filename-ish tokens seen in transcript + OCR text."""
    text_parts: list[str] = []
    transcript = out_dir / f"{out_dir.name}_clean_text.txt"
    if transcript.exists():
        text_parts.append(transcript.read_text())
    ocr_path = out_dir / "ocr.json"
    if ocr_path.exists():
        from frame_ocr import read_ocr_json
        text_parts.extend(f.ocr_text for f in read_ocr_json(ocr_path))
    blob = "\n".join(text_parts).lower()
    # Tokens that look like filenames or dotted module paths.
    return set(re.findall(r"[\w][\w./-]*\.[a-z]{1,10}\b", blob))


def snapshot_repo(url: str, dest_root: Path, *, max_repo_mb: int,
                  tutorial_tokens: set[str]) -> dict:
    """Shallow-clone, pin SHA, snapshot key files. Returns detail dict."""
    owner, repo, referenced = parse_github_repo(url)
    clone_url = f"https://github.com/{owner}/{repo}.git"

    with tempfile.TemporaryDirectory(prefix="refclone_") as tmp:
        tmp_repo = Path(tmp) / repo
        r = subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(tmp_repo)],
            capture_output=True, text=True, timeout=600,
        )
        if r.returncode != 0:
            raise RuntimeError(f"clone failed for {clone_url}: {r.stderr.strip()[:300]}")

        sha = subprocess.run(
            ["git", "-C", str(tmp_repo), "rev-parse", "HEAD"],
            capture_output=True, text=True,
        ).stdout.strip()

        size = _dir_size_bytes(tmp_repo)
        if size > max_repo_mb * 1024 * 1024:
            raise RuntimeError(
                f"repo {owner}/{repo} is {size / 1e6:.0f} MB > --max-repo-mb {max_repo_mb}; skipped")

        all_files = [p for p in tmp_repo.rglob("*")
                     if p.is_file() and ".git" not in p.parts]

        selected: dict[str, str] = {}  # rel path → why
        import fnmatch
        for p in all_files:
            rel = str(p.relative_to(tmp_repo))
            name = p.name.lower()
            if any(fnmatch.fnmatch(name, pat) for pat in _BUILD_SETUP_PATTERNS):
                selected.setdefault(rel, "build_setup")
            elif name in tutorial_tokens or rel.lower() in tutorial_tokens:
                selected.setdefault(rel, "referenced_in_tutorial")
        if referenced:
            for p in all_files:
                rel = str(p.relative_to(tmp_repo))
                if rel == referenced or rel.startswith(referenced.rstrip("/") + "/"):
                    selected.setdefault(rel, "linked_directly")

        snap_dir = dest_root / f"{owner}__{repo}@{sha[:12]}"
        if snap_dir.exists():
            shutil.rmtree(snap_dir)
        copied = []
        for rel, why in sorted(selected.items()):
            src = tmp_repo / rel
            dst = snap_dir / "snapshot" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied.append({"path": rel, "why": why})

        file_index = sorted(str(p.relative_to(tmp_repo)) for p in all_files)
        detail = {
            "owner": owner,
            "repo": repo,
            "clone_url": clone_url,
            "sha": sha,
            "clone_date": _utc_now(),
            "size_bytes": size,
            "snapshot_dir": str(snap_dir.name),
            "files_snapshotted": copied,
            "file_index_count": len(file_index),
        }
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / "provenance.json").write_text(json.dumps(
            {**detail, "file_index": file_index}, indent=2, sort_keys=True))
        return detail


# ---------------------------------------------------------------------------
# docs fetch
# ---------------------------------------------------------------------------

def fetch_doc(url: str, dest_root: Path) -> dict:
    """Fetch a docs page → markdown-ish text under refs/docs/."""
    import hashlib

    import requests

    r = requests.get(url, timeout=60, headers={"User-Agent": "youtube-transcripts/refs"})
    r.raise_for_status()
    content_type = r.headers.get("content-type", "")
    body = r.text

    if "html" in content_type:
        try:
            import html2text
            h = html2text.HTML2Text()
            h.ignore_images = True
            h.body_width = 0
            body = h.handle(body)
        except ImportError:
            body = re.sub(r"<script.*?</script>|<style.*?</style>", "", body,
                          flags=re.DOTALL | re.IGNORECASE)
            body = re.sub(r"<[^>]+>", " ", body)
            body = re.sub(r"[ \t]+", " ", body)

    slug = re.sub(r"[^\w-]+", "_", urlparse(url).path).strip("_")[:60] or "index"
    digest = hashlib.sha1(normalize_url(url).encode()).hexdigest()[:10]
    dest = dest_root / "docs" / f"{digest}_{slug}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    header = f"<!-- source: {url}\n     fetched_at: {_utc_now()} -->\n\n"
    dest.write_text(header + body)
    return {"path": f"{REFS_DIRNAME}/docs/{dest.name}", "bytes": dest.stat().st_size,
            "fetched_at": _utc_now()}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _resolve_out_dir(title_or_path: str) -> Path:
    p = Path(title_or_path)
    if p.is_absolute() and p.is_dir():
        return p
    base = Path(os.environ.get("YT_GENERATED_DATA_DIR") or "Generated_Data")
    return (base / title_or_path).resolve()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Harvest, classify, and snapshot references linked from a video.")
    p.add_argument("title", help="Artifact dir name under Generated_Data, or absolute path")
    p.add_argument("--max-repo-mb", type=int, default=200,
                   help="Skip repos whose shallow clone exceeds this size (default 200)")
    p.add_argument("--max-fetches", type=int, default=10,
                   help="Cap network fetches (clones + doc pages) per run (default 10)")
    p.add_argument("--max-comments", type=int, default=40,
                   help="Top comments to scan for links (default 40)")
    p.add_argument("--no-comments", action="store_true", help="Skip comment harvesting")
    p.add_argument("--cookies-from-browser", default=None)
    p.add_argument("--force", action="store_true", help="Re-run even if references.json is intact")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    import env_bootstrap
    env_bootstrap.load()
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    out_dir = _resolve_out_dir(args.title)
    manifest_path = out_dir / MANIFEST_FILENAME
    if not manifest_path.exists():
        raise RuntimeError(f"no {MANIFEST_FILENAME} in {out_dir}; run extract.py first")

    data = json.loads(manifest_path.read_text())
    manifest = Manifest(out_dir, data)
    source_url = data.get("source_url") or ""

    references_path = out_dir / REFERENCES_FILENAME
    if not args.force and references_path.exists() and manifest.file_intact("references", "references_json"):
        print("[refs] skipping (already complete)")
        return 0

    refs_root = out_dir / REFS_DIRNAME
    refs_root.mkdir(parents=True, exist_ok=True)

    source_meta = _load_or_fetch_source_meta(
        out_dir, source_url,
        with_comments=not args.no_comments,
        max_comments=args.max_comments,
        cookies_browser=args.cookies_from_browser,
        force=args.force,
    )

    candidates = collect_candidates(out_dir, source_meta)
    print(f"[refs] harvested {len(candidates)} unique URLs")

    tokens = _tutorial_tokens(out_dir)
    fetches_used = 0
    records = []
    for rec in candidates.values():
        kind = rec["kind"]
        try:
            if kind == "github_repo":
                if fetches_used >= args.max_fetches:
                    rec["status"], rec["detail"] = "skipped", {"reason": "max_fetches reached"}
                else:
                    fetches_used += 1
                    rec["detail"] = snapshot_repo(
                        rec["url"], refs_root,
                        max_repo_mb=args.max_repo_mb, tutorial_tokens=tokens)
                    rec["status"] = "snapshotted"
                    print(f"[refs] snapshotted {rec['detail']['owner']}/{rec['detail']['repo']}"
                          f"@{rec['detail']['sha'][:12]} "
                          f"({len(rec['detail']['files_snapshotted'])} files)")
            elif kind == "docs":
                if fetches_used >= args.max_fetches:
                    rec["status"], rec["detail"] = "skipped", {"reason": "max_fetches reached"}
                else:
                    fetches_used += 1
                    rec["detail"] = fetch_doc(rec["url"], refs_root)
                    rec["status"] = "fetched"
                    print(f"[refs] fetched doc {rec['url']}")
            else:
                rec["status"], rec["detail"] = "recorded", {}
        except Exception as exc:  # noqa: BLE001 - per-reference isolation
            rec["status"], rec["detail"] = "error", {"reason": str(exc)[:500]}
            print(f"[refs] {rec['url']}: {exc}", file=sys.stderr)
        records.append(rec)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "source_id": data.get("source_id"),
        "harvested_at": _utc_now(),
        "sources_scanned": {
            "description": bool(source_meta.get("description")),
            "comments_scanned": len(source_meta.get("comments") or []),
            "transcript": (out_dir / f"{out_dir.name}_formatted_transcript.txt").exists(),
            "ocr": (out_dir / "ocr.json").exists(),
        },
        "budgets": {"max_repo_mb": args.max_repo_mb, "max_fetches": args.max_fetches,
                    "fetches_used": fetches_used},
        "references": sorted(records, key=lambda r: r["normalized_url"]),
    }
    references_path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    manifest.set_references({"harvested_at": payload["harvested_at"],
                             "reference_count": len(records), "files": {}})
    manifest.record_file("references", "references_json", references_path)
    manifest.save()

    counts: dict[str, int] = {}
    for r in records:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    print(f"[refs] done: {counts or 'no references found'} → {references_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
