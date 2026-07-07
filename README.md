# CellarMind

CellarMind is a privacy-first Python CLI for managing a wine cellar from local CSV data.

It imports cellar spreadsheets into a local SQLite database, tracks physical bottles, locations, formats, purchase prices, personal drinking windows, reference drinking-window evidence, and AI-assisted drinking-window estimates.

Core principle:

```text
CSV is import/export.
SQLite is the source of truth.
Personal cellar data stays local unless you explicitly run an internet/API command.
```

## Requirements

- Python 3.13+
- `uv`

Optional features:

- OpenAI API key for `reference-window estimate --provider openai`
- Ollama installed locally for `reference-window estimate --provider ollama`
- Internet access for search, URL fetch, Jina Reader, and OpenAI-backed estimates

## Quick start

```bash
uv sync --extra dev
uv run cellarmind --help
uv run pytest
```

## Privacy and network access

Do not commit your personal cellar CSV, SQLite database, reports, API keys, or local caches.

Use a local ignored directory for private data:

```bash
mkdir -p data/private
cp /path/to/your/cave.csv data/private/cave.csv
```

The repository should ignore local data and generated artifacts such as:

```text
data/
cache/
logs/
reports/
*.sqlite
*.db
.env
```

Most commands are fully local. These commands may use the network:

```text
reference-window search
reference-window fetch
reference-window estimate --provider openai
reference-window estimate --provider ollama --web-search
```

`reference-window estimate --provider ollama --no-web-search` uses only local Ollama inference and local database data.

## CSV workflow

Inspect, validate, normalize, and import:

```bash
uv run cellarmind inspect data/private/cave.csv
uv run cellarmind validate data/private/cave.csv
uv run cellarmind normalize data/private/cave.csv --output /tmp/cave.canonical.csv
uv run cellarmind import data/private/cave.csv --database data/private/cellarmind.sqlite
```

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
50      -> 500ml
75      -> 750ml
150     -> 1500ml
50cl    -> 500ml
75cl    -> 750ml
150cl   -> 1500ml
magnum  -> 1500ml
```

A missing vintage is imported as `NV`.

A quantity of `0` is accepted and creates no physical bottles.

## Location-based cellar mapping

Some cellar spreadsheets encode the cellar indirectly in the location code.

CellarMind supports a mapping CSV:

```csv
pattern,cellar
^BOX,Pending boxes
^M[A-Z][0-9]+$,Annex cellar
^[A-Z][0-9]+$,Main cellar
^G[0-9][A-Z]+$,Large cellar
^C[0-9][A-Z]+$,Climate-controlled cellar
```

Rules are evaluated from top to bottom. The first matching rule wins.

```bash
uv run cellarmind import data/private/cave.csv \
  --database data/private/cellarmind.sqlite \
  --cellar-map data/private/cellar-map.csv
```

## Bottle and cellar workflow

List bottles:

```bash
uv run cellarmind list bottles --database data/private/cellarmind.sqlite --limit 30
```

Add bottles manually:

```bash
uv run cellarmind bottle add \
  --database data/private/cellarmind.sqlite \
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

Move a bottle:

```bash
uv run cellarmind bottle move 123 \
  --database data/private/cellarmind.sqlite \
  --cellar "Main cellar" \
  --location "A12"
```

Mark a bottle status:

```bash
uv run cellarmind bottle mark-opened 123 --database data/private/cellarmind.sqlite
uv run cellarmind bottle mark-consumed 123 --database data/private/cellarmind.sqlite
```

Other out-of-cellar commands are:

```text
mark-gifted
mark-sold
mark-lost
```

Configure a cellar profile:

```bash
uv run cellarmind cellar update "Main cellar" \
  --database data/private/cellarmind.sqlite \
  --purpose aging \
  --capacity-estimate 350 \
  --capacity-warning-threshold 330 \
  --notes "Main long-term aging cellar"
```

Supported cellar purposes:

```text
aging
drink_soon
mixed
staging
overflow
```

## Reports and recommendations

```bash
uv run cellarmind db stats --path data/private/cellarmind.sqlite
uv run cellarmind db audit --path data/private/cellarmind.sqlite
uv run cellarmind cellar list --database data/private/cellarmind.sqlite
uv run cellarmind report placement --database data/private/cellarmind.sqlite --year 2026
uv run cellarmind plan transfers --database data/private/cellarmind.sqlite --year 2026 --limit 50
uv run cellarmind report drinking-window --database data/private/cellarmind.sqlite --year 2026 --limit 50
uv run cellarmind recommend drinking --database data/private/cellarmind.sqlite --year 2026 --limit 50
```

Reports are advisory and read-only. They do not move bottles, update bottle statuses, or overwrite personal drinking windows.

## Reference drinking windows

Personal drinking windows come from your cellar data and are stored on `WineVariant`.

Reference drinking windows are separate evidence linked to `Wine`. They can come from manual entry, fetched web pages, online search, or AI estimates. They never overwrite personal windows automatically.

Manual reference:

```bash
uv run cellarmind reference-window add \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --source-name "Producer note" \
  --source-url "https://example.com/wine-page" \
  --drink-from-year 2024 \
  --drink-until-year 2032 \
  --confidence medium \
  --notes "Manual reference"
```

List and compare:

```bash
uv run cellarmind reference-window list --database data/private/cellarmind.sqlite --wine-id 123
uv run cellarmind report window-comparison --database data/private/cellarmind.sqlite --tolerance-years 2 --limit 50
```

## Fetch and search online reference sources

Fetch one known URL:

```bash
uv run cellarmind reference-window fetch \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --url "https://example.com/wine-page"
```

Save explicitly:

```bash
uv run cellarmind reference-window fetch \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --url "https://example.com/wine-page" \
  --source-name "Producer website" \
  --confidence medium \
  --save
```

Search:

```bash
uv run cellarmind reference-window search \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --limit 10
```

Custom query and fetch:

```bash
uv run cellarmind reference-window search \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --query "Ghislaine Barthod Bourgogne Rouge 2017 drinking window" \
  --fetch \
  --limit 10
```

Search and fetch are best-effort. Some sites block automated access. In that case, open the page in a browser and add the reference manually if useful.

## AI drinking-window estimates

AI estimates are stored as reference evidence, not as personal windows.

OpenAI dry-run:

```bash
export OPENAI_API_KEY="sk-..."
uv run cellarmind reference-window estimate \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --provider openai
```

OpenAI save:

```bash
uv run cellarmind reference-window estimate \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --provider openai \
  --save
```

Disable OpenAI web search to reduce cost:

```bash
uv run cellarmind reference-window estimate \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --provider openai \
  --no-web-search
```

Local Ollama with web evidence gathered through search and Jina Reader:

```bash
ollama serve
ollama pull llama3.1

uv run cellarmind reference-window estimate \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --provider ollama \
  --model llama3.1
```

Local Ollama without web evidence:

```bash
uv run cellarmind reference-window estimate \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --provider ollama \
  --model llama3.1 \
  --no-web-search
```

Useful AI environment variables:

```text
OPENAI_API_KEY
CELLARMIND_OPENAI_MODEL
CELLARMIND_OLLAMA_HOST
CELLARMIND_OLLAMA_MODEL
CELLARMIND_JINA_READER_BASE_URL
```

Stored source names:

```text
AI estimate (OpenAI)
AI estimate (local)
```

AI estimate notes include model/provider metadata, web-search status, token usage when available, rationale, returned sources, and gathered evidence.

## Development

Run the full local check suite:

```bash
./scripts/premerge.sh
uv run ruff check .
uv run ruff format --check .
```

`premerge.sh` must stay deterministic and must not require live internet or API credentials.

## Current status

Implemented so far:

- Python 3.13 / `uv` project setup
- CSV inspect, validate, normalize, and import
- canonical CSV schema with French aliases
- SQLite database initialization and import sessions
- physical bottle creation from quantities
- bottle formats and non-vintage wines
- cellar/location mapping
- bottle movement and location history
- bottle lifecycle statuses
- cellar profiles and capacity hints
- purchase prices and personal drinking windows
- database stats and audit
- placement report
- transfer planning
- drinking-window report
- drinking recommendations
- manual reference drinking windows
- fetched reference drinking windows
- online reference-source search
- personal/reference window comparison
- OpenAI drinking-window estimates
- local Ollama drinking-window estimates with Jina Reader evidence gathering
- tests and GitHub Actions CI


## Gemini drinking-window estimates

Gemini estimates use `GEMINI_API_KEY` and optional Google Search grounding.

```bash
export GEMINI_API_KEY="..."
uv run cellarmind reference-window estimate \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --provider gemini
```

Saved rows use `source_name = "AI estimate (Gemini)"`.
