from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.storage.ai_window_estimator import (
    AIWindowUsage,
    OpenAIEstimateResponse,
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

    def fake_call_openai_estimate(
        *,
        wine,
        model: str,
        use_web_search: bool,
    ) -> OpenAIEstimateResponse:
        return _fake_estimate_response(
            payload={
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
            },
            web_search_used=True,
        )

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
    assert estimate.web_search_enabled is True
    assert estimate.web_search_used is True
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

    def fake_call_openai_estimate(
        *,
        wine,
        model: str,
        use_web_search: bool,
    ) -> OpenAIEstimateResponse:
        return _fake_estimate_response(
            payload={
                "drink_from_year": 2030,
                "drink_until_year": 2020,
                "confidence": "medium",
                "rationale": "Invalid.",
                "sources": [],
            },
            web_search_used=True,
        )

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


def test_openai_estimate_requires_web_search_when_enabled(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    captured_request: dict[str, Any] = {}

    class FakeResponses:
        def create(self, **kwargs):
            captured_request.update(kwargs)

            return _fake_openai_response(
                payload={
                    "drink_from_year": 2022,
                    "drink_until_year": 2030,
                    "confidence": "medium",
                    "rationale": "Example rationale.",
                    "sources": [],
                },
                output=[{"type": "web_search_call"}],
                usage={
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                },
            )

    class FakeClient:
        def __init__(self) -> None:
            self.responses = FakeResponses()

    monkeypatch.setattr(
        "cellarmind.storage.ai_window_estimator.OpenAI",
        FakeClient,
    )

    estimate = estimate_ai_drinking_window(
        database_path,
        wine_id=wine_id,
        model="test-model",
        use_web_search=True,
    )

    assert captured_request["tools"] == [{"type": "web_search"}]
    assert captured_request["tool_choice"] == "required"
    assert estimate.web_search_used is True
    assert estimate.usage is not None
    assert estimate.usage.input_tokens == 100
    assert estimate.usage.output_tokens == 50
    assert estimate.usage.total_tokens == 150


def test_openai_estimate_does_not_enable_web_search_when_disabled(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    captured_request: dict[str, Any] = {}

    class FakeResponses:
        def create(self, **kwargs):
            captured_request.update(kwargs)

            return _fake_openai_response(
                payload={
                    "drink_from_year": 2022,
                    "drink_until_year": 2030,
                    "confidence": "medium",
                    "rationale": "Example rationale.",
                    "sources": [],
                },
                output=[],
                usage={
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                },
            )

    class FakeClient:
        def __init__(self) -> None:
            self.responses = FakeResponses()

    monkeypatch.setattr(
        "cellarmind.storage.ai_window_estimator.OpenAI",
        FakeClient,
    )

    estimate = estimate_ai_drinking_window(
        database_path,
        wine_id=wine_id,
        model="test-model",
        use_web_search=False,
    )

    assert captured_request["tools"] == []
    assert "tool_choice" not in captured_request
    assert estimate.web_search_enabled is False
    assert estimate.web_search_used is False


def test_reference_window_estimate_command_dry_run(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_call_openai_estimate(
        *,
        wine,
        model: str,
        use_web_search: bool,
    ) -> OpenAIEstimateResponse:
        return _fake_estimate_response(
            payload={
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
            },
            web_search_used=True,
            usage=AIWindowUsage(
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
            ),
        )

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
    assert "enabled, used" in result.output
    assert "2022-2030" in result.output
    assert "input=100 tokens" in result.output
    assert "output=50 tokens" in result.output
    assert "total=150 tokens" in result.output
    assert "Dry-run only" in result.output

    assert list_reference_windows(database_path, wine_id=wine_id) == ()


def test_reference_window_estimate_command_save(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    calls = 0

    def fake_call_openai_estimate(
        *,
        wine,
        model: str,
        use_web_search: bool,
    ) -> OpenAIEstimateResponse:
        nonlocal calls
        calls += 1

        return _fake_estimate_response(
            payload={
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
            },
            web_search_used=True,
            usage=AIWindowUsage(
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
            ),
        )

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
    assert "input=100 tokens" in result.output
    assert "output=50 tokens" in result.output
    assert "total=150 tokens" in result.output
    assert calls == 1

    windows = list_reference_windows(database_path, wine_id=wine_id)

    assert len(windows) == 1
    assert windows[0].source_name == "AI estimate (OpenAI)"
    assert windows[0].source_url is None
    assert windows[0].drink_from_year == 2022
    assert windows[0].drink_until_year == 2030
    assert windows[0].confidence == "medium"

    notes = windows[0].notes or ""

    assert "AI model: test-model" in notes
    assert "Provider: OpenAI" in notes
    assert "Web search enabled: True" in notes
    assert "Web search used: True" in notes
    assert "input_tokens=100" in notes
    assert "output_tokens=50" in notes
    assert "total_tokens=150" in notes
    assert "https://example.com/wine" in notes


def _fake_estimate_response(
    *,
    payload: dict[str, Any],
    web_search_used: bool,
    usage: AIWindowUsage | None = None,
) -> OpenAIEstimateResponse:
    return OpenAIEstimateResponse(
        payload=payload,
        usage=usage,
        web_search_used=web_search_used,
    )


def _fake_openai_response(
    *,
    payload: dict[str, Any],
    output: list[dict[str, str]],
    usage: dict[str, int],
):
    return SimpleNamespace(
        output_text=json.dumps(payload),
        output=output,
        usage=usage,
    )


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
