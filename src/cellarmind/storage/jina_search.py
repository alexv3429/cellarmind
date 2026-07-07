"""Jina Search helpers for AI evidence gathering."""

from __future__ import annotations

from dataclasses import dataclass
from os import environ
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

JINA_SEARCH_BASE_URL_ENV = "CELLARMIND_JINA_SEARCH_BASE_URL"
DEFAULT_JINA_SEARCH_BASE_URL = "https://s.jina.ai"
JINA_SEARCH_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class JinaSearchResult:
    title: str
    url: str
    snippet: str | None


def search_jina_for_reference_sources(
    *,
    query: str,
    limit: int,
    timeout_seconds: float = JINA_SEARCH_TIMEOUT_SECONDS,
) -> tuple[JinaSearchResult, ...]:
    """Search with Jina Reader Search and return URL/title/snippet candidates."""
    body = _read_jina_search(query=query, timeout_seconds=timeout_seconds)
    return _parse_jina_search_results(body, limit=limit)


def _read_jina_search(*, query: str, timeout_seconds: float) -> str:
    search_url = _jina_search_url(query)
    request = Request(
        search_url,
        headers={
            "Accept": "text/plain",
            "User-Agent": "CellarMind/0.1 (Jina Search evidence gathering)",
        },
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read()
    except HTTPError as error:
        raise ValueError(f"Could not search with Jina: HTTP {error.code}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise ValueError(f"Could not search with Jina: {error}") from error

    return body.decode("utf-8", errors="replace")


def _jina_search_url(query: str) -> str:
    base_url = environ.get(JINA_SEARCH_BASE_URL_ENV, DEFAULT_JINA_SEARCH_BASE_URL)
    return f"{base_url.rstrip('/')}/{quote(query)}"


def _parse_jina_search_results(body: str, *, limit: int) -> tuple[JinaSearchResult, ...]:
    """Parse common markdown-ish Jina Search response shapes."""
    results = _parse_title_url_blocks(body)

    if not results:
        results = _parse_markdown_link_blocks(body)

    deduped: list[JinaSearchResult] = []
    seen_urls: set[str] = set()

    for result in results:
        if result.url in seen_urls:
            continue

        deduped.append(result)
        seen_urls.add(result.url)

        if len(deduped) >= limit:
            break

    return tuple(deduped)


def _parse_title_url_blocks(body: str) -> list[JinaSearchResult]:
    results: list[JinaSearchResult] = []
    current_title: str | None = None
    current_url: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_title, current_url, current_lines

        if current_title and current_url:
            snippet = "".join(current_lines).strip() or None
            results.append(
                JinaSearchResult(
                    title=current_title,
                    url=current_url,
                    snippet=snippet,
                )
            )

        current_title = None
        current_url = None
        current_lines = []

    for raw_line in body.splitlines():
        line = raw_line.strip()

        if line.startswith("Title: "):
            flush()
            current_title = line.removeprefix("Title: ").strip()
            continue

        if line.startswith("URL Source: "):
            current_url = line.removeprefix("URL Source: ").strip()
            continue

        if line.startswith("URL: ") and current_url is None:
            current_url = line.removeprefix("URL: ").strip()
            continue

        if (current_title or current_url) and line:
            current_lines.append(line)

    flush()
    return results


def _parse_markdown_link_blocks(body: str) -> list[JinaSearchResult]:
    results: list[JinaSearchResult] = []

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if "](" not in line or ")" not in line:
            continue

        before, after = line.split("](", 1)
        url, *_rest = after.split(")", 1)
        title = before.rsplit("[", 1)[-1].strip()

        if title and url.startswith(("http://", "https://")):
            results.append(JinaSearchResult(title=title, url=url, snippet=None))

    return results
