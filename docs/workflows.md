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

## Update bottle status

CellarMind can update the lifecycle status of a physical bottle.

Mark a bottle as opened:

```⁠bash
uv run cellarmind bottle mark-opened 123 \
  --database data/cellarmind.sqlite
```

Alternatively, a bottle can be marked as out of the cellar using status:

- `mark-consumed`
- `mark-sold`
- `mark-gifted`
- `mark-lost`

## Audit an imported cellar

After importing a cellar CSV into SQLite, CellarMind can produce an audit summary.

```bash
uv run cellarmind db audit --path data/cellarmind.sqlite
```

## Configure cellar profiles

CellarMind can  store the intended role and approximate capacityof each cellar.

```bash
uv run cellarmind cellar update "Main cellar" \
  --database data/cellarmind.sqlite \
  --purpose aging \
  --capacity-estimate 350 \
  --capacity-warning-threshold 330
```
