from pathlib import Path

from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.storage.bottle_status import update_bottle_status
from cellarmind.storage.cellars import update_cellar_profile
from cellarmind.storage.placement import audit_placement

runner = CliRunner()


def test_placement_audit_reports_capacity_and_staging_issues(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "Aging,A1,2018,Brut Réserve,Champagne,Blanc,Maison Test,2020,2024,2,75\n"
        "Staging,S1,2021,Carton Wine,France,Rouge,Domaine Test,,,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    update_cellar_profile(
        database_path,
        name="Aging",
        purpose="aging",
        capacity_estimate=1,
        capacity_warning_threshold=1,
    )
    update_cellar_profile(
        database_path,
        name="Staging",
        purpose="staging",
    )

    report = audit_placement(database_path, as_of_year=2025)

    assert report.summary.active_bottles == 3
    assert report.summary.cellars_over_capacity == 1
    assert report.summary.bottles_in_staging_cellars == 1
    assert report.summary.ready_or_overdue_bottles_in_aging_cellars == 2

    assert [issue.issue_type for issue in report.issues] == [
        "overdue_in_aging_cellar",
        "overdue_in_aging_cellar",
        "bottle_in_staging_cellar",
    ]


def test_placement_audit_reports_too_young_in_drink_soon_cellar(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "DrinkSoon,D1,2022,Young Wine,Bourgogne,Rouge,Domaine Test,2030,2035,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    update_cellar_profile(
        database_path,
        name="DrinkSoon",
        purpose="drink_soon",
        capacity_estimate=10,
        capacity_warning_threshold=8,
    )

    report = audit_placement(database_path, as_of_year=2025)

    assert report.summary.too_young_bottles_in_drink_soon_cellars == 1
    assert len(report.issues) == 1
    assert report.issues[0].issue_type == "too_young_in_drink_soon_cellar"
    assert report.issues[0].severity == "high"


def test_placement_audit_reports_unknown_window_in_drink_soon_cellar(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,Nb,Fmt\n"
        "DrinkSoon,D1,2022,Unknown Window,Bourgogne,Rouge,Domaine Test,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    update_cellar_profile(
        database_path,
        name="DrinkSoon",
        purpose="drink_soon",
    )

    report = audit_placement(database_path, as_of_year=2025)

    assert report.summary.unknown_window_bottles_in_drink_soon_cellars == 1
    assert len(report.issues) == 1
    assert report.issues[0].issue_type == "unknown_window_in_drink_soon_cellar"


def test_placement_audit_reports_bottles_without_location(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,Nb,Fmt\n"
        "2018,No Location,France,Blanc,Maison Test,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    report = audit_placement(database_path, as_of_year=2025)

    assert report.summary.active_bottles == 1
    assert report.summary.bottles_without_location == 1
    assert len(report.issues) == 1
    assert report.issues[0].issue_type == "missing_location"
    assert report.issues[0].cellar is None
    assert report.issues[0].location is None


def test_placement_audit_ignores_consumed_bottles(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "Aging,A1,2018,Consumed Wine,France,Blanc,Maison Test,2020,2024,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    update_cellar_profile(
        database_path,
        name="Aging",
        purpose="aging",
    )

    update_bottle_status(
        database_path,
        bottle_id=1,
        new_status="consumed",
    )

    report = audit_placement(database_path, as_of_year=2025)

    assert report.summary.active_bottles == 0
    assert report.issues == ()


def test_report_placement_command_outputs_audit(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "Aging,A1,2018,Brut Réserve,Champagne,Blanc,Maison Test,2020,2024,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    update_cellar_profile(
        database_path,
        name="Aging",
        purpose="aging",
    )

    result = runner.invoke(
        app,
        [
            "report",
            "placement",
            "--database",
            str(database_path),
            "--year",
            "2025",
        ],
    )

    print(result.output)

    assert result.exit_code == 0
    assert "Database:" in result.output
    assert "Placement audit" in result.output
    assert "Cellar occupancy" in result.output
    assert "Placement issues" in result.output
    assert "overdue_in_aging_cellar" in result.output
