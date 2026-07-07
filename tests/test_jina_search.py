from __future__ import annotations

from cellarmind.storage.jina_search import _parse_jina_search_results


def test_parse_jina_title_url_blocks() -> None:
    body = """
Title: Example Wine Page
URL Source: https://example.com/wine
Markdown Content:
Drink from 2022 until 2030.

Title: Other Page
URL Source: https://example.com/other
Markdown Content:
No window here.
"""

    results = _parse_jina_search_results(body, limit=10)

    assert len(results) == 2
    assert results[0].title == "Example Wine Page"
    assert results[0].url == "https://example.com/wine"
    assert "2022 until 2030" in (results[0].snippet or "")


def test_parse_jina_markdown_links() -> None:
    body = """
## [Example Wine Page](https://example.com/wine)
Some surrounding text.
"""

    results = _parse_jina_search_results(body, limit=10)

    assert len(results) == 1
    assert results[0].title == "Example Wine Page"
    assert results[0].url == "https://example.com/wine"
