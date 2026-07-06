from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from sqlite3 import Connection

from cellarmind.storage.cellars import CellarProfile, list_cellars
from cellarmind.storage.sqlite import connect_database

ACTIVE_BOTTLE_STATUSES = ("in_cellar", "opened")


@dataclass(frozen=True)
class PlacementSummary:
    as_of_year: int
    active_bottles: int
    bottles_without_location: int
    cellars_near_capacity: int
    cellars_over_capacity: int
    bottles_in_staging_cellars: int
    bottles_in_overflow_cellars: int
    too_young_bottles_in_drink_soon_cellars: int
    ready_or_overdue_bottles_in_aging_cellars: int
    unknown_window_bottles_in_drink_soon_cellars: int


@dataclass(frozen=True)
class CellarOccupancyRow:
    name: str
    purpose: str
    active_bottles: int
    capacity_estimate: int | None
    capacity_warning_threshold: int | None
    occupancy_status: str
    notes: str | None


@dataclass(frozen=True)
class PlacementIssue:
    issue_type: str
    severity: str
    bottle_id: int
    producer: str
    cuvee: str
    vintage: str
    bottle_format: str
    cellar: str | None
    location: str | None
    personal_drink_from_year: int | None
    personal_drink_until_year: int | None
    note: str


@dataclass(frozen=True)
class PlacementAudit:
    summary: PlacementSummary
    cellar_occupancy: tuple[CellarOccupancyRow, ...]
    issues: tuple[PlacementIssue, ...]


def audit_placement(
    database_path: Path,
    *,
    as_of_year: int | None = None,
) -> PlacementAudit:
    if not database_path.exists():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    resolved_year = as_of_year if as_of_year is not None else date.today().year

    cellar_profiles = list_cellars(database_path)

    with connect_database(database_path) as connection:
        bottle_rows = _fetch_active_bottle_rows(connection)

    issues = tuple(
        issue
        for row in bottle_rows
        for issue in _classify_bottle_placement(row, as_of_year=resolved_year)
    )

    cellar_occupancy = tuple(_to_cellar_occupancy_row(cellar) for cellar in cellar_profiles)

    summary = PlacementSummary(
        as_of_year=resolved_year,
        active_bottles=len(bottle_rows),
        bottles_without_location=sum(
            1 for issue in issues if issue.issue_type == "missing_location"
        ),
        cellars_near_capacity=sum(
            1 for cellar in cellar_occupancy if cellar.occupancy_status == "near_capacity"
        ),
        cellars_over_capacity=sum(
            1 for cellar in cellar_occupancy if cellar.occupancy_status == "over_capacity"
        ),
        bottles_in_staging_cellars=sum(
            1 for issue in issues if issue.issue_type == "bottle_in_staging_cellar"
        ),
        bottles_in_overflow_cellars=sum(
            1 for issue in issues if issue.issue_type == "bottle_in_overflow_cellar"
        ),
        too_young_bottles_in_drink_soon_cellars=sum(
            1 for issue in issues if issue.issue_type == "too_young_in_drink_soon_cellar"
        ),
        ready_or_overdue_bottles_in_aging_cellars=sum(
            1
            for issue in issues
            if issue.issue_type
            in {
                "ready_in_aging_cellar",
                "overdue_in_aging_cellar",
            }
        ),
        unknown_window_bottles_in_drink_soon_cellars=sum(
            1 for issue in issues if issue.issue_type == "unknown_window_in_drink_soon_cellar"
        ),
    )

    return PlacementAudit(
        summary=summary,
        cellar_occupancy=cellar_occupancy,
        issues=tuple(sorted(issues, key=_issue_sort_key)),
    )


def _fetch_active_bottle_rows(connection: Connection):
    return connection.execute(
        """
        SELECT
            bottle.id AS bottle_id,
            wine.producer,
            wine.cuvee,
            wine.vintage,
            wine_variant.format AS bottle_format,
            wine_variant.personal_drink_from_year,
            wine_variant.personal_drink_until_year,
            cellar.name AS cellar_name,
            cellar.purpose AS cellar_purpose,
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


def _classify_bottle_placement(row, *, as_of_year: int) -> tuple[PlacementIssue, ...]:
    issues: list[PlacementIssue] = []

    cellar_name = row["cellar_name"]
    cellar_purpose = row["cellar_purpose"]

    if cellar_name is None:
        issues.append(
            _issue(
                row,
                issue_type="missing_location",
                severity="high",
                note="Bottle has no active location.",
            )
        )
        return tuple(issues)

    if cellar_purpose == "staging":
        issues.append(
            _issue(
                row,
                issue_type="bottle_in_staging_cellar",
                severity="medium",
                note="Bottle is in a staging cellar and should be reviewed or stored.",
            )
        )

    if cellar_purpose == "overflow":
        issues.append(
            _issue(
                row,
                issue_type="bottle_in_overflow_cellar",
                severity="low",
                note="Bottle is in an overflow cellar.",
            )
        )

    drink_from = row["personal_drink_from_year"]
    drink_until = row["personal_drink_until_year"]

    if cellar_purpose == "drink_soon":
        if drink_from is None and drink_until is None:
            issues.append(
                _issue(
                    row,
                    issue_type="unknown_window_in_drink_soon_cellar",
                    severity="medium",
                    note="Bottle is in a drink-soon cellar but has no personal drinking window.",
                )
            )
        elif drink_from is not None and as_of_year < drink_from:
            issues.append(
                _issue(
                    row,
                    issue_type="too_young_in_drink_soon_cellar",
                    severity="high",
                    note=(f"Bottle is too young for a drink-soon cellar as of {as_of_year}."),
                )
            )

    if cellar_purpose == "aging":
        if drink_until is not None and as_of_year > drink_until:
            issues.append(
                _issue(
                    row,
                    issue_type="overdue_in_aging_cellar",
                    severity="high",
                    note=(
                        "Bottle is past its personal drinking window "
                        "but remains in an aging cellar."
                    ),
                )
            )
        elif drink_from is not None and as_of_year >= drink_from:
            issues.append(
                _issue(
                    row,
                    issue_type="ready_in_aging_cellar",
                    severity="medium",
                    note=(
                        "Bottle is ready according to its personal drinking window "
                        "but remains in an aging cellar."
                    ),
                )
            )

    return tuple(issues)


def _issue(
    row,
    *,
    issue_type: str,
    severity: str,
    note: str,
) -> PlacementIssue:
    return PlacementIssue(
        issue_type=issue_type,
        severity=severity,
        bottle_id=int(row["bottle_id"]),
        producer=row["producer"],
        cuvee=row["cuvee"],
        vintage=row["vintage"],
        bottle_format=row["bottle_format"],
        cellar=row["cellar_name"],
        location=row["location_name"],
        personal_drink_from_year=row["personal_drink_from_year"],
        personal_drink_until_year=row["personal_drink_until_year"],
        note=note,
    )


def _to_cellar_occupancy_row(cellar: CellarProfile) -> CellarOccupancyRow:
    return CellarOccupancyRow(
        name=cellar.name,
        purpose=cellar.purpose,
        active_bottles=cellar.active_bottles,
        capacity_estimate=cellar.capacity_estimate,
        capacity_warning_threshold=cellar.capacity_warning_threshold,
        occupancy_status=cellar.occupancy_status,
        notes=cellar.notes,
    )


def _issue_sort_key(issue: PlacementIssue) -> tuple[int, str, int]:
    severity_order = {
        "high": 0,
        "medium": 1,
        "low": 2,
    }

    return (
        severity_order.get(issue.severity, 99),
        issue.issue_type,
        issue.bottle_id,
    )
