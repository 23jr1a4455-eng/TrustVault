<!--
Sync Impact Report
Version change: uninitialized template → 1.0.0
Modified principles: none; the project-specific principles are established below.
Added sections: Security Requirements; Development Workflow and Compliance.
Removed sections: unresolved scaffold placeholders and template examples.
Follow-up TODOs: confirm the original ratification date.
-->

# TrustVault Constitution

## Core Principles

### I. Explicit Grants and Server-Side Authorization
A document is reachable only by a user with an explicit grant. Every request
that touches a document MUST authorize the requested action on the server
using current grants from the database. The server MUST NOT rely on a prior
request's decision.

### II. Complete, Append-Only Audit
Every authorization ALLOW and DENY MUST be recorded in the audit log before
the server replies. The audit log MUST be append-only and tamper-evident;
application code MUST NOT edit or delete existing audit events. This provides
accountability and preserves trustworthy evidence of access decisions.

### III. Immediate Revocation
Revoking a document grant MUST prevent access on the next request. Authorization
MUST read current database grants for every request and MUST NOT use cached
grants or token permissions that can outlive revocation.

### IV. Deny by Default and Conceal Unreadable Documents
Unknown users, roles, actions, grants, or document states MUST be denied.
Requests for documents the user cannot read MUST return 404, not 403, so the
response does not disclose whether a document exists.

### V. Treat Upload Metadata as Untrusted
The application MUST NOT trust an uploaded filename or content type. It MUST
validate uploads using server-controlled rules and MUST use safe, generated
storage names rather than using a client-supplied filename as a trusted path.

### VI. Authorization Changes Require Regression Tests
Every authentication or authorization change MUST include a test that fails
when the relevant authorization check is removed. Tests MUST cover the access
decision and, where applicable, the audit event recorded before the response.

### VII. Tokens Carry No Permissions
Authentication tokens MUST NOT contain document grants or other permissions.
The server MUST obtain authorization grants from the database when deciding
each request.

## Security Requirements

All document access paths, including future routes, background operations, and
administrative flows, MUST apply these principles consistently. Authorization
MUST be action-specific, use current persisted grants, deny unknown states, and
produce an auditable decision before returning a response. Audit records MUST
not be updated or deleted by application behavior.

## Development Workflow and Compliance

Changes that add or modify document access, authentication, authorization,
uploads, or audit behavior MUST include focused automated tests. Tests MUST
verify denial as well as allowed access, 404 behavior for unreadable documents,
and append-only audit behavior where relevant. Code review MUST check
compliance with this constitution before changes are merged. Any proposed
exception MUST be documented and approved through a constitution amendment
before implementation.

## Governance

This constitution governs TrustVault design, implementation, tests, and
reviews. Amendments require review and approval by project maintainers and
MUST update this document's version and last-amended date. Versioning follows
semantic versioning: a MAJOR increment marks incompatible governance changes,
a MINOR increment adds or materially expands principles or requirements, and
a PATCH increment clarifies wording without changing requirements. Every
change that affects authentication or authorization MUST be reviewed for
compliance and include a regression test that fails if its authorization check
is removed.

**Version**: 1.0.0 | **Ratified**: TODO(RATIFICATION_DATE): original adoption date unknown | **Last Amended**: 2026-10-19
