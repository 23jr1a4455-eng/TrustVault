"""WSGI config for TrustVault."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "trustvault.settings")

application = get_wsgi_application()
