from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection

from cellarmind.storage.sqlite import connect_database


@dataclass(frozen=True)
class BottleLocation:
    cellar: str
    location: str


@dataclass(frozen=True)
class BottleMoveResult:
    bottle_id: int
    moved: bool
    previous_location: BottleLocation | None
    new_location: BottleLocation


def move_bottle(
    database_path: Path,
    *,
    bottle_id: int,
    cellar_name: str,
    location_name: str,
) -> BottleMoveResult:
    if not database_path.exists():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    normalized_cellar_name = cellar_name.strip()
    normalized_location_name = location_name.strip()

    if not normalized_cellar_name:
        raise ValueError("Cellar name is required.")

    if not normalized_location_name:
        raise ValueError("Location name is required.")

    with connect_database(database_path) as connection:
        _ensure_bottle_exists(connection, bottle_id)

        previous_location = _get_active_bottle_location(connection, bottle_id)

        new_location = BottleLocation(
            cellar=normalized_cellar_name,
            location=normalized_location_name,
        )

        if previous_location == new_location:
            return BottleMoveResult(
                bottle_id=bottle_id,
                moved=False,
                previous_location=previous_location,
                new_location=new_location,
            )

        cellar_id = _get_or_create_cellar(connection, normalized_cellar_name)
        location_id = _get_or_create_location(
            connection,
            cellar_id,
            normalized_location_name,
        )

        connection.execute(
            """
            UPDATE bottle_location_history
            SET ended_at = CURRENT_TIMESTAMP
            WHERE bottle_id = ?
              AND ended_at IS NULL
            """,
            (bottle_id,),
        )

        connection.execute(
            """
            INSERT INTO bottle_location_history (
                bottle_id,
                location_id
            )
            VALUES (?, ?)
            """,
            (bottle_id, location_id),
        )

        return BottleMoveResult(
            bottle_id=bottle_id,
            moved=True,
            previous_location=previous_location,
            new_location=new_location,
        )


def _ensure_bottle_exists(connection: Connection, bottle_id: int) -> None:
    row = connection.execute(
        """
        SELECT id
        FROM bottle
        WHERE id = ?
        """,
        (bottle_id,),
    ).fetchone()

    if row is None:
        raise ValueError(f"Bottle does not exist: {bottle_id}")


def _get_active_bottle_location(
    connection: Connection,
    bottle_id: int,
) -> BottleLocation | None:
    row = connection.execute(
        """
        SELECT
            cellar.name AS cellar_name,
            location.name AS location_name
        FROM bottle_location_history
        JOIN location
            ON location.id = bottle_location_history.location_id
        JOIN cellar
            ON cellar.id = location.cellar_id
        WHERE bottle_location_history.bottle_id = ?
          AND bottle_location_history.ended_at IS NULL
        """,
        (bottle_id,),
    ).fetchone()

    if row is None:
        return None

    return BottleLocation(
        cellar=row["cellar_name"],
        location=row["location_name"],
    )


def _get_or_create_cellar(connection: Connection, name: str) -> int:
    connection.execute(
        """
        INSERT OR IGNORE INTO cellar (name)
        VALUES (?)
        """,
        (name,),
    )

    return int(
        connection.execute(
            """
            SELECT id
            FROM cellar
            WHERE name = ?
            """,
            (name,),
        ).fetchone()["id"]
    )


def _get_or_create_location(
    connection: Connection,
    cellar_id: int,
    name: str,
) -> int:
    connection.execute(
        """
        INSERT OR IGNORE INTO location (
            cellar_id,
            name
        )
        VALUES (?, ?)
        """,
        (cellar_id, name),
    )

    return int(
        connection.execute(
            """
            SELECT id
            FROM location
            WHERE cellar_id = ?
              AND name = ?
            """,
            (cellar_id, name),
        ).fetchone()["id"]
    )
