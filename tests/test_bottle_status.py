from pathlib import Path

import pytest
from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.storage.bottle_status import update_bottle_status
from cellarmind.storage.sqlite import connect_database

runner = CliRunner()


def test_mark_bottle_opened_keeps_active_location(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,Nb,Fmt\n"
        "Main,A1,2018,Brut Réserve,Champagne,Blanc,Maison Test,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    result = update_bottle_status(
        database_path,
        bottle_id=1,
        new_status="opened",
    )

    assert result.previous_status == "in_cellar"
    assert result.new_status == "opened"
    assert result.changed is True
    assert result.closed_location_history_rows == 0

    with connect_database(database_path) as connection:
        bottle_row = connection.execute(
            """
            SELECT status
            FROM bottle
            WHERE id = 1
            """
        ).fetchone()

        active_location_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM bottle_location_history
            WHERE bottle_id = 1
              AND ended_at IS NULL
            """
        ).fetchone()["count"]

    assert bottle_row["status"] == "opened"
    assert active_location_count == 1


def test_mark_bottle_consumed_closes_active_location(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,Nb,Fmt\n"
        "Main,A1,2018,Brut Réserve,Champagne,Blanc,Maison Test,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    result = update_bottle_status(
        database_path,
        bottle_id=1,
        new_status="consumed",
    )

    assert result.previous_status == "in_cellar"
    assert result.new_status == "consumed"
    assert result.changed is True
    assert result.closed_location_history_rows == 1

    with connect_database(database_path) as connection:
        bottle_row = connection.execute(
            """
            SELECT status
            FROM bottle
            WHERE id = 1
            """
        ).fetchone()

        history_row = connection.execute(
            """
            SELECT ended_at
            FROM bottle_location_history
            WHERE bottle_id = 1
            """
        ).fetchone()

        active_location_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM bottle_location_history
            WHERE bottle_id = 1
              AND ended_at IS NULL
            """
        ).fetchone()["count"]

    assert bottle_row["status"] == "consumed"
    assert history_row["ended_at"] is not None
    assert active_location_count == 0


def test_mark_bottle_gifted_without_location_updates_status(
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

    result = update_bottle_status(
        database_path,
        bottle_id=1,
        new_status="gifted",
    )

    assert result.previous_status == "in_cellar"
    assert result.new_status == "gifted"
    assert result.changed is True
    assert result.closed_location_history_rows == 0

    with connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT status
            FROM bottle
            WHERE id = 1
            """
        ).fetchone()

    assert row["status"] == "gifted"


def test_mark_bottle_status_is_idempotent(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,Nb,Fmt\n"
        "Main,A1,2018,Brut Réserve,Champagne,Blanc,Maison Test,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    first_result = update_bottle_status(
        database_path,
        bottle_id=1,
        new_status="consumed",
    )
    second_result = update_bottle_status(
        database_path,
        bottle_id=1,
        new_status="consumed",
    )

    assert first_result.changed is True
    assert first_result.closed_location_history_rows == 1

    assert second_result.changed is False
    assert second_result.closed_location_history_rows == 0

    with connect_database(database_path) as connection:
        active_location_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM bottle_location_history
            WHERE bottle_id = 1
              AND ended_at IS NULL
            """
        ).fetchone()["count"]

    assert active_location_count == 0


def test_mark_bottle_status_rejects_unknown_bottle(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,Nb,Fmt\n"
        "2018,Brut Réserve,Champagne,Blanc,Maison Test,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    with pytest.raises(ValueError, match="Bottle does not exist"):
        update_bottle_status(
            database_path,
            bottle_id=999,
            new_status="consumed",
        )


def test_mark_bottle_status_rejects_invalid_status(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,Nb,Fmt\n"
        "2018,Brut Réserve,Champagne,Blanc,Maison Test,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    with pytest.raises(ValueError, match="Invalid bottle status"):
        update_bottle_status(
            database_path,
            bottle_id=1,
            new_status="broken",
        )


def test_bottle_mark_consumed_command(tmp_path: Path) -> None:
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
            "mark-consumed",
            "1",
            "--database",
            str(database_path),
        ],
    )

    assert result.exit_code == 0
    assert "Bottle 1 status changed from in_cellar to consumed." in result.output
    assert "Closed active location." in result.output

    with connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT status
            FROM bottle
            WHERE id = 1
            """
        ).fetchone()

    assert row["status"] == "consumed"
