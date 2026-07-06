from pathlib import Path

import pytest
from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.storage.reference_windows import (
    add_reference_window,
    list_reference_windows,
)
from cellarmind.storage.sqlite import connect_database

runner = CliRunner()


def test_add_reference_window_for_existing_wine(tmp_path: Path) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path, cuvee="Reference Wine")

    window = add_reference_window(
        database_path,
        wine_id=wine_id,
        source_name="Manual reference",
        source_url="https://example.com/wine",
        drink_from_year=2024,
        drink_until_year=2032,
        confidence="high",
        notes="Producer note.",
    )

    assert window.id == 1
    assert window.wine_id == wine_id
    assert window.source_name == "Manual reference"
    assert window.source_url == "https://example.com/wine"
    assert window.drink_from_year == 2024
    assert window.drink_until_year == 2032
    assert window.confidence == "high"
    assert window.notes == "Producer note."


def test_list_reference_windows_by_wine_id(tmp_path: Path) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path, cuvee="Reference Wine")

    add_reference_window(
        database_path,
        wine_id=wine_id,
        source_name="Reference A",
        drink_from_year=2024,
        drink_until_year=2030,
    )
    add_reference_window(
        database_path,
        wine_id=wine_id,
        source_name="Reference B",
        drink_from_year=2025,
        drink_until_year=2032,
        confidence="low",
    )

    windows = list_reference_windows(database_path, wine_id=wine_id)

    assert len(windows) == 2
    assert {window.source_name for window in windows} == {
        "Reference A",
        "Reference B",
    }


def test_list_reference_windows_without_filter(tmp_path: Path) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path, cuvee="Reference Wine")

    add_reference_window(
        database_path,
        wine_id=wine_id,
        source_name="Reference A",
        drink_from_year=2024,
    )

    windows = list_reference_windows(database_path)

    assert len(windows) == 1
    assert windows[0].source_name == "Reference A"


def test_add_reference_window_rejects_missing_database(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        add_reference_window(
            tmp_path / "missing.sqlite",
            wine_id=1,
            source_name="Manual reference",
            drink_from_year=2024,
        )


def test_add_reference_window_rejects_unknown_wine_id(tmp_path: Path) -> None:
    database_path = _create_database_with_wine(tmp_path)

    with pytest.raises(ValueError, match="Unknown wine id"):
        add_reference_window(
            database_path,
            wine_id=999,
            source_name="Manual reference",
            drink_from_year=2024,
        )


def test_add_reference_window_rejects_blank_source_name(tmp_path: Path) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path, cuvee="Reference Wine")

    with pytest.raises(ValueError, match="source_name must not be blank"):
        add_reference_window(
            database_path,
            wine_id=wine_id,
            source_name=" ",
            drink_from_year=2024,
        )


def test_add_reference_window_rejects_invalid_confidence(tmp_path: Path) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path, cuvee="Reference Wine")

    with pytest.raises(ValueError, match="Confidence"):
        add_reference_window(
            database_path,
            wine_id=wine_id,
            source_name="Manual reference",
            drink_from_year=2024,
            confidence="certain",
        )


def test_add_reference_window_rejects_empty_window(tmp_path: Path) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path, cuvee="Reference Wine")

    with pytest.raises(ValueError, match="At least one"):
        add_reference_window(
            database_path,
            wine_id=wine_id,
            source_name="Manual reference",
        )


def test_add_reference_window_rejects_invalid_year_order(tmp_path: Path) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path, cuvee="Reference Wine")

    with pytest.raises(ValueError, match="less than or equal"):
        add_reference_window(
            database_path,
            wine_id=wine_id,
            source_name="Manual reference",
            drink_from_year=2030,
            drink_until_year=2024,
        )


def test_reference_window_add_command(tmp_path: Path) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path, cuvee="Reference Wine")

    result = runner.invoke(
        app,
        [
            "reference-window",
            "add",
            "--database",
            str(database_path),
            "--wine-id",
            str(wine_id),
            "--source-name",
            "Manual reference",
            "--drink-from-year",
            "2024",
            "--drink-until-year",
            "2032",
            "--confidence",
            "medium",
            "--notes",
            "Producer note.",
        ],
    )

    assert result.exit_code == 0
    assert "Database:" in result.output
    assert "Created reference drinking window" in result.output


def test_reference_window_list_command(tmp_path: Path) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path, cuvee="Reference Wine")

    add_reference_window(
        database_path,
        wine_id=wine_id,
        source_name="Manual reference",
        drink_from_year=2024,
        drink_until_year=2032,
    )

    result = runner.invoke(
        app,
        [
            "reference-window",
            "list",
            "--database",
            str(database_path),
            "--wine-id",
            str(wine_id),
        ],
    )

    assert result.exit_code == 0
    assert "Database:" in result.output
    assert "Reference drinking windows" in result.output
    assert "Manual reference" in result.output


def _create_database_with_wine(tmp_path: Path) -> Path:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "Main,A1,2018,Reference Wine,France,Rouge,Producer A,2020,2030,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    return database_path


def _get_wine_id(database_path: Path, *, cuvee: str) -> int:
    with connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT id
            FROM wine
            WHERE cuvee = ?
            """,
            (cuvee,),
        ).fetchone()

    assert row is not None

    return int(row["id"])
