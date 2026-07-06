# Workflows

## Import

Basic format (CSV)

↓

Validate

↓

Normalize

↓

Import into database (SQLite)

## Enrichment

WineVariant

↓

Providers

↓

Evidence

↓

Scoring

↓

Interpolation

↓

DrinkWindow

## Consumption

Search

↓

Select bottle

↓

Open bottle

↓

Taste

↓

Record tasting

↓

Update bottle status

## Organize

Search

↓

Select bottle

↓

Move bottle

↓

Create / update bottle location

## Move a bottle

CellarMind tracks bottle locations through location history.

To move a physical bottle:

```bash
uv run cellarmind bottle move 123 \
  --database data/cellarmind.sqlite \
  --cellar "Main cellar" \
  --location "A12"
```

## Audit an imported cellar

After importing a cellar CSV into SQLite, CellarMind can produce an audit summary.

```bash
uv run cellarmind db audit --path data/cellarmind.sqlite
```
