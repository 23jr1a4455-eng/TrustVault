# TrustVault

## Development setup

1. Create and activate a Python virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env`, then set a unique `SECRET_KEY` and the
   appropriate `DATABASE_URL`. `.env` is excluded from version control.
4. Start the development server with `python manage.py runserver`.

`DATABASE_URL` accepts SQLite and PostgreSQL URLs. When it is omitted, the
project uses a local SQLite database. Set `DEBUG=0` and configure production
hosts, origins, and TLS before deployment; never deploy with the example
secret key.

Document routes must authorize each requested action and record both allowed
and denied decisions in the append-only audit log before responding. Deny by
default, return 404 when a user cannot read a document, and never trust
uploaded filenames or content types. Authentication or authorization changes
must include a test that fails if the check is removed.


## What it is
TrustVault is a secure, enterprise-grade document sharing and collaboration platform featuring a custom user model, database-driven permissions, hidden administrative routing, and append-only hash-chained auditing.

## Live URL
- [TrustVault Live Application](https://trustvault-app-1tp1.onrender.com)

## Demo accounts
- **Admin User**: `admin@trustvault.com` (configured via initial seed data)
- **Standard User**: [Add demo user details here]

## Run locally
1. Clone the repository and navigate to the project root.
2. Create and activate a virtual environment:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
Install dependencies:

PowerShell
pip install -r requirements.txt
Run migrations and seed local database:

PowerShell
python manage.py migrate
python manage.py seed
Start the development server:

PowerShell
python manage.py runserver
Deploy
Deployed continuously to Render via GitHub integration using Gunicorn and WhiteNoise for static files.

Build Command: pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate

Start Command: gunicorn config.wsgi

Docs
Architecture and Threat Modeling: docs/threat-model/

Implementation plans, specs, and security checklists: specs/