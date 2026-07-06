from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection

from cellarmind.storage.sqlite import connect_database

IN_CELLAR_STATUS = "in_cellar"
OPENED_STATUS = "opened"
CONSUMED_STATUS = "consumed"
GIFTED_STATUS = "gifted"
SOLD_STATUS = "sold"
LOST_STATUS = "lost"

VALID_BOTTLE_STATUSES = frozenset(
    {
        IN_CELLAR_STATUS,
        OPENED_STATUS,
        CONSUMED_STATUS,
        GIFTED_STATUS,
        SOLD_STATUS,
        LOST_STATUS,
    }
)

OUT_OF_CELLAR_STATUSES = frozenset(
    {
        CONSUMED_STATUS,
        GIFTED_STATUS,
        SOLD_STATUS,
        LOST_STATUS,
    }
)


@dataclass(frozen=True)
class BottleStatusUpdateResult:
    bottle_id: int
    previous_status: str
    new_status: str
    changed: bool
    closed_location_history_rows: int


def update_bottle_status(
    database_path: Path,
    *,
    bottle_id: int,
    new_status: str,
) -> BottleStatusUpdateResult:
    if not database_path.exists():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    normalized_status = new_status.strip().casefold()

    if normalized_status not in VALID_BOTTLE_STATUSES:
        valid_statuses = ", ".join(sorted(VALID_BOTTLE_STATUSES))
        raise ValueError(f"Invalid bottle status: {new_status}. Expected one of: {valid_statuses}.")

    with connect_database(database_path) as connection:
        previous_status = _get_bottle_status(connection, bottle_id)
        changed = previous_status != normalized_status

        if changed:
            connection.execute(
                """
                UPDATE bottle
                SET status = ?
                WHERE id = ?
                """,
                (normalized_status, bottle_id),
            )

        closed_location_history_rows = 0

        if normalized_status in OUT_OF_CELLAR_STATUSES:
            cursor = connection.execute(
                """
                UPDATE bottle_location_history
                SET ended_at = CURRENT_TIMESTAMP
                WHERE bottle_id = ?
                  AND ended_at IS NULL
                """,
                (bottle_id,),
            )
            closed_location_history_rows = cursor.rowcount

        return BottleStatusUpdateResult(
            bottle_id=bottle_id,
            previous_status=previous_status,
            new_status=normalized_status,
            changed=changed,
            closed_location_history_rows=closed_location_history_rows,
        )


def _get_bottle_status(connection: Connection, bottle_id: int) -> str:
    row = connection.execute(
        """
        SELECT status
        FROM bottle
        WHERE id = ?
        """,
        (bottle_id,),
    ).fetchone()

    if row is None:
        raise ValueError(f"Bottle does not exist: {bottle_id}")

    return str(row["status"])
