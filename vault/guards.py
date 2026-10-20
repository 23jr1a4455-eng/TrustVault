"""Route markers. Every route must declare how it is protected, or a test fails."""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login

from vault.authorization import authorize
from vault.services import audit


def public(view):
    """Anyone may call this route (health check, login)."""
    view.access = "public"
    return view


def authenticated(view):
    """Needs a login but is about no single document (the list of my documents)."""
    wrapped = login_required(view)
    wrapped.access = "authenticated"
    return wrapped


def gated(action):
    """Run the authorisation gate before the view; the view receives the document."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, doc_id, *args, **kwargs):
            if not request.user.is_authenticated:
                audit.record(
                    actor=None,
                    action=f"document.{action}",
                    allowed=False,
                    document_id=doc_id,
                    request=request,
                    detail={"reason": "anonymous"},
                )
                return redirect_to_login(request.get_full_path())
            document = authorize(request.user, doc_id, action, request=request)
            return view(request, document, *args, **kwargs)

        wrapper.access = "gated"
        wrapper.action = action
        return wrapper

    return decorator
