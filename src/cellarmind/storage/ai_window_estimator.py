from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection
from typing import Any

from openai import OpenAI, OpenAIError

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
class AIWindowUsage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True)
class OpenAIEstimateResponse:
    payload: dict[str, Any]
    usage: AIWindowUsage | None
    web_search_used: bool


@dataclass(frozen=True)
class AIWindowEstimate:
    wine: WineIdentity
    source_name: str
    model: str
    web_search_enabled: bool
    web_search_used: bool
    drink_from_year: int | None
    drink_until_year: int | None
    confidence: str
    rationale: str
    sources: tuple[AIWindowSource, ...]
    usage: AIWindowUsage | None


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

    openai_response = _call_openai_estimate(
        wine=wine,
        model=resolved_model,
        use_web_search=use_web_search,
    )

    return _payload_to_estimate(
        wine=wine,
        model=resolved_model,
        use_web_search=use_web_search,
        openai_response=openai_response,
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

    return add_ai_reference_window_from_estimate(
        database_path,
        estimate=estimate,
    )


def add_ai_reference_window_from_estimate(
    database_path: Path,
    *,
    estimate: AIWindowEstimate,
) -> ReferenceDrinkingWindow:
    return add_reference_window(
        database_path,
        wine_id=estimate.wine.wine_id,
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
) -> OpenAIEstimateResponse:
    if not os.environ.get(OPENAI_API_KEY_ENV):
        raise ValueError(
            "OPENAI_API_KEY is not set. Set it before using AI drinking-window estimates."
        )

    client = OpenAI()

    request: dict[str, Any] = {
        "model": model,
        "tools": [],
        "input": _estimate_prompt(wine, use_web_search=use_web_search),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "drinking_window_estimate",
                "strict": True,
                "schema": _estimate_schema(),
            }
        },
    }

    if use_web_search:
        request["tools"] = [{"type": "web_search"}]
        request["tool_choice"] = "required"

    try:
        response = client.responses.create(**request)
    except OpenAIError as error:
        raise ValueError(f"OpenAI estimate failed: {error}") from error

    return OpenAIEstimateResponse(
        payload=json.loads(response.output_text),
        usage=_response_usage(response),
        web_search_used=_response_used_web_search(response),
    )


def _estimate_prompt(wine: WineIdentity, *, use_web_search: bool) -> str:
    web_rule = (
        "Use web search before answering. Prefer cited, source-backed information."
        if use_web_search
        else "Do not use web search. Estimate from general wine knowledge only."
    )

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
- {web_rule}
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
    use_web_search: bool,
    openai_response: OpenAIEstimateResponse,
) -> AIWindowEstimate:
    payload = openai_response.payload

    drink_from_year = payload["drink_from_year"]
    drink_until_year = payload["drink_until_year"]
    confidence = str(payload["confidence"]).strip().lower()

    _validate_window(
        drink_from_year=drink_from_year,
        drink_until_year=drink_until_year,
    )
    _validate_confidence(confidence)

    if use_web_search and not openai_response.web_search_used:
        raise ValueError("OpenAI did not use web search even though web search was required.")

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
        web_search_enabled=use_web_search,
        web_search_used=openai_response.web_search_used,
        drink_from_year=drink_from_year,
        drink_until_year=drink_until_year,
        confidence=confidence,
        rationale=str(payload["rationale"]).strip(),
        sources=sources,
        usage=openai_response.usage,
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


def _response_used_web_search(response: object) -> bool:
    output = getattr(response, "output", None)

    if output is None:
        return False

    return any(_get_output_item_type(item) == "web_search_call" for item in output)


def _get_output_item_type(item: object) -> str | None:
    value = item.get("type") if isinstance(item, dict) else getattr(item, "type", None)

    if value is None:
        return None

    return str(value)


def _response_usage(response: object) -> AIWindowUsage | None:
    usage = getattr(response, "usage", None)

    if usage is None:
        return None

    return AIWindowUsage(
        input_tokens=_optional_int(_get_usage_value(usage, "input_tokens")),
        output_tokens=_optional_int(_get_usage_value(usage, "output_tokens")),
        total_tokens=_optional_int(_get_usage_value(usage, "total_tokens")),
    )


def _get_usage_value(usage: object, key: str) -> object:
    if isinstance(usage, dict):
        return usage.get(key)

    return getattr(usage, key, None)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None

    return int(value)


def _estimate_notes(estimate: AIWindowEstimate) -> str:
    source_lines = [
        _format_source_note(index, source) for index, source in enumerate(estimate.sources, start=1)
    ]

    sources_text = "\n".join(source_lines) if source_lines else "No sources returned."

    return (
        f"AI model: {estimate.model}\n"
        "Provider: OpenAI\n"
        f"Web search enabled: {estimate.web_search_enabled}\n"
        f"Web search used: {estimate.web_search_used}\n"
        f"{_format_usage_notes(estimate.usage)}"
        f"Rationale: {estimate.rationale}\n"
        f"Sources:\n{sources_text}"
    )


def _format_usage_notes(usage: AIWindowUsage | None) -> str:
    if usage is None:
        return "Usage: unavailable\n"

    return (
        "Usage: "
        f"input_tokens={usage.input_tokens}, "
        f"output_tokens={usage.output_tokens}, "
        f"total_tokens={usage.total_tokens}\n"
    )


def _format_source_note(index: int, source: AIWindowSource) -> str:
    parts = [f"{index}. {source.title}"]

    if source.url is not None:
        parts.append(f"URL: {source.url}")

    if source.note is not None:
        parts.append(f"Note: {source.note}")

    return " | ".join(parts)
