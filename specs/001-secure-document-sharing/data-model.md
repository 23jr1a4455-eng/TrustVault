# Data Model: Secure Document Sharing

The relational store is PostgreSQL. All company-owned rows carry an explicit
company relationship, and queries are scoped to the active company before
authorization-sensitive filtering. UUIDs are used for externally visible
document and invitation identifiers; identifiers are not authorization
controls.

## Entities

### Company

Represents a tenant.

- `id`: UUID primary key
- `name`: required display name
- `created_at`: UTC creation time
- Relationships: has members, categories, documents, invitations, and audit
  events
- Validation: company names are non-empty; all related records are tenant
  scoped

### User

The project's Django authentication user, established before the first
migration.

- `id`: UUID primary key
- Sign-in identity and password hash: managed by Django authentication
- `is_active`: deactivation immediately prevents future authenticated access
- Relationships: belongs to one company through membership; can act on audit
  events
- Validation: normalized sign-in identity is unique; credentials are never
  stored in audit payloads
- Security: Django session state contains identity only, never document grants

### CompanyMembership

Associates one user with their single company, administrative capability, and
document-owner/viewer role. These are separate axes so a person may be both an
administrator and an owner without gaining document access from administrator
capability.

- `id`: UUID primary key
- `company_id`: required foreign key
- `user_id`: required one-to-one foreign key to User
- `is_admin`: boolean administrative capability
- `document_role`: `owner` or `viewer`; unknown values fail closed
- `created_at`, `updated_at`: UTC timestamps
- Constraints: unique user membership; document role restricted to the known
  values
- Relationships: one company and one user; may own documents and receive
  grants
- Validation: an administrator cannot change their own administrator
  capability; only another administrator may change an administrator
  capability. Administrator capability alone never grants document access.
- Composition: a member may be an owner and an administrator at the same time;
  a viewer can read or edit only when current document grants permit it.

### Invitation

Represents a pending company member invitation.

- `id`: UUID primary key
- `company_id`: required foreign key
- `email`: normalized invitee identity
- `document_role`: `owner` or `viewer`
- `token_digest`: digest of a one-time invitation secret; never store the
  plaintext token
- `invited_by_id`: requesting administrator
- `created_at`, `expires_at`, `accepted_at`, `revoked_at`: UTC lifecycle
  timestamps
- State transitions: pending → accepted, expired, or revoked; only pending
  invitations can be accepted
- Validation: only an administrator can issue or revoke an invitation;
  invitations cannot grant administrator capability
- Audit: issue, acceptance, revocation, expiry, and refused attempts

### Category

Company-scoped organization label.

- `id`: UUID primary key
- `company_id`: required foreign key
- `name`: required normalized label
- Constraints: unique normalized name per company
- Relationships: a category can label many documents
- Validation: a member may only assign a category belonging to the document's
  company

### Document

Metadata and lifecycle for a private stored file.

- `id`: UUID primary key
- `company_id`: required foreign key
- `owner_id`: required membership foreign key
- `category_id`: optional company category foreign key
- `title`: required display name, treated as untrusted and escaped on output
- `original_filename`: optional display metadata only; never used as a path
- `storage_key`: generated opaque key, never derived from client input
- `verified_format`: one of PDF, DOCX, XLSX, PPTX after server-side validation
- `size_bytes`: integer, 1 through 26,214,400
- `created_at`, `updated_at`, `deleted_at`: UTC lifecycle timestamps
- `state`: active or deleted; deleted rows are excluded from search and access
- Relationships: owner and grants are company members; has optional category,
  one edit lease, and audit events
- Validation: owner, category, and grants all belong to the same company;
  only active documents can be read, changed, or leased
- Deletion: authorize and audit deletion, mark the row unavailable
  transactionally, then delete private bytes after commit; retry failed
  physical cleanup without restoring access

### DocumentGrant

An explicit, current, revocable per-document authorization.

- `id`: UUID primary key
- `document_id`: required foreign key
- `member_id`: required company membership foreign key
- `level`: `read` or `edit`
- `granted_by_id`: required membership foreign key
- `created_at`, `updated_at`, `revoked_at`: UTC timestamps
- Constraints: unique active grant per document/member; grant level restricted
  to the known values
- Relationships: document and grantee must belong to the same company
- Semantics: `edit` includes read; owner receives an explicit edit grant at
  upload; role membership alone never grants document access
- State transitions: grant/re-grant → active; revoke → inactive; changes take
  effect on the next request
- Audit: every allowed or refused grant, change, and revoke operation

### EditLease

Enforces one active editor for a document.

- `id`: UUID primary key
- `document_id`: unique required foreign key
- `member_id`: current authorized editor
- `generation`: monotonically increasing integer fencing stale editors
- `last_activity_at`, `expires_at`: UTC lease timestamps
- State transitions: acquired → renewed; released on save or cancel; expires
  after 15 minutes without activity and may then be acquired by another member
- Validation: member must hold current edit authorization on every acquire,
  renew, and save; a prior generation cannot save after expiry/reacquisition
- Concurrency: acquire/save/renew lock the document row in a short PostgreSQL
  transaction; no lock is held while streaming or doing file I/O
- Audit: acquisition, wait, renewal, expiration, release, save, and denial

### AuditChainHead

The serialized head of the global audit chain.

- `id`: singleton key
- `sequence`: last committed event sequence, initially zero
- `event_hash`: digest for the last event, initialized to a documented genesis
  value
- Concurrency: append operation locks this row before reading/updating it
- Mutability: runtime role may update this head as part of append operations;
  it is not an audit event

### AuditEvent

An append-only record of authorization decisions and required business
activity.

- `id`: UUID primary key
- `sequence`: monotonically increasing global sequence, unique
- `company_id`: nullable for pre-authentication or system events
- `actor_id`: nullable for unauthenticated attempts
- `action`: allowlisted action name (upload, download, edit, delete, grant,
  revoke, invite, deactivate, role change, lease, login, and related denial)
- `outcome`: allow or deny
- `target_type`, `target_id`: event subject, when known; an attempted opaque ID
  may be recorded even if no matching document exists
- `reason_code`: bounded non-secret explanation for refusals
- `occurred_at`: UTC event time
- `event_data`: minimal structured metadata; no file bytes, credentials,
  session IDs, or unnecessary personal data
- `previous_hash`: prior event digest, or the genesis digest for the first row
- `event_hash`: SHA-256 over canonical event bytes and `previous_hash`
- Constraints: unique sequence; event table denies UPDATE and DELETE to the
  application runtime role; append protection is enforced in the database as
  well as the application
- Append transaction: lock chain head, assign sequence and prior digest,
  compute hash, insert event, update head, commit atomically
- Verification: recompute each event's canonical representation and digest in
  sequence, checking both the prior-hash link and stored head

## Cross-Entity Invariants

1. Every document-bearing operation resolves the current member and document,
   calls the authorization service for the action, and records ALLOW/DENY
   before returning a response.
2. Every document, owner, grantee, category, and invitation relationship is
   company-consistent. Queries for search and activity start with an explicit
   company scope.
3. Access requires an active grant at request time; role or session alone
   cannot grant access. Missing/unknown role, action, state, or grant denies.
4. A document without a read grant is indistinguishable from a nonexistent
   document to that requester (404).
5. Search results and all derived counts contain only documents the member
   currently has read access to.
6. An edit lease does not supersede or cache document grants; authorization is
   rechecked for every lease and save operation.
7. Audit events are appended before a success or denial response and cannot be
   edited/deleted by application or administrator users.
8. A failure to persist a required audit event must not yield an unaudited
   success. The request fails closed and records an operational error outside
   the protected event table where possible.
