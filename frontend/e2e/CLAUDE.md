# E2E gotchas

`README.md` covers how to run these. This is the short list of things that
waste an afternoon.

## Run it locally

Users are seeded straight into the DB and the browser is handed a session
instead of signing in, so nothing external is needed. It wants the backend
running with `TESTING=true`; Playwright starts the frontend itself.

```bash
docker compose up db -d                                   # note: no -f
cd backend && TESTING=true ENVIRONMENT=local uv run uvicorn app.main:app --port 8787
cd frontend && pnpm exec playwright test --reporter=list  # list, or it opens a server and blocks
```

Filter noisy Vite output with `| grep -vE "^\[WebServer\]"`.

`frontend/.env` needs `VITE_E2E_AUTH_BYPASS=true`, and the run also has to set
an `e2e_bypass=1` cookie — the fixtures do. Without both, every spec that uses
`adminPage` lands on `/login` instead of the app.

`just e2e-up` publishes the same 5555 and 8787 from Docker. With `just dev-backend`
or `just dev-frontend` still running, Windows splits `localhost` between them
(uvicorn holds 127.0.0.1:8787, Vite ::1:5555, Docker the rest), so one run can reach
both stacks at once. Stop one side first.

## `tests/auth/` is the exception, on purpose

The `auth` project drives `/login`, `/register` and `/forgot-password` for real:
no bypass cookie, no seeded session, an anonymous visitor and the actual
endpoints. It is the only coverage those screens get, since every other spec is
already signed in before its first line.

Two consequences. Those files clear `storageState` (a signed-in visitor is
redirected off `/login` before the test can look at it), and they delete their
own accounts — registering with a password gives an account a `local|…` subject,
which `POST /testing/reset` deliberately does not touch.

## Membership is required for almost everything

Authorisation lives on the event, so a seeded user who is not a member of
anything sees an empty app and cannot even set a selected event. Fixtures put
people into events through the real invitation endpoints:

- `joinEvent(eventId, inviterEmail, inviteeEmail, role)` in `fixtures.ts`
- `addMember(inviterPage, inviteePage, eventId, email, role)` in `helpers/api.ts`

Both take *two* identities on purpose — an invitation is created by an
organiser and redeemed by the invitee. There is deliberately no "add this user"
endpoint to shortcut.

Pass `disposableUserOptions: { joinWorkerEvent: false }` for a user in no event
at all, which is what a genuine first sign-in looks like.

## A project's `use` only arrives if the fixture passes it on

`adminPage`, `memberPage` and `disposablePage` build their own context rather
than taking Playwright's `page`, so they have to hand `contextOptions` to
`browser.newContext()` themselves. A bare `newContext()` silently takes
Playwright's defaults and drops whatever the project asked for — viewport,
device, locale, colour scheme.

This hid for a long time because the default viewport is the same 1280x720
`devices['Desktop Chrome']` sets, so every project agreed with the default by
accident. The `mobile` project is the first that asks for something else, and
without the fix it ran at a desktop viewport and cheerfully reported that the
bottom drawer worked.

`tests/mobile/responsive-dialog.spec.ts` therefore opens with a test that just
asserts the viewport is narrow. If that one fails, ignore the rest of the file
— they are all testing the wrong shell.

## Assertions must survive parallel workers

Every worker seeds its **own** admin, member and event, and they all run
against one database. So a locator that is unique within your test can match
several elements once other workers are doing the same thing.

```ts
// flaky — other workers feature their own events concurrently
await expect(page.locator('[data-featured="true"]')).toContainText(name)
// stable — pin it to this worker's fixture
await expect(
  page.locator('[data-featured="true"]').filter({ hasText: workerEvent.name }),
).toHaveCount(1)
```

Never target `adminUser` / `memberUser` / `workerEvent` with a destructive
action — they are shared by every test that worker runs. Use the `disposable*`
fixtures, which are deleted in teardown.

Wait for what the page is waiting for, not for a fixed window. A `toPass` loop that
re-opens a page and gives each visit 2 s fails whenever the stack is busy, and each
retry pays for another page load. The backend commits before it responds (`get_db`),
so a write is visible to the next request: open the page once, `waitForResponse` on
the request that carries the data, then assert with the default timeout.

## On a full set of local workers

With the default worker count (half your CPU threads, 12 when this was measured) on
the Docker stack, everything goes through one Vite dev server and tests take about
five times as long as they do alone. Before blaming a timeout, rerun it with
`--workers=3`.

`actionTimeout` (5 s) is also the default for `page.waitForResponse`, while `goto` has
no limit of its own below the test's 30 s. A `waitForResponse` started before a `goto`
has to cover the whole page load, so give it its own `timeout`.

Discover lists the first 100 public events by start date, and every worker's
`workerEvent` is public and starts tomorrow. They stay until the next run's
`/testing/reset` (an event goes with its owner; `--no-deps` skips that reset). One run
can start more than 100 workers, because workers restart after a failure and between
projects and `--repeat-each=N` gives every repeat its own. A test that looks for its own
event in Discover has to create it starting today.

## Asserting a refusal

`api()` throws on any non-2xx, which loses the status. Use `apiStatus()` when
the test cares *which* refusal it got — 403 ("not allowed here") and 404 ("you
cannot even see this") mean different things in this codebase and are worth
distinguishing.

## Don't touch the shared fixtures, including indirectly

`adminUser`, `memberUser` and `workerEvent` are shared by every test a worker
runs, so anything that mutates them poisons whatever comes later — and the
failure surfaces somewhere else entirely, which makes it look like flakiness.

The subtle case is mutation through the UI. Accepting an invitation on
`/invite/:token` calls `setSelectedEvent()`, so clicking that button as
`memberPage` repoints the shared member at a throwaway event. When the test
tears that event down, the FK nulls the selection, and every later test that
needs a selected event gets bounced to the picker instead of the page it was
testing.

Any test that *acts* as an invitee — accepting, joining, switching events —
should use `disposablePage` / `disposableUser`, which are deleted in teardown.
Read-only checks (viewing an invite, asserting a refusal) are fine as
`memberPage`.

Before blaming flakiness, reproduce serially — that is how CI runs each shard:

```bash
pnpm exec playwright test --workers=1
```

If it fails there, it is not flaky. It is an ordering bug, and the cause is
usually shared state.
