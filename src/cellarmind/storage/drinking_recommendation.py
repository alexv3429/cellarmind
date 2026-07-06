from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from sqlite3 import Connection

from cellarmind.storage.sqlite import connect_database

DRINK_NOW_ACTION = "drink_now"
CONSIDER_DRINKING_ACTION = "consider_drinking"
HOLD_ACTION = "hold"
REVIEW_ACTION = "review"

HIGH_PRIORITY = "high"
MEDIUM_PRIORITY = "medium"
LOW_PRIORITY = "low"

READY_CATEGORY = "ready"
TOO_YOUNG_CATEGORY = "too_young"
OVERDUE_CATEGORY = "overdue"
UNKNOWN_CATEGORY = "unknown"


@dataclass(frozen=True)
class DrinkingRecommendationSummary:
    as_of_year: int
    active_bottles: int
    drink_now_recommendations: int
    consider_drinking_recommendations: int
    hold_recommendations: int
    review_recommendations: int


@dataclass(frozen=True)
class DrinkingRecommendation:
    action: str
    priority: str
    drinking_window_category: str
    bottle_id: int
    producer: str
    cuvee: str
    vintage: str
    appellation: str
    color: str
    bottle_format: str
    status: str
    cellar: str | None
    cellar_purpose: str | None
    location: str | None
    personal_drink_from_year: int | None
    personal_drink_until_year: int | None
    reason: str


@dataclass(frozen=True)
class DrinkingRecommendationReport:
    summary: DrinkingRecommendationSummary
    recommendations: tuple[DrinkingRecommendation, ...]


def recommend_drinking(
    database_path: Path,
    *,
    as_of_year: int | None = None,
    limit: int | None = None,
) -> DrinkingRecommendationReport:
    if not database_path.exists():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    if limit is not None and limit < 1:
        raise ValueError("Limit must be at least 1.")

    resolved_year = as_of_year if as_of_year is not None else date.today().year

    with connect_database(database_path) as connection:
        rows = _fetch_active_bottle_rows(connection)

    recommendations = tuple(_recommend_bottle(row, as_of_year=resolved_year) for row in rows)

    sorted_recommendations = tuple(sorted(recommendations, key=_recommendation_sort_key))

    if limit is not None:
        sorted_recommendations = sorted_recommendations[:limit]

    summary = DrinkingRecommendationSummary(
        as_of_year=resolved_year,
        active_bottles=len(recommendations),
        drink_now_recommendations=sum(
            1 for recommendation in recommendations if recommendation.action == DRINK_NOW_ACTION
        ),
        consider_drinking_recommendations=sum(
            1
            for recommendation in recommendations
            if recommendation.action == CONSIDER_DRINKING_ACTION
        ),
        hold_recommendations=sum(
            1 for recommendation in recommendations if recommendation.action == HOLD_ACTION
        ),
        review_recommendations=sum(
            1 for recommendation in recommendations if recommendation.action == REVIEW_ACTION
        ),
    )

    return DrinkingRecommendationReport(
        summary=summary,
        recommendations=sorted_recommendations,
    )


def _fetch_active_bottle_rows(connection: Connection):
    return connection.execute(
        """
        SELECT
            bottle.id AS bottle_id,
            bottle.status,
            wine.producer,
            wine.cuvee,
            wine.vintage,
            wine.appellation,
            wine.color,
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


def _recommend_bottle(row, *, as_of_year: int) -> DrinkingRecommendation:
    drink_from = row["personal_drink_from_year"]
    drink_until = row["personal_drink_until_year"]
    category = _drinking_window_category(
        drink_from=drink_from,
        drink_until=drink_until,
        as_of_year=as_of_year,
    )

    action, priority, reason = _recommendation_action(
        status=row["status"],
        cellar_name=row["cellar_name"],
        cellar_purpose=row["cellar_purpose"],
        category=category,
        drink_from=drink_from,
        drink_until=drink_until,
    )

    return DrinkingRecommendation(
        action=action,
        priority=priority,
        drinking_window_category=category,
        bottle_id=int(row["bottle_id"]),
        producer=row["producer"],
        cuvee=row["cuvee"],
        vintage=row["vintage"],
        appellation=row["appellation"],
        color=row["color"],
        bottle_format=row["bottle_format"],
        status=row["status"],
        cellar=row["cellar_name"],
        cellar_purpose=row["cellar_purpose"],
        location=row["location_name"],
        personal_drink_from_year=drink_from,
        personal_drink_until_year=drink_until,
        reason=reason,
    )


def _drinking_window_category(
    *,
    drink_from: int | None,
    drink_until: int | None,
    as_of_year: int,
) -> str:
    if drink_from is None and drink_until is None:
        return UNKNOWN_CATEGORY

    if drink_until is not None and as_of_year > drink_until:
        return OVERDUE_CATEGORY

    if drink_from is not None and as_of_year < drink_from:
        return TOO_YOUNG_CATEGORY

    return READY_CATEGORY


def _recommendation_action(
    *,
    status: str,
    cellar_name: str | None,
    cellar_purpose: str | None,
    category: str,
    drink_from: int | None,
    drink_until: int | None,
) -> tuple[str, str, str]:
    if status == "opened":
        return (
            DRINK_NOW_ACTION,
            HIGH_PRIORITY,
            "Bottle is already opened and should be prioritized.",
        )

    if cellar_name is None:
        return (
            REVIEW_ACTION,
            HIGH_PRIORITY,
            "Bottle has no active location and needs manual review.",
        )

    if category == OVERDUE_CATEGORY:
        return (
            DRINK_NOW_ACTION,
            HIGH_PRIORITY,
            f"Past personal drink-until year {drink_until}.",
        )

    if category == READY_CATEGORY:
        return _ready_recommendation(cellar_purpose=cellar_purpose)

    if category == TOO_YOUNG_CATEGORY:
        return (
            HOLD_ACTION,
            LOW_PRIORITY,
            f"Not ready before personal drink-from year {drink_from}.",
        )

    return (
        REVIEW_ACTION,
        MEDIUM_PRIORITY,
        "No personal drinking window available.",
    )


def _ready_recommendation(
    *,
    cellar_purpose: str | None,
) -> tuple[str, str, str]:
    if cellar_purpose == "drink_soon":
        return (
            DRINK_NOW_ACTION,
            MEDIUM_PRIORITY,
            "Ready and already in a drink-soon cellar.",
        )

    if cellar_purpose == "aging":
        return (
            CONSIDER_DRINKING_ACTION,
            MEDIUM_PRIORITY,
            "Ready according to personal window but still in an aging cellar.",
        )

    if cellar_purpose in {"staging", "overflow"}:
        return (
            CONSIDER_DRINKING_ACTION,
            MEDIUM_PRIORITY,
            f"Ready and currently in a {cellar_purpose} cellar.",
        )

    return (
        CONSIDER_DRINKING_ACTION,
        LOW_PRIORITY,
        "Ready according to personal drinking window.",
    )


def _recommendation_sort_key(
    recommendation: DrinkingRecommendation,
) -> tuple[int, int, int, int, str, str, int]:
    priority_order = {
        HIGH_PRIORITY: 0,
        MEDIUM_PRIORITY: 1,
        LOW_PRIORITY: 2,
    }
    action_order = {
        DRINK_NOW_ACTION: 0,
        CONSIDER_DRINKING_ACTION: 1,
        REVIEW_ACTION: 2,
        HOLD_ACTION: 3,
    }
    category_order = {
        OVERDUE_CATEGORY: 0,
        READY_CATEGORY: 1,
        UNKNOWN_CATEGORY: 2,
        TOO_YOUNG_CATEGORY: 3,
    }

    drink_until = (
        recommendation.personal_drink_until_year
        if recommendation.personal_drink_until_year is not None
        else 9999
    )

    return (
        priority_order.get(recommendation.priority, 99),
        action_order.get(recommendation.action, 99),
        category_order.get(recommendation.drinking_window_category, 99),
        drink_until,
        recommendation.producer,
        recommendation.cuvee,
        recommendation.bottle_id,
    )
