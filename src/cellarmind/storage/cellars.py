from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection

from cellarmind.storage.sqlite import connect_database

VALID_CELLAR_PURPOSES = frozenset(
    {
        "aging",
        "drink_soon",
        "mixed",
        "staging",
        "overflow",
    }
)


@dataclass(frozen=True)
class CellarProfile:
    name: str
    purpose: str
    active_bottles: int
    capacity_estimate: int | None
    capacity_warning_threshold: int | None
    occupancy_status: str
    notes: str | None


def list_cellars(database_path: Path) -> tuple[CellarProfile, ...]:
    if not database_path.exists():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    with connect_database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                cellar.name,
                cellar.purpose,
                cellar.capacity_estimate,
                cellar.capacity_warning_threshold,
                cellar.notes,
                COUNT(bottle.id) AS active_bottles
            FROM cellar
            LEFT JOIN location
                ON location.cellar_id = cellar.id
            LEFT JOIN bottle_location_history
                ON bottle_location_history.location_id = location.id
               AND bottle_location_history.ended_at IS NULL
            LEFT JOIN bottle
                ON bottle.id = bottle_location_history.bottle_id
               AND bottle.status IN ('in_cellar', 'opened')
            GROUP BY cellar.id
            ORDER BY cellar.name
            """
        ).fetchall()

    return tuple(
        CellarProfile(
            name=row["name"],
            purpose=row["purpose"],
            active_bottles=int(row["active_bottles"]),
            capacity_estimate=row["capacity_estimate"],
            capacity_warning_threshold=row["capacity_warning_threshold"],
            occupancy_status=_occupancy_status(
                active_bottles=int(row["active_bottles"]),
                capacity_estimate=row["capacity_estimate"],
                capacity_warning_threshold=row["capacity_warning_threshold"],
            ),
            notes=row["notes"],
        )
        for row in rows
    )


def update_cellar_profile(
    database_path: Path,
    *,
    name: str,
    purpose: str | None = None,
    capacity_estimate: int | None = None,
    capacity_warning_threshold: int | None = None,
    notes: str | None = None,
) -> None:
    if not database_path.exists():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    normalized_name = name.strip()

    if not normalized_name:
        raise ValueError("Cellar name is required.")

    if purpose is not None and purpose not in VALID_CELLAR_PURPOSES:
        valid_purposes = ", ".join(sorted(VALID_CELLAR_PURPOSES))
        raise ValueError(f"Invalid cellar purpose: {purpose}. Expected one of: {valid_purposes}.")

    if capacity_estimate is not None and capacity_estimate < 0:
        raise ValueError("Capacity estimate must be greater than or equal to 0.")

    if capacity_warning_threshold is not None and capacity_warning_threshold < 0:
        raise ValueError("Capacity warning threshold must be greater than or equal to 0.")

    if (
        capacity_estimate is not None
        and capacity_warning_threshold is not None
        and capacity_warning_threshold > capacity_estimate
    ):
        raise ValueError("Capacity warning threshold cannot exceed capacity estimate.")

    with connect_database(database_path) as connection:
        _get_or_create_cellar(connection, normalized_name)

        updates: list[str] = []
        values: list[object] = []

        if purpose is not None:
            updates.append("purpose = ?")
            values.append(purpose)

        if capacity_estimate is not None:
            updates.append("capacity_estimate = ?")
            values.append(capacity_estimate)

        if capacity_warning_threshold is not None:
            updates.append("capacity_warning_threshold = ?")
            values.append(capacity_warning_threshold)

        if notes is not None:
            updates.append("notes = ?")
            values.append(notes)

        if not updates:
            return

        values.append(normalized_name)

        connection.execute(
            f"""
            UPDATE cellar
            SET {", ".join(updates)}
            WHERE name = ?
            """,
            values,
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


def _occupancy_status(
    *,
    active_bottles: int,
    capacity_estimate: int | None,
    capacity_warning_threshold: int | None,
) -> str:
    if capacity_estimate is None:
        return "unknown"

    if active_bottles > capacity_estimate:
        return "over_capacity"

    if capacity_warning_threshold is not None and active_bottles >= capacity_warning_threshold:
        return "near_capacity"

    return "ok"
