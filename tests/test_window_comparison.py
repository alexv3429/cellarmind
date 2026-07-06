from pathlib import Path

from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.storage.reference_windows import add_reference_window
from cellarmind.storage.sqlite import connect_database
from cellarmind.storage.window_comparison import compare_drinking_windows

runner = CliRunner()


def test_window_comparison_reports_aligned_window(tmp_path: Path) -> None:
    database_path = _create_database(
        tmp_path,
        cuvee="Aligned Wine",
        personal_from=2024,
        personal_until=2030,
    )
    wine_id = _get_wine_id(database_path, cuvee="Aligned Wine")

    add_reference_window(
        database_path,
        wine_id=wine_id,
        source_name="Reference",
        drink_from_year=2025,
        drink_until_year=2031,
    )

    report = compare_drinking_windows(
        database_path,
        tolerance_years=2,
    )

    assert report.summary.active_variants == 1
    assert report.summary.aligned == 1
    assert report.rows[0].category == "aligned"
    assert report.rows[0].severity == "info"


def test_window_comparison_reports_missing_personal_window(
    tmp_path: Path,
) -> None:
    database_path = _create_database(
        tmp_path,
        cuvee="Missing Personal Wine",
        personal_from=None,
        personal_until=None,
    )
    wine_id = _get_wine_id(database_path, cuvee="Missing Personal Wine")

    add_reference_window(
        database_path,
        wine_id=wine_id,
        source_name="Reference",
        drink_from_year=2025,
        drink_until_year=2031,
    )

    report = compare_drinking_windows(database_path)

    assert report.summary.missing_personal_windows == 1
    assert report.rows[0].category == "missing_personal_window"
    assert report.rows[0].severity == "high"


def test_window_comparison_reports_missing_reference_window(
    tmp_path: Path,
) -> None:
    database_path = _create_database(
        tmp_path,
        cuvee="Missing Reference Wine",
        personal_from=2024,
        personal_until=2030,
    )

    report = compare_drinking_windows(database_path)

    assert report.summary.missing_reference_windows == 1
    assert report.rows[0].category == "missing_reference_window"
    assert report.rows[0].severity == "low"


def test_window_comparison_reports_both_windows_missing(
    tmp_path: Path,
) -> None:
    database_path = _create_database(
        tmp_path,
        cuvee="Both Missing Wine",
        personal_from=None,
        personal_until=None,
    )

    report = compare_drinking_windows(database_path)

    assert report.summary.missing_personal_and_reference == 1
    assert report.rows[0].category == "missing_personal_and_reference"
    assert report.rows[0].severity == "medium"


def test_window_comparison_reports_personal_earlier_than_reference(
    tmp_path: Path,
) -> None:
    database_path = _create_database(
        tmp_path,
        cuvee="Earlier Wine",
        personal_from=2020,
        personal_until=2024,
    )
    wine_id = _get_wine_id(database_path, cuvee="Earlier Wine")

    add_reference_window(
        database_path,
        wine_id=wine_id,
        source_name="Reference",
        drink_from_year=2028,
        drink_until_year=2035,
    )

    report = compare_drinking_windows(database_path)

    assert report.summary.personal_earlier_than_reference == 1
    assert report.rows[0].category == "personal_earlier_than_reference"
    assert report.rows[0].severity == "high"


def test_window_comparison_reports_personal_later_than_reference(
    tmp_path: Path,
) -> None:
    database_path = _create_database(
        tmp_path,
        cuvee="Later Wine",
        personal_from=2035,
        personal_until=2040,
    )
    wine_id = _get_wine_id(database_path, cuvee="Later Wine")

    add_reference_window(
        database_path,
        wine_id=wine_id,
        source_name="Reference",
        drink_from_year=2020,
        drink_until_year=2030,
    )

    report = compare_drinking_windows(database_path)

    assert report.summary.personal_later_than_reference == 1
    assert report.rows[0].category == "personal_later_than_reference"
    assert report.rows[0].severity == "high"


def test_window_comparison_reports_large_disagreement(
    tmp_path: Path,
) -> None:
    database_path = _create_database(
        tmp_path,
        cuvee="Disagreement Wine",
        personal_from=2020,
        personal_until=2030,
    )
    wine_id = _get_wine_id(database_path, cuvee="Disagreement Wine")

    add_reference_window(
        database_path,
        wine_id=wine_id,
        source_name="Reference",
        drink_from_year=2023,
        drink_until_year=2035,
    )

    report = compare_drinking_windows(
        database_path,
        tolerance_years=2,
    )

    assert report.summary.large_disagreements == 1
    assert report.rows[0].category == "large_disagreement"
    assert report.rows[0].severity == "medium"


def test_window_comparison_reports_partial_comparison(
    tmp_path: Path,
) -> None:
    database_path = _create_database(
        tmp_path,
        cuvee="Partial Wine",
        personal_from=2024,
        personal_until=None,
    )
    wine_id = _get_wine_id(database_path, cuvee="Partial Wine")

    add_reference_window(
        database_path,
        wine_id=wine_id,
        source_name="Reference",
        drink_from_year=2024,
    )

    report = compare_drinking_windows(database_path)

    assert report.summary.partial_comparisons == 1
    assert report.rows[0].category == "partial_comparison"
    assert report.rows[0].severity == "low"


def test_window_comparison_prefers_high_confidence_reference(
    tmp_path: Path,
) -> None:
    database_path = _create_database(
        tmp_path,
        cuvee="Confidence Wine",
        personal_from=2024,
        personal_until=2030,
    )
    wine_id = _get_wine_id(database_path, cuvee="Confidence Wine")

    add_reference_window(
        database_path,
        wine_id=wine_id,
        source_name="Low Reference",
        drink_from_year=2024,
        drink_until_year=2030,
        confidence="low",
    )
    add_reference_window(
        database_path,
        wine_id=wine_id,
        source_name="High Reference",
        drink_from_year=2035,
        drink_until_year=2040,
        confidence="high",
    )

    report = compare_drinking_windows(database_path)

    assert report.rows[0].reference_source_name == "High Reference"
    assert report.rows[0].category == "personal_earlier_than_reference"


def test_window_comparison_respects_limit(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "Main,A1,2018,Wine 1,France,Rouge,Producer A,2020,2030,1,75\n"
        "Main,A2,2018,Wine 2,France,Rouge,Producer B,2020,2030,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    report = compare_drinking_windows(
        database_path,
        limit=1,
    )

    assert report.summary.active_variants == 2
    assert len(report.rows) == 1


def test_window_comparison_command_outputs_report(tmp_path: Path) -> None:
    database_path = _create_database(
        tmp_path,
        cuvee="CLI Wine",
        personal_from=2020,
        personal_until=2030,
    )
    wine_id = _get_wine_id(database_path, cuvee="CLI Wine")

    add_reference_window(
        database_path,
        wine_id=wine_id,
        source_name="Reference",
        drink_from_year=2023,
        drink_until_year=2035,
    )

    result = runner.invoke(
        app,
        [
            "report",
            "window-comparison",
            "--database",
            str(database_path),
            "--tolerance-years",
            "2",
        ],
    )

    assert result.exit_code == 0
    assert "Database:" in result.output
    assert "Window comparison summary" in result.output
    assert "Window comparisons" in result.output
    assert "large_disagreement" in result.output
    assert "CLI Wine" in result.output


def _create_database(
    tmp_path: Path,
    *,
    cuvee: str,
    personal_from: int | None,
    personal_until: int | None,
) -> Path:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    from_value = "" if personal_from is None else str(personal_from)
    until_value = "" if personal_until is None else str(personal_until)

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        f"Main,A1,2018,{cuvee},France,Rouge,Producer A,"
        f"{from_value},{until_value},1,75\n",
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
