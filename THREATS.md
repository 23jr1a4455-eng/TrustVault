# THREATS.md



Status updated 2026-10-24. I update it as implementation and verification progress.

Sources: my Threat Dragon model (`docs/threat-model/`), the Spec Kit plan, and my own list.



> **\*\*Draft.\*\*** Rewrite each "Defence" in your own words, and keep a status of

> **\*\*Done\*\*** only where you can point at code, a test or a setting.



**\*\*Status key:\*\*** **\*\*Done\*\*** = built and passed locally and in CI. **\*\*Local pass; CI pending\*\*** = verified in the current worktree, but not yet in a CI run for that revision. **\*\*Planned Dn\*\*** = designed, to be built on day *\*n\**. **\*\*Accepted\*\*** = I know about it, and the reason is in "Accepted risks" below.



## 1. Authorisation (the gate)



| ID | Threat | Defence | Test | Status |

|---|---|---|---|---|

| A-01 | Guessing document IDs (`/documents/42` then 43) | One `authorize(user, doc, action)` gate; unguessable UUID ids; 404 for anything unreadable | `test_other_user_gets_404_for_unreadable_document`, `test_strangers_cannot_download` | Done |

| A-02 | A new route that forgets the check | Route-inventory test requires each URL to declare its protection mechanism | `test_every_route_declares_how_it_is_protected` | Done |

| A-03 | Viewer calls owner-only actions directly (grant, delete, upload) | Each action needs its own permission, not only a role | `test_only_the_owner_can_manage_access`, `test_viewers_and_admins_cannot_upload`, delete authorization tests | Done |

| A-04 | Owner A reads or edits owner B's document | Ownership checked per document | `test_owner_cannot_access_other_owners_document` | Done |

| A-05 | 403 vs 404, or response differences, reveal that a file exists | Same status and body for "absent" and "not yours" | `test_nonexistent_and_unreadable_look_identical` | Done |

| A-06 | Mass assignment (`role`, `owner`, `is_staff` in a request body) | Document edits ignore owner changes; web routes do not provide role changes | `test_edit_ignores_owner_field`, `test_the_website_has_no_way_to_change_roles` | Done |

| A-07 | Side doors: preview, thumbnail, versions, export, HEAD, OPTIONS, trailing slash, encoded paths | Every currently implemented document route is gated; preview and export remain planned | `test_all_gated_routes_deny_an_ungranted_user_for_every_method` (implemented routes only) | Done for implemented routes; preview/export planned |

| A-08 | Search, autocomplete, counts or pagination leak titles or existence | Permission filtering is applied in the query before results and counts are paginated | `test_search_only_finds_what_the_person_may_read`, `test_counts_never_include_hidden_documents`, `test_pagination_stays_inside_permissions` | Done |

| A-09 | Admin grants themselves access, takes ownership or silently makes another admin | Admin has no document-content access or web role management; administrator page views are audited; ownership transfer is not built | `test_the_admin_still_cannot_open_documents`, `test_the_website_has_no_way_to_change_roles`, `test_administrators_looking_at_the_log_are_themselves_recorded` | Done |

| A-10 | Open redirect through `?next=` after login | Only same-host redirect targets are allowed | `test_login_rejects_external_next_url` | Done |

| A-11 | Public Django admin bypasses the gate and the audit | Admin app removed from `INSTALLED_APPS` and not routed | `test_django_admin_is_not_exposed` | Done |

| A-12 | Disabling a user leaves an existing session usable | Disabling a non-admin user ends their active sessions immediately | `test_disabling_a_user_ends_every_session_at_once` | Done |

| G-01 | A guessed grant id revokes someone else's access | The grant must belong to the document being managed | `test_a_grant_id_from_another_document_cannot_be_revoked` | Done |

| G-02 | An editor shares the document | Sharing and access management require owner-level authorization | `test_only_the_owner_can_manage_access` | Done |

| G-03 | A grant is created without its audit row | Grant creation and audit recording are atomic | `test_no_audit_row_means_no_grant` | Done |



## 2. Revocation and deletion



| ID | Threat | Defence | Test | Status |

|---|---|---|---|---|

| R-01 | Revoked user replays an old request, link or session | Grants read from the database on every request; revocation removes access to documents, downloads, and search immediately | `test_revoking_takes_effect_on_the_next_request`, `test_revoked_user_cannot_download_on_the_next_request`, `test_revoked_expired_and_deleted_documents_leave_search_at_once` | Done |

| R-02 | Disabled user keeps an existing session | `is_active=False` is refused on the next request; sessions deleted on disable | `test_disabled_user_session_stops_working`, `test_disabling_a_user_ends_every_session_at_once` | Done |

| R-03 | A download already streaming finishes after revoke | Checked once at the start of the response | none | Accepted (A-1) |

| R-04 | Revoked editor saves after access is revoked | Save re-checks the current grant. Edit leases are cut; leases are not built. | `test_a_revoked_editor_cannot_save` | Done for revoked-editor save; leases cut/not built |

| R-05 | Browser or proxy caches a document after logout or revoke | `Cache-Control: no-store` on document and download responses | `test_document_pages_are_not_cacheable` | Done |

| R-06 | Restoring a deleted document revives old grants | Delete revokes grants; restore does not revive them | `test_deleting_revokes_every_grant_and_restoring_does_not_bring_them_back` | Done |



## 3. Audit trail



| ID | Threat | Defence | Test | Status |

|---|---|---|---|---|

| U-01 | Audit rows edited or deleted (app bug, SQL injection, insider) | ORM protections reject changes and the PostgreSQL trigger rejects UPDATE and DELETE | `test_the_model_refuses_bulk_changes`, `test_the_database_itself_refuses_updates_and_deletes` | Done |

| U-02 | The whole hash chain rewritten | Keyed HMAC chain, verifier, and saved external anchors detect rewrites covered by an anchor | `test_an_edited_row_is_detected`, `test_an_attacker_with_the_key_is_caught_only_by_the_anchors` | Done |

| U-03 | Refused attempts lost when the 404 rolls back the transaction | Request-wide transactions are disabled; the denial audit is committed before the 404 | `test_denied_request_leaves_audit_row` | Done |

| U-04 | Audit write fails but an upload or download still succeeds, or a document persists without its audit row | Fail closed: audit failure must not leave a stored document or return protected content; coordinate database and file-storage rollback/cleanup | `test_no_audit_row_means_no_stored_document`, `test_audit_failure_blocks_access`, `test_download_fails_if_audit_write_fails` | Done |

| U-05 | Log injection (newlines or huge strings in titles or usernames) | Structured fields, control-character cleanup, length caps, and escaped display | `test_log_values_cannot_forge_lines_or_grow_without_limit` | Done |

| U-06 | Two writers fork the chain | Row lock on the chain head serializes appends | `test_concurrent_writers_never_fork_the_chain` | Done |

| U-07 | Audit flooding to hide an attack or fill the disk | Login throttling and an anonymous document-probe limit return 429 after thresholds; one summary audit event is written per address and window | `test_login_is_rate_limited`, `test_anonymous_probing_is_slowed_down_and_logged_once` | Local pass; CI pending for Day 6 changes |

| U-08 | Wrong or forged timestamps | Server UTC timestamp; never accept a client-supplied audit time | `test_audit_uses_server_time` | Done |

| U-10 | Database owner with the audit key rewrites the complete chain | A saved Git anchor detects a rewrite of history covered by that anchor | `test_an_attacker_with_the_key_is_caught_only_by_the_anchors` | Done |

| U-11 | Rows written before chain creation are not tamper-evident | Pre-chain rows are counted and reported separately from chained rows | `test_rows_from_before_the_chain_are_counted_not_failed` | Done |

| U-09 | Sensitive data copied into audit or host logs | Log ids and actions, never file contents; titles kept out of server logs | review in `docs/` | Planned D5 |



## 4. Authentication and sessions



| ID | Threat | Defence | Test | Status |

|---|---|---|---|---|

| S-01 | Brute force or credential stuffing | Login throttling per account and per address; passwords at least 12 characters | `test_login_is_rate_limited` | Done |

| S-02 | User enumeration through login messages or timing | One generic error message for every login failure | `test_login_error_is_identical_for_every_kind_of_failure` | Done |

| S-03 | Cookie theft, fixation, long-lived sessions | HttpOnly, Secure, SameSite=Lax cookies; one-hour idle timeout; Django cycles the key on login; logout deletes the session | settings check, `test_logout_ends_the_session` | Done |

| S-04 | CSRF on grant, revoke, delete | `CsrfViewMiddleware` is enabled and unsafe requests need a token | `test_post_without_csrf_token_is_rejected`, `test_granting_needs_a_csrf_token`, `test_upload_needs_a_csrf_token` | Done |

| S-05 | Clickjacking | `X-Frame-Options: DENY` | `curl.exe -I` check | Done |

| S-06 | No second factor | Not built | none | Accepted (A-5) |

| S-07 | Demo accounts and password are public | Required by the brief; throwaway password, fake data only | none | Accepted (A-6) |

| S-08 | Injected scripts, framing, or unsafe browser capabilities | A site-wide Content-Security-Policy, Permissions-Policy, and same-origin resource policy constrain browser behavior; templates use an external stylesheet | `test_every_response_has_security_headers`, `test_pages_have_no_inline_script_or_style` | Local pass; CI pending for Day 6 changes |



## 5. Uploads and stored content



| ID | Threat | Defence | Test | Status |

|---|---|---|---|---|

| F-01 | Path traversal or tricks in filenames | Storage key is random and server-made; the original name is metadata only, cleaned | `test_file_names_cannot_escape_or_inject_headers`, `test_uploaded_path_name_is_stored_as_plain_name` | Done |

| F-02 | Fake type (an executable renamed `.pdf`) | Allow-list of PDF, DOCX, XLSX, PPTX; reject bad signatures and malformed Office archives | `test_executable_renamed_to_pdf_is_rejected`, `test_zip_that_is_not_an_office_file_is_rejected` | Done |

| F-03 | Zip bomb inside DOCX, XLSX or PPTX (they are zip files) | Per-file cap plus archive entry and uncompressed-size limits | `test_zip_bomb_is_rejected`, `test_archive_with_too_many_entries_is_rejected`, `test_archive_that_unpacks_too_large_is_rejected` | Done |

| F-04 | Active content (HTML, SVG, scripts) served inline | Download only as an attachment, `nosniff`, no inline rendering | `test_download_is_a_safe_attachment` | Done |

| F-05 | Header injection through the filename | Sanitize stored display names before constructing `Content-Disposition` | `test_file_names_cannot_escape_or_inject_headers`, `test_download_is_a_safe_attachment` | Done |

| F-06 | Stored XSS through titles or categories | Template auto-escaping; test with a script payload | `test_titles_are_escaped_in_pages` | Done |

| F-07 | Uploaded files lost on redeploy (host filesystem is ephemeral) | Store file bytes in PostgreSQL, not on disk | `test_owner_can_upload_a_pdf` (DB round-trip; no process-restart test yet) | DB-backed storage passes locally/in CI; process-restart test not present |

| F-08 | Malware inside an allowed file type | No antivirus scanning | none | Accepted (A-4) |

| F-09 | Disk or database exhaustion through uploads | Per-file cap and declared total multipart size are checked; missing content length relies on streaming file limits and host/server request limits; no per-user quota | `test_oversized_file_is_rejected`, `test_declared_oversized_multipart_is_rejected` | Local pass; CI pending for Day 6 changes; per-user quota accepted |
| F-10 | Stored file bytes are altered after upload | Store a cryptographic hash and verify the stored bytes before every download; reject and audit integrity failures | `test_altered_file_bytes_are_detected` | Done |



## 6. AI suggestions



| ID | Threat | Defence | Test | Status |

|---|---|---|---|---|

| I-01 | Text inside a document tells the assistant to widen access | Rule-based suggestions are metadata-only and read-only; the owner must explicitly accept any proposal | `test_engine_cannot_write_or_read_file_contents`, `test_document_title_cannot_steer_suggestions`, `test_requesting_suggestions_creates_no_grants` | Local pass; CI pending for Day 6 changes |

| I-02 | Document contents leave the system | Suggestions use local rules over metadata and existing grants; no external model or network call is used | `test_engine_cannot_write_or_read_file_contents` | Local pass; CI pending for Day 6 changes |

| I-03 | Replaying or swapping a suggestion | Acceptance is limited to a pending suggestion for the gated document, and a decision is single-use | `test_suggestion_id_from_another_document_cannot_be_used`, `test_suggestion_can_be_decided_only_once` | Local pass; CI pending for Day 6 changes |

| I-04 | Suggesting people outside the organisation | Candidates must be active users already granted access to similar documents owned by the same person; admins and current grantees are excluded | `test_engine_skips_admins_existing_grantees_and_disabled_users` | Local pass; CI pending for Day 6 changes |

| I-05 | Suggestion and decision not recorded | Suggestion and accept/reject decisions are audited; grant and decision share a transaction | `test_requesting_suggestions_creates_no_grants`, `test_accepting_suggestion_creates_one_audited_grant`, `test_dismissing_suggestion_is_audited_and_grants_nothing`, `test_missing_decision_audit_means_no_grant` | Local pass; CI pending for Day 6 changes |



## 7. Platform, configuration and supply chain



| ID | Threat | Defence | Test | Status |

|---|---|---|---|---|

| P-01 | Secrets in the repository | `.env` ignored; GitHub secret scanning and push protection | repository settings | Done (confirm both are on) |

| P-02 | Debug pages leak code and settings | `DEBUG` defaults to false; set `false` on the host | `check --deploy` | Done |

| P-03 | Weak or default `SECRET_KEY` | App refuses to start with a short or `django-insecure` key when `DEBUG` is off | startup check | Done |

| P-04 | Silent fallback to SQLite | PostgreSQL URL required; guard test | `test_runs_on_postgresql` | Done |

| P-05 | HTTP downgrade or redirect loop behind the proxy | HTTPS redirect, proxy header, HSTS of one hour | `curl.exe -I` | Done (HSTS short: Accepted A-8) |

| P-06 | Host header attacks | `ALLOWED_HOSTS` comes from the environment | settings check | Done |

| P-07 | Vulnerable or invented dependencies | CI runs Bandit, pip-audit, and Semgrep scanners | security workflow | Local configuration; first CI scan pending |

| P-08 | Hosted database URL leaks | Used only in my local shell, never committed; rotate it if exposed | none | Done (process) |

| P-09 | Error pages leak internals | Custom error page does not expose debug details | `test_404_page_has_no_debug_information` | Done |



## Accepted risks



| ID | Risk | Why I accept it |

|---|---|---|

| A-1 | A download already streaming may finish after access is revoked | Checking on every chunk adds complexity; the window is one response. Revocation applies to the very next request. |

| A-2 | Someone with the database owner account and the audit key could rewrite the whole chain | A saved Git anchor detects changes to history covered by that anchor; it does not prevent tampering or cover changes after the last anchor. I cannot make this impossible on a managed host. |

| A-3 | Free host: database expires after 30 days, has no backups, the service sleeps when idle | Demo environment with fake data. Expiry date is in the README. |

| A-4 | No antivirus or macro scanning | Out of scope for one week. Mitigated by type allow-list, attachment-only downloads, no inline rendering. |

| A-5 | No multi-factor sign-in | Out of scope. Mitigated by throttling and 12-character minimum. |

| A-6 | Demo credentials are public | The brief asks for them. Throwaway password, fake data. |

| A-7 | Login and anonymous-probe rate-limit counters live in one server process; an attacker can rotate addresses | Fine for one instance; use a shared cache and network-level controls to scale or resist address rotation. |

| A-8 | HSTS is only one hour, no preload | Raise it only after HTTPS has been confirmed everywhere. |

| A-9 | One global audit chain serialises writes | Fine at demo volume; writes wait on the single chain-head lock. |

| A-10 | Admin sees document titles in the activity view | Needed to investigate; titles can be sensitive, so contents are never shown. |

| AR-11 | The grant form reveals whether a username exists inside the organisation | Accepted for this release; unknown and disabled users receive the same generic response. |

| AR-12 | Concurrent edits are last-write-wins | Accepted for this release; edit leases and conflict detection are not built. |

| AR-13 | Deleted documents and their file bytes remain in the trash/database | Accepted for this release; retention cleanup must be performed manually. |

| AR-14 | Replacing a file overwrites its previous bytes | Accepted for this release; the audit log retains hashes, not old file contents. |

| AR-15 | The database owner can drop the append-only trigger; this host has one database account | Accepted operational limit: the trigger protects against ordinary UPDATE/DELETE statements, not the table owner or a disabled/dropped trigger. |

| AR-16 | `AUDIT_HMAC_KEY` is lost | Without the original key, the chain cannot be verified; keep the key in the host's secret settings and a managed password store. |

| AR-17 | The external daily anchor is stale | The anchor only witnesses the chain as of the last successful run of the anchor script. |

| AR-18 | Documents owned by a disabled user remain in the vault | Access is disabled with the account; documents remain stored and cannot currently be reassigned through the website. |

| AR-19 | Cross-site request forgery checks run before document authorization on unsafe methods | Requests without a valid CSRF token can receive the same 403 before the document gate runs; this does not distinguish real from invented document ids. |



## Deliberately not built



- Folder permissions (a folder grant is how "one file" turns into forty).

- Public share links.

- Search inside file contents (a search index is a second copy of the document).

- Single sign-on.

- Multi-company tenancy. `[confirm]`

- Live co-editing. Edit leases: `[decide on Day 4]`



## Day 1 checks before I commit this file



Run these, and change any "Done" above that fails:



```powershell

pytest

$env:DEBUG = "false"; python manage.py check --deploy; Remove-Item Env:DEBUG

curl.exe -I https://trustvault-app-1tp1.onrender.com/health/

curl.exe -I https://trustvault-app-1tp1.onrender.com/admin/

```



- `pytest` passes, including the admin test and the PostgreSQL guard test.

- The `/admin/` request returns 404.

- Security headers appear on `/health/`.

- GitHub shows secret scanning and push protection as on.



Refused edits by someone who can read the document show “Not found”, not “Forbidden”. It’s one uniform behaviour, and the UI hides buttons the user can’t use.

Application ORM protections reject audit-row instance and queryset updates/deletes, including operations through the base manager. Direct privileged SQL still needs database-level privileges or a trigger.

Anonymous document URL probes are rate-limited after 30 requests per address per 10-minute window; one summary audit event is recorded when the limit is crossed.

Seed grants are not audited; real grants go through the audited service.

Login and probe throttling counters live in one server process. The client address is taken from the last X-Forwarded-For entry under the host proxy trust assumption; rotating addresses can evade address-based limits.

## Security-drill verification

The full suite passed locally (170 tests) with `pytest -q`. Django checks and
migration-state checks also passed. GitHub CI passed on commit `d2c845a`, which
includes the verifier, ORM, and guard hardening changes.

- Drill 6 — `test_no_audit_row_means_no_stored_document` now passes: the failed
  upload transaction leaves no document or file row.
- File-integrity regression — `test_altered_file_bytes_are_detected` now passes: tampered bytes
  raise an integrity error and produce an integrity-failure audit event.
- U-04 now has a direct download test that makes the download authorization
  audit write fail; local upload, protected-view and download checks pass.
- U-08's server-time regression test passes locally and is included in the
  successful CI run for `d2c845a`.
- F-07 has no cross-process persistence test yet; uploaded bytes are stored in
  PostgreSQL and the upload/download round-trip is covered.

## Known Limitations

- **ZIP archive checks:** ZIP checks use sizes declared in the archive. The server does not unpack the file.
- **Antivirus:** No antivirus scanning is implemented in this release. This limitation is accepted.
- **Missing content-length header:** The upload handler enforces a per-file limit while parsing, but a client can still send a multipart request body larger than 25 MB without a length header. Total request size then relies on host and server limits.
- **Database file storage:** Uploaded files are stored in the database. A database backup or an administrator with sufficient database access can read their contents. Encryption at rest is not implemented in this release; this limitation is accepted.
- **Search response differences:** Search results stay within the caller's permissions, but the caller can distinguish “no matches” from an invalid search. This is accepted.
- **Owner usernames:** A viewer can see the username of the owner on documents they can already read. This is accepted because it helps viewers identify and contact the owner.
- **Seed grants:** Seed grants are not audited. Real grants made through the application use the audited grant service.
- **Assistant:** Suggestions are generated by deterministic local rules, not a language model. They use titles, categories, and existing grants; no document bytes are read and no external AI service is called.
- **Login and probe throttling:** Counters live in one server process. Address-based throttling can be evaded by rotating addresses; up to 30 anonymous document probes per address per 10-minute window are individually audited, after which requests are throttled and one summary event is recorded per window.
- **CSRF and authorization order:** For unsafe requests, CSRF middleware can reject a request with 403 before document authorization runs. This response is the same for existing and invented document ids.
- **Content Security Policy:** The site-wide policy blocks scripts and inline styles. A future feature requiring JavaScript needs a deliberate policy and test change. Download responses retain their own stricter sandbox policy.
