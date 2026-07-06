from pathlib import Path

import pytest
from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.storage.bottle_movement import move_bottle
from cellarmind.storage.sqlite import connect_database

runner = CliRunner()


def test_move_bottle_closes_previous_location_and_creates_new_active_location(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,Nb,Fmt\n"
        "Main,A1,2018,Brut Réserve,Champagne,Blanc,Maison Test,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    result = move_bottle(
        database_path,
        bottle_id=1,
        cellar_name="Annex",
        location_name="B2",
    )

    assert result.moved is True
    assert result.previous_location is not None
    assert result.previous_location.cellar == "Main"
    assert result.previous_location.location == "A1"
    assert result.new_location.cellar == "Annex"
    assert result.new_location.location == "B2"

    with connect_database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                cellar.name AS cellar_name,
                location.name AS location_name,
                bottle_location_history.ended_at
            FROM bottle_location_history
            JOIN location
                ON location.id = bottle_location_history.location_id
            JOIN cellar
                ON cellar.id = location.cellar_id
            WHERE bottle_location_history.bottle_id = 1
            ORDER BY bottle_location_history.id
            """
        ).fetchall()

    assert len(rows) == 2

    assert rows[0]["cellar_name"] == "Main"
    assert rows[0]["location_name"] == "A1"
    assert rows[0]["ended_at"] is not None

    assert rows[1]["cellar_name"] == "Annex"
    assert rows[1]["location_name"] == "B2"
    assert rows[1]["ended_at"] is None


def test_move_bottle_to_same_location_is_noop(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,Nb,Fmt\n"
        "Main,A1,2018,Brut Réserve,Champagne,Blanc,Maison Test,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    result = move_bottle(
        database_path,
        bottle_id=1,
        cellar_name="Main",
        location_name="A1",
    )

    assert result.moved is False
    assert result.previous_location is not None
    assert result.previous_location.cellar == "Main"
    assert result.previous_location.location == "A1"

    with connect_database(database_path) as connection:
        history_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM bottle_location_history
            WHERE bottle_id = 1
            """
        ).fetchone()["count"]

        active_history_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM bottle_location_history
            WHERE bottle_id = 1
              AND ended_at IS NULL
            """
        ).fetchone()["count"]

    assert history_count == 1
    assert active_history_count == 1


def test_move_bottle_without_existing_location_creates_active_location(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,Nb,Fmt\n"
        "2018,Brut Réserve,Champagne,Blanc,Maison Test,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    result = move_bottle(
        database_path,
        bottle_id=1,
        cellar_name="Main",
        location_name="A1",
    )

    assert result.moved is True
    assert result.previous_location is None
    assert result.new_location.cellar == "Main"
    assert result.new_location.location == "A1"

    with connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT
                cellar.name AS cellar_name,
                location.name AS location_name,
                bottle_location_history.ended_at
            FROM bottle_location_history
            JOIN location
                ON location.id = bottle_location_history.location_id
            JOIN cellar
                ON cellar.id = location.cellar_id
            WHERE bottle_location_history.bottle_id = 1
            """
        ).fetchone()

    assert row["cellar_name"] == "Main"
    assert row["location_name"] == "A1"
    assert row["ended_at"] is None


def test_move_bottle_rejects_unknown_bottle(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,Nb,Fmt\n"
        "2018,Brut Réserve,Champagne,Blanc,Maison Test,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    with pytest.raises(ValueError, match="Bottle does not exist"):
        move_bottle(
            database_path,
            bottle_id=999,
            cellar_name="Main",
            location_name="A1",
        )


def test_bottle_move_command(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,Nb,Fmt\n"
        "Main,A1,2018,Brut Réserve,Champagne,Blanc,Maison Test,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    result = runner.invoke(
        app,
        [
            "bottle",
            "move",
            "1",
            "--database",
            str(database_path),
            "--cellar",
            "Annex",
            "--location",
            "B2",
        ],
    )

    assert result.exit_code == 0
    assert "Moved bottle 1" in result.output
    assert "Main" in result.output
    assert "A1" in result.output
    assert "Annex" in result.output
    assert "B2" in result.output
