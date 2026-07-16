from yt_distill.stages.frame_ocr import FrameClass, FrameRecord
from yt_distill.core.video_profile import build_video_profile, format_route_proposal


def _rec(idx: int, text: str, klass: FrameClass) -> FrameRecord:
    return FrameRecord(
        path=f"frames/frame_{idx:03d}_t-00-{idx:02d}.jpg",
        timestamp_seconds=float(idx),
        ocr_text=text,
        ocr_confidence=0.9,
        frame_class=klass,
        class_confidence=0.9,
        cluster_id="c0" if klass == FrameClass.CODE else None,
    )


def test_profiles_coding_video_from_code_and_commands():
    profile = build_video_profile(
        title="Build an AI coding agent with FastAPI",
        transcript_text=(
            "We will install the package, create src/app.py, run uv run pytest, "
            "define a function, and call the API endpoint."
        ),
        frames=[
            _rec(1, "def handler(request):\n    return client.chat.completions.create()", FrameClass.CODE),
            _rec(2, "uv run python app.py", FrameClass.CODE),
        ],
    )

    assert profile.recommended_style == "coding_agent"
    assert profile.confidence >= 0.7
    assert profile.needs_confirmation is False
    assert profile.scores["coding_agent"] > profile.scores["knowledge_base"]


def test_profiles_diy_video_from_materials_measurements_and_tools():
    profile = build_video_profile(
        title="Build a workbench with plywood and pocket screws",
        transcript_text=(
            "Cut two 2x4 boards to 36 inches, drill pilot holes, sand the plywood, "
            "wear safety glasses, and attach the hinges with screws."
        ),
        frames=[
            _rec(1, "Materials: plywood, screws, hinges", FrameClass.SLIDE_TEXT),
            _rec(2, "Step 3: clamp the board before drilling", FrameClass.SLIDE_TEXT),
        ],
    )

    assert profile.recommended_style == "diy_project"
    assert profile.confidence >= 0.7
    assert profile.signals["diy_project"]["keyword_hits"] >= 3


def test_profiles_knowledge_base_video_when_conceptual():
    profile = build_video_profile(
        title="Architecture patterns for agent systems",
        transcript_text=(
            "This talk explains the mental model, tradeoffs, design principles, "
            "and conceptual framework behind agent orchestration."
        ),
        frames=[
            _rec(1, "Architecture Overview", FrameClass.DIAGRAM),
            _rec(2, "Tradeoffs and Principles", FrameClass.SLIDE_TEXT),
        ],
    )

    assert profile.recommended_style == "knowledge_base"
    assert profile.confidence >= 0.55
    assert profile.needs_confirmation is False


def test_profiles_ambiguous_video_requires_confirmation():
    profile = build_video_profile(
        title="AI hardware project overview",
        transcript_text=(
            "We discuss the design, then wire the sensor, install the SDK, "
            "and run a command to test the prototype."
        ),
        frames=[
            _rec(1, "npm install sensor-sdk", FrameClass.CODE),
            _rec(2, "Materials: sensor, jumper wires", FrameClass.SLIDE_TEXT),
        ],
    )

    assert profile.needs_confirmation is True
    assert profile.confidence < 0.7
    assert profile.alternatives


def test_profiles_zero_signal_video_defaults_to_knowledge_base_with_confirmation():
    profile = build_video_profile(
        title="test_video",
        transcript_text="",
        frames=[],
    )

    assert profile.recommended_style == "knowledge_base"
    assert profile.confidence == 0.0
    assert profile.needs_confirmation is True


def test_format_route_proposal_includes_reasoning_for_user():
    profile = build_video_profile(
        title="AI hardware project overview",
        transcript_text="Install the SDK, wire the sensor, and explain the system design.",
        frames=[
            _rec(1, "npm install sensor-sdk", FrameClass.CODE),
            _rec(2, "Materials: sensor, jumper wires", FrameClass.SLIDE_TEXT),
        ],
    )

    proposal = format_route_proposal(profile)

    assert profile.recommended_style in proposal
    assert "Reason" in proposal
    assert "Alternative" in proposal
