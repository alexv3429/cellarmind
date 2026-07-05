from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection

from cellarmind.storage.sqlite import connect_database


@dataclass(frozen=True)
class AuditSummary:
    bottles: int
    wines: int
    wine_variants: int
    bottles_with_price: int
    bottles_without_price: int
    total_purchase_value: float
    variants_with_personal_drink_window: int
    variants_without_personal_drink_window: int
    non_vintage_wines: int
    bottles_without_location: int


@dataclass(frozen=True)
class AuditBreakdownRow:
    label: str
    bottle_count: int


@dataclass(frozen=True)
class CellarAudit:
    summary: AuditSummary
    bottles_by_cellar: tuple[AuditBreakdownRow, ...]
    bottles_by_format: tuple[AuditBreakdownRow, ...]
    top_producers: tuple[AuditBreakdownRow, ...]
    top_appellations: tuple[AuditBreakdownRow, ...]


def audit_database(database_path: Path, *, top_limit: int = 10) -> CellarAudit:
    if not database_path.exists():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    with connect_database(database_path) as connection:
        bottles = _count(connection, "SELECT COUNT(*) AS count FROM bottle")
        wines = _count(connection, "SELECT COUNT(*) AS count FROM wine")
        wine_variants = _count(
            connection,
            "SELECT COUNT(*) AS count FROM wine_variant",
        )

        price_row = connection.execute(
            """
            SELECT
                COUNT(purchase_price) AS bottles_with_price,
                COUNT(*) - COUNT(purchase_price) AS bottles_without_price,
                COALESCE(SUM(purchase_price), 0) AS total_purchase_value
            FROM bottle
            """
        ).fetchone()

        variants_with_personal_drink_window = _count(
            connection,
            """
            SELECT COUNT(*) AS count
            FROM wine_variant
            WHERE personal_drink_from_year IS NOT NULL
               OR personal_drink_until_year IS NOT NULL
            """,
        )

        non_vintage_wines = _count(
            connection,
            """
            SELECT COUNT(*) AS count
            FROM wine
            WHERE vintage = 'NV'
            """,
        )

        bottles_without_location = _count(
            connection,
            """
            SELECT COUNT(*) AS count
            FROM bottle
            WHERE NOT EXISTS (
                SELECT 1
                FROM bottle_location_history
                WHERE bottle_location_history.bottle_id = bottle.id
            )
            """,
        )

        summary = AuditSummary(
            bottles=bottles,
            wines=wines,
            wine_variants=wine_variants,
            bottles_with_price=int(price_row["bottles_with_price"]),
            bottles_without_price=int(price_row["bottles_without_price"]),
            total_purchase_value=float(price_row["total_purchase_value"]),
            variants_with_personal_drink_window=variants_with_personal_drink_window,
            variants_without_personal_drink_window=(
                wine_variants - variants_with_personal_drink_window
            ),
            non_vintage_wines=non_vintage_wines,
            bottles_without_location=bottles_without_location,
        )

        return CellarAudit(
            summary=summary,
            bottles_by_cellar=_fetch_bottles_by_cellar(connection),
            bottles_by_format=_fetch_bottles_by_format(connection),
            top_producers=_fetch_top_producers(connection, top_limit),
            top_appellations=_fetch_top_appellations(connection, top_limit),
        )


def _count(connection: Connection, query: str) -> int:
    return int(connection.execute(query).fetchone()["count"])


def _fetch_bottles_by_cellar(
    connection: Connection,
) -> tuple[AuditBreakdownRow, ...]:
    rows = connection.execute(
        """
        WITH latest_location_history AS (
            SELECT
                bottle_id,
                MAX(id) AS latest_history_id
            FROM bottle_location_history
            GROUP BY bottle_id
        )
        SELECT
            cellar.name AS label,
            COUNT(*) AS bottle_count
        FROM bottle
        JOIN latest_location_history
            ON latest_location_history.bottle_id = bottle.id
        JOIN bottle_location_history
            ON bottle_location_history.id =
               latest_location_history.latest_history_id
        JOIN location
            ON location.id = bottle_location_history.location_id
        JOIN cellar
            ON cellar.id = location.cellar_id
        GROUP BY cellar.name
        ORDER BY bottle_count DESC, cellar.name
        """
    ).fetchall()

    return tuple(
        AuditBreakdownRow(
            label=row["label"],
            bottle_count=int(row["bottle_count"]),
        )
        for row in rows
    )


def _fetch_bottles_by_format(
    connection: Connection,
) -> tuple[AuditBreakdownRow, ...]:
    rows = connection.execute(
        """
        SELECT
            wine_variant.format AS label,
            COUNT(*) AS bottle_count
        FROM bottle
        JOIN wine_variant
            ON wine_variant.id = bottle.wine_variant_id
        GROUP BY wine_variant.format
        ORDER BY bottle_count DESC, wine_variant.format
        """
    ).fetchall()

    return tuple(
        AuditBreakdownRow(
            label=row["label"],
            bottle_count=int(row["bottle_count"]),
        )
        for row in rows
    )


def _fetch_top_producers(
    connection: Connection,
    limit: int,
) -> tuple[AuditBreakdownRow, ...]:
    rows = connection.execute(
        """
        SELECT
            wine.producer AS label,
            COUNT(*) AS bottle_count
        FROM bottle
        JOIN wine_variant
            ON wine_variant.id = bottle.wine_variant_id
        JOIN wine
            ON wine.id = wine_variant.wine_id
        GROUP BY wine.producer
        ORDER BY bottle_count DESC, wine.producer
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    return tuple(
        AuditBreakdownRow(
            label=row["label"],
            bottle_count=int(row["bottle_count"]),
        )
        for row in rows
    )


def _fetch_top_appellations(
    connection: Connection,
    limit: int,
) -> tuple[AuditBreakdownRow, ...]:
    rows = connection.execute(
        """
        SELECT
            wine.appellation AS label,
            COUNT(*) AS bottle_count
        FROM bottle
        JOIN wine_variant
            ON wine_variant.id = bottle.wine_variant_id
        JOIN wine
            ON wine.id = wine_variant.wine_id
        GROUP BY wine.appellation
        ORDER BY bottle_count DESC, wine.appellation
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    return tuple(
        AuditBreakdownRow(
            label=row["label"],
            bottle_count=int(row["bottle_count"]),
        )
        for row in rows
    )
