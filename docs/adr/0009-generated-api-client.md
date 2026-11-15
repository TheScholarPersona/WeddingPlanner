# ADR 009: Generated TypeScript client from OpenAPI

- Status: Accepted (15.11.2026)

## Decision
The backend's OpenAPI schema is exported (`make api-types`) and `openapi-typescript` generates `frontend/src/lib/api/schema.d.ts`.

## Consequences
Frontend and backend cannot drift apart silently; a changed response shape breaks the frontend type check.
