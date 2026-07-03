from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cellarmind.storage.sqlite import connect_database


@dataclass(frozen=True)
class BottleStatusCount:
    status: str
    count: int


@dataclass(frozen=True)
class DatabaseStats:
    database_path: Path
    import_sessions: int
    wines: int
    wine_variants: int
    bottles: int
    active_bottles: int
    cellars: int
    locations: int
    bottle_location_history_rows: int
    active_location_rows: int
    bottle_status_counts: tuple[BottleStatusCount, ...]


def get_database_stats(database_path: Path) -> DatabaseStats:
    if not database_path.exists():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    with connect_database(database_path) as connection:
        status_counts = tuple(
            BottleStatusCount(status=row["status"], count=int(row["count"]))
            for row in connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM bottle
                GROUP BY status
                ORDER BY status
                """
            )
        )

        return DatabaseStats(
            database_path=database_path,
            import_sessions=_count_table(connection, "import_session"),
            wines=_count_table(connection, "wine"),
            wine_variants=_count_table(connection, "wine_variant"),
            bottles=_count_table(connection, "bottle"),
            active_bottles=_count_where(connection, "bottle", "status = 'in_cellar'"),
            cellars=_count_table(connection, "cellar"),
            locations=_count_table(connection, "location"),
            bottle_location_history_rows=_count_table(
                connection,
                "bottle_location_history",
            ),
            active_location_rows=_count_where(
                connection,
                "bottle_location_history",
                "ended_at IS NULL",
            ),
            bottle_status_counts=status_counts,
        )


def _count_table(connection, table_name: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])


def _count_where(connection, table_name: str, where_clause: str) -> int:
    return int(
        connection.execute(
            f"SELECT COUNT(*) FROM {table_name} WHERE {where_clause}",
        ).fetchone()[0]
    )
