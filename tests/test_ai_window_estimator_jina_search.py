from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.storage.ai_window_estimator import estimate_ai_drinking_window
from cellarmind.storage.sqlite import connect_database


def test_ollama_estimate_can_use_jina_search_provider(monkeypatch, tmp_path: Path) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path)
    captured_query: dict[str, object] = {}

    def fake_search_jina_for_reference_sources(
        *,
        query: str,
        limit: int,
        timeout_seconds: float,
    ):
        captured_query["query"] = query
        captured_query["limit"] = limit
        return (
            SimpleNamespace(
                title="Low relevance page",
                url="https://example.com/other",
                snippet="Generic Burgundy text.",
            ),
            SimpleNamespace(
                title="Producer A AI Estimate Wine 2018 drinking window",
                url="https://example.com/wine",
                snippet="Drink from 2022 until 2030.",
            ),
        )

    def fake_read_url_with_jina(source_url: str) -> str:
        if source_url == "https://example.com/wine":
            return "Recommended drinking window 2022-2030."
        return "Generic page."

    def fake_post_json(
        url: str,
        payload: dict[str, Any],
        *,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        prompt = payload["messages"][1]["content"]
        assert "https://example.com/wine" in prompt
        return {
            "message": {
                "content": json.dumps(
                    {
                        "drink_from_year": 2022,
                        "drink_until_year": 2030,
                        "confidence": "medium",
                        "rationale": "The ranked Jina evidence states 2022-2030.",
                        "sources": [
                            {
                                "title": "Producer A AI Estimate Wine 2018 drinking window",
                                "url": "https://example.com/wine",
                                "note": "Explicit window.",
                            }
                        ],
                    }
                )
            },
            "prompt_eval_count": 100,
            "eval_count": 30,
        }

    monkeypatch.setattr(
        "cellarmind.storage.ai_window_estimator.search_jina_for_reference_sources",
        fake_search_jina_for_reference_sources,
    )
    monkeypatch.setattr(
        "cellarmind.storage.ai_window_estimator._read_url_with_jina",
        fake_read_url_with_jina,
    )
    monkeypatch.setattr(
        "cellarmind.storage.ai_window_estimator._post_json",
        fake_post_json,
    )

    estimate = estimate_ai_drinking_window(
        database_path,
        wine_id=wine_id,
        provider="ollama",
        model="test-local-model",
        web_search_provider="jina",
        evidence_limit=2,
    )

    assert "AI Estimate Wine" in str(captured_query["query"])
    assert captured_query["limit"] == 2
    assert estimate.web_search_provider == "jina"
    assert estimate.evidence[0].url == "https://example.com/wine"
    assert estimate.drink_from_year == 2022
    assert estimate.drink_until_year == 2030


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
