# Workflows

This document describes practical CellarMind workflows.

## Import and audit a cellar

```bash
mkdir -p data/private
cp /path/to/your/cave.csv data/private/cave.csv

uv run cellarmind inspect data/private/cave.csv
uv run cellarmind validate data/private/cave.csv
uv run cellarmind normalize data/private/cave.csv --output /tmp/cave.canonical.csv
uv run cellarmind import data/private/cave.csv --database data/private/cellarmind.sqlite

uv run cellarmind db stats --path data/private/cellarmind.sqlite
uv run cellarmind db audit --path data/private/cellarmind.sqlite
```

Use `--cellar-map` when location codes imply cellar names:

```bash
uv run cellarmind import data/private/cave.csv \
  --database data/private/cellarmind.sqlite \
  --cellar-map data/private/cellar-map.csv
```

## Manual bottle management

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
  --location "A12"
```

Move a bottle:

```bash
uv run cellarmind bottle move 123 \
  --database data/private/cellarmind.sqlite \
  --cellar "Main cellar" \
  --location "A12"
```

Update status:

```bash
uv run cellarmind bottle mark-opened 123 --database data/private/cellarmind.sqlite
uv run cellarmind bottle mark-consumed 123 --database data/private/cellarmind.sqlite
uv run cellarmind bottle mark-gifted 123 --database data/private/cellarmind.sqlite
uv run cellarmind bottle mark-sold 123 --database data/private/cellarmind.sqlite
uv run cellarmind bottle mark-lost 123 --database data/private/cellarmind.sqlite
```

Out-of-cellar statuses close the active location. Opened bottles keep their active location.

## Cellar profiles

```bash
uv run cellarmind cellar update "Main cellar" \
  --database data/private/cellarmind.sqlite \
  --purpose aging \
  --capacity-estimate 350 \
  --capacity-warning-threshold 330 \
  --notes "Main long-term aging cellar"

uv run cellarmind cellar list --database data/private/cellarmind.sqlite
```

Supported purposes:

```text
aging
drink_soon
mixed
staging
overflow
```

## Placement and drinking reports

```bash
uv run cellarmind report placement \
  --database data/private/cellarmind.sqlite \
  --year 2026 \
  --limit 50

uv run cellarmind plan transfers \
  --database data/private/cellarmind.sqlite \
  --year 2026 \
  --limit 50

uv run cellarmind report drinking-window \
  --database data/private/cellarmind.sqlite \
  --year 2026 \
  --limit 50

uv run cellarmind recommend drinking \
  --database data/private/cellarmind.sqlite \
  --year 2026 \
  --limit 50
```

These commands are advisory and read-only.

Drinking-window classifications:

```text
overdue
ready
too_young
unknown
```

Recommendation actions:

```text
drink_now
consider_drinking
hold
review
```

## Reference-window workflow

Add a manual reference:

```bash
uv run cellarmind reference-window add \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --source-name "Producer note" \
  --source-url "https://example.com/wine-page" \
  --drink-from-year 2024 \
  --drink-until-year 2032 \
  --confidence medium
```

Fetch a known URL:

```bash
uv run cellarmind reference-window fetch \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --url "https://example.com/wine-page"
```

Save a fetched candidate explicitly:

```bash
uv run cellarmind reference-window fetch \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --url "https://example.com/wine-page" \
  --source-name "Producer website" \
  --confidence medium \
  --save
```

Search online sources:

```bash
uv run cellarmind reference-window search \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --limit 10
```

Search with fetch:

```bash
uv run cellarmind reference-window search \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --fetch \
  --limit 10
```

Compare personal and reference windows:

```bash
uv run cellarmind report window-comparison \
  --database data/private/cellarmind.sqlite \
  --tolerance-years 2 \
  --limit 50
```

Reference windows never overwrite personal windows automatically.

## OpenAI estimate workflow

Set an API key:

```bash
export OPENAI_API_KEY="sk-..."
```

Dry-run:

```bash
uv run cellarmind reference-window estimate \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --provider openai
```

Save:

```bash
uv run cellarmind reference-window estimate \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --provider openai \
  --save
```

Cheaper no-web-search mode:

```bash
uv run cellarmind reference-window estimate \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --provider openai \
  --no-web-search
```

OpenAI estimates are saved as:

```text
source_name = "AI estimate (OpenAI)"
source_url = NULL
```

## Local Ollama + Jina Reader workflow

Start Ollama and pull a model:

```bash
ollama serve
ollama pull llama3.1
```

Dry-run with local AI and web evidence:

```bash
uv run cellarmind reference-window estimate \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --provider ollama \
  --model llama3.1
```

Save:

```bash
uv run cellarmind reference-window estimate \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --provider ollama \
  --model llama3.1 \
  --save
```

Use only search snippets, without Jina Reader:

```bash
uv run cellarmind reference-window estimate \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --provider ollama \
  --model llama3.1 \
  --search-provider jina \
  --web-reader none
```

Fully local, no web evidence:

```bash
uv run cellarmind reference-window estimate \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --provider ollama \
  --model llama3.1 \
  --no-web-search
```

Local estimates are saved as:

```text
source_name = "AI estimate (local)"
source_url = NULL
```

## Real-cellar test sequence

```bash
uv run cellarmind list bottles --database data/private/cellarmind.sqlite --limit 30

uv run cellarmind reference-window search \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --limit 10

uv run cellarmind reference-window estimate \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --provider ollama \
  --model llama3.1

uv run cellarmind reference-window estimate \
  --database data/private/cellarmind.sqlite \
  --wine-id 123 \
  --provider ollama \
  --model llama3.1 \
  --save

uv run cellarmind report window-comparison \
  --database data/private/cellarmind.sqlite \
  --tolerance-years 2 \
  --limit 50
```


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
