from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cellarmind.storage.sqlite import connect_database


@dataclass(frozen=True)
class BottleListItem:
    bottle_id: int
    producer: str
    cuvee: str
    vintage: int
    appellation: str
    color: str
    format: str
    status: str
    cellar: str | None
    location: str | None


def list_bottles(database_path: Path, limit: int = 50) -> tuple[BottleListItem, ...]:
    if not database_path.exists():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    with connect_database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                bottle.id AS bottle_id,
                wine.producer AS producer,
                wine.cuvee AS cuvee,
                wine.vintage AS vintage,
                wine.appellation AS appellation,
                wine.color AS color,
                wine_variant.format AS format,
                bottle.status AS status,
                cellar.name AS cellar,
                location.name AS location
            FROM bottle
            JOIN wine_variant
                ON wine_variant.id = bottle.wine_variant_id
            JOIN wine
                ON wine.id = wine_variant.wine_id
            LEFT JOIN bottle_location_history
                ON bottle_location_history.bottle_id = bottle.id
                AND bottle_location_history.ended_at IS NULL
            LEFT JOIN location
                ON location.id = bottle_location_history.location_id
            LEFT JOIN cellar
                ON cellar.id = location.cellar_id
            ORDER BY
                wine.producer,
                wine.cuvee,
                wine.vintage,
                bottle.id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return tuple(
        BottleListItem(
            bottle_id=int(row["bottle_id"]),
            producer=str(row["producer"]),
            cuvee=str(row["cuvee"]),
            vintage=int(row["vintage"]),
            appellation=str(row["appellation"]),
            color=str(row["color"]),
            format=str(row["format"]),
            status=str(row["status"]),
            cellar=row["cellar"],
            location=row["location"],
        )
        for row in rows
    )
