# ADR 010: Documents are stored privately and only served through the API

- Status: Accepted (15.11.2026)

## Context
Wedding documents (contracts, invoices, guest lists) are personal data. Presigned S3 URLs
would be faster, but a leaked URL works for anyone until it expires, and access rules would
have to be repeated outside the database.

## Decision
- Files go into a private S3 bucket (SeaweedFS locally) under
  `orgs/{org}/projects/{wedding}/documents/{document}/{version}`. The key is never trusted for
  access decisions.
- Uploads and downloads go through the API, which checks the user's rights under row-level
  security first (couples: only documents shared with them). Downloads are always
  `Content-Disposition: attachment` with `nosniff` and a sandboxing CSP.
- The server decides the file type from the extension and checks the first bytes; the type
  sent by the browser is ignored. Up to 25 MB per file, 50 versions per document.
- Every upload is scanned by ClamAV in the worker before it can be downloaded. Infected files
  are deleted and the event is audited. Scanning may only be switched off outside production.
- Jobs are enqueued only after the request's transaction committed (`app.jobs.queue.Jobs`).
- Deleting a document removes all its files at once; the audit log keeps the fact.

## Consequences
Downloads pass through the API process (fine for pilot sizes). A crash between storing a file
and committing can leave an orphaned object; a cleanup job can remove objects without rows.
