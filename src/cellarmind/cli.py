from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from cellarmind.importing.normalizer import normalize_csv_to_canonical
from cellarmind.importing.schema import validate_csv_schema
from cellarmind.importing.sqlite_importer import import_csv_to_database
from cellarmind.infrastructure.csv_inspector import inspect_csv
from cellarmind.storage.audit import AuditBreakdownRow, audit_database
from cellarmind.storage.bottle_addition import add_bottles
from cellarmind.storage.bottle_movement import move_bottle
from cellarmind.storage.bottle_status import update_bottle_status
from cellarmind.storage.cellars import list_cellars, update_cellar_profile
from cellarmind.storage.inventory import list_bottles
from cellarmind.storage.placement import PlacementIssue, audit_placement
from cellarmind.storage.sqlite import initialize_database
from cellarmind.storage.stats import get_database_stats
from cellarmind.storage.transfer_plan import TransferSuggestion, plan_transfers

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
BottleDatabasePathOption = Annotated[
    Path,
    typer.Option(
        "--database",
        "-d",
        help="SQLite database path.",
    ),
]
CellarNameOption = Annotated[str, typer.Option("--cellar", help="Target cellar name.")]
LocationNameOption = Annotated[str, typer.Option("--location", help="Target location name.")]
CellarPurposeOption = Annotated[
    str | None,
    typer.Option(
        "--purpose",
        help="Cellar purpose (aging, drink_soon, mixed, staging, overflow).",
    ),
]
CapacityEstimateOption = Annotated[
    int | None,
    typer.Option(
        "--capacity-estimate",
        help="Estimated capacity of the cellar (number of bottles).",
    ),
]
CapacityWarningThresholdOption = Annotated[
    int | None,
    typer.Option(
        "--capacity-warning-threshold",
        help="Capacity warning threshold (number of bottles).",
    ),
]
CellarNotesOption = Annotated[
    str | None,
    typer.Option(
        "--notes",
        help="Optional notes for the cellar.",
    ),
]
ProducerOption = Annotated[
    str,
    typer.Option("--producer", help="Wine producer."),
]

CuveeOption = Annotated[
    str,
    typer.Option("--cuvee", help="Wine cuvée."),
]

VintageOption = Annotated[
    str,
    typer.Option("--vintage", help="Wine vintage year or NV."),
]

AppellationOption = Annotated[
    str,
    typer.Option("--appellation", help="Wine appellation."),
]

ColorOption = Annotated[
    str,
    typer.Option("--color", help="Wine color."),
]

BottleFormatOption = Annotated[
    str,
    typer.Option("--format", help="Bottle format, for example 750ml or 150."),
]

BottleQuantityOption = Annotated[
    int,
    typer.Option("--quantity", "-q", min=1, help="Number of bottles to add."),
]

OptionalCellarNameOption = Annotated[
    str | None,
    typer.Option("--cellar", help="Cellar name."),
]

OptionalLocationNameOption = Annotated[
    str | None,
    typer.Option("--location", help="Location name."),
]

PurchasePriceOption = Annotated[
    float | None,
    typer.Option("--purchase-price", help="Purchase price per bottle."),
]

PersonalDrinkFromYearOption = Annotated[
    int | None,
    typer.Option("--personal-drink-from-year", help="Personal drink-from year."),
]

PersonalDrinkUntilYearOption = Annotated[
    int | None,
    typer.Option("--personal-drink-until-year", help="Personal drink-until year."),
]

ReportYearOption = Annotated[
    int | None,
    typer.Option(
        "--year",
        help="Year used to evaluate drinking windows. Defaults to current year.",
    ),
]

PlacementIssueLimitOption = Annotated[
    int,
    typer.Option(
        "--limit",
        "-l",
        min=1,
        help="Maximum number of placement issues to display.",
    ),
]

app = typer.Typer(help="CellarMind: wine cellar enrichment and maturity analysis.")
db_app = typer.Typer(help="Manage the CellarMind SQLite database.")
app.add_typer(db_app, name="db")
list_app = typer.Typer(help="List cellar contents.")
app.add_typer(list_app, name="list")
bottle_app = typer.Typer(help="Manage physical bottles.")
app.add_typer(bottle_app, name="bottle")
cellar_app = typer.Typer(help="Manage cellar profiles.")
app.add_typer(cellar_app, name="cellar")
report_app = typer.Typer(help="Generate cellar reports.")
app.add_typer(report_app, name="report")
plan_app = typer.Typer(help="Generate cellar transfer plans.")
app.add_typer(plan_app, name="plan")
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


@db_app.command("audit")
def audit_cellar_database(
    path: DatabasePathOption = DEFAULT_DATABASE_PATH,
) -> None:
    """Audit imported cellar data."""
    try:
        report = audit_database(path)
    except FileNotFoundError as error:
        raise typer.BadParameter(str(error)) from error

    console.print(f"Database: {path}")

    _print_audit_summary(report)
    _print_audit_breakdown("Bottles by cellar", report.bottles_by_cellar)
    _print_audit_breakdown("Bottles by format", report.bottles_by_format)
    _print_audit_breakdown("Top producers", report.top_producers)
    _print_audit_breakdown("Top appellations", report.top_appellations)


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


@bottle_app.command("move")
def move_bottle_command(
    bottle_id: int,
    database: BottleDatabasePathOption = DEFAULT_DATABASE_PATH,
    cellar: CellarNameOption = ...,
    location: LocationNameOption = ...,
) -> None:
    """Move a physical bottle to another cellar location."""
    try:
        result = move_bottle(
            database,
            bottle_id=bottle_id,
            cellar_name=cellar,
            location_name=location,
        )
    except FileNotFoundError as error:
        raise typer.BadParameter(str(error)) from error
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error

    console.print(f"Database: {database}")

    if result.moved:
        if result.previous_location is None:
            console.print(
                f"Moved bottle {result.bottle_id} to "
                f"{result.new_location.cellar} / {result.new_location.location}"
            )
        else:
            console.print(
                f"Moved bottle {result.bottle_id} from "
                f"{result.previous_location.cellar} / "
                f"{result.previous_location.location} to "
                f"{result.new_location.cellar} / "
                f"{result.new_location.location}"
            )
    else:
        console.print(
            f"Bottle {result.bottle_id} is already at "
            f"{result.new_location.cellar} / {result.new_location.location}"
        )


@bottle_app.command("mark-opened")
def mark_bottle_opened(
    bottle_id: int,
    database: BottleDatabasePathOption = DEFAULT_DATABASE_PATH,
) -> None:
    """Mark a physical bottle as opened."""
    _mark_bottle_status(
        database=database,
        bottle_id=bottle_id,
        status="opened",
    )


@bottle_app.command("mark-consumed")
def mark_bottle_consumed(
    bottle_id: int,
    database: BottleDatabasePathOption = DEFAULT_DATABASE_PATH,
) -> None:
    """Mark a physical bottle as consumed and remove it from active location."""
    _mark_bottle_status(
        database=database,
        bottle_id=bottle_id,
        status="consumed",
    )


@bottle_app.command("mark-gifted")
def mark_bottle_gifted(
    bottle_id: int,
    database: BottleDatabasePathOption = DEFAULT_DATABASE_PATH,
) -> None:
    """Mark a physical bottle as gifted and remove it from active location."""
    _mark_bottle_status(
        database=database,
        bottle_id=bottle_id,
        status="gifted",
    )


@bottle_app.command("mark-sold")
def mark_bottle_sold(
    bottle_id: int,
    database: BottleDatabasePathOption = DEFAULT_DATABASE_PATH,
) -> None:
    """Mark a physical bottle as sold and remove it from active location."""
    _mark_bottle_status(
        database=database,
        bottle_id=bottle_id,
        status="sold",
    )


@bottle_app.command("mark-lost")
def mark_bottle_lost(
    bottle_id: int,
    database: BottleDatabasePathOption = DEFAULT_DATABASE_PATH,
) -> None:
    """Mark a physical bottle as lost and remove it from active location."""
    _mark_bottle_status(
        database=database,
        bottle_id=bottle_id,
        status="lost",
    )


@bottle_app.command("add")
def add_bottle_command(
    database: BottleDatabasePathOption = DEFAULT_DATABASE_PATH,
    producer: ProducerOption = ...,
    cuvee: CuveeOption = ...,
    vintage: VintageOption = ...,
    appellation: AppellationOption = ...,
    color: ColorOption = ...,
    bottle_format: BottleFormatOption = "750ml",
    quantity: BottleQuantityOption = 1,
    cellar: OptionalCellarNameOption = None,
    location: OptionalLocationNameOption = None,
    purchase_price: PurchasePriceOption = None,
    personal_drink_from_year: PersonalDrinkFromYearOption = None,
    personal_drink_until_year: PersonalDrinkUntilYearOption = None,
) -> None:
    """Add physical bottles manually."""
    try:
        result = add_bottles(
            database,
            producer=producer,
            cuvee=cuvee,
            vintage=vintage,
            appellation=appellation,
            color=color,
            bottle_format=bottle_format,
            quantity=quantity,
            cellar_name=cellar,
            location_name=location,
            purchase_price=purchase_price,
            personal_drink_from_year=personal_drink_from_year,
            personal_drink_until_year=personal_drink_until_year,
        )
    except FileNotFoundError as error:
        raise typer.BadParameter(str(error)) from error
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error

    console.print(f"Database: {database}")
    console.print(f"Created bottles: {result.created_bottles}")
    console.print(f"Wine ID: {result.wine_id}")
    console.print(f"Wine variant ID: {result.wine_variant_id}")
    console.print("Bottle IDs: " + ", ".join(str(bottle_id) for bottle_id in result.bottle_ids))


@cellar_app.command("list")
def list_cellar_profiles(
    database: ImportDatabasePathOption = DEFAULT_DATABASE_PATH,
) -> None:
    """List cellar profiles and approximate occupancy."""
    try:
        cellars = list_cellars(database)
    except FileNotFoundError as error:
        raise typer.BadParameter(str(error)) from error

    console.print(f"Database: {database}")

    table = Table(title="Cellars", expand=False)
    table.add_column("Name", no_wrap=True)
    table.add_column("Purpose", no_wrap=True)
    table.add_column("Bottles", justify="right", no_wrap=True)
    table.add_column("Capacity", justify="right", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Notes", no_wrap=True)

    for cellar in cellars:
        table.add_row(
            cellar.name,
            cellar.purpose,
            str(cellar.active_bottles),
            (str(cellar.capacity_estimate) if cellar.capacity_estimate is not None else ""),
            cellar.occupancy_status,
            cellar.notes or "",
        )

    console.print(table)


@cellar_app.command("update")
def update_cellar(
    name: str,
    database: ImportDatabasePathOption = DEFAULT_DATABASE_PATH,
    purpose: CellarPurposeOption = None,
    capacity_estimate: CapacityEstimateOption = None,
    capacity_warning_threshold: CapacityWarningThresholdOption = None,
    notes: CellarNotesOption = None,
) -> None:
    """Create or update a cellar profile."""
    try:
        update_cellar_profile(
            database,
            name=name,
            purpose=purpose,
            capacity_estimate=capacity_estimate,
            capacity_warning_threshold=capacity_warning_threshold,
            notes=notes,
        )
    except FileNotFoundError as error:
        raise typer.BadParameter(str(error)) from error
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error

    console.print(f"Database: {database}")
    console.print(f"Updated cellar: {name}")


@report_app.command("placement")
def report_placement(
    database: ImportDatabasePathOption = DEFAULT_DATABASE_PATH,
    year: ReportYearOption = None,
    limit: PlacementIssueLimitOption = 50,
) -> None:
    """Audit cellar placement, capacity, and location issues."""
    try:
        report = audit_placement(
            database,
            as_of_year=year,
        )
    except FileNotFoundError as error:
        raise typer.BadParameter(str(error)) from error

    console.print(f"Database: {database}")

    _print_placement_summary(report)
    _print_cellar_occupancy(report)
    _print_placement_issues(report.issues, limit=limit)


@plan_app.command("transfers")
def plan_cellar_transfers(
    database: ImportDatabasePathOption = DEFAULT_DATABASE_PATH,
    year: ReportYearOption = None,
    limit: PlacementIssueLimitOption = 50,
) -> None:
    """Suggest cellar transfers without applying them."""
    try:
        transfer_plan = plan_transfers(
            database,
            as_of_year=year,
            limit=limit,
        )
    except FileNotFoundError as error:
        raise typer.BadParameter(str(error)) from error

    console.print(f"Database: {database}")

    _print_transfer_suggestions(transfer_plan.suggestions)


def _print_audit_summary(report) -> None:
    summary = report.summary

    table = Table(title="Cellar audit", expand=False)
    table.add_column("Metric", no_wrap=True)
    table.add_column("Value", justify="right", no_wrap=True)

    table.add_row("Total bottles", str(summary.bottles))
    table.add_row("Wines", str(summary.wines))
    table.add_row("Wine variants", str(summary.wine_variants))
    table.add_row("Bottles with purchase price", str(summary.bottles_with_price))
    table.add_row("Bottles without purchase price", str(summary.bottles_without_price))
    table.add_row("Total purchase value", f"{summary.total_purchase_value:.2f}")
    table.add_row(
        "Variants with personal drink window",
        str(summary.variants_with_personal_drink_window),
    )
    table.add_row(
        "Variants without personal drink window",
        str(summary.variants_without_personal_drink_window),
    )
    table.add_row("Non-vintage wines", str(summary.non_vintage_wines))
    table.add_row("Bottles without location", str(summary.bottles_without_location))

    console.print(table)


def _print_audit_breakdown(
    title: str,
    rows: tuple[AuditBreakdownRow, ...],
) -> None:
    table = Table(title=title, expand=False)
    table.add_column("Label", no_wrap=True)
    table.add_column("Bottles", justify="right", no_wrap=True)

    for row in rows:
        table.add_row(row.label, str(row.bottle_count))

    console.print(table)


def _mark_bottle_status(
    *,
    database: Path,
    bottle_id: int,
    status: str,
) -> None:
    try:
        result = update_bottle_status(
            database,
            bottle_id=bottle_id,
            new_status=status,
        )
    except FileNotFoundError as error:
        raise typer.BadParameter(str(error)) from error
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error

    console.print(f"Database: {database}")

    if result.changed:
        console.print(
            f"Bottle {result.bottle_id} status changed from "
            f"{result.previous_status} to {result.new_status}."
        )
    else:
        console.print(f"Bottle {result.bottle_id} is already marked as {result.new_status}.")

    if result.closed_location_history_rows:
        console.print("Closed active location.")


def _print_placement_summary(report) -> None:
    summary = report.summary

    table = Table(title="Placement audit", expand=False)
    table.add_column("Metric", no_wrap=True)
    table.add_column("Value", justify="right", no_wrap=True)

    table.add_row("As of year", str(summary.as_of_year))
    table.add_row("Active bottles", str(summary.active_bottles))
    table.add_row("Bottles without location", str(summary.bottles_without_location))
    table.add_row("Cellars near capacity", str(summary.cellars_near_capacity))
    table.add_row("Cellars over capacity", str(summary.cellars_over_capacity))
    table.add_row("Bottles in staging cellars", str(summary.bottles_in_staging_cellars))
    table.add_row("Bottles in overflow cellars", str(summary.bottles_in_overflow_cellars))
    table.add_row(
        "Too young in drink-soon cellars",
        str(summary.too_young_bottles_in_drink_soon_cellars),
    )
    table.add_row(
        "Ready or overdue in aging cellars",
        str(summary.ready_or_overdue_bottles_in_aging_cellars),
    )
    table.add_row(
        "Unknown window in drink-soon cellars",
        str(summary.unknown_window_bottles_in_drink_soon_cellars),
    )

    console.print(table)


def _print_cellar_occupancy(report) -> None:
    table = Table(title="Cellar occupancy", expand=False)
    table.add_column("Cellar", no_wrap=True, overflow="ignore")
    table.add_column("Purpose", no_wrap=True)
    table.add_column("Bottles", justify="right", no_wrap=True)
    table.add_column("Capacity", justify="right", no_wrap=True)
    table.add_column("Warning", justify="right", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Notes", no_wrap=True, overflow="ignore")

    for cellar in report.cellar_occupancy:
        table.add_row(
            cellar.name,
            cellar.purpose,
            str(cellar.active_bottles),
            (str(cellar.capacity_estimate) if cellar.capacity_estimate is not None else ""),
            (
                str(cellar.capacity_warning_threshold)
                if cellar.capacity_warning_threshold is not None
                else ""
            ),
            cellar.occupancy_status,
            cellar.notes or "",
        )

    console.print(table)


def _print_placement_issues(
    issues: tuple[PlacementIssue, ...],
    *,
    limit: int,
) -> None:
    if not issues:
        console.print("No placement issues found.")
        return

    table = Table(title=f"Placement issues, first {limit}", expand=False)
    table.add_column("Severity", no_wrap=True, overflow="ignore", min_width=8)
    table.add_column("Issue", no_wrap=True, overflow="ignore", min_width=32)
    table.add_column("Bottle", justify="right", no_wrap=True, min_width=6)
    table.add_column("Wine", overflow="fold", max_width=42)
    table.add_column("Cellar", no_wrap=True, overflow="ignore", min_width=8)
    table.add_column("Location", no_wrap=True, overflow="ignore", min_width=8)
    table.add_column("Window", no_wrap=True, overflow="ignore", min_width=9)
    table.add_column("Note", overflow="fold", max_width=56)

    for issue in issues[:limit]:
        table.add_row(
            issue.severity,
            issue.issue_type,
            str(issue.bottle_id),
            _format_issue_wine(issue),
            issue.cellar or "",
            issue.location or "",
            _format_issue_window(issue),
            issue.note,
        )

    console.print(table)


def _format_issue_wine(issue: PlacementIssue) -> str:
    return f"{issue.producer} — {issue.cuvee} {issue.vintage} ({issue.bottle_format})"


def _format_issue_window(issue: PlacementIssue) -> str:
    if issue.personal_drink_from_year is None and issue.personal_drink_until_year is None:
        return ""

    from_year = (
        str(issue.personal_drink_from_year) if issue.personal_drink_from_year is not None else "?"
    )
    until_year = (
        str(issue.personal_drink_until_year) if issue.personal_drink_until_year is not None else "?"
    )

    return f"{from_year}-{until_year}"


def _print_transfer_suggestions(
    suggestions: tuple[TransferSuggestion, ...],
) -> None:
    if not suggestions:
        console.print("No transfer suggestions found.")
        return

    table = Table(title="Transfer plan", expand=False)
    table.add_column("Action", no_wrap=True)
    table.add_column("Bottle", justify="right", no_wrap=True)
    table.add_column("Wine", overflow="fold", max_width=42)
    table.add_column("From", overflow="fold", max_width=28)
    table.add_column("To", overflow="fold", max_width=28)
    table.add_column("Reason", overflow="fold", max_width=56)

    for suggestion in suggestions:
        table.add_row(
            suggestion.action,
            str(suggestion.bottle_id),
            _format_transfer_wine(suggestion),
            _format_transfer_current_location(suggestion),
            _format_transfer_target(suggestion),
            suggestion.reason,
        )

    console.print(table)


def _format_transfer_wine(suggestion: TransferSuggestion) -> str:
    return (
        f"{suggestion.producer} — {suggestion.cuvee} "
        f"{suggestion.vintage} ({suggestion.bottle_format})"
    )


def _format_transfer_current_location(suggestion: TransferSuggestion) -> str:
    if suggestion.current_cellar is None:
        return ""

    if suggestion.current_location is None:
        return suggestion.current_cellar

    return f"{suggestion.current_cellar} / {suggestion.current_location}"


def _format_transfer_target(suggestion: TransferSuggestion) -> str:
    if suggestion.target_cellar is not None:
        return suggestion.target_cellar

    if suggestion.target_purpose is not None:
        return f"Any {suggestion.target_purpose} cellar"

    return "Review manually"
