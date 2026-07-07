from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ddgs import DDGS

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
    query_override: str | None = None,
) -> ReferenceWindowSearchReport:
    if not database_path.exists():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    if limit < 1:
        raise ValueError("Limit must be at least 1.")

    with connect_database(database_path) as connection:
        wine = _get_wine_identity(connection, wine_id=wine_id)

    query = (
        query_override.strip()
        if query_override is not None and query_override.strip()
        else build_reference_window_search_query(wine)
    )

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
    return _search_ddgs(
        query=query,
        limit=limit,
        timeout_seconds=timeout_seconds,
    )


def _search_ddgs(
    *,
    query: str,
    limit: int,
    timeout_seconds: float,
) -> tuple[_RawSearchResult, ...]:
    results: list[_RawSearchResult] = []

    try:
        with DDGS(timeout=timeout_seconds) as ddgs:
            for result in ddgs.text(
                query,
                max_results=limit,
            ):
                title = str(result.get("title") or "").strip()
                url = str(result.get("href") or result.get("url") or "").strip()
                snippet = str(result.get("body") or "").strip() or None

                if not title or not url:
                    continue

                results.append(
                    _RawSearchResult(
                        title=title,
                        url=url,
                        snippet=snippet,
                    )
                )

                if len(results) >= limit:
                    break
    except Exception as error:
        raise ValueError(f"Could not search online sources: {error}") from error

    return tuple(results)


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
