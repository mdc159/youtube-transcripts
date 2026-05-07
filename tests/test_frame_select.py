from PIL import Image
from frame_select import detect_scene_changes, ChangePoint


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
