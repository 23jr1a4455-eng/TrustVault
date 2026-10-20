"""Audit hooks for sign-in and sign-out."""

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from vault import throttle
from vault.services import audit


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    throttle.clear(request, user.get_username())
    audit.record(actor=user, action="auth.login", allowed=True, request=request)


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    if user is not None:
        audit.record(actor=user, action="auth.logout", allowed=True, request=request)


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request=None, **kwargs):
    # Only the username is kept, never the password. People do sometimes type a
    # password into the username box, so the value is cut short.
    username = str(credentials.get("username", ""))[:64]
    throttle.register_failure(request, username)
    audit.record(
        actor=None,
        action="auth.login_failed",
        allowed=False,
        request=request,
        detail={"username": username},
    )
