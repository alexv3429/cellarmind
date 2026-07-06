from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 1

EXPECTED_TABLES: tuple[str, ...] = (
    "import_session",
    "wine",
    "wine_variant",
    "bottle",
    "cellar",
    "location",
    "bottle_location_history",
)

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS import_session (
    id INTEGER PRIMARY KEY,
    source_file TEXT,
    source_hash TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_count INTEGER NOT NULL DEFAULT 0 CHECK (row_count >= 0),
    created_bottle_count INTEGER NOT NULL DEFAULT 0 CHECK (created_bottle_count >= 0),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS wine (
    id INTEGER PRIMARY KEY,
    producer TEXT NOT NULL,
    cuvee TEXT NOT NULL,
    vintage TEXT NOT NULL,
    appellation TEXT NOT NULL,
    color TEXT NOT NULL,
    country TEXT,
    region TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (producer, cuvee, vintage, appellation, color)
);

CREATE TABLE IF NOT EXISTS wine_variant (
    id INTEGER PRIMARY KEY,
    wine_id INTEGER NOT NULL,
    format TEXT NOT NULL DEFAULT '750ml',
    personal_drink_from_year INTEGER,
    personal_drink_until_year INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (wine_id, format),
    FOREIGN KEY (wine_id) REFERENCES wine (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS bottle (
    id INTEGER PRIMARY KEY,
    wine_variant_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'in_cellar',
    import_session_id INTEGER,
    purchase_date TEXT,
    purchase_price REAL,
    purchase_currency TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        status IN (
            'in_cellar',
            'opened',
            'consumed',
            'sold',
            'gifted',
            'lost'
        )
    ),
    FOREIGN KEY (wine_variant_id) REFERENCES wine_variant (id) ON DELETE RESTRICT,
    FOREIGN KEY (import_session_id) REFERENCES import_session (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS cellar (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    purpose TEXT NOT NULL DEFAULT 'mixed',
    capacity_estimate INTEGER,
    capacity_warning_threshold INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        purpose IN (
            'aging',
            'drinking',
            'mixed',
            'staging',
            'overflow',
            'other'
        )
    ),
    CHECK (
        capacity_estimate IS NULL OR capacity_estimate >= 0
    ),
    CHECK (
        capacity_warning_threshold IS NULL OR capacity_warning_threshold >= 0
    )
);

CREATE TABLE IF NOT EXISTS location (
    id INTEGER PRIMARY KEY,
    cellar_id INTEGER NOT NULL,
    parent_location_id INTEGER,
    name TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cellar_id) REFERENCES cellar (id) ON DELETE CASCADE,
    FOREIGN KEY (parent_location_id) REFERENCES location (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_location_unique
ON location (
    cellar_id,
    COALESCE(parent_location_id, -1),
    name
);

CREATE TABLE IF NOT EXISTS bottle_location_history (
    id INTEGER PRIMARY KEY,
    bottle_id INTEGER NOT NULL,
    location_id INTEGER NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (bottle_id) REFERENCES bottle (id) ON DELETE CASCADE,
    FOREIGN KEY (location_id) REFERENCES location (id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_bottle_wine_variant_id
ON bottle (wine_variant_id);

CREATE INDEX IF NOT EXISTS idx_bottle_status
ON bottle (status);

CREATE INDEX IF NOT EXISTS idx_bottle_location_history_bottle_id
ON bottle_location_history (bottle_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_bottle_location_history_active
ON bottle_location_history (bottle_id)
WHERE ended_at IS NULL;

PRAGMA user_version = 1;
"""


@dataclass(frozen=True)
class DatabaseInitResult:
    path: Path
    schema_version: int
    tables: tuple[str, ...]


def connect_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(path: Path) -> DatabaseInitResult:
    path.parent.mkdir(parents=True, exist_ok=True)

    with connect_database(path) as connection:
        connection.executescript(SCHEMA_SQL)
        schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        tables = tuple(
            row["name"]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                ORDER BY name
                """
            )
        )

    return DatabaseInitResult(
        path=path,
        schema_version=schema_version,
        tables=tables,
    )
