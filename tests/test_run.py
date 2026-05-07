import pytest

import run


def test_help_returns_zero(capsys):
    with pytest.raises(SystemExit) as ei:
        run.main(["--help"])
    assert ei.value.code == 0
    out = capsys.readouterr().out
    assert "extract" in out.lower() or "distill" in out.lower() or "source" in out.lower()
