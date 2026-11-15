# ADR 005: Local pilot with Docker Compose, cloud-neutral

- Status: Accepted (15.11.2026)

## Decision
The pilot runs locally with Docker Compose: Caddy, API, worker, frontend, PostgreSQL, Redis, S3-compatible storage, Mailpit, ClamAV. Configuration only through environment variables.

S3-compatible storage is SeaweedFS, because MinIO no longer publishes community container images. The application only uses the S3 API, so the provider can be swapped without code changes.

## Consequences
No hosting cost during the pilot. Moving to an EU host needs a production compose file and real secrets, not code changes.
