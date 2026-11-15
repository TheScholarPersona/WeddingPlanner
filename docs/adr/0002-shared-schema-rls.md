# ADR 002: Shared schema with `organization_id` and PostgreSQL row-level security

- Status: Accepted (15.11.2026)

## Context
Tenants must be strictly separated. Schema-per-tenant or database-per-tenant multiplies migration and operating effort.

## Decision
All tenants share one schema. Every business table has `organization_id` and a `tenant_isolation` RLS policy (`ENABLE` + `FORCE`). The application connects as `app_user` without `BYPASSRLS`; the tenant is set per transaction with `set_config('app.org_id', …, true)`. Migrations run as the schema owner.

## Consequences
Simple migrations, scales to thousands of organizations. A missing check in application code is still caught by the database. Every new table must call `enable_tenant_rls()` in its migration and get a cross-tenant test.
