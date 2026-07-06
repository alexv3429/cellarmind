from pathlib import Path

from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.storage.bottle_status import update_bottle_status
from cellarmind.storage.cellars import update_cellar_profile
from cellarmind.storage.drinking_recommendation import recommend_drinking

runner = CliRunner()


def test_drinking_recommendations_classify_active_bottles(
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

    update_cellar_profile(
        database_path,
        name="Main",
        purpose="drink_soon",
    )

    report = recommend_drinking(database_path, as_of_year=2026)

    assert report.summary.as_of_year == 2026
    assert report.summary.active_bottles == 4
    assert report.summary.drink_now_recommendations == 2
    assert report.summary.consider_drinking_recommendations == 0
    assert report.summary.hold_recommendations == 1
    assert report.summary.review_recommendations == 1

    by_cuvee = {recommendation.cuvee: recommendation for recommendation in report.recommendations}

    assert by_cuvee["Overdue Wine"].action == "drink_now"
    assert by_cuvee["Overdue Wine"].priority == "high"
    assert by_cuvee["Overdue Wine"].drinking_window_category == "overdue"

    assert by_cuvee["Ready Wine"].action == "drink_now"
    assert by_cuvee["Ready Wine"].priority == "medium"
    assert by_cuvee["Ready Wine"].drinking_window_category == "ready"

    assert by_cuvee["Young Wine"].action == "hold"
    assert by_cuvee["Young Wine"].priority == "low"
    assert by_cuvee["Young Wine"].drinking_window_category == "too_young"

    assert by_cuvee["Unknown Wine"].action == "review"
    assert by_cuvee["Unknown Wine"].priority == "medium"
    assert by_cuvee["Unknown Wine"].drinking_window_category == "unknown"


def test_drinking_recommendations_prioritize_opened_bottles(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "Main,A1,2020,Opened Young Wine,France,Rouge,Producer A,2030,2035,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    update_bottle_status(
        database_path,
        bottle_id=1,
        new_status="opened",
    )

    report = recommend_drinking(database_path, as_of_year=2026)

    assert report.summary.active_bottles == 1
    assert report.summary.drink_now_recommendations == 1

    recommendation = report.recommendations[0]

    assert recommendation.action == "drink_now"
    assert recommendation.priority == "high"
    assert recommendation.status == "opened"
    assert recommendation.drinking_window_category == "too_young"
    assert "opened" in recommendation.reason


def test_drinking_recommendations_review_bottle_without_location(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "2018,No Location Wine,France,Blanc,Producer A,2020,2030,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    report = recommend_drinking(database_path, as_of_year=2026)

    assert report.summary.active_bottles == 1
    assert report.summary.review_recommendations == 1

    recommendation = report.recommendations[0]

    assert recommendation.action == "review"
    assert recommendation.priority == "high"
    assert recommendation.cellar is None
    assert recommendation.location is None
    assert "no active location" in recommendation.reason


def test_drinking_recommendations_consider_ready_bottle_in_aging_cellar(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "Aging,A1,2018,Ready Aging Wine,France,Rouge,Producer A,2020,2030,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    update_cellar_profile(
        database_path,
        name="Aging",
        purpose="aging",
    )

    report = recommend_drinking(database_path, as_of_year=2026)

    assert report.summary.active_bottles == 1
    assert report.summary.consider_drinking_recommendations == 1

    recommendation = report.recommendations[0]

    assert recommendation.action == "consider_drinking"
    assert recommendation.priority == "medium"
    assert recommendation.drinking_window_category == "ready"
    assert recommendation.cellar == "Aging"
    assert recommendation.cellar_purpose == "aging"


def test_drinking_recommendations_ignore_consumed_bottles(
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

    report = recommend_drinking(database_path, as_of_year=2026)

    assert report.summary.active_bottles == 0
    assert report.recommendations == ()


def test_drinking_recommendations_respect_limit(
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

    report = recommend_drinking(
        database_path,
        as_of_year=2026,
        limit=1,
    )

    assert report.summary.active_bottles == 2
    assert report.summary.drink_now_recommendations == 2
    assert len(report.recommendations) == 1


def test_recommend_drinking_command_outputs_recommendations(
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
            "recommend",
            "drinking",
            "--database",
            str(database_path),
            "--year",
            "2026",
        ],
    )

    assert result.exit_code == 0
    assert "Database:" in result.output
    assert "Drinking recommendations summary" in result.output
    assert "Drinking recommendations" in result.output
    assert "drink_now" in result.output
    assert "Overdue Wine" in result.output
