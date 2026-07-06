from pathlib import Path

from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.storage.cellars import update_cellar_profile
from cellarmind.storage.transfer_plan import plan_transfers

runner = CliRunner()


def test_transfer_plan_moves_too_young_bottle_to_aging_cellar(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "DrinkSoon,D1,2022,Young Wine,Bourgogne,Rouge,Domaine Test,2030,2035,1,75\n"
        "Aging,A1,2020,Aging Placeholder,Bourgogne,Rouge,Domaine Test,,,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    update_cellar_profile(database_path, name="DrinkSoon", purpose="drink_soon")
    update_cellar_profile(database_path, name="Aging", purpose="aging")

    transfer_plan = plan_transfers(database_path, as_of_year=2025)

    assert len(transfer_plan.suggestions) == 1
    assert transfer_plan.suggestions[0].action == "move"
    assert transfer_plan.suggestions[0].bottle_id == 1
    assert transfer_plan.suggestions[0].current_cellar == "DrinkSoon"
    assert transfer_plan.suggestions[0].current_location == "D1"
    assert transfer_plan.suggestions[0].target_cellar == "Aging"
    assert transfer_plan.suggestions[0].target_purpose == "aging"


def test_transfer_plan_moves_overdue_bottle_to_drink_soon_cellar(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "Aging,A1,2018,Ready Wine,Champagne,Blanc,Maison Test,2020,2024,1,75\n"
        "DrinkSoon,D1,2020,Drink Soon Placeholder,France,Rouge,Domaine Test,,,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    update_cellar_profile(database_path, name="Aging", purpose="aging")
    update_cellar_profile(database_path, name="DrinkSoon", purpose="drink_soon")

    transfer_plan = plan_transfers(database_path, as_of_year=2025)

    assert len(transfer_plan.suggestions) == 1
    assert transfer_plan.suggestions[0].action == "move"
    assert transfer_plan.suggestions[0].bottle_id == 1
    assert transfer_plan.suggestions[0].current_cellar == "Aging"
    assert transfer_plan.suggestions[0].current_location == "A1"
    assert transfer_plan.suggestions[0].target_cellar == "DrinkSoon"
    assert transfer_plan.suggestions[0].target_purpose == "drink_soon"


def test_transfer_plan_reviews_when_no_target_cellar_exists(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "Aging,A1,2018,Ready Wine,Champagne,Blanc,Maison Test,2020,2024,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    update_cellar_profile(database_path, name="Aging", purpose="aging")

    transfer_plan = plan_transfers(database_path, as_of_year=2025)

    assert len(transfer_plan.suggestions) == 1
    assert transfer_plan.suggestions[0].action == "review"
    assert transfer_plan.suggestions[0].target_cellar is None
    assert transfer_plan.suggestions[0].target_purpose == "drink_soon"


def test_transfer_plan_reviews_bottle_without_location(
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

    transfer_plan = plan_transfers(database_path, as_of_year=2025)

    assert len(transfer_plan.suggestions) == 1
    assert transfer_plan.suggestions[0].action == "review"
    assert transfer_plan.suggestions[0].current_cellar is None
    assert transfer_plan.suggestions[0].current_location is None
    assert transfer_plan.suggestions[0].target_cellar is None
    assert transfer_plan.suggestions[0].target_purpose is None


def test_transfer_plan_uses_less_full_matching_target_cellar(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "DrinkSoon,D1,2022,Young Wine,Bourgogne,Rouge,Domaine Test,2030,2035,1,75\n"
        "AgingFull,A1,2020,Aging Full Placeholder,Bourgogne,Rouge,Domaine Test,,,5,75\n"
        "AgingEmpty,A2,2020,Aging Empty Placeholder,Bourgogne,Rouge,Domaine Test,,,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    update_cellar_profile(database_path, name="DrinkSoon", purpose="drink_soon")
    update_cellar_profile(
        database_path,
        name="AgingFull",
        purpose="aging",
        capacity_estimate=5,
        capacity_warning_threshold=5,
    )
    update_cellar_profile(
        database_path,
        name="AgingEmpty",
        purpose="aging",
        capacity_estimate=10,
        capacity_warning_threshold=9,
    )

    transfer_plan = plan_transfers(database_path, as_of_year=2025)

    assert len(transfer_plan.suggestions) == 1
    assert transfer_plan.suggestions[0].target_cellar == "AgingEmpty"


def test_transfer_plan_respects_limit(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "Aging,A1,2018,Ready Wine 1,Champagne,Blanc,Maison Test,2020,2024,1,75\n"
        "Aging,A2,2018,Ready Wine 2,Champagne,Blanc,Maison Test,2020,2024,1,75\n"
        "DrinkSoon,D1,2020,Drink Soon Placeholder,France,Rouge,Domaine Test,,,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    update_cellar_profile(database_path, name="Aging", purpose="aging")
    update_cellar_profile(database_path, name="DrinkSoon", purpose="drink_soon")

    transfer_plan = plan_transfers(
        database_path,
        as_of_year=2025,
        limit=1,
    )

    assert len(transfer_plan.suggestions) == 1


def test_plan_transfers_command_outputs_suggestions(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "Aging,A1,2018,Ready Wine,Champagne,Blanc,Maison Test,2020,2024,1,75\n"
        "DrinkSoon,D1,2020,Drink Soon Placeholder,France,Rouge,Domaine Test,,,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    update_cellar_profile(database_path, name="Aging", purpose="aging")
    update_cellar_profile(database_path, name="DrinkSoon", purpose="drink_soon")

    result = runner.invoke(
        app,
        [
            "plan",
            "transfers",
            "--database",
            str(database_path),
            "--year",
            "2025",
        ],
    )

    assert result.exit_code == 0
    assert "Database:" in result.output
    assert "Transfer plan" in result.output
    assert "Ready Wine" in result.output
    assert "DrinkSoon" in result.output


def test_transfer_plan_does_not_target_cellar_at_capacity(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "DrinkSoon,D1,2022,Young Wine,Bourgogne,Rouge,Domaine Test,2030,2035,1,75\n"
        "AgingFull,A1,2020,Aging Full Placeholder,Bourgogne,Rouge,Domaine Test,,,5,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    update_cellar_profile(database_path, name="DrinkSoon", purpose="drink_soon")
    update_cellar_profile(
        database_path,
        name="AgingFull",
        purpose="aging",
        capacity_estimate=5,
        capacity_warning_threshold=5,
    )

    transfer_plan = plan_transfers(database_path, as_of_year=2025)

    assert len(transfer_plan.suggestions) == 1
    assert transfer_plan.suggestions[0].action == "review"
    assert transfer_plan.suggestions[0].target_cellar is None
    assert transfer_plan.suggestions[0].target_purpose == "aging"
