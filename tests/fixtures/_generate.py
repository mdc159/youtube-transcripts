"""Generates synthetic frames that exercise the classifier signals.
Run once: `uv run python tests/fixtures/_generate.py`
"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

OUT = Path(__file__).parent
SZ = (512, 384)
FONT = ImageFont.load_default()


def _frame(name: str, lines: list[str], bg=(255, 255, 255)) -> None:
    img = Image.new("RGB", SZ, bg)
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        d.text((10, 10 + i * 16), ln, fill=(0, 0, 0), font=FONT)
    img.save(OUT / name, "JPEG", quality=85)


_frame("frame_code.jpg", [
    "def fetch_user(user_id):",
    "    return db.query(User).get(user_id)",
    "",
    "class UserService:",
    "    def __init__(self, db):",
    "        self.db = db",
    "",
    "    def all_users(self) -> list[User]:",
    "        return self.db.query(User).all()",
])
_frame("frame_slide.jpg", [
    "Building a RAG Pipeline",
    "",
    "Step 1: Ingest documents",
    "Step 2: Chunk and embed",
    "Step 3: Store in vector DB",
    "Step 4: Retrieve top-k",
    "Step 5: Generate response",
])
_frame("frame_ui.jpg", ["Settings", "Account", "Privacy", "Save"])
_frame("frame_diagram.jpg", ["Embeddings"])  # mostly empty -> low text density
_frame("frame_other.jpg", ["misc background visual without code or slides"])
