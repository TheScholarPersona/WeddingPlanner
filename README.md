# Wedding Planning Platform

A multi-tenant SaaS for wedding planners and their clients. Planners manage weddings, clients,
vendors, tasks, budgets, calendars and documents in one place; couples follow and take part in
their planning through a mobile-first client portal.

> Status: **Sprint 1 – authentication and organizations.** Sign-in, invitations, password
> reset, team management, organization settings and the audit log work end to end. Weddings,
> clients and tasks follow in Sprint 2.

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

Run `make trust-cert` once so your browser trusts the local HTTPS certificate.
`make help` lists all commands.

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
