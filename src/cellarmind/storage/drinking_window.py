from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from sqlite3 import Connection

from cellarmind.storage.sqlite import connect_database

ACTIVE_BOTTLE_STATUSES = ("in_cellar", "opened")

READY_CATEGORY = "ready"
TOO_YOUNG_CATEGORY = "too_young"
OVERDUE_CATEGORY = "overdue"
UNKNOWN_CATEGORY = "unknown"


@dataclass(frozen=True)
class DrinkingWindowSummary:
    as_of_year: int
    active_bottles: int
    ready_bottles: int
    too_young_bottles: int
    overdue_bottles: int
    unknown_window_bottles: int


@dataclass(frozen=True)
class DrinkingWindowBottle:
    category: str
    bottle_id: int
    producer: str
    cuvee: str
    vintage: str
    appellation: str
    color: str
    bottle_format: str
    status: str
    cellar: str | None
    location: str | None
    personal_drink_from_year: int | None
    personal_drink_until_year: int | None
    note: str


@dataclass(frozen=True)
class DrinkingWindowReport:
    summary: DrinkingWindowSummary
    bottles: tuple[DrinkingWindowBottle, ...]


def report_drinking_windows(
    database_path: Path,
    *,
    as_of_year: int | None = None,
    limit: int | None = None,
) -> DrinkingWindowReport:
    if not database_path.exists():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    resolved_year = as_of_year if as_of_year is not None else date.today().year

    with connect_database(database_path) as connection:
        rows = _fetch_active_bottle_rows(connection)

    bottles = tuple(_classify_bottle(row, as_of_year=resolved_year) for row in rows)

    sorted_bottles = tuple(sorted(bottles, key=_bottle_sort_key))

    if limit is not None:
        sorted_bottles = sorted_bottles[:limit]

    summary = DrinkingWindowSummary(
        as_of_year=resolved_year,
        active_bottles=len(bottles),
        ready_bottles=sum(1 for bottle in bottles if bottle.category == READY_CATEGORY),
        too_young_bottles=sum(1 for bottle in bottles if bottle.category == TOO_YOUNG_CATEGORY),
        overdue_bottles=sum(1 for bottle in bottles if bottle.category == OVERDUE_CATEGORY),
        unknown_window_bottles=sum(1 for bottle in bottles if bottle.category == UNKNOWN_CATEGORY),
    )

    return DrinkingWindowReport(
        summary=summary,
        bottles=sorted_bottles,
    )


def _fetch_active_bottle_rows(connection: Connection):
    return connection.execute(
        """
        SELECT
            bottle.id AS bottle_id,
            bottle.status,
            wine.producer,
            wine.cuvee,
            wine.vintage,
            wine.appellation,
            wine.color,
            wine_variant.format AS bottle_format,
            wine_variant.personal_drink_from_year,
            wine_variant.personal_drink_until_year,
            cellar.name AS cellar_name,
            location.name AS location_name
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
        WHERE bottle.status IN ('in_cellar', 'opened')
        ORDER BY wine.producer, wine.cuvee, wine.vintage, bottle.id
        """
    ).fetchall()


def _classify_bottle(row, *, as_of_year: int) -> DrinkingWindowBottle:
    drink_from = row["personal_drink_from_year"]
    drink_until = row["personal_drink_until_year"]

    category = _drinking_window_category(
        drink_from=drink_from,
        drink_until=drink_until,
        as_of_year=as_of_year,
    )

    return DrinkingWindowBottle(
        category=category,
        bottle_id=int(row["bottle_id"]),
        producer=row["producer"],
        cuvee=row["cuvee"],
        vintage=row["vintage"],
        appellation=row["appellation"],
        color=row["color"],
        bottle_format=row["bottle_format"],
        status=row["status"],
        cellar=row["cellar_name"],
        location=row["location_name"],
        personal_drink_from_year=drink_from,
        personal_drink_until_year=drink_until,
        note=_category_note(
            category=category,
            drink_from=drink_from,
            drink_until=drink_until,
            as_of_year=as_of_year,
        ),
    )


def _drinking_window_category(
    *,
    drink_from: int | None,
    drink_until: int | None,
    as_of_year: int,
) -> str:
    if drink_from is None and drink_until is None:
        return UNKNOWN_CATEGORY

    if drink_until is not None and as_of_year > drink_until:
        return OVERDUE_CATEGORY

    if drink_from is not None and as_of_year < drink_from:
        return TOO_YOUNG_CATEGORY

    return READY_CATEGORY


def _category_note(
    *,
    category: str,
    drink_from: int | None,
    drink_until: int | None,
    as_of_year: int,
) -> str:
    if category == UNKNOWN_CATEGORY:
        return "No personal drinking window."

    if category == OVERDUE_CATEGORY:
        return f"Past personal drink-until year {drink_until}."

    if category == TOO_YOUNG_CATEGORY:
        return f"Personal drink-from year is {drink_from}."

    return f"Ready according to personal window as of {as_of_year}."


def _bottle_sort_key(bottle: DrinkingWindowBottle) -> tuple[int, int, str, str, int]:
    category_order = {
        OVERDUE_CATEGORY: 0,
        READY_CATEGORY: 1,
        TOO_YOUNG_CATEGORY: 2,
        UNKNOWN_CATEGORY: 3,
    }

    until_year = (
        bottle.personal_drink_until_year if bottle.personal_drink_until_year is not None else 9999
    )

    return (
        category_order.get(bottle.category, 99),
        until_year,
        bottle.producer,
        bottle.cuvee,
        bottle.bottle_id,
    )
