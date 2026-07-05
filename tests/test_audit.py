from pathlib import Path

from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.storage.audit import audit_database

runner = CliRunner()


def test_audit_database_summarizes_imported_cellar(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Prix,Année min,Année Max,Nb,Fmt\n"
        "Main,A1,2018,Brut Réserve,Champagne,Blanc,Maison Test,"
        "42.5,2024,2030,2,75\n"
        "Annex,B2,,Sans Millésime,France,Rouge,Domaine Test,"
        ",,,1,150\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    report = audit_database(database_path)

    assert report.summary.bottles == 3
    assert report.summary.wines == 2
    assert report.summary.wine_variants == 2
    assert report.summary.bottles_with_price == 2
    assert report.summary.bottles_without_price == 1
    assert report.summary.total_purchase_value == 85.0
    assert report.summary.variants_with_personal_drink_window == 1
    assert report.summary.variants_without_personal_drink_window == 1
    assert report.summary.non_vintage_wines == 1
    assert report.summary.bottles_without_location == 0

    assert [(row.label, row.bottle_count) for row in report.bottles_by_cellar] == [
        ("Main", 2),
        ("Annex", 1),
    ]

    assert [(row.label, row.bottle_count) for row in report.bottles_by_format] == [
        ("750ml", 2),
        ("1500ml", 1),
    ]


def test_audit_database_counts_bottles_without_location(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,Nb,Fmt\n"
        "2018,Brut Réserve,Champagne,Blanc,Maison Test,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    report = audit_database(database_path)

    assert report.summary.bottles == 1
    assert report.summary.bottles_without_location == 1
    assert report.bottles_by_cellar == ()


def test_db_audit_command_outputs_report(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Prix,Année min,Année Max,Nb,Fmt\n"
        "Main,A1,2018,Brut Réserve,Champagne,Blanc,Maison Test,"
        "42.5,2024,2030,2,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    result = runner.invoke(
        app,
        [
            "db",
            "audit",
            "--path",
            str(database_path),
        ],
    )

    assert result.exit_code == 0
    assert "Database:" in result.output
    assert "Cellar audit" in result.output
    assert "Total bottles" in result.output
    assert "Bottles by cellar" in result.output
    assert "Bottles by format" in result.output
    assert "Main" in result.output
    assert "750ml" in result.output
