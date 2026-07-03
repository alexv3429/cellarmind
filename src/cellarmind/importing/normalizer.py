from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl

from cellarmind.importing.schema import REQUIRED_FIELDS, validate_csv_schema


@dataclass(frozen=True)
class CanonicalCsvResult:
    input_path: Path
    output_path: Path
    rows: int
    columns: tuple[str, ...]
    mapping: dict[str, str]


def default_canonical_output_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}.canonical.csv")


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

    canonical_df = df.select(
        [
            pl.col(validation.mapping[field]).str.strip_chars().alias(field)
            for field in REQUIRED_FIELDS
        ]
    )

    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_df.write_csv(final_output_path)

    return CanonicalCsvResult(
        input_path=input_path,
        output_path=final_output_path,
        rows=canonical_df.height,
        columns=tuple(canonical_df.columns),
        mapping=validation.mapping,
    )
