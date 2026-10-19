# Tasks: Secure Document Sharing

**Input**: Design documents from `/specs/001-secure-document-sharing/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/web-workflows.md`, and `quickstart.md`

**Tests**: Included because the specification requires authorization regression
tests and PostgreSQL-backed security/concurrency validation.

**Organization**: Tasks are grouped by user story. All task lines use the
required checkbox, task ID, optional parallel marker, story label, and
concrete file path format.

## Phase 1: Setup

**Purpose**: Add development tooling and test configuration without changing
the existing project bootstrap.

- [ ] T001 [P] Add pytest, pytest-django, and coverage dependencies in `requirements-dev.txt`
- [ ] T002 [P] Configure pytest discovery, Django settings module, and test paths in `pyproject.toml`
- [ ] T003 [P] Add environment-variable documentation for PostgreSQL, HTTPS, private storage, and secrets in `.env.example`
- [ ] T004 Add PostgreSQL test configuration and reusable company/member fixtures in `tests/conftest.py`

## Phase 2: Foundational

**Purpose**: Establish tenant identity, append-only audit, request-level audit
integration, and shared security response boundaries required by every story.

**Checkpoint**: No user-story work starts until the project-owned user model,
foundational migrations, hash-chain append service, and audit-before-response
contract are in place. The document-specific authorization service is
implemented with the document and grant models in User Story 1.

- [ ] T005 Define UUID-authenticated user and initial company/membership schema in `vault/models.py`; preserve `user_id`: required one-to-one foreign key to User, normalized unique sign-in identity, `is_admin`, and `document_role`: `owner` or `viewer`
- [ ] T006 Configure `AUTH_USER_MODEL`, PostgreSQL environment settings, database-backed sessions, secure cookie settings, HTTPS settings, and private storage root in `trustvault/settings.py`
- [ ] T007 Create the initial custom-user, Company, and CompanyMembership migration in `vault/migrations/0001_initial.py`
- [ ] T008 Create shared CSRF-protected base and sign-in templates with navigation for server-rendered pages in `vault/templates/vault/base.html` and `vault/templates/vault/login.html`
- [ ] T009 Create AuditEvent and singleton AuditChainHead in `vault/models.py`; preserve `sequence`: unique and monotonic, nullable `company_id`/`actor_id` for pre-authentication events, `outcome`: allow or deny, `event_data`: no file bytes/credentials/session IDs/unnecessary personal data, and `previous_hash`/`event_hash`: SHA-256 chain
- [ ] T010 Create audit schema and chain-head initialization migration in `vault/migrations/0002_audit_chain.py`
- [ ] T011 Implement serialized global hash-chain append, deterministic event encoding, and chain verification in `vault/services/audit.py`
- [ ] T012 Install database-level protection against AuditEvent UPDATE/DELETE in `vault/migrations/0003_audit_append_only.py`
- [ ] T013 Implement request-level audit integration that records ALLOW and DENY before responding and fails closed if required audit persistence fails in `vault/services/audit.py`
- [ ] T014 Add PostgreSQL transactional tests for global audit ordering, chain verification, audit failure behavior, and rejected event mutation/deletion in `tests/test_audit.py`
- [ ] T015 Add production-safe security headers, private no-store response helpers, and trusted-proxy configuration guards in `vault/security.py`
- [ ] T016 Implement shared not-found handling for both absent and unreadable document identifiers in `vault/views.py`
- [ ] T017 Implement login/logout views and routes with session rotation, CSRF protection, and audited authentication outcomes in `vault/views.py` and `vault/urls.py`
- [ ] T018 Add custom-user, login/session-rotation, security-configuration, and initial-migration tests in `tests/test_foundation.py`

---

## Phase 3: User Story 1 - Grant and Use Document Access (Priority: P1)

**Goal**: Owners manage explicit per-document grants, while all document reads,
edits, downloads, revocations, and edit leases use current authorization.

**Independent Test**: Create a company, owner, and two members; grant one
read-only and one edit access; verify permitted and denied actions, immediate
revocation, 404 for unreadable documents, audit ordering, and exclusive editing.

### Tests for User Story 1

- [ ] T019 [P] [US1] Add authorization matrix tests for owners, viewers, admins without grants, cross-company members, and unknown actions in `tests/test_authorization.py`
- [ ] T020 [P] [US1] Add tests for 404 equivalence, immediate grant revocation, and read-versus-edit semantics in `tests/test_documents.py`
- [ ] T021 [P] [US1] Add PostgreSQL transactional tests for one active editor, 15-minute expiry, and stale-generation rejection in `tests/test_leases.py`

### Implementation for User Story 1

- [ ] T022 [US1] Add Category, Document, and DocumentGrant models in `vault/models.py`; preserve Category `name`: required normalized label and unique normalized name per company; Document `storage_key`: generated opaque key never derived from client input and `size_bytes`: integer 1 through 26,214,400; Grant `level`: `read` or `edit`, same-company document/member relationship, and unique active grant per document/member
- [ ] T023 [US1] Create category, document, and grant schema migration with same-company consistency constraints and indexes in `vault/migrations/0004_documents_and_grants.py`
- [ ] T024 [US1] Implement action-specific `authorize(user, document, action)` using current membership/grant state and deny-by-default behavior in `vault/authorization.py`; implement grant/re-grant, read/edit checks, immediate revocation, and owner-only grant management in `vault/services/grants.py`
- [ ] T025 [US1] Implement document detail, grant, and revoke views with `authorize(user, document, action)` before access in `vault/views.py`
- [ ] T026 [US1] Define document detail, grant, and revoke routes in `vault/urls.py`
- [ ] T027 [US1] Add CSRF-protected document detail, grant, and revoke forms/templates in `vault/templates/vault/document_detail.html`
- [ ] T028 [US1] Implement EditLease in `vault/models.py`; preserve the data-model constraints `document_id`: unique required foreign key, `generation`: monotonically increasing integer, and expiry after 15 minutes without activity
- [ ] T029 [US1] Create edit-lease schema migration and unique document constraint in `vault/migrations/0005_edit_lease.py`
- [ ] T030 [US1] Implement lease acquire, wait, renew, expire, release, save fencing, and audit operations under short PostgreSQL transactions in `vault/services/leases.py`
- [ ] T031 [US1] Add lease acquisition, heartbeat, save, and cancel routes that re-authorize the current grant and lease generation in `vault/urls.py`
- [ ] T032 [US1] Add server-rendered editor/waiting states and minimal lease-heartbeat behavior in `vault/templates/vault/document_edit.html`
- [ ] T033 [US1] Add edit lease heartbeat client code that stops on save, cancel, expiry, or loss of authorization in `vault/static/vault/edit-lease.js`
- [ ] T034 [US1] Add regression tests proving each document view denies access when its authorization guard is removed in `tests/test_documents.py`
- [ ] T035 [US1] Record allowed/refused detail, grant, revoke, edit, lease, and download actions before each response in `vault/views.py`

**Checkpoint**: A member can independently use explicitly granted access;
revocation takes effect on the next request, unreadable IDs return 404, and
concurrent edits cannot silently overwrite one another.

---

## Phase 4: User Story 2 - Upload, Organize, and Find Documents (Priority: P1)

**Goal**: Owners safely upload and organize private files; members search only
documents for which they currently have read grants.

**Independent Test**: Upload valid and invalid file fixtures, organize valid
documents, and search as members with differing grants; verify server-side
validation, private storage, access filtering, audit, and cleanup behavior.

### Tests for User Story 2

- [ ] T036 [P] [US2] Add valid, malformed, wrong-content-type, path-like filename, unsupported-format, and 25 MiB boundary tests in `tests/test_uploads.py`
- [ ] T037 [P] [US2] Add search field, company scope, result/count privacy, and current-grant tests in `tests/test_search.py`
- [ ] T038 [P] [US2] Add private streaming, 404, no-store header, and audit-before-file-open tests in `tests/test_documents.py`

### Implementation for User Story 2

- [ ] T039 [US2] Implement streamed server-side validation for PDF, DOCX, XLSX, and PPTX; accept files from 1 through 26,214,400 bytes and reject unsupported/malformed content in `vault/services/uploads.py`
- [ ] T040 [US2] Configure a private filesystem storage backend outside the web root with generated opaque keys and no public URLs in `vault/storage.py`
- [ ] T041 [US2] Implement upload transaction orchestration that creates the document and owner edit grant, audits the result, and cleans up staged bytes on failure in `vault/services/documents.py`
- [ ] T042 [US2] Add owner upload form with validated display metadata and CSRF token in `vault/forms.py`
- [ ] T043 [US2] Implement upload and document replacement views with authorization, size checks, content validation, and audit-before-response behavior in `vault/views.py`
- [ ] T044 [US2] Implement app-mediated authorized downloads using private storage, attachment disposition, `nosniff`, and `Cache-Control: private, no-store` in `vault/views.py`
- [ ] T045 [US2] Implement company-scoped search by name, owner, category, and date; authorize each returned document with the current `read` grant before including it, and exclude inaccessible metadata and counts in `vault/selectors.py`
- [ ] T046 [US2] Add owner category assignment and document deletion with immediate unavailability and retryable post-commit private-byte cleanup in `vault/services/documents.py`
- [ ] T047 [US2] Add upload, download, search, organize, and delete routes in `vault/urls.py`
- [ ] T048 [US2] Add safe document result and upload templates in `vault/templates/vault/document_list.html` and `vault/templates/vault/document_upload.html`
- [ ] T049 [US2] Add regression tests proving upload, download, edit, organize, and delete routes fail closed if their authorization guard is removed in `tests/test_documents.py`

**Checkpoint**: Owners can add and organize accepted documents; all file
delivery is private and authorized per request; searches reveal only currently
readable documents.

---

## Phase 5: User Story 3 - Review Activity and Access Suggestions (Priority: P2)

**Goal**: Administrators review company-scoped event metadata and suspicious
flags without obtaining document access; optional local suggestions never grant
access without confirmation.

**Independent Test**: Generate allowed and refused activity, inspect the
administrator view, confirm suspicious attempts are flagged, and verify
suggestions use metadata only and leave grants unchanged until confirmation.

### Tests for User Story 3

- [ ] T050 [P] [US3] Add tests that activity is company-scoped and exposes metadata but never ungranted document contents in `tests/test_activity.py`
- [ ] T051 [P] [US3] Add tests for five refused document-access attempts in a rolling ten-minute window and non-triggering boundary cases in `tests/test_activity.py`
- [ ] T052 [P] [US3] Add tests that metadata-only suggestions create no grant until an authorized confirmation and never invoke an external provider in `tests/test_suggestions.py`

### Implementation for User Story 3

- [ ] T053 [US3] Implement company-scoped audit activity selectors and suspicious flags at five denied document attempts per member within ten rolling minutes in `vault/selectors.py`
- [ ] T054 [US3] Implement administrator activity view requiring administrative capability and excluding document bytes/content in `vault/views.py`
- [ ] T055 [US3] Add admin activity route and actor/action/time/outcome/suspicious-flag list template in `vault/urls.py` and `vault/templates/vault/activity_list.html`
- [ ] T056 [US3] Implement optional local recipient suggestions using company sharing metadata only and no external AI or document-content access in `vault/services/suggestions.py`
- [ ] T057 [US3] Add explicit confirmation form that routes a suggested grant through the normal owner-authorized grant service and audit path in `vault/forms.py`
- [ ] T058 [US3] Add suggestion and confirmation routes with owner authorization in `vault/urls.py`
- [ ] T059 [US3] Add regression tests proving admin activity and suggestion routes enforce authorization and never grant document access by role alone in `tests/test_activity.py`

**Checkpoint**: Administrators can review audit metadata and flags without
document access; optional suggestions do not change grants until confirmed.

---

## Phase 6: User Story 4 - Manage Company Members (Priority: P2)

**Goal**: Administrators invite/deactivate members and assign owner/viewer
document roles, while administrator-capability changes require a different
administrator.

**Independent Test**: Invite and accept owner/viewer memberships, deactivate a
member, assign document roles, and verify self-administration changes are
denied and audited.

### Tests for User Story 4

- [ ] T060 [P] [US4] Add invitation state, one-time token, expiry, and cross-company acceptance tests in `tests/test_members_and_admin.py`
- [ ] T061 [P] [US4] Add tests for member deactivation, owner/viewer assignment, different-admin requirement, and denied self-change audit in `tests/test_members_and_admin.py`

### Implementation for User Story 4

- [ ] T062 [US4] Implement Invitation in `vault/models.py`; preserve `email`: normalized invitee identity, `document_role`: `owner` or `viewer`, `token_digest`: digest of a one-time invitation secret (never plaintext), and pending → accepted/expired/revoked lifecycle
- [ ] T063 [US4] Create invitation and membership lifecycle migration in `vault/migrations/0006_invitations.py`
- [ ] T064 [US4] Implement invitation issue, accept, revoke, and expiry flows with transactionally audited outcomes in `vault/services/invitations.py`; configure a seven-day invitation expiry default and make it adjustable through deployment settings
- [ ] T065 [US4] Implement member deactivation and role changes, requiring a different administrator for administrator-capability changes in `vault/services/members.py`
- [ ] T066 [US4] Implement invitation acceptance and member-management, deactivation, and role-change views with per-action authorization and audit outcomes in `vault/views.py`; register their routes in `vault/urls.py`
- [ ] T067 [US4] Add invitation, role-management, and deactivation forms with CSRF-compatible validation in `vault/forms.py`
- [ ] T068 [US4] Add admin member-list and invitation templates with CSRF protection and no document-content access in `vault/templates/vault/member_list.html`
- [ ] T069 [US4] Add regression tests proving member-administration guards, cross-company denial, and denied self-role changes in `tests/test_members_and_admin.py`

**Checkpoint**: Company membership and role lifecycle work independently, with
all changes and refused attempts audited.

---

## Phase 7: Polish and Cross-Cutting Security

**Purpose**: Complete operational hardening, deployment documentation, and
end-to-end validation across the user stories.

- [ ] T070 [P] Add staged-file cleanup management command and operational logging for failed post-commit deletion in `vault/management/commands/cleanup_document_files.py`
- [ ] T071 [P] Add audit-chain verification management command with non-mutating failure reporting in `vault/management/commands/verify_audit_chain.py`
- [ ] T072 Document HTTPS, trusted proxy handling, managed PostgreSQL TLS verification, runtime database privileges, private persistent storage, and a 25 MiB upload ingress limit in `docs/deployment.md`
- [ ] T073 Add security settings and Django deployment-check assertions for production configuration in `tests/test_security_settings.py`
- [ ] T074 Add end-to-end workflows for grant/revoke, private upload/download, audit review, member administration, and optional suggestions in `tests/test_workflows.py`
- [ ] T075 Run formatting, Django checks, PostgreSQL pytest suite, and deployment checks; document exact commands and prerequisites in `specs/001-secure-document-sharing/quickstart.md`
- [ ] T076 Update user-facing setup, security, and operations guidance for the implemented workflows in `README.md`

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No feature prerequisites; T001–T003 may proceed in
  parallel, then T004 uses the configured test dependencies.
- **Foundational (Phase 2)**: Depends on setup. T005–T007 must complete before
  migrations or user-story models; T009–T014 establish audit models, append
  service, and request ordering; Phase 3 and later depend on the complete
  foundation.
- **User Stories (Phases 3–6)**: Depend on Phase 2. P1 stories precede P2
  stories for delivery. US2 consumes US1's document authorization and grant
  services. US3 consumes audit and document/grant services. US4 consumes the
  foundational identity and audit services.
- **Polish (Phase 7)**: Depends on all user stories selected for release.

### User Story Dependencies

- **US1 (P1)**: Starts after foundational identity and audit services. It
  establishes the document authorization service and document/grant/lease
  primitives.
- **US2 (P1)**: Starts after foundation and uses US1 document/grant primitives
  for upload ownership, authorized downloads, search, organize, and delete.
- **US3 (P2)**: Starts after audit foundation and depends on US1/US2 event and
  document metadata for activity and suggestions.
- **US4 (P2)**: Starts after foundation; membership management is distinct but
  integrates with shared membership and audit models.

### Parallel Opportunities

- T001–T003 can proceed in parallel because they modify distinct setup files.
- Foundational audit, user/session, and migration tests T014, T017, and T018
  can be prepared in parallel after their data contracts are agreed.
- Within US1, T019–T021 can be authored in parallel; lease work depends on
  document/grant models.
- Within US2, upload validation tests T036, search tests T037, and streaming
  tests T038 can proceed in parallel; implementation shares document models
  and the authorization service.
- US3 activity and suggestion tests T050–T052 can be authored in parallel.
- US4 invitation and role tests T060–T061 can be authored in parallel.
- US3 and US4 can be implemented in parallel after the foundation and shared
  model contracts are stable; coordinate edits to `vault/models.py`,
  `vault/forms.py`, `vault/urls.py`, and `vault/views.py`.
- Phase 7 T070–T071 can proceed in parallel; deployment and whole-suite
  validation follow feature completion.

## Parallel Example: User Story 1

```text
T019: Authorization matrix tests in tests/test_authorization.py
T020: Grant, revocation, and 404 tests in tests/test_documents.py
T021: PostgreSQL lease tests in tests/test_leases.py
```

## Implementation Strategy

### MVP First (P1 Access and Document Handling)

1. Complete setup and foundational phases, including the custom user model,
   login, database migrations, append-only audit, and audit-before-response
   service.
2. Implement US1 explicit document grants, 404 privacy behavior, immediate
   revocation, and exclusive editing.
3. Implement US2 upload, private authorized downloads, search, organization,
   and deletion so P1 grant/access workflows can operate on real documents.
4. Run the US1 and US2 authorization, upload, search, and PostgreSQL lease
   tests; do not proceed if guard-removal tests fail to detect removed checks.
5. **Stop and validate** the P1 increment before adding P2 oversight and
   member-management workflows.

### Incremental Delivery

1. Setup + foundation → stable identity, audit chain, and authorization.
2. US1 → independently testable grant/revoke and document access MVP.
3. US2 → private uploads, streaming downloads, organization, and authorized
   search.
4. US3 → activity review, suspicious flags, and optional metadata-only
   suggestions.
5. US4 → invitations, deactivation, and role administration.
6. Polish → production deployment, recovery checks, full PostgreSQL suite, and
   updated operations guidance.
