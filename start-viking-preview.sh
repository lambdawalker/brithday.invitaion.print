#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
exec uv run python preview.py --background ./backgrounds/B.png "$@"
