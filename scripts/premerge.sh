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

echo "==> Updating sample cellar profile"
uv run cellarmind cellar update "Example" \
  --database "$DATABASE_PATH" \
  --purpose "aging" \
  --capacity-estimate 100 \
  --capacity-warning-threshold 90 \
  --notes "Sample aging cellar"

echo "==> Listing cellars"
uv run cellarmind cellar list --database "$DATABASE_PATH"

echo "==> Database stats"
uv run cellarmind db stats --path "$DATABASE_PATH"

echo "==> Listing bottles"
uv run cellarmind list bottles --database "$DATABASE_PATH" --limit 10

echo "==> Auditing database"
uv run cellarmind db audit --path "$DATABASE_PATH"

echo "==> Placement report"
uv run cellarmind report placement --database "$DATABASE_PATH" --year 2026 --limit 10

echo "==> Transfer plan"
uv run cellarmind plan transfers --database "$DATABASE_PATH" --year 2026 --limit 10

echo
echo "Pre-merge checks passed."
