# CellarMind

CellarMind is a privacy-first Python CLI for managing a wine cellar from local CSV data.

The project imports cellar spreadsheets into a local SQLite database, tracks physical bottles, locations, formats, purchase prices, and personal drinking-window estimates, and provides local audit/reporting commands.

CellarMind is designed to keep personal cellar data private. Local data files and generated databases are ignored by Git.

## Requirements

- Python 3.13+
- `uv`

## Quick start

```bash
uv sync --extra dev
uv run cellarmind --help
uv run pytest
```

## Privacy

Do not commit your personal cellar CSV or SQLite database.

Use the local `data/` directory for private files:

```bash
mkdir -p data
cp /path/to/your/cave.csv data/cave.csv
```

The repository ignores local data and generated artifacts such as:

- `data/`
- `cache/`
- `logs/`
- `reports/`
- SQLite databases

## CSV workflow

Inspect a CSV:

```bash
uv run cellarmind inspect data/cave.csv
```

Validate required cellar fields:

```bash
uv run cellarmind validate data/cave.csv
```

Normalize a CSV to CellarMind canonical columns:

```bash
uv run cellarmind normalize data/cave.csv --output /tmp/cave.canonical.csv
```

## Supported cellar CSV data

CellarMind supports canonical fields such as:

```text
producer
cuvee
vintage
appellation
color
format
quantity
cellar
location
purchase_price
personal_drink_from_year
personal_drink_until_year
```

It also supports common French cellar spreadsheet headers, including:

```text
Producteur
Cuvée
Année prod
Millésime
Appellation
Vignoble couleur
Couleur
Cave
Place
Nb
Fmt
Prix
Année min
Année Max
```

Format values are normalized to canonical bottle formats, for example:

```text
50    -> 500ml
75    -> 750ml
150   -> 1500ml
50cl  -> 500ml
75cl  -> 750ml
150cl -> 1500ml
magnum -> 1500ml
```

A missing vintage is imported as `NV`.

A quantity of `0` is accepted and creates no physical bottles. This is useful for historical rows or bottles already opened/consumed in the source spreadsheet.

## Location-based cellar mapping

Some cellar spreadsheets encode the cellar indirectly in the location code.

CellarMind supports an optional user-provided mapping file:

```csv
pattern,cellar
^BOX,Pending boxes
^M[A-Z][0-9]+$,Annex cellar
^[A-Z][0-9]+$,Main cellar
^G[0-9][A-Z]+$,Large cellar
^C[0-9][A-Z]+$,Climate-controlled cellar
```

Rules are evaluated from top to bottom. The first matching rule wins.

Import with a cellar map:

```bash
uv run cellarmind import data/cave.csv \
  --database data/cellarmind.sqlite \
  --cellar-map data/cellar-map.csv
```

Without a cellar map, CellarMind uses a generic default cellar when a location is present but no cellar is explicitly provided.

## SQLite workflow

Initialize a database:

```bash
uv run cellarmind db init --path data/cellarmind.sqlite
```

Import a cellar CSV:

```bash
uv run cellarmind import data/cave.csv --database data/cellarmind.sqlite
```

Import with location mapping:

```bash
uv run cellarmind import data/cave.csv \
  --database data/cellarmind.sqlite \
  --cellar-map data/cellar-map.csv
```

Show database stats:

```bash
uv run cellarmind db stats --path data/cellarmind.sqlite
```

List physical bottles:

```bash
uv run cellarmind list bottles --database data/cellarmind.sqlite --limit 30
```

Move a physical bottle to another cellar location:

```bash
uv run cellarmind bottle move 123 \
  --database data/cellarmind.sqlite \
  --cellar "Main cellar" \
  --location "A12"
```

Mark a bottle as opened:

```bash
uv run cellarmind bottle mark-opened 123 \
  --database data/cellarmind.sqlite
```

Mark a bottle as out of the cellar:

```bash
uv run cellarmind bottle mark-consumed 123 \
  --database data/cellarmind.sqlite
```

Other options can be used to mark a bottle as out:
 * `mark-gifted`
 * `mark-sold`
 * `mark-lost`

Audit an imported cellar:

```bash
uv run cellarmind db audit --path data/cellarmind.sqlite
```

The audit reports:

- total bottles, wines, and wine variants;
- bottles with and without purchase price;
- total purchase value based on imported purchase prices;
- wine variants with and without personal drinking windows;
- non-vintage wines;
- bottles without location;
- bottles by cellar;
- bottles by format;
- top producers;
- top appellations.

The audit command does not enrich data from external sources. It only summarizes data already imported into the local SQLite database.

## Domain model

CellarMind separates wine identity from physical inventory:

```text
Wine
  -> WineVariant
      -> Bottle
```

A `Wine` represents identity:

```text
producer + cuvee + vintage + appellation + color
```

A `WineVariant` represents format-specific information:

```text
wine + format
```

A `Bottle` represents one physical bottle in the cellar.

CSV `quantity` is import-only. A row with `Nb = 3` creates three physical `Bottle` rows. A row with `Nb = 0` creates no bottles.

Locations are tracked through `BottleLocationHistory`, so physical location can evolve over time.

## Personal data imported from CSV

`purchase_price` is stored on each physical bottle.

If a CSV row has:

```text
Nb = 3
Prix = 42
```

CellarMind creates three bottles, each with:

```text
purchase_price = 42
```

Personal drinking windows are stored on the wine variant:

```text
personal_drink_from_year
personal_drink_until_year
```

These fields represent the user’s own estimates. They are intentionally separate from future external enrichment data, confidence scores, and evidence.

## Development

Run the full local check suite:

```bash
./scripts/premerge.sh
uv run ruff check .
uv run ruff format --check .
```

Format code:

```bash
uv run ruff format .
```

Run tests:

```bash
uv run pytest
```

## Current status

CellarMind is pre-release software.

Implemented so far:

- Python 3.13 / `uv` project setup;
- CLI foundation;
- CSV inspect, validate, and normalize commands;
- canonical CSV schema with French aliases;
- SQLite database initialization;
- CSV import into SQLite;
- physical bottle creation from quantities;
- bottle formats and non-vintage wines;
- location-based cellar mapping;
- purchase prices and personal drinking windows;
- database stats;
- bottle listing;
- cellar audit command;
- tests and GitHub Actions CI.

Planned next steps include richer audit reports, drinking-window enrichment, evidence tracking, and eventually higher-level cellar recommendations.
