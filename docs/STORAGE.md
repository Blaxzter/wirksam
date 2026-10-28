# Uploaded files

wirksam keeps three kinds of uploaded files: avatars (WebP, up to 256×256),
venue plan and template pictures (WebP, the largest), and documents a requester
attaches to a pending team request (PDF or WebP, up to 5 MB, deleted when the
request is decided). Image processing (Pillow, WebP re-encoding, EXIF
stripping) happens before any of them is stored and is the same for every
backend.

## Where the bytes live

`STORAGE_BACKEND` picks one of two backends (`backend/app/core/storage.py`):

| Backend | Bytes in | Use it for |
| --- | --- | --- |
| `s3` (what `.env.example` sets) | a private bucket of any S3-compatible store: the bundled Garage container, Cloudflare R2, MinIO | the normal case; keeps the database and its backups small |
| `postgres` | the `stored_objects` table, written in the request's own transaction | an install that wants nothing but a database |

A new install that starts from `.env.example` gets Garage: `COMPOSE_PROFILES=s3`
runs the container and `STORAGE_BACKEND=s3` points the backend at it. An `.env`
without those lines, from before this existed, stays on `postgres`, which is
also the backend's own default; [switching](#switching-an-existing-install-to-s3)
is a separate step.

The rows that own a file (`user_avatars`, `venue_plan_images`,
`venue_template_images`, `event_team_documents`) hold only a `storage_key`
such as `team-documents/3f2a…`, never the bytes. Every read and write goes
through `get_storage()`; nothing else touches `stored_objects` or the bucket.
Keys are never reused: a replaced file gets a new key.

## How files are served

The bucket is never public. Every file is asked for at the same API endpoint
as before, behind the same access check (avatars public by unguessable user
id, plan and template pictures to event members and the owner, team documents
to the team's managers and the requester only). What happens after the check
(`backend/app/api/files.py`):

| | `postgres` | `s3` |
| --- | --- | --- |
| Avatars, plan and template pictures | streamed by the API | `302` to a signed link into the bucket; the bytes never pass the API |
| Team documents | streamed by the API | streamed by the API, never a link |

A signed link works for two hours, for whoever holds it, and nothing else in
the bucket can be read without one. Signing is a local computation, so a
redirect costs the API one database lookup and no request to the store. The
redirect is cached for one hour and carries no ETag, so a browser replays it
while the link still works and lands on the same link, which it has cached as
well; the bucket answers with the image's own `Cache-Control`, passed along in
the signature. A revalidation (`If-None-Match` on the API URL) is still
answered with 304 from the row's etag without touching the store.

Team documents (a police certificate, say) are not handed out as links, since
a link outlives the access check that granted it. They are rare and small, so
streaming them costs little: the API passes a bucket object on in 64 KiB
pieces and never holds it whole. A file the copy script has not moved yet is
streamed too.

The frontend loads plan and template pictures with `fetch` (they need the
bearer token), so after the redirect the bucket must allow a cross-origin
`GET`. `python -m app.scripts.setup_bucket`, which `prestart.sh` runs on every
deploy, sets that CORS rule: any origin, `GET` and `HEAD`. The origin is `*`
because a browser sends `Origin: null` after a cross-origin redirect, and the
rule grants nothing a signed link does not. If the key may not change bucket
settings, the script only prints a warning; set the rule by hand then (R2:
the bucket's *Settings → CORS policy*):

```json
[{ "AllowedOrigins": ["*"], "AllowedMethods": ["GET", "HEAD"], "MaxAgeSeconds": 3600 }]
```

## How files are deleted

No code deletes a file directly. Each of the four tables has an
`AFTER DELETE OR UPDATE OF storage_key` trigger (migration `20261027_0001`)
that, in the deleting transaction,

1. deletes the `stored_objects` row of the old key, so with the Postgres
   backend the bytes go at commit, and
2. queues the key in `storage_deletions`.

That covers every way a row goes: an ORM delete, a bulk `DELETE`, a replaced
upload, and an `ON DELETE CASCADE` from a user, an event, a team member or the
[sandbox purge](SANDBOX.md#teardown-and-why-the-order-is-what-it-is), none of
which have to know about files. A transaction that rolls back queues nothing.

`backend/app/logic/storage_gc.py` drains the queue: it deletes the objects in
the bucket (`DeleteObjects`, up to 1000 keys per call) and then the queue rows.
It runs in every backend worker, every `STORAGE_GC_INTERVAL_SECONDS` (60), and
right after any commit whose request deleted or replaced a file
(`drain_after_commit`), so a decided team request's document leaves the bucket
within moments, not a minute later. Workers share the queue with
`FOR UPDATE SKIP LOCKED`; a failed delete leaves the rows queued for the next
run.

One gap is left: an upload written to the bucket whose request then fails
before its commit leaves an object no row points at. `--sweep-orphans` (below)
removes those.

## Settings

| Variable | Default | Meaning |
| --- | --- | --- |
| `COMPOSE_PROFILES` | – | `s3` runs the Garage container; leave it out with R2 or `postgres` |
| `STORAGE_BACKEND` | `postgres` | `postgres` or `s3` |
| `S3_ENDPOINT_URL` | the Garage container | the store's endpoint. Unset, the stack uses `http://garage:3900` and a backend on the host `http://localhost:3900`; AWS itself needs `https://s3.<region>.amazonaws.com` |
| `S3_REGION` | `auto` | `auto` for R2, `garage` for the bundled Garage |
| `S3_BUCKET` | – | required with `s3`; the backend refuses to start without it |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | – | a key with read, write and delete on that bucket only. Outside `ENVIRONMENT=local` the backend refuses to start on the key `.env.example` ships with |
| `S3_PUBLIC_ENDPOINT_URL` | see meaning | the store as the browser reaches it; links are signed for this host. Unset, the stack uses `https://files.<DOMAIN>` for Garage and `S3_ENDPOINT_URL` for any other store |
| `STORAGE_GC_INTERVAL_SECONDS` | `60` | how often the deletion queue is worked without a nudge |

The client uses path-style addressing and sends checksums only where S3
requires them, which every one of the stores above accepts.

### Cloudflare R2 (wirksam.app)

Create a bucket and an R2 API token with *Object Read & Write* on it, remove
`COMPOSE_PROFILES=s3` and `GARAGE_RPC_SECRET`, then:

```bash
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
S3_REGION=auto
S3_BUCKET=wirksam
S3_ACCESS_KEY_ID=<token access key id>
S3_SECRET_ACCESS_KEY=<token secret>
```

Leave public access and the `r2.dev` URL off, and leave
`S3_PUBLIC_ENDPOINT_URL` empty: R2 signs links only for its S3 endpoint, not
for a custom domain, and that endpoint is reachable from browsers anyway. Add
the CORS rule above unless the token may set it.

### Garage (the default, self-hosted)

`docker-compose.yml` has a single-node Garage behind the `s3` profile, which
`.env.example` turns on. On its first start it creates `S3_BUCKET` and the key
pair from `.env`, and `prestart` sets the CORS rule, so there is nothing to set
up by hand. `.env.example` carries throwaway values that only local
development may use; for a real install generate your own:

```bash
echo "S3_ACCESS_KEY_ID=GK$(openssl rand -hex 12)"
echo "S3_SECRET_ACCESS_KEY=$(openssl rand -hex 32)"
echo "GARAGE_RPC_SECRET=$(openssl rand -hex 32)"
```

and point a DNS record for `files.<DOMAIN>` at the server. Traefik routes it
to Garage's S3 port and passes the `Host` header on unchanged, which the link's
signature covers; a different proxy must do the same and must not rewrite the
path. Leave `S3_ENDPOINT_URL` and `S3_PUBLIC_ENDPOINT_URL` empty: inside the
stack they default to `http://garage:3900` and `https://files.<DOMAIN>`.

The files live in the `garage-meta` and `garage-data` volumes, not in the
database dump; back them up together with it.

`just dev local` starts the container next to Postgres and sets the CORS rule
whenever `.env` says `STORAGE_BACKEND=s3`; the backend on the host reaches it
at `http://localhost:3900` (`GARAGE_PORT` moves the host port if 3900 is taken;
set `S3_ENDPOINT_URL` to match). The Docker dev stack reaches it as
`garage:3900` and signs links for `localhost:3900`.

## Switching an existing install to S3

1. Set the `S3_*` settings and `STORAGE_BACKEND=s3` (for Garage also
   `COMPOSE_PROFILES=s3`, the generated keys and the `files.<DOMAIN>` record),
   and restart the stack.
   New uploads go to the bucket. Files uploaded before are still read from
   `stored_objects`: `S3Storage` falls back to it for a key the bucket does not
   have, so nothing goes missing in between.
2. Move the old files:

   ```bash
   docker compose exec backend python -m app.scripts.move_files_to_s3
   ```

   It uploads `stored_objects` in batches of 50 and deletes each batch from
   Postgres in the same transaction once the upload succeeded. Stop it and run
   it again at any time; it picks up where it left off, and a second run on a
   finished install moves nothing.
3. Optionally, a day later, `… move_files_to_s3 --sweep-orphans` deletes
   bucket objects no row refers to that are older than a day.

Going back to `postgres` needs the files copied back into `stored_objects`
first; there is no script for that direction. The migration's downgrade
refuses to run while any file is only in a bucket.

## Tests

`TEST_STORAGE_BACKEND=s3` runs the whole backend suite against `S3Storage` on
an in-process moto bucket (`backend/tests/fixtures/storage.py`); CI runs it
both ways. The Playwright suite in CI runs with `STORAGE_BACKEND=s3` against
the Garage container.
