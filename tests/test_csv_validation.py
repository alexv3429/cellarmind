from pathlib import Path

from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.importing.schema import normalize_column_name, validate_csv_schema


def write_csv(path: Path, header: str) -> Path:
    path.write_text(
        f"{header}\nDomaine Test,Cuvée Test,2020,Test Appellation,Rouge\n",
        encoding="utf-8",
    )
    return path


def test_validate_csv_accepts_french_aliases(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "cave.csv",
        "Producteur,Cuvée,Millésime,Appellation,Couleur",
    )

    result = validate_csv_schema(path)

    assert result.valid
    assert result.mapping["producer"] == "Producteur"
    assert result.mapping["cuvee"] == "Cuvée"
    assert result.mapping["vintage"] == "Millésime"
    assert result.mapping["color"] == "Couleur"


def test_validate_csv_accepts_annee_prod_alias(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "cave.csv",
        "Producteur,Cuvée,Année Prod,Appellation,Couleur",
    )

    result = validate_csv_schema(path)

    assert result.valid
    assert result.mapping["vintage"] == "Année Prod"


def test_validate_csv_reports_missing_required_field(tmp_path: Path) -> None:
    path = tmp_path / "cave.csv"
    path.write_text(
        "Producteur,Cuvée,Millésime,Appellation\nDomaine Test,Cuvée Test,2020,Test Appellation\n",
        encoding="utf-8",
    )

    result = validate_csv_schema(path)

    assert not result.valid
    assert result.missing == ("color",)


def test_validate_command_returns_success_for_valid_csv(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "cave.csv",
        "Producteur,Cuvée,Millésime,Appellation,Couleur",
    )

    runner = CliRunner()
    result = runner.invoke(app, ["validate", str(path)])

    assert result.exit_code == 0
    assert "Valid CSV" in result.output


def test_normalize_column_name_removes_accents() -> None:
    assert normalize_column_name("Millésime") == "millesime"
    assert normalize_column_name("Année Prod") == "annee prod"
