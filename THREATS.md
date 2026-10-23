# THREATS.md



Status at the end of Day 1 (2026-10-19). I update it every day.

Sources: my Threat Dragon model (`docs/threat-model/`), the Spec Kit plan, and my own list.



> **\*\*Draft.\*\*** Rewrite each "Defence" in your own words, and keep a status of

> **\*\*Done\*\*** only where you can point at code, a test or a setting.



**\*\*Status key:\*\*** **\*\*Done\*\*** = built and I can show it. **\*\*Planned Dn\*\*** = designed, to be built on day *\*n\**. **\*\*Accepted\*\*** = I know about it, and the reason is in "Accepted risks" below.



## 1. Authorisation (the gate)



| ID | Threat | Defence | Test | Status |

|---|---|---|---|---|

| A-01 | Guessing document IDs (`/documents/42` then 43) | One `authorize(user, doc, action)` gate; unguessable UUID ids; 404 for anything unreadable | `test_other_user_gets_404_for_unreadable_document` | Planned D2 |

| A-02 | A new route that forgets the check | Route-inventory test lists every URL and fails unless it calls the gate or is on a short public allow-list | `test_every_route_is_guarded_or_allowlisted` | Planned D2 |

| A-03 | Viewer calls owner-only actions directly (grant, delete, upload) | Each action needs its own permission, not only a role | `test_viewer_cannot_grant_delete_or_upload` | Planned D2 |

| A-04 | Owner A reads or edits owner B's document | Ownership checked per document | `test_owner_cannot_access_other_owners_document` | Planned D2 |

| A-05 | 403 vs 404, or response differences, reveal that a file exists | Same status and body for "absent" and "not yours" | `test_nonexistent_and_unreadable_look_identical` | Planned D2 |

| A-06 | Mass assignment (`role`, `owner`, `is_staff` in a request body) | Explicit form fields; role changed only in the admin user view | `test_profile_update_ignores_role_and_owner` | Planned D2 |

| A-07 | Side doors: preview, thumbnail, versions, export, HEAD, OPTIONS, trailing slash, encoded paths | Every one goes through the gate; parametrised test over methods and path variants | `test_all_document_routes_deny_ungranted_user` | Planned D3 to D4 |

| A-08 | Search, autocomplete, counts or pagination leak titles or existence | Permission join inside the SQL query, never filtering afterwards | `test_search_returns_only_granted_documents`, `test_counts_do_not_leak` | Planned D4 |

| A-09 | Admin grants themselves access, takes ownership or silently makes another admin | Admin has no content access; ownership transfer not built; every admin action audited and flagged | `test_admin_cannot_read_ungranted_document`, `test_admin_actions_are_audited` | Planned D2 / D5 |

| A-10 | Open redirect through `?next=` after login | Only same-host redirect targets are allowed | `test_login_rejects_external_next_url` | Planned D2 |

| A-11 | Public Django admin bypasses the gate and the audit | Admin app removed from `INSTALLED_APPS` and not routed | `test_django_admin_is_not_exposed` | Done |



## 2. Revocation and deletion



| ID | Threat | Defence | Test | Status |

|---|---|---|---|---|

| R-01 | Revoked user replays an old request, link or session | Grants read from the database on every request; no permissions in tokens or sessions | `test_revoked_user_gets_404_on_next_request` | Planned D4 |

| R-02 | Disabled user keeps an existing session | `is_active=False` is refused on the next request; sessions deleted on disable | `test_disabled_user_session_stops_working` | Planned D2 |

| R-03 | A download already streaming finishes after revoke | Checked once at the start of the response | none | Accepted (A-1) |

| R-04 | Edit lease or stale save after revoke | Save re-checks the current grant; revoke ends the lease (only if leases are built) | `test_revoked_editor_cannot_save` | Planned D4 |

| R-05 | Browser or proxy caches a document after logout or revoke | `Cache-Control: no-store` on document and download responses | `test_document_responses_are_not_cacheable` | Planned D3 |

| R-06 | Restoring a deleted document revives old grants | Soft delete hides it from everyone; restore does not bring grants back | `test_restore_does_not_revive_grants` | Planned D4 |



## 3. Audit trail



| ID | Threat | Defence | Test | Status |

|---|---|---|---|---|

| U-01 | Audit rows edited or deleted (app bug, SQL injection, insider) | Insert-only database role if the host allows it; trigger rejecting UPDATE and DELETE | `test_audit_update_and_delete_fail` | Planned D5 |

| U-02 | The whole hash chain rewritten | Keyed hash (HMAC) with the key kept outside the database; `verify_audit` command; daily copy of the last hash outside the app | `test_tampered_row_breaks_chain_verification` | Planned D5 |

| U-03 | Refused attempts lost when the 404 rolls back the transaction | Denial row committed on its own before the 404 is returned. **\*\*Suspected from plan review, not yet proven\*\*** | `test_denied_request_leaves_audit_row` | Planned D2 |

| U-04 | Audit write fails but an upload or download still succeeds, or a document persists without its audit row | Fail closed: audit failure must not leave a stored document or return protected content; coordinate database and file-storage rollback/cleanup | `test_download_fails_if_audit_write_fails`, `test_no_audit_row_means_no_stored_document` | Open — fix and verify |

| U-05 | Log injection (newlines or huge strings in titles or usernames) | Structured fields, length caps, escaped on display | `test_audit_fields_are_escaped_and_capped` | Planned D5 |

| U-06 | Two writers fork the chain | Row lock on the chain head | `test_concurrent_appends_keep_one_chain` | Planned D5 |

| U-07 | Audit flooding to hide an attack or fill the disk | Rate limits on login and write routes; size caps | `test_login_is_rate_limited` | Planned D2 |

| U-08 | Wrong or forged timestamps | Server and database UTC time only, never client time | `test_audit_uses_server_time` | Planned D3 |

| U-09 | Sensitive data copied into audit or host logs | Log ids and actions, never file contents; titles kept out of server logs | review in `docs/` | Planned D5 |



## 4. Authentication and sessions



| ID | Threat | Defence | Test | Status |

|---|---|---|---|---|

| S-01 | Brute force or credential stuffing | Login throttling per account and per address; passwords at least 12 characters | `test_login_is_rate_limited` | Planned D2 |

| S-02 | User enumeration through login messages or timing | One generic error message | `test_login_error_is_identical` | Planned D2 |

| S-03 | Cookie theft, fixation, long-lived sessions | HttpOnly, Secure, SameSite=Lax cookies; one-hour idle timeout; Django cycles the key on login; logout deletes the session | settings check | Done (flags and timeout); logout test Planned D2 |

| S-04 | CSRF on grant, revoke, delete | `CsrfViewMiddleware` on; token required on POST | `test_post_without_csrf_token_is_rejected` | Done (middleware); test Planned D2 |

| S-05 | Clickjacking | `X-Frame-Options: DENY` | `curl.exe -I` check | Done |

| S-06 | No second factor | Not built | none | Accepted (A-5) |

| S-07 | Demo accounts and password are public | Required by the brief; throwaway password, fake data only | none | Accepted (A-6) |



## 5. Uploads and stored content



| ID | Threat | Defence | Test | Status |

|---|---|---|---|---|

| F-01 | Path traversal or tricks in filenames | Storage key is random and server-made; the original name is metadata only, cleaned | `test_upload_with_path_traversal_name_is_safe` | Planned D3 |

| F-02 | Fake type (an executable renamed `.pdf`) | Allow-list of PDF, DOCX, XLSX, PPTX plus a check of the real file signature | `test_upload_rejects_wrong_signature` | Planned D3 |

| F-03 | Zip bomb inside DOCX, XLSX or PPTX (they are zip files) | 25 MB cap; limits on entry count, uncompressed size and nesting | `test_upload_rejects_zip_bomb` | Planned D3 |

| F-04 | Active content (HTML, SVG, scripts) served inline | Download only as an attachment, `nosniff`, no inline rendering | `test_download_is_attachment_with_nosniff` | Planned D3 |

| F-05 | Header injection through the filename | Safe filename encoding in `Content-Disposition` | `test_filename_header_injection` | Planned D3 |

| F-06 | Stored XSS through titles or categories | Template auto-escaping; test with a script payload | `test_titles_are_escaped_in_pages` | Planned D3 |

| F-07 | Uploaded files lost on redeploy (host filesystem is ephemeral) | Store file bytes in PostgreSQL, not on disk. **\*\*Decision to confirm\*\*** | `test_uploaded_file_survives_new_process` | Planned D3 |

| F-08 | Malware inside an allowed file type | No antivirus scanning | none | Accepted (A-4) |

| F-09 | Disk or database exhaustion through uploads | Size cap per file; no per-user quota yet | `test_upload_rejects_oversized_file` | Planned D3; quota Accepted |
| F-10 | Stored file bytes are altered after upload | Store a cryptographic hash and verify the stored bytes before every download; reject and audit integrity failures | `test_altered_file_bytes_are_detected` | Open — fix and verify |



## 6. AI suggestions



| ID | Threat | Defence | Test | Status |

|---|---|---|---|---|

| I-01 | Text inside a document tells the AI to widen access (prompt injection) | The AI module has no way to create grants; it only returns *\*pending\** suggestions; only the owner's confirmation creates one | `test_ai_module_cannot_create_grants` | Planned D6 |

| I-02 | Document contents leave the system | Metadata only (title, category, team); no external AI provider in this release | `test_ai_prompt_contains_no_file_contents` | Planned D6 |

| I-03 | Replaying or swapping a suggestion | Suggestion tied to one document and owner, single use; permission re-checked on confirm | `test_confirm_rechecks_owner_and_document` | Planned D6 |

| I-04 | Suggesting people outside the organisation | Only active existing users can be suggested | `test_suggestions_only_for_existing_users` | Planned D6 |

| I-05 | Suggestion and decision not recorded | Both written to the audit log | `test_ai_suggestion_and_decision_are_audited` | Planned D6 |



## 7. Platform, configuration and supply chain



| ID | Threat | Defence | Test | Status |

|---|---|---|---|---|

| P-01 | Secrets in the repository | `.env` ignored; GitHub secret scanning and push protection | repository settings | Done (confirm both are on) |

| P-02 | Debug pages leak code and settings | `DEBUG` defaults to false; set `false` on the host | `check --deploy` | Done |

| P-03 | Weak or default `SECRET_KEY` | App refuses to start with a short or `django-insecure` key when `DEBUG` is off | startup check | Done |

| P-04 | Silent fallback to SQLite | PostgreSQL URL required; guard test | `test_runs_on_postgresql` | Done |

| P-05 | HTTP downgrade or redirect loop behind the proxy | HTTPS redirect, proxy header, HSTS of one hour | `curl.exe -I` | Done (HSTS short: Accepted A-8) |

| P-06 | Host header attacks | `ALLOWED_HOSTS` comes from the environment | settings check | Done |

| P-07 | Vulnerable or invented dependencies | `pip-audit`, Dependabot alerts, check each AI-suggested package exists | CI step | Planned D6 |

| P-08 | Hosted database URL leaks | Used only in my local shell, never committed; rotate it if exposed | none | Done (process) |

| P-09 | Error pages leak internals | Custom 404 and 500 pages | `test_404_page_has_no_debug_info` | Planned D2 |



## Accepted risks



| ID | Risk | Why I accept it |

|---|---|---|

| A-1 | A download already streaming may finish after access is revoked | Checking on every chunk adds complexity; the window is one response. Revocation applies to the very next request. |

| A-2 | Someone with the database owner account and the audit key could rewrite the whole chain | Daily external copy of the last hash makes this detectable after the fact; I cannot make it impossible on a managed host. |

| A-3 | Free host: database expires after 30 days, has no backups, the service sleeps when idle | Demo environment with fake data. Expiry date is in the README. |

| A-4 | No antivirus or macro scanning | Out of scope for one week. Mitigated by type allow-list, attachment-only downloads, no inline rendering. |

| A-5 | No multi-factor sign-in | Out of scope. Mitigated by throttling and 12-character minimum. |

| A-6 | Demo credentials are public | The brief asks for them. Throwaway password, fake data. |

| A-7 | Rate-limit counters live in one server process | Fine for one instance; would need a shared store to scale. |

| A-8 | HSTS is only one hour, no preload | Raise it only after HTTPS has been confirmed everywhere. |

| A-9 | One global audit chain serialises writes | Fine at demo volume. |

| A-10 | Admin sees document titles in the activity view | Needed to investigate; titles can be sensitive, so contents are never shown. |



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

Audit rows are protected only in the model for now. Queryset updates and deletes still work until the database trigger on Day 5.

Anonymous requests to document URLs are audited, so someone could flood the log. Rate limiting is on Day 5.

Seed grants aren’t audited. Real grants go through the audited service on Day 4.

Login throttling counters live in one server process. The client address is the last X-Forwarded-For entry, which is the one your host’s proxy adds.

## Security-drill findings — open

These findings came from security drills and remain open until the fixes are implemented and verified locally and in CI.

- **Drill 6 — upload audit failure can leave a document stored.** Test: `test_no_audit_row_means_no_stored_document`. The audit service raises `RuntimeError`, but a document remains in the database. Ensure the database row, file storage, and audit write have coordinated failure handling and cleanup. Verify by rerunning the regression test and the full test suite.
- **Drill 8 — altered file bytes are not detected.** Test: `test_altered_file_bytes_are_detected`. Altering stored bytes did not raise the expected `RuntimeError`. Store a cryptographic hash and verify file bytes on every download. Verify by rerunning the regression test and the full test suite.

Do not change these findings to **Done** until the corresponding tests pass and the implementation has been reviewed.
