from pathlib import Path

import polars as pl


def inspect_csv(path: Path) -> dict[str, object]:
    df = pl.read_csv(path, infer_schema_length=0)

    result: dict[str, object] = {
        "path": str(path),
        "rows": df.height,
        "columns": len(df.columns),
        "column_names": df.columns,
    }

    for label, candidates in {
        "vintages": ["Année Prod", "Vintage", "Millésime"],
        "producers": ["Producteur", "Producer"],
        "appellations": ["Appellation"],
        "colors": ["Couleur", "Color"],
    }.items():
        col = next((c for c in candidates if c in df.columns), None)
        if col is None:
            result[label] = None
            continue

        values = df.get_column(col).drop_nulls()
        result[label] = {
            "column": col,
            "unique": values.n_unique(),
        }

        if label == "vintages":
            years = values.cast(pl.Int64, strict=False).drop_nulls()
            result[label]["min"] = years.min()
            result[label]["max"] = years.max()

        if label in {"producers", "appellations", "colors"}:
            top = df.group_by(col).len().sort("len", descending=True).head(10).rows()
            result[label]["top"] = top

    return result
