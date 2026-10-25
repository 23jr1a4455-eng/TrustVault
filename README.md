# TrustVault

## 1. Project Overview

TrustVault is a Django document-vault application for storing and sharing
documents between named users. It enforces per-document authorization on the
server and records allowed and refused actions in an append-only audit log.
Document bytes are stored in PostgreSQL and are served through the application
only after authorization.

## 2. Features

- User accounts with `admin`, `owner`, and `viewer` roles.
- Upload, search, view, edit, replace, soft-delete, and restore documents,
  subject to role and per-document grants.
- Per-document `read` and `edit` grants, optional expiry, and revocation.
- Search over only the documents the current user can read, with filters for
  title/file name, owner, category, and date.
- Upload validation for PDF, DOCX, XLSX, and PPTX files, including content
  inspection, filename cleanup, a 25 MB file-size limit, and rejection of
  macro-enabled Office files.
- Rule-based sharing suggestions based on access to other documents in the
  same category. Suggestions do not grant access unless an owner accepts them.
- Administrator pages for user enable/disable, audit activity, activity flags,
  and audit-chain verification. Administrators do not automatically gain
  access to document contents.
- Per-document history for owners.
- PostgreSQL-backed file storage, SHA-256 download integrity checks, and an
  HMAC-linked audit chain.

## 3. Security Design

- The authorization gate checks the current database state for each document
  action. Roles or document permissions are not stored in authentication
  tokens.
- Access is denied by default. Unknown actions, roles, and grant levels do not
  grant access. An administrator role alone does not grant document access.
- Authenticated users who cannot read a document receive a generic 404 rather
  than a 403. Anonymous users may be redirected to sign in. Both missing and
  inaccessible document responses use a generic not-found body.
- Authorization decisions, including denials, are recorded before the
  response. Audit events are protected as append-only in application code and
  by a PostgreSQL trigger. Chained rows use an HMAC key kept outside the
  database; external anchors provide an additional check against rewriting
  history.
- Upload filenames and client-provided content types are not trusted. Files
  are checked from their bytes and are not exposed through a public media
  directory.
- Downloads are authorized, checked against the stored SHA-256 digest, and
  returned as attachments with restrictive response headers.
- Django sessions are server-side. HTTPS, secure cookies, CSRF protection,
  security headers, and upload request/file-size limits are configured in the
  application.
- The public Django admin (`/admin/`) is not installed or exposed. The
  application's custom administrator pages use the `admin` role and are
  audited.

This is a project implementation, not a guarantee that a deployment or its
operating environment is secure. Review the deployment configuration and
follow the verification steps below before using real documents.

## 4. Technology Stack

- Python 3.12 (the version used by the CI workflow)
- Django 5.2
- PostgreSQL (PostgreSQL 16 is used in CI)
- `psycopg` 3 and `dj-database-url`
- Server-rendered Django templates
- WhiteNoise for static files and Gunicorn as the production WSGI server
- pytest and pytest-django

Pinned Python dependencies are listed in [`requirements.txt`](requirements.txt).

## 5. Prerequisites

- Windows 10/11 with PowerShell for the commands in this guide
- Git
- Python 3.12 and the Python launcher (`py`)
- PostgreSQL 16 recommended (PostgreSQL is required; SQLite is not supported)
- A PostgreSQL client such as `psql` or pgAdmin to create a local database

## 6. Installation

Clone the repository and create a virtual environment from PowerShell:

```powershell
git clone https://github.com/23jr1a4455-eng/trustvault.git
Set-Location trustvault
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
python -m pip install -r requirements.txt
```

The dependency-installation command above installs the pinned packages from
[`requirements.txt`](requirements.txt).

If PowerShell blocks activation, allow scripts for the current terminal only,
then activate the environment:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Create the dedicated local PostgreSQL database as described in
[Database Setup and Migrations](#8-database-setup-and-migrations), then set
the matching `DATABASE_URL` in `.env` before running Django commands.

## 7. Environment Configuration

The settings module loads `.env` from the repository root with
`python-dotenv`. Copy `.env.example` to `.env` and replace its placeholders.
`.env` is ignored by Git; do not commit it. Settings use the process
environment as well, so deployment platforms can configure the same variables
directly.

| Variable | Required? | Purpose and local-development configuration |
|---|---|---|
| `SECRET_KEY` | Yes | Django signing and cryptographic secret. Required for every run. Generate a unique random value locally; when `DEBUG=0`, it must be at least 50 characters and cannot begin with Django's insecure prefix. |
| `DATABASE_URL` | Yes | PostgreSQL connection URL. Must begin with `postgres://` or `postgresql://`; use the local database, username, and URL-encoded password created in section 8. SQLite is not supported. |
| `DEBUG` | No | Debug mode. Defaults to `false`; set to `1` locally so the development server uses local HTTP and does not enable production-only requirements. Set to `0` in production. |
| `ALLOWED_HOSTS` | No | Comma-separated allowed hostnames. Defaults to `localhost,127.0.0.1`, suitable for the local server. Set the real hostnames when deployed. |
| `CSRF_TRUSTED_ORIGINS` | No | Comma-separated full origins, including scheme (for example, `https://<hostname>`). Defaults to an empty list; leave empty for local development unless your local setup needs a trusted origin. |
| `AUDIT_HMAC_KEY` | No in local debug; yes when `DEBUG=0` | Secret used to authenticate audit-chain rows. Local debug mode uses a fixed development-only key if this is unset. For production, set a separate random secret of at least 32 characters and keep it outside the database and source control. |
| `SEED_PASSWORD` | Only for demo seeding | Password used for newly created seed accounts. Set it to a disposable, strong local password before running `python manage.py seed`; the command validates it. Existing accounts' passwords are not reset. |
| `NEW_USER_PASSWORD` | No | Optional password for `python manage.py create_user`. If omitted, that command prompts interactively. |

Generate a Django secret key in PowerShell and copy the printed value into
`.env`:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Use a unique local `SECRET_KEY`; never reuse a production secret. URL-encode
special characters in the `DATABASE_URL` password.

## 8. Database Setup and Migrations

Start the local PostgreSQL service. Using pgAdmin, create a login role and an
empty database owned by that role; or, after installing PostgreSQL and making
`psql` available, substitute your own local values and run:

```powershell
psql -U postgres -c "CREATE ROLE <local-db-user> LOGIN PASSWORD '<local-password>';"
psql -U postgres -c "CREATE DATABASE <local-db-name> OWNER <local-db-user>;"
```

Set `DATABASE_URL` in `.env` to
`postgresql://<local-db-user>:<url-encoded-password>@localhost:5432/<local-db-name>`.
Replace all placeholders with your local values, and URL-encode special
characters in the password. If the role or database already exists, use
pgAdmin to verify or update it rather than rerunning the `CREATE` command.

With the local database running and `.env` configured, apply the committed
migrations:

```powershell
python manage.py migrate
```

The migrations create the application tables and install PostgreSQL-specific
append-only protections for audit events. Run the test suite against
PostgreSQL; a successful SQLite run would not verify those database-level
protections.

## 9. Creating Demo Data

Only run this command against a disposable development database (or another
disposable test database), never against production. Set `SEED_PASSWORD` in
that database's local `.env` to a strong, disposable password, then run:

```powershell
python manage.py seed
```

The seed command is safe to repeat on that disposable database. It creates
missing fake users, documents, files, and initial grants; it does not reset
existing users' passwords. All newly created seed users share the configured
`SEED_PASSWORD`:

| Username | Role |
|---|---|
| `meena` | Administrator |
| `priya` | Owner |
| `anita` | Owner |
| `ravi` | Viewer |
| `sunil` | Viewer |
| `kiran` | Viewer |

Demo documents and their contents are fake. These accounts and their shared
seed password are for local demonstration only. Do not seed production data
as part of local installation or use the seed password in a deployment.

To create an individual account instead, use the management command. It
prompts for a password unless `NEW_USER_PASSWORD` is set:

```powershell
python manage.py create_user <username> --role viewer --email user@example.com
```

The accepted roles are `admin`, `owner`, and `viewer`.

## 10. Running the Application

Activate the virtual environment, ensure the configured local PostgreSQL
database is running, and start the Django development server:

```powershell
.\.venv\Scripts\Activate.ps1
python manage.py runserver
```

Open <http://127.0.0.1:8000/> (also available at
<http://localhost:8000/>). The health check is at
<http://127.0.0.1:8000/health/>. Stop the server with **Ctrl+C** in the
PowerShell window where it is running.

## 11. Running Tests

Tests require the configured PostgreSQL database. Run the full suite with:

```powershell
pytest
```

For concise output:

```powershell
pytest -q
```

`pytest` runs the application's Django/pytest regression tests and is the
command used by the CI workflow, which provisions PostgreSQL 16. The separate
[`scripts/attack_check.py`](scripts/attack_check.py) script is an HTTP-level
adversarial check, not part of pytest or automatically run by that workflow.
It requires seeded demo users and reads their shared password from
`ATTACK_PASSWORD`. Run it only against your own disposable local development
instance and database:

```powershell
$env:ATTACK_PASSWORD = "<same-disposable-password-used-for-seeding>"
python scripts/attack_check.py --base http://127.0.0.1:8000 --proxy-header
```

The default script exercises anonymous, unauthorized, authorized, and hostile
input cases. Optional `--include-upload` and `--include-revocation` checks
create a temporary document and try to delete it during cleanup; use only a
disposable database, and check for leftover test data if the run is
interrupted. `--include-throttle` exercises login throttling using an invented
username. Do not point this script at a production service or database.

## 12. API and Endpoint Documentation

TrustVault currently provides a server-rendered web application, not a
versioned REST or JSON API. The routes below are defined in
[`vault/urls.py`](vault/urls.py). Document routes are authorized and audited.
Routes that change state accept POST requests; use the forms rendered by the
application, which include CSRF protection.

For methods, authentication, request formats, response types, and errors for
every route, see the [API and endpoint reference](docs/API.md).

| Route | Purpose | Access |
|---|---|---|
| `/`, `/login/`, `/logout/` | Home, sign-in, and sign-out | Public home/sign-in; sign-out requires authentication and POST |
| `/health/` | Host health check (`ok`) | Public |
| `/documents/` | List and search readable documents | Signed-in users; results are restricted to documents they may read |
| `/documents/new/` | Upload a document | Active users with the `owner` role |
| `/documents/trash/` | View one's deleted documents | Signed-in users; only one's own documents are listed |
| `/documents/<doc_id>/` | View document details | Owner or active read/edit grantee |
| `/documents/<doc_id>/download/` | Download a file | Owner or active read/edit grantee |
| `/documents/<doc_id>/edit/` | Change title/category | Owner or active edit grantee |
| `/documents/<doc_id>/replace/` | Replace stored file bytes | Owner or active edit grantee |
| `/documents/<doc_id>/delete/`, `/restore/` | Soft-delete or restore a document | Owner |
| `/documents/<doc_id>/access/` | View grants and pending suggestions | Owner |
| `/documents/<doc_id>/access/grant/` | Grant read or edit access | Owner |
| `/documents/<doc_id>/access/<grant_id>/revoke/` | Revoke a grant | Owner |
| `/documents/<doc_id>/access/suggest/` | Generate rule-based suggestions | Owner |
| `/documents/<doc_id>/access/suggestions/<id>/accept/`, `/reject/` | Decide on a suggestion | Owner |
| `/documents/<doc_id>/history/` | View audit history for a document | Owner |
| `/activity/`, `/activity/flags/`, `/activity/verify/` | Review audit activity, flags, and chain verification | Administrator; verification uses POST |
| `/users/`, `/users/<id>/disable/`, `/enable/` | List and enable/disable users | Administrator; changes use POST |

`<doc_id>` is a document UUID. Document access is checked on each request;
having an `admin` role does not bypass a document grant.

## 13. Security Verification

Run the regression suite and Django's checks:

```powershell
pytest -q
python manage.py check
python manage.py check --deploy
```

`check --deploy` reports deployment-sensitive configuration; review
host-specific warnings rather than assuming the local result validates a
deployment. Verify the audit chain with:

```powershell
python manage.py verify_audit
```

To also verify against saved external anchors:

```powershell
python manage.py verify_audit --anchors docs/anchors.log
```

An anchor can be printed only after the chain verifies:

```powershell
python manage.py anchor
```

Store generated anchors somewhere outside the application database and
deployment filesystem if they are intended to protect against an attacker who
can rewrite both. See [`docs/threat-model/`](docs/threat-model/) for threat
model artifacts and [`SECURITY-REVIEW.md`](SECURITY-REVIEW.md) for recorded
review findings and validation limits. The latest available GitHub Actions
results observed on 2026-10-25 were successful CI
([run](https://github.com/23jr1a4455-eng/TrustVault/actions/runs/40101618614))
and security
([run](https://github.com/23jr1a4455-eng/TrustVault/actions/runs/40101618630))
workflow runs on commit `b6e16f4`. Those results do not verify the hosting
provider, its proxy, or runtime configuration.

## 14. Deployment

There is no deployment workflow or provider configuration checked into this
repository. The CI workflow tests the application; it does not deploy it. A
Render URL and Render/Gunicorn/WhiteNoise settings have appeared in earlier
project notes, but the provider configuration and end-to-end deployment
procedure cannot be verified from the checked-in project. Therefore this
README does not present a build/start command as a tested deployment recipe.
Confirm the current deployment process and service status in the hosting
provider before relying on that URL.

The Django settings require a PostgreSQL `DATABASE_URL` and, with `DEBUG=0`,
strong `SECRET_KEY` and `AUDIT_HMAC_KEY` values. They also assume the trusted
proxy overwrites `X-Forwarded-Proto` correctly. These are configuration
requirements, not evidence that a particular production deployment has been
tested. Uploaded file bytes are stored in PostgreSQL and count toward its
storage capacity.

## 15. Limitations and Known Issues

- PostgreSQL is required; SQLite is not a supported database.
- File bytes are stored in PostgreSQL. The maximum upload size is 25 MB, and
  document files contribute to database storage consumption.
- Replacing a document overwrites its current file; the application does not
  provide file version history.
- Sharing suggestions use document category and existing grants only. They are
  deterministic rules, not AI-generated recommendations.
- The application does not implement folder permissions, public share links,
  full-text search inside document contents, or single sign-on.
- Seed data is for local demonstration only and uses one configured password
  for all newly seeded accounts.
- Production deployment and external anchor retention must be configured and
  operated separately; repository settings cannot establish the security of
  the hosting environment.
- The latest available GitHub Actions CI and security workflow runs on commit
  `b6e16f4` completed successfully ([CI](https://github.com/23jr1a4455-eng/TrustVault/actions/runs/40101618614),
  [security](https://github.com/23jr1a4455-eng/TrustVault/actions/runs/40101618630)).
  The security workflow runs Bandit, `pip-audit`, and Semgrep; this is
  evidence for that revision only, not a guarantee against all vulnerabilities.
- The security review records no unresolved confirmed remote-user finding.
  Its earlier denial-audit concern was conditional and is not active while
  `ATOMIC_REQUESTS=False`; a regression test checks this setting. The review
  notes that privileged direct database access is outside the protection of
  application ORM guards, and that deployment proxy behavior was not
  independently verified.
- Upload validation checks file structure but is not malware scanning.
- The repository does not verify external retention of audit anchors or
  production secret backup/rotation. Configure and test those operational
  controls separately.
- No deployment procedure has been validated from the checked-in deployment
  configuration because no deployment workflow or host manifest is present.

## 16. Project Structure

```text
config/                  Compatibility settings and URL modules
trustvault/              Django project settings, URLs, WSGI, and ASGI
vault/                   Application models, authorization, views, services,
                         upload handling, templates, and migrations
vault/management/        User, seed, audit verification, and anchor commands
tests/                   pytest regression and security tests
docs/threat-model/       Threat model diagrams and source data
.github/workflows/       CI and security workflows
requirements.txt         Pinned Python dependencies
```


## Demo Video

Watch the TrustVault project demonstration:

[**Watch the TrustVault Demo Video**](https://drive.google.com/file/d/1WgEyeRXehFRi8Eh0stPSnW4lDCni5iYQ/view?usp=sharing)

The demonstration covers the application's main features, document access controls, audit logging, and security-testing process, including known limitations.
