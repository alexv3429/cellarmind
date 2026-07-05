from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import polars as pl

REQUIRED_FIELDS: tuple[str, ...] = (
    "producer",
    "cuvee",
    "vintage",
    "appellation",
    "color",
)

OPTIONAL_FIELDS: tuple[str, ...] = (
    "format",
    "quantity",
    "cellar",
    "location",
)

CANONICAL_FIELDS: tuple[str, ...] = REQUIRED_FIELDS + OPTIONAL_FIELDS

COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "producer": ("producer", "producteur"),
    "cuvee": ("cuvee", "cuvée", "wine", "vin", "cuvée / vin", "cuvee / vin"),
    "vintage": (
        "vintage",
        "millésime",
        "millesime",
        "année prod",
        "annee prod",
        "année production",
        "annee production",
        "année",
        "annee",
        "year",
    ),
    "appellation": ("appellation",),
    "color": (
        "color",
        "couleur",
        "vignoble couleur",
        "vin couleur",
    ),
    "format": (
        "format",
        "fmt",
        "bottle format",
        "format bouteille",
        "contenance",
        "contenant",
        "taille",
    ),
    "quantity": (
        "quantity",
        "qty",
        "quantité",
        "quantite",
        "nombre",
        "nb",
    ),
    "cellar": ("cellar", "cave"),
    "location": (
        "location",
        "emplacement",
        "place",
        "casier",
    ),
}


@dataclass(frozen=True)
class CsvSchemaValidation:
    path: Path
    columns: tuple[str, ...]
    mapping: dict[str, str]
    missing: tuple[str, ...]
    conflicts: dict[str, tuple[str, ...]]

    @property
    def valid(self) -> bool:
        return not self.missing and not self.conflicts


def normalize_column_name(value: str) -> str:
    without_accents = "".join(
        char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char)
    )
    normalized = without_accents.casefold().strip()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def validate_csv_schema(path: Path) -> CsvSchemaValidation:
    df = pl.read_csv(path, n_rows=0, infer_schema_length=0)
    columns = tuple(df.columns)

    normalized_columns: dict[str, list[str]] = {}
    for column in columns:
        normalized_columns.setdefault(normalize_column_name(column), []).append(column)

    mapping: dict[str, str] = {}
    missing: list[str] = []
    conflicts: dict[str, tuple[str, ...]] = {}

    for canonical_name in CANONICAL_FIELDS:
        aliases = COLUMN_ALIASES[canonical_name]
        matches: list[str] = []

        for alias in aliases:
            matches.extend(normalized_columns.get(normalize_column_name(alias), []))

        unique_matches = tuple(dict.fromkeys(matches))

        if len(unique_matches) == 0:
            if canonical_name in REQUIRED_FIELDS:
                missing.append(canonical_name)
        elif len(unique_matches) == 1:
            mapping[canonical_name] = unique_matches[0]
        else:
            conflicts[canonical_name] = unique_matches

    return CsvSchemaValidation(
        path=path,
        columns=columns,
        mapping=mapping,
        missing=tuple(missing),
        conflicts=conflicts,
    )
