# TrustVault API and Endpoint Reference

TrustVault is currently a server-rendered Django web application. It does not
expose a versioned JSON API, and it has no OpenAPI schema, Swagger UI, or
Redoc. This reference documents the routes and behavior implemented in
[`../vault/urls.py`](../vault/urls.py); it does not imply JSON endpoints or
methods that the views do not implement.

## Authentication

- `/health/`, `/`, and `/login/` are public routes.
- The home route redirects signed-in users to `/documents/` and other visitors
  to `/login/`.
- `/logout/` requires an authenticated user and a POST request.
- Signed-in pages use Django's server-side session authentication. Document
  permissions are looked up from the database for each request.
- For routes protected by the `authenticated`, `uploader`, `admin_only`, and
  `gated` wrappers, an anonymous visitor is redirected to the login page when
  authorization fails. Repeated anonymous document probes may instead receive
  HTTP 429 due to probe throttling.
- An authenticated user who is not authorized for a document receives HTTP
  404, the same status and generic plain-text body as for a missing route or
  document. The administrator role does not grant document access.

## Endpoint Reference

Methods shown below reflect explicit method checks in the views. `Any method`
means the view has no explicit method guard; it is not a REST-method contract.
Unsupported methods on views with an explicit allow-list receive HTTP 405.
Query parameters and forms are documented in
[Request and Response Formats](#request-and-response-formats).

| Method | Endpoint | Authentication | Required permission | Expected response |
|---|---|---|---|---|
| Any method | `/health/` | None | None | HTTP 200, plain text `ok`. |
| Any method | `/` | None | None | HTTP 302 redirect to `/documents/` when signed in, otherwise `/login/`. |
| GET, POST | `/login/` | None | None | GET renders the HTML sign-in form (200); successful POST redirects (302); invalid credentials render the form (200); throttled POST returns an HTML page (429). Other methods are handled by Django's `LoginView`. |
| POST | `/logout/` | Signed in | Any authenticated user | Logs out and redirects to `/login/` (302). Explicitly disallowed methods receive 405. |
| Any method (GET UI) | `/documents/` | Signed in | Any active signed-in user; list/search is restricted to readable documents | HTML page with at most 20 documents per page. Invalid search query renders an empty result state. |
| GET, POST | `/documents/new/` | Signed in | Active user with role `owner`; admin and viewer are denied | GET renders upload form (200); valid POST creates document and redirects to its detail page (302); invalid form/file returns HTML with 400; oversized request/file returns 413. Other methods return 405. |
| Any method (GET UI) | `/documents/trash/` | Signed in | Any signed-in user; query is restricted to documents owned by that user | HTML page listing the current user's soft-deleted documents (200). |
| GET, HEAD | `/documents/<doc_id>/` | Signed in; anonymous visitor is redirected if denied | Document owner or active `read`/`edit` grant; document must not be deleted | HTML detail page (200); inaccessible, deleted, or missing document returns generic 404. Other methods return 405. |
| GET, HEAD | `/documents/<doc_id>/download/` | Signed in; anonymous visitor is redirected if denied | Document owner or active `read`/`edit` grant; document must not be deleted | Authorized, intact file is returned as an attachment (`FileResponse`, 200). Missing file returns 404. A stored SHA-256 mismatch is audited and raises an unhandled integrity error (server error, normally 500). Other methods return 405. |
| POST | `/documents/<doc_id>/edit/` | Signed in; anonymous visitor is redirected if denied | Document owner or active `edit` grant | Valid title/category form updates metadata and redirects to detail (302); invalid form returns the HTML detail page with 400. Other methods return 405. |
| POST | `/documents/<doc_id>/delete/` | Signed in; anonymous visitor is redirected if denied | Document owner only | Soft-deletes the document, revokes grants, and redirects to `/documents/` (302). Other methods return 405. |
| POST | `/documents/<doc_id>/replace/` | Signed in; anonymous visitor is redirected if denied | Document owner or active `edit` grant | Valid file replacement redirects to detail (302); invalid or rejected upload renders the HTML detail page with 400. Other methods return 405. |
| POST | `/documents/<doc_id>/restore/` | Signed in; anonymous visitor is redirected if denied | Document owner only; document must currently be deleted | Restores the document and redirects to detail (302). If it is not deleted, returns generic 404. Other methods return 405. Existing grants remain revoked. |
| GET, HEAD | `/documents/<doc_id>/access/` | Signed in; anonymous visitor is redirected if denied | Document owner only | HTML page listing grants and pending suggestions (200). Other methods return 405. |
| POST | `/documents/<doc_id>/access/grant/` | Signed in; anonymous visitor is redirected if denied | Document owner only | Valid grant redirects to access page (302); invalid form or refused grant renders the HTML access page with 400. |
| POST | `/documents/<doc_id>/access/<grant_id>/revoke/` | Signed in; anonymous visitor is redirected if denied | Document owner only | Revokes the grant through the grant service and redirects to access page (302). Other methods return 405. |
| POST | `/documents/<doc_id>/access/suggest/` | Signed in; anonymous visitor is redirected if denied | Document owner only | Generates rule-based suggestions and redirects to access page (302). Other methods return 405. |
| POST | `/documents/<doc_id>/access/suggestions/<suggestion_id>/accept/` | Signed in; anonymous visitor is redirected if denied | Document owner only | Accepts the pending suggestion with the submitted `level` and redirects to access page (302); refused grant renders the HTML access page with 400. Other methods return 405. |
| POST | `/documents/<doc_id>/access/suggestions/<suggestion_id>/reject/` | Signed in; anonymous visitor is redirected if denied | Document owner only | Rejects the pending suggestion and redirects to access page (302). Other methods return 405. |
| GET, HEAD | `/documents/<doc_id>/history/` | Signed in; anonymous visitor is redirected if denied | Document owner only | HTML page of that document's audit history, paginated (200). Other methods return 405. |
| Any method (GET UI) | `/activity/` | Signed in | Active user with role `admin` | HTML audit activity page, paginated and filterable (200). |
| Any method (GET UI) | `/activity/flags/` | Signed in | Active user with role `admin` | HTML activity-flags page (200). |
| POST | `/activity/verify/` | Signed in | Active user with role `admin` | HTML verification report: 200 if the chain verifies, 409 if it does not. Other methods return 405. |
| Any method (GET UI) | `/users/` | Signed in | Active user with role `admin` | HTML user listing (200). |
| POST | `/users/<user_id>/disable/` | Signed in | Active user with role `admin` | Disables the target and redirects to `/users/` (302); refused change renders HTML with 400; missing target returns 404. Other methods return 405. |
| POST | `/users/<user_id>/enable/` | Signed in | Active user with role `admin` | Enables the target and redirects to `/users/` (302); refused change renders HTML with 400; missing target returns 404. Other methods return 405. |

The `doc_id` path value must be a UUID; `grant_id`, `suggestion_id`, and
`user_id` must be integers. Paths that do not match a route return the generic
404 response.

## Authorization Requirements

- Every document-specific route uses the document authorization gate before
  executing its view. The gate records allow and deny decisions to the audit
  log before returning a response.
- An owner has access to their own document. A currently active `read` or
  `edit` grant permits reading and downloading. An `edit` grant also permits
  editing and replacing the file. Grants can expire or be revoked.
- Sharing, grant revocation, suggestion generation/decisions, deletion,
  restoration, and document history are owner-only operations.
- Deleted documents are not readable, downloadable, editable, or shareable.
  Owners may restore a deleted document; restore does not revive old grants.
- Uploading a new document requires an active user with the `owner` role.
- Administrator-only pages require an active user with the `admin` role.
  Administrators do not receive implicit access to documents.
- The document search query includes only documents readable by the current
  user; filtering, counts, and pagination do not widen that permission.

## Request and Response Formats

This is an HTML form application. It does not accept or return a documented
JSON API format.

- Search and activity filters are query-string parameters.
- Document search accepts `q`, `owner`, `category`, `date_from`, `date_to`,
  and `page`. Invalid query values produce an empty search result state rather
  than an API error document.
- The activity page accepts `group`, `actor`, `document`, `date_from`,
  `date_to`, and `page`.
- Sign-in uses Django's HTML form fields `username` and `password`.
- Document edit accepts `title` and optional `category`.
- Document upload accepts multipart form data with optional `title`,
  optional `category`, and required file field `file`.
- File replacement accepts multipart form data with required file field
  `file`. File content, not the submitted MIME type, determines accepted file
  type.
- Grant creation accepts `username`, `level` (`read` or `edit`), and optional
  `expires_on` date.
- Suggestion acceptance accepts a `level` form field. User enable/disable,
  deletion, restore, revocation, suggestion generation/decision, audit
  verification, and logout are POST form actions.
- Successful state-changing operations generally redirect with HTTP 302.
  Downloads return file bytes as an attachment. Health and generic not-found
  responses are plain text; application pages and form errors are HTML.

## Error Responses

| Status | Behavior |
|---|---|
| 400 | Invalid edit/grant form or rejected upload; HTML form page. Invalid multipart body length may return plain text 400. |
| 403 | Django CSRF middleware rejects a missing or invalid CSRF token on an unsafe request. |
| 404 | Missing route/document, denied access for authenticated users, deleted document outside restore, or a restore attempt when the document is not deleted. Body is generic plain text `Not found.` |
| 405 | Explicitly method-restricted view receives a method other than its listed methods. |
| 409 | Administrator audit-chain verification reports an invalid chain. |
| 413 | Upload request/file exceeds configured size limit. |
| 429 | Login or anonymous document-probe throttling is triggered. |
| 500 | Unexpected server error. For example, a downloaded file whose stored bytes fail the SHA-256 check is audited and raises an integrity exception; it is not served. |

Unauthorized access decisions are audited. A failed integrity check is audited
before the server error is raised.

## CSRF Requirements

Django's `CsrfViewMiddleware` is enabled. Unsafe requests, including POST form
submissions, must include a valid CSRF token. Use the token included in
TrustVault's rendered forms; external scripts or clients must first obtain and
submit a valid token and maintain the session cookies. No application route is
marked CSRF-exempt. A failed CSRF check returns HTTP 403.
