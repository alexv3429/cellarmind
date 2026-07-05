from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from cellarmind.importing.normalizer import normalize_csv_to_canonical
from cellarmind.importing.schema import validate_csv_schema
from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.infrastructure.csv_inspector import inspect_csv
from cellarmind.storage.inventory import list_bottles
from cellarmind.storage.sqlite import initialize_database
from cellarmind.storage.stats import get_database_stats

DEFAULT_DATABASE_PATH = Path("data/cellarmind.sqlite")
LimitOption = Annotated[
    int,
    typer.Option(
        "--limit",
        "-l",
        min=1,
        help="Maximum number of rows to display.",
    ),
]

OutputPathOption = Annotated[
    Path | None,
    typer.Option("--output", "-o", help="Output path for the canonical CSV."),
]
CellarMapPathOption = Annotated[
    Path | None,
    typer.Option(
        "--cellar-map",
        "-c",
        help="Optional path to a CSV file containing cellar mapping rules.",
    ),
]
DatabasePathOption = Annotated[
    Path,
    typer.Option("--path", "-p", help="SQLite database path."),
]
ImportDatabasePathOption = Annotated[
    Path,
    typer.Option(
        "--database",
        "-d",
        help="SQLite database path.",
    ),
]

app = typer.Typer(help="CellarMind: wine cellar enrichment and maturity analysis.")
db_app = typer.Typer(help="Manage the CellarMind SQLite database.")
app.add_typer(db_app, name="db")
list_app = typer.Typer(help="List cellar contents.")
app.add_typer(list_app, name="list")
console = Console(width=160)


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


@app.command()
def validate(path: Path) -> None:
    """Validate that a CSV can be imported by CellarMind."""
    if not path.exists():
        raise typer.BadParameter(f"File does not exist: {path}")

    result = validate_csv_schema(path)

    if result.valid:
        console.print("[green]Valid CSV[/green]")

        table = Table(title="Column mapping")
        table.add_column("Canonical field")
        table.add_column("CSV column")

        for canonical, original in result.mapping.items():
            table.add_row(canonical, original)

        console.print(table)
        return

    console.print("[red]Invalid CSV[/red]")

    if result.missing:
        console.print("\n[bold]Missing required fields[/bold]")
        for field in result.missing:
            console.print(f"- {field}")

    if result.conflicts:
        console.print("\n[bold]Conflicting columns[/bold]")
        for field, columns in result.conflicts.items():
            console.print(f"- {field}: {', '.join(columns)}")

    raise typer.Exit(code=1)


@app.command()
def normalize(
    path: Path,
    output: OutputPathOption = None,
) -> None:
    """Normalize a cellar CSV to CellarMind canonical import format."""
    if not path.exists():
        raise typer.BadParameter(f"File does not exist: {path}")

    try:
        result = normalize_csv_to_canonical(path, output)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print("[green]Canonical CSV created[/green]")
    console.print(f"Input: {result.input_path}")
    console.print(f"Output: {result.output_path}")
    console.print(f"Rows: {result.rows}")


@db_app.command("init")
def init_database(path: DatabasePathOption = DEFAULT_DATABASE_PATH) -> None:
    """Initialize a CellarMind SQLite database."""
    result = initialize_database(path)

    console.print("[green]Database initialized[/green]")
    console.print(f"Path: {result.path}")
    console.print(f"Schema version: {result.schema_version}")
    console.print(f"Tables: {len(result.tables)}")


@app.command("import")
def import_cellar(
    path: Path,
    database: ImportDatabasePathOption = DEFAULT_DATABASE_PATH,
    cellar_map: CellarMapPathOption = None,
) -> None:
    """Import a cellar CSV into the SQLite database."""
    if not path.exists():
        raise typer.BadParameter(f"File does not exist: {path}")

    console.print(f"Database: {database}")
    if cellar_map is not None:
        console.print(f"Cellar map: {cellar_map}")

    try:
        result = import_csv_to_database(path, database, cellar_map_path=cellar_map)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print("[green]CSV imported[/green]")
    console.print(f"Database: {result.database_path}")
    console.print(f"Import session: {result.import_session_id}")
    console.print(f"Source rows: {result.source_rows}")
    console.print(f"Created bottles: {result.created_bottles}")
    console.print(f"Wines touched: {result.wines}")
    console.print(f"Wine variants touched: {result.wine_variants}")


@db_app.command("stats")
def database_stats(path: Path = DEFAULT_DATABASE_PATH) -> None:
    """Show SQLite database statistics."""
    try:
        stats = get_database_stats(path)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print("[bold]Database stats[/bold]")
    console.print(f"Path: {stats.database_path}")
    console.print(f"Import sessions: {stats.import_sessions}")
    console.print(f"Wines: {stats.wines}")
    console.print(f"Wine variants: {stats.wine_variants}")
    console.print(f"Bottles: {stats.bottles}")
    console.print(f"Active bottles: {stats.active_bottles}")
    console.print(f"Cellars: {stats.cellars}")
    console.print(f"Locations: {stats.locations}")
    console.print(f"Location history rows: {stats.bottle_location_history_rows}")
    console.print(f"Active location rows: {stats.active_location_rows}")

    if stats.bottle_status_counts:
        table = Table(title="Bottle statuses")
        table.add_column("Status")
        table.add_column("Count", justify="right")

        for item in stats.bottle_status_counts:
            table.add_row(item.status, str(item.count))

        console.print(table)


@list_app.command("bottles")
def list_bottle_inventory(
    database: ImportDatabasePathOption = DEFAULT_DATABASE_PATH,
    limit: LimitOption = 50,
) -> None:
    """List physical bottles from the cellar database."""
    try:
        bottles = list_bottles(database, limit=limit)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"Database: {database}")

    if not bottles:
        console.print("[yellow]No bottles found[/yellow]")
        return

    table = Table(title="Bottles", expand=False)
    table.add_column("ID", justify="right", no_wrap=True)
    table.add_column("Producer", no_wrap=True)
    table.add_column("Cuvée", no_wrap=True)
    table.add_column("Vintage", justify="right", no_wrap=True)
    table.add_column("Appellation", no_wrap=True)
    table.add_column("Color", no_wrap=True)
    table.add_column("Format", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Cellar", no_wrap=True)
    table.add_column("Location", no_wrap=True)

    for bottle in bottles:
        table.add_row(
            str(bottle.bottle_id),
            bottle.producer,
            bottle.cuvee,
            str(bottle.vintage),
            bottle.appellation,
            bottle.color,
            bottle.format,
            bottle.status,
            bottle.cellar or "",
            bottle.location or "",
        )

    console.print(table)
