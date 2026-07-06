from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection

from cellarmind.storage.sqlite import connect_database


@dataclass(frozen=True)
class AddBottlesResult:
    created_bottles: int
    wine_id: int
    wine_variant_id: int
    bottle_ids: tuple[int, ...]


def add_bottles(
    database_path: Path,
    *,
    producer: str,
    cuvee: str,
    vintage: str,
    appellation: str,
    color: str,
    bottle_format: str,
    quantity: int,
    cellar_name: str | None = None,
    location_name: str | None = None,
    purchase_price: float | None = None,
    personal_drink_from_year: int | None = None,
    personal_drink_until_year: int | None = None,
) -> AddBottlesResult:
    if not database_path.exists():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    normalized_producer = _required_text(producer, "producer")
    normalized_cuvee = _required_text(cuvee, "cuvee")
    normalized_vintage = _canonicalize_vintage(vintage)
    normalized_appellation = _required_text(appellation, "appellation")
    normalized_color = _required_text(color, "color")
    normalized_format = _canonicalize_format(bottle_format)

    if quantity < 1:
        raise ValueError("Quantity must be greater than or equal to 1.")

    if purchase_price is not None and purchase_price < 0:
        raise ValueError("Purchase price must be greater than or equal to 0.")

    if (
        personal_drink_from_year is not None
        and personal_drink_until_year is not None
        and personal_drink_from_year > personal_drink_until_year
    ):
        raise ValueError("Drink-from year cannot be after drink-until year.")

    normalized_cellar_name = cellar_name.strip() if cellar_name is not None else ""
    normalized_location_name = location_name.strip() if location_name is not None else ""

    if bool(normalized_cellar_name) != bool(normalized_location_name):
        raise ValueError("Cellar and location must be provided together.")

    with connect_database(database_path) as connection:
        import_session_id = _create_manual_import_session(
            connection,
            source_rows=1,
            created_bottle_count=quantity,
        )

        wine_id = _get_or_create_wine(
            connection,
            producer=normalized_producer,
            cuvee=normalized_cuvee,
            vintage=normalized_vintage,
            appellation=normalized_appellation,
            color=normalized_color,
        )

        wine_variant_id = _get_or_create_wine_variant(
            connection,
            wine_id=wine_id,
            bottle_format=normalized_format,
            personal_drink_from_year=personal_drink_from_year,
            personal_drink_until_year=personal_drink_until_year,
        )

        location_id = None

        if normalized_cellar_name and normalized_location_name:
            cellar_id = _get_or_create_cellar(connection, normalized_cellar_name)
            location_id = _get_or_create_location(
                connection,
                cellar_id=cellar_id,
                name=normalized_location_name,
            )

        bottle_ids: list[int] = []

        for _ in range(quantity):
            bottle_id = _create_bottle(
                connection,
                wine_variant_id=wine_variant_id,
                import_session_id=import_session_id,
                purchase_price=purchase_price,
            )
            bottle_ids.append(bottle_id)

            if location_id is not None:
                _create_bottle_location_history(
                    connection,
                    bottle_id=bottle_id,
                    location_id=location_id,
                )

        return AddBottlesResult(
            created_bottles=quantity,
            wine_id=wine_id,
            wine_variant_id=wine_variant_id,
            bottle_ids=tuple(bottle_ids),
        )


def _required_text(value: str, field_name: str) -> str:
    text = value.strip()

    if not text:
        raise ValueError(f"{field_name} is required.")

    return text


def _canonicalize_vintage(value: str) -> str:
    text = value.strip()

    if not text:
        return "NV"

    normalized = (
        text.casefold().replace("é", "e").replace("è", "e").replace("ê", "e").replace("-", " ")
    )

    if normalized in {"nv", "nm", "non vintage", "non millesime"}:
        return "NV"

    return text


def _canonicalize_format(value: str) -> str:
    text = value.strip().casefold()

    if not text:
        return "750ml"

    aliases = {
        "50": "500ml",
        "50cl": "500ml",
        "500ml": "500ml",
        "75": "750ml",
        "75cl": "750ml",
        "750ml": "750ml",
        "bottle": "750ml",
        "standard": "750ml",
        "bouteille": "750ml",
        "150": "1500ml",
        "150cl": "1500ml",
        "1500ml": "1500ml",
        "magnum": "1500ml",
        "half": "375ml",
        "half_bottle": "375ml",
        "demi": "375ml",
        "375ml": "375ml",
        "jeroboam": "3000ml",
        "3000ml": "3000ml",
        "imperial": "6000ml",
        "6000ml": "6000ml",
    }

    try:
        return aliases[text]
    except KeyError as error:
        raise ValueError(f"Unsupported bottle format: {value}") from error


def _create_manual_import_session(
    connection: Connection,
    *,
    source_rows: int,
    created_bottle_count: int,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO import_session (
            source_file,
            source_hash,
            row_count,
            created_bottle_count,
            notes
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "manual",
            None,
            source_rows,
            created_bottle_count,
            "Manual bottle addition",
        ),
    )

    return int(cursor.lastrowid)


def _get_or_create_wine(
    connection: Connection,
    *,
    producer: str,
    cuvee: str,
    vintage: str,
    appellation: str,
    color: str,
) -> int:
    connection.execute(
        """
        INSERT OR IGNORE INTO wine (
            producer,
            cuvee,
            vintage,
            appellation,
            color
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (producer, cuvee, vintage, appellation, color),
    )

    return int(
        connection.execute(
            """
            SELECT id
            FROM wine
            WHERE producer = ?
              AND cuvee = ?
              AND vintage = ?
              AND appellation = ?
              AND color = ?
            """,
            (producer, cuvee, vintage, appellation, color),
        ).fetchone()["id"]
    )


def _get_or_create_wine_variant(
    connection: Connection,
    *,
    wine_id: int,
    bottle_format: str,
    personal_drink_from_year: int | None,
    personal_drink_until_year: int | None,
) -> int:
    connection.execute(
        """
        INSERT OR IGNORE INTO wine_variant (
            wine_id,
            format,
            personal_drink_from_year,
            personal_drink_until_year
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            wine_id,
            bottle_format,
            personal_drink_from_year,
            personal_drink_until_year,
        ),
    )

    connection.execute(
        """
        UPDATE wine_variant
        SET personal_drink_from_year = COALESCE(personal_drink_from_year, ?),
            personal_drink_until_year = COALESCE(personal_drink_until_year, ?)
        WHERE wine_id = ?
          AND format = ?
        """,
        (
            personal_drink_from_year,
            personal_drink_until_year,
            wine_id,
            bottle_format,
        ),
    )

    return int(
        connection.execute(
            """
            SELECT id
            FROM wine_variant
            WHERE wine_id = ?
              AND format = ?
            """,
            (wine_id, bottle_format),
        ).fetchone()["id"]
    )


def _create_bottle(
    connection: Connection,
    *,
    wine_variant_id: int,
    import_session_id: int,
    purchase_price: float | None,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO bottle (
            wine_variant_id,
            import_session_id,
            purchase_price
        )
        VALUES (?, ?, ?)
        """,
        (wine_variant_id, import_session_id, purchase_price),
    )

    return int(cursor.lastrowid)


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
    *,
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


def _create_bottle_location_history(
    connection: Connection,
    *,
    bottle_id: int,
    location_id: int,
) -> None:
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
