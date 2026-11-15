# ADR 006: One React app with separate areas

- Status: Accepted (15.11.2026)

## Decision
One React + TypeScript app with three areas: `/app` (planner), `/portal` (couple), `/admin` (platform). They share the design system, API client and login.

## Consequences
One build and one design system. Permissions in the frontend only hide UI; every action is authorized again on the server.
