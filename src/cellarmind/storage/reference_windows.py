from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection

from cellarmind.storage.sqlite import connect_database

VALID_CONFIDENCES = {"low", "medium", "high"}


REFERENCE_WINDOW_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS reference_drinking_window (
    id INTEGER PRIMARY KEY,
    wine_id INTEGER NOT NULL,
    source_name TEXT NOT NULL CHECK (trim(source_name) != ''),
    source_url TEXT,
    drink_from_year INTEGER,
    drink_until_year INTEGER,
    confidence TEXT NOT NULL DEFAULT 'medium'
        CHECK (confidence IN ('low', 'medium', 'high')),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (wine_id) REFERENCES wine(id),

    CHECK (
        drink_from_year IS NOT NULL
        OR drink_until_year IS NOT NULL
    ),

    CHECK (
        drink_from_year IS NULL
        OR drink_until_year IS NULL
        OR drink_from_year <= drink_until_year
    )
)
"""


@dataclass(frozen=True)
class ReferenceDrinkingWindow:
    id: int
    wine_id: int
    source_name: str
    source_url: str | None
    drink_from_year: int | None
    drink_until_year: int | None
    confidence: str
    notes: str | None
    created_at: str


def ensure_reference_window_schema(connection: Connection) -> None:
    connection.execute(REFERENCE_WINDOW_SCHEMA_SQL)


def add_reference_window(
    database_path: Path,
    *,
    wine_id: int,
    source_name: str,
    source_url: str | None = None,
    drink_from_year: int | None = None,
    drink_until_year: int | None = None,
    confidence: str = "medium",
    notes: str | None = None,
) -> ReferenceDrinkingWindow:
    if not database_path.exists():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    normalized_source_name = _normalize_required_text(
        source_name,
        field_name="source_name",
    )
    normalized_source_url = _normalize_optional_text(source_url)
    normalized_notes = _normalize_optional_text(notes)
    normalized_confidence = confidence.strip().lower()

    _validate_confidence(normalized_confidence)
    _validate_window(
        drink_from_year=drink_from_year,
        drink_until_year=drink_until_year,
    )

    with connect_database(database_path) as connection:
        ensure_reference_window_schema(connection)
        _ensure_wine_exists(connection, wine_id)

        cursor = connection.execute(
            """
            INSERT INTO reference_drinking_window (
                wine_id,
                source_name,
                source_url,
                drink_from_year,
                drink_until_year,
                confidence,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                wine_id,
                normalized_source_name,
                normalized_source_url,
                drink_from_year,
                drink_until_year,
                normalized_confidence,
                normalized_notes,
            ),
        )

        reference_id = int(cursor.lastrowid)

        row = connection.execute(
            """
            SELECT
                id,
                wine_id,
                source_name,
                source_url,
                drink_from_year,
                drink_until_year,
                confidence,
                notes,
                created_at
            FROM reference_drinking_window
            WHERE id = ?
            """,
            (reference_id,),
        ).fetchone()

    return _row_to_reference_window(row)


def list_reference_windows(
    database_path: Path,
    *,
    wine_id: int | None = None,
) -> tuple[ReferenceDrinkingWindow, ...]:
    if not database_path.exists():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    with connect_database(database_path) as connection:
        ensure_reference_window_schema(connection)

        if wine_id is not None:
            _ensure_wine_exists(connection, wine_id)
            rows = connection.execute(
                """
                SELECT
                    id,
                    wine_id,
                    source_name,
                    source_url,
                    drink_from_year,
                    drink_until_year,
                    confidence,
                    notes,
                    created_at
                FROM reference_drinking_window
                WHERE wine_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (wine_id,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT
                    id,
                    wine_id,
                    source_name,
                    source_url,
                    drink_from_year,
                    drink_until_year,
                    confidence,
                    notes,
                    created_at
                FROM reference_drinking_window
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()

    return tuple(_row_to_reference_window(row) for row in rows)


def _ensure_wine_exists(connection: Connection, wine_id: int) -> None:
    row = connection.execute(
        """
        SELECT id
        FROM wine
        WHERE id = ?
        """,
        (wine_id,),
    ).fetchone()

    if row is None:
        raise ValueError(f"Unknown wine id: {wine_id}")


def _validate_confidence(confidence: str) -> None:
    if confidence not in VALID_CONFIDENCES:
        raise ValueError("Confidence must be one of: low, medium, high.")


def _validate_window(
    *,
    drink_from_year: int | None,
    drink_until_year: int | None,
) -> None:
    if drink_from_year is None and drink_until_year is None:
        raise ValueError("At least one of drink_from_year or drink_until_year is required.")

    if (
        drink_from_year is not None
        and drink_until_year is not None
        and drink_from_year > drink_until_year
    ):
        raise ValueError("drink_from_year must be less than or equal to drink_until_year.")


def _normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()

    if not normalized:
        raise ValueError(f"{field_name} must not be blank.")

    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()

    if not normalized:
        return None

    return normalized


def _row_to_reference_window(row) -> ReferenceDrinkingWindow:
    return ReferenceDrinkingWindow(
        id=int(row["id"]),
        wine_id=int(row["wine_id"]),
        source_name=row["source_name"],
        source_url=row["source_url"],
        drink_from_year=row["drink_from_year"],
        drink_until_year=row["drink_until_year"],
        confidence=row["confidence"],
        notes=row["notes"],
        created_at=row["created_at"],
    )
