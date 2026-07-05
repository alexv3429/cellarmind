from pathlib import Path

from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.storage.sqlite import connect_database


def count_rows(database_path: Path, table: str) -> int:
    with connect_database(database_path) as connection:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_import_csv_creates_wine_variant_bottles_and_location(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Producteur,Cuvée,Millésime,Appellation,Couleur,Format,Quantité,Cave,Place\n"
        "Domaine Test,Cuvée Test,2020,Test Appellation,Rouge,50cl,2,Cave maison,Casier A\n",
        encoding="utf-8",
    )

    result = import_csv_to_database(input_path, database_path)

    assert result.source_rows == 1
    assert result.created_bottles == 2
    assert count_rows(database_path, "wine") == 1
    assert count_rows(database_path, "wine_variant") == 1
    assert count_rows(database_path, "bottle") == 2
    assert count_rows(database_path, "cellar") == 1
    assert count_rows(database_path, "location") == 1
    assert count_rows(database_path, "bottle_location_history") == 2
    assert count_rows(database_path, "import_session") == 1

    with connect_database(database_path) as connection:
        variant = connection.execute(
            """
            SELECT format
            FROM wine_variant
            """
        ).fetchone()

        session = connection.execute(
            """
            SELECT row_count, created_bottle_count
            FROM import_session
            """
        ).fetchone()

    assert variant["format"] == "500ml"
    assert session["row_count"] == 1
    assert session["created_bottle_count"] == 2


def test_import_csv_reuses_wine_and_variant_across_locations(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Producteur,Cuvée,Millésime,Appellation,Couleur,Format,Quantité,Cave,Place\n"
        "Domaine Test,Cuvée Test,2020,Test Appellation,Rouge,750ml,2,Cave maison,Casier A\n"
        "Domaine Test,Cuvée Test,2020,Test Appellation,Rouge,750ml,1,Cave externe,Caisse 12\n",
        encoding="utf-8",
    )

    result = import_csv_to_database(input_path, database_path)

    assert result.source_rows == 2
    assert result.created_bottles == 3
    assert count_rows(database_path, "wine") == 1
    assert count_rows(database_path, "wine_variant") == 1
    assert count_rows(database_path, "bottle") == 3
    assert count_rows(database_path, "cellar") == 2
    assert count_rows(database_path, "location") == 2
    assert count_rows(database_path, "bottle_location_history") == 3


def test_import_command_imports_csv_into_database(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Producteur,Cuvée,Millésime,Appellation,Couleur\n"
        "Domaine Test,Cuvée Test,2020,Test Appellation,Rouge\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["import", str(input_path), "--database", str(database_path)],
    )

    assert result.exit_code == 0
    assert "CSV imported" in result.output
    assert count_rows(database_path, "wine") == 1
    assert count_rows(database_path, "wine_variant") == 1
    assert count_rows(database_path, "bottle") == 1


def test_import_csv_canonicalizes_empty_vintage_to_nv(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Producteur,Cuvée,Millésime,Appellation,Couleur\n"
        "Maison Test,Brut Réserve,,Champagne,Blanc\n",
        encoding="utf-8",
    )

    result = import_csv_to_database(input_path, database_path)

    assert result.source_rows == 1
    assert result.created_bottles == 1

    with connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT vintage
            FROM wine
            WHERE producer = 'Maison Test'
            """
        ).fetchone()

    assert row["vintage"] == "NV"


def test_import_csv_canonicalizes_non_vintage_aliases_to_nv(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Producteur,Cuvée,Millésime,Appellation,Couleur\n"
        "Maison Test,Brut Réserve,NM,Champagne,Blanc\n"
        "Maison Test,Extra Brut,Non millésimé,Champagne,Blanc\n",
        encoding="utf-8",
    )

    result = import_csv_to_database(input_path, database_path)

    assert result.source_rows == 2
    assert result.created_bottles == 2

    with connect_database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT cuvee, vintage
            FROM wine
            ORDER BY cuvee
            """
        ).fetchall()

    assert [(row["cuvee"], row["vintage"]) for row in rows] == [
        ("Brut Réserve", "NV"),
        ("Extra Brut", "NV"),
    ]


def test_import_uses_default_cellar_without_mapping(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,Nb,Fmt\n"
        "A1,2018,Brut Réserve,Champagne,Blanc,Maison Test,2,75\n",
        encoding="utf-8",
    )

    result = import_csv_to_database(input_path, database_path)

    assert result.source_rows == 1
    assert result.created_bottles == 2

    with connect_database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT cellar.name AS cellar_name, location.name AS location_name
            FROM bottle_location_history
            JOIN location ON location.id = bottle_location_history.location_id
            JOIN cellar ON cellar.id = location.cellar_id
            ORDER BY bottle_location_history.bottle_id
            """
        ).fetchall()

    assert [(row["cellar_name"], row["location_name"]) for row in rows] == [
        ("default", "A1"),
        ("default", "A1"),
    ]


def test_import_maps_cellar_from_location_mapping_file(tmp_path: Path) -> None:
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

    result = import_csv_to_database(
        input_path,
        database_path,
        cellar_map_path=cellar_map_path,
    )

    assert result.source_rows == 1
    assert result.created_bottles == 1

    with connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT cellar.name AS cellar_name, location.name AS location_name
            FROM bottle_location_history
            JOIN location ON location.id = bottle_location_history.location_id
            JOIN cellar ON cellar.id = location.cellar_id
            """
        ).fetchone()

    assert row["cellar_name"] == "Large cellar"
    assert row["location_name"] == "G1A"


def test_import_without_cellar_or_location_does_not_create_location_history(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,Nb,Fmt\n"
        "2018,Brut Réserve,Champagne,Blanc,Maison Test,1,75\n",
        encoding="utf-8",
    )

    result = import_csv_to_database(input_path, database_path)

    assert result.created_bottles == 1

    with connect_database(database_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM bottle_location_history"
        ).fetchone()["count"]

    assert count == 0


def test_import_explicit_cellar_takes_priority_over_location_mapping(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"
    cellar_map_path = tmp_path / "cellar-map.csv"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,Nb,Fmt\n"
        "Explicit cellar,G1A,2018,Brut Réserve,Champagne,Blanc,Maison Test,1,150\n",
        encoding="utf-8",
    )

    cellar_map_path.write_text(
        "pattern,cellar\n^G[0-9][A-Z]+$,Mapped cellar\n",
        encoding="utf-8",
    )

    import_csv_to_database(
        input_path,
        database_path,
        cellar_map_path=cellar_map_path,
    )

    with connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT cellar.name AS cellar_name, location.name AS location_name
            FROM bottle_location_history
            JOIN location ON location.id = bottle_location_history.location_id
            JOIN cellar ON cellar.id = location.cellar_id
            """
        ).fetchone()

    assert row["cellar_name"] == "Explicit cellar"
    assert row["location_name"] == "G1A"
