# Security and privacy review (Sprint 6, before the pilot)

- Date: 16.11.2026
- Scope: everything in `main` plus Sprint 6, running as the local pilot (Docker Compose).
- Method: code walk-through along the requirements below, automated tests for each control,
  dependency audits, an accessibility audit and a load test.

## Requirements and how they are met

| Requirement | Implementation | Verified by |
| --- | --- | --- |
| Strict tenant separation | Shared schema with PostgreSQL row-level security on every business table; the app connects as `app_user` (no `BYPASSRLS`); tenant context per transaction (`set_config(..., true)`). Couples get additional restrictive policies. | `test_rls.py` (incl. "every table with `organization_id` has RLS and a policy"), `test_authorization_matrix.py`, SQL-level client tests |
| Role-based permissions | Org roles and per-wedding roles as permission sets in code; every `/orgs/...` route declares a permission. | `test_route_protection.py` fails for any unprotected route |
| Server-side authorization | All checks in FastAPI dependencies plus RLS underneath; the UI only hides. | Matrix tests call the API directly |
| Secure passwords | Argon2id, 12+ characters, lockout after 10 failures, rate limits, reset links 60 min, sessions revoked on reset. | `test_auth.py` |
| Two-factor authentication | TOTP (RFC 6238) with encrypted secret, one-time recovery codes (hashed), replay protection, 5 wrong codes end the attempt; organizations can require it; platform admins must use it. | `test_two_factor.py` |
| Privacy by default | Emails contain no comment text or amounts; calendar feeds carry no notes or amounts; fonts are bundled (no request to Google); every notification can be switched off; consents default to "not decided". | `test_notifications.py`, `test_calendar.py` |
| Audit logging | Append-only `audit_log` (no UPDATE/DELETE for the app role); security events, sharing, exports, erasure, support access and platform admin actions are recorded in the affected organization. | Tests assert audit entries per feature |
| No real customer data in tests | Generated data only; demo data invented, `example.com` addresses. | Review of `tests/`, `app/demo.py` |

## GDPR tools added in this sprint

- **Access and portability (Art. 15/20):** client export as ZIP (`data.json` and files) for
  organization admins; personal export for every user.
- **Erasure (Art. 17):** client erasure deletes the client, weddings, files and couple access;
  account deletion anonymizes the login and removes all memberships.
- **Storage limitation (Art. 5):** daily cleanup of expired sessions, reset links, stale
  invitations, revoked calendar links, old support grants and digest logs; couple access ends
  automatically after the archive period the organization chose.
- **Consent:** couples decide on optional uses (portfolio, review request) and can change their
  answer at any time; decisions are audited and visible to the planner.

## Findings fixed during the review

| # | Finding | Severity | Fix |
| --- | --- | --- | --- |
| 1 | Fonts were loaded from Google Fonts, sending visitors' IP addresses to Google (see LG München I, 3 O 17493/20). | High (privacy) | Fonts bundled with the app (`@fontsource`). |
| 2 | An authenticator code could be reused within its 30-second window. | Medium | Last accepted time step stored; codes work once. |
| 3 | Accepting an invitation signed existing accounts in without their second factor. | High | Invitation acceptance now ends in the 2FA step like a normal sign-in. |
| 4 | The "couple access after archiving" setting was not enforced. | Medium | Enforced on every portal request and by the cleanup job. |
| 5 | Uploads had no rate limit. | Low | 30 uploads per minute per user. |
| 6 | No Content-Security-Policy for the web app. | Medium | CSP in Caddy; only `'self'` sources. |
| 7 | Production images would contain test and lint tools. | Low | `--build-arg DEV=false` builds without them. |

## Dependency audit

- Python runtime dependencies (`pip-audit`): no known vulnerabilities.
- npm runtime dependencies (`npm audit --omit=dev`): no known vulnerabilities.
- npm development tools: 7 moderate advisories in ESLint's `minimatch` (denial of service with
  crafted patterns). They do not ship to users; update with the next ESLint release.

## Load test

`backend/scripts/loadtest.py`, 20 concurrent users for 30 s against the demo organization on the
local stack (single API process with auto-reload, i.e. slower than production):
4,383 requests, 0 errors, worst p95 219 ms (dashboard). Goal p95 < 300 ms: met.

## Accessibility

Automated WCAG 2.2 AA audit (axe) of 24 pages (15 planner pages, 8 portal pages, sign-in) with
demo data in the Playwright suite (`e2e/accessibility.spec.ts`), on desktop and phone viewports:
no violations. Automated checks find about half of all issues; a manual keyboard and screen
reader pass with a pilot user is still recommended. Colors were chosen for 4.5:1
contrast from Sprint 0; forms use labels, dialogs trap focus and close with Escape.

## Before going beyond the local pilot

These are not needed for the local pilot but must be done before hosting it for real use:

1. Serve the built frontend (`npm run build`) instead of the Vite dev server, then remove
   `'unsafe-inline'` from `script-src` and the websocket from `connect-src` in the CSP.
2. Set `ENVIRONMENT=production` (enforces virus scanning and a strong `SECRET_KEY`), use real
   SMTP with SPF/DKIM, and build images with `DEV=false`.
3. Encrypted backups of PostgreSQL and the object storage, with a tested restore.
4. A data processing agreement (Art. 28 GDPR) template for planners, and a privacy notice.
5. An external penetration test.
