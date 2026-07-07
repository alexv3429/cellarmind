from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection
from typing import Any

from openai import OpenAI

from cellarmind.storage.reference_windows import (
    ReferenceDrinkingWindow,
    add_reference_window,
)
from cellarmind.storage.sqlite import connect_database

OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_MODEL_ENV = "CELLARMIND_OPENAI_MODEL"
DEFAULT_OPENAI_MODEL = "gpt-5.5"

VALID_CONFIDENCES = {"low", "medium", "high"}


@dataclass(frozen=True)
class WineIdentity:
    wine_id: int
    producer: str
    cuvee: str
    vintage: str
    appellation: str
    color: str


@dataclass(frozen=True)
class AIWindowSource:
    title: str
    url: str | None
    note: str | None


@dataclass(frozen=True)
class AIWindowEstimate:
    wine: WineIdentity
    source_name: str
    model: str
    drink_from_year: int | None
    drink_until_year: int | None
    confidence: str
    rationale: str
    sources: tuple[AIWindowSource, ...]


def estimate_ai_drinking_window(
    database_path: Path,
    *,
    wine_id: int,
    model: str | None = None,
    use_web_search: bool = True,
) -> AIWindowEstimate:
    if not database_path.exists():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    resolved_model = _resolve_model(model)

    with connect_database(database_path) as connection:
        wine = _get_wine_identity(connection, wine_id=wine_id)

    payload = _call_openai_estimate(
        wine=wine,
        model=resolved_model,
        use_web_search=use_web_search,
    )

    return _payload_to_estimate(
        wine=wine,
        model=resolved_model,
        payload=payload,
    )


def estimate_and_add_ai_reference_window(
    database_path: Path,
    *,
    wine_id: int,
    model: str | None = None,
    use_web_search: bool = True,
) -> ReferenceDrinkingWindow:
    estimate = estimate_ai_drinking_window(
        database_path,
        wine_id=wine_id,
        model=model,
        use_web_search=use_web_search,
    )

    return add_reference_window(
        database_path,
        wine_id=wine_id,
        source_name=estimate.source_name,
        source_url=None,
        drink_from_year=estimate.drink_from_year,
        drink_until_year=estimate.drink_until_year,
        confidence=estimate.confidence,
        notes=_estimate_notes(estimate),
    )


def _resolve_model(model: str | None) -> str:
    if model is not None and model.strip():
        return model.strip()

    configured_model = os.environ.get(OPENAI_MODEL_ENV)

    if configured_model is not None and configured_model.strip():
        return configured_model.strip()

    return DEFAULT_OPENAI_MODEL


def _get_wine_identity(connection: Connection, *, wine_id: int) -> WineIdentity:
    row = connection.execute(
        """
        SELECT
            id,
            producer,
            cuvee,
            vintage,
            appellation,
            color
        FROM wine
        WHERE id = ?
        """,
        (wine_id,),
    ).fetchone()

    if row is None:
        raise ValueError(f"Unknown wine id: {wine_id}")

    return WineIdentity(
        wine_id=int(row["id"]),
        producer=row["producer"],
        cuvee=row["cuvee"],
        vintage=row["vintage"],
        appellation=row["appellation"],
        color=row["color"],
    )


def _call_openai_estimate(
    *,
    wine: WineIdentity,
    model: str,
    use_web_search: bool,
) -> dict[str, Any]:
    if not os.environ.get(OPENAI_API_KEY_ENV):
        raise ValueError(
            "OPENAI_API_KEY is not set. Set it before using AI drinking-window estimates."
        )

    client = OpenAI()

    tools: list[dict[str, str]] = []
    if use_web_search:
        tools.append({"type": "web_search"})

    response = client.responses.create(
        model=model,
        tools=tools,
        input=_estimate_prompt(wine),
        text={
            "format": {
                "type": "json_schema",
                "name": "drinking_window_estimate",
                "strict": True,
                "schema": _estimate_schema(),
            }
        },
    )

    return json.loads(response.output_text)


def _estimate_prompt(wine: WineIdentity) -> str:
    return f"""
Estimate a drinking window for this wine.

Wine:
- producer: {wine.producer}
- cuvee: {wine.cuvee}
- vintage: {wine.vintage}
- appellation: {wine.appellation}
- color: {wine.color}

Return only the structured JSON required by the schema.

Rules:
- Prefer cited, source-backed information.
- If sources disagree, choose a conservative practical cellar window.
- If you are uncertain, use confidence "low".
- Use null when a boundary cannot be estimated.
- Do not invent URLs.
- The estimate is advisory and must not claim certainty.
""".strip()


def _estimate_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "drink_from_year": {
                "type": ["integer", "null"],
                "description": "Estimated first year to drink the wine.",
            },
            "drink_until_year": {
                "type": ["integer", "null"],
                "description": "Estimated last year to drink the wine.",
            },
            "confidence": {
                "type": "string",
                "enum": ["low", "medium", "high"],
            },
            "rationale": {
                "type": "string",
                "description": "Short explanation of the estimate.",
            },
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "url": {"type": ["string", "null"]},
                        "note": {"type": ["string", "null"]},
                    },
                    "required": ["title", "url", "note"],
                    "additionalProperties": False,
                },
            },
        },
        "required": [
            "drink_from_year",
            "drink_until_year",
            "confidence",
            "rationale",
            "sources",
        ],
        "additionalProperties": False,
    }


def _payload_to_estimate(
    *,
    wine: WineIdentity,
    model: str,
    payload: dict[str, Any],
) -> AIWindowEstimate:
    drink_from_year = payload["drink_from_year"]
    drink_until_year = payload["drink_until_year"]
    confidence = str(payload["confidence"]).strip().lower()

    _validate_window(
        drink_from_year=drink_from_year,
        drink_until_year=drink_until_year,
    )
    _validate_confidence(confidence)

    sources = tuple(
        AIWindowSource(
            title=str(source["title"]).strip(),
            url=_optional_text(source.get("url")),
            note=_optional_text(source.get("note")),
        )
        for source in payload["sources"]
    )

    return AIWindowEstimate(
        wine=wine,
        source_name="AI estimate (OpenAI)",
        model=model,
        drink_from_year=drink_from_year,
        drink_until_year=drink_until_year,
        confidence=confidence,
        rationale=str(payload["rationale"]).strip(),
        sources=sources,
    )


def _validate_window(
    *,
    drink_from_year: int | None,
    drink_until_year: int | None,
) -> None:
    if drink_from_year is None and drink_until_year is None:
        raise ValueError("AI estimate did not return a drinking window.")

    if (
        drink_from_year is not None
        and drink_until_year is not None
        and drink_from_year > drink_until_year
    ):
        raise ValueError(
            "AI estimate returned an invalid drinking window: "
            "drink_from_year is after drink_until_year."
        )


def _validate_confidence(confidence: str) -> None:
    if confidence not in VALID_CONFIDENCES:
        raise ValueError("AI estimate returned invalid confidence.")


def _optional_text(value: object) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()

    if not normalized:
        return None

    return normalized


def _estimate_notes(estimate: AIWindowEstimate) -> str:
    source_lines = [
        _format_source_note(index, source) for index, source in enumerate(estimate.sources, start=1)
    ]

    sources_text = "\n".join(source_lines) if source_lines else "No sources returned."

    return f"AI model: {estimate.model}\nRationale: {estimate.rationale}\nSources:\n{sources_text}"


def _format_source_note(index: int, source: AIWindowSource) -> str:
    parts = [f"{index}. {source.title}"]

    if source.url is not None:
        parts.append(f"URL: {source.url}")

    if source.note is not None:
        parts.append(f"Note: {source.note}")

    return " | ".join(parts)
