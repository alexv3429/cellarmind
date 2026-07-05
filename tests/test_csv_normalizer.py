from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.importing.normalizer import normalize_csv_to_canonical


def test_normalize_csv_to_canonical_accepts_french_aliases(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    output_path = tmp_path / "canonical.csv"

    input_path.write_text(
        "Producteur,Cuvée,Millésime,Appellation,Couleur\n"
        " Domaine Test , Cuvée Test , 2020 , Test Appellation , Rouge \n",
        encoding="utf-8",
    )

    result = normalize_csv_to_canonical(input_path, output_path)

    assert result.output_path == output_path
    assert result.rows == 1
    assert result.columns == (
        "producer",
        "cuvee",
        "vintage",
        "appellation",
        "color",
        "format",
        "quantity",
        "cellar",
        "location",
        "purchase_price",
        "personal_drink_from_year",
        "personal_drink_until_year",
    )

    df = pl.read_csv(output_path, infer_schema_length=0)

    assert df.columns == [
        "producer",
        "cuvee",
        "vintage",
        "appellation",
        "color",
        "format",
        "quantity",
        "cellar",
        "location",
        "purchase_price",
        "personal_drink_from_year",
        "personal_drink_until_year",
    ]
    assert df.row(0) == (
        "Domaine Test",
        "Cuvée Test",
        "2020",
        "Test Appellation",
        "Rouge",
        "750ml",
        "1",
        "",
        "",
        "",
        "",
        "",
    )


def test_normalize_command_creates_canonical_csv(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    output_path = tmp_path / "canonical.csv"

    input_path.write_text(
        "Producteur,Cuvée,Année Prod,Appellation,Couleur\n"
        "Domaine Test,Cuvée Test,2020,Test Appellation,Rouge\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["normalize", str(input_path), "--output", str(output_path)],
    )

    assert result.exit_code == 0
    assert output_path.exists()
    assert "Canonical CSV created" in result.output


def test_normalize_csv_to_canonical_accepts_stock_fields(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    output_path = tmp_path / "canonical.csv"

    input_path.write_text(
        "Producteur,Cuvée,Millésime,Appellation,Couleur,Format,Quantité,Cave,Place\n"
        "Domaine Test,Cuvée Test,2020,Test Appellation,Rouge,50cl,2,Cave maison,Casier A\n",
        encoding="utf-8",
    )

    normalize_csv_to_canonical(input_path, output_path)

    df = pl.read_csv(output_path, infer_schema_length=0)

    assert df.row(0) == (
        "Domaine Test",
        "Cuvée Test",
        "2020",
        "Test Appellation",
        "Rouge",
        "500ml",
        "2",
        "Cave maison",
        "Casier A",
        "",
        "",
        "",
    )


def test_normalize_csv_to_canonical_accepts_personal_fields(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    output_path = tmp_path / "canonical.csv"

    input_path.write_text(
        "Producteur,Cuvée,Millésime,Appellation,Couleur,Format,Quantité,Cave,Place,Prix,Min,Max\n"
        "Domaine Test,Cuvée Test,2020,Test Appellation,Rouge,50cl,2,House,Casier A,10,2020,2025\n",
        encoding="utf-8",
    )

    normalize_csv_to_canonical(input_path, output_path)

    df = pl.read_csv(output_path, infer_schema_length=0)

    assert df.row(0) == (
        "Domaine Test",
        "Cuvée Test",
        "2020",
        "Test Appellation",
        "Rouge",
        "500ml",
        "2",
        "House",
        "Casier A",
        "10",
        "2020",
        "2025",
    )


def test_normalize_csv_rejects_invalid_quantity(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"

    input_path.write_text(
        "Producteur,Cuvée,Millésime,Appellation,Couleur,Quantité\n"
        "Domaine Test,Cuvée Test,2020,Test Appellation,Rouge,-1\n",
        encoding="utf-8",
    )

    try:
        normalize_csv_to_canonical(input_path)
    except ValueError as exc:
        assert "Quantity must be a positive integer: '-1'" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_normalize_allows_zero_quantity(tmp_path: Path) -> None:
    input_path = tmp_path / "cave.csv"
    output_path = tmp_path / "canonical.csv"

    input_path.write_text(
        "Producteur,Cuvée,Année prod,Appellation,Vignoble couleur,Nb,Fmt\n"
        "Maison Test,Brut Réserve,2018,Champagne,Blanc,0,75\n",
        encoding="utf-8",
    )

    normalize_csv_to_canonical(input_path, output_path)

    assert ",0," in output_path.read_text(encoding="utf-8")
