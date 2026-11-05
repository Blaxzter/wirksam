---
title: Run WirkSam yourself
lede: WirkSam is open source under the MIT licence, and you can run it on your own server with Docker Compose. You decide who may sign up, where files live and which pages are public.
related: feature/members, feature/notifications, feature/teams
---

The source code is on [GitHub](https://github.com/Blaxzter/wirksam). Your server gets the same app as [wirksam.app](https://wirksam.app), in English and German.

This page is for people who look after a server, so it uses technical words and setting names.

## What you need

- a server with Docker Engine and Docker Compose
- a domain whose DNS points at the server, most easily with a wildcard record
- ports 80 and 443 free for Traefik, which also fetches the HTTPS certificates from Let's Encrypt
- an SMTP account for email

Compose starts PostgreSQL, the backend, the frontend, Adminer and Garage as the file store. Traefik runs in front as its own stack.

The app runs at `DOMAIN`, the backend at `API_DOMAIN`, the file store at `files.<DOMAIN>` and Adminer at `adminer.<DOMAIN>`. Keep `API_DOMAIN` under the same domain, such as `api.example.org` next to `example.org`. The sign-in cookie uses `SameSite=lax`. On an unrelated domain, signing in won't survive a page reload.

## Start it with Docker Compose

Get the code and create the settings file:

```bash
git clone \
  https://github.com/Blaxzter/wirksam.git
cd wirksam
cp .env.example .env
```

In `.env`, set at least:

- `ENVIRONMENT=production`, `DOMAIN`, `API_DOMAIN` and `FRONTEND_HOST`, the public address of the app.
- `PROJECT_NAME` and `STACK_NAME`. The project name is the sender name on emails.
- `SECRET_KEY` with at least 32 bytes. With `changethis` or anything shorter, the backend won't start outside `ENVIRONMENT=local`.
- `POSTGRES_PASSWORD`. `.env.example` has `admin`, and nothing stops the stack from starting with it. Adminer is public, so use a strong password.

Start Traefik first. It creates the `traefik-net` network the stack needs. It expects `DOMAIN` and `EMAIL` in the shell for the certificates, and `USERNAME` and `HASHED_PASSWORD` for its dashboard:

```bash
docker compose \
  -f docker-compose.traefik.yml up -d
```

Then the app, without the override file for development:

```bash
docker compose \
  -f docker-compose.yml up -d --build
```

Before the backend starts, the `prestart` container runs the database migrations. The frontend image has `API_DOMAIN` built in, so rebuild it if that address changes. There's more in [docs/deployment.md](https://github.com/Blaxzter/wirksam/blob/main/docs/deployment.md).

## The first admin account

Without `SUPERADMIN_EMAILS`, a fresh install has no administrator. The setting is a JSON list:

```bash
SUPERADMIN_EMAILS=["you@example.org"]
```

Anyone who registers or signs in with one of these addresses gets the platform admin role. That role manages accounts under "User Management" and can open any event except demos.

These addresses get in under every registration mode and are approved straight away. So set them before you restrict signup. If you remove an address later, the account keeps its role.

## Who may register

`REGISTRATION_MODE` has three values:

- `open` (the default): anyone can sign up and use the account straight away. An account alone gives no access to any event.
- `approval`: anyone can sign up. The account waits until a platform admin approves it under "User Management".
- `invite`: only people with a valid event invitation can sign up, meaning the invitation link or an open invitation to their own address.

`REGISTRATION_ALLOWED_DOMAINS` limits signup in any mode to certain email domains, comma-separated, such as `gemeinde.de,example.org`. Empty means any domain.

`REGISTRATION_INVITE_BYPASS` is `true` by default. Anyone with a valid invitation then skips the approval queue and the domain list. With `false`, both apply to invited people too.

You can also put Cloudflare Turnstile in front of the form, with `TURNSTILE_SITE_KEY` and `TURNSTILE_SECRET_KEY`. The domain doesn't have to be on Cloudflare. Empty switches the check off, which is the default. If it's on and Cloudflare can't be reached, registration is refused.

## Where files live

People upload profile pictures, venue plan pictures and documents for team requests. `STORAGE_BACKEND` has two values:

- `s3` is what `.env.example` sets. With `COMPOSE_PROFILES=s3`, the bundled Garage container runs alongside. It creates the bucket and key on its first start. For a real install, generate your own keys (the commands are in `.env.example`), because the backend won't start on the example key. You also need a DNS record for `files.<DOMAIN>`.
- `postgres` puts the files in the database, with nothing else to run. This also applies if the variable is missing.

Instead of Garage you can use Cloudflare R2 or another S3-compatible store. Remove `COMPOSE_PROFILES` and set `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET` and the key pair.

You can move from `postgres` to `s3` later. Change the settings and move the old files with `docker compose exec backend python -m app.scripts.move_files_to_s3`. There's no script for the way back. Details are in [docs/STORAGE.md](https://github.com/Blaxzter/wirksam/blob/main/docs/STORAGE.md).

## Time zone, demo and public pages

- `EVENT_TIMEZONE` (default `Europe/Berlin`) is an IANA name and the time zone a new event starts with. After that, each event has its own, which organisers set on the event. Shift times carry no zone, so the event's zone decides when a shift has started or ended, and so when hours and vouchers count. Changing the setting later doesn't move existing events. With an unknown name, the backend won't start.
- `SANDBOX_ENABLED` (default `true`) controls the "Try a demo event" button. It creates a throwaway account with an example event, without signing up. With `false`, the button goes away and the backend refuses new demos. `SANDBOX_TTL_MINUTES` (60) and `SANDBOX_MAX_ACTIVE` (25) limit how long they last and how many run at once.
- `LANDING_ENABLED` (default `true`): with `false`, `/` leads to sign-in or, if you're signed in, into the app. The content pages like this one go too. Privacy, terms, impressum and the changelog stay.
- `SEARCH_INDEXING` (default `true`): with `false`, `robots.txt` tells every crawler to stay away, and `sitemap.xml` and `llms.txt` are removed.
- `LEGAL_NAME`, `LEGAL_ADDRESS`, `LEGAL_CITY`, `LEGAL_EMAIL` and `LEGAL_PHONE` put your details on the impressum and privacy pages.

## Email and reminders

For email, set `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` and `EMAILS_FROM_EMAIL`, plus `SMTP_PORT` (default 587) and `SMTP_TLS` if you need them.

Without SMTP, links for verifying an address, resetting a password and invitations only go to the backend's log, and notifications by email are dropped. Signing in still works without a verified address.

The backend sends reminders itself, so you don't need a cron job for them. Browser push needs the `VAPID_*` keys, and Telegram a bot with `TELEGRAM_BOT_TOKEN` and `TELEGRAM_BOT_USERNAME`. Both are optional.

## Behind Cloudflare

With the Cloudflare proxy on, every request comes from a Cloudflare server. Without changes, the backend counts every rate limit against a handful of Cloudflare addresses and locks strangers out together. Cloudflare's IP ranges have to be trusted in two places:

1. In Traefik: `docker-compose.traefik.yml` already includes them. A deploy doesn't restart Traefik, so after a change you copy the file to Traefik's folder and restart it there.
2. In the backend: `FORWARDED_ALLOW_IPS` in `.env`, after the default private ranges. Without Cloudflare, leave the variable out.

When Cloudflare changes the list, update both. If Cloudflare answers port 80 itself ("Always Use HTTPS"), Let's Encrypt's HTTP challenge fails. In that case, define a DNS-challenge resolver in Traefik and name it in `TRAEFIK_CERT_RESOLVER`.

## Frequently asked questions

### Do I have to run WirkSam myself?

No. [wirksam.app](https://wirksam.app) is free and needs no server of your own.

### How do I update?

Get the new code with `git pull` and run the same command as at the start, `up -d --build`. The `prestart` container runs the migrations before the backend starts.

### What do I need to back up?

The database, which is in the `app-db-data` volume. With Garage, also the `garage-meta` and `garage-data` volumes, because the files aren't in a database dump then.

### What does the MIT licence allow?

You may use, change and pass on WirkSam, also commercially, as long as the licence notice stays with it. It comes without any warranty. The wording is in the [LICENSE](https://github.com/Blaxzter/wirksam/blob/main/LICENSE) file.
