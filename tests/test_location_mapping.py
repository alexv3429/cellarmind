from pathlib import Path

import pytest

from cellarmind.importing.location_mapping import (
    load_location_mapping,
    resolve_cellar_from_location,
)


def test_load_location_mapping_and_resolve_cellar(tmp_path: Path) -> None:
    cellar_map_path = tmp_path / "cellar-map.csv"

    cellar_map_path.write_text(
        "pattern,cellar\n^G[0-9][A-Z]+$,Large cellar\n",
        encoding="utf-8",
    )

    rules = load_location_mapping(cellar_map_path)

    assert resolve_cellar_from_location("G1A", rules) == "Large cellar"


def test_location_mapping_uses_default_when_no_rule_matches(tmp_path: Path) -> None:
    cellar_map_path = tmp_path / "cellar-map.csv"

    cellar_map_path.write_text(
        "pattern,cellar\n^G[0-9][A-Z]+$,Large cellar\n",
        encoding="utf-8",
    )

    rules = load_location_mapping(cellar_map_path)

    assert resolve_cellar_from_location("A1", rules) == "default"


def test_location_mapping_uses_first_matching_rule(tmp_path: Path) -> None:
    cellar_map_path = tmp_path / "cellar-map.csv"

    cellar_map_path.write_text(
        "pattern,cellar\n^A,First cellar\n^A1$,Second cellar\n",
        encoding="utf-8",
    )

    rules = load_location_mapping(cellar_map_path)

    assert resolve_cellar_from_location("A1", rules) == "First cellar"


def test_load_location_mapping_rejects_missing_required_columns(
    tmp_path: Path,
) -> None:
    cellar_map_path = tmp_path / "cellar-map.csv"

    cellar_map_path.write_text(
        "regex,name\n^A,Main cellar\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="pattern.*cellar"):
        load_location_mapping(cellar_map_path)


def test_load_location_mapping_rejects_invalid_regex(tmp_path: Path) -> None:
    cellar_map_path = tmp_path / "cellar-map.csv"

    cellar_map_path.write_text(
        "pattern,cellar\n[,Broken cellar\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid cellar map regex"):
        load_location_mapping(cellar_map_path)
