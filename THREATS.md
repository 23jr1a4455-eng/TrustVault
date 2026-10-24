# THREATS.md



Status updated 2026-10-24. I update it as implementation and verification progress.

Sources: my Threat Dragon model (`docs/threat-model/`), the Spec Kit plan, and my own list.



> **\*\*Draft.\*\*** Rewrite each "Defence" in your own words, and keep a status of

> **\*\*Done\*\*** only where you can point at code, a test or a setting.



**\*\*Status key:\*\*** **\*\*Done\*\*** = built and passed locally and in CI. **\*\*Local pass; CI pending\*\*** = verified in the current worktree, but not yet in a CI run for that revision. **\*\*Planned Dn\*\*** = designed, to be built on day *\*n\**. **\*\*Accepted\*\*** = I know about it, and the reason is in "Accepted risks" below.



## 1. Authorisation (the gate)



| ID | Threat | Defence | Test | Status |

|---|---|---|---|---|

| A-01 | Guessing document IDs (`/documents/42` then 43) | Each document operation checks the current user's grant through `authorize`; UUIDs make IDs harder to guess, and unreadable documents return 404 | `test_other_user_gets_404_for_unreadable_document`, `test_strangers_cannot_download` | Done |

| A-02 | A new route that forgets the check | A test walks the URL table and fails if a route has no declared access guard | `test_every_route_declares_how_it_is_protected` | Done |

| A-03 | Viewer calls owner-only actions directly (grant, delete, upload) | The server checks the specific permission required by each action; hiding a button is not treated as authorization | `test_only_the_owner_can_manage_access`, `test_viewers_and_admins_cannot_upload`, delete authorization tests | Done |

| A-04 | Owner A reads or edits owner B's document | The authorization decision checks ownership and grants against the specific document on every request | `test_owner_cannot_access_other_owners_document` | Done |

| A-05 | 403 vs 404, or response differences, reveal that a file exists | Requests for inaccessible and nonexistent documents receive the same not-found response | `test_nonexistent_and_unreadable_look_identical`, `test_404_responses_are_generic_and_match_for_unavailable_documents` | Local pass; CI pending for the latest 404 regression |

| A-06 | Mass assignment (`role`, `owner`, `is_staff` in a request body) | Edit forms accept document fields only; account roles are not editable through web routes | `test_edit_ignores_owner_field`, `test_the_website_has_no_way_to_change_roles` | Done |

| A-07 | Side doors: preview, thumbnail, versions, export, HEAD, OPTIONS, trailing slash, encoded paths | Every document endpoint that exists today runs through the document gate; preview and export do not exist yet | `test_all_gated_routes_deny_and_conceal_documents_for_every_method` (implemented routes only) | Local pass; CI pending for the latest 404 regression; preview/export not built |

| A-08 | Search, autocomplete, counts or pagination leak titles or existence | Search filters by current access before it counts or paginates results | `test_search_only_finds_what_the_person_may_read`, `test_counts_never_include_hidden_documents`, `test_pagination_stays_inside_permissions` | Done |

| A-09 | Admin grants themselves access, takes ownership or silently makes another admin | Admin accounts cannot open document content or change roles on the site, and visits to admin pages are logged; ownership transfer is not available | `test_the_admin_still_cannot_open_documents`, `test_the_website_has_no_way_to_change_roles`, `test_administrators_looking_at_the_log_are_themselves_recorded` | Done |

| A-10 | Open redirect through `?next=` after login | Login accepts a return address only when it resolves to this site | `test_login_rejects_external_next_url` | Done |

| A-11 | Public Django admin bypasses the gate and the audit | The Django admin application is not installed or exposed by the URL configuration | `test_django_admin_is_not_exposed` | Done |

| A-12 | Disabling a user leaves an existing session usable | Disabling an account removes its active sessions so they cannot keep working | `test_disabling_a_user_ends_every_session_at_once` | Done |

| G-01 | A guessed grant id revokes someone else's access | A revoke request looks up the grant using both its id and the document id | `test_a_grant_id_from_another_document_cannot_be_revoked` | Done |

| G-02 | An editor shares the document | Only the document owner passes the share/access-management gate | `test_only_the_owner_can_manage_access` | Done |

| G-03 | A grant is created without its audit row | The grant and its audit event commit together or both roll back | `test_no_audit_row_means_no_grant` | Done |



## 2. Revocation and deletion



| ID | Threat | Defence | Test | Status |

|---|---|---|---|---|

| R-01 | Revoked user replays an old request, link or session | Authorization reads active grants from the database for each request, so revocation affects the next document, download, and search request | `test_revoking_takes_effect_on_the_next_request`, `test_revoked_user_cannot_download_on_the_next_request`, `test_revoked_expired_and_deleted_documents_leave_search_at_once` | Done |

| R-02 | Disabled user keeps an existing session | Inactive accounts are rejected during authentication, and disabling also deletes their stored sessions | `test_disabled_user_session_stops_working`, `test_disabling_a_user_ends_every_session_at_once` | Done |

| R-03 | A download already streaming finishes after revoke | Permission is checked when the download starts, not repeatedly while bytes are streaming | none | Accepted (A-1) |

| R-04 | Revoked editor saves after access is revoked | Saving checks the editor's current grant again; edit leases were cut from scope and are not implemented | `test_a_revoked_editor_cannot_save` | Done for revoked-editor save; leases cut/not built |

| R-05 | Browser or proxy caches a document after logout or revoke | Document pages and downloads send cache headers that tell clients not to retain them | `test_document_pages_are_not_cacheable` | Done |

| R-06 | Restoring a deleted document revives old grants | Deletion revokes the document's grants, and restoration leaves those grants revoked | `test_deleting_revokes_every_grant_and_restoring_does_not_bring_them_back` | Done |



## 3. Audit trail



| ID | Threat | Defence | Test | Status |

|---|---|---|---|---|

| U-01 | Audit rows edited or deleted (app bug, SQL injection, insider) | Both the model layer and a PostgreSQL trigger block updates and deletes to audit records | `test_the_model_refuses_bulk_changes`, `test_the_database_itself_refuses_updates_and_deletes` | Done |

| U-02 | The whole hash chain rewritten | Each chained event uses a keyed HMAC; verification checks the chain, and committed Git anchors expose rewrites of witnessed history | `test_an_edited_row_is_detected`, `test_an_attacker_with_the_key_is_caught_only_by_the_anchors` | Done |

| U-03 | Refused attempts lost when the 404 rolls back the transaction | The denial event is saved before the view returns 404, outside a request-wide rollback | `test_denied_request_leaves_audit_row` | Done |

| U-04 | Audit write fails but an upload or download still succeeds, or a document persists without its audit row | If recording the action fails, the transaction must not leave the upload behind or return protected content | `test_no_audit_row_means_no_stored_document`, `test_audit_failure_blocks_access`, `test_download_fails_if_audit_write_fails` | Done |

| U-05 | Log injection (newlines or huge strings in titles or usernames) | Audit values are cleaned and capped before storage, then escaped when displayed | `test_log_values_cannot_forge_lines_or_grow_without_limit` | Done |

| U-06 | Two writers fork the chain | Writers lock the chain head before appending so concurrent writes serialize | `test_concurrent_writers_never_fork_the_chain` | Done |

| U-07 | Audit flooding to hide an attack or fill the disk | Login and anonymous document probes are capped; after the probe threshold, requests get 429 and one summary event records the window | `test_login_is_rate_limited`, `test_anonymous_probing_is_slowed_down_and_logged_once` | Local pass; CI pending for Day 6 changes |

| U-08 | Wrong or forged timestamps | Audit timestamps are assigned by the server clock rather than copied from request data | `test_audit_uses_server_time` | Done |

| U-10 | Database owner with the audit key rewrites the complete chain | A Git-held anchor gives an outside reference for detecting changes to the chain up to that point | `test_an_attacker_with_the_key_is_caught_only_by_the_anchors` | Done |

| U-11 | Rows written before chain creation are not tamper-evident | Verification reports legacy rows separately instead of claiming they have chain protection | `test_rows_from_before_the_chain_are_counted_not_failed` | Done |

| U-09 | Sensitive data copied into audit or host logs | Audit records keep action metadata rather than document bytes; titles are kept out of server logs | review in `docs/` | Planned D5 |



## 4. Authentication and sessions



| ID | Threat | Defence | Test | Status |

|---|---|---|---|---|

| S-01 | Brute force or credential stuffing | Login attempts are throttled by username and address, and password rules require at least 12 characters | `test_login_is_rate_limited` | Done |

| S-02 | User enumeration through login messages or timing | The login form gives the same error for unknown users and other failed sign-ins | `test_login_error_is_identical_for_every_kind_of_failure` | Done |

| S-03 | Cookie theft, fixation, long-lived sessions | Session cookies use the configured security flags and idle expiry; login rotates the session key, and logout removes the session | settings check, `test_logout_ends_the_session` | Done |

| S-04 | CSRF on grant, revoke, delete | Django's CSRF middleware protects state-changing forms, including grant and upload requests | `test_post_without_csrf_token_is_rejected`, `test_granting_needs_a_csrf_token`, `test_upload_needs_a_csrf_token` | Done |

| S-05 | Clickjacking | Responses tell browsers not to render TrustVault inside a frame | `curl.exe -I` check | Done |

| S-06 | No second factor | Not built | none | Accepted (A-5) |

| S-07 | Demo accounts and password are public | Required by the brief; throwaway password, fake data only | none | Accepted (A-6) |

| S-08 | Injected scripts, framing, or unsafe browser capabilities | Browser headers restrict scripts, framing, and device access; page templates keep styles in external files | `test_every_response_has_security_headers`, `test_pages_have_no_inline_script_or_style` | Local pass; CI pending for Day 6 changes |



## 5. Uploads and stored content



| ID | Threat | Defence | Test | Status |

|---|---|---|---|---|

| F-01 | Path traversal or tricks in filenames | The app chooses its own storage key and keeps a cleaned client filename only as display metadata | `test_file_names_cannot_escape_or_inject_headers`, `test_uploaded_path_name_is_stored_as_plain_name` | Done |

| F-02 | Fake type (an executable renamed `.pdf`) | Upload validation checks the supported formats' signatures and rejects malformed Office archives, not just the extension | `test_executable_renamed_to_pdf_is_rejected`, `test_zip_that_is_not_an_office_file_is_rejected` | Done |

| F-03 | Zip bomb inside DOCX, XLSX or PPTX (they are zip files) | Uploads have a byte limit, and Office archives are rejected when their declared entry count or expanded size exceeds limits | `test_zip_bomb_is_rejected`, `test_archive_with_too_many_entries_is_rejected`, `test_archive_that_unpacks_too_large_is_rejected` | Done |

| F-04 | Active content (HTML, SVG, scripts) served inline | Files are delivered as attachments with a safe content type and `nosniff`, rather than rendered in the page | `test_download_is_a_safe_attachment` | Done |

| F-05 | Header injection through the filename | The filename is normalized before it is placed in the download response header | `test_file_names_cannot_escape_or_inject_headers`, `test_download_is_a_safe_attachment` | Done |

| F-06 | Stored XSS through titles or categories | Django templates escape document metadata before showing it as HTML | `test_titles_are_escaped_in_pages` | Done |

| F-07 | Uploaded files lost on redeploy (host filesystem is ephemeral) | File bytes are stored in PostgreSQL so they are not tied to an instance's local disk | `test_owner_can_upload_a_pdf` (database round-trip; no process-restart test yet) | DB-backed storage passes locally/in CI; process-restart test not present |

| F-08 | Malware inside an allowed file type | No antivirus scanning | none | Accepted (A-4) |

| F-09 | Disk or database exhaustion through uploads | The upload handler caps file bytes and checks declared multipart size; requests without a length header still depend on host/server request limits, and there is no user quota | `test_oversized_file_is_rejected`, `test_declared_oversized_multipart_is_rejected` | Local pass; CI pending for Day 6 changes; per-user quota accepted |
| F-10 | Stored file bytes are altered after upload | The app saves a hash at upload and checks it against the database bytes before sending a download | `test_altered_file_bytes_are_detected` | Done |



## 6. AI suggestions



| ID | Threat | Defence | Test | Status |

|---|---|---|---|---|

| I-01 | Text inside a document tells the assistant to widen access | Suggestions come from local rules over metadata; creating a suggestion cannot grant access, and only the owner can approve one | `test_engine_cannot_write_or_read_file_contents`, `test_document_title_cannot_steer_suggestions`, `test_requesting_suggestions_creates_no_grants` | Local pass; CI pending for Day 6 changes |

| I-02 | Document contents leave the system | The suggestion engine uses titles, categories, and existing grants only; it has no file-content or network access | `test_engine_cannot_write_or_read_file_contents` | Local pass; CI pending for Day 6 changes |

| I-03 | Replaying or swapping a suggestion | An approval must refer to a pending suggestion belonging to this document; a decided suggestion cannot be reused | `test_suggestion_id_from_another_document_cannot_be_used`, `test_suggestion_can_be_decided_only_once` | Local pass; CI pending for Day 6 changes |

| I-04 | Suggesting people outside the organisation | The engine considers active users who already have grants on similar documents by this owner, while excluding admins and anyone already granted this document | `test_engine_skips_admins_existing_grantees_and_disabled_users` | Local pass; CI pending for Day 6 changes |

| I-05 | Suggestion and decision not recorded | Suggestion creation and owner decisions write audit events; approval rolls back if its grant or audit write fails | `test_requesting_suggestions_creates_no_grants`, `test_accepting_suggestion_creates_one_audited_grant`, `test_dismissing_suggestion_is_audited_and_grants_nothing`, `test_missing_decision_audit_means_no_grant` | Local pass; CI pending for Day 6 changes |



## 7. Platform, configuration and supply chain



| ID | Threat | Defence | Test | Status |

|---|---|---|---|---|

| P-01 | Secrets in the repository | `.env` ignored; GitHub secret scanning and push protection | repository settings | Done (confirm both are on) |

| P-02 | Debug pages leak code and settings | Production settings keep Django debug mode off, and deployment checks flag unsafe settings | `check --deploy` | Done |

| P-03 | Weak or default `SECRET_KEY` | In production mode, startup stops if the secret key is missing, too short, or Django's insecure default | startup check | Done |

| P-04 | Silent fallback to SQLite | Configuration requires a PostgreSQL database URL rather than quietly using SQLite | `test_runs_on_postgresql` | Done |

| P-05 | HTTP downgrade or redirect loop behind the proxy | Django honors the trusted proxy's HTTPS signal, redirects insecure requests, and sends a short HSTS policy | `curl.exe -I` | Done (HSTS short: Accepted A-8) |

| P-06 | Host header attacks | Only hostnames configured in the environment are accepted by Django | settings check | Done |

| P-07 | Vulnerable or invented dependencies | The security workflow is configured to run Bandit, pip-audit, and Semgrep; its first result is still pending | security workflow | Local configuration; first CI scan pending |

| P-08 | Hosted database URL leaks | Used only in my local shell, never committed; rotate it if exposed | none | Done (process) |

| P-09 | Error pages leak internals | Middleware replaces 404 bodies with a generic message, including when debug mode would otherwise render diagnostic details | `test_404_responses_are_generic_and_match_for_unavailable_documents` | Local pass; CI pending for the latest 404 regression |



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



## Release checks



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

The current worktree passes the full local suite (200 tests) with `pytest -q`.
Django's system check and migration-state check also pass. CI has not run for
the current uncommitted changes; the earlier CI result for `d2c845a` does not
cover the Day 6 changes or the latest 404-response fix.

- The ten Day 6 remove-one-check mutations each made the corresponding focused
  test fail; all mutations were restored before the full suite was run.
- `test_all_gated_routes_deny_and_conceal_documents_for_every_method` now
  checks denied and nonexistent document responses for three ungranted roles
  across all HTTP methods, including with `DEBUG=True`.
- `test_404_responses_are_generic_and_match_for_unavailable_documents`
  verifies that debug-mode 404 pages contain no debug details and that
  inaccessible and nonexistent documents have the same response body.
- The automated HTTP attack script was not run against a server; its results
  are not claimed as verified here.

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
