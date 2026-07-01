# API — Django REST Framework Base

A generic, Dockerized Django REST Framework starter to fork for new projects.

## Features

- **Django 5.2 + DRF 3.17**, Python 3.13, Postgres 17, Redis 7
- **uv** for fast, locked dependency management
- **Split settings** per environment: `dev`, `test`, `e2e`, `staging`, `production`
- **JWT auth** (Simple JWT) with web/mobile-aware delivery:
  - Web → tokens in `HttpOnly` cookies
  - Mobile → tokens in the response body (`X-Client-Type: mobile`)
- **Custom user model** (email login, UUID pk)
- **drf-spectacular** OpenAPI schema + Swagger/Redoc (dev & staging only)
- **django-unfold** admin theme
- **Celery + Redis** worker & beat (DB-backed schedule)
- **nginx + gunicorn** for staging/production
- **pytest-django**, **ruff**, **pre-commit**, **django-debug-toolbar**

## Layout

```
config/            # settings (split), urls, wsgi/asgi, celery
apps/
  common/          # base models, pagination, exception handler, health check
  users/           # custom user model, admin, register/me endpoints
  authentication/  # JWT login/refresh/logout + cookie-or-header auth class
compose/           # Dockerfiles + nginx configs
envs/              # per-environment .env templates (*.example committed)
scripts/           # start.sh / stop.sh / manage.sh / shell.sh / entrypoint.sh
```

## Quick start (development)

```bash
./scripts/start.sh                       # builds & starts the dev stack (copies env from example)
./scripts/manage.sh createsuperuser      # run any manage.py command in the container
```

- API:        http://localhost:8000/
- Admin:      http://localhost:8000/admin/
- Swagger UI: http://localhost:8000/api/schema/swagger-ui/
- Health:     http://localhost:8000/healthz/

Stop it:

```bash
./scripts/stop.sh            # add --volumes to also drop the database
```

## Environments

| Env       | Settings module               | Command            | Docs | Notes                         |
|-----------|-------------------------------|--------------------|------|-------------------------------|
| dev       | `config.settings.dev`         | runserver          | yes  | source-mounted, debug toolbar |
| test      | `config.settings.test`        | pytest             | no   | eager Celery, fast hashers    |
| e2e       | `config.settings.e2e`         | gunicorn + nginx   | yes  | prod-like, isolated DB        |
| staging   | `config.settings.staging`     | gunicorn + nginx   | yes  | hardened                      |
| production| `config.settings.production`  | gunicorn + nginx   | no   | hardened, secrets required    |

Run any of them:

```bash
./scripts/start.sh test       # run the test suite
./scripts/start.sh staging
./scripts/start.sh prod
```

Each environment reads `envs/.env.<env>` (created from the matching `.example`
on first run; **edit staging/prod with real secrets**).

## Authentication

One set of endpoints serves both client types; the `X-Client-Type` header
(default `web`) selects token delivery.

| Endpoint              | Web                              | Mobile (`X-Client-Type: mobile`) |
|-----------------------|----------------------------------|----------------------------------|
| `POST /api/auth/login/`   | sets HttpOnly cookies; user in body | tokens in body                   |
| `POST /api/auth/refresh/` | reads refresh cookie; re-sets cookie | refresh in body → new access     |
| `POST /api/auth/logout/`  | blacklists refresh; clears cookies | refresh in body → blacklisted    |

`CookieOrHeaderJWTAuthentication` (the default auth class) reads the access
token from the cookie, falling back to the `Authorization: Bearer` header.

> **CSRF (web only).** Because the browser sends the access-token cookie
> ambiently, the auth class runs Django's CSRF check on **cookie-authenticated
> unsafe requests** (POST/PUT/PATCH/DELETE). Login responses set a readable
> `csrftoken` cookie; a web/SPA client must echo it back as the `X-CSRFToken`
> header on those requests. `Bearer`-header (mobile/API) clients send no ambient
> cookie and are exempt. `SameSite` is defense-in-depth, **not** the primary
> control — so a cross-origin SPA on `SameSite=None` is still protected. For a
> cross-origin SPA, set `CORS_ALLOWED_ORIGINS`/`CSRF_TRUSTED_ORIGINS` to its
> origin (credentialed CORS forbids `*`).
>
> Note: `login`/`refresh`/`logout` themselves are not CSRF-checked (they don't
> use the default auth class); they rely on `SameSite` and on requiring a valid
> token. The CSRF control covers authenticated, state-changing API endpoints.

### Identity layer (django-allauth)

[django-allauth](https://docs.allauth.org/) owns accounts, email verification,
social providers, and account linking. Our JWT views stay the single token
mechanism — **dj-rest-auth is used only to verify social tokens**, then hands
off to the same web-cookie/mobile-body delivery as email/password login.

- **Registration** `POST /api/users/register/` creates the user + an allauth
  `EmailAddress` (so verification and social-account linking work), then returns
  `201`. When verification is enabled, a confirmation email is sent.
  Enumeration-safe: registering an **already-registered** email returns the same
  `201` body (no duplicate created) and notifies the address owner out of band,
  so the response can't be used to discover which emails have accounts.
- **Email verification** is env-driven via `ACCOUNT_EMAIL_VERIFICATION`:
  `optional` (dev default — login allowed before verifying), `mandatory` (prod
  default — unverified email/password logins are blocked), or `none` (tests).
  Confirmation/reset links resolve under `/accounts/…` (allauth's routes).
- **Account linking**: signing in with a provider whose email matches an
  existing account links to it (instead of duplicating) — but only when the
  provider asserts the email is *verified* (see `CustomSocialAccountAdapter`).

### Social sign-in

```
POST /api/auth/social/google/
POST /api/auth/social/apple/
```

The client obtains a token from the provider SDK (native on mobile, JS/redirect
on web) and POSTs it; the response is your JWTs (web cookies or mobile body,
same as login). Accepted body fields: `id_token` (native apps), or
`access_token` / `code` (web flows). Example:

```bash
curl -X POST http://localhost:8000/api/auth/social/google/ \
  -H 'Content-Type: application/json' \
  -d '{"id_token": "<google-id-token>"}'        # add -H 'X-Client-Type: mobile' for body tokens
```

#### Provider configuration you must supply

Credentials come from the environment (`SOCIALACCOUNT_PROVIDERS` reads them in
`config/settings/base.py`); sign-in for a provider is inert until set. Leave a
provider's vars blank to disable it.

**Google** — [Google Cloud Console](https://console.cloud.google.com/) →
*APIs & Services → Credentials → Create OAuth client ID*:
- Create a **Web application** client (and/or iOS/Android clients for native).
- Add your SPA origin to *Authorized JavaScript origins* and redirect URIs.
- Set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.

**Apple** — [Apple Developer](https://developer.apple.com/account/) → *Certificates,
Identifiers & Profiles*. Sign in with Apple needs four values mapped to these
env vars (allauth's field names are non-obvious; the mapping is handled for you
in settings):

| Env var | What it is | Where to get it |
|---|---|---|
| `APPLE_CLIENT_ID` | **Services ID** (web) or app **Bundle ID** (native) | *Identifiers* → register a Services ID / App ID, enable *Sign in with Apple* |
| `APPLE_TEAM_ID` | 10-char **Team ID** | Top-right of the Developer account membership page |
| `APPLE_KEY_ID` | **Key ID** of the sign-in key | *Keys* → create a key with *Sign in with Apple* enabled |
| `APPLE_PRIVATE_KEY` | Full contents of the **`.p8`** key file | Downloaded once when you create the key — store it as a secret |

For web, also register your return URL under the Services ID's *Sign in with
Apple* config and set `APPLE_CALLBACK_URL`. Apple verification can't be
exercised without these real credentials, so its tests are mocked.

## Common tasks

```bash
# any manage.py command in the container (defaults to the dev stack)
./scripts/manage.sh migrate
./scripts/manage.sh makemigrations
./scripts/manage.sh createsuperuser
./scripts/manage.sh shell                # Django shell
ENV=staging ./scripts/manage.sh migrate  # target another environment

# drop into an interactive shell inside the container
./scripts/shell.sh

# tests in an isolated containerized stack (own Postgres; args pass through to pytest)
./scripts/test.sh                                   # whole suite
./scripts/test.sh -k login -x                       # filter + stop on first fail

# tests (host-side, requires uv + a reachable Postgres)
uv run pytest

# lint/format
uv run ruff check . && uv run ruff format .
pre-commit install
```

## Forking checklist

1. Update `[project].name`/description in `pyproject.toml`.
2. Set `API_TITLE`, `ADMIN_SITE_TITLE`, image name (`api-app` in compose), and
   `COMPOSE_PROJECT_NAME` prefix (`api_` in the scripts).
3. Add your apps under `apps/` and register them in `LOCAL_APPS`.
4. Fill in real secrets in `envs/.env.staging` / `envs/.env.prod`.
