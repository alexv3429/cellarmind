from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, urlparse
from urllib.request import Request, urlopen

from cellarmind.storage.reference_windows_fetcher import (
    ReferenceWindowCandidate,
    fetch_reference_window_candidate,
)
from cellarmind.storage.sqlite import connect_database


@dataclass(frozen=True)
class WineSearchIdentity:
    wine_id: int
    producer: str
    cuvee: str
    vintage: str
    appellation: str
    color: str


@dataclass(frozen=True)
class ReferenceWindowSearchResult:
    title: str
    url: str
    snippet: str | None
    candidate: ReferenceWindowCandidate | None
    error: str | None


@dataclass(frozen=True)
class ReferenceWindowSearchReport:
    wine: WineSearchIdentity
    query: str
    results: tuple[ReferenceWindowSearchResult, ...]


def search_reference_window_sources(
    database_path: Path,
    *,
    wine_id: int,
    limit: int = 5,
    fetch_candidates: bool = False,
    timeout_seconds: float = 15.0,
) -> ReferenceWindowSearchReport:
    if not database_path.exists():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    if limit < 1:
        raise ValueError("Limit must be at least 1.")

    with connect_database(database_path) as connection:
        wine = _get_wine_identity(connection, wine_id=wine_id)

    query = build_reference_window_search_query(wine)

    raw_results = search_web_for_reference_sources(
        query=query,
        limit=limit,
        timeout_seconds=timeout_seconds,
    )

    results: list[ReferenceWindowSearchResult] = []

    for result in raw_results:
        candidate: ReferenceWindowCandidate | None = None
        error: str | None = None

        if fetch_candidates:
            try:
                candidate = fetch_reference_window_candidate(
                    source_url=result.url,
                    source_name=result.title,
                    timeout_seconds=timeout_seconds,
                )
            except ValueError as exc:
                error = str(exc)

        results.append(
            ReferenceWindowSearchResult(
                title=result.title,
                url=result.url,
                snippet=result.snippet,
                candidate=candidate,
                error=error,
            )
        )

    return ReferenceWindowSearchReport(
        wine=wine,
        query=query,
        results=tuple(results),
    )


def build_reference_window_search_query(wine: WineSearchIdentity) -> str:
    parts = [
        wine.producer,
        wine.cuvee,
        wine.vintage,
        wine.appellation,
        "drinking window",
    ]

    return " ".join(part for part in parts if part and part != "NV")


@dataclass(frozen=True)
class _RawSearchResult:
    title: str
    url: str
    snippet: str | None


def search_web_for_reference_sources(
    *,
    query: str,
    limit: int,
    timeout_seconds: float,
) -> tuple[_RawSearchResult, ...]:
    search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"

    html = _fetch_search_html(
        search_url,
        timeout_seconds=timeout_seconds,
    )

    parser = _DuckDuckGoHTMLParser()
    parser.feed(html)

    deduped: list[_RawSearchResult] = []
    seen_urls: set[str] = set()

    for result in parser.results:
        normalized_url = _normalize_result_url(result.url)

        if not normalized_url or normalized_url in seen_urls:
            continue

        seen_urls.add(normalized_url)

        deduped.append(
            _RawSearchResult(
                title=result.title,
                url=normalized_url,
                snippet=result.snippet,
            )
        )

        if len(deduped) >= limit:
            break

    return tuple(deduped)


def _get_wine_identity(connection, *, wine_id: int) -> WineSearchIdentity:
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

    return WineSearchIdentity(
        wine_id=int(row["id"]),
        producer=row["producer"],
        cuvee=row["cuvee"],
        vintage=row["vintage"],
        appellation=row["appellation"],
        color=row["color"],
    )


def _fetch_search_html(
    url: str,
    *,
    timeout_seconds: float,
) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": ("CellarMind/0.1 (reference-window source search; manual user request)")
        },
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read(1_000_000).decode(charset, errors="replace")
    except HTTPError as error:
        raise ValueError(f"Could not search online sources: HTTP {error.code}") from error
    except URLError as error:
        raise ValueError(f"Could not search online sources: {error.reason}") from error
    except TimeoutError as error:
        raise ValueError("Could not search online sources: request timed out.") from error


def _normalize_result_url(url: str) -> str | None:
    if not url:
        return None

    if url.startswith("/l/"):
        return _normalize_result_url(f"https://duckduckgo.com{url}")

    if url.startswith("//duckduckgo.com/l/"):
        return _normalize_result_url(f"https:{url}")

    parsed = urlparse(url)

    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        params = parse_qs(parsed.query)
        target = params.get("uddg", [None])[0]

        if target:
            return target

        return None

    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return url

    return None


class _DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[_RawSearchResult] = []
        self._in_result_link = False
        self._current_href: str | None = None
        self._current_title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_dict = dict(attrs)

        if tag == "a" and "result__a" in attrs_dict.get("class", ""):
            self._in_result_link = True
            self._current_href = attrs_dict.get("href")
            self._current_title_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_result_link:
            title = " ".join(self._current_title_parts).strip()

            if title and self._current_href:
                self.results.append(
                    _RawSearchResult(
                        title=title,
                        url=self._current_href,
                        snippet=None,
                    )
                )

            self._in_result_link = False
            self._current_href = None
            self._current_title_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_result_link and data.strip():
            self._current_title_parts.append(data.strip())
