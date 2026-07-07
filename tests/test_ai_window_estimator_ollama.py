from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.storage.ai_window_estimator import estimate_ai_drinking_window
from cellarmind.storage.reference_windows import list_reference_windows
from cellarmind.storage.sqlite import connect_database

runner = CliRunner()


def test_ollama_estimate_uses_jina_reader_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path)

    captured_ollama_payload: dict[str, Any] = {}
    read_urls: list[str] = []

    def fake_search_web_for_reference_sources(
        *,
        query: str,
        limit: int,
        timeout_seconds: float,
    ):
        assert "AI Estimate Wine" in query
        assert limit == 2

        return (
            SimpleNamespace(
                title="Example merchant page",
                url="https://example.com/wine",
                snippet="Drink from 2022 until 2030.",
            ),
        )

    def fake_read_url_with_jina(source_url: str) -> str:
        read_urls.append(source_url)
        return "This wine has a recommended drinking window from 2022 to 2030."

    def fake_post_json(
        url: str,
        payload: dict[str, Any],
        *,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        captured_ollama_payload.update(payload)

        return {
            "message": {
                "content": json.dumps(
                    {
                        "drink_from_year": 2022,
                        "drink_until_year": 2030,
                        "confidence": "medium",
                        "rationale": "The gathered evidence gives a 2022-2030 window.",
                        "sources": [
                            {
                                "title": "Example merchant page",
                                "url": "https://example.com/wine",
                                "note": "Evidence states 2022-2030.",
                            }
                        ],
                    }
                )
            },
            "prompt_eval_count": 120,
            "eval_count": 40,
        }

    monkeypatch.setattr(
        "cellarmind.storage.ai_window_estimator.search_web_for_reference_sources",
        fake_search_web_for_reference_sources,
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
        evidence_limit=2,
    )

    assert estimate.provider == "ollama"
    assert estimate.source_name == "AI estimate (local)"
    assert estimate.model == "test-local-model"
    assert estimate.web_search_enabled is True
    assert estimate.web_search_used is True
    assert estimate.web_reader == "jina"
    assert estimate.drink_from_year == 2022
    assert estimate.drink_until_year == 2030
    assert estimate.usage is not None
    assert estimate.usage.input_tokens == 120
    assert estimate.usage.output_tokens == 40
    assert estimate.usage.total_tokens == 160
    assert len(estimate.evidence) == 1
    assert estimate.evidence[0].url == "https://example.com/wine"
    assert read_urls == ["https://example.com/wine"]
    assert captured_ollama_payload["model"] == "test-local-model"
    assert captured_ollama_payload["stream"] is False
    assert "format" in captured_ollama_payload


def test_ollama_estimate_can_run_without_web_search(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path)

    def fail_search_web_for_reference_sources(
        *,
        query: str,
        limit: int,
        timeout_seconds: float,
    ):
        raise AssertionError("Search should not run when web search is disabled.")

    def fake_post_json(
        url: str,
        payload: dict[str, Any],
        *,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        return {
            "message": {
                "content": json.dumps(
                    {
                        "drink_from_year": 2022,
                        "drink_until_year": 2028,
                        "confidence": "low",
                        "rationale": "General local-model estimate.",
                        "sources": [],
                    }
                )
            },
            "prompt_eval_count": 80,
            "eval_count": 30,
        }

    monkeypatch.setattr(
        "cellarmind.storage.ai_window_estimator.search_web_for_reference_sources",
        fail_search_web_for_reference_sources,
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
        use_web_search=False,
    )

    assert estimate.provider == "ollama"
    assert estimate.web_search_enabled is False
    assert estimate.web_search_used is False
    assert estimate.evidence == ()
    assert estimate.drink_from_year == 2022
    assert estimate.drink_until_year == 2028


def test_reference_window_estimate_command_ollama_save(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path)

    calls = 0

    def fake_search_web_for_reference_sources(
        *,
        query: str,
        limit: int,
        timeout_seconds: float,
    ):
        return (
            SimpleNamespace(
                title="Example merchant page",
                url="https://example.com/wine",
                snippet="Drink from 2022 until 2030.",
            ),
        )

    def fake_read_url_with_jina(source_url: str) -> str:
        return "This wine has a recommended drinking window from 2022 to 2030."

    def fake_post_json(
        url: str,
        payload: dict[str, Any],
        *,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        nonlocal calls
        calls += 1

        return {
            "message": {
                "content": json.dumps(
                    {
                        "drink_from_year": 2022,
                        "drink_until_year": 2030,
                        "confidence": "medium",
                        "rationale": "The gathered evidence gives a 2022-2030 window.",
                        "sources": [
                            {
                                "title": "Example merchant page",
                                "url": "https://example.com/wine",
                                "note": "Evidence states 2022-2030.",
                            }
                        ],
                    }
                )
            },
            "prompt_eval_count": 120,
            "eval_count": 40,
        }

    monkeypatch.setattr(
        "cellarmind.storage.ai_window_estimator.search_web_for_reference_sources",
        fake_search_web_for_reference_sources,
    )
    monkeypatch.setattr(
        "cellarmind.storage.ai_window_estimator._read_url_with_jina",
        fake_read_url_with_jina,
    )
    monkeypatch.setattr(
        "cellarmind.storage.ai_window_estimator._post_json",
        fake_post_json,
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
            "--provider",
            "ollama",
            "--model",
            "test-local-model",
            "--save",
        ],
    )

    assert result.exit_code == 0
    assert "AI drinking-window estimate" in result.output
    assert "ollama" in result.output
    assert "Gathered web evidence" in result.output
    assert "input=120 tokens" in result.output
    assert "output=40 tokens" in result.output
    assert "total=160 tokens" in result.output
    assert "Saved AI reference drinking window" in result.output
    assert calls == 1

    windows = list_reference_windows(database_path, wine_id=wine_id)

    assert len(windows) == 1
    assert windows[0].source_name == "AI estimate (local)"
    assert windows[0].source_url is None
    assert windows[0].drink_from_year == 2022
    assert windows[0].drink_until_year == 2030
    assert windows[0].confidence == "medium"

    notes = windows[0].notes or ""

    assert "Provider: ollama" in notes
    assert "Source name: AI estimate (local)" in notes
    assert "Web reader: jina" in notes
    assert "input_tokens=120" in notes
    assert "output_tokens=40" in notes
    assert "total_tokens=160" in notes
    assert "https://example.com/wine" in notes


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
