from pathlib import Path

from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.storage.inventory import list_bottles


def test_list_bottles_returns_imported_physical_bottles(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Producteur,Cuvée,Millésime,Appellation,Couleur,Format,Quantité,Cave,Place\n"
        "Domaine Test,Cuvée Test,2020,Test Appellation,Rouge,50cl,2,Cave maison,Casier A\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    bottles = list_bottles(database_path)

    assert len(bottles) == 2
    assert bottles[0].producer == "Domaine Test"
    assert bottles[0].cuvee == "Cuvée Test"
    assert bottles[0].vintage == 2020
    assert bottles[0].format == "500ml"
    assert bottles[0].cellar == "Cave maison"
    assert bottles[0].location == "Casier A"


def test_list_bottles_respects_limit(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Producteur,Cuvée,Millésime,Appellation,Couleur,Quantité\n"
        "Domaine Test,Cuvée Test,2020,Test Appellation,Rouge,3\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    bottles = list_bottles(database_path, limit=2)

    assert len(bottles) == 2


def test_list_bottles_command(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Producteur,Cuvée,Millésime,Appellation,Couleur\n"
        "Domaine Test,Cuvée Test,2020,Test Appellation,Rouge\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["list", "bottles", "--database", str(database_path)],
    )

    assert result.exit_code == 0
    assert "Bottles" in result.output
    assert "Domaine Test" in result.output
    assert "Cuvée Test" in result.output


def test_list_bottles_command_fails_when_database_is_missing(tmp_path: Path) -> None:
    database_path = tmp_path / "missing.sqlite"

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["list", "bottles", "--database", str(database_path)],
    )

    assert result.exit_code == 1
    assert "Database does not exist" in result.output
