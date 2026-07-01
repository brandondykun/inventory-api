#!/usr/bin/env bash
# Run the API test suite (pytest) in an isolated test stack.
#   ./scripts/test.sh [pytest args...]
#
# Runs against the `test` environment (docker-compose.test.yml): its own
# Postgres, test settings, eager Celery, fast password hashing. Any extra
# arguments are passed straight through to pytest.
#
# Examples:
#   ./scripts/test.sh                                   # whole suite
#   ./scripts/test.sh apps/users                        # one app
#   ./scripts/test.sh -k login -x                       # filter + stop on first fail
#   ./scripts/test.sh apps/authentication/tests/test_auth.py --no-cov
#
# Isolated from the dev stack (separate Compose project), so it's safe to run
# while `./scripts/start.sh dev` is up. The test stack is torn down on exit.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

ENV="test"
OVERLAY="docker-compose.test.yml"

# Ensure the env file exists; bootstrap from the committed example if not.
ENV_FILE="envs/.env.${ENV}"
if [[ ! -f "$ENV_FILE" ]]; then
    if [[ -f "${ENV_FILE}.example" ]]; then
        echo "[test] $ENV_FILE not found — creating it from ${ENV_FILE}.example"
        cp "${ENV_FILE}.example" "$ENV_FILE"
    else
        echo "[test] Missing $ENV_FILE and no example to copy from." >&2
        exit 1
    fi
fi

export DJANGO_ENV="$ENV"
export COMPOSE_PROJECT_NAME="inventory_api_${ENV}"

COMPOSE=(docker compose -f docker-compose.yml -f "$OVERLAY")

# Build the (dev-target) image once so a stale image doesn't mask code changes.
echo "[test] Building test image..."
"${COMPOSE[@]}" build web

# Run pytest in a one-off container (deps started via depends_on). Don't let a
# non-zero pytest exit abort the script before we tear the stack down.
echo "[test] Running test suite..."
set +e
"${COMPOSE[@]}" run --rm web pytest "$@"
code=$?
set -e

echo "[test] Tearing down test stack..."
"${COMPOSE[@]}" down

exit "$code"
