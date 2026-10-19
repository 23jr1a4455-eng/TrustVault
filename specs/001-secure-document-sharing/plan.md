# Implementation Plan: Secure Document Sharing

**Branch**: `001-secure-document-sharing` | **Date**: 2026-10-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-secure-document-sharing/spec.md`

## Summary

Build TrustVault as a Django 5.2 LTS server-rendered application backed by
PostgreSQL. Use Django authentication with database-backed sessions, explicit
company membership and per-document grants, and an authorization service
called by every document operation. Store uploads privately under generated
storage keys and deliver them only through an application view that authorizes
the current request before streaming. Record decisions and business activity
in an append-only, globally hash-chained audit log. Use PostgreSQL row locks
for serialized audit appends and one-editor leases. Validate behavior with
pytest, including transactional tests against PostgreSQL. Deploy behind HTTPS
with managed PostgreSQL.

## Technical Context

**Language/Version**: Python 3.13; Django 5.2 LTS (Django 5.x as requested)

**Primary Dependencies**: Django 5.2, psycopg 3, python-dotenv; pytest and
pytest-django for development tests

**Storage**: Managed PostgreSQL for relational data, sessions, grants, leases,
and audit events; private persistent file storage outside the web root for
document bytes. Database connection and stored-file secrets/configuration are
provided by the host environment.

**Testing**: pytest, pytest-django, Django system checks; authorization and
audit tests plus PostgreSQL-backed transactional and concurrency tests

**Target Platform**: HTTPS-enabled application host connected to managed
PostgreSQL; private persistent storage accessible to the application

**Project Type**: Server-rendered multi-tenant web application

**Performance Goals**: No numeric service-level targets or expected company
volume were specified. Keep authorization and metadata transactions short,
index company-scoped lookup paths, and establish capacity targets before
production load qualification.

**Constraints**: Every document operation checks current database grants;
unreadable documents return 404; authorization and refused attempts are
audited before responding; audit events cannot be updated or deleted;
revocation applies on the next request; file bytes are never publicly served;
uploads accept PDF, DOCX, XLSX, and PPTX up to 25 MB; only one editor holds a
document lease, expiring after 15 minutes of inactivity; AI suggestions use
company sharing metadata only, with no external AI processing or document
contents.

**Scale/Scope**: One company per member for this release; administrator,
owner, and viewer roles; document-level read/edit grants. No numeric user or
document volume is specified. Folder permissions, public links, content
search, and SSO remain out of scope.

## Constitution Check

### Pre-Phase 0

- **Explicit grants / request-time authorization**: PASS. The plan uses a
  single authorization service for each document action and reads current
  membership and grant state from PostgreSQL on every request.
- **Audit ALLOW and DENY before response**: PASS. Authorization and business
  activity are audited before the response; audit persistence failure fails
  the operation closed rather than returning an unaudited success.
- **Append-only, tamper-evident audit**: PASS. Audit events form a serialized
  SHA-256 hash chain; runtime database permissions and database protections
  deny UPDATE/DELETE on event rows.
- **Revocation, default deny, and 404**: PASS. Grant checks are not cached;
  missing or unknown states deny; unreadable document requests return 404.
- **Upload trust boundary**: PASS. Server-side content validation, generated
  storage keys, private storage, and application-mediated downloads are
  required.
- **Authorization regression tests**: PASS. Tests must fail when a relevant
  authorization check is removed; PostgreSQL tests verify transactional locks
  and audit ordering.
- **No token permissions**: PASS. Django session state carries identity only;
  document grants are read from PostgreSQL for each decision.
- **Violations**: None.

## Project Structure

### Documentation (this feature)

```text
specs/001-secure-document-sharing/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── web-workflows.md
└── tasks.md                 # Created by /speckit-tasks
```

### Source Code (repository root)

```text
manage.py
requirements.txt
requirements-dev.txt
pyproject.toml
trustvault/
├── settings.py
├── urls.py
├── asgi.py
└── wsgi.py
vault/
├── apps.py
├── models.py
├── forms.py
├── urls.py
├── views.py
├── authorization.py
├── selectors.py
├── services/
│   ├── audit.py
│   ├── documents.py
│   ├── grants.py
│   ├── invitations.py
│   ├── leases.py
│   └── uploads.py
├── templates/vault/
├── static/vault/
└── management/commands/
tests/
├── conftest.py
├── test_authorization.py
├── test_audit.py
├── test_documents.py
├── test_uploads.py
├── test_leases.py
└── test_members_and_admin.py
```

**Structure Decision**: Extend the existing Django project and `vault` app;
keep HTTP views thin, place authorization and transactional operations in
explicit app services, and use focused top-level pytest tests. Define the
custom user model before creating the initial database migration so identity
and company membership are stable from the start. Templates remain server
rendered; the only planned client script is the minimum needed to maintain an
active edit lease while an editor is using the edit screen.

## Constitution Check (Post-Phase 1 Design)

- **Every document route calls `authorize(user, doc, action)`**: PASS. The web
  contract requires an action-specific decision before document data or file
  bytes are returned or changed.
- **Current grants / revocation / no permissions in tokens**: PASS. The
  authorization service checks active company membership and current grant
  rows; the session stores identity only.
- **ALLOWED and DENIED decisions audited before replying**: PASS. Audit append
  and protected state mutation share a database transaction where possible;
  private file operations are staged around database transactions and never
  expose success before the audit append commits.
- **Append-only and tamper-evident audit**: PASS. Audit event rows are
  insert-only, globally hash chained, and protected from update/delete by
  runtime role privileges and database safeguards.
- **404 for unreadable documents**: PASS. The same not-found response is used
  for absent and unreadable document identifiers.
- **Untrusted uploads / private streaming**: PASS. Verified file format,
  generated storage key, private storage, no direct public URL, and
  per-request authorization before streaming.
- **Security regression testing**: PASS. Each authorization path gets a
  negative test that fails if its guard is removed; lease and audit locking
  tests run against PostgreSQL.
- **Violations**: None.

## Complexity Tracking

No constitution violations or unjustified architectural complexity.

## Requirement Coverage

| Spec area | Design location |
|---|---|
| FR-001, FR-002, FR-017: sign-in, membership, roles, user administration | Company, user, membership, invitation model and member workflows |
| FR-003–FR-007: document authorization, grants, revocation, 404 | Authorization service and document/grant web workflows |
| FR-008–FR-009: activity audit, ordering, append-only integrity | Audit event model, chain head, database protections |
| FR-010: upload validation and safe storage | Upload service and private storage rules |
| FR-011: access-filtered search | Company- and grant-scoped search selector |
| FR-012–FR-013: admin activity and suspicious-attempt flag | Audit activity query and configurable threshold policy |
| FR-014: confirmed metadata-only AI suggestions | Optional suggestion workflow; no external provider |
| FR-015: auth regression tests | pytest authorization and workflow test suite |
| FR-016: exclusions | No folder grants, public links, content search, or SSO routes |
| FR-018: exclusive edits and expiry | PostgreSQL-backed edit lease and its web workflow |
| SC-001–SC-009 | Permission, audit, upload, search, admin, AI, and PostgreSQL concurrency tests |
