from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.storage.ai_window_estimator import estimate_ai_drinking_window
from cellarmind.storage.sqlite import connect_database


def test_gemini_estimate_uses_google_search_when_enabled(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path)
    captured: dict[str, Any] = {}

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def fake_post_json(url: str, payload: dict[str, Any], *, timeout_seconds: float):
        captured["url"] = url
        captured["payload"] = payload
        return _fake_gemini_response(grounded=True)

    monkeypatch.setattr(
        "cellarmind.storage.ai_window_estimator._post_json",
        fake_post_json,
    )

    estimate = estimate_ai_drinking_window(
        database_path,
        wine_id=wine_id,
        provider="gemini",
        model="gemini-test-model",
    )

    assert "gemini-test-model:generateContent" in str(captured["url"])
    assert captured["payload"]["tools"] == [{"googleSearch": {}}]
    assert estimate.provider == "gemini"
    assert estimate.source_name == "AI estimate (Gemini)"
    assert estimate.web_search_used is True
    assert estimate.drink_from_year == 2022
    assert estimate.drink_until_year == 2030
    assert estimate.usage is not None
    assert estimate.usage.input_tokens == 100
    assert estimate.usage.output_tokens == 50
    assert estimate.usage.total_tokens == 150


def test_gemini_estimate_does_not_enable_search_when_disabled(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path)
    captured: dict[str, Any] = {}

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def fake_post_json(url: str, payload: dict[str, Any], *, timeout_seconds: float):
        captured["payload"] = payload
        return _fake_gemini_response(grounded=False)

    monkeypatch.setattr(
        "cellarmind.storage.ai_window_estimator._post_json",
        fake_post_json,
    )

    estimate = estimate_ai_drinking_window(
        database_path,
        wine_id=wine_id,
        provider="gemini",
        model="gemini-test-model",
        use_web_search=False,
    )

    assert "tools" not in captured["payload"]
    assert estimate.web_search_enabled is False
    assert estimate.web_search_used is False


def test_gemini_estimate_requires_api_key(monkeypatch, tmp_path: Path) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path)

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        estimate_ai_drinking_window(
            database_path,
            wine_id=wine_id,
            provider="gemini",
            model="gemini-test-model",
        )


def _fake_gemini_response(*, grounded: bool) -> dict[str, Any]:
    candidate: dict[str, Any] = {
        "content": {
            "parts": [
                {
                    "text": json.dumps(
                        {
                            "drink_from_year": 2022,
                            "drink_until_year": 2030,
                            "confidence": "medium",
                            "rationale": "Grounded Gemini estimate.",
                            "sources": [
                                {
                                    "title": "Example source",
                                    "url": "https://example.com/wine",
                                    "note": "Grounded source.",
                                }
                            ],
                        }
                    )
                }
            ]
        }
    }

    if grounded:
        candidate["groundingMetadata"] = {
            "webSearchQueries": ["Producer A AI Estimate Wine 2018 drinking window"],
            "groundingChunks": [
                {"web": {"uri": "https://example.com/wine", "title": "Example source"}}
            ],
        }

    return {
        "candidates": [candidate],
        "usageMetadata": {
            "promptTokenCount": 100,
            "candidatesTokenCount": 50,
            "totalTokenCount": 150,
        },
    }


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
