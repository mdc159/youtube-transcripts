import distill


def test_parse_args_minimal():
    ns = distill._parse_args(["My_Title", "coding_agent"])
    assert ns.title == "My_Title"
    assert ns.style == "coding_agent"
    assert ns.dry_run_payload is False


def test_parse_args_flags():
    ns = distill._parse_args(["X", "y", "--model", "gpt-4o", "--max-vision-frames", "8", "--dry-run-payload", "--force"])
    assert ns.model == "gpt-4o"
    assert ns.max_vision_frames == 8
    assert ns.dry_run_payload is True
    assert ns.force is True
