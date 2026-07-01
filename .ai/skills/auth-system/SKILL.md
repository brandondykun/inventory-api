---
name: auth-system
description: How authentication works in this DRF API — JWT login/refresh/logout, web-cookie vs mobile-body token delivery, the CookieOrHeaderJWTAuthentication class, registration + email verification, social sign-in (Google/Apple via allauth + dj-rest-auth), and the custom email/UUID user model. Use when working on anything touching auth, tokens, login, users, sessions, or accounts.
---

# Authentication system

One set of endpoints serves **both** web and mobile clients. The
`X-Client-Type` request header (default `web`) selects how tokens are
delivered; everything else is identical.

- **Web** (`X-Client-Type` absent or `web`) → tokens set as **HttpOnly cookies**;
  response body carries only `{"user": {...}}`.
- **Mobile** (`X-Client-Type: mobile`) → tokens returned **in the body**:
  `{"access": "...", "refresh": "...", "user": {...}}`; no cookies.

Source of truth: `apps/authentication/` and `apps/users/`. Settings live in
`config/settings/base.py` (`REST_FRAMEWORK`, `SIMPLE_JWT`, `AUTH_COOKIE_*`,
allauth `ACCOUNT_*`/`SOCIALACCOUNT_*`, `REST_AUTH`).

## URL map

Mounted in `config/urls.py`; app routes in each app's `urls.py`.

| Method | Path | View (`apps/...`) |
|--------|------|-------------------|
| POST | `/api/auth/login/` | `authentication.views.LoginView` |
| POST | `/api/auth/refresh/` | `authentication.views.RefreshView` |
| POST | `/api/auth/logout/` | `authentication.views.LogoutView` |
| POST | `/api/auth/social/google/` | `authentication.views.GoogleLoginView` |
| POST | `/api/auth/social/apple/` | `authentication.views.AppleLoginView` |
| POST | `/api/users/register/` | `users.views.RegisterView` |
| GET/PATCH | `/api/users/me/` | `users.views.MeView` |
| * | `/accounts/...` | allauth (email confirm, password reset) |

## How requests are authenticated

`CookieOrHeaderJWTAuthentication` (`apps/authentication/authentication.py`) is the
**global default** auth class (`REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]`),
paired with a global `IsAuthenticated` default permission. It subclasses Simple
JWT's `JWTAuthentication` and resolves the access token in this order:

1. `Authorization: Bearer <token>` header (mobile / API clients), else
2. the access-token **cookie** named by `settings.AUTH_COOKIE_ACCESS`
   (default `access_token`) — used by web browsers.

Returns `None` (anonymous) when neither is present; otherwise validates and
returns `(user, validated_token)`.

**CSRF on the cookie path.** When the token comes from the **cookie** (not the
`Bearer` header), the class runs Django's CSRF check (`enforce_csrf`, the same
mechanism as DRF's `SessionAuthentication`) — because the browser sends the
cookie ambiently, an unsafe (POST/PUT/PATCH/DELETE) request must carry a valid
CSRF token or it's rejected with `403 CSRF Failed`. The `Bearer`-header path is
exempt (no ambient cookie → not reachable by CSRF). Web login responses bootstrap
a readable `csrftoken` cookie (`ensure_csrf_cookie` in `utils.py`), which a
web/SPA client echoes back as the `X-CSRFToken` header. `SameSite` is
defense-in-depth, not the primary control. Note: `login`/`refresh`/`logout` use
no auth class, so they are *not* CSRF-checked — they rely on `SameSite` plus
requiring a valid token; the CSRF control protects authenticated, state-changing
endpoints.

To make an endpoint public, set on the view:
```python
authentication_classes: list = []
permission_classes = [AllowAny]
```
(That's exactly what `HealthCheckView` and `LogoutView` do.)

## Token delivery helpers

`apps/authentication/utils.py` centralizes the web/mobile split:

- `is_web_client(request)` → `request.headers.get("X-Client-Type", "web") != "mobile"`.
- `set_auth_cookies(response, access, refresh)` / `set_access_cookie` /
  `set_refresh_cookie` / `clear_auth_cookies` — set/clear cookies using the
  `AUTH_COOKIE_*` settings, with `max_age` taken from the Simple JWT lifetimes.

Cookie flags come from settings (`config/settings/base.py`):

| Setting | Default | Notes |
|---------|---------|-------|
| `AUTH_COOKIE_ACCESS` | `access_token` | access-token cookie name |
| `AUTH_COOKIE_REFRESH` | `refresh_token` | refresh-token cookie name |
| `AUTH_COOKIE_HTTP_ONLY` | `True` | hardcoded — always HttpOnly |
| `AUTH_COOKIE_SECURE` | `False` (dev) | **`True` in production** |
| `AUTH_COOKIE_SAMESITE` | `Lax` | |
| `AUTH_COOKIE_PATH` / `AUTH_COOKIE_DOMAIN` | `/` / `None` | |

## Flows

### Login — `POST /api/auth/login/`
`LoginView` extends `TokenObtainPairView` with `LoginSerializer`
(`USERNAME_FIELD = "email"`; adds an `email` claim to the token). If
`ACCOUNT_EMAIL_VERIFICATION == "mandatory"` and the user's email is unverified,
login is rejected (`code="email_not_verified"`). On success:
- **web** → 200, `{"user": ...}`, access+refresh cookies set (+ a `csrftoken`
  cookie, see CSRF above).
- **mobile** → 200, `{"access", "refresh", "user"}`, no cookies.

**Throttled.** `throttle_scope = "login"` (`ScopedRateThrottle`), default
`10/min` per client IP (`THROTTLE_LOGIN`) to blunt credential stuffing — a
dedicated bucket, separate from the global `anon`/`user` throttles. Behind a
proxy this keys on the real client IP only if `REST_FRAMEWORK["NUM_PROXIES"]` is
set (0 in dev; production defaults it to 1 for the bundled nginx) — otherwise
every client shares the proxy's bucket.

### Refresh — `POST /api/auth/refresh/`
`RefreshView` extends `TokenRefreshView`.
- **web** → reads refresh from the `AUTH_COOKIE_REFRESH` cookie; responds
  `{"detail": "Token refreshed."}` and re-sets the access cookie (and a rotated
  refresh cookie, since `ROTATE_REFRESH_TOKENS=True`).
- **mobile** → reads `refresh` from the body; returns new tokens in the body.

### Logout — `POST /api/auth/logout/`
`LogoutView` is `AllowAny` with no auth class. Reads the refresh token from the
cookie (web) or `request.data["refresh"]` (mobile), **blacklists** it
(idempotently — `TokenError` suppressed), clears cookies for web, returns
**205 Reset Content**.

### Registration — `POST /api/users/register/`
`RegisterView` (`CreateAPIView`, `RegisterSerializer`) creates the user via
`User.objects.create_user(...)`, then in `perform_create` creates an allauth
`EmailAddress` (`primary=True, verified=False`) so verification + social linking
work. Sends a confirmation email unless `ACCOUNT_EMAIL_VERIFICATION == "none"`.
Returns **201** with a fixed `{"detail": ...}` body (never the user object).

**Enumeration-safe.** `RegisterSerializer` declares `email` explicitly to drop
the model's auto `UniqueValidator` (which would 400 "already exists" and leak
account existence). An already-registered email instead returns the *same* 201
body, creates no duplicate, and emails the real owner a heads-up
(`_notify_existing_account`). Don't reintroduce a uniqueness error on this view.

**Throttled.** `throttle_scope = "register"` (`ScopedRateThrottle`), default
`10/min` per client IP (`THROTTLE_REGISTER`).

## JWT configuration (`SIMPLE_JWT`)

- `ACCESS_TOKEN_LIFETIME` = **15 min** (env `JWT_ACCESS_LIFETIME_MIN`)
- `REFRESH_TOKEN_LIFETIME` = **7 days** (env `JWT_REFRESH_LIFETIME_DAYS`)
- `ROTATE_REFRESH_TOKENS=True`, `BLACKLIST_AFTER_ROTATION=True`,
  `UPDATE_LAST_LOGIN=True`, `AUTH_HEADER_TYPES=("Bearer",)`
- Blacklisting requires `rest_framework_simplejwt.token_blacklist` (installed).

## Email verification (`ACCOUNT_EMAIL_VERIFICATION`)

Env-driven; gates email/password login:
- `optional` — **dev default**; login allowed before verifying.
- `mandatory` — **production default**; unverified email/password logins blocked.
- `none` — **tests**; verification skipped.

Confirmation / reset links resolve under `/accounts/...` (allauth). A fork with
its own frontend can override the adapter's `get_email_confirmation_url()`.

## Social sign-in (Google / Apple)

The client gets a token from the provider SDK and POSTs it; the response is our
own JWTs (web cookies or mobile body — same delivery as login).

- Views: `GoogleLoginView` / `AppleLoginView` extend a `_BaseSocialLoginView`
  that subclasses `dj_rest_auth`'s `SocialLoginView` and overrides
  `get_response()` to issue our JWTs via `_issue_jwt_response(request, user)`.
- **dj-rest-auth is used *only* as the social-token verification bridge** — our
  JWT views remain the single token mechanism. `REST_AUTH` disables its token
  model and session login (`USE_JWT=True`, `TOKEN_MODEL=None`, `SESSION_LOGIN=False`).
- Accepted body fields: `id_token` (native apps) **or** `access_token` / `code`
  (web OAuth flows).
- **Account linking** (`apps/authentication/adapters.py` →
  `CustomSocialAccountAdapter.pre_social_login`): a provider login whose
  **verified** email matches an existing user links to that account instead of
  duplicating — only when both the provider asserts the email verified and the
  local account is itself verified (or has no `EmailAddress` yet).
- Provider creds come from the environment (`SOCIALACCOUNT_PROVIDERS` in
  `base.py`); a provider is inert until its vars are set. Apple's env-var mapping
  is non-obvious — see the README "Social sign-in" table and `envs/*.example`.
- `SOCIALACCOUNT_STORE_TOKENS=False`, `SOCIALACCOUNT_EMAIL_VERIFICATION="none"`
  (we trust the provider's verified email).

## Custom user model (`apps/users`)

`User` extends `AbstractBaseUser, PermissionsMixin, BaseModel`:
- **Email is the identifier** (`USERNAME_FIELD = "email"`, unique;
  `REQUIRED_FIELDS = []`). No username field.
- **UUID primary key** + timestamps (from `apps.common.models.BaseModel`).
- `first_name` / `last_name`, `is_staff`, `is_active`; `full_name` property.
- `UserManager` (`apps/users/managers.py`) normalizes email and implements
  `create_user` / `create_superuser`.
- `AUTH_USER_MODEL = "users.User"`. allauth is configured email-first
  (`ACCOUNT_LOGIN_METHODS={"email"}`, `ACCOUNT_USER_MODEL_USERNAME_FIELD=None`).

## Web-cookie security notes

Credentialed CORS forbids `*`. For an SPA on another origin you must set
`CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` to the SPA origin
(`CORS_ALLOW_CREDENTIALS=True` is already on). Cookie-authenticated unsafe
methods are CSRF-checked by `CookieOrHeaderJWTAuthentication` (see "How requests
are authenticated") — the SPA reads the `csrftoken` cookie set at login and sends
it back as `X-CSRFToken`. `SameSite` is defense-in-depth on top of that, so a
cross-origin SPA on `SameSite=None` is still protected. In production, cookies
are `Secure` (TLS-only).
