from pathlib import Path

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


def test_import_command_accepts_cellar_map(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"
    cellar_map_path = tmp_path / "cellar-map.csv"

    input_path.write_text(
        "Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,Nb,Fmt\n"
        "G1A,2018,Brut Réserve,Champagne,Blanc,Maison Test,1,150\n",
        encoding="utf-8",
    )

    cellar_map_path.write_text(
        "pattern,cellar\n^G[0-9][A-Z]+$,Large cellar\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "import",
            str(input_path),
            "--database",
            str(database_path),
            "--cellar-map",
            str(cellar_map_path),
        ],
    )

    assert result.exit_code == 0
    assert "imported" in result.output
