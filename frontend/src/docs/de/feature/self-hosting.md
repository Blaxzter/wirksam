---
title: WirkSam selbst betreiben
lede: WirkSam ist Open Source unter MIT-Lizenz und läuft mit Docker Compose auf deinem eigenen Server. Du bestimmst, wer sich registrieren darf, wo Dateien liegen und welche Seiten öffentlich sind.
points: Open Source unter MIT-Lizenz | Läuft mit Docker Compose auf deinem Server | Du legst fest, wer sich registrieren darf
related: feature/members, feature/notifications, feature/teams
---

Der Quellcode liegt auf [GitHub](https://github.com/Blaxzter/wirksam). Dein Server bekommt dieselbe App wie [wirksam.app](https://wirksam.app), auf Deutsch und Englisch.

Diese Seite ist für alle, die einen Server betreuen. Deshalb stehen hier auch technische Begriffe und Einstellungen.

## Was du brauchst

- einen Server mit Docker Engine und Docker Compose
- eine Domain, deren DNS auf den Server zeigt, am einfachsten mit einem Wildcard-Eintrag
- freie Ports 80 und 443 für Traefik, das auch die HTTPS-Zertifikate von Let's Encrypt holt
- ein SMTP-Konto für E-Mails

Compose startet PostgreSQL, Backend, Frontend, Adminer und Garage als Dateispeicher. Traefik läuft als eigener Stack davor.

Die App läuft unter `DOMAIN`, das Backend unter `API_DOMAIN`, der Dateispeicher unter `files.<DOMAIN>` und Adminer unter `adminer.<DOMAIN>`.

> Leg `API_DOMAIN` unter dieselbe Domain wie die App, zum Beispiel `api.example.org` neben `example.org`. Auf einer fremden Domain übersteht die Anmeldung kein Neuladen.

## Mit Docker Compose starten

Hol den Code und leg die Einstellungen an:

```bash
git clone \
  https://github.com/Blaxzter/wirksam.git
cd wirksam
cp .env.example .env
```

In `.env` setzt du mindestens:

- `ENVIRONMENT=production`, `DOMAIN`, `API_DOMAIN` und `FRONTEND_HOST`, die öffentliche Adresse der App.
- `PROJECT_NAME` und `STACK_NAME`. Der Projektname erscheint als Absender in E-Mails.
- `SECRET_KEY` mit mindestens 32 Bytes. Mit `changethis` oder einem kürzeren Wert startet das Backend außerhalb von `ENVIRONMENT=local` nicht.
- `POSTGRES_PASSWORD` mit einem starken Passwort, denn Adminer ist öffentlich erreichbar. Mit dem `admin` aus `.env.example` würde der Stack trotzdem starten.

Starte zuerst Traefik. Es legt das Netzwerk `traefik-net` an, das der Stack braucht. In der Shell erwartet es `DOMAIN` und `EMAIL` für die Zertifikate sowie `USERNAME` und `HASHED_PASSWORD` für sein Dashboard:

```bash
docker compose \
  -f docker-compose.traefik.yml up -d
```

Dann die App, ohne die Override-Datei für die Entwicklung:

```bash
docker compose \
  -f docker-compose.yml up -d --build
```

Vor dem Backend läuft der Container `prestart` und spielt die Datenbank-Migrationen ein. Mehr dazu steht in [docs/deployment.md](https://github.com/Blaxzter/wirksam/blob/main/docs/deployment.md).

## Das erste Admin-Konto

Ohne `SUPERADMIN_EMAILS` hat eine frische Installation keinen Admin. Die Einstellung ist eine JSON-Liste:

```bash
SUPERADMIN_EMAILS=["du@example.org"]
```

Wer sich mit einer dieser Adressen registriert oder anmeldet, bekommt die Rolle Plattform-Admin. Diese Rolle verwaltet Konten unter „Benutzerverwaltung“ und darf in jede Veranstaltung außer in Demos. Streichst du später eine Adresse, behält das Konto seine Rolle.

> Die Adressen aus `SUPERADMIN_EMAILS` kommen in jedem Registrierungsmodus rein und sind sofort freigegeben. Setz sie also, bevor du die Registrierung einschränkst.

## Wer sich registrieren darf

`REGISTRATION_MODE` hat drei Werte:

- `open` (Standard): Alle können sich registrieren und das Konto sofort nutzen. Ein Konto allein gibt noch keinen Zugriff auf eine Veranstaltung.
- `approval`: Alle können sich registrieren. Das Konto wartet, bis ein Plattform-Admin es unter „Benutzerverwaltung“ freigibt.
- `invite`: Nur wer eine gültige Einladung zu einer Veranstaltung hat, kann sich registrieren. Gemeint ist der Einladungslink oder eine offene Einladung an die eigene Adresse.

`REGISTRATION_ALLOWED_DOMAINS` beschränkt die Registrierung in jedem Modus auf bestimmte E-Mail-Domains. Du trennst sie mit Komma, zum Beispiel `gemeinde.de,example.org`. Leer heißt alle Domains.

## Wo Dateien liegen

Hochgeladen werden Profilbilder, Bilder für Lagepläne und Dokumente zu Team-Anfragen. `STORAGE_BACKEND` hat zwei Werte:

- `s3` steht in `.env.example`. Mit `COMPOSE_PROFILES=s3` läuft dazu der mitgelieferte Garage-Container. Er legt Bucket und Schlüssel beim ersten Start selbst an, und du brauchst einen DNS-Eintrag für `files.<DOMAIN>`.
- `postgres` legt die Dateien in die Datenbank, und es muss nichts weiter laufen. Das gilt auch, wenn die Variable fehlt.

Mit dem Beispielschlüssel startet das Backend nicht. Für den echten Betrieb erzeugst du also eigene Schlüssel, die Befehle dafür stehen in `.env.example`.

## E-Mail und Erinnerungen

Für E-Mails setzt du `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` und `EMAILS_FROM_EMAIL`. Bei Bedarf kommen `SMTP_PORT` (Standard 587) und `SMTP_TLS` dazu.

Ohne SMTP landen Links zur Bestätigung, zum Zurücksetzen des Passworts und aus Einladungen nur im Log des Backends. Benachrichtigungen per E-Mail fallen dann weg. Anmelden geht auch ohne bestätigte Adresse.

Erinnerungen verschickt das Backend selbst, einen Cron-Job brauchst du dafür nicht. Browser-Push braucht die `VAPID_*`-Schlüssel, Telegram einen Bot mit `TELEGRAM_BOT_TOKEN` und `TELEGRAM_BOT_USERNAME`. Beides ist freiwillig.

## Häufige Fragen

### Muss ich WirkSam selbst betreiben?

Nein. [wirksam.app](https://wirksam.app) ist kostenlos und braucht keinen eigenen Server.

### Was muss ich bei der Adresse des Backends beachten?

Das Anmelde-Cookie nutzt `SameSite=lax`, deshalb muss `API_DOMAIN` unter derselben Domain liegen wie die App. Außerdem enthält das Frontend-Image `API_DOMAIN` fest. Ändert sich die Adresse, baust du das Image neu.

### Gelten Freigabe und Domain-Liste auch für Eingeladene?

Standardmäßig nicht. `REGISTRATION_INVITE_BYPASS` steht auf `true`, dann überspringt eine gültige Einladung die Freigabe und die Domain-Liste. Mit `false` gelten beide auch für Eingeladene.

### Kann ich Cloudflare Turnstile vor die Registrierung schalten?

Ja, mit `TURNSTILE_SITE_KEY` und `TURNSTILE_SECRET_KEY`. Die Domain muss dafür nicht bei Cloudflare liegen. Bleiben die Werte leer, ist die Prüfung aus, das ist der Standard.

Ist die Prüfung an und Cloudflare nicht erreichbar, wird die Registrierung abgelehnt.

### Kann ich statt Garage einen anderen S3-Speicher nehmen?

Ja, zum Beispiel Cloudflare R2 oder einen anderen S3-kompatiblen Speicher. Dann entfernst du `COMPOSE_PROFILES` und setzt `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET` und das Schlüsselpaar.

### Kann ich später von Postgres zu S3 wechseln?

Ja. Stell die Einstellungen um und verschieb die alten Dateien mit `docker compose exec backend python -m app.scripts.move_files_to_s3`.

Für den Weg zurück gibt es kein Skript. Details stehen in [docs/STORAGE.md](https://github.com/Blaxzter/wirksam/blob/main/docs/STORAGE.md).

### Welche Zeitzone gilt für Veranstaltungen?

Jede Veranstaltung hat ihre eigene, die Organisator:innen an der Veranstaltung einstellen. Eine neue Veranstaltung startet mit `EVENT_TIMEZONE`, einem IANA-Namen (Standard `Europe/Berlin`).

Schichtzeiten haben keine Zeitzone. Deshalb entscheidet die Zone der Veranstaltung, wann eine Schicht begonnen hat oder vorbei ist. Davon hängt auch ab, wann Stunden und Marken zählen.

Änderst du `EVENT_TIMEZONE` später, bleiben bestehende Veranstaltungen, wie sie sind. Mit einem unbekannten Namen startet das Backend nicht.

### Wie passe ich die Demo und die öffentlichen Seiten an?

- `SANDBOX_ENABLED` (Standard `true`) steuert den Knopf „Demo-Veranstaltung ansehen“. Er legt ohne Anmeldung ein Wegwerf-Konto mit einer Beispielveranstaltung an. Mit `false` verschwindet der Knopf, und das Backend lehnt neue Demos ab. `SANDBOX_TTL_MINUTES` (60) und `SANDBOX_MAX_ACTIVE` (25) begrenzen Dauer und Anzahl.
- `LANDING_ENABLED` (Standard `true`): Mit `false` führt `/` zur Anmeldung oder, wenn du angemeldet bist, in die App. Die Inhaltsseiten wie diese hier entfallen mit. Datenschutz, Nutzungsbedingungen, Impressum und Changelog bleiben.
- `SEARCH_INDEXING` (Standard `true`): Mit `false` verbietet `robots.txt` allen Crawlern den Zugriff, und `sitemap.xml` und `llms.txt` entfallen.
- `LEGAL_NAME`, `LEGAL_ADDRESS`, `LEGAL_CITY`, `LEGAL_EMAIL` und `LEGAL_PHONE` tragen deine Angaben in Impressum und Datenschutz ein.

### Was muss ich hinter Cloudflare beachten?

Mit eingeschaltetem Cloudflare-Proxy kommt jede Anfrage von einem Cloudflare-Server. Ohne Anpassung rechnet das Backend alle Rate-Limits auf wenige Cloudflare-Adressen an und sperrt so Fremde gemeinsam aus. Die IP-Bereiche von Cloudflare müssen deshalb an zwei Stellen als vertrauenswürdig stehen:

1. In Traefik: `docker-compose.traefik.yml` enthält sie schon. Ein Deploy startet Traefik aber nicht neu. Nach einer Änderung kopierst du die Datei also in den Ordner von Traefik und startest es dort neu.
2. Im Backend: `FORWARDED_ALLOW_IPS` in `.env`, hinter den privaten Standardbereichen. Ohne Cloudflare lässt du die Variable weg.

Ändert Cloudflare die Liste, aktualisierst du beide. Antwortet Cloudflare selbst auf Port 80 („Always Use HTTPS“), scheitert die HTTP-Challenge von Let's Encrypt. Dann definierst du in Traefik einen DNS-Challenge-Resolver und trägst ihn in `TRAEFIK_CERT_RESOLVER` ein.

### Wie spiele ich ein Update ein?

Hol den neuen Code mit `git pull` und führ denselben Befehl wie beim Start aus, also `up -d --build`. Der Container `prestart` spielt die Migrationen ein, bevor das Backend startet.

### Was muss ich sichern?

Die Datenbank, sie liegt im Volume `app-db-data`. Mit Garage außerdem die Volumes `garage-meta` und `garage-data`, denn die Dateien stecken dann nicht im Datenbank-Dump.

### Was erlaubt die MIT-Lizenz?

Du darfst WirkSam nutzen, ändern und weitergeben, auch gewerblich, solange der Lizenzhinweis dabei bleibt. Eine Gewährleistung gibt es nicht. Den Wortlaut findest du in der Datei [LICENSE](https://github.com/Blaxzter/wirksam/blob/main/LICENSE).
