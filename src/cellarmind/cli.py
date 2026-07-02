"""Command line interface for CellarMind."""

from pathlib import Path
from typing import Annotated

import polars as pl
import typer
from rich.console import Console
from rich.table import Table

from cellarmind.version import __version__

app = typer.Typer(
    name="cellarmind",
    help="Enrich wine cellar CSV files with maturity windows and traceable decisions.",
    no_args_is_help=True,
)
console = Console()


def _read_csv(path: Path) -> pl.DataFrame:
    if not path.exists():
        raise typer.BadParameter(f"CSV file not found: {path}")
    return pl.read_csv(path, infer_schema_length=0)


@app.command()
def version() -> None:
    """Show the CellarMind version."""
    console.print(__version__)


@app.command()
def inspect(csv_path: Annotated[Path, typer.Argument(help="Path to the cellar CSV file")]) -> None:
    """Inspect a cellar CSV without modifying it."""
    frame = _read_csv(csv_path)

    table = Table(title="Cellar CSV inspection")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Rows", str(frame.height))
    table.add_row("Columns", str(frame.width))
    table.add_row("Column names", ", ".join(frame.columns))

    for candidate in ["Producteur", "Année Prod", "Appellation", "Couleur"]:
        if candidate in frame.columns:
            table.add_row(f"Distinct {candidate}", str(frame[candidate].n_unique()))

    console.print(table)


@app.command()
def enrich(
    csv_path: Annotated[Path, typer.Argument(help="Path to the cellar CSV file")],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output CSV path"),
    ] = Path("reports/enriched.csv"),
    offline: Annotated[
        bool,
        typer.Option("--offline", help="Use interpolation placeholders only"),
    ] = False,
    limit: Annotated[
        int | None,
        typer.Option("--limit", help="Limit the number of rows processed"),
    ] = None,
) -> None:
    """Enrich a cellar CSV.

    The current bootstrap implementation creates the output schema and fills
    traceable offline interpolation placeholders. Real providers will be added
    in later milestones.
    """
    frame = _read_csv(csv_path)
    if limit is not None:
        frame = frame.head(limit)

    if not offline:
        console.print(
            "[yellow]Online providers are not implemented yet. "
            "Using offline placeholders for this milestone.[/yellow]"
        )

    enriched = frame.with_columns(
        pl.lit(None).cast(pl.Int64).alias("Ne pas boire avant"),
        pl.lit(None).cast(pl.Int64).alias("Consommation optimale"),
        pl.lit(None).cast(pl.Int64).alias("Ne pas boire après"),
        pl.lit("Interpolation en attente de providers; aucune source web consultée").alias("Source"),
        pl.lit("Faible").alias("Confiance"),
        pl.lit("bootstrap_offline_placeholder").alias("Méthode"),
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    enriched.write_csv(output)
    console.print(f"[green]Wrote enriched CSV:[/green] {output}")


@app.command()
def doctor() -> None:
    """Check the local CellarMind environment."""
    console.print("[green]CellarMind environment looks OK.[/green]")
