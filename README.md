# Wedding Planning Platform

A multi-tenant SaaS for wedding planners and their clients. Planners manage weddings, clients,
vendors, tasks, budgets, calendars and documents in one place; couples follow and take part in
their planning through a mobile-first client portal.

> Status: **Sprint 6 – ready for the pilot.** Planners run weddings end to end: clients, tasks,
> budget, documents, appointments and a shared calendar; couples use a mobile-first portal.
> Sprint 6 added two-factor authentication, GDPR tools (exports, erasure, consents, retention),
> support access and a platform admin area, a demo organization, a security review
> ([`docs/security-review.md`](docs/security-review.md)), a load test and an accessibility audit.

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

### Try it with demo data

```bash
make demo
```

This creates "Atelier Lumière (Demo)" with three weddings, budgets, appointments, documents and a
couple's portal login, and prints the sign-in details for an admin, a planner and the couple.
Everything is invented; the example.com addresses receive no email.

### Security and data protection

- **Two-factor authentication:** everyone can turn it on under **Account**. Organization admins
  can require it for their team (**Settings → Security**). Platform admins must use it.
- **Data requests:** on a client's page, organization admins can export everything stored about
  the client (ZIP with data and files) or erase the client for good. Everyone can download their
  own data or delete their account under **Account**.
- **Consents:** couples decide in their portal (**Account → Privacy**) whether their wedding may be
  used as a reference and whether they may be asked for a review; planners see the answers on
  the wedding.
- **Support access:** under **Settings → Support access** an admin lets platform support look in
  read-only for 1 to 14 days; every look appears in the audit log.
- **Platform admin:** `make admin email=you@example.com`, then sign in, turn on two-factor
  authentication and open **Platform admin** in the sidebar (or `/admin`).
- A cleanup job removes expired data every night (see the review document).

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

### Open it on a phone in the same Wi-Fi

```bash
make lan
```

This makes the app answer to your Mac's network name (e.g. `https://my-mac.local`, also printed
with its IP address) and points links in emails and calendar feeds there. The phone has to trust
the local certificate once: AirDrop the exported `caddy-root.crt` to the iPhone, install the
profile under **Settings → Profile Downloaded**, then turn it on under **Settings → General →
About → Certificate Trust Settings**. The command prints these steps too. `make lan-off` switches
back to `https://localhost` only.

Only use this in a Wi-Fi you trust: everyone in it can reach the sign-in page.

### If the app does not open

- **Safari "can't connect to the server"** although everything runs: Safari remembers a failed
  connection. Open https://localhost in a private window (Cmd + Shift + N) or quit Safari once.
- **Check that everything is up:** `docker compose ps` lists every service as "Up";
  `curl -sk https://localhost/api/v1/health` answers `{"status":"ok","database":"ok"}`.
- **Blank page right after an update:** the frontend is still installing or bundling new
  packages; wait a moment and reload with Cmd + Shift + R.
- **Still stuck:** `docker compose logs --tail=40 proxy api frontend` shows what went wrong.

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
make loadtest email=... password=...   # p95 per endpoint, 20 users for 30 s
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
