"""yt-distill dispatcher: routes subcommands to module main(argv) functions."""
import pytest

from yt_distill import cli


def test_no_args_prints_usage_and_exits_nonzero(capsys):
    rc = cli.main([])
    assert rc != 0
    assert "usage" in capsys.readouterr().err.lower()


def test_unknown_command_exits_nonzero(capsys):
    rc = cli.main(["frobnicate"])
    assert rc != 0
    assert "frobnicate" in capsys.readouterr().err


def test_help_lists_all_subcommands(capsys):
    rc = cli.main(["--help"])
    out = capsys.readouterr().out
    assert rc == 0
    for cmd in ("extract", "refs", "distill", "review", "run", "enrich", "clean", "doctor"):
        assert cmd in out


@pytest.mark.parametrize(
    "cmd,target,forwarded",
    [
        ("extract", "yt_distill.pipeline.extract.main", ["x.mp4", "--force"]),
        ("refs", "yt_distill.stages.references.main", ["TitleDir"]),
        ("distill", "yt_distill.pipeline.distill.main", ["TitleDir", "coding_agent"]),
        ("review", "yt_distill.pipeline.review.main", ["TitleDir"]),
        ("run", "yt_distill.pipeline.run.main", ["x.mp4", "auto"]),
        ("enrich", "yt_distill.stages.visual.main", ["TitleDir", "coding_agent"]),
        ("clean", "yt_distill.clean.main", ["--apply"]),
    ],
)
def test_dispatch_forwards_argv_verbatim(cmd, target, forwarded, mocker):
    m = mocker.patch(target, return_value=0)
    rc = cli.main([cmd, *forwarded])
    assert rc == 0
    m.assert_called_once_with(forwarded)


def test_doctor_prepends_subcommand_for_models_main(mocker):
    m = mocker.patch("yt_distill.core.models.main", return_value=0)
    rc = cli.main(["doctor", "--profile", "gemini-3.5-flash"])
    assert rc == 0
    m.assert_called_once_with(["doctor", "--profile", "gemini-3.5-flash"])


def test_none_return_from_module_main_maps_to_zero(mocker):
    mocker.patch("yt_distill.clean.main", return_value=None)
    assert cli.main(["clean"]) == 0
