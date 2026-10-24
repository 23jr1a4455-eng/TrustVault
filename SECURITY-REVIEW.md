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
**Status:** Fixed in the application
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

Expired grants are now included when reissuing, revoking, and deleting
documents. The owner access page lists unrevoked expired grants and labels
them, so they can be explicitly revoked. Reissuing updates the existing row
and retains its audit record.

Recommended regression tests:

- Reissue access to a recipient who has an expired, unrevoked grant.
- Revoke an expired, unrevoked grant through the supported workflow.

### F-02: Search can include a document for an invalid grant level

**Severity:** Low  
**Status:** Fixed in the application and database schema

`readable_documents()` includes a document when any active grant exists,
without checking whether its level is recognized. Authorization, in contrast,
recognizes only `read` and `edit`; an unknown level grants no access. A
malformed active grant can therefore put a document into search results even
though the authorization check denies access. The grant service rejects
invalid levels, and no remote write path for creating such a row was
identified.

Relevant code: `vault/selectors.py`, `vault/authorization.py`, and
`vault/models.py`.

The readable-document query now uses the shared active-grant queryset, which
requires a supported level. A database constraint rejects invalid levels on
unrevoked grants. The migration revokes malformed active legacy rows before
adding the constraint.

Recommended regression test: Create or attempt to create a grant with an
unsupported level, then assert it cannot make the document appear in the
recipient's search results. Account for database rejection when the constraint
is installed.

### F-03: Bulk ORM operations bypass audit model immutability

**Severity:** Low  
**Status:** Fixed for standard application ORM operations; no remote user path
was identified.

The audit model blocks changes through instance `save()` and `delete()`, but
these methods do not prevent `QuerySet.update()` or `QuerySet.delete()`.
Application code with ORM access can therefore bypass those model-level
protections. No user-facing endpoint that performs these operations was
identified. This does not establish that an ordinary authenticated user can
modify audit records.

Relevant code: `vault/models.py`.

The audit queryset now rejects bulk update, delete, bulk update APIs, raw
queryset deletion, and conflict-updating bulk inserts. Instance `save()` and
`delete()` protections remain. Database-level privileges or triggers are still
needed to protect against direct database clients or privileged SQL.

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
preconditions. The fixes add regression coverage for expired grants, invalid
grant levels, and queryset bulk operations. F-03 still requires ORM or database
access and was not shown to be reachable by an ordinary remote user. H-01's
transaction precondition is disabled in current settings.

Validation: `pytest -q` — 125 passed. `manage.py makemigrations --check
--dry-run` reports no ungenerated migrations.

## Additional review — 2026-10-24

The following findings were validated against the repository after reviewing a
new report. No implementation changes were made as part of this report-only
follow-up.

### F-04: Concurrent stale edit can undo document deletion

**Severity:** Medium
**Status:** Valid, conditional on a concurrent edit and delete request
**Confidence:** 9/10

The edit view authorizes the request and later saves the fetched document
instance without locking or rechecking its current lifecycle state. If an
editor's request is authorized before an owner deletes the document but saves
after that deletion, the stale instance can write `deleted_at=None` back to the
database. The replacement view has a related time-of-check/time-of-use window.

This does not itself restore the editor's revoked grant or grant renewed
access, but it bypasses the owner-only restore workflow and can leave a
document live without the expected restore audit event.

Relevant code: `vault/guards.py` and `vault/views.py` (document edit, delete,
and replacement views).

Recommended remediation: Lock and re-read the document inside the write
transaction, verify it is still active, and re-check the actor's current
permission before applying edits or replacement. Use a compatible locking
protocol for deletion.

Recommended regression test: Deterministically interleave an editor request
that has passed its initial gate with an owner delete, then verify the stale
request cannot modify or undelete the document.

### F-05: Audit immutability can be bypassed through the base manager

**Severity:** Low
**Status:** Valid ORM-layer integrity weakness; no ordinary remote-user path
identified
**Confidence:** 10/10

The custom append-only queryset is attached to `AuditEvent.objects`, but the
model does not configure its base manager to use that protected queryset.
`AuditEvent._base_manager` therefore exposes ordinary queryset update/delete
operations that bypass the guards on the default manager.

Relevant code: `vault/models.py` (`AuditEventQuerySet` and `AuditEvent`).

Recommended remediation: Configure a protected base manager, ensuring it
remains suitable for Django's base-manager use cases, and add tests that attempt
bulk update and deletion through `_base_manager`. Database privileges or
triggers are still required to protect against direct SQL or privileged
database access.

### F-06: File inspection accepts structurally malformed supported formats

**Status:** Confirmed format-validation gap; security impact not established
**Confidence:** 10/10

PDF inspection checks a prefix, while Office-document inspection checks ZIP
metadata and required entry names but does not validate the document XML. The
review reproduced acceptance of a non-PDF with a `%PDF-` prefix and an Office
archive whose required XML entry contains non-XML bytes.

Relevant code: `vault/services/uploads.py`.

This establishes malformed-file acceptance, not code execution or an exploit
against a recipient's viewer. If structural validity is a product requirement,
use format-aware parsing and add malformed PDF and Office-document rejection
tests. Passing structural validation must not be treated as a malware scan.

### F-07: Corrupt Office archive data can raise an uncaught parsing error

**Status:** Confirmed error-handling defect; not a demonstrated security
vulnerability
**Confidence:** 10/10

Office archive entry reads are not fully covered by the `BadZipFile` handler.
A CRC-corrupt entry can therefore raise an unexpected exception rather than
the application's controlled upload-rejection error. The upload and
replacement views handle `UploadRejected`, not that raw archive exception.

Relevant code: `vault/services/uploads.py` and `vault/views.py`.

Recommended remediation: Convert archive-read and decompression failures to
`UploadRejected` around the complete validation operation. Add a corrupt-entry
regression test and verify the expected rejection and audit behavior.

### H-02: Multipart parsing may precede view-level size checks

**Status:** Conditional deployment concern; impact is resource exhaustion and
was not established
**Confidence:** Not fully determined

The configured CSRF middleware can access multipart request data before
view-level upload-size checks. No explicit request-body limit was found in the
repository, but upstream proxy/server limits were not available for
verification.

Recommended action: Confirm and enforce request-body limits at the deployment
edge and test the deployed upload configuration. No code change is justified
without confirming the deployment's limits.

## Additional review validation limits

F-04 requires an in-flight request racing with document deletion. F-05
requires access to the application ORM; no route for ordinary users to invoke
the base-manager operations was identified. F-06 and F-07 concern upload
validation and error handling, not demonstrated exploitation. H-02 depends on
deployment configuration unavailable in the repository.
