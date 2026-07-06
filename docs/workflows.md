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

## Add bottles manually

CellarMind can add physical bottles without importing a CSV.

```bash
uv run cellarmind bottle add \
  --database data/cellarmind.sqlite \
  --producer "Domaine Test" \
  --cuvee "Cuvée Test" \
  --vintage 2020 \
  --appellation "Bourgogne" \
  --color Rouge \
  --format 750ml \
  --quantity 2 \
  --cellar "Main cellar" \
  --location "A12" \
  --purchase-price 42 \
  --personal-drink-from-year 2025 \
  --personal-drink-until-year 2030
```

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

CellarMind can  store the intended role and approximate capacity of each cellar.

```bash
uv run cellarmind cellar update "Main cellar" \
  --database data/cellarmind.sqlite \
  --purpose aging \
  --capacity-estimate 350 \
  --capacity-warning-threshold 330
```

## Audit cellar placement

After configuring cellar profiles, CellarMind can audit cellar placement.

```bash
uv run cellarmind report placement \
  --database data/cellarmind.sqlite
```

The placement report combines:

- active bottle locations;
- bottle lifecycle status;
- cellar purpose;
- approximate cellar capacity;
- personal drinking windows.

Examples of detected placement issues:

- bottle without active location;
- bottle in a staging cellar;
- bottle in an overflow cellar;
- too-young bottle in a `drink_soon` cellar;
- ready or overdue bottle still in an `aging` cellar;
- cellar near or over approximate capacity.

Use `--year` to evaluate drinking windows against a specific year:

```bash
uv run cellarmind report placement \
  --database data/cellarmind.sqlite \
  --year 2026
```

The report is read-only. It does not move bottles automatically.

## Plan cellar transfers

After running the placement report, CellarMind can turn placement issues into a
dry-run transfer plan.

```bash
uv run cellarmind plan transfers \
  --database data/cellarmind.sqlite \
  --year 2026 \
  --limit 30
```

The plan is advisory. It suggests target cellars when possible, but it does not
assign exact physical slots and does not apply moves.

Typical suggestions include:

- moving too-young bottles from `drink_soon` cellars to `aging` cellars;
- moving ready or overdue bottles from `aging` cellars to `drink_soon` cellars;
- reviewing bottles in `staging` or `overflow` cellars;
- reviewing bottles without an active location.

## Report drinking windows

CellarMind can classify active bottles according to personal drinking windows.

```bash
uv run cellarmind report drinking-window \
  --database data/cellarmind.sqlite \
  --year 2026 \
  --limit 50
```

The command is read-only and reports:

- overdue bottles;
- bottles ready to drink;
- bottles that are still too young;
- bottles with unknown personal drinking windows.

Only active bottles are included. Bottles marked as `consumed`, `gifted`, `sold`,
or `lost` are excluded.

## Recommend bottles to drink

After importing bottles and personal drinking windows, CellarMind can recommend
what to drink, hold, or review.

```bash
uv run cellarmind recommend drinking \
  --database data/cellarmind.sqlite \
  --year 2026 \
  --limit 50
```

The recommendation command combines:

- active bottle status;
- personal drinking windows;
- cellar purpose;
- current location.

Typical actions are:

- `drink_now` for opened or overdue bottles;
- `consider_drinking` for bottles that are ready but not urgent;
- `hold` for bottles that are too young;
- `review` for bottles with missing location or missing drinking-window data.

The command is advisory and read-only.

## Add reference drinking windows

Reference drinking windows can be added manually.

```bash
uv run cellarmind reference-window add \
  --database data/cellarmind.sqlite \
  --wine-id 123 \
  --source-name "Producer note" \
  --source-url "https://example.com" \
  --drink-from-year 2024 \
  --drink-until-year 2032 \
  --confidence medium \
  --notes "Manual reference"
```

Reference windows are local data. This command does not fetch data from the
internet and does not overwrite personal drinking windows.

## Compare drinking-window evidence

After adding reference drinking windows, compare them with personal windows:

```bash
uv run cellarmind report window-comparison \
  --database data/cellarmind.sqlite \
  --tolerance-years 2 \
  --limit 50
```

## Fetch a reference drinking window from a web page

Use `reference-window fetch` when you have a producer, merchant, critic, or
other source page that mentions a drinking window.

```bash
uv run cellarmind reference-window fetch \
  --database data/cellarmind.sqlite \
  --wine-id 123 \
  --url "https://example.com/wine-page"
```

Review the extracted candidate. Then save it explicitly:

```bash
uv run cellarmind reference-window fetch \
  --database data/cellarmind.sqlite \
  --wine-id 123 \
  --url "https://example.com/wine-page" \
  --source-name "Producer website" \
  --confidence medium \
  --save
```

The fetched window is stored as reference evidence. It does not replace the
personal drinking window.
