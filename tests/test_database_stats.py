from pathlib import Path

from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.storage.stats import get_database_stats


def test_get_database_stats_after_import(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Producteur,Cuvée,Millésime,Appellation,Couleur,Format,Quantité,Cave,Place\n"
        "Domaine Test,Cuvée Test,2020,Test Appellation,Rouge,50cl,2,Cave maison,Casier A\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    stats = get_database_stats(database_path)

    assert stats.import_sessions == 1
    assert stats.wines == 1
    assert stats.wine_variants == 1
    assert stats.bottles == 2
    assert stats.active_bottles == 2
    assert stats.cellars == 1
    assert stats.locations == 1
    assert stats.bottle_location_history_rows == 2
    assert stats.active_location_rows == 2
    assert stats.bottle_status_counts[0].status == "in_cellar"
    assert stats.bottle_status_counts[0].count == 2


def test_db_stats_command(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Producteur,Cuvée,Millésime,Appellation,Couleur\n"
        "Domaine Test,Cuvée Test,2020,Test Appellation,Rouge\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    runner = CliRunner()
    result = runner.invoke(app, ["db", "stats", "--path", str(database_path)])

    assert result.exit_code == 0
    assert "Database stats" in result.output
    assert "Wines: 1" in result.output
    assert "Bottles: 1" in result.output


def test_db_stats_command_fails_when_database_is_missing(tmp_path: Path) -> None:
    database_path = tmp_path / "missing.sqlite"

    runner = CliRunner()
    result = runner.invoke(app, ["db", "stats", "--path", str(database_path)])

    assert result.exit_code == 1
    assert "Database does not exist" in result.output
