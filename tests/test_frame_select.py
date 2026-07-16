import json

from PIL import Image
from yt_distill.stages.frame_select import (
    ChangePoint,
    Selected,
    SelectionResult,
    detect_scene_changes,
    select_frames,
    write_selected_frames_json,
)
from yt_distill.stages.frame_ocr import FrameRecord, FrameClass


def _solid(path, color):
    Image.new("RGB", (64, 64), color).save(path, "JPEG")


def test_detects_change_between_distinct_solids(tmp_path):
    paths = []
    for i, c in enumerate([(0, 0, 0), (0, 0, 0), (255, 255, 255), (255, 255, 255)]):
        p = tmp_path / f"f{i}.jpg"
        _solid(p, c)
        paths.append(p)
    changes = detect_scene_changes(paths)
    # Expect a change point at index 2 (transition from black to white).
    assert any(c.index == 2 for c in changes), f"got {changes}"


def test_no_change_for_identical_frames(tmp_path):
    paths = []
    for i in range(4):
        p = tmp_path / f"f{i}.jpg"
        _solid(p, (128, 128, 128))
        paths.append(p)
    assert detect_scene_changes(paths) == []


def _rec(i, ts, klass=FrameClass.OTHER):
    return FrameRecord(
        path=f"frames/f{i}.jpg",
        timestamp_seconds=ts,
        ocr_text="",
        ocr_confidence=0.0,
        frame_class=klass,
        class_confidence=0.9,
        cluster_id=None,
    )


def test_excludes_code_frames_from_selection(tmp_path):
    frames = [_rec(0, 0, FrameClass.CODE), _rec(1, 5, FrameClass.SLIDE_TEXT), _rec(2, 10)]
    res = select_frames(frames, change_points=[], max_frames=10, token_budget=None)
    assert all(s.frame_class != FrameClass.CODE for s in res.selected)


def test_coding_style_can_include_code_frames():
    frames = [_rec(0, 0, FrameClass.CODE), _rec(1, 5, FrameClass.SLIDE_TEXT), _rec(2, 10)]
    res = select_frames(frames, change_points=[], max_frames=2, token_budget=None, style="coding_agent")
    assert any(s.frame_class == FrameClass.CODE for s in res.selected)


def test_diy_style_prioritizes_visual_step_frames():
    frames = [
        _rec(0, 0, FrameClass.OTHER),
        _rec(1, 5, FrameClass.SLIDE_TEXT),
        _rec(2, 10, FrameClass.UI),
        _rec(3, 15, FrameClass.OTHER),
    ]
    res = select_frames(frames, change_points=[], max_frames=2, token_budget=None, style="diy_project")
    assert [s.frame_class for s in res.selected] == [FrameClass.SLIDE_TEXT, FrameClass.UI]


def test_diy_style_outputs_selected_frames_chronologically():
    frames = [
        _rec(0, 0, FrameClass.OTHER),
        _rec(1, 5, FrameClass.SLIDE_TEXT),
        _rec(2, 10, FrameClass.UI),
        _rec(3, 15, FrameClass.DIAGRAM),
        _rec(4, 20, FrameClass.OTHER),
    ]
    res = select_frames(frames, change_points=[], max_frames=4, token_budget=None, style="diy_project")
    assert [s.timestamp_seconds for s in res.selected] == sorted(s.timestamp_seconds for s in res.selected)


def test_uses_change_points_when_available():
    frames = [_rec(i, i * 1.0) for i in range(10)]
    cps = [ChangePoint(index=3, distance=20), ChangePoint(index=7, distance=20)]
    res = select_frames(frames, change_points=cps, max_frames=4, token_budget=None)
    indices = [s.timestamp_seconds for s in res.selected]
    assert 3.0 in indices
    assert 7.0 in indices
    assert all(r.reason for r in res.selected)


def test_falls_back_to_even_spacing_when_budget_unfilled():
    frames = [_rec(i, i * 1.0) for i in range(20)]
    res = select_frames(frames, change_points=[], max_frames=4, token_budget=None)
    assert len(res.selected) == 4
    assert all("even_spacing" in s.reason for s in res.selected)


def test_token_budget_caps_below_max_frames():
    frames = [_rec(i, i * 1.0) for i in range(20)]
    # token budget allows only 2 frames
    res = select_frames(frames, change_points=[], max_frames=10, token_budget=2 * 5000, est_image_tokens=5000)
    assert len(res.selected) == 2


def test_selected_frames_json_includes_reason(tmp_path):
    sel = SelectionResult(selected=[
        Selected(path="frames/f1.jpg", timestamp_seconds=1.0, frame_class=FrameClass.SLIDE_TEXT, reason="scene_change@t=00:01"),
    ])
    target = tmp_path / "selected_frames.json"
    write_selected_frames_json(target, sel)
    raw = json.loads(target.read_text())
    assert raw["selected"][0]["reason"].startswith("scene_change")


def test_even_spacing_fills_cap_when_change_points_collide_with_grid():
    """Regression: change-points that land on even-spacing grid positions must
    not cause the selector to under-fill cap. With 20 eligible frames, cap=8,
    and change-points at the exact grid {0, 5, 10, 15}, the selector should
    still return 8 frames (4 change-point + 4 fill)."""
    frames = [_rec(i, i * 1.0) for i in range(20)]
    cps = [ChangePoint(index=i, distance=20) for i in (0, 5, 10, 15)]
    res = select_frames(frames, change_points=cps, max_frames=8, token_budget=None)
    assert len(res.selected) == 8


def test_even_spacing_anchored_to_endpoints():
    """With cap=4 and 20 eligible frames, anchored spacing should include both
    the first (i=0) and last (i=19) frames, not bias toward the start."""
    frames = [_rec(i, i * 1.0) for i in range(20)]
    res = select_frames(frames, change_points=[], max_frames=4, token_budget=None)
    timestamps = sorted(s.timestamp_seconds for s in res.selected)
    assert len(timestamps) == 4
    assert timestamps[0] == 0.0
    assert timestamps[-1] == 19.0
