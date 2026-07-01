#!/usr/bin/env bash
# Run a Django management command inside the web container.
#   ./scripts/manage.sh <command> [args...]
#
# Examples:
#   ./scripts/manage.sh migrate
#   ./scripts/manage.sh makemigrations users
#   ./scripts/manage.sh createsuperuser
#   ./scripts/manage.sh shell
#
# Targets the dev stack by default. Override with the ENV variable:
#   ENV=staging ./scripts/manage.sh migrate
#
# Uses the already-running web container when one is up (fast); otherwise
# spins up a one-off container that is removed when the command finishes.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ $# -eq 0 ]]; then
    echo "Usage: ./scripts/manage.sh <command> [args...]" >&2
    echo "  e.g. ./scripts/manage.sh migrate" >&2
    exit 1
fi

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

# Only suppress the pseudo-TTY when NOT attached to a terminal (piped/CI use).
# (Empty-array expansion under `set -u` is unsafe on bash 3.2, so use a string.)
TTY_FLAG=""
[[ -t 0 ]] || TTY_FLAG="-T"

# Prefer exec into the live container; fall back to a one-off run if it's down.
if [[ -n "$("${COMPOSE[@]}" ps --status running -q web 2>/dev/null)" ]]; then
    exec "${COMPOSE[@]}" exec ${TTY_FLAG} web python manage.py "$@"
else
    echo "[manage] web container not running — using a one-off container." >&2
    exec "${COMPOSE[@]}" run --rm ${TTY_FLAG} web python manage.py "$@"
fi
