from pathlib import Path

import pytest
from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.storage.bottle_status import update_bottle_status
from cellarmind.storage.cellars import list_cellars, update_cellar_profile
from cellarmind.storage.sqlite import connect_database

runner = CliRunner()


def test_update_cellar_profile(tmp_path: Path) -> None:
    database_path = tmp_path / "cellarmind.sqlite"

    from cellarmind.storage.sqlite import initialize_database

    initialize_database(database_path)

    update_cellar_profile(
        database_path,
        name="Main",
        purpose="aging",
        capacity_estimate=350,
        capacity_warning_threshold=330,
        notes="Main aging cellar",
    )

    with connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT purpose, capacity_estimate, capacity_warning_threshold, notes
            FROM cellar
            WHERE name = 'Main'
            """
        ).fetchone()

    assert row["purpose"] == "aging"
    assert row["capacity_estimate"] == 350
    assert row["capacity_warning_threshold"] == 330
    assert row["notes"] == "Main aging cellar"


def test_list_cellars_counts_active_bottles(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,Nb,Fmt\n"
        "Main,A1,2018,Brut Réserve,Champagne,Blanc,Maison Test,2,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    update_cellar_profile(
        database_path,
        name="Main",
        purpose="drinking",
        capacity_estimate=3,
        capacity_warning_threshold=2,
    )

    cellars = list_cellars(database_path)

    assert len(cellars) == 1
    assert cellars[0].name == "Main"
    assert cellars[0].purpose == "drinking"
    assert cellars[0].active_bottles == 2
    assert cellars[0].capacity_estimate == 3
    assert cellars[0].occupancy_status == "near_capacity"


def test_list_cellars_ignores_consumed_bottles(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,Nb,Fmt\n"
        "Main,A1,2018,Brut Réserve,Champagne,Blanc,Maison Test,2,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    update_bottle_status(
        database_path,
        bottle_id=1,
        new_status="consumed",
    )

    cellars = list_cellars(database_path)

    assert cellars[0].active_bottles == 1


def test_update_cellar_profile_rejects_invalid_purpose(tmp_path: Path) -> None:
    from cellarmind.storage.sqlite import initialize_database

    database_path = tmp_path / "cellarmind.sqlite"
    initialize_database(database_path)

    with pytest.raises(ValueError, match="Invalid cellar purpose"):
        update_cellar_profile(
            database_path,
            name="Main",
            purpose="invalid",
        )


def test_cellar_list_command(tmp_path: Path) -> None:
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
            "cellar",
            "list",
            "--database",
            str(database_path),
        ],
    )

    assert result.exit_code == 0
    assert "Cellars" in result.output
    assert "Main" in result.output
    assert "mixed" in result.output


def test_cellar_update_command(tmp_path: Path) -> None:
    from cellarmind.storage.sqlite import initialize_database

    database_path = tmp_path / "cellarmind.sqlite"
    initialize_database(database_path)

    result = runner.invoke(
        app,
        [
            "cellar",
            "update",
            "Main",
            "--database",
            str(database_path),
            "--purpose",
            "aging",
            "--capacity-estimate",
            "350",
            "--capacity-warning-threshold",
            "330",
            "--notes",
            "Main aging cellar",
        ],
    )

    assert result.exit_code == 0
    assert "Updated cellar: Main" in result.output

    cellars = list_cellars(database_path)

    assert cellars[0].name == "Main"
    assert cellars[0].purpose == "aging"
    assert cellars[0].capacity_estimate == 350
    assert cellars[0].capacity_warning_threshold == 330
    assert cellars[0].notes == "Main aging cellar"
