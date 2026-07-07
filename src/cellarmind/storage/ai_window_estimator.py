from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from openai import OpenAI, OpenAIError

from cellarmind.storage.reference_window_search import search_web_for_reference_sources
from cellarmind.storage.reference_windows import (
    ReferenceDrinkingWindow,
    add_reference_window,
)
from cellarmind.storage.sqlite import connect_database

OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_MODEL_ENV = "CELLARMIND_OPENAI_MODEL"
DEFAULT_OPENAI_MODEL = "gpt-5.5"

OLLAMA_HOST_ENV = "CELLARMIND_OLLAMA_HOST"
OLLAMA_MODEL_ENV = "CELLARMIND_OLLAMA_MODEL"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3.1"

JINA_READER_BASE_URL_ENV = "CELLARMIND_JINA_READER_BASE_URL"
DEFAULT_JINA_READER_BASE_URL = "https://r.jina.ai"

VALID_CONFIDENCES = {"low", "medium", "high"}
VALID_PROVIDERS = {"openai", "ollama"}
VALID_WEB_READERS = {"jina", "none"}

SEARCH_TIMEOUT_SECONDS = 20.0
JINA_TIMEOUT_SECONDS = 30.0
OLLAMA_TIMEOUT_SECONDS = 120.0
EVIDENCE_CONTENT_CHAR_LIMIT = 3500
EVIDENCE_TOTAL_CHAR_LIMIT = 14000


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
class AIWindowEvidence:
    title: str
    url: str
    snippet: str | None
    content: str | None


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
    provider: str
    model: str
    web_search_enabled: bool
    web_search_used: bool
    web_reader: str | None
    drink_from_year: int | None
    drink_until_year: int | None
    confidence: str
    rationale: str
    sources: tuple[AIWindowSource, ...]
    evidence: tuple[AIWindowEvidence, ...]
    usage: AIWindowUsage | None


def estimate_ai_drinking_window(
    database_path: Path,
    *,
    wine_id: int,
    provider: str = "openai",
    model: str | None = None,
    use_web_search: bool = True,
    web_reader: str = "jina",
    evidence_limit: int = 5,
    ollama_host: str | None = None,
) -> AIWindowEstimate:
    if not database_path.exists():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    resolved_provider = _normalize_provider(provider)
    resolved_model = _resolve_model(model, provider=resolved_provider)
    resolved_web_reader = _normalize_web_reader(web_reader)

    with connect_database(database_path) as connection:
        wine = _get_wine_identity(connection, wine_id=wine_id)

    evidence: tuple[AIWindowEvidence, ...] = ()

    if resolved_provider == "openai":
        provider_response = _call_openai_estimate(
            wine=wine,
            model=resolved_model,
            use_web_search=use_web_search,
        )
    elif resolved_provider == "ollama":
        if use_web_search:
            evidence = _gather_web_evidence(
                wine=wine,
                limit=evidence_limit,
                web_reader=resolved_web_reader,
            )

            if not evidence:
                raise ValueError("Could not gather web evidence for the Ollama estimate.")

        provider_response = _call_ollama_estimate(
            wine=wine,
            model=resolved_model,
            use_web_search=use_web_search,
            evidence=evidence,
            ollama_host=ollama_host,
        )
    else:
        raise ValueError(f"Unsupported AI provider: {provider}")

    return _payload_to_estimate(
        wine=wine,
        provider=resolved_provider,
        model=resolved_model,
        use_web_search=use_web_search,
        web_reader=resolved_web_reader if resolved_provider == "ollama" else None,
        evidence=evidence,
        provider_response=provider_response,
    )


def estimate_and_add_ai_reference_window(
    database_path: Path,
    *,
    wine_id: int,
    provider: str = "openai",
    model: str | None = None,
    use_web_search: bool = True,
    web_reader: str = "jina",
    evidence_limit: int = 5,
    ollama_host: str | None = None,
) -> ReferenceDrinkingWindow:
    estimate = estimate_ai_drinking_window(
        database_path,
        wine_id=wine_id,
        provider=provider,
        model=model,
        use_web_search=use_web_search,
        web_reader=web_reader,
        evidence_limit=evidence_limit,
        ollama_host=ollama_host,
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


def _normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower()

    if normalized not in VALID_PROVIDERS:
        raise ValueError("AI provider must be one of: openai, ollama.")

    return normalized


def _normalize_web_reader(web_reader: str) -> str:
    normalized = web_reader.strip().lower()

    if normalized not in VALID_WEB_READERS:
        raise ValueError("AI web reader must be one of: jina, none.")

    return normalized


def _resolve_model(model: str | None, *, provider: str) -> str:
    if model is not None and model.strip():
        return model.strip()

    if provider == "openai":
        configured_model = os.environ.get(OPENAI_MODEL_ENV)

        if configured_model is not None and configured_model.strip():
            return configured_model.strip()

        return DEFAULT_OPENAI_MODEL

    configured_model = os.environ.get(OLLAMA_MODEL_ENV)

    if configured_model is not None and configured_model.strip():
        return configured_model.strip()

    return DEFAULT_OLLAMA_MODEL


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
        "input": _estimate_prompt(
            wine,
            provider="openai",
            use_web_search=use_web_search,
            evidence=(),
        ),
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


def _call_ollama_estimate(
    *,
    wine: WineIdentity,
    model: str,
    use_web_search: bool,
    evidence: tuple[AIWindowEvidence, ...],
    ollama_host: str | None,
) -> OpenAIEstimateResponse:
    host = _resolve_ollama_host(ollama_host)
    url = f"{host.rstrip('/')}/api/chat"

    request_body = {
        "model": model,
        "stream": False,
        "format": _estimate_schema(),
        "options": {
            "temperature": 0.1,
        },
        "messages": [
            {
                "role": "system",
                "content": (
                    "You estimate wine drinking windows. "
                    "Return only valid JSON matching the requested schema. "
                    "Do not use markdown fences."
                ),
            },
            {
                "role": "user",
                "content": _estimate_prompt(
                    wine,
                    provider="ollama",
                    use_web_search=use_web_search,
                    evidence=evidence,
                ),
            },
        ],
    }

    response = _post_json(
        url,
        request_body,
        timeout_seconds=OLLAMA_TIMEOUT_SECONDS,
    )

    message = response.get("message")

    if not isinstance(message, dict):
        raise ValueError("Ollama response did not contain a message.")

    content = message.get("content")

    if not isinstance(content, str) or not content.strip():
        raise ValueError("Ollama response did not contain JSON content.")

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError("Ollama response was not valid JSON.") from error

    return OpenAIEstimateResponse(
        payload=payload,
        usage=_ollama_usage(response),
        web_search_used=bool(evidence),
    )


def _resolve_ollama_host(ollama_host: str | None) -> str:
    if ollama_host is not None and ollama_host.strip():
        return ollama_host.strip()

    configured_host = os.environ.get(OLLAMA_HOST_ENV)

    if configured_host is not None and configured_host.strip():
        return configured_host.strip()

    return DEFAULT_OLLAMA_HOST


def _gather_web_evidence(
    *,
    wine: WineIdentity,
    limit: int,
    web_reader: str,
) -> tuple[AIWindowEvidence, ...]:
    query = _search_query_for_wine(wine)
    raw_results = search_web_for_reference_sources(
        query=query,
        limit=limit,
        timeout_seconds=SEARCH_TIMEOUT_SECONDS,
    )

    evidence: list[AIWindowEvidence] = []
    total_chars = 0

    for result in raw_results:
        content: str | None = None

        if web_reader == "jina":
            try:
                content = _read_url_with_jina(result.url)
            except ValueError:
                content = None

        content = _limit_text(content, EVIDENCE_CONTENT_CHAR_LIMIT)
        snippet = _limit_text(result.snippet, EVIDENCE_CONTENT_CHAR_LIMIT)

        if content is None and snippet is None:
            continue

        evidence_item = AIWindowEvidence(
            title=result.title,
            url=result.url,
            snippet=snippet,
            content=content,
        )

        evidence.append(evidence_item)
        total_chars += len(_evidence_text(evidence_item))

        if total_chars >= EVIDENCE_TOTAL_CHAR_LIMIT:
            break

    return tuple(evidence)


def _search_query_for_wine(wine: WineIdentity) -> str:
    return " ".join(
        part
        for part in (
            wine.producer,
            wine.cuvee,
            wine.vintage,
            wine.appellation,
            wine.color,
            "drinking window drink from until",
        )
        if part
    )


def _read_url_with_jina(source_url: str) -> str:
    reader_url = _jina_reader_url(source_url)
    request = Request(
        reader_url,
        headers={
            "Accept": "text/plain",
            "User-Agent": "CellarMind/0.1 (Jina Reader evidence gathering)",
        },
    )

    try:
        with urlopen(request, timeout=JINA_TIMEOUT_SECONDS) as response:
            body = response.read()
    except HTTPError as error:
        raise ValueError(f"Could not read URL with Jina: HTTP {error.code}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise ValueError(f"Could not read URL with Jina: {error}") from error

    return body.decode("utf-8", errors="replace").strip()


def _jina_reader_url(source_url: str) -> str:
    base_url = os.environ.get(JINA_READER_BASE_URL_ENV, DEFAULT_JINA_READER_BASE_URL)
    return f"{base_url.rstrip('/')}/{source_url}"


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "CellarMind/0.1",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read()
    except HTTPError as error:
        raise ValueError(f"Could not call Ollama: HTTP {error.code}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise ValueError(f"Could not call Ollama: {error}") from error

    try:
        parsed = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("Ollama returned invalid JSON.") from error

    if not isinstance(parsed, dict):
        raise ValueError("Ollama returned an unexpected response.")

    return parsed


def _estimate_prompt(
    wine: WineIdentity,
    *,
    provider: str,
    use_web_search: bool,
    evidence: tuple[AIWindowEvidence, ...],
) -> str:
    web_rule = (
        "Use web search before answering. Prefer cited, source-backed information."
        if use_web_search and provider == "openai"
        else "Do not use web search. Estimate from general wine knowledge only."
    )

    if provider == "ollama" and evidence:
        web_rule = (
            "Use only the evidence supplied below plus general wine knowledge. "
            "Prefer explicit drinking windows from the evidence when available."
        )

    evidence_text = _format_evidence_for_prompt(evidence)

    return f"""
Estimate a drinking window for this wine.

Wine:
- producer: {wine.producer}
- cuvee: {wine.cuvee}
- vintage: {wine.vintage}
- appellation: {wine.appellation}
- color: {wine.color}

Rules:
- {web_rule}
- If sources disagree, choose a conservative practical cellar window.
- If you are uncertain, use confidence "low".
- Use null when a boundary cannot be estimated.
- Do not invent URLs.
- The estimate is advisory and must not claim certainty.
- Return only the structured JSON required by the schema.

{evidence_text}
""".strip()


def _format_evidence_for_prompt(evidence: tuple[AIWindowEvidence, ...]) -> str:
    if not evidence:
        return ""

    sections = ["Evidence:"]

    for index, item in enumerate(evidence, start=1):
        text = _evidence_text(item)
        sections.append(
            f"""
[{index}] {item.title}
URL: {item.url}
{text}
""".strip()
        )

    return "\n\n".join(sections)


def _evidence_text(evidence: AIWindowEvidence) -> str:
    parts: list[str] = []

    if evidence.snippet:
        parts.append(f"Snippet:\n{evidence.snippet}")

    if evidence.content:
        parts.append(f"Content:\n{evidence.content}")

    return "\n\n".join(parts)


def _limit_text(value: str | None, max_chars: int) -> str | None:
    if value is None:
        return None

    normalized = value.strip()

    if not normalized:
        return None

    if len(normalized) <= max_chars:
        return normalized

    return normalized[:max_chars].rstrip() + "…"


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
    provider: str,
    model: str,
    use_web_search: bool,
    web_reader: str | None,
    evidence: tuple[AIWindowEvidence, ...],
    provider_response: OpenAIEstimateResponse,
) -> AIWindowEstimate:
    payload = provider_response.payload

    drink_from_year = payload["drink_from_year"]
    drink_until_year = payload["drink_until_year"]
    confidence = str(payload["confidence"]).strip().lower()

    _validate_window(
        drink_from_year=drink_from_year,
        drink_until_year=drink_until_year,
    )
    _validate_confidence(confidence)

    if provider == "openai" and use_web_search and not provider_response.web_search_used:
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
        source_name=_source_name_for_provider(provider),
        provider=provider,
        model=model,
        web_search_enabled=use_web_search,
        web_search_used=provider_response.web_search_used,
        web_reader=web_reader,
        drink_from_year=drink_from_year,
        drink_until_year=drink_until_year,
        confidence=confidence,
        rationale=str(payload["rationale"]).strip(),
        sources=sources,
        evidence=evidence,
        usage=provider_response.usage,
    )


def _source_name_for_provider(provider: str) -> str:
    if provider == "openai":
        return "AI estimate (OpenAI)"

    if provider == "ollama":
        return "AI estimate (local)"

    raise ValueError(f"Unsupported AI provider: {provider}")


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


def _ollama_usage(response: dict[str, Any]) -> AIWindowUsage | None:
    input_tokens = _optional_int(response.get("prompt_eval_count"))
    output_tokens = _optional_int(response.get("eval_count"))

    if input_tokens is None and output_tokens is None:
        return None

    total_tokens = None

    if input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens

    return AIWindowUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
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

    evidence_lines = [
        _format_evidence_note(index, evidence)
        for index, evidence in enumerate(estimate.evidence, start=1)
    ]

    sources_text = "\n".join(source_lines) if source_lines else "No sources returned."
    evidence_text = "\n".join(evidence_lines) if evidence_lines else "No gathered evidence stored."

    return (
        f"AI model: {estimate.model}\n"
        f"Provider: {_provider_display_name(estimate.provider)}\n"
        f"Source name: {estimate.source_name}\n"
        f"Web search enabled: {estimate.web_search_enabled}\n"
        f"Web search used: {estimate.web_search_used}\n"
        f"Web reader: {estimate.web_reader or 'none'}\n"
        f"{_format_usage_notes(estimate.usage)}"
        f"Rationale: {estimate.rationale}\n"
        f"Sources:\n{sources_text}\n"
        f"Gathered evidence:\n{evidence_text}"
    )


def _provider_display_name(provider: str) -> str:
    if provider == "openai":
        return "OpenAI"

    return provider


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


def _format_evidence_note(index: int, evidence: AIWindowEvidence) -> str:
    return f"{index}. {evidence.title} | URL: {evidence.url}"
