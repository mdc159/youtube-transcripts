"""Tests that --cookies-from-browser is propagated into the yt-dlp subtitle tier."""
from unittest.mock import patch, MagicMock

from transcript import _fetch_via_ytdlp, fetch_transcript


def _fake_run_no_subs():
    """Pretend yt-dlp ran but produced no .vtt — keeps the test hermetic."""
    result = MagicMock()
    result.returncode = 0
    result.stderr = ""
    result.stdout = ""
    return result


@patch("transcript.subprocess.run")
def test_ytdlp_includes_cookies_when_set(mock_run, tmp_path, monkeypatch):
    mock_run.return_value = _fake_run_no_subs()
    monkeypatch.chdir(tmp_path)

    try:
        _fetch_via_ytdlp("https://youtu.be/abc123XYZ_-", cookies_browser="chrome")
    except RuntimeError:
        pass

    assert mock_run.called, "yt-dlp subprocess should be invoked"
    argv = mock_run.call_args.args[0]
    assert "--cookies-from-browser" in argv, f"--cookies-from-browser missing from {argv}"
    idx = argv.index("--cookies-from-browser")
    assert argv[idx + 1] == "chrome"


@patch("transcript.subprocess.run")
def test_ytdlp_omits_cookies_when_none(mock_run, tmp_path, monkeypatch):
    mock_run.return_value = _fake_run_no_subs()
    monkeypatch.chdir(tmp_path)

    try:
        _fetch_via_ytdlp("https://youtu.be/abc123XYZ_-", cookies_browser=None)
    except RuntimeError:
        pass

    assert mock_run.called
    argv = mock_run.call_args.args[0]
    assert "--cookies-from-browser" not in argv


@patch("transcript._fetch_via_ytdlp")
@patch("transcript._fetch_via_pytube")
@patch("transcript._fetch_via_transcript_api")
def test_fetch_transcript_threads_cookies_to_ytdlp_tier(api, pyt, ytdlp):
    """fetch_transcript(cookies_browser=...) must reach _fetch_via_ytdlp."""
    api.side_effect = Exception("blocked")
    pyt.side_effect = Exception("blocked")
    ytdlp.return_value = [(0.0, "ok")]

    fetch_transcript("https://youtu.be/abc123XYZ_-", cookies_browser="chrome")

    assert ytdlp.called
    _, kwargs = ytdlp.call_args
    assert kwargs.get("cookies_browser") == "chrome", (
        f"cookies_browser='chrome' was not threaded into _fetch_via_ytdlp; got {kwargs}"
    )
