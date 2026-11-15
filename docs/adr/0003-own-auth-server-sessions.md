# ADR 003: Own authentication with server-side sessions in httpOnly cookies

- Status: Accepted (15.11.2026)

## Decision
Authentication is implemented in FastAPI: Argon2id password hashes, server-side sessions referenced by an httpOnly, Secure, SameSite cookie, CSRF token for writes, optional TOTP.

## Consequences
Full control and data residency in the EU, sessions can be revoked instantly, no tokens in browser storage. SSO can be added later.
