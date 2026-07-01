#!/usr/bin/env bash
# Spin up the stack for a given environment.
#   ./scripts/start.sh [dev|test|e2e|staging|prod]   (default: dev)
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

# Ensure the env file exists; bootstrap from the committed example if not.
ENV_FILE="envs/.env.${ENV}"
if [[ ! -f "$ENV_FILE" ]]; then
    if [[ -f "${ENV_FILE}.example" ]]; then
        echo "[start] $ENV_FILE not found — creating it from ${ENV_FILE}.example"
        cp "${ENV_FILE}.example" "$ENV_FILE"
        [[ "$ENV" == "staging" || "$ENV" == "prod" ]] && \
            echo "[start] WARNING: edit $ENV_FILE and set real secrets before deploying."
    else
        echo "[start] Missing $ENV_FILE and no example to copy from." >&2
        exit 1
    fi
fi

export DJANGO_ENV="$ENV"
export COMPOSE_PROJECT_NAME="api_${ENV}"

COMPOSE=(docker compose -f docker-compose.yml -f "$OVERLAY")

# Test environment: run the suite to completion and report its exit code.
if [[ "$ENV" == "test" ]]; then
    echo "[start] Running test suite..."
    set +e
    "${COMPOSE[@]}" up --build --abort-on-container-exit --exit-code-from web web
    code=$?
    "${COMPOSE[@]}" down
    exit $code
fi

echo "[start] Building and starting '$ENV' stack..."
"${COMPOSE[@]}" up -d --build
echo
"${COMPOSE[@]}" ps
echo
echo "[start] '$ENV' is up. Tail logs with:"
echo "    docker compose -p $COMPOSE_PROJECT_NAME -f docker-compose.yml -f $OVERLAY logs -f"
