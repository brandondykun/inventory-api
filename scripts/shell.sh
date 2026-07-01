#!/usr/bin/env bash
# Drop into an interactive shell inside the web container.
#   ./scripts/shell.sh
#
# Targets the dev stack by default. Override with the ENV variable:
#   ENV=staging ./scripts/shell.sh
#
# Once inside you can run `python manage.py ...`, inspect files, etc. Uses the
# already-running web container when one is up; otherwise spins up a one-off
# container that is removed on exit.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

ENV="${ENV:-dev}"

case "$ENV" in
    dev)              OVERLAY="docker-compose.override.yml" ;;
    test)             OVERLAY="docker-compose.test.yml" ;;
    e2e)              OVERLAY="docker-compose.e2e.yml" ;;
    staging)          OVERLAY="docker-compose.staging.yml" ;;
    prod|production)  ENV="prod"; OVERLAY="docker-compose.prod.yml" ;;
    *)
        echo "Unknown environment: '$ENV' (expected dev|test|e2e|staging|prod)" >&2
        exit 1
        ;;
esac

export DJANGO_ENV="$ENV"
export COMPOSE_PROJECT_NAME="inventory_api_${ENV}"

COMPOSE=(docker compose -f docker-compose.yml -f "$OVERLAY")

# The slim image ships bash; fall back to sh if it's ever swapped out.
SHELL_CMD='bash || sh'

if [[ -n "$("${COMPOSE[@]}" ps --status running -q web 2>/dev/null)" ]]; then
    exec "${COMPOSE[@]}" exec web sh -c "$SHELL_CMD"
else
    echo "[shell] web container not running — using a one-off container." >&2
    exec "${COMPOSE[@]}" run --rm web sh -c "$SHELL_CMD"
fi
