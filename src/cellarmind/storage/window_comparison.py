from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection

from cellarmind.storage.reference_windows import ensure_reference_window_schema
from cellarmind.storage.sqlite import connect_database

ALIGNED_CATEGORY = "aligned"
MISSING_REFERENCE_CATEGORY = "missing_reference_window"
MISSING_PERSONAL_CATEGORY = "missing_personal_window"
BOTH_MISSING_CATEGORY = "missing_personal_and_reference"
PERSONAL_EARLIER_CATEGORY = "personal_earlier_than_reference"
PERSONAL_LATER_CATEGORY = "personal_later_than_reference"
LARGE_DISAGREEMENT_CATEGORY = "large_disagreement"
PARTIAL_COMPARISON_CATEGORY = "partial_comparison"

HIGH_SEVERITY = "high"
MEDIUM_SEVERITY = "medium"
LOW_SEVERITY = "low"
INFO_SEVERITY = "info"


@dataclass(frozen=True)
class WindowComparisonSummary:
    active_variants: int
    aligned: int
    missing_reference_windows: int
    missing_personal_windows: int
    missing_personal_and_reference: int
    personal_earlier_than_reference: int
    personal_later_than_reference: int
    large_disagreements: int
    partial_comparisons: int


@dataclass(frozen=True)
class WindowComparisonRow:
    category: str
    severity: str
    wine_id: int
    wine_variant_id: int
    active_bottle_count: int
    producer: str
    cuvee: str
    vintage: str
    bottle_format: str
    personal_drink_from_year: int | None
    personal_drink_until_year: int | None
    reference_id: int | None
    reference_source_name: str | None
    reference_source_url: str | None
    reference_drink_from_year: int | None
    reference_drink_until_year: int | None
    reference_confidence: str | None
    note: str


@dataclass(frozen=True)
class WindowComparisonReport:
    summary: WindowComparisonSummary
    rows: tuple[WindowComparisonRow, ...]


@dataclass(frozen=True)
class _ReferenceWindow:
    id: int
    source_name: str
    source_url: str | None
    drink_from_year: int | None
    drink_until_year: int | None
    confidence: str


def compare_drinking_windows(
    database_path: Path,
    *,
    tolerance_years: int = 2,
    limit: int | None = None,
) -> WindowComparisonReport:
    if not database_path.exists():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    if tolerance_years < 0:
        raise ValueError("tolerance_years must be greater than or equal to 0.")

    if limit is not None and limit < 1:
        raise ValueError("Limit must be at least 1.")

    with connect_database(database_path) as connection:
        ensure_reference_window_schema(connection)
        variant_rows = _fetch_active_variant_rows(connection)

        comparisons = tuple(
            _compare_variant_row(
                row,
                reference=_fetch_best_reference_for_wine(
                    connection,
                    wine_id=int(row["wine_id"]),
                ),
                tolerance_years=tolerance_years,
            )
            for row in variant_rows
        )

    sorted_rows = tuple(sorted(comparisons, key=_comparison_sort_key))

    if limit is not None:
        sorted_rows = sorted_rows[:limit]

    summary = WindowComparisonSummary(
        active_variants=len(comparisons),
        aligned=sum(1 for row in comparisons if row.category == ALIGNED_CATEGORY),
        missing_reference_windows=sum(
            1 for row in comparisons if row.category == MISSING_REFERENCE_CATEGORY
        ),
        missing_personal_windows=sum(
            1 for row in comparisons if row.category == MISSING_PERSONAL_CATEGORY
        ),
        missing_personal_and_reference=sum(
            1 for row in comparisons if row.category == BOTH_MISSING_CATEGORY
        ),
        personal_earlier_than_reference=sum(
            1 for row in comparisons if row.category == PERSONAL_EARLIER_CATEGORY
        ),
        personal_later_than_reference=sum(
            1 for row in comparisons if row.category == PERSONAL_LATER_CATEGORY
        ),
        large_disagreements=sum(
            1 for row in comparisons if row.category == LARGE_DISAGREEMENT_CATEGORY
        ),
        partial_comparisons=sum(
            1 for row in comparisons if row.category == PARTIAL_COMPARISON_CATEGORY
        ),
    )

    return WindowComparisonReport(
        summary=summary,
        rows=sorted_rows,
    )


def _fetch_active_variant_rows(connection: Connection):
    return connection.execute(
        """
        SELECT
            wine.id AS wine_id,
            wine_variant.id AS wine_variant_id,
            wine.producer,
            wine.cuvee,
            wine.vintage,
            wine_variant.format AS bottle_format,
            wine_variant.personal_drink_from_year,
            wine_variant.personal_drink_until_year,
            COUNT(bottle.id) AS active_bottle_count
        FROM wine_variant
        JOIN wine
            ON wine.id = wine_variant.wine_id
        JOIN bottle
            ON bottle.wine_variant_id = wine_variant.id
        WHERE bottle.status IN ('in_cellar', 'opened')
        GROUP BY
            wine.id,
            wine_variant.id,
            wine.producer,
            wine.cuvee,
            wine.vintage,
            wine_variant.format,
            wine_variant.personal_drink_from_year,
            wine_variant.personal_drink_until_year
        ORDER BY wine.producer, wine.cuvee, wine.vintage, wine_variant.format
        """
    ).fetchall()


def _fetch_best_reference_for_wine(
    connection: Connection,
    *,
    wine_id: int,
) -> _ReferenceWindow | None:
    row = connection.execute(
        """
        SELECT
            id,
            source_name,
            source_url,
            drink_from_year,
            drink_until_year,
            confidence
        FROM reference_drinking_window
        WHERE wine_id = ?
        ORDER BY
            CASE confidence
                WHEN 'high' THEN 0
                WHEN 'medium' THEN 1
                WHEN 'low' THEN 2
                ELSE 3
            END,
            created_at DESC,
            id DESC
        LIMIT 1
        """,
        (wine_id,),
    ).fetchone()

    if row is None:
        return None

    return _ReferenceWindow(
        id=int(row["id"]),
        source_name=row["source_name"],
        source_url=row["source_url"],
        drink_from_year=row["drink_from_year"],
        drink_until_year=row["drink_until_year"],
        confidence=row["confidence"],
    )


def _compare_variant_row(
    row,
    *,
    reference: _ReferenceWindow | None,
    tolerance_years: int,
) -> WindowComparisonRow:
    personal_from = row["personal_drink_from_year"]
    personal_until = row["personal_drink_until_year"]
    personal_exists = personal_from is not None or personal_until is not None

    if reference is None:
        if personal_exists:
            return _comparison_row(
                row,
                reference=None,
                category=MISSING_REFERENCE_CATEGORY,
                severity=LOW_SEVERITY,
                note="Personal window exists but no reference window is available.",
            )

        return _comparison_row(
            row,
            reference=None,
            category=BOTH_MISSING_CATEGORY,
            severity=MEDIUM_SEVERITY,
            note="Neither personal nor reference window is available.",
        )

    if not personal_exists:
        return _comparison_row(
            row,
            reference=reference,
            category=MISSING_PERSONAL_CATEGORY,
            severity=HIGH_SEVERITY,
            note="Reference window exists but personal window is missing.",
        )

    category, severity, note = _compare_windows(
        personal_from=personal_from,
        personal_until=personal_until,
        reference_from=reference.drink_from_year,
        reference_until=reference.drink_until_year,
        tolerance_years=tolerance_years,
    )

    return _comparison_row(
        row,
        reference=reference,
        category=category,
        severity=severity,
        note=note,
    )


def _compare_windows(
    *,
    personal_from: int | None,
    personal_until: int | None,
    reference_from: int | None,
    reference_until: int | None,
    tolerance_years: int,
) -> tuple[str, str, str]:
    if (
        personal_until is not None
        and reference_from is not None
        and personal_until < reference_from
    ):
        return (
            PERSONAL_EARLIER_CATEGORY,
            HIGH_SEVERITY,
            "Personal window ends before the reference window starts.",
        )

    if (
        personal_from is not None
        and reference_until is not None
        and personal_from > reference_until
    ):
        return (
            PERSONAL_LATER_CATEGORY,
            HIGH_SEVERITY,
            "Personal window starts after the reference window ends.",
        )

    boundary_deltas = _boundary_deltas(
        personal_from=personal_from,
        personal_until=personal_until,
        reference_from=reference_from,
        reference_until=reference_until,
    )

    if boundary_deltas and max(abs(delta) for delta in boundary_deltas) > tolerance_years:
        return (
            LARGE_DISAGREEMENT_CATEGORY,
            MEDIUM_SEVERITY,
            ("Personal and reference windows overlap, but differ beyond the tolerance."),
        )

    if (
        personal_from is None
        or personal_until is None
        or reference_from is None
        or reference_until is None
    ):
        return (
            PARTIAL_COMPARISON_CATEGORY,
            LOW_SEVERITY,
            "Only a partial comparison is possible.",
        )

    return (
        ALIGNED_CATEGORY,
        INFO_SEVERITY,
        "Personal and reference windows are aligned within tolerance.",
    )


def _boundary_deltas(
    *,
    personal_from: int | None,
    personal_until: int | None,
    reference_from: int | None,
    reference_until: int | None,
) -> tuple[int, ...]:
    deltas: list[int] = []

    if personal_from is not None and reference_from is not None:
        deltas.append(personal_from - reference_from)

    if personal_until is not None and reference_until is not None:
        deltas.append(personal_until - reference_until)

    return tuple(deltas)


def _comparison_row(
    row,
    *,
    reference: _ReferenceWindow | None,
    category: str,
    severity: str,
    note: str,
) -> WindowComparisonRow:
    return WindowComparisonRow(
        category=category,
        severity=severity,
        wine_id=int(row["wine_id"]),
        wine_variant_id=int(row["wine_variant_id"]),
        active_bottle_count=int(row["active_bottle_count"]),
        producer=row["producer"],
        cuvee=row["cuvee"],
        vintage=row["vintage"],
        bottle_format=row["bottle_format"],
        personal_drink_from_year=row["personal_drink_from_year"],
        personal_drink_until_year=row["personal_drink_until_year"],
        reference_id=reference.id if reference is not None else None,
        reference_source_name=reference.source_name if reference is not None else None,
        reference_source_url=reference.source_url if reference is not None else None,
        reference_drink_from_year=(reference.drink_from_year if reference is not None else None),
        reference_drink_until_year=(reference.drink_until_year if reference is not None else None),
        reference_confidence=reference.confidence if reference is not None else None,
        note=note,
    )


def _comparison_sort_key(row: WindowComparisonRow) -> tuple[int, int, str, str, int]:
    severity_order = {
        HIGH_SEVERITY: 0,
        MEDIUM_SEVERITY: 1,
        LOW_SEVERITY: 2,
        INFO_SEVERITY: 3,
    }

    category_order = {
        MISSING_PERSONAL_CATEGORY: 0,
        PERSONAL_EARLIER_CATEGORY: 1,
        PERSONAL_LATER_CATEGORY: 2,
        LARGE_DISAGREEMENT_CATEGORY: 3,
        BOTH_MISSING_CATEGORY: 4,
        MISSING_REFERENCE_CATEGORY: 5,
        PARTIAL_COMPARISON_CATEGORY: 6,
        ALIGNED_CATEGORY: 7,
    }

    return (
        severity_order.get(row.severity, 99),
        category_order.get(row.category, 99),
        row.producer,
        row.cuvee,
        row.wine_variant_id,
    )
