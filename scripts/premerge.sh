#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

CANONICAL_CSV="$TMP_DIR/cave.canonical.csv"

echo "==> Formatting"
uv run ruff format .

echo "==> Running tests"
uv run pytest

echo "==> Running ruff"
uv run ruff check .

echo "==> Verifying formatting"
uv run ruff format --check .

echo "==> Validating sample CSV"
uv run cellarmind validate examples/cave.sample.csv

echo "==> Normalizing sample CSV"
uv run cellarmind normalize examples/cave.sample.csv --output "$CANONICAL_CSV"

echo "==> Canonical CSV preview"
cat "$CANONICAL_CSV"

DATABASE_PATH="$TMP_DIR/cellarmind.sqlite"

echo "==> Initializing database"
uv run cellarmind db init --path "$DATABASE_PATH"

echo "==> Importing sample CSV"
uv run cellarmind import examples/cave.sample.csv --database "$DATABASE_PATH"

echo "==> Database stats"
uv run cellarmind db stats --path "$DATABASE_PATH"

echo
echo "Pre-merge checks passed."
