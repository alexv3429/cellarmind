from pathlib import Path

from cellarmind.infrastructure.csv_inspector import inspect_csv


def test_inspect_sample_csv() -> None:
    info = inspect_csv(Path("examples/cave.sample.csv"))

    assert info["rows"] >= 1
    assert info["columns"] >= 1
    assert "column_names" in info
