# Research: Secure Document Sharing

**Date**: 2026-10-19
**Scope**: Resolve technology and security design choices for the plan.

## Decisions

### Framework and runtime

- **Decision**: Use Django 5.2 LTS, Python 3.13, and PostgreSQL through psycopg 3.
- **Rationale**: The repository already targets Django 5.2 or later within the
  Django 5 series. Django 5.2 is the supported LTS line and the 5.2
  documentation matches the selected runtime.
- **Alternatives considered**: Django 5.0/5.1 are not selected; they are no
  longer supported. Django 6.x is outside the requested Django 5 scope.
- **References**: [Django supported releases](https://www.djangoproject.com/download/);
  [Django 5.2 documentation](https://docs.djangoproject.com/en/5.2/).

### Authentication and sessions

- **Decision**: Use Django authentication and database-backed server-side
  sessions. Keep grant data out of session contents; authenticate with a
  project-owned user model defined before the first migration.
- **Rationale**: This uses Django's established login/session behavior and
  ensures grant revocation is visible on the next request because grants are
  queried independently of session state. Keep CSRF middleware and require
  CSRF tokens on every state-changing form, including uploads and edit-lease
  actions.
- **Alternatives considered**: Custom cookies, permission-bearing sessions,
  and client-side permission tokens violate the required trust boundary.
- **References**: [Django sessions](https://docs.djangoproject.com/en/5.2/topics/http/sessions/#using-database-backed-sessions);
  [Django authentication](https://docs.djangoproject.com/en/5.2/topics/auth/default/#how-to-log-a-user-in);
  [Django CSRF guide](https://docs.djangoproject.com/en/5.2/howto/csrf/).

### Document authorization and private file delivery

- **Decision**: Centralize action-specific checks in `authorize(user, doc,
  action)` and call it for every document detail, search result, download,
  edit, grant, revoke, organize, delete, and lease operation. Use generated
  storage keys and private persistent storage outside the web root. A download
  view checks the current grant, records its audit event, commits the short
  database transaction, then opens and streams the file through the app. Send
  private no-store cache headers and `X-Content-Type-Options: nosniff`.
- **Rationale**: Django authentication does not automatically implement
  document-level object grants. No storage URL may bypass application
  authorization. Django consumes streaming response bodies after the view
  returns, so the authorization transaction must finish before streaming and
  must not be held open during file I/O.
- **Alternatives considered**: Public media paths, public/signed storage URLs,
  trusting opaque identifiers, and relying on a previously authorized
  document page all bypass per-request authorization.
- **References**: [Django permissions](https://docs.djangoproject.com/en/5.2/topics/auth/default/#permissions-and-authorization);
  [Django file uploads](https://docs.djangoproject.com/en/5.2/topics/http/file-uploads/);
  [Uploaded content security](https://docs.djangoproject.com/en/5.2/topics/security/#user-uploaded-content);
  [Django storage API](https://docs.djangoproject.com/en/5.2/ref/files/storage/);
  [FileResponse](https://docs.djangoproject.com/en/5.2/ref/request-response/#fileresponse-objects);
  [Django transactions](https://docs.djangoproject.com/en/5.2/topics/db/transactions/);
  [HTTP Cache-Control](https://www.rfc-editor.org/rfc/rfc9111.html#name-cache-control).

### Upload validation

- **Decision**: Enforce the specified 25 MB limit at both request ingress and
  application level. Verify actual content against PDF or OOXML format
  structure; do not treat the filename or client MIME type as authoritative.
  Store under a random key, outside the static/media web root. Reject malformed
  packages and unsupported types.
- **Rationale**: Extension and content-type strings are user-controlled;
  structure checks and a private generated path prevent trivial type/path
  spoofing. A host-level limit reduces resource exhaustion before Django
  receives the body.
- **Alternatives considered**: Extension-only checks, public media serving, and
  reading the complete file into memory are rejected.
- **References**: [Django uploads](https://docs.djangoproject.com/en/5.2/topics/http/file-uploads/);
  [Django uploaded-content security](https://docs.djangoproject.com/en/5.2/topics/security/#user-uploaded-content).
- **Scope note**: No malware-scanning provider or malware-scanning requirement
  is specified; do not claim uploaded files are virus-scanned.

### Append-only audit chain

- **Decision**: Use one global chain-head row and a SHA-256 chain over a
  deterministic UTF-8 JSON encoding of each event and its prior digest.
  Serialize append operations by locking the head row with PostgreSQL
  `select_for_update()` inside a short `transaction.atomic()` block; insert
  the event and advance the head in the same transaction. Establish a genesis
  digest. Give the runtime database role SELECT/INSERT on event rows, but no
  UPDATE/DELETE; protect rows with database-level safeguards as well.
- **Rationale**: A global order is the simplest verifiable model for an
  initial deployment. Database role restrictions make ordinary application
  credentials unable to rewrite the history. File I/O must not occur while the
  chain-head lock is held.
- **Alternatives considered**: Per-document chains improve parallel append
  throughput but provide no global event order; an unchained event table is
  not tamper-evident; external checkpoints add an integration not requested.
- **Limit**: A hash chain detects changes only when verified against a trusted
  head. A database owner or attacker able to replace the entire database can
  rewrite a chain. External anchoring is not included in this release.
- **References**: [Django row locking](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update);
  [PostgreSQL explicit locking](https://www.postgresql.org/docs/current/explicit-locking.html);
  [PostgreSQL privileges](https://www.postgresql.org/docs/current/ddl-priv.html);
  [PostgreSQL triggers](https://www.postgresql.org/docs/current/sql-createtrigger.html).

### Exclusive editing

- **Decision**: Represent one active edit per document as a lease row with a
  unique document constraint, owner, last-activity time, expiry, and generation
  number. Acquire, renew, release, and save under a short document-row lock and
  transaction. Expire at 15 minutes without activity; an editor with an
  expired generation must reopen before saving. Record acquisition, renewal,
  wait, expiry, release, and save outcomes in the audit trail.
- **Rationale**: PostgreSQL row locks and a unique constraint prevent concurrent
  lease creation; a generation number prevents a stale editor from saving
  after another editor has acquired the document.
- **Alternatives considered**: Client-only locks and SQLite tests do not
  protect concurrent application workers. Permanent locks are inconsistent
  with the clarified inactivity policy.
- **References**: [Django `select_for_update`](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update);
  [Django transactions](https://docs.djangoproject.com/en/5.2/topics/db/transactions/);
  [PostgreSQL locking and deadlocks](https://www.postgresql.org/docs/current/explicit-locking.html).

### Tests and production security

- **Decision**: Use pytest and pytest-django. Use transactional database tests
  against PostgreSQL for lock/concurrency and hash-chain ordering. Run Django's
  deployment checks with production settings. Deploy with `DEBUG=False`,
  explicit hosts, secure session/CSRF cookies, HTTPS, HSTS after HTTPS is
  confirmed, and TLS-verified managed PostgreSQL connectivity.
- **Rationale**: Django `TestCase` wraps each test in a transaction and can
  mask incorrect `select_for_update()` use; SQLite lacks PostgreSQL row-lock
  behavior. Deployment checks and TLS/cookie settings align the platform with
  the confidential-document threat boundary.
- **Alternatives considered**: SQLite-only validation is insufficient for
  concurrency. HTTP database connections and insecure cookies are not
  acceptable for production.
- **References**: [pytest-django database tests](https://pytest-django.readthedocs.io/en/latest/database.html);
  [Django `select_for_update` test caveat](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update);
  [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/);
  [Django security settings](https://docs.djangoproject.com/en/5.2/ref/settings/#security);
  [PostgreSQL TLS verification](https://www.postgresql.org/docs/current/libpq-ssl.html).

## Explicit Planning Assumptions

- Use an encrypted, persistent private volume mounted only to application
  workers as the initial file backend; the deployment host must provide
  persistence and backup. No public file URL is configured. Revisit a private
  object-storage backend if the host cannot provide shared durable storage.
- Define the initial audit event fields as actor/member identifier (nullable
  for unauthenticated attempts), company identifier, action, outcome,
  target type and identifier when known, reason code, UTC timestamp, prior
  digest, and event digest. Avoid recording file contents, credentials,
  session identifiers, or unnecessary personal data.
- Use a distinct migration/owner database credential for schema changes and a
  restricted runtime credential for serving requests; provision these through
  the deployment secret manager.
- Treat numeric scale, SLOs, audit retention, invitation expiration, and
  external audit anchoring as deployment/product policy decisions not supplied
  by the feature request. They are not blockers to this initial design.
