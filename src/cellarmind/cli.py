from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from cellarmind.infrastructure.csv_inspector import inspect_csv

app = typer.Typer(help="CellarMind: wine cellar enrichment and maturity analysis.")
console = Console()


@app.command()
def version() -> None:
    console.print("cellarmind 0.1.0")


@app.command()
def inspect(path: Path) -> None:
    """Inspect a cellar CSV file."""
    if not path.exists():
        raise typer.BadParameter(f"File does not exist: {path}")

    info = inspect_csv(path)

    console.print(f"\n[bold]CSV[/bold] {info['path']}")
    console.print(f"Rows: {info['rows']}")
    console.print(f"Columns: {info['columns']}")

    vintages = info.get("vintages")
    if isinstance(vintages, dict) and vintages.get("min") is not None:
        console.print(f"Millésimes: {vintages['min']} → {vintages['max']}")

    for key, title in [
        ("producers", "Top producteurs"),
        ("appellations", "Top appellations"),
        ("colors", "Couleurs"),
    ]:
        section = info.get(key)
        if not isinstance(section, dict) or "top" not in section:
            continue

        table = Table(title=title)
        table.add_column("Valeur")
        table.add_column("Nombre", justify="right")

        for value, count in section["top"]:
            table.add_row(str(value), str(count))

        console.print(table)
