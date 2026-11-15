# ADR 001: Modular monolith instead of microservices

- Status: Accepted (15.11.2026)

## Context
A small team builds a multi-tenant SaaS with nine business modules. Operating many services would cost more than it saves at this stage.

## Decision
One FastAPI deployment. Each business module is its own package (`router`, `schemas`, `service`, `repository`, `models`, `policies`). Modules talk to each other only through service interfaces, never through another module's tables.

## Consequences
One build, one deployment, simple transactions. Clear module boundaries keep a later split into services possible.
