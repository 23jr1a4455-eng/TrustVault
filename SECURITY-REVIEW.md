# Security Review

Review date: 2026-10-24

## Scope

This review validated the reported grant-management, search-permission, audit
immutability, and request-transaction findings against the current application.
It distinguishes application-level weaknesses from issues with a demonstrated
remote user path.

## Findings

### F-01: Expired grants can block re-sharing and revocation

**Severity:** Medium  
**Status:** Confirmed access-management availability defect  
**Remote impact:** Does not grant unauthorized access; an owner can be unable
to reissue or revoke a grant through the normal workflow.

`GrantQuerySet.active()` excludes expired grants, while the database uniqueness
constraint applies to every grant whose `revoked_at` is null. `grant_access()`
therefore misses an expired row and can fail to insert a replacement due to the
unique constraint. `revoke_access()` also searches only active grants and
cannot revoke that expired row. The owner-facing access listing also uses
active grants only.

Relevant code: `vault/models.py`, `vault/services/grants.py`, and
`vault/views.py`.

Recommended remediation: Find existing unrevoked grants regardless of expiry
when reissuing or revoking. Update or revoke the existing row and preserve the
audit record.

Recommended regression tests:

- Reissue access to a recipient who has an expired, unrevoked grant.
- Revoke an expired, unrevoked grant through the supported workflow.

### F-02: Search can include a document for an invalid grant level

**Severity:** Low  
**Status:** Confirmed permission-query inconsistency; exploitability is
conditional on malformed grant data being persisted.

`readable_documents()` includes a document when any active grant exists,
without checking whether its level is recognized. Authorization, in contrast,
recognizes only `read` and `edit`; an unknown level grants no access. A
malformed active grant can therefore put a document into search results even
though the authorization check denies access. The grant service rejects
invalid levels, and no remote write path for creating such a row was
identified.

Relevant code: `vault/selectors.py`, `vault/authorization.py`, and
`vault/models.py`.

Recommended remediation: Restrict the readable-document query to supported
grant levels, and add a database check constraint to prevent invalid values
from being persisted. The query restriction also protects against malformed
legacy rows.

Recommended regression test: Create or attempt to create a grant with an
unsupported level, then assert it cannot make the document appear in the
recipient's search results. Account for database rejection when the constraint
is installed.

### F-03: Bulk ORM operations bypass audit model immutability

**Severity:** Low  
**Status:** Confirmed model-layer integrity weakness; no remote user path
identified.

The audit model blocks changes through instance `save()` and `delete()`, but
these methods do not prevent `QuerySet.update()` or `QuerySet.delete()`.
Application code with ORM access can therefore bypass those model-level
protections. No user-facing endpoint that performs these operations was
identified. This does not establish that an ordinary authenticated user can
modify audit records.

Relevant code: `vault/models.py`.

Recommended remediation: Block bulk update and delete in a custom audit
queryset/manager to guard application-level operations. If the guarantee must
also hold against privileged application code or direct database clients, use
database-level privileges or triggers.

Recommended regression tests:

- Assert a queryset bulk update cannot rewrite an audit event.
- Assert a queryset bulk delete cannot erase an audit event.

### H-01: Denial audit loss with `ATOMIC_REQUESTS`

**Severity:** Not currently applicable  
**Status:** Conditional hypothesis; current settings disable the precondition.

If a denied request is enclosed in a transaction that rolls back when the view
raises `Http404`, its audit write could also be rolled back. The current
settings set `ATOMIC_REQUESTS = False`, and a test asserts that request views
are not wrapped in a transaction. The hypothesis is therefore not an active
issue under the current configuration.

Relevant code: `vault/authorization.py` and `trustvault/settings.py`.

Recommended action: Retain the `ATOMIC_REQUESTS = False` setting. If request
transactions are introduced later, verify that denied authorization events
remain durable.

Existing tests: `tests/test_settings.py` and `tests/test_audit.py` cover the
current transaction setting and denied-request audit behavior.

## Validation limits

The confirmed issues above describe implementation behavior and stated
preconditions. F-02 requires malformed persisted grant data, and F-03 requires
ORM or database access; neither was shown to be reachable by an ordinary
remote user in this review. H-01's transaction precondition is disabled in
current settings.

No application code was changed as part of this report-only follow-up.
