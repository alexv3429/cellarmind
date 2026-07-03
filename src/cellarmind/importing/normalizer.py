from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from cellarmind.importing.schema import CANONICAL_FIELDS, validate_csv_schema

DEFAULT_FORMAT = "750ml"
DEFAULT_QUANTITY = 1

FORMAT_ALIASES: dict[str, str] = {
    "bottle": "750ml",
    "standard": "750ml",
    "bouteille": "750ml",
    "half": "375ml",
    "half bottle": "375ml",
    "half_bottle": "375ml",
    "demi": "375ml",
    "magnum": "1500ml",
    "jeroboam": "3000ml",
    "imperial": "6000ml",
}


@dataclass(frozen=True)
class CanonicalCsvResult:
    input_path: Path
    output_path: Path
    rows: int
    columns: tuple[str, ...]
    mapping: dict[str, str]


def default_canonical_output_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}.canonical.csv")


def canonicalize_format(value: object | None) -> str:
    if value is None:
        return DEFAULT_FORMAT

    text = str(value).strip().lower().replace(",", ".")
    if not text:
        return DEFAULT_FORMAT

    compact_text = re.sub(r"[\s_-]+", "", text)

    explicit_volume = re.fullmatch(r"(\d+(?:\.\d+)?)(ml|cl|l)", compact_text)
    if explicit_volume:
        amount = float(explicit_volume.group(1))
        unit = explicit_volume.group(2)

        if unit == "ml":
            volume_ml = amount
        elif unit == "cl":
            volume_ml = amount * 10
        else:
            volume_ml = amount * 1000

        return f"{int(volume_ml)}ml"

    alias_key = re.sub(r"[_-]+", " ", text)
    alias_key = re.sub(r"\s+", " ", alias_key).strip()

    if alias_key in FORMAT_ALIASES:
        return FORMAT_ALIASES[alias_key]

    raise ValueError(f"Unknown bottle format: {value!r}")


def canonicalize_quantity(value: object | None) -> int:
    if value is None:
        return DEFAULT_QUANTITY

    text = str(value).strip().replace(",", ".")
    if not text:
        return DEFAULT_QUANTITY

    try:
        quantity_float = float(text)
    except ValueError as exc:
        raise ValueError(f"Invalid quantity: {value!r}") from exc

    if not quantity_float.is_integer():
        raise ValueError(f"Quantity must be an integer: {value!r}")

    quantity = int(quantity_float)

    if quantity < 1:
        raise ValueError(f"Quantity must be greater than or equal to 1: {value!r}")

    return quantity


def _clean_string_series(df: pl.DataFrame, column: str, name: str) -> pl.Series:
    return df.get_column(column).cast(pl.Utf8).str.strip_chars().alias(name)


def _default_string_series(name: str, rows: int, value: str = "") -> pl.Series:
    return pl.Series(name, [value] * rows)


def normalize_csv_to_canonical(
    input_path: Path,
    output_path: Path | None = None,
) -> CanonicalCsvResult:
    validation = validate_csv_schema(input_path)

    if not validation.valid:
        missing = ", ".join(validation.missing)
        conflicts = ", ".join(validation.conflicts)
        details = []
        if missing:
            details.append(f"missing fields: {missing}")
        if conflicts:
            details.append(f"conflicting fields: {conflicts}")
        raise ValueError(f"Invalid CSV schema ({'; '.join(details)})")

    final_output_path = output_path or default_canonical_output_path(input_path)

    df = pl.read_csv(input_path, infer_schema_length=0)

    columns: list[pl.Series] = []

    for field in CANONICAL_FIELDS:
        source_column = validation.mapping.get(field)

        if field == "format":
            if source_column is None:
                columns.append(_default_string_series("format", df.height, DEFAULT_FORMAT))
            else:
                columns.append(
                    pl.Series(
                        "format",
                        [
                            canonicalize_format(value)
                            for value in _clean_string_series(df, source_column, field)
                        ],
                    )
                )
            continue

        if field == "quantity":
            if source_column is None:
                columns.append(pl.Series("quantity", [DEFAULT_QUANTITY] * df.height))
            else:
                columns.append(
                    pl.Series(
                        "quantity",
                        [
                            canonicalize_quantity(value)
                            for value in _clean_string_series(df, source_column, field)
                        ],
                    )
                )
            continue

        if source_column is None:
            columns.append(_default_string_series(field, df.height))
        else:
            columns.append(_clean_string_series(df, source_column, field))

    canonical_df = pl.DataFrame(columns)

    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_df.write_csv(final_output_path)

    return CanonicalCsvResult(
        input_path=input_path,
        output_path=final_output_path,
        rows=canonical_df.height,
        columns=tuple(canonical_df.columns),
        mapping=validation.mapping,
    )
