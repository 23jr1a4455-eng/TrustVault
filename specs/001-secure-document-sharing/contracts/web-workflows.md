# Web Workflow Contracts

TrustVault exposes server-rendered HTML workflows, not a public JSON API.
Every state-changing form uses POST and Django CSRF protection. Authentication
and session cookies carry identity only; the server reads current company
membership and grants for each decision. No route returns a public or signed
file URL.

## Response and Audit Rules

- Unreadable and nonexistent document identifiers return the same 404
  response.
- Every document action calls `authorize(user, document, action)` with current
  database state.
- Every authorization ALLOW or DENY is appended to the audit chain before the
  corresponding response. If required audit persistence fails, the operation
  fails closed.
- Successful writes return only after the state change and required audit
  entry commit.
- File responses stream through the application after authorization and audit
  commit. Use attachment disposition by default, `nosniff`, and private
  no-store caching.
- Validation errors preserve the form context, do not persist a document, and
  have a denied/failed audit event.

## Routes

| Method and path | Actor / required action | Contract |
|---|---|---|
| `GET, POST /login/` | Anonymous / authentication | Render sign-in form; POST validates credentials, rotates session identity, and does not place grants in session state. Record successful and refused authentication before responding. |
| `POST /logout/` | Signed-in member / logout | End the server-side session; CSRF required. |
| `GET, POST /invitations/<token>/accept/` | Invitee / invitation acceptance | Accept a valid one-time invitation; expired, revoked, reused, or invalid tokens do not create membership. |
| `GET /documents/` | Signed-in member / `search` | Search name, owner, category, and date within current readable grants only. Call `authorize(user, document, "read")` for each result before including it. Do not expose inaccessible metadata or counts. |
| `GET, POST /documents/upload/` | Owner / `upload` | Render and process upload form; validate type/content and 25 MB limit; store only under a generated private key; create owner grant and audit before success. |
| `GET /documents/<uuid>/` | Member / `read` | Return metadata only after authorization; otherwise 404 and denial audit. |
| `GET /documents/<uuid>/download/` | Member / `read` | Authorize and audit current access before opening/streaming private bytes; no direct storage URL. |
| `POST /documents/<uuid>/edit/` | Member / `edit` | Acquire an exclusive lease or show a waiting state; each attempt is authorized and audited. |
| `POST /documents/<uuid>/edit/heartbeat/` | Lease holder / `edit` | Renew only a current lease generation and current grant; expire after 15 minutes without activity. |
| `POST /documents/<uuid>/edit/save/` | Lease holder / `edit` | Recheck current grant and lease generation; validate replacement content; persist and audit, then release lease. Stale generations cannot save. |
| `POST /documents/<uuid>/edit/cancel/` | Lease holder / `edit` | Release the matching lease generation and audit. |
| `POST /documents/<uuid>/grants/` | Owner / `grant` | Grant read/edit to a named same-company member; admin status alone is not document permission. |
| `POST /documents/<uuid>/grants/<member_id>/revoke/` | Owner / `revoke` | Revoke the current grant; subsequent requests use the updated database state. |
| `POST /documents/<uuid>/organize/` | Owner / `organize` | Set company-scoped category and supported metadata; audit change. |
| `POST /documents/<uuid>/delete/` | Owner / `delete` | Mark unavailable and audit in a transaction; remove private bytes after commit with retryable cleanup. |
| `GET, POST /admin/members/` | Admin / member management | List members and invite allowed roles; never grants document access. |
| `POST /admin/members/<member_id>/deactivate/` | Admin / `deactivate_member` | Deactivate member and audit before responding. |
| `POST /admin/members/<member_id>/role/` | Admin / `change_role` | Assign owner/viewer; administrator role changes require a different admin; deny and audit self-change. |
| `GET /admin/activity/` | Admin / `view_activity` | Show company-scoped audit metadata and suspicious flags, not document content. |
| `POST /documents/<uuid>/access-suggestions/` | Owner / `suggest_recipients` | Optional local suggestion workflow uses company sharing metadata only; no permission changes until an authorized explicit grant form is confirmed. |

## Upload Contract

- Accept only PDF, DOCX, XLSX, and PPTX with a maximum size of 25 MiB
  (26,214,400 bytes).
- Determine validity from server-side content inspection, not a client-supplied
  extension or MIME type. Reject malformed files and unsupported formats.
- Never compose a filesystem path from the uploaded filename. Escape any
  retained display name in rendered templates.
- Store outside the web root. Do not expose public storage URLs.

## HTML and Privacy

- Server-rendered forms include CSRF tokens and use escaped template output.
- Forms distinguish validation failures from authorization failures without
  revealing document existence.
- Document pages and streamed files use `Cache-Control: private, no-store`.
- An admin activity row may identify a document for audit purposes but cannot
  link to or embed content unless that admin separately has a current grant.
- Suspicious access flags appear after at least five refused document-access
  attempts by the same member within a rolling ten-minute window.
- The optional suggestion flow never sends company data to an external AI
  provider and never reads document contents.
