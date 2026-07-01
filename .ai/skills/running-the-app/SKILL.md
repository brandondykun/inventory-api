---
name: running-the-app
description: How to run this Dockerized DRF app — the five environments (dev/test/e2e/staging/production), how Docker Compose overlays + env files are wired, the start/stop/manage/shell scripts, the container topology (web/worker/beat/db/redis/nginx), and common management/test/lint commands. Use when starting or stopping the stack, running migrations or management commands, running tests, or reasoning about environment differences.
---

# Running the app

Everything runs in Docker via `docker compose`. One **base** file defines the
service topology; exactly **one overlay** per environment is layered on top by
the scripts. Never run `docker compose` by hand for the wrong env — use the
scripts, which set `DJANGO_ENV` + `COMPOSE_PROJECT_NAME` and pick the overlay.

## TL;DR

```bash
./scripts/start.sh                    # build + start the dev stack (default)
./scripts/manage.sh createsuperuser   # run a manage.py command in the container
./scripts/stop.sh                     # stop dev;  add --volumes to drop the DB
./scripts/start.sh test               # run the full pytest suite, then tear down
```

Dev URLs: API `http://localhost:8000/`, Admin `/admin/`,
Swagger `/api/schema/swagger-ui/`, Health `/healthz/`.

## Environments

| Env | Settings module | Overlay | Web process | Docs | Notes |
|-----|-----------------|---------|-------------|------|-------|
| dev | `config.settings.dev` | `docker-compose.override.yml` | `runserver` | yes | source bind-mounted, debug toolbar, ports exposed |
| test | `config.settings.test` | `docker-compose.test.yml` | `pytest` | no | eager Celery (no worker/beat), MD5 hasher, locmem cache/email |
| e2e | `config.settings.e2e` | `docker-compose.e2e.yml` | gunicorn + nginx (`:8080`) | yes | prod-like, real Celery, isolated DB |
| staging | `config.settings.staging` | `docker-compose.staging.yml` | gunicorn + nginx (`:80`) | yes | prod hardening + docs |
| production | `config.settings.production` | `docker-compose.prod.yml` | gunicorn + nginx (`:80`) | no | hardened; secrets required, no defaults |

`staging` inherits from `production` (same hardening) and just turns docs on.
The settings module is selected by `DJANGO_SETTINGS_MODULE` (set per env file);
`DJANGO_ENV` is the informational label the scripts export.

## How the scripts map env → compose

`start.sh` / `stop.sh` / `manage.sh` / `shell.sh` all share the same dispatch:

```
dev → override.yml   test → test.yml   e2e → e2e.yml
staging → staging.yml   prod|production → prod.yml
```

Each exports `DJANGO_ENV=<env>` and `COMPOSE_PROJECT_NAME=api_<env>` (so each
env gets its own isolated container/volume namespace) and runs
`docker compose -f docker-compose.yml -f <overlay> ...`.

### `start.sh [env]` (default `dev`)
- Bootstraps `envs/.env.<env>` from `envs/.env.<env>.example` on first run
  (warns to set real secrets for staging/prod).
- **test**: runs the suite to completion (`up --build --abort-on-container-exit
  --exit-code-from web`), tears down, and exits with the suite's code.
- otherwise: `up -d --build`, then prints `ps` and the `logs -f` command.

### `stop.sh [env] [--volumes|-v]`
`docker compose ... down`. Pass `--volumes` (or `-v`) to also delete the named
volumes (**Postgres data, static, media** — destructive).

### `manage.sh <cmd> [args...]` — run any `manage.py` command
Targets dev by default; override with `ENV=...`. Uses the **running** `web`
container if up (`exec`), else a one-off `run --rm` container.
```bash
./scripts/manage.sh migrate
./scripts/manage.sh makemigrations users
./scripts/manage.sh createsuperuser
./scripts/manage.sh shell
ENV=staging ./scripts/manage.sh migrate
```

### `shell.sh` — interactive shell inside the `web` container
Same dev-default / `ENV=` override / running-or-one-off behavior.

## Container topology

Defined in `docker-compose.yml` (overlays add env files, build target, commands,
ports, and `nginx`):

- **db** — `postgres:17-alpine`, healthchecked, `postgres_data` volume.
- **redis** — `redis:7-alpine`, healthchecked. Broker (db 0), result backend
  (db 1), cache (db 2).
- **web** — Django. `runserver` in dev; `gunicorn` in prod-like envs.
- **worker** — `celery -A config worker`.
- **beat** — `celery -A config beat` with the DB-backed scheduler
  (`django_celery_beat`). *(test disables worker/beat — Celery runs eager.)*
- **nginx** — only in e2e/staging/prod; serves static/media and proxies to web.

Volumes: `postgres_data`, `static_volume`, `media_volume`.

### Container entrypoint (`scripts/entrypoint.sh`)
On every container start it waits for Postgres, then for non-Celery processes
applies `migrate --noinput` (idempotent) and, in e2e/staging/production, runs
`collectstatic --noinput`. Celery containers skip migrations. So you usually
**don't** need to run migrate manually after a build — it happens on boot.

## Docker image (`compose/django/Dockerfile`)

Multi-stage, uv-based, non-root `app` user. Targets:
- **dev** — includes the dev dependency group; source is bind-mounted by the dev
  overlay for live reload.
- **prod** — slim runtime, prod deps only, runs gunicorn.

## Env files (`envs/`)

`*.example` files are committed; the real `envs/.env.<env>` are gitignored and
created from the example on first `start.sh`. **Edit `envs/.env.staging` and
`envs/.env.prod` with real secrets** before deploying — production settings have
no fallback for `SECRET_KEY`, `ALLOWED_HOSTS`, etc. and fail loudly if missing.
Common knobs: `WEB_PORT`/`DB_PORT`/`REDIS_PORT` (dev port overrides),
`DJANGO_SETTINGS_MODULE`, Postgres creds, JWT lifetimes, social-provider creds,
`ENABLE_API_DOCS`, `CORS_ALLOWED_ORIGINS`/`CSRF_TRUSTED_ORIGINS`.

## Host-side dev (no container) — requires `uv`

```bash
uv run pytest                                   # tests (uses config.settings.test)
uv run ruff check . && uv run ruff format .     # lint + format
pre-commit install                              # enable pre-commit hooks
```
The test settings default `POSTGRES_HOST=localhost`, so a host-run suite expects
Postgres reachable locally (or set `POSTGRES_HOST`).
