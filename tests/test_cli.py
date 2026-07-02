from typer.testing import CliRunner

from cellarmind.cli import app

runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_inspect_sample_csv() -> None:
    result = runner.invoke(app, ["inspect", "examples/cave.sample.csv"])
    assert result.exit_code == 0
    assert "Rows" in result.stdout
    assert "2" in result.stdout
