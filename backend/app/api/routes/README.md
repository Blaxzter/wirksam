# API Routes

This directory holds the FastAPI routers, one file per domain. Each is
registered in `app/api/api.py`.

## Tech Stack

-   **FastAPI** routers and dependency injection
-   **Local, database-backed auth** via the identity aliases in `app.api.deps`
-   **SQLModel + AsyncSession** via `DBDep`
-   **Pydantic** schemas for request/response models

## Route Structure Guidelines

```python
from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem

router = APIRouter(prefix="/your-prefix", tags=["your-tag"])


@router.get("/", response_model=ThingRead)
async def get_thing(
    current_user: CurrentUser,
    session: DBDep,
) -> ThingRead:
    """One sentence on what this returns, then *why* anything non-obvious."""
    thing = await crud_thing.get(session, id=..., raise_404_error=True)
    if thing.owner_id != current_user.id:
        raise_problem(
            status.HTTP_403_FORBIDDEN,
            code="thing.not_yours",
            detail="This item belongs to someone else.",
        )
    return thing
```

`current_user` is a fully loaded `User` row — id, email, roles, everything. There
is no separate "claims" object to consult and no profile living somewhere else:
the access token carries the user id and nothing more, precisely so that a
single primary-key lookup answers the whole identity question.

## Authentication Patterns

Take identity through the aliases in `app/api/deps.py` and nowhere else:

- **`CurrentUser`** — the default. Validates the bearer token, loads the row,
  requires `is_active` and `approval_status == "approved"` (the latter only ever
  differs under `REGISTRATION_MODE=approval`).
- **`CurrentSuperuser`** — additionally requires the platform `admin` role. For
  user management and other install-wide operations only.
- **`AnyUser`** — same as `CurrentUser` but does *not* require `is_active` or an
  approved registration, so a suspended or still-pending account can still read
  or delete its own profile.
- **`QueryTokenUser`** — for SSE endpoints only. `EventSource` cannot send
  headers, so the token arrives as `?token=…`.
- **`AccessClaimsDep`** — claims without a database hit, for the rare case where
  the *session* matters and the user row does not (e.g. sparing the caller's own
  session when signing the others out).

Per-event authorisation is **not** done here. It goes through
`app/logic/permissions.py`:

- `require_event_role(user, session, event_id, minimum=...)` for mutations — 403
- `require_event_visible(user, session, event)` for reads — **404**, so a private
  event cannot be probed by id

Grepping those two names must keep finding every check, so do not inline an
equivalent condition.

Authentication itself — register, login, refresh, logout, password reset, email
verification, session management — lives in `auth.py` under its own `/auth`
prefix. See `docs/AUTH.md`. Keep it there: `GET /users/{user_id}` in `users.py`
is a catch-all, and a literal `/users/<something>` route registered after it is
shadowed silently.

## Best Practices

### Route Organization

- One route file per logical domain/resource
- Use descriptive prefixes and tags — `custom_generate_unique_id` builds the
  operation id as `{tag}-{function_name}`, which becomes the **generated
  frontend client's method name**. Renaming a function here renames a method in
  the Vue app.
- Register the router in `app/api/api.py`

### Errors

- `raise_problem(status, code="domain.reason", detail="A human sentence.")` from
  `app/core/errors.py` for anything the frontend should be able to switch on. The
  code is translated through the frontend's `errorCodes` i18n namespace; a code
  with no entry renders as the raw string on screen.
- A bare `HTTPException` carries no code at all. It survives in older routes;
  prefer `raise_problem` in new ones.

### Transactions

- Routes and CRUD **flush**, they do not commit. `deps.get_db` owns the
  transaction and commits *before* the response is sent, so a client's immediate
  follow-up request cannot race its own write.
- Side effects that must not block the response (mail, notifications) go through
  `BackgroundTasks`. They run after the commit, which is exactly the ordering a
  token-bearing mail needs.

### Response Models

- Declare the model **both** as `response_model=` and as the return annotation
- Use the appropriate status code; `status.HTTP_*` constants, not integers

## Registration

```python
# app/api/api.py
from app.api.routes import auth, users, your_routes

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(your_routes.router)
```

After any change to the OpenAPI surface, regenerate the typed frontend client
with `just generate-client` — never hand-edit `frontend/src/client/`.
