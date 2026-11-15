# ADR 011: Private iCal feeds with a secret token

- Status: Accepted (15.11.2026)

## Context
Planners and couples want their appointments in Apple Calendar, Google Calendar or Outlook.
Those apps cannot sign in; they poll a URL.

## Decision
- Each member can create one feed per organization. The URL contains a random 256-bit token;
  only its SHA-256 hash is stored, so the URL is shown exactly once. Creating a new link turns
  the old one off; members can turn it off at any time. A disabled membership stops the feed.
- The token is resolved by a SECURITY DEFINER function; the feed is then built with the
  member's own tenant context and role, so it never contains more than the app would show.
- Feeds leave the platform (calendar providers sync them), so they only carry titles, dates,
  times and places: no notes, descriptions or amounts. Tasks are limited to the member's own
  (team) or the couple's tasks (couple).

## Consequences
Anyone who obtains the URL can read the feed until it is reset; the UI says so. Feeds are
rate limited per IP and marked `noindex`.
