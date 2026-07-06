from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from cellarmind.storage.reference_windows import (
    ReferenceDrinkingWindow,
    add_reference_window,
)

VALID_CONFIDENCES = {"low", "medium", "high"}

YEAR_PATTERN = r"(?:19|20)\d{2}"

RANGE_PATTERNS = (
    re.compile(
        rf"""
        (?P<context>
            (?:
                drinking\s+window|
                drink\s+window|
                window|
                best\s+from|
                best|
                drink|
                drinking|
                maturity|
                mature|
                cellar|
                hold|
                apog[eé]e|
                [aà]\s+boire|
                garde
            )
            [^.\n]{{0,160}}?
        )
        (?P<from>{YEAR_PATTERN})
        \s*
        (?:
            [-–—/]|
            to|
            until|
            through|
            [aà]|
            au|
            jusqu['’]?[aà]
        )
        \s*
        (?P<until>{YEAR_PATTERN})
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    re.compile(
        rf"""
        (?P<from>{YEAR_PATTERN})
        \s*
        (?:
            [-–—/]|
            to|
            until|
            through|
            [aà]|
            au|
            jusqu['’]?[aà]
        )
        \s*
        (?P<until>{YEAR_PATTERN})
        (?P<context>
            [^.\n]{{0,160}}?
            (?:
                drinking\s+window|
                drink\s+window|
                window|
                drink|
                drinking|
                maturity|
                mature|
                cellar|
                hold|
                apog[eé]e|
                [aà]\s+boire|
                garde
            )
        )
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
)

UNTIL_PATTERNS = (
    re.compile(
        rf"""
        (?:
            drink\s+until|
            drinking\s+until|
            best\s+before|
            hold\s+until|
            cellar\s+until|
            [aà]\s+boire\s+jusqu['’]?[aà]?|
            garde\s+jusqu['’]?[aà]?
        )
        [^.\n0-9]{{0,80}}
        (?P<until>{YEAR_PATTERN})
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
)

FROM_PATTERNS = (
    re.compile(
        rf"""
        (?:
            drink\s+from|
            drinking\s+from|
            best\s+from|
            ready\s+from|
            [aà]\s+boire\s+[aà]\s+partir\s+de
        )
        [^.\n0-9]{{0,80}}
        (?P<from>{YEAR_PATTERN})
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
)


@dataclass(frozen=True)
class ReferenceWindowCandidate:
    source_name: str
    source_url: str
    drink_from_year: int | None
    drink_until_year: int | None
    confidence: str
    evidence_text: str


def fetch_reference_window_candidate(
    *,
    source_url: str,
    source_name: str | None = None,
    timeout_seconds: float = 15.0,
) -> ReferenceWindowCandidate:
    normalized_url = _validate_url(source_url)
    resolved_source_name = _normalize_source_name(
        source_name,
        fallback_url=normalized_url,
    )

    html = fetch_url_text(
        normalized_url,
        timeout_seconds=timeout_seconds,
    )
    text = html_to_text(html)

    extracted = extract_reference_window_from_text(text)

    return ReferenceWindowCandidate(
        source_name=resolved_source_name,
        source_url=normalized_url,
        drink_from_year=extracted.drink_from_year,
        drink_until_year=extracted.drink_until_year,
        confidence=extracted.confidence,
        evidence_text=extracted.evidence_text,
    )


def fetch_and_add_reference_window(
    database_path: Path,
    *,
    wine_id: int,
    source_url: str,
    source_name: str | None = None,
    confidence: str | None = None,
    timeout_seconds: float = 15.0,
) -> ReferenceDrinkingWindow:
    candidate = fetch_reference_window_candidate(
        source_url=source_url,
        source_name=source_name,
        timeout_seconds=timeout_seconds,
    )

    resolved_confidence = (
        confidence.strip().lower() if confidence is not None else candidate.confidence
    )

    if resolved_confidence not in VALID_CONFIDENCES:
        raise ValueError("Confidence must be one of: low, medium, high.")

    return add_reference_window(
        database_path,
        wine_id=wine_id,
        source_name=candidate.source_name,
        source_url=candidate.source_url,
        drink_from_year=candidate.drink_from_year,
        drink_until_year=candidate.drink_until_year,
        confidence=resolved_confidence,
        notes=f"Extracted evidence: {candidate.evidence_text}",
    )


@dataclass(frozen=True)
class _ExtractedReferenceWindow:
    drink_from_year: int | None
    drink_until_year: int | None
    confidence: str
    evidence_text: str


def extract_reference_window_from_text(text: str) -> _ExtractedReferenceWindow:
    normalized_text = normalize_text(text)

    for pattern in RANGE_PATTERNS:
        for match in pattern.finditer(normalized_text):
            drink_from_year = int(match.group("from"))
            drink_until_year = int(match.group("until"))

            if _is_valid_window(
                drink_from_year=drink_from_year,
                drink_until_year=drink_until_year,
            ):
                return _ExtractedReferenceWindow(
                    drink_from_year=drink_from_year,
                    drink_until_year=drink_until_year,
                    confidence="medium",
                    evidence_text=_shorten_evidence(match.group(0)),
                )

    for pattern in UNTIL_PATTERNS:
        match = pattern.search(normalized_text)

        if match is not None:
            return _ExtractedReferenceWindow(
                drink_from_year=None,
                drink_until_year=int(match.group("until")),
                confidence="low",
                evidence_text=_shorten_evidence(match.group(0)),
            )

    for pattern in FROM_PATTERNS:
        match = pattern.search(normalized_text)

        if match is not None:
            return _ExtractedReferenceWindow(
                drink_from_year=int(match.group("from")),
                drink_until_year=None,
                confidence="low",
                evidence_text=_shorten_evidence(match.group(0)),
            )

    raise ValueError("No drinking window could be extracted from the page.")


def fetch_url_text(
    source_url: str,
    *,
    timeout_seconds: float,
    max_bytes: int = 2_000_000,
) -> str:
    request = Request(
        source_url,
        headers={
            "User-Agent": ("CellarMind/0.1 (reference-window extraction; manual user request)")
        },
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            raw = response.read(max_bytes + 1)
    except HTTPError as error:
        raise ValueError(f"Could not fetch URL: HTTP {error.code}") from error
    except URLError as error:
        raise ValueError(f"Could not fetch URL: {error.reason}") from error
    except TimeoutError as error:
        raise ValueError("Could not fetch URL: request timed out.") from error

    if len(raw) > max_bytes:
        raw = raw[:max_bytes]

    return raw.decode(charset, errors="replace")


def html_to_text(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return normalize_text(" ".join(parser.parts))


def normalize_text(text: str) -> str:
    normalized = text.replace("\u00a0", " ")
    normalized = normalized.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", normalized).strip()


def _validate_url(source_url: str) -> str:
    normalized = source_url.strip()
    parsed = urlparse(normalized)

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("source_url must be an http or https URL.")

    return normalized


def _normalize_source_name(
    source_name: str | None,
    *,
    fallback_url: str,
) -> str:
    if source_name is not None and source_name.strip():
        return source_name.strip()

    host = urlparse(fallback_url).netloc.lower()

    if host.startswith("www."):
        host = host[4:]

    return host or "Internet reference"


def _is_valid_window(
    *,
    drink_from_year: int,
    drink_until_year: int,
) -> bool:
    return drink_from_year <= drink_until_year and drink_until_year - drink_from_year <= 80


def _shorten_evidence(evidence_text: str, *, max_length: int = 240) -> str:
    normalized = normalize_text(evidence_text)

    if len(normalized) <= max_length:
        return normalized

    return f"{normalized[: max_length - 1]}…"


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data.strip():
            self.parts.append(data.strip())
