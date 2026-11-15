# ADR 004: Organization in the URL path, one domain

- Status: Accepted (15.11.2026)

## Decision
Planner API paths are `/api/v1/orgs/{org_id}/…`. The client portal and planner app share one domain; the portal shows the organization's branding.

## Consequences
No wildcard DNS or certificates for the pilot. Subdomains or custom domains can be added later with middleware that maps a host to an organization.
