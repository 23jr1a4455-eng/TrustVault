# PROMPTS.md

How I use AI on TrustVault, and where it was wrong. Entries are in date order.
All dates are 2026.
Draft from Day 1

## How I work with AI
- Planning and explanation: Claude (chat). Spec-driven planning: GitHub Spec Kit with coding agent.
- Code: Coding agent writes it. I read every diff that touches authorisation, audit, storage or settings.
- Threat model: OWASP Threat Dragon. Checks: pytest, manage.py check --deploy, pip-audit, GitHub secret scanning and CodeQL.
- My rule: AI output is untrusted until I have (1) read it, (2) run it, (3) tried to break it with two accounts, and (4) written a test that fails when the check is removed.
- I never paste real documents, passwords or keys into an AI tool. Seed data is fake.

## Reusable instructions and context

### Rules file (CLAUDE.md, loaded by the agent on every task)
TrustVault rules for the AI agent
1. Every route touching a document calls authorize(user, doc, action).
2. Deny by default. Unknown role, action or state means deny.
3. Never put permissions in tokens; read grants from the DB each request.
4. Log every allow AND deny to audit_events before replying.
5. audit_events is append-only. Never write code that edits or deletes it.
6. Return 404, not 403, for documents the user cannot read.
7. Never trust uploaded filenames or content types.
8. Any auth change needs a test that fails when the check is removed.

### Spec Kit prompts (as I ran them on 2026-10-19)
- `/speckit.constitution` Principles for TrustVault, a secure document-sharing platform: (1) a document is reachable only by someone explicitly granted it; the server decides on every request; (2) every allow and deny is audited in an append-only, tamper-evident log; (3) revoking access takes effect on the next request; (4) deny by default, 404 for unreadable documents; (5) never trust uploaded filenames or types; (6) every auth change needs a test that fails when the check is removed; (7) no permissions in tokens.
- `/speckit.specify` TrustVault lets companies share confidential documents. Roles: admin (manages users, sees activity and permission changes, no document access unless granted), owner (uploads, organises, grants and revokes read/edit to named people on own documents, deletes own documents), viewer (reads or edits only what is granted). Features: login; upload with validation; search by name, owner, category, date (only granted documents); per-document grants; audit trail of uploads, downloads, edits, deletions, permission changes AND refused attempts; admin activity view with flags for suspicious behaviour; optional AI suggestions of who should get access, which a person must confirm and which are audited. Out of scope: folder permissions, public share links, search inside file contents, SSO.
- `/speckit.plan` Django 5 + PostgreSQL, server-rendered templates, server-side sessions, files in private storage streamed through the app only after authorize(), hash-chained append-only audit table, pytest, deployed on a host with managed Postgres and HTTPS.
- `/speckit.checklist` Focus on security: per-document grants, immediate revocation, 404 for non-granted users, append-only audit, upload validation.

### Review questions I reuse on every plan or diff
1. Which single function makes the authorisation decision, and does every route call it?
2. Are permissions read from the database on every request?
3. Are refused attempts audited, even when the response is a 404?
4. What stops an audit row being edited or deleted?
5. How are files kept unreachable without the gate?
6. Does search filter by permission inside the query?

## Entries

### 2026-10-19: Scaffold left the public Django admin mounted (access control)
- Status: verified.
- Asked: Scaffold a Django project for TrustVault with custom apps: accounts, documents, access, audit, adminview, and vault, using a custom user model mapping AUTH_USER_MODEL = "vault.User".
- Produced: a working project where trustvault/urls.py mounted path("admin/", admin.site.urls) and django.contrib.admin was in INSTALLED_APPS.
- What was wrong: Django's admin can read and edit every model. It bypasses authorize() and writes no audit events, which breaks rules 1 and 4 of my own rules file. It is also a public login page that nobody asked for.
- What I did instead: removed the route and removed django.contrib.admin from INSTALLED_APPS, so it is not just unmounted. Added test_django_admin_is_not_exposed, which fails if /admin/ ever returns anything but 404. My admin role is the role field plus my own admin views.
- Commit: local-initial-scaffold

### 2026-10-19: Spec Kit plan graded itself PASS and disagreed with the code and the host (authorisation design)
- Status: verified.
- Asked: /speckit.plan with the prompt above, then I read plan.md against my six review questions.
- Produced: a detailed plan whose "Constitution Check" marks every principle PASS.
- What was wrong: It stores roles in company membership, but the code I already had stores role on User. Two copies of a role can disagree, which is an authorisation bug. It assumes "private persistent file storage". My host's free web service has an ephemeral filesystem, so uploaded files would vanish on every redeploy or restart. Multi-company tenancy, invitations and edit leases are a lot of isolation and concurrency testing for a one-week build. The PASS marks were the AI marking its own work. None of them was tested.
- What I did instead: role lives only on User.role; single organisation, tenancy cut; files stored in PostgreSQL; leases decided on Day 4.
- Commit: local-plan-refactor

### 2026-10-19: Plan may lose the audit row of a refused request (audit trail)
- Status: verified (passed).
- Asked: same plan review as above.
- Produced: the plan says authorisation and the audit append "share a database transaction where possible" and refused requests return 404.
- Suspected problem: if the denial row is written inside a transaction and the view then raises Http404, the row can be rolled back, and the refused attempt the brief wants as evidence disappears.
- Test to run on Day 2: test_denied_request_leaves_audit_row: log in as Sunil, request Priya's document, expect 404, then expect one DENIED audit row.
- Result: pass. The denial row is committed in its own transaction before the 404 is raised.
- Commit: local-audit-denial-test

### 2026-10-19: Settings with a silent SQLite fallback and a hand-written URL parser (configuration)
- Status: verified.
- Asked: Scaffold settings read from environment variables for PostgreSQL database configuration.
- Produced: trustvault/settings.py with a 30-line database_config() function. If DATABASE_URL was missing, the app quietly used db.sqlite3. The parser also accepted sqlite:// URLs.
- What was wrong: my design needs PostgreSQL (append-only audit permissions, row locks, concurrency tests). A forgotten variable on the host would have meant a throwaway local file. A home-made parser for connection strings is also something I would have to defend line by line.
- What I did instead: PostgreSQL only, parsed by dj-database-url. The app refuses to start without a postgres:// URL. Added test_runs_on_postgresql.
- Commit: local-settings-postgres

### 2026-10-19: Settings were not safe behind the host's HTTPS proxy (configuration)
- Status: verified by reading the settings and running check --deploy.
- Asked: same settings prompt.
- Produced: SECURE_SSL_REDIRECT on, no SECURE_PROXY_SSL_HEADER, HSTS for one year with preload from the first deploy, and Django's two-week default sessions.
- What was wrong: behind a proxy, Django would think every request is plain HTTP and redirect forever. A preloaded one-year HSTS is hard to undo if HTTPS is misconfigured. Two-week sessions are too long for a document vault. There was also no STATIC_ROOT or WhiteNoise, so collectstatic would have failed on the host.
- What I did instead: added the proxy header (SECURE_PROXY_SSL_HEADER), HSTS of one hour with no preload, one-hour idle sessions with SameSite cookies, and WhiteNoise plus STATIC_ROOT. Exempted /health/ from the redirect for the host's health check. Checked with check --deploy and curl.exe -I.
- Commit: local-security-headers

### 2026-10-19: Commands written for Linux on a Windows machine (tooling)
- Status: verified.
- Asked: a step-by-step Day 1 procedure.
- Produced: bash commands (python3, source venv/bin/activate, curl ... | sh, # comments, Docker for the database).
- What was wrong: none of that works in Windows cmd. python3, sh and Docker were not available, and PostgreSQL's installer download returned HTTP 403 once.
- What I did instead: asked for a PowerShell version with py, the uv PowerShell installer and a direct PostgreSQL install, and fixed the uv PATH by hand.
- Commit: none (environment setup).

### 2026-10-19: Threat model drawn with the wrong shapes (threat modelling)
- Status: verified.
- Asked: an overview diagram of the system for Threat Dragon.
- Produced: a diagram with plain boxes for every element.
- What was wrong: I copied it as ten plain rectangles, which Threat Dragon treats as Actors. Its own documentation limits Actors mostly to Spoofing and Repudiation, so I could not attach Tampering or Elevation of privilege to the gate or the audit log. I found this by reviewing a screenshot of my diagram.
- What I did instead: redrew the four processes as Process shapes and four stores as Store shapes, kept the browsers as Actors, and kept the AI flows inside the App Server boundary.
- Commit: docs-threat-model-update

"@

### 2026-10-19: Audit rollback concern was a false positive under current settings

- **Asked:** Review the transaction boundary between authorization denial, audit recording, and the resulting 404.
- **Hypothesis:** A request-wide transaction might roll back the denial audit event when the view raises `Http404`.
- **Evidence:** `ATOMIC_REQUESTS` is false in the current settings. `test_denied_request_leaves_audit_row` uses a transaction-enabled test and confirms the denial row remains after the 404.
- **Second-model review:** Confirmed this was conditional, not an active defect with current settings. Keep request-wide transactions disabled unless denial-audit durability is revalidated.
- **Status:** False positive for the current configuration; `test_denied_request_leaves_audit_row` passes locally, and CI passed for the current revision.

### 2026-10-24: Multipart parsing limit was a fair design finding

- **Finding:** CSRF middleware can trigger multipart parsing before a view-level upload-size check, so a view check alone does not protect the parser from oversized uploads.
- **Change:** Added an early declared-body-size middleware check and a streaming upload handler for actual file bytes. The middleware preserves uploader/document authorization and records a rejection before returning 413.
- **Tests:** `test_declared_oversized_multipart_is_rejected_before_csrf_parsing`, `test_upload_handler_stops_oversized_file_during_multipart_parsing`, and oversized replacement tests.
- **Status:** Regression tests and the full suite pass locally; CI passed for commit `519767c`.


## Findings from security drills and review

### Finding: Upload audit failure can leave a document stored

- **Source:** Upload transaction regression — `test_no_audit_row_means_no_stored_document`
- **Evidence:** The audit service raises `RuntimeError`; the required invariant is that document and file rows roll back with the upload transaction.
- **Impact:** A document may persist without the required audit record.
- **Resolution:** Document creation, file storage, and audit recording run in one database transaction.
- **Verification:** `test_no_audit_row_means_no_stored_document` and the full suite pass locally (138 tests); CI passed for commit `519767c`.
- **Status:** Fixed and verified locally and in CI.

### Finding: File-integrity verification was missing or ineffective

- **Source:** Integrity-check regression — `test_altered_file_bytes_are_detected`
- **Evidence:** The remove-one-check drill exposed that stored file bytes must be checked against their recorded digest before serving.
- **Impact:** Modified file content could be served without detection.
- **Resolution:** Verify the SHA-256 digest on every download, audit integrity failure, and do not return the altered bytes.
- **Verification:** `test_altered_file_bytes_are_detected`, valid download coverage, and the full suite pass locally (138 tests); CI passed for commit `519767c`.
- **Status:** Fixed and verified locally and in CI.

### Finding: Restore test could pass because the document was still deleted

- **Source:** Phase 4, check 8 — restore authorization regression.
- **Initial test flaw:** The first test attempted access while the document remained soft-deleted. It would return 404 because of the deleted state even if a grant had incorrectly survived, so it did not prove that restoring failed to revive access.
- **Correction:** Delete the document through the owner route, restore it through the owner route, then verify the grantee is still denied and the grant remains revoked. `test_deleting_revokes_every_grant_and_restoring_does_not_bring_them_back` exercises this sequence.
- **Impact:** A test could appear to verify revocation while only testing the soft-delete gate.
- **Verification:** The corrected test and full suite pass locally (138 tests); CI passed for commit `519767c`.
- **Status:** Test weakness corrected; the grant-revocation invariant is verified locally and in CI.

### Finding: Download route and view parameter mismatch

- **Source:** Download-route regression drill
- **Evidence:** `document_download()` raised `TypeError: unexpected keyword argument 'doc_id'`; nine download tests failed alongside the route-marker test.
- **Impact:** The download endpoint failed, preventing its expected authorization and integrity behavior from being exercised.
- **Resolution:** Align the URL parameter and view signature, and ensure the route has the required protection marker.
- **Verification:** Download and route tests pass in the local full suite (138 tests); CI passed for commit `519767c`.
- **Status:** Fixed and verified locally and in CI.

### Finding: Authorization and upload review found real gaps

- **Source:** Remove-one-check drill and follow-up code review.
- **Confirmed issues:** An expired unrevoked grant could block re-sharing/revocation; an invalid grant level could make a document appear in search; audit queryset protections could be bypassed through bulk operations or the base manager; stale edit/replacement writes could race with deletion; malformed PDFs/Office XML and CRC-corrupt archives were not consistently rejected; and multipart parsing could begin before a view-level size check.
- **Changes:** Grant queries and constraints now reject/handle these cases; audit append-only protections cover the base manager; edit/delete/replace serialize on a document lock and recheck permission; format-aware validation maps corrupt input to audited rejection; request and file-size limits apply before/during parsing.
- **Verification:** Relevant regression tests and the local full suite pass (138 tests); CI passed for commit `519767c`.
- **Drill result:** Each of the ten requested “remove one check” mutations made its associated test fail; no all-green mutation remained to prompt another missing test.
- **Status:** Confirmed findings fixed and verified locally and in CI.