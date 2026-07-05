from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from re import Pattern

DEFAULT_CELLAR_NAME = "default"


@dataclass(frozen=True)
class LocationMappingRule:
    pattern: Pattern[str]
    cellar: str


def load_location_mapping(path: Path) -> list[LocationMappingRule]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        if reader.fieldnames is None:
            return []

        fieldnames = {field.strip().casefold(): field for field in reader.fieldnames}

        pattern_field = fieldnames.get("pattern")
        cellar_field = fieldnames.get("cellar")

        if pattern_field is None or cellar_field is None:
            raise ValueError("Cellar map must contain 'pattern' and 'cellar' columns.")

        rules: list[LocationMappingRule] = []

        for line_number, row in enumerate(reader, start=2):
            pattern = (row.get(pattern_field) or "").strip()
            cellar = (row.get(cellar_field) or "").strip()

            if not pattern and not cellar:
                continue

            if not pattern or not cellar:
                raise ValueError(
                    f"Invalid cellar map row {line_number}: both pattern and cellar are required."
                )

            try:
                compiled_pattern = re.compile(pattern)
            except re.error as error:
                raise ValueError(
                    f"Invalid cellar map regex at row {line_number}: {pattern}"
                ) from error

            rules.append(LocationMappingRule(pattern=compiled_pattern, cellar=cellar))

    return rules


def resolve_cellar_from_location(
    location: str,
    rules: list[LocationMappingRule],
    default_cellar: str = DEFAULT_CELLAR_NAME,
) -> str:
    normalized_location = location.strip()

    for rule in rules:
        if rule.pattern.search(normalized_location):
            return rule.cellar

    return default_cellar
