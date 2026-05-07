"""Locks in the pre-merge behavior of download_transcript.py.

The legacy script must keep producing _formatted_transcript.txt and _clean_text.txt
exactly as before when no style argument is passed.
"""
from unittest.mock import patch
from pathlib import Path
import download_transcript as legacy


@patch("download_transcript.get_safe_title", return_value="Test_Video")
@patch("download_transcript.fetch_transcript_with_fallbacks")
def test_legacy_output_files(fetch_mock, _title_mock, tmp_path):
    fetch_mock.return_value = [(0.0, "hello"), (1.5, "world")]
    out = tmp_path / "Test_Video"
    out.mkdir()
    legacy.download_transcript("vid", str(out), title="Test_Video")
    formatted = out / "Test_Video_formatted_transcript.txt"
    clean = out / "Test_Video_clean_text.txt"
    assert formatted.read_text().splitlines() == ["0.0|hello", "1.5|world"]
    assert "hello" in clean.read_text()
    assert "world" in clean.read_text()
