"""Pages for administrators (users, activity, flags) and the per-document history for owners."""

from django import forms
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render

from vault.authorization import HISTORY
from vault.guards import admin_only, gated
from vault.models import AuditEvent, Document
from vault.services import audit, users
from vault.services.audit_chain import verify_chain
from vault.services.flags import find_flags

GROUPS = {
    "all": ("Everything", Q()),
    "permissions": ("Permission changes", Q(action__startswith="grant.") | Q(action__in=["document.deleted", "document.restored"])),
    "denied": ("Refused attempts", Q(allowed=False)),
    "downloads": ("Downloads and uploads", Q(action__in=["document.download", "document.uploaded", "document.file_replaced"])),
    "auth": ("Sign-ins", Q(action__startswith="auth.")),
    "admin": ("Administrator actions", Q(action__startswith="admin.") | Q(action__startswith="user.") | Q(action__startswith="audit.")),
}


class ActivityForm(forms.Form):
    group = forms.ChoiceField(required=False, choices=[(k, v[0]) for k, v in GROUPS.items()])
    actor = forms.CharField(required=False, max_length=150)
    document = forms.UUIDField(required=False)
    date_from = forms.DateField(required=False)
    date_to = forms.DateField(required=False)
    page = forms.IntegerField(required=False, min_value=1, max_value=100000)


def _with_titles(events):
    ids = {e.document_id for e in events if e.document_id}
    titles = dict(Document.objects.filter(pk__in=ids).values_list("pk", "title"))
    for event in events:
        event.document_title = titles.get(event.document_id, "") if event.document_id else ""
    return events


def _filtered(form):
    data = form.cleaned_data if form.is_valid() else None
    if data is None:
        return AuditEvent.objects.none()
    events = AuditEvent.objects.filter(GROUPS[data.get("group") or "all"][1])
    if data.get("actor"):
        events = events.filter(actor_name__iexact=data["actor"])
    if data.get("document"):
        events = events.filter(document_id=data["document"])
    if data.get("date_from"):
        events = events.filter(created_at__date__gte=data["date_from"])
    if data.get("date_to"):
        events = events.filter(created_at__date__lte=data["date_to"])
    return events.order_by("-created_at", "-id")


@admin_only
def admin_activity(request):
    form = ActivityForm(request.GET)
    page = Paginator(_filtered(form), 50).get_page((form.cleaned_data.get("page") if form.is_valid() else None) or 1)
    page.object_list = _with_titles(list(page.object_list))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "vault/admin_activity.html", {
        "form": form, "form_invalid": not form.is_valid(), "page": page, "groups": GROUPS,
        "current_group": (form.cleaned_data.get("group") if form.is_valid() else "") or "all",
        "querystring": params.urlencode(),
    })


@admin_only
def admin_flags(request):
    return render(request, "vault/admin_flags.html", {"flags": find_flags()})


@admin_only
def admin_verify(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    report = verify_chain()
    audit.record(actor=request.user, action="audit.verified", allowed=report.ok, request=request,
                 detail={"checked": report.checked, "problems": len(report.problems)})
    return render(request, "vault/admin_verify.html", {"report": report}, status=200 if report.ok else 409)


@admin_only
def admin_users(request):
    return render(request, "vault/admin_users.html", {
        "people": get_user_model().objects.order_by("username"), "error": request.GET.get("error"),
    })


def _change_user(request, user_id, action):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    target = get_object_or_404(get_user_model(), pk=user_id)
    try:
        action(target=target, by=request.user, request=request)
    except users.UserChangeRefused as refused:
        return render(request, "vault/admin_users.html", {
            "people": get_user_model().objects.order_by("username"), "error": str(refused),
        }, status=400)
    return redirect("admin_users")


@admin_only
def admin_user_disable(request, user_id):
    return _change_user(request, user_id, users.disable_user)


@admin_only
def admin_user_enable(request, user_id):
    return _change_user(request, user_id, users.enable_user)


@gated(HISTORY)
def document_history(request, document):
    """The owner sees who opened, downloaded, changed or was refused on their own document."""
    if request.method not in ("GET", "HEAD"):
        return HttpResponseNotAllowed(["GET", "HEAD"])
    events = AuditEvent.objects.filter(document_id=document.pk).order_by("-created_at", "-id")
    page = Paginator(events, 50).get_page(request.GET.get("page") or 1)
    return render(request, "vault/document_history.html", {"document": document, "page": page})
