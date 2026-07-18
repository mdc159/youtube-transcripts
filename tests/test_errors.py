"""Typed error hierarchy: catchable as RuntimeError, distinguishable by type."""
import pytest

from yt_distill.core import errors
from yt_distill import cli

ALL = [errors.TranscriptError, errors.ExtractError, errors.DistillError,
       errors.CitationError, errors.RefFollowError, errors.LLMError,
       errors.ModelConfigError]


@pytest.mark.parametrize("exc", ALL)
def test_subclasses_are_runtime_and_ytdistill_errors(exc):
    assert issubclass(exc, errors.YtDistillError)
    assert issubclass(exc, RuntimeError)  # legacy `except RuntimeError` still works


def test_cli_maps_ytdistill_error_to_exit_1(mocker, capsys):
    mocker.patch("yt_distill.clean.main",
                 side_effect=errors.DistillError("style 'bogus' not found"))
    rc = cli.main(["clean"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "style 'bogus' not found" in err
    assert "Traceback" not in err


def test_cli_lets_unexpected_exceptions_raise(mocker):
    mocker.patch("yt_distill.clean.main", side_effect=ValueError("bug"))
    with pytest.raises(ValueError):
        cli.main(["clean"])
