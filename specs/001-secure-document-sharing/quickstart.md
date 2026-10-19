# Quickstart Validation Guide

This guide describes the planned end-to-end validation path for the TrustVault
feature. It is intended for implementation and deployment verification; it
does not replace the test suite.

## Prerequisites

- Python 3.13 and the project virtual environment
- PostgreSQL database (use PostgreSQL for the full suite, especially leases and
  audit-chain concurrency)
- A `.env` file with a strong `SECRET_KEY`, PostgreSQL `DATABASE_URL`,
  `ALLOWED_HOSTS`, `DEBUG=0` for production checks, and an absolute private
  storage directory outside the web root
- A private persistent volume mounted at the configured storage directory
- Deployment HTTPS endpoint and trusted managed-Postgres TLS CA configuration

## Install and Initialize

In PowerShell from the repository root:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Edit .env with local test credentials and DATABASE_URL; do not overwrite an existing file.
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py check
```

The development SQLite fallback may be used for simple template and form
checks, but it does not establish PostgreSQL locking, lease, or audit append
correctness.

## Run Automated Validation

```powershell
.\venv\Scripts\python.exe -m pytest
.\venv\Scripts\python.exe manage.py check --deploy
```

Expected outcomes:

- All unit and workflow tests pass.
- PostgreSQL transactional tests prove grant revocation, exclusive edit
  leases, expiry/fencing, and serialized audit-chain appends under concurrency.
- Authorization tests fail if any required document authorization check is
  removed.
- Deployment checks pass with production settings, explicit hosts, HTTPS
  security settings, and secure cookies.

## End-to-End Scenarios

1. Create a company, an administrator, an owner, and two viewers. Sign in using
   server-side sessions and verify CSRF rejection for missing tokens on
   state-changing forms.
2. Upload valid PDF, DOCX, XLSX, and PPTX fixtures up to 25 MiB. Confirm the
   file bytes reside only in private storage under generated keys. Reject
   malformed content, unsupported formats, and files larger than 25 MiB.
3. Grant read access to one viewer and edit access to another. Confirm read-only
   download succeeds only for the first member, editing succeeds only for the
   second, and an ungranted admin receives 404.
4. Revoke access, then immediately repeat both direct document and search
   requests. Confirm no stale session, page, or grant cache preserves access.
5. Start an edit lease for one member. Confirm a second authorized editor
   waits, lease renewal works only for the current generation, and an idle
   lease expires after 15 minutes so a stale generation cannot save.
6. Attempt unauthorized access, invalid upload, role self-escalation, and
   disallowed grant changes. Confirm each denial is recorded before its
   response and unreadable documents return 404.
7. Append events concurrently and verify globally increasing sequence,
   matching previous hashes, and successful chain verification. Confirm the
   runtime database credential cannot update or delete audit events.
8. Review the admin activity view and verify it displays event metadata and
   suspicious flags without exposing document contents or bypassing grants.
9. Generate an optional access suggestion and verify it uses only company
   sharing metadata, does not call an external AI provider, and creates no
   grant until a person confirms the normal grant flow.

Refer to [web-workflows.md](./contracts/web-workflows.md) for route behavior and
[data-model.md](./data-model.md) for entity and audit invariants.
