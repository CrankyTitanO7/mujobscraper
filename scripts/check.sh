#!/usr/bin/env bash
# Repository checks: lint, formatting, and tests.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "==> ruff check"
uv run ruff check src tests user/parseEgToSet.py

echo "==> ruff format --check"
uv run ruff format --check src tests user/parseEgToSet.py

echo "==> pytest"
uv run pytest -q

echo "All checks passed."
