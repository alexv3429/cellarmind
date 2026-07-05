from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from cellarmind.importing.location_mapping import (
    LocationMappingRule,
    load_location_mapping,
    resolve_cellar_from_location,
)
from cellarmind.importing.normalizer import (
    canonicalize_quantity,
    normalize_csv_to_canonical,
)
from cellarmind.storage.sqlite import connect_database, initialize_database

DEFAULT_CELLAR_NAME = "Default cellar"
DEFAULT_LOCATION_NAME = "Unspecified location"


@dataclass(frozen=True)
class DatabaseImportResult:
    database_path: Path
    source_file: Path
    import_session_id: int
    source_rows: int
    created_bottles: int
    wines: int
    wine_variants: int


def import_csv_to_database(
    input_path: Path, database_path: Path, *, cellar_map_path: Path | None = None
) -> DatabaseImportResult:
    rules: list[LocationMappingRule] = []
    if cellar_map_path is not None:
        rules = load_location_mapping(cellar_map_path)

    initialize_database(database_path)

    with tempfile.TemporaryDirectory() as tmp_dir:
        canonical_path = Path(tmp_dir) / "canonical.csv"
        normalize_csv_to_canonical(input_path, canonical_path)
        df = pl.read_csv(canonical_path, infer_schema_length=0)

        with connect_database(database_path) as connection:
            import_session_id = _create_import_session(
                connection=connection,
                input_path=input_path,
                row_count=df.height,
            )

            created_bottles = 0
            touched_wines: set[int] = set()
            touched_variants: set[int] = set()

            for row in df.iter_rows(named=True):
                wine_id = _get_or_create_wine(connection, row)
                variant_id = _get_or_create_wine_variant(connection, wine_id, _text(row, "format"))

                touched_wines.add(wine_id)
                touched_variants.add(variant_id)

                location_id = _get_or_create_import_location(connection, row, rules)
                quantity = canonicalize_quantity(_text(row, "quantity"))

                for _ in range(quantity):
                    bottle_id = _create_bottle(
                        connection=connection,
                        wine_variant_id=variant_id,
                        import_session_id=import_session_id,
                    )
                    created_bottles += 1

                    if location_id is not None:
                        _create_initial_location_history(
                            connection=connection,
                            bottle_id=bottle_id,
                            location_id=location_id,
                        )

            connection.execute(
                """
                UPDATE import_session
                SET created_bottle_count = ?
                WHERE id = ?
                """,
                (created_bottles, import_session_id),
            )

    return DatabaseImportResult(
        database_path=database_path,
        source_file=input_path,
        import_session_id=import_session_id,
        source_rows=df.height,
        created_bottles=created_bottles,
        wines=len(touched_wines),
        wine_variants=len(touched_variants),
    )


def _create_import_session(connection, input_path: Path, row_count: int) -> int:
    cursor = connection.execute(
        """
        INSERT INTO import_session (source_file, source_hash, row_count)
        VALUES (?, ?, ?)
        """,
        (str(input_path), _sha256_file(input_path), row_count),
    )
    return int(cursor.lastrowid)


def _get_or_create_wine(connection, row: dict[str, object]) -> int:
    values = (
        _text(row, "producer"),
        _text(row, "cuvee"),
        _canonicalize_vintage(_text(row, "vintage")),
        _text(row, "appellation"),
        _text(row, "color"),
    )

    connection.execute(
        """
        INSERT OR IGNORE INTO wine (producer, cuvee, vintage, appellation, color)
        VALUES (?, ?, ?, ?, ?)
        """,
        values,
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
            values,
        ).fetchone()["id"]
    )


def _get_or_create_wine_variant(connection, wine_id: int, bottle_format: str) -> int:
    connection.execute(
        """
        INSERT OR IGNORE INTO wine_variant (wine_id, format)
        VALUES (?, ?)
        """,
        (wine_id, bottle_format),
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


def _get_or_create_import_location(
    connection, row: dict[str, object], rules: list[LocationMappingRule]
) -> int | None:
    location_name = _text(row, "location")
    explicit_cellar_name = _text(row, "cellar")

    if not explicit_cellar_name and not location_name:
        return None

    cellar_name = explicit_cellar_name or resolve_cellar_from_location(location_name, rules)

    cellar_id = _get_or_create_cellar(connection, cellar_name)
    return _get_or_create_location(connection, cellar_id, location_name)


def _get_or_create_cellar(connection, name: str) -> int:
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


def _get_or_create_location(connection, cellar_id: int, name: str) -> int:
    connection.execute(
        """
        INSERT OR IGNORE INTO location (cellar_id, name)
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
              AND COALESCE(parent_location_id, -1) = -1
              AND name = ?
            """,
            (cellar_id, name),
        ).fetchone()["id"]
    )


def _create_bottle(connection, wine_variant_id: int, import_session_id: int) -> int:
    cursor = connection.execute(
        """
        INSERT INTO bottle (wine_variant_id, import_session_id)
        VALUES (?, ?)
        """,
        (wine_variant_id, import_session_id),
    )
    return int(cursor.lastrowid)


def _create_initial_location_history(connection, bottle_id: int, location_id: int) -> None:
    connection.execute(
        """
        INSERT INTO bottle_location_history (bottle_id, location_id)
        VALUES (?, ?)
        """,
        (bottle_id, location_id),
    )


def _text(row: dict[str, object], field: str) -> str:
    value = row.get(field)
    if value is None:
        return ""
    return str(value).strip()


def _canonicalize_vintage(value: str) -> str:
    text = value.strip()
    if not text:
        return "NV"

    normalized = text.casefold().replace("é", "e").replace("è", "e").replace("ê", "e")

    if normalized in ("nv", "nm", "non vintage", "non millesime", "non-millesime"):
        return "NV"

    return text


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()
