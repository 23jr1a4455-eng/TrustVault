# Feature Specification: Secure Document Sharing

**Feature Branch**: `001-secure-document-sharing`

**Created**: 2026-10-19

**Status**: Draft

**Input**: User description: "TrustVault lets companies share confidential documents. Roles: admin (manages users, sees activity and permission changes, no document access unless granted), owner (uploads, organises, grants and revokes read/edit to named people on own documents, deletes own documents), viewer (reads or edits only what is granted). Features: login; upload with validation; search by name, owner, category, date (only granted documents); per-document grants; audit trail of uploads, downloads, edits, deletions, permission changes AND refused attempts; admin activity view with flags for suspicious behaviour; optional AI suggestions of who should get access, which a person must confirm and which are audited. Out of scope: folder permissions, public share links, search inside file contents, SSO."

## Clarifications

### Session 2026-10-19

- Q: Which file types and maximum size should valid uploads support? → A: PDF, DOCX, XLSX, and PPTX, up to 25 MB per file.
- Q: Which user-management actions should company administrators be allowed to perform? → A: Invite and deactivate members; assign owner/viewer roles; only another administrator may change an administrator role.
- Q: What information may optional AI access suggestions use to recommend recipients? → A: Company sharing metadata only; no external AI processing or document contents.
- Q: If two people edit the same document at the same time, how should the system handle conflicting changes? → A: Allow only one editor at a time; others wait.
- Q: How should an active editing session be released if its editor stops interacting without saving or cancelling? → A: Release after 15 minutes inactive; the editor must reopen before saving.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Grant and use document access (Priority: P1)

A company member signs in, finds a document they are allowed to read, and
reads or edits it according to the access explicitly granted to them. A document
owner can grant or revoke read or edit access for named members on documents
they own. Only one person edits a document at a time; other authorized editors
wait until the active edit ends.

**Why this priority**: Explicitly controlled document access is the core value
of confidential document sharing.

**Independent Test**: Create an owner, two other members, and a document.
Grant one member read access and the other edit access; verify that each can
perform only their granted actions. Revoke a grant and verify that the next
request is denied.

**Acceptance Scenarios**:

1. **Given** a signed-in owner and a document they own, **When** they grant a
   named member read access, **Then** that member can read the document and
   cannot edit it.
2. **Given** a signed-in owner and a document they own, **When** they grant a
   named member edit access, **Then** that member can read and edit the
   document.
3. **Given** a member with a grant, **When** the owner revokes it, **Then** the
   member's next document request is denied.
4. **Given** a member without a read grant, **When** they request a document,
   **Then** the system denies the request with a not-found response and records
   the refusal before responding.
5. **Given** an administrator without an explicit document grant, **When**
   they request the document, **Then** they are denied in the same way as any
   other ungranted member.
6. **Given** a member is editing a document, **When** another member with edit
   access tries to edit it, **Then** the second member must wait until the
   active edit ends and cannot save simultaneous changes.

---

### User Story 2 - Upload, organize, and find documents (Priority: P1)

A document owner uploads and organizes a confidential document, then searches
for documents they are allowed to read using the document name, owner,
category, or date.

**Why this priority**: Owners need to add and manage content, and members need
to find authorized content without learning about documents they cannot read.

**Independent Test**: Upload documents with valid and invalid content, assign
categories, then search as members with different read grants and verify that
only readable documents appear.

**Acceptance Scenarios**:

1. **Given** an owner, **When** they upload a document that passes validation,
   **Then** it is stored as a document they own, the owner receives explicit
   access, and the upload is audited.
2. **Given** an upload with a disallowed or invalid file, **When** the owner
   submits it, **Then** it is rejected without making a document available and
   the refusal is audited.
3. **Given** a member with read access to some documents, **When** they search
   by name, owner, category, or date, **Then** results include only documents
   for which they have current read access.
4. **Given** an owner, **When** they organize a document they own, **Then** its
   category or other supported organizational metadata is updated and the
   change is audited.
5. **Given** an owner, **When** they delete a document they own, **Then** it
   is no longer available and the deletion is audited.

---

### User Story 3 - Review activity and access suggestions (Priority: P2)

An administrator reviews company activity and permission changes, including
refused attempts and suspicious-activity flags, without gaining access to
document content by virtue of the administrator role. An owner may request
optional AI suggestions for named recipients, but a suggestion grants no
access until an authorized person confirms it.

**Why this priority**: A trustworthy activity record helps companies oversee
sharing, while optional suggestions can reduce the effort of choosing
recipients without weakening explicit approval.

**Independent Test**: Generate representative document and permission events,
including refusals, then verify an administrator can review the activity and
flags but cannot read ungranted document content. Request a recipient
suggestion and verify that access remains unchanged until a person confirms
it.

**Acceptance Scenarios**:

1. **Given** an administrator, **When** they open the activity view, **Then**
   they can review document activity metadata, permission changes, refused
   attempts, and suspicious-activity flags, but cannot read document content
   without an explicit grant.
2. **Given** repeated refused document-access attempts by a member, **When**
   the activity view is reviewed, **Then** the attempts are visible and the
   affected activity is flagged as suspicious.
3. **Given** an owner requesting optional AI suggestions, **When** suggestions
   are returned using company sharing metadata only, **Then** they identify
   possible named company members without processing document contents or
   changing any permission.
4. **Given** a suggested recipient, **When** an authorized person explicitly
   confirms a proposed grant, **Then** the resulting permission change is
   applied and audited; without confirmation, no access is granted.

---

### User Story 4 - Manage company members (Priority: P2)

A company administrator invites or deactivates members and assigns owner or
viewer roles. A change to an administrator's role requires a different
administrator.

**Why this priority**: Companies need to manage membership and roles without
allowing one administrator to change their own administrative privileges.

**Independent Test**: As an administrator, invite and deactivate a member,
assign owner and viewer roles, and verify that changing an administrator's role
requires a different administrator.

**Acceptance Scenarios**:

1. **Given** an administrator, **When** they invite a company member, **Then**
   the member can sign in after completing the invitation.
2. **Given** an administrator, **When** they deactivate a company member,
   **Then** that member can no longer access the company.
3. **Given** an administrator, **When** they assign a member the owner or
   viewer role, **Then** the member has that role.
4. **Given** an administrator, **When** they change another administrator's
   role, **Then** the change is allowed and recorded in the audit trail.
5. **Given** an administrator, **When** they attempt to change their own
   administrator role, **Then** the attempt is denied and audited.

---

### Edge Cases

- A signed-out user, a user from another company, or a user with an unknown
  role requests a document: deny the request, return not found for unreadable
  documents, and record the refusal before responding.
- A member has edit access but no separately described read grant: edit access
  permits reading as well as editing; a read-only grant does not permit edits.
- An owner tries to grant access to a person outside their company or tries to
  manage a document they do not own: deny and audit the refused attempt.
- A grant is revoked while a member has an open session or a search result:
  subsequent document requests and searches use the current grant and deny or
  omit the document.
- A second member with edit access tries to edit a document with an active
  editor: the second member waits and cannot make simultaneous changes; the
  active edit ends when its editor saves or cancels, or after 15 minutes of
  inactivity. After expiration, the original editor must reopen the document
  before saving.
- A search query has no matches, or matches documents with different access
  grants: return an empty result or only currently readable matches without
  revealing inaccessible document names or metadata.
- An upload has a misleading filename or declared content type, unsupported
  content, or exceeds 25 MB: validate using server-controlled rules, reject
  invalid content, and never use the submitted filename or type as trusted
  evidence or as a trusted storage path.
- An administrator reviews an event for a document they cannot read: show
  permitted activity metadata only, not the document contents.
- A document owner is also an administrator: administrator privileges do not
  add document access; access follows the explicit grants on each document.
- An AI suggestion is unavailable, incomplete, or declined: no permission
  changes; the person can use the normal grant flow instead.
- AI suggestions are requested: only company sharing metadata may be used;
  document contents must not be processed or sent to an external AI service.
- A request is denied because authorization state is missing, invalid, or
  unknown: fail closed and record the denial before responding.
- An administrator attempts to assign themselves an administrator role or
  change their own administrator role: deny and audit the attempt.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST allow company users to sign in and MUST restrict
  each signed-in user to their company.
- **FR-002**: The system MUST support administrator, owner, and viewer roles.
  An administrator MUST be able to invite and deactivate company members,
  assign owner or viewer roles, and review activity and permission changes.
  Only a different administrator may change an administrator's role.
  Administrators MUST NOT receive document access unless explicitly granted.
- **FR-003**: The system MUST authorize every document operation for the
  current user, document, and requested action using current grants. It MUST
  deny by default when the user, role, action, document state, or grant is
  unknown.
- **FR-004**: Document access MUST require an explicit grant. Owner upload
  MUST establish an explicit grant for the owner. An edit grant MUST permit
  reading and editing; a read grant MUST permit reading but not editing.
- **FR-005**: An owner MUST be able to organize, grant and revoke read or edit
  access for named members on documents they own, and delete documents they
  own. An owner MUST NOT manage documents owned by another person.
- **FR-006**: Grant revocation MUST take effect on the next request that
  touches the affected document. Searches MUST use current grants as well.
- **FR-007**: A user without read access MUST receive a not-found response when
  requesting a document. The response MUST NOT disclose whether an unreadable
  document exists.
- **FR-008**: The system MUST audit successful and refused uploads, downloads,
  edits, deletions, permission changes, member invitations, member
  deactivations, role changes, and document-access attempts. Each authorization
  ALLOW or DENY MUST be recorded before the corresponding response.
- **FR-009**: Audit events MUST be append-only and tamper-evident. The system
  MUST NOT permit application users or administrators to edit or delete
  recorded events.
- **FR-010**: The system MUST accept valid PDF, DOCX, XLSX, and PPTX files up
  to 25 MB per file and reject other formats or larger files. It MUST validate
  uploaded content using server-controlled criteria, MUST NOT trust
  client-supplied filenames or content types, and MUST NOT use an uploaded
  filename as a trusted storage path.
- **FR-011**: Users MUST be able to search by document name, owner, category,
  and date. Search results and related counts or suggestions MUST include only
  documents the user currently has read access to.
- **FR-012**: Administrators MUST be able to review user activity and
  permission changes, including refused attempts and suspicious-activity
  flags. The activity view MUST NOT grant access to document content.
- **FR-013**: The system MUST flag repeated refused document-access attempts
  for administrative review. The default threshold is five such attempts by
  the same user within ten minutes.
- **FR-014**: The system MAY offer AI-generated recipient suggestions using
  company sharing metadata only. Suggestions MUST NOT use document contents
  or send company data to an external AI service. A suggestion MUST NOT create
  or change a grant; an authorized person MUST explicitly confirm each
  permission change, and every resulting change MUST be audited.
- **FR-015**: Every authentication or authorization change MUST have an
  automated test that fails if the relevant security check is removed.
- **FR-016**: The system MUST NOT support folder-level permissions, public
  share links, searching inside document contents, or single sign-on as part
  of this feature.
- **FR-017**: The system MUST deny and audit an administrator's attempt to
  change their own administrator role.
- **FR-018**: The system MUST allow only one active editor per document.
  Another authorized editor MUST wait until the active editor saves, cancels,
  or has been inactive for 15 minutes before editing. A waiting editor MUST
  NOT save simultaneous changes. After an edit session expires, its editor
  MUST reopen the document before saving. The system MUST audit edit requests,
  including requests that have to wait.

### Key Entities *(include if feature involves data)*

- **Company member**: A person belonging to a company, with a role and
  sign-in identity.
- **Document**: Confidential content owned by a company member, with a name,
  category, creation or modification dates, and lifecycle state.
- **Document grant**: An explicit, revocable permission connecting a named
  company member to a document and authorizing read or edit actions.
- **Audit event**: An append-only, tamper-evident record of an allowed or
  refused action, its actor, affected document or permission where applicable,
  and event time.
- **Suspicious-activity flag**: An indicator connecting a pattern of refused
  attempts to activity that requires administrator review.
- **Access suggestion**: An optional proposed recipient and permission that
  has no effect unless an authorized person confirms it.
- **Active edit**: A period in which one authorized person is editing a
  document; other authorized editors wait until it ends. The session expires
  after 15 minutes without activity, and the original editor must reopen the
  document before saving after expiry.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In authorization tests, 100% of document requests without a
  current explicit grant are denied, and 100% of requests with a matching grant
  receive only the granted level of access.
- **SC-002**: In revocation tests, 100% of requests made after revocation,
  including searches, reflect the revoked permission on the next request.
- **SC-003**: 100% of tested ALLOW and DENY authorization decisions have an
  audit event recorded before the response; attempts to change or delete
  existing events are rejected.
- **SC-004**: In search tests, 100% of returned documents are currently
  readable by the searching member, across all supported search fields.
- **SC-005**: 100% of uploads in unsupported formats, over 25 MB, or with
  invalid content are rejected without exposing a stored document under a
  client-supplied filename or type.
- **SC-006**: An administrator can identify the actor, action, time, and
  outcome for each tested document and permission event, including refusals,
  without being able to retrieve ungranted document contents.
- **SC-007**: No AI suggestion changes access before explicit confirmation;
  100% of confirmed permission changes are auditable. Suggestions use company
  sharing metadata only and do not process document contents or send data to
  an external AI service.
- **SC-008**: Every attempted administrator role change is allowed only when
  initiated by a different administrator; every self-change attempt is denied
  and audited.
- **SC-009**: In concurrent-edit tests, no two users can edit the same
  document simultaneously, and a waiting editor cannot overwrite the active
  editor's changes. An inactive edit session expires after 15 minutes, and its
  original editor must reopen the document before saving.

## Assumptions

- Each user belongs to one company for this feature, and named grant recipients
  must be members of the same company as the document.
- A viewer's ability to edit is determined by an explicit edit grant; the
  viewer role itself does not grant document access.
- When an owner uploads a document, the system creates an explicit owner grant
  so the owner can manage that document under the explicit-grant rule.
- An edit grant includes read access; read and edit are the only grant levels
  in scope.
- An edit session is exclusive to one editor per document and ends when that
  editor saves, cancels, or is inactive for 15 minutes. An editor whose
  session expired must reopen the document before saving.
- Administrators can see audit metadata, including document identity where
  needed to review activity, but cannot see document contents without a
  separate explicit grant.
- "Suspicious behaviour" means at least five refused document-access attempts
  by the same user within a rolling ten-minute period. This threshold can be
  revised by product policy.
- Uploads are limited to PDF, DOCX, XLSX, and PPTX files no larger than 25 MB
  each. Client-declared file types are never authoritative.
- AI suggestions are optional and can be unavailable without affecting
  ordinary permission management. Suggestions use company sharing metadata
  only, do not process document contents or send data to an external AI
  service, and are proposals only until an authorized person confirms them.
- A successful authentication method is required for login; enterprise SSO is
  expressly out of scope.
- Mobile-specific behavior, retention periods, and external compliance
  certifications are not defined by this feature description.
