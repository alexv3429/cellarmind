# CellarMind

CellarMind is a Python CLI for enriching a wine cellar CSV with maturity windows,
sources, confidence scores, and reports.

The project is designed to keep personal cellar data private: `data/`, `cache/`,
`logs/`, and generated reports are ignored by Git.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

## Quick start

```bash
uv sync --extra dev
uv run cellarmind --help
uv run pytest
```

## Use with your own CSV

Do not commit your personal CSV. Copy it locally into `data/`:

```bash
cp /path/to/your/cave.csv data/cave.csv
uv run cellarmind inspect data/cave.csv
uv run cellarmind enrich data/cave.csv --offline --limit 50
```

## Current status

This first milestone contains the project bootstrap:

- uv project configuration
- CLI skeleton
- CSV inspection command
- offline enrichment placeholder
- tests
- GitHub Actions
- privacy-focused `.gitignore`

