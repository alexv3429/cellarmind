from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cellarmind.storage.cellars import CellarProfile, list_cellars
from cellarmind.storage.placement import PlacementIssue, audit_placement


@dataclass(frozen=True)
class TransferSuggestion:
    action: str
    bottle_id: int
    producer: str
    cuvee: str
    vintage: str
    bottle_format: str
    current_cellar: str | None
    current_location: str | None
    target_cellar: str | None
    target_purpose: str | None
    reason: str


@dataclass(frozen=True)
class TransferPlan:
    suggestions: tuple[TransferSuggestion, ...]


def plan_transfers(
    database_path: Path,
    *,
    as_of_year: int | None = None,
    limit: int = 50,
) -> TransferPlan:
    placement_audit = audit_placement(database_path, as_of_year=as_of_year)
    cellars = list_cellars(database_path)

    suggestions: list[TransferSuggestion] = []

    for issue in placement_audit.issues:
        suggestion = _suggest_transfer(
            issue,
            cellars=cellars,
            as_of_year=placement_audit.summary.as_of_year,
        )

        if suggestion is not None:
            suggestions.append(suggestion)

    return TransferPlan(
        suggestions=tuple(suggestions[:limit]),
    )


def _suggest_transfer(
    issue: PlacementIssue,
    *,
    cellars: tuple[CellarProfile, ...],
    as_of_year: int,
) -> TransferSuggestion | None:
    if issue.issue_type == "too_young_in_drink_soon_cellar":
        target = _find_target_cellar(
            cellars,
            purpose="aging",
            current_cellar=issue.cellar,
        )

        return _suggestion(
            issue,
            action="move" if target is not None else "review",
            target=target,
            target_purpose="aging",
            reason="Bottle is too young for a drink-soon cellar.",
        )

    if issue.issue_type in {"ready_in_aging_cellar", "overdue_in_aging_cellar"}:
        target = _find_target_cellar(
            cellars,
            purpose="drink_soon",
            current_cellar=issue.cellar,
        )

        return _suggestion(
            issue,
            action="move" if target is not None else "review",
            target=target,
            target_purpose="drink_soon",
            reason="Bottle is ready or overdue but remains in an aging cellar.",
        )

    if issue.issue_type == "bottle_in_staging_cellar":
        target_purpose = _target_purpose_for_window(
            issue,
            as_of_year=as_of_year,
        )
        target = _find_target_cellar(
            cellars,
            purpose=target_purpose,
            current_cellar=issue.cellar,
        )

        return _suggestion(
            issue,
            action="move" if target is not None else "review",
            target=target,
            target_purpose=target_purpose,
            reason="Bottle is in a staging cellar and should be placed.",
        )

    if issue.issue_type == "bottle_in_overflow_cellar":
        target_purpose = _target_purpose_for_window(
            issue,
            as_of_year=as_of_year,
        )
        target = _find_target_cellar(
            cellars,
            purpose=target_purpose,
            current_cellar=issue.cellar,
        )

        return _suggestion(
            issue,
            action="move" if target is not None else "review",
            target=target,
            target_purpose=target_purpose,
            reason="Bottle is in an overflow cellar and should be reviewed.",
        )

    if issue.issue_type == "missing_location":
        return _suggestion(
            issue,
            action="review",
            target=None,
            target_purpose=None,
            reason="Bottle has no active location.",
        )

    return None


def _target_purpose_for_window(
    issue: PlacementIssue,
    *,
    as_of_year: int,
) -> str:
    drink_from = issue.personal_drink_from_year
    drink_until = issue.personal_drink_until_year

    if drink_from is None and drink_until is None:
        return "mixed"

    if drink_from is not None and as_of_year < drink_from:
        return "aging"

    return "drink_soon"


def _has_available_capacity(cellar: CellarProfile) -> bool:
    if cellar.capacity_estimate is None:
        return True

    return cellar.active_bottles < cellar.capacity_estimate


def _find_target_cellar(
    cellars: tuple[CellarProfile, ...],
    *,
    purpose: str,
    current_cellar: str | None,
) -> CellarProfile | None:
    candidates = [
        cellar
        for cellar in cellars
        if cellar.purpose == purpose
        and cellar.name != current_cellar
        and cellar.occupancy_status != "over_capacity"
        and _has_available_capacity(cellar)
    ]

    if not candidates:
        return None

    return sorted(
        candidates,
        key=lambda cellar: (
            _occupancy_sort_value(cellar.occupancy_status),
            cellar.active_bottles,
            cellar.name,
        ),
    )[0]


def _occupancy_sort_value(occupancy_status: str) -> int:
    order = {
        "ok": 0,
        "unknown": 1,
        "near_capacity": 2,
        "over_capacity": 3,
    }

    return order.get(occupancy_status, 99)


def _suggestion(
    issue: PlacementIssue,
    *,
    action: str,
    target: CellarProfile | None,
    target_purpose: str | None,
    reason: str,
) -> TransferSuggestion:
    return TransferSuggestion(
        action=action,
        bottle_id=issue.bottle_id,
        producer=issue.producer,
        cuvee=issue.cuvee,
        vintage=issue.vintage,
        bottle_format=issue.bottle_format,
        current_cellar=issue.cellar,
        current_location=issue.location,
        target_cellar=target.name if target is not None else None,
        target_purpose=target_purpose,
        reason=reason,
    )
