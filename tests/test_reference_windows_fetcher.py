from pathlib import Path

import pytest
from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.storage.reference_windows import list_reference_windows
from cellarmind.storage.reference_windows_fetcher import (
    extract_reference_window_from_text,
    fetch_reference_window_candidate,
    html_to_text,
)
from cellarmind.storage.sqlite import connect_database

runner = CliRunner()


def test_extract_reference_window_from_english_text() -> None:
    candidate = extract_reference_window_from_text(
        "This wine has a drinking window from 2024 to 2032."
    )

    assert candidate.drink_from_year == 2024
    assert candidate.drink_until_year == 2032
    assert candidate.confidence == "medium"


def test_extract_reference_window_from_french_text() -> None:
    candidate = extract_reference_window_from_text("Cette cuvée est à boire de 2025 à 2035.")

    assert candidate.drink_from_year == 2025
    assert candidate.drink_until_year == 2035
    assert candidate.confidence == "medium"


def test_extract_reference_window_until_only() -> None:
    candidate = extract_reference_window_from_text("A boire jusqu'à 2030.")

    assert candidate.drink_from_year is None
    assert candidate.drink_until_year == 2030
    assert candidate.confidence == "low"


def test_extract_reference_window_rejects_text_without_window() -> None:
    with pytest.raises(ValueError, match="No drinking window"):
        extract_reference_window_from_text(
            "This page talks about a wine but does not mention a drinking window."
        )


def test_html_to_text_ignores_script_and_style() -> None:
    text = html_to_text(
        """
        <html>
            <head>
                <style>.hidden { color: red; }</style>
                <script>const year = 2099;</script>
            </head>
            <body>
                <p>Drinking window 2024-2032.</p>
            </body>
        </html>
        """
    )

    assert "Drinking window 2024-2032." in text
    assert "2099" not in text
    assert "hidden" not in text


def test_fetch_reference_window_candidate_from_url(monkeypatch) -> None:
    def fake_fetch_url_text(
        source_url: str, *, timeout_seconds: float, max_bytes: int = 2_000_000
    ) -> str:
        return "<html><body>Drinking window 2024-2032.</body></html>"

    monkeypatch.setattr(
        "cellarmind.storage.reference_windows_fetcher.fetch_url_text",
        fake_fetch_url_text,
    )

    candidate = fetch_reference_window_candidate(
        source_url="https://example.com/wine",
        source_name="Example source",
    )

    assert candidate.source_name == "Example source"
    assert candidate.source_url == "https://example.com/wine"
    assert candidate.drink_from_year == 2024
    assert candidate.drink_until_year == 2032
    assert candidate.confidence == "medium"
    assert "2024-2032" in candidate.evidence_text


def test_fetch_reference_window_candidate_defaults_source_name(monkeypatch) -> None:
    def fake_fetch_url_text(
        source_url: str, *, timeout_seconds: float, max_bytes: int = 2_000_000
    ) -> str:
        return "<html><body>Drinking window 2024-2032.</body></html>"

    monkeypatch.setattr(
        "cellarmind.storage.reference_windows_fetcher.fetch_url_text",
        fake_fetch_url_text,
    )

    candidate = fetch_reference_window_candidate(
        source_url="https://www.example.com/wine",
    )

    assert candidate.source_name == "example.com"


def test_reference_window_fetch_command_dry_run(monkeypatch, tmp_path: Path) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path, cuvee="Internet Wine")

    def fake_fetch_url_text(
        source_url: str, *, timeout_seconds: float, max_bytes: int = 2_000_000
    ) -> str:
        return "<html><body>Drinking window 2024-2032.</body></html>"

    monkeypatch.setattr(
        "cellarmind.storage.reference_windows_fetcher.fetch_url_text",
        fake_fetch_url_text,
    )

    result = runner.invoke(
        app,
        [
            "reference-window",
            "fetch",
            "--database",
            str(database_path),
            "--wine-id",
            str(wine_id),
            "--url",
            "https://example.com/wine",
            "--source-name",
            "Example source",
        ],
    )

    assert result.exit_code == 0
    assert "Fetched reference drinking window" in result.output
    assert "2024-2032" in result.output
    assert "Dry-run only" in result.output

    assert list_reference_windows(database_path, wine_id=wine_id) == ()


def test_reference_window_fetch_command_save(monkeypatch, tmp_path: Path) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path, cuvee="Internet Wine")

    def fake_fetch_url_text(
        source_url: str, *, timeout_seconds: float, max_bytes: int = 2_000_000
    ) -> str:
        return "<html><body>Drinking window 2024-2032.</body></html>"

    monkeypatch.setattr(
        "cellarmind.storage.reference_windows_fetcher.fetch_url_text",
        fake_fetch_url_text,
    )

    result = runner.invoke(
        app,
        [
            "reference-window",
            "fetch",
            "--database",
            str(database_path),
            "--wine-id",
            str(wine_id),
            "--url",
            "https://example.com/wine",
            "--source-name",
            "Example source",
            "--confidence",
            "high",
            "--save",
        ],
    )

    assert result.exit_code == 0
    assert "Saved reference drinking window" in result.output

    windows = list_reference_windows(database_path, wine_id=wine_id)

    assert len(windows) == 1
    assert windows[0].source_name == "Example source"
    assert windows[0].source_url == "https://example.com/wine"
    assert windows[0].drink_from_year == 2024
    assert windows[0].drink_until_year == 2032
    assert windows[0].confidence == "high"
    assert "Extracted evidence" in (windows[0].notes or "")


def _create_database_with_wine(tmp_path: Path) -> Path:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "Main,A1,2018,Internet Wine,France,Rouge,Producer A,2020,2030,1,75\n",
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


def test_reference_window_fetch_command_save_uses_extracted_confidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path, cuvee="Internet Wine")

    def fake_fetch_url_text(
        source_url: str,
        *,
        timeout_seconds: float,
        max_bytes: int = 2_000_000,
    ) -> str:
        return "A boire jusqu'à 2030."

    monkeypatch.setattr(
        "cellarmind.storage.reference_windows_fetcher.fetch_url_text",
        fake_fetch_url_text,
    )

    result = runner.invoke(
        app,
        [
            "reference-window",
            "fetch",
            "--database",
            str(database_path),
            "--wine-id",
            str(wine_id),
            "--url",
            "https://example.com/wine",
            "--source-name",
            "Example source",
            "--save",
        ],
    )

    assert result.exit_code == 0

    windows = list_reference_windows(database_path, wine_id=wine_id)

    assert len(windows) == 1
    assert windows[0].drink_from_year is None
    assert windows[0].drink_until_year == 2030
    assert windows[0].confidence == "low"
