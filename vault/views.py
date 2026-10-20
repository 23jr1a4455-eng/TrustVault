from django import forms
from django.contrib.auth import logout
from django.contrib.auth import views as auth_views
from django.db import transaction
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.utils import timezone

from vault import throttle
from vault.authorization import DELETE, EDIT, READ, can
from vault.guards import authenticated, gated, public
from vault.selectors import readable_documents
from vault.services import audit


@public
def health(request):
    return HttpResponse("ok")


@public
def home(request):
    return redirect("document_list" if request.user.is_authenticated else "login")


class ThrottledLoginView(auth_views.LoginView):
    template_name = "vault/login.html"
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        username = request.POST.get("username", "")
        if throttle.is_blocked(request, username):
            audit.record(
                actor=None,
                action="auth.login_throttled",
                allowed=False,
                request=request,
                detail={"username": username[:64]},
            )
            return render(request, "vault/throttled.html", status=429)
        return super().post(request, *args, **kwargs)


login_view = public(ThrottledLoginView.as_view())


@authenticated
def logout_view(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    logout(request)
    return redirect("login")


@authenticated
def document_list(request):
    documents = readable_documents(request.user).select_related("owner").order_by("-created_at")
    return render(request, "vault/document_list.html", {"documents": documents})


def _detail_context(request, document, **extra):
    return {
        "document": document,
        "can_edit": can(request.user, document, EDIT),
        "can_delete": can(request.user, document, DELETE),
        **extra,
    }


@gated(READ)
def document_detail(request, document):
    if request.method not in ("GET", "HEAD"):
        return HttpResponseNotAllowed(["GET", "HEAD"])
    return render(request, "vault/document_detail.html", _detail_context(request, document))


class DocumentEditForm(forms.Form):
    # Only these two fields exist, so a request cannot change the owner or anything else.
    title = forms.CharField(max_length=200)
    category = forms.CharField(max_length=100, required=False)


@gated(EDIT)
def document_edit(request, document):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    form = DocumentEditForm(request.POST)
    if not form.is_valid():
        context = _detail_context(request, document, errors=form.errors)
        return render(request, "vault/document_detail.html", context, status=400)
    changed = [f for f in ("title", "category") if getattr(document, f) != form.cleaned_data[f]]
    with transaction.atomic():
        document.title = form.cleaned_data["title"]
        document.category = form.cleaned_data["category"]
        document.save()
        audit.record(
            actor=request.user,
            action="document.updated",
            allowed=True,
            document_id=document.pk,
            request=request,
            detail={"fields": changed},  # names only, never the values
        )
    return redirect("document_detail", doc_id=document.pk)


@gated(DELETE)
def document_delete(request, document):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    with transaction.atomic():
        document.deleted_at = timezone.now()
        document.save(update_fields=["deleted_at", "updated_at"])
        audit.record(
            actor=request.user,
            action="document.deleted",
            allowed=True,
            document_id=document.pk,
            request=request,
        )
    return redirect("document_list")
