from pathlib import Path

from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.storage.sqlite import (
    EXPECTED_TABLES,
    connect_database,
    initialize_database,
)


def test_initialize_database_creates_expected_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "cellarmind.sqlite"

    result = initialize_database(database_path)

    assert database_path.exists()
    assert result.schema_version == 1
    assert set(EXPECTED_TABLES).issubset(set(result.tables))


def test_database_enables_foreign_keys(tmp_path: Path) -> None:
    database_path = tmp_path / "cellarmind.sqlite"
    initialize_database(database_path)

    with connect_database(database_path) as connection:
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]

    assert foreign_keys == 1


def test_database_rejects_invalid_bottle_status(tmp_path: Path) -> None:
    database_path = tmp_path / "cellarmind.sqlite"
    initialize_database(database_path)

    with connect_database(database_path) as connection:
        wine_id = connection.execute(
            """
            INSERT INTO wine (producer, cuvee, vintage, appellation, color)
            VALUES ('Domaine Test', 'Cuvée Test', 2020, 'Test Appellation', 'Rouge')
            RETURNING id
            """
        ).fetchone()[0]

        wine_variant_id = connection.execute(
            """
            INSERT INTO wine_variant (wine_id, format)
            VALUES (?, '750ml')
            RETURNING id
            """,
            (wine_id,),
        ).fetchone()[0]

        try:
            connection.execute(
                """
                INSERT INTO bottle (wine_variant_id, status)
                VALUES (?, 'invalid_status')
                """,
                (wine_variant_id,),
            )
        except Exception as exc:
            assert "CHECK constraint failed" in str(exc)
        else:
            raise AssertionError("Expected invalid bottle status to be rejected")


def test_db_init_command_creates_database(tmp_path: Path) -> None:
    database_path = tmp_path / "cellarmind.sqlite"

    runner = CliRunner()
    result = runner.invoke(app, ["db", "init", "--path", str(database_path)])

    assert result.exit_code == 0
    assert database_path.exists()
    assert "Database initialized" in result.output
