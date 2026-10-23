"""Route markers. Every route must declare how it is protected, or a test fails."""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.http import Http404
from django.utils.cache import add_never_cache_headers

from vault.authorization import authorize, authorize_upload


def public(view):
    """Anyone may call this route (health check, login)."""
    view.access = "public"
    return view


def authenticated(view):
    """Needs a login but is about no single document (the list of my documents)."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        response = view(request, *args, **kwargs)
        add_never_cache_headers(response)
        return response

    wrapped = login_required(wrapper)
    wrapped.access = "authenticated"
    return wrapped


def uploader(view):
    """Creating a new document: owners only. The decision lives in authorize_upload()."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        authorize_upload(request.user, request)
        response = view(request, *args, **kwargs)
        add_never_cache_headers(response)
        return response

    wrapped = login_required(wrapper)
    wrapped.access = "uploader"
    return wrapped


def gated(action):
    """Run the authorisation gate before the view; the view receives the document.

    Everyone, including anonymous visitors, goes through authorize(). The only thing
    done here is to send a refused anonymous visitor to the login page instead of
    showing a 404, which tells them nothing about whether the document exists.
    """

    def decorator(view):
        @wraps(view)
        def wrapper(request, doc_id, *args, **kwargs):
            try:
                document = authorize(request.user, doc_id, action, request=request)
            except Http404:
                if not request.user.is_authenticated:
                    return redirect_to_login(request.get_full_path())
                raise
            response = view(request, document, *args, **kwargs)
            add_never_cache_headers(response)  # documents must never sit in a cache
            return response

        wrapper.access = "gated"
        wrapper.action = action
        return wrapper

    return decorator
