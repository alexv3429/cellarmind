from pathlib import Path

from typer.testing import CliRunner

from cellarmind.cli import app
from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.storage.reference_window_search import (
    _RawSearchResult,
    build_reference_window_search_query,
    search_reference_window_sources,
)
from cellarmind.storage.sqlite import connect_database

runner = CliRunner()


def test_build_reference_window_search_query() -> None:
    from cellarmind.storage.reference_window_search import WineSearchIdentity

    query = build_reference_window_search_query(
        WineSearchIdentity(
            wine_id=1,
            producer="Domaine Test",
            cuvee="Clos Example",
            vintage="2018",
            appellation="Bourgogne",
            color="Rouge",
        )
    )

    assert query == "Domaine Test Clos Example 2018 Bourgogne drinking window"


def test_reference_window_search_returns_results(monkeypatch, tmp_path: Path) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path)

    def fake_search_ddgs(
        *,
        query: str,
        limit: int,
        timeout_seconds: float,
    ) -> tuple[_RawSearchResult, ...]:
        return (
            _RawSearchResult(
                title="Example Wine Page",
                url="https://example.com/wine",
                snippet="Example snippet",
            ),
        )

    monkeypatch.setattr(
        "cellarmind.storage.reference_window_search._search_ddgs",
        fake_search_ddgs,
    )

    report = search_reference_window_sources(
        database_path,
        wine_id=wine_id,
        limit=5,
    )

    assert report.wine.wine_id == wine_id
    assert "Internet Search Wine" in report.query
    assert len(report.results) == 1
    assert report.results[0].title == "Example Wine Page"
    assert report.results[0].url == "https://example.com/wine"
    assert report.results[0].candidate is None


def test_reference_window_search_fetches_candidates(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path)

    def fake_search_ddgs(
        *,
        query: str,
        limit: int,
        timeout_seconds: float,
    ) -> tuple[_RawSearchResult, ...]:
        return (
            _RawSearchResult(
                title="Example Wine Page",
                url="https://example.com/wine",
                snippet="Example snippet",
            ),
        )

    def fake_fetch_reference_window_candidate(
        *,
        source_url: str,
        source_name: str | None = None,
        timeout_seconds: float = 15.0,
    ):
        from cellarmind.storage.reference_windows_fetcher import ReferenceWindowCandidate

        return ReferenceWindowCandidate(
            source_name=source_name or "Example",
            source_url=source_url,
            drink_from_year=2024,
            drink_until_year=2032,
            confidence="medium",
            evidence_text="Drinking window 2024-2032.",
        )

    monkeypatch.setattr(
        "cellarmind.storage.reference_window_search._search_ddgs",
        fake_search_ddgs,
    )
    monkeypatch.setattr(
        "cellarmind.storage.reference_window_search.fetch_reference_window_candidate",
        fake_fetch_reference_window_candidate,
    )

    report = search_reference_window_sources(
        database_path,
        wine_id=wine_id,
        limit=5,
        fetch_candidates=True,
    )

    assert len(report.results) == 1
    assert report.results[0].candidate is not None
    assert report.results[0].candidate.drink_from_year == 2024
    assert report.results[0].candidate.drink_until_year == 2032


def test_reference_window_search_command_outputs_results(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _create_database_with_wine(tmp_path)
    wine_id = _get_wine_id(database_path)

    def fake_search_ddgs(
        *,
        query: str,
        limit: int,
        timeout_seconds: float,
    ) -> tuple[_RawSearchResult, ...]:
        return (
            _RawSearchResult(
                title="Example Wine Page",
                url="https://example.com/wine",
                snippet="Example snippet",
            ),
        )

    monkeypatch.setattr(
        "cellarmind.storage.reference_window_search._search_ddgs",
        fake_search_ddgs,
    )

    result = runner.invoke(
        app,
        [
            "reference-window",
            "search",
            "--database",
            str(database_path),
            "--wine-id",
            str(wine_id),
        ],
    )

    assert result.exit_code == 0
    assert "Database:" in result.output
    assert "Reference-window source search" in result.output
    assert "Example Wine Page" in result.output


def _create_database_with_wine(tmp_path: Path) -> Path:
    input_path = tmp_path / "cave.csv"
    database_path = tmp_path / "cellarmind.sqlite"

    input_path.write_text(
        "Cave,Place,Année prod,Cuvée,Appellation,Vignoble couleur,Producteur,"
        "Année min,Année Max,Nb,Fmt\n"
        "Main,A1,2018,Internet Search Wine,France,Rouge,Producer A,2020,2030,1,75\n",
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
            ("Internet Search Wine",),
        ).fetchone()

    assert row is not None

    return int(row["id"])
