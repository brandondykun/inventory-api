#!/usr/bin/env bash
# Tear down the stack for a given environment.
#   ./scripts/stop.sh [dev|test|e2e|staging|prod] [--volumes]
# Pass --volumes (or -v) to also delete named volumes (database, static, media).
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

ENV="${1:-dev}"

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

VOLUMES=""
if [[ "${2:-}" == "--volumes" || "${2:-}" == "-v" ]]; then
    VOLUMES="--volumes"
    echo "[stop] Removing named volumes for '$ENV' (data will be lost)."
fi

export DJANGO_ENV="$ENV"
export COMPOSE_PROJECT_NAME="inventory_api_${ENV}"

echo "[stop] Stopping '$ENV' stack..."
docker compose -f docker-compose.yml -f "$OVERLAY" down $VOLUMES
echo "[stop] Done."
