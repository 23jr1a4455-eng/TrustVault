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