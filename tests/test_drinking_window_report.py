from pathlib import Path

from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.storage.bottle_status import update_bottle_status
from cellarmind.storage.drinking_window import report_drinking_windows

runner = CliRunner()


def test_drinking_window_report_classifies_bottles(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "Main,A1,2018,Overdue Wine,France,Rouge,Producer A,2020,2024,1,75\n"
        "Main,A2,2019,Ready Wine,France,Rouge,Producer B,2020,2030,1,75\n"
        "Main,A3,2020,Young Wine,France,Rouge,Producer C,2030,2035,1,75\n"
        "Main,A4,2021,Unknown Wine,France,Rouge,Producer D,,,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    report = report_drinking_windows(database_path, as_of_year=2026)

    assert report.summary.as_of_year == 2026
    assert report.summary.active_bottles == 4
    assert report.summary.overdue_bottles == 1
    assert report.summary.ready_bottles == 1
    assert report.summary.too_young_bottles == 1
    assert report.summary.unknown_window_bottles == 1

    assert [bottle.category for bottle in report.bottles] == [
        "overdue",
        "ready",
        "too_young",
        "unknown",
    ]


def test_drinking_window_report_handles_partial_windows(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "Main,A1,2018,Open Ended Ready,France,Rouge,Producer A,2020,,1,75\n"
        "Main,A2,2019,Only Until Ready,France,Rouge,Producer B,,2030,1,75\n"
        "Main,A3,2020,Only Until Overdue,France,Rouge,Producer C,,2024,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    report = report_drinking_windows(database_path, as_of_year=2026)

    assert report.summary.ready_bottles == 2
    assert report.summary.overdue_bottles == 1
    assert report.summary.too_young_bottles == 0
    assert report.summary.unknown_window_bottles == 0


def test_drinking_window_report_ignores_consumed_bottles(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "Main,A1,2018,Consumed Wine,France,Rouge,Producer A,2020,2024,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    update_bottle_status(
        database_path,
        bottle_id=1,
        new_status="consumed",
    )

    report = report_drinking_windows(database_path, as_of_year=2026)

    assert report.summary.active_bottles == 0
    assert report.bottles == ()


def test_drinking_window_report_respects_limit(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "Main,A1,2018,Overdue Wine 1,France,Rouge,Producer A,2020,2024,1,75\n"
        "Main,A2,2018,Overdue Wine 2,France,Rouge,Producer B,2020,2024,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    report = report_drinking_windows(
        database_path,
        as_of_year=2026,
        limit=1,
    )

    assert report.summary.active_bottles == 2
    assert report.summary.overdue_bottles == 2
    assert len(report.bottles) == 1


def test_report_drinking_window_command_outputs_report(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "Main,A1,2018,Overdue Wine,France,Rouge,Producer A,2020,2024,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    result = runner.invoke(
        app,
        [
            "report",
            "drinking-window",
            "--database",
            str(database_path),
            "--year",
            "2026",
        ],
    )

    assert result.exit_code == 0
    assert "Database:" in result.output
    assert "Drinking-window report" in result.output
    assert "Drinking-window bottles" in result.output
    assert "overdue" in result.output
    assert "Overdue Wine" in result.output
