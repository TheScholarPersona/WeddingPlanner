# Wedding Planning Platform

A multi-tenant SaaS for wedding planners and their clients. Planners manage weddings, clients,
vendors, tasks, budgets, calendars and documents in one place; couples follow and take part in
their planning through a mobile-first client portal.

> Status: **Sprint 5 – documents, calendar and notifications.** Planners run each wedding's
> tasks, budget, documents (virus-scanned, versioned, shareable with the couple) and
> appointments, see everything in one calendar and subscribe to it from their calendar app.
> Couples use a mobile-first portal for their countdown, tasks, budget, files and appointments.
> Email notifications (assignments, comments, documents, a daily overview) are on by default and
> can be switched off per person. Next: hardening and data protection tools (Sprint 6).

## Stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic |
| Database | PostgreSQL 17 with row-level security |
| Jobs | ARQ on Redis |
| Frontend | React 19, TypeScript, Vite, React Router, TanStack Query, Tailwind CSS 4, shadcn/ui, react-i18next |
| Files / mail / scan | S3-compatible storage (SeaweedFS), Mailpit, ClamAV |
| Tests | Pytest + Testcontainers, Vitest + Testing Library, Playwright |

Architecture decisions are recorded in [`docs/adr/`](docs/adr).

## Quick start

Requirements: Docker with Compose, `make`. For running tests on the host also
[uv](https://docs.astral.sh/uv/) and Node.js 22.

```bash
make setup     # creates .env from .env.example, installs local dependencies
make up        # builds and starts all services
```

| Service | URL |
| --- | --- |
| App (planner `/app`, portal `/portal`) | https://localhost |
| API docs | https://localhost/api/v1/docs |
| Mailpit (captured emails) | http://localhost:8025 |
| S3 storage | http://localhost:8333 |

The first start downloads and builds all images and takes a few minutes. `make help` lists all
commands.

### Virus scanning of uploads

Uploaded documents are scanned with ClamAV before anyone can download them. Locally the scanner
is off by default, so the app starts quickly; uploads are then marked "not scanned". To scan:

1. Set `VIRUS_SCAN=clamav` in `.env`.
2. Start the scanner too: `docker compose --profile scan up -d`

ClamAV downloads its virus signatures on the first start, which takes a few minutes; until then
uploads stay "Checking for viruses…". On Apple Silicon it runs emulated and needs about 3 GB of
memory for Docker. Production refuses to start without scanning.

### Calendar subscriptions

In **Calendar → Subscribe** (planners) or **Calendar → Add to my calendar** (couples) you get a
private link for Apple Calendar, Google Calendar or Outlook. Calendar apps on your own computer
can read `https://localhost` once the certificate is trusted; cloud services like Google
Calendar cannot reach a local pilot, so they only work once the platform is hosted.

### Daily overview email

The worker sends the daily overview at 07:05 in the organization's time zone (`DIGEST_HOUR`).
To see one locally right away:

```bash
docker compose exec worker python -m app.cli send-digests --now
```

### Trust the local HTTPS certificate (optional)

Caddy issues its own certificate for `https://localhost`. Until you trust it, the browser shows a
warning that you can click through. To trust it once:

```bash
make trust-cert
```

Then add the exported `caddy-root.crt` to your system:

- macOS: `sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain caddy-root.crt`
- Windows (PowerShell as administrator): `certutil -addstore -f ROOT caddy-root.crt`
- Linux (Debian/Ubuntu): `sudo cp caddy-root.crt /usr/local/share/ca-certificates/ && sudo update-ca-certificates`

Firefox keeps its own certificate store: Settings → Privacy & Security → Certificates → Import.

### Without `make` (e.g. Windows)

```bash
cp .env.example .env
docker compose up --build -d
docker compose exec api python -m app.cli create-organization --name "Atelier Example" --admin-email admin@example.com
```

### Create the first organization

Organizations are activated manually during the pilot. This creates one and prints the
invitation link for its first admin (the email also arrives in Mailpit):

```bash
make org name="Atelier Example" email=admin@example.com
```

Open the link, choose a name and password, and you are signed in as the organization admin.

## Development

```bash
make test        # backend (real PostgreSQL in a container) + frontend unit tests
make e2e         # Playwright, desktop and phone viewports
make lint        # ruff, eslint, prettier
make typecheck   # mypy (strict), tsc
make api-types   # regenerate the typed API client after backend changes
make migration m="describe change"
```

Run the frontend without Docker with `cd frontend && npm run dev`; it proxies `/api` to
`http://localhost:8000`.

## Security rules every change follows

- Every business table has `organization_id` and a row-level security policy
  (`app.db.rls.enable_tenant_rls`). The app connects as `app_user`, which cannot bypass RLS.
- Authorization is decided on the server; the frontend only hides what a user cannot do.
- Client-facing responses use separate schemas without internal fields.
- Tests and demos use generated data only (`backend/tests/factories.py`). Never commit real
  customer data.
- UI copy is English and lives in `frontend/src/lib/i18n/locales/`; dates and amounts follow
  the organization's locale.

## Repository layout

```text
backend/    FastAPI app, Alembic migrations, tests
frontend/   React app, unit tests, Playwright e2e tests
docker/     Caddy, PostgreSQL init, SeaweedFS
docs/adr/   Architecture decision records
```
