#!/usr/bin/env bash
# Container entrypoint: wait for Postgres, apply migrations, optionally collect
# static, then exec the container's command (runserver / gunicorn / celery).
set -euo pipefail

DJANGO_ENV="${DJANGO_ENV:-dev}"
POSTGRES_HOST="${POSTGRES_HOST:-db}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

echo "[entrypoint] environment: ${DJANGO_ENV}"

# --- Wait for the database -------------------------------------------------
echo "[entrypoint] waiting for postgres at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
until python -c "
import os, socket, sys
s = socket.socket()
s.settimeout(2)
try:
    s.connect((os.environ.get('POSTGRES_HOST', 'db'), int(os.environ.get('POSTGRES_PORT', '5432'))))
except OSError:
    sys.exit(1)
finally:
    s.close()
" 2>/dev/null; do
    echo "[entrypoint] postgres unavailable - sleeping 1s"
    sleep 1
done
echo "[entrypoint] postgres is up"

# --- The first CLI arg tells us what kind of process this is ---------------
# Web/worker/beat all need migrations applied once; we run them on every
# container start (Django migrations are idempotent) except for celery, which
# waits for the web container to have migrated.
case "${1:-}" in
    celery)
        echo "[entrypoint] celery process - skipping migrations"
        ;;
    *)
        echo "[entrypoint] applying migrations"
        python manage.py migrate --noinput

        # Collect static for prod-like environments (nginx serves them).
        if [[ "${DJANGO_ENV}" == "production" || "${DJANGO_ENV}" == "staging" || "${DJANGO_ENV}" == "e2e" ]]; then
            echo "[entrypoint] collecting static files"
            python manage.py collectstatic --noinput
        fi
        ;;
esac

echo "[entrypoint] starting: $*"
exec "$@"
