# ADR 007: ARQ on Redis for background jobs

- Status: Accepted (15.11.2026)

## Decision
Emails, virus scans, reminders, exports and cleanup run as ARQ jobs on Redis.

## Consequences
Async-native and much lighter than Celery. Requests never send email or scan files themselves.
