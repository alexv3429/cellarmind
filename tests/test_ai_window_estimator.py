from pathlib import Path

import pytest
from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.storage.ai_window_estimator import (
    estimate_ai_drinking_window,
)
from cellarmind.storage.reference_windows import list_reference_windows
from cellarmind.storage.sqlite import connect_database

runner = CliRunner()


def test_ai_window_estimate_returns_structured_estimate(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_call_openai_estimate(*, wine, model: str, use_web_search: bool):
        return {
            "drink_from_year": 2022,
            "drink_until_year": 2030,
            "confidence": "medium",
            "rationale": "Regional and producer style suggest mid-term drinking.",
            "sources": [
                {
                    "title": "Example source",
                    "url": "https://example.com/wine",
                    "note": "Mentions a 2022-2030 window.",
                }
            ],
        }

    monkeypatch.setattr(
        "cellarmind.storage.ai_window_estimator._call_openai_estimate",
        fake_call_openai_estimate,
    )

    estimate = estimate_ai_drinking_window(
        database_path,
        wine_id=wine_id,
        model="test-model",
    )

    assert estimate.wine.wine_id == wine_id
    assert estimate.drink_from_year == 2022
    assert estimate.drink_until_year == 2030
    assert estimate.confidence == "medium"
    assert estimate.sources[0].url == "https://example.com/wine"


def test_ai_window_estimate_rejects_unknown_wine_id(tmp_path: Path) -> None:
    database_path = _create_database_with_wine(tmp_path)

    with pytest.raises(ValueError, match="Unknown wine id"):
        estimate_ai_drinking_window(
            database_path,
            wine_id=999,
            model="test-model",
        )


def test_ai_window_estimate_rejects_missing_database(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        estimate_ai_drinking_window(
            tmp_path / "missing.sqlite",
            wine_id=1,
            model="test-model",
        )


def test_ai_window_estimate_requires_api_key(monkeypatch, tmp_path: Path) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path)

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        estimate_ai_drinking_window(
            database_path,
            wine_id=wine_id,
            model="test-model",
        )


def test_ai_window_estimate_rejects_invalid_window(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_call_openai_estimate(*, wine, model: str, use_web_search: bool):
        return {
            "drink_from_year": 2030,
            "drink_until_year": 2020,
            "confidence": "medium",
            "rationale": "Invalid.",
            "sources": [],
        }

    monkeypatch.setattr(
        "cellarmind.storage.ai_window_estimator._call_openai_estimate",
        fake_call_openai_estimate,
    )

    with pytest.raises(ValueError, match="invalid drinking window"):
        estimate_ai_drinking_window(
            database_path,
            wine_id=wine_id,
            model="test-model",
        )


def test_reference_window_estimate_command_dry_run(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_call_openai_estimate(*, wine, model: str, use_web_search: bool):
        return {
            "drink_from_year": 2022,
            "drink_until_year": 2030,
            "confidence": "medium",
            "rationale": "Example rationale.",
            "sources": [
                {
                    "title": "Example source",
                    "url": "https://example.com/wine",
                    "note": "Example note.",
                }
            ],
        }

    monkeypatch.setattr(
        "cellarmind.storage.ai_window_estimator._call_openai_estimate",
        fake_call_openai_estimate,
    )

    result = runner.invoke(
        app,
        [
            "reference-window",
            "estimate",
            "--database",
            str(database_path),
            "--wine-id",
            str(wine_id),
            "--model",
            "test-model",
        ],
    )

    assert result.exit_code == 0
    assert "AI drinking-window estimate" in result.output
    assert "2022-2030" in result.output
    assert "Dry-run only" in result.output

    assert list_reference_windows(database_path, wine_id=wine_id) == ()


def test_reference_window_estimate_command_save(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_call_openai_estimate(*, wine, model: str, use_web_search: bool):
        return {
            "drink_from_year": 2022,
            "drink_until_year": 2030,
            "confidence": "medium",
            "rationale": "Example rationale.",
            "sources": [
                {
                    "title": "Example source",
                    "url": "https://example.com/wine",
                    "note": "Example note.",
                }
            ],
        }

    monkeypatch.setattr(
        "cellarmind.storage.ai_window_estimator._call_openai_estimate",
        fake_call_openai_estimate,
    )

    result = runner.invoke(
        app,
        [
            "reference-window",
            "estimate",
            "--database",
            str(database_path),
            "--wine-id",
            str(wine_id),
            "--model",
            "test-model",
            "--save",
        ],
    )

    assert result.exit_code == 0
    assert "Saved AI reference drinking window" in result.output

    windows = list_reference_windows(database_path, wine_id=wine_id)

    assert len(windows) == 1
    assert windows[0].source_name == "AI estimate (OpenAI)"
    assert windows[0].source_url is None
    assert windows[0].drink_from_year == 2022
    assert windows[0].drink_until_year == 2030
    assert windows[0].confidence == "medium"
    assert "AI model: test-model" in (windows[0].notes or "")
    assert "https://example.com/wine" in (windows[0].notes or "")


def _create_database_with_wine(tmp_path: Path) -> Path:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "Main,A1,2018,AI Estimate Wine,France,Rouge,Producer A,2020,2030,1,75\n",
        encoding="utf-8",
    )

    import_csv_to_database(input_path, database_path)

    return database_path


def _get_wine_id(database_path: Path) -> int:
    with connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT id
            FROM wine
            WHERE cuvee = ?
            """,
            ("AI Estimate Wine",),
        ).fetchone()

    assert row is not None

    return int(row["id"])
