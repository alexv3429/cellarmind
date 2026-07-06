from pathlib import Path

import pytest
from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.storage.bottle_addition import add_bottles
from cellarmind.storage.sqlite import connect_database, initialize_database

runner = CliRunner()


def test_add_bottles_creates_wine_variant_bottles_and_location(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "cellarmind.sqlite"
    initialize_database(database_path)

    result = add_bottles(
        database_path,
        producer="Maison Test",
        cuvee="Brut Réserve",
        vintage="2018",
        appellation="Champagne",
        color="Blanc",
        bottle_format="75",
        quantity=2,
        cellar_name="Main",
        location_name="A1",
        purchase_price=42.5,
        personal_drink_from_year=2024,
        personal_drink_until_year=2030,
    )

    assert result.created_bottles == 2
    assert len(result.bottle_ids) == 2

    with connect_database(database_path) as connection:
        wine_row = connection.execute(
            """
            SELECT producer, cuvee, vintage, appellation, color
            FROM wine
            """
        ).fetchone()

        variant_row = connection.execute(
            """
            SELECT format, personal_drink_from_year, personal_drink_until_year
            FROM wine_variant
            """
        ).fetchone()

        bottle_rows = connection.execute(
            """
            SELECT purchase_price, status
            FROM bottle
            ORDER BY id
            """
        ).fetchall()

        location_rows = connection.execute(
            """
            SELECT
                cellar.name AS cellar_name,
                location.name AS location_name,
                bottle_location_history.ended_at
            FROM bottle_location_history
            JOIN location ON location.id = bottle_location_history.location_id
            JOIN cellar ON cellar.id = location.cellar_id
            ORDER BY bottle_location_history.bottle_id
            """
        ).fetchall()

    assert dict(wine_row) == {
        "producer": "Maison Test",
        "cuvee": "Brut Réserve",
        "vintage": "2018",
        "appellation": "Champagne",
        "color": "Blanc",
    }

    assert variant_row["format"] == "750ml"
    assert variant_row["personal_drink_from_year"] == 2024
    assert variant_row["personal_drink_until_year"] == 2030

    assert [(row["purchase_price"], row["status"]) for row in bottle_rows] == [
        (42.5, "in_cellar"),
        (42.5, "in_cellar"),
    ]

    assert [
        (row["cellar_name"], row["location_name"], row["ended_at"]) for row in location_rows
    ] == [
        ("Main", "A1", None),
        ("Main", "A1", None),
    ]


def test_add_bottles_can_add_without_location(tmp_path: Path) -> None:
    database_path = tmp_path / "cellarmind.sqlite"
    initialize_database(database_path)

    result = add_bottles(
        database_path,
        producer="Maison Test",
        cuvee="Brut Réserve",
        vintage="2018",
        appellation="Champagne",
        color="Blanc",
        bottle_format="750ml",
        quantity=1,
    )

    assert result.created_bottles == 1

    with connect_database(database_path) as connection:
        location_history_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM bottle_location_history
            """
        ).fetchone()["count"]

    assert location_history_count == 0


def test_add_bottles_reuses_existing_wine_variant(tmp_path: Path) -> None:
    database_path = tmp_path / "cellarmind.sqlite"
    initialize_database(database_path)

    first_result = add_bottles(
        database_path,
        producer="Maison Test",
        cuvee="Brut Réserve",
        vintage="2018",
        appellation="Champagne",
        color="Blanc",
        bottle_format="750ml",
        quantity=1,
    )

    second_result = add_bottles(
        database_path,
        producer="Maison Test",
        cuvee="Brut Réserve",
        vintage="2018",
        appellation="Champagne",
        color="Blanc",
        bottle_format="75",
        quantity=2,
    )

    assert second_result.wine_id == first_result.wine_id
    assert second_result.wine_variant_id == first_result.wine_variant_id
    assert second_result.created_bottles == 2

    with connect_database(database_path) as connection:
        wine_count = connection.execute("SELECT COUNT(*) AS count FROM wine").fetchone()["count"]

        variant_count = connection.execute("SELECT COUNT(*) AS count FROM wine_variant").fetchone()[
            "count"
        ]

        bottle_count = connection.execute("SELECT COUNT(*) AS count FROM bottle").fetchone()[
            "count"
        ]

    assert wine_count == 1
    assert variant_count == 1
    assert bottle_count == 3


def test_add_bottles_rejects_partial_location(tmp_path: Path) -> None:
    database_path = tmp_path / "cellarmind.sqlite"
    initialize_database(database_path)

    with pytest.raises(ValueError, match="Cellar and location must be provided together"):
        add_bottles(
            database_path,
            producer="Maison Test",
            cuvee="Brut Réserve",
            vintage="2018",
            appellation="Champagne",
            color="Blanc",
            bottle_format="750ml",
            quantity=1,
            cellar_name="Main",
            location_name=None,
        )


def test_add_bottles_rejects_zero_quantity(tmp_path: Path) -> None:
    database_path = tmp_path / "cellarmind.sqlite"
    initialize_database(database_path)

    with pytest.raises(ValueError, match="Quantity must be greater than or equal to 1"):
        add_bottles(
            database_path,
            producer="Maison Test",
            cuvee="Brut Réserve",
            vintage="2018",
            appellation="Champagne",
            color="Blanc",
            bottle_format="750ml",
            quantity=0,
        )


def test_bottle_add_command(tmp_path: Path) -> None:
    database_path = tmp_path / "cellarmind.sqlite"
    initialize_database(database_path)

    result = runner.invoke(
        app,
        [
            "bottle",
            "add",
            "--database",
            str(database_path),
            "--producer",
            "Maison Test",
            "--cuvee",
            "Brut Réserve",
            "--vintage",
            "2018",
            "--appellation",
            "Champagne",
            "--color",
            "Blanc",
            "--format",
            "75",
            "--quantity",
            "2",
            "--cellar",
            "Main",
            "--location",
            "A1",
            "--purchase-price",
            "42.5",
            "--personal-drink-from-year",
            "2024",
            "--personal-drink-until-year",
            "2030",
        ],
    )

    assert result.exit_code == 0
    assert "Created bottles: 2" in result.output
    assert "Bottle IDs:" in result.output

    with connect_database(database_path) as connection:
        bottle_count = connection.execute("SELECT COUNT(*) AS count FROM bottle").fetchone()[
            "count"
        ]

    assert bottle_count == 2


def test_add_bottles_creates_manual_import_session(tmp_path: Path) -> None:
    database_path = tmp_path / "cellarmind.sqlite"
    initialize_database(database_path)

    add_bottles(
        database_path,
        producer="Maison Test",
        cuvee="Brut Réserve",
        vintage="2018",
        appellation="Champagne",
        color="Blanc",
        bottle_format="750ml",
        quantity=2,
    )

    with connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT
                source_file,
                source_hash,
                row_count,
                created_bottle_count,
                notes
            FROM import_session
            """
        ).fetchone()

    assert row["source_file"] == "manual"
    assert row["source_hash"] is None
    assert row["row_count"] == 1
    assert row["created_bottle_count"] == 2
    assert row["notes"] == "Manual bottle addition"
