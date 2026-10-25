# TrustVault Security Review

**Review date:** 2026-10-25  
**Review target:** Current local worktree and the local PostgreSQL database
configured for development. This is not a review or attestation of a live
deployment.

## 1. Scope

This review covers the TrustVault Django application, its current document
authorization and upload paths, PostgreSQL audit-chain behavior, relevant
security tests, and the local adversarial HTTP check. The review used source
inspection, the project's pytest suite, a temporary isolated PostgreSQL
database for HTTP checks, and read-only verification of the configured local
database's audit chain.

No production credentials were read into this report. No adversarial HTTP
checks were run against the live deployment. Application code was not changed
as part of this write-up. The current working tree includes documentation
changes and is not a newly created commit.

## 2. Application Architecture

TrustVault is a server-rendered Django application. Django routes in
[`../vault/urls.py`](../vault/urls.py) are implemented by views in
[`../vault/views.py`](../vault/views.py) and
[`../vault/views_admin.py`](../vault/views_admin.py). Application data,
document bytes, grants, and audit events are stored in PostgreSQL. Uploaded
file bytes are returned through the authorized download view; the application
does not expose a public media directory.

The `vault` application contains:

- A custom user model with `admin`, `owner`, and `viewer` roles.
- Documents, file bytes, grants, and suggestions in
  [`../vault/models.py`](../vault/models.py).
- A shared per-document authorization gate in
  [`../vault/authorization.py`](../vault/authorization.py), called through
  route decorators in [`../vault/guards.py`](../vault/guards.py).
- Read-side queries that restrict results to documents the user can read in
  [`../vault/selectors.py`](../vault/selectors.py).
- Upload validation and file-integrity checks in
  [`../vault/services/uploads.py`](../vault/services/uploads.py) and the
  download view.
- A keyed audit chain in
  [`../vault/services/audit.py`](../vault/services/audit.py), with a
  PostgreSQL update/delete trigger installed by migration
  [`../vault/migrations/0007_audit_append_only_trigger.py`](../vault/migrations/0007_audit_append_only_trigger.py).

The project does not expose a versioned JSON API. Its pages and form responses
are HTML, apart from the health check, generic not-found response, and file
downloads.

## 3. Threat Model

**Assets:** confidential document bytes and metadata; user credentials and
sessions; document grants; audit events and audit-chain key; deployment
secrets; database availability and integrity.

**Actors and trust boundaries:**

- Anonymous visitors may attempt login, probe document routes, or submit
  malformed requests.
- Authenticated viewers, owners, and administrators may attempt to exceed
  their role or per-document grants.
- A document owner may upload files that will be shared with grantees.
- The Django application, PostgreSQL database, deployment host, and HTTPS
  proxy are separate trust boundaries. The proxy is trusted to overwrite
  `X-Forwarded-Proto` as configured in
  [`../trustvault/settings.py`](../trustvault/settings.py).
- A database operator with sufficient privileges may bypass application
  controls or disable database protections. Audit anchors only provide
  evidence through the last valid anchor and only if retained independently.

The primary controls are deny-by-default authorization, generic 404 responses
for unavailable documents, per-request database grant checks, CSRF protection,
append-only audit recording, HMAC-linked rows, file-size/type checks, and
download integrity verification. The threat inventory in
[`../THREATS.md`](../THREATS.md) describes additional accepted operational
limitations; those statements are not a substitute for deployment testing.

## 4. Authentication and Authorization

Django uses server-side sessions. `SECRET_KEY` is required at startup;
permissions are not placed in session tokens and grants are checked from the
database on each gated document request. Login and logout audit hooks are
registered by the application.

The authorization gate records allow and deny decisions before the protected
view proceeds. Owners control their own documents. Active `read` and `edit`
grants permit document reading and download; edit grants also permit content
replacement and metadata changes. Sharing, revocation, restore, deletion, and
document history are owner-only. Uploading requires the `owner` role.

The `admin` role protects custom activity and user-management pages; it does
not grant document access. Search is permission-scoped in the database query.
Anonymous visitors denied by a gate are normally redirected to login;
authenticated users denied document access receive the generic 404 response.

## 5. Document Access Controls

Every document-specific route uses the gate in
[`../vault/guards.py`](../vault/guards.py), which delegates to
`authorize(user, doc, action)` in
[`../vault/authorization.py`](../vault/authorization.py). Unknown actions,
unknown grant levels, inactive users, revoked or expired grants, and deleted
documents do not grant access. Restoring a document does not reinstate old
grants.

Uploads accept PDF, DOCX, XLSX, and PPTX extensions and enforce size and
archive limits. Filenames are cleaned and the client-supplied MIME type is not
trusted. Downloads are attachments and are checked against the recorded
SHA-256 digest before bytes are returned.

**Review qualification:** the current PDF inspection checks only for a
`%PDF-` prefix. Office-file inspection checks ZIP structure and metadata but
does not parse the required document XML. A direct local check during this
review confirmed that a malformed PDF with the prefix and an Office archive
with invalid XML are accepted by `inspect_upload()`. See finding TV-02.
File-format checks are not antivirus scanning.

## 6. Audit Logging and Integrity

Audit events record allowed and refused actions. Chained rows contain a
sequence, previous hash, row hash, and HMAC computed with `AUDIT_HMAC_KEY`.
The chain head is locked while a new event is appended. Application-level
queryset guards and a PostgreSQL trigger reject ordinary event updates and
deletes. `ATOMIC_REQUESTS=False` is intended to keep a denial audit write from
being rolled back with an HTTP 404.

This review's default local verification passed for **1,336 chained rows and
0 legacy unchained rows**, with **0 anchors supplied**. Passing this
verification establishes only internal consistency against the key available
to this local process; it does not demonstrate an independently retained
anchor.

The explicit check against [`anchors.log`](anchors.log) **failed**: its anchor
at sequence 445 did not match the configured local database. The cause is not
known from available evidence; it could reflect a database/environment
mismatch or a history-integrity problem. Do not replace or regenerate the
anchor without first investigating the discrepancy. See finding TV-03.

The default-manager append-only queryset is configured, but the current
`AuditEvent` runtime model reports `base_manager_name=None` and uses Django's
plain `Manager` as `_base_manager`. The PostgreSQL trigger is the effective
protection against ordinary SQL updates and deletes; no user-facing route for
calling the base manager was identified. This model-level mismatch remains a
defense-in-depth gap (TV-05).

## 7. Security Test Methodology

Checks were performed against the current worktree as follows:

1. Ran the full pytest suite against PostgreSQL using the configured local
   Python 3.13.7 virtual environment.
2. Re-ran the generic-404 and all-gated-route concealment tests.
3. Ran `scripts/attack_check.py` against a local server backed by a newly
   created temporary PostgreSQL database. The extended run included upload,
   grant-revocation, and throttling checks. The temporary database and server
   were removed/stopped after the run. No live host was targeted.
4. Ran audit-chain verification with and without the saved anchor file.
5. Inspected upload validation behavior directly with malformed in-memory
   inputs; no files were stored by this check.
6. Ran `makemigrations --check --dry-run`.

The earlier result of **60 passed / 4 failed** for a local attack check, and
the earlier live login failure, are prior results reported in the task
context. Their raw output is not present in this repository. The current
isolated local run did not reproduce the 404 failures. The live deployment was
not re-tested.

## 8. Findings

### TV-01 — Historical 404 differential failures are not reproduced

- **ID:** TV-01
- **Severity:** Medium (historical observation); current retest passed
- **Affected component:** `GenericNotFoundMiddleware`, gated document routes,
  and the unauthorized-versus-missing response behavior.
- **Preconditions:** An authenticated user without a grant requests an
  existing document and compares the response to a nonexistent document.
- **Reproduction:** On a disposable local database, seed demo users and a
  document, sign in as an ungranted user, and run the default and extended
  `scripts/attack_check.py` checks. The regression tests also compare
  inaccessible and nonexistent document responses.
- **Expected behavior:** Inaccessible and nonexistent documents return the
  same generic 404 status and body across gated routes.
- **Actual behavior:** The earlier task context reported four failures
  involving response differences and a 404 information-leak check. That
  historical run has no saved raw transcript. In the current run,
  `test_404_responses_are_generic_and_match_for_unavailable_documents` and
  `test_all_gated_routes_deny_and_conceal_documents_for_every_method` passed;
  the extended local attack check reported 68 passed and 0 failed.
- **Remediation:** Generic 404 response middleware and regression coverage
  are present in the current worktree. Do not infer that the earlier
  deployment or source revision was verified by this local retest.
- **Verification:** `test_404_responses_are_generic_and_match_for_unavailable_documents`
  and `test_all_gated_routes_deny_and_conceal_documents_for_every_method` —
  2 passed. `scripts/attack_check.py` with
  `--include-upload --include-revocation --include-throttle` — 68 passed,
  0 failed, against an isolated local database.
- **Status:** Verified for the current local worktree; historical failures
  remain part of the review record.

### TV-02 — Malformed supported file formats are accepted

- **ID:** TV-02
- **Severity:** Low
- **Affected component:** `inspect_upload()` in
  [`../vault/services/uploads.py`](../vault/services/uploads.py), used by the
  upload and replacement views.
- **Preconditions:** An owner uploads a file named with a supported extension.
- **Reproduction:** In a local code check, pass bytes beginning with `%PDF-`
  but not containing a valid PDF to `inspect_upload("sample.pdf", data)`.
  Similarly, make a ZIP with the expected Office filenames but invalid XML
  contents and pass it as a `.docx`. Do not upload these test bytes to a
  non-disposable database.
- **Expected behavior:** A malformed document is rejected before storage and
  the rejection is audited.
- **Actual behavior:** The direct check accepted both the malformed PDF and
  the Office archive with invalid XML. The PDF branch checks the prefix only;
  the Office branch checks archive metadata and expected entry names, not XML
  document structure. The current pytest suite does not include these
  malformed-structure cases.
- **Remediation:** Validate supported formats with appropriate safe parsers
  and strict resource limits, and add regression tests that prove malformed
  content is rejected. Continue to describe malware scanning separately; it
  is not implemented.
- **Verification:** No regression test currently verifies structural PDF or
  Office XML parsing. The one-off local `inspect_upload()` probe returned
  accepted for both malformed samples.
- **Status:** Open.

### TV-03 — Saved audit anchor does not match the local database

- **ID:** TV-03
- **Severity:** Medium
- **Affected component:** `verify_audit`, `verify_chain()`, the configured
  local PostgreSQL audit history, and [`anchors.log`](anchors.log).
- **Preconditions:** Verification is run against the local database currently
  configured by the development environment and the checked-in anchor file.
- **Reproduction:** Run:

  ```powershell
  python manage.py verify_audit
  python manage.py verify_audit --anchors docs\anchors.log
  ```

- **Expected behavior:** The chain verifies, and a supplied anchor matches
  the row at its recorded sequence.
- **Actual behavior:** The default command verified 1,336 chained rows, 0
  legacy rows, and 0 anchors. The anchored command checked one anchor at
  sequence 445 and failed because its digest did not match the database.
  The mismatch does not, by itself, establish malicious tampering.
- **Remediation:** Confirm that the intended database and HMAC key are being
  used; compare against a trusted backup or independently retained anchor;
  investigate the mismatch before accepting or replacing any anchor.
- **Verification:** `python manage.py verify_audit` — passed with no anchor.
  `python manage.py verify_audit --anchors docs/anchors.log` — failed at
  anchor sequence 445.
- **Status:** Open.

### TV-04 — Live HTTP attack check remains unverified

- **ID:** TV-04
- **Severity:** Informational
- **Affected component:** Deployed login flow and the live adversarial HTTP
  check.
- **Preconditions:** A live deployment, its current demo account state, and
  authorized access to run the check.
- **Reproduction:** The prior task context reports that the script's sign-in
  attempt for `ravi` received HTTP 200 where the script expected a redirect,
  so execution stopped before the live checks completed. No live rerun was
  performed for this report.
- **Expected behavior:** With a valid demo account and password, sign-in
  redirects successfully and the authorized live check completes.
- **Actual behavior:** Only the prior reported HTTP 200 is available; its
  cause is not established. [`scans/attack-check-live.txt`](scans/attack-check-live.txt)
  is empty (0 bytes), so there is no saved live transcript. The local isolated
  check successfully authenticated seeded users, but that does not validate
  the deployment.
- **Remediation:** Verify live account state, credentials, and deployment
  configuration, then rerun only with explicit authorization in a controlled
  staging environment. Save a redacted transcript.
- **Verification:** No current live test. The local isolated extended check
  reported 68 passed, 0 failed; it is not a substitute for live verification.
- **Status:** Open.

### TV-05 — Audit base manager bypasses the Python append-only queryset

- **ID:** TV-05
- **Severity:** Low
- **Affected component:** `AuditEvent` base-manager configuration in
  [`../vault/models.py`](../vault/models.py).
- **Preconditions:** Code with ORM access uses `AuditEvent._base_manager` to
  attempt an update or deletion. No ordinary user-facing route for this
  operation was identified.
- **Reproduction:** On a disposable PostgreSQL test database, inspect
  `AuditEvent._meta.base_manager_name` and the manager class of
  `AuditEvent._base_manager`. Do not attempt to edit or delete audit rows in a
  persistent database.
- **Expected behavior:** Every ORM manager exposed by the model should enforce
  the append-only restriction, in addition to the PostgreSQL trigger.
- **Actual behavior:** Runtime inspection reported
  `base_manager_name=None` and `_base_manager` class `Manager`, while the
  default manager is `ManagerFromAppendOnlyQuerySet`. The PostgreSQL trigger
  remains in place and blocks ordinary SQL updates/deletes; no remote user
  path was found.
- **Remediation:** Configure the model's base manager to use the append-only
  queryset and add regression tests for base-manager update/delete attempts.
  Retain the PostgreSQL trigger as the independent database-layer control.
- **Verification:** `test_the_database_itself_refuses_updates_and_deletes`
  passed as part of the full suite, confirming the PostgreSQL trigger. No
  dedicated base-manager regression test is present.
- **Status:** Open (defense-in-depth gap; database trigger currently blocks
  ordinary row changes).

## 9. Remediation Status

| ID | Status | Summary |
|---|---|---|
| TV-01 | Verified | Current tests and isolated HTTP checks pass; the historical 4 failures were not reproduced. |
| TV-02 | Open | Malformed PDF and Office structures are accepted by the current upload inspector. |
| TV-03 | Open | Local database is internally consistent without an anchor, but does not match the saved sequence-445 anchor. |
| TV-04 | Open | Live login/attack check did not complete and was not rerun. |
| TV-05 | Open | PostgreSQL trigger works, but the model's base manager lacks the append-only queryset. |

The historical findings and remediation notes in
[`../SECURITY-REVIEW.md`](../SECURITY-REVIEW.md) should be read alongside this
current-state review. In particular, claims there that PDF parsing and Office
XML structural validation are fixed are not supported by the current
[`../vault/services/uploads.py`](../vault/services/uploads.py) implementation
or by this review's direct check.

## 10. Verification Evidence

| Check | Result | Evidence |
|---|---|---|
| Full Django/pytest suite | **200 passed** in 25.58 seconds | [`scans/security-writeup-pytest.txt`](scans/security-writeup-pytest.txt) |
| Focused 404 concealment tests | **2 passed** in 14.32 seconds | Command: `pytest -q tests\test_hardening.py::test_404_responses_are_generic_and_match_for_unavailable_documents tests\test_routes.py::test_all_gated_routes_deny_and_conceal_documents_for_every_method` |
| Isolated local adversarial HTTP check | **68 passed, 0 failed**; includes upload, revocation, and throttling cases | [`scans/security-writeup-local-attack-check-extended.txt`](scans/security-writeup-local-attack-check-extended.txt) |
| Base local adversarial HTTP check | **46 passed, 0 failed** | [`scans/security-writeup-local-attack-check.txt`](scans/security-writeup-local-attack-check.txt) |
| Audit chain, no supplied anchor | **Passed:** 1,336 chained, 0 legacy, 0 anchors | [`scans/security-writeup-audit-chain.txt`](scans/security-writeup-audit-chain.txt) |
| Audit chain with `docs/anchors.log` | **Failed:** saved anchor at sequence 445 mismatched | [`scans/security-writeup-anchor-check.txt`](scans/security-writeup-anchor-check.txt) |
| Model/migration consistency | **Passed:** no changes detected | `python manage.py makemigrations --check --dry-run` |
| Malformed file-format probe | **Failed expected validation:** malformed PDF and invalid-XML Office archive were accepted | [`scans/security-writeup-upload-validation.txt`](scans/security-writeup-upload-validation.txt); no file was stored. |
| Live adversarial HTTP check | **Not run for this review** | [`scans/attack-check-live.txt`](scans/attack-check-live.txt) is 0 bytes; prior login failure is user-reported. |

The local pytest run used Python 3.13.7 and the locally configured PostgreSQL
database. The adversarial HTTP checks used a separate temporary PostgreSQL
database with freshly seeded disposable users and documents; that database
was dropped and the server was stopped after the run.

An initial local attack-check harness attempt did not reach the application
checks: its in-process Django connection remained attached to the default
local database while the test server targeted the temporary database, so
login returned HTTP 500. The seed command reported 0 users and 0 documents
created. The current default database has the expected six demo users, three
demo documents, three files, and two grants. The failed harness output is not
counted as a security test; the corrected isolated subprocess run is the
68-pass result above.

## 11. Known Limitations

- No antivirus or malware scanning is implemented. Uploaded bytes are stored
  in PostgreSQL; an operator with sufficient database access can read them,
  and application-level encryption at rest is not implemented.
- Total multipart request size without a `Content-Length` header still depends
  on host/server limits, although per-file upload limits apply during parsing.
- Login and anonymous-probe throttling counters are process-local and
  address-based; rotating addresses can evade those limits.
- A download already in progress may finish after a grant is revoked.
- The PostgreSQL trigger does not protect against a sufficiently privileged
  database owner disabling/dropping it. The audit HMAC key must be backed up
  securely; without it, chained rows cannot be verified.
- No independent anchor was verified for the current local chain. The saved
  repository anchor mismatches the configured local database. The earlier
  report of 21 chained rows, 83 legacy rows, and 0 anchors is historical and
  does not describe the current local database result; it also does not prove
  that those earlier legacy events were covered by the chain.
- The live deployment's proxy behavior, current account state, secret
  management, backup/rotation procedures, and deployment configuration were
  not independently verified.
- Search differences between no matches and invalid input, owner usernames
  visible to existing grantees, seed grants not being audited, and several
  retention/concurrency trade-offs are documented as accepted limitations in
  [`../THREATS.md`](../THREATS.md).

## 12. Conclusion

The current local regression suite and isolated HTTP adversarial checks pass,
including the previously reported 404-concealment cases. This is useful
evidence for the current local worktree, not proof of live deployment
security. Two audit-chain facts require careful distinction: the local chain
is internally consistent without an anchor, while the saved sequence-445
anchor does not match that database. In addition, malformed supported file
formats are currently accepted, and live testing remains incomplete.

Do not characterize the live deployment as verified or claim an independent
audit anchor until TV-03 and TV-04 have been investigated with the intended
database and a controlled, authorized staging deployment.
