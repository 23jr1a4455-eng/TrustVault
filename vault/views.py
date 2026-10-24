import hashlib
import io
from contextlib import contextmanager

from django import forms
from django.contrib.auth import logout
from django.contrib.auth import views as auth_views
from django.db import transaction
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.utils import timezone

from vault import throttle
from vault.authorization import DELETE, DOWNLOAD, EDIT, READ, RESTORE, SHARE, authorize, can
from vault.guards import authenticated, gated, public, uploader
from vault.models import Document, DocumentFile, Grant
from vault.selectors import readable_categories, search_documents
from vault.services import audit, grants, uploads


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


class SearchForm(forms.Form):
    q = forms.CharField(required=False, max_length=100)
    owner = forms.CharField(required=False, max_length=150)
    category = forms.CharField(required=False, max_length=100)
    date_from = forms.DateField(required=False)
    date_to = forms.DateField(required=False)
    page = forms.IntegerField(required=False, min_value=1, max_value=100000)


@authenticated
def document_list(request):
    form = SearchForm(request.GET)
    valid = form.is_valid()
    filters = {k: v for k, v in (form.cleaned_data if valid else {}).items() if k != "page" and v}
    # An unreadable search shows nothing (and a message) rather than quietly widening to everything.
    results = search_documents(request.user, **filters) if valid else Document.objects.none()
    page = Paginator(results, 20).get_page((form.cleaned_data.get("page") if valid else None) or 1)
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "vault/document_list.html", {
        "form": form, "form_invalid": not valid, "page": page,
        "total": page.paginator.count, "categories": readable_categories(request.user),
        "querystring": params.urlencode(),
    })


@authenticated
def document_trash(request):
    deleted = Document.objects.filter(owner=request.user, deleted_at__isnull=False).order_by("-deleted_at")
    return render(request, "vault/document_trash.html", {"documents": deleted})


def _detail_context(request, document, **extra):
    stored = DocumentFile.objects.filter(document=document).only("original_name", "size").first()
    return {
        "document": document,
        "stored_file": stored,
        "can_edit": can(request.user, document, EDIT),
        "can_delete": can(request.user, document, DELETE),
        "can_share": can(request.user, document, SHARE),
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


@contextmanager
def _locked_document_for_write(request, document, action):
    while True:
        denied = False
        with transaction.atomic():
            current = Document.objects.select_for_update().get(pk=document.pk)
            if current.deleted_at is not None or not can(request.user, current, action):
                denied = True
            else:
                yield current
                return
        if denied:
            authorize(request.user, document.pk, action, request=request)


@gated(EDIT)
def document_edit(request, document):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    form = DocumentEditForm(request.POST)
    if not form.is_valid():
        context = _detail_context(request, document, errors=form.errors)
        return render(request, "vault/document_detail.html", context, status=400)
    with _locked_document_for_write(request, document, EDIT) as current:
        changed = [f for f in ("title", "category") if getattr(current, f) != form.cleaned_data[f]]
        current.title = form.cleaned_data["title"]
        current.category = form.cleaned_data["category"]
        current.save(update_fields=["title", "category", "updated_at"])
        audit.record(
            actor=request.user,
            action="document.updated",
            allowed=True,
            document_id=current.pk,
            request=request,
            detail={"fields": changed},  # names only, never the values
        )
    return redirect("document_detail", doc_id=current.pk)


@gated(DELETE)
def document_delete(request, document):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    with _locked_document_for_write(request, document, DELETE) as current:
        current.deleted_at = timezone.now()
        current.save(update_fields=["deleted_at", "updated_at"])
        revoked = grants.revoke_all(document=current, by=request.user)
        audit.record(
            actor=request.user,
            action="document.deleted",
            allowed=True,
            document_id=current.pk,
            request=request,
            detail={"grants_revoked": revoked},
        )
    return redirect("document_list")


@gated(DOWNLOAD)
def document_download(request, document):
    if request.method not in ("GET", "HEAD"):
        return HttpResponseNotAllowed(["GET", "HEAD"])
    stored = DocumentFile.objects.filter(document=document).first()
    if stored is None:
        raise Http404
    data = bytes(stored.data)  # PostgreSQL hands back a memoryview
    if hashlib.sha256(data).hexdigest() != stored.sha256:
        audit.record(
            actor=request.user,
            action="document.integrity_failure",
            allowed=False,
            document_id=document.pk,
            request=request,
        )
        raise RuntimeError("Stored file failed its integrity check.")
    response = FileResponse(
        io.BytesIO(data),
        as_attachment=True,
        filename=stored.original_name,
        content_type=stored.content_type,
    )
    # The browser must save this, never render it, and must not let it run anything.
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


class UploadForm(forms.Form):
    title = forms.CharField(max_length=200, required=False)
    category = forms.CharField(max_length=100, required=False)
    file = forms.FileField()


def _declared_length(request):
    try:
        return int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        return 0


def _read_and_inspect(form):
    uploaded = form.cleaned_data["file"]
    if uploaded.size > uploads.MAX_UPLOAD_BYTES:
        raise uploads.UploadRejected("too_large")
    data = uploaded.read()
    return data, uploads.inspect_upload(uploaded.name, data), uploaded.size


def _upload_page(request, form, error=None, status=200):
    return render(request, "vault/document_upload.html", {"form": form, "error": error}, status=status)


@uploader
def document_upload(request):
    if request.method == "GET":
        return _upload_page(request, UploadForm())
    if request.method != "POST":
        return HttpResponseNotAllowed(["GET", "POST"])
    if _declared_length(request) > uploads.MAX_UPLOAD_BYTES + uploads.MAX_MULTIPART_OVERHEAD_BYTES:
        audit.record(actor=request.user, action="document.upload_rejected", allowed=False,
                     request=request, detail={"reason": "too_large"})
        request._upload_rejection_logged = True
        return _upload_page(request, UploadForm(), uploads.MESSAGES["too_large"], status=413)
    form = UploadForm(request.POST, request.FILES)
    if getattr(request, "upload_too_large", False):
        audit.record(
            actor=request.user,
            action="document.upload_rejected",
            allowed=False,
            request=request,
            detail={"reason": "too_large"},
        )
        request._upload_rejection_logged = True
        return _upload_page(request, form, uploads.MESSAGES["too_large"], status=413)
    if not form.is_valid():
        return _upload_page(request, form, "Please choose a file.", status=400)
    try:
        data, info, declared_size = _read_and_inspect(form)
    except uploads.UploadRejected as problem:
        audit.record(actor=request.user, action="document.upload_rejected", allowed=False,
                     request=request, detail={"reason": problem.code})
        status = 413 if problem.code == "too_large" else 400
        return _upload_page(request, form, problem.message, status=status)
    title = form.cleaned_data["title"].strip() or info.safe_name.rsplit(".", 1)[0]
    # Document, file bytes and the audit row succeed or fail together: no audit row,
    # no stored document.
    with transaction.atomic():
        document = Document.objects.create(
            owner=request.user, title=title[:200], category=form.cleaned_data["category"]
        )
        DocumentFile.objects.create(
            document=document,
            original_name=info.safe_name,
            content_type=info.content_type,
            size=info.size,
            sha256=info.sha256,
            data=data,
            uploaded_by=request.user,
        )
        audit.record(
            actor=request.user,
            action="document.uploaded",
            allowed=True,
            document_id=document.pk,
            request=request,
            detail={"kind": info.kind, "size": info.size, "sha256": info.sha256},
        )
    return redirect("document_detail", doc_id=document.pk)


class FileOnlyForm(forms.Form):
    file = forms.FileField()


@gated(EDIT)
def document_replace(request, document):
    """An editor swaps in a new file. The old bytes are overwritten (no version history
    is kept); the audit row records the hash of the old and the new file."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    form = FileOnlyForm(request.POST, request.FILES)
    problem = None
    if getattr(request, "upload_too_large", False):
        problem = uploads.UploadRejected("too_large")
    elif not form.is_valid():
        problem = uploads.UploadRejected("empty")
    else:
        try:
            data, info, _ = _read_and_inspect(form)
        except uploads.UploadRejected as rejected:
            problem = rejected
    if problem is not None:
        audit.record(actor=request.user, action="document.upload_rejected", allowed=False,
                     document_id=document.pk, request=request, detail={"reason": problem.code})
        if problem.code == "too_large":
            request._upload_rejection_logged = True
        context = _detail_context(request, document, upload_error=problem.message)
        status = 413 if problem.code == "too_large" else 400
        return render(request, "vault/document_detail.html", context, status=status)
    with _locked_document_for_write(request, document, EDIT) as current:
        stored = DocumentFile.objects.select_for_update().filter(document=current).first()
        old_hash = stored.sha256 if stored else None
        if stored is None:
            stored = DocumentFile(document=current, uploaded_by=request.user)
        stored.original_name, stored.content_type = info.safe_name, info.content_type
        stored.size, stored.sha256, stored.data = info.size, info.sha256, data
        stored.uploaded_by = request.user
        stored.save()
        current.save(update_fields=["updated_at"])
        audit.record(
            actor=request.user,
            action="document.file_replaced",
            allowed=True,
            document_id=current.pk,
            request=request,
            detail={"old_sha256": old_hash, "new_sha256": info.sha256, "size": info.size},
        )
    return redirect("document_detail", doc_id=current.pk)


@gated(RESTORE)
def document_restore(request, document):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if document.deleted_at is None:
        raise Http404
    with transaction.atomic():
        document.deleted_at = None
        document.save(update_fields=["deleted_at", "updated_at"])
        audit.record(
            actor=request.user,
            action="document.restored",
            allowed=True,
            document_id=document.pk,
            request=request,
            detail={"grants_restored": 0},  # old grants stay revoked; the owner shares again
        )
    return redirect("document_detail", doc_id=document.pk)


class GrantForm(forms.Form):
    username = forms.CharField(max_length=150)
    level = forms.CharField(max_length=4)
    expires_on = forms.DateField(required=False)


def _access_context(document, **extra):
    unrevoked = (
        Grant.objects.unrevoked()
        .filter(document=document)
        .select_related("user")
        .order_by("user__username")
    )
    return {"document": document, "grants": unrevoked, **extra}


@gated(SHARE)
def document_access(request, document):
    if request.method not in ("GET", "HEAD"):
        return HttpResponseNotAllowed(["GET", "HEAD"])
    return render(request, "vault/document_access.html", _access_context(document))


@gated(SHARE)
def document_grant(request, document):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    form = GrantForm(request.POST)
    error = None
    if form.is_valid():
        try:
            grants.grant_access(
                document=document, by=request.user,
                username=form.cleaned_data["username"], level=form.cleaned_data["level"],
                expires_on=form.cleaned_data["expires_on"], request=request,
            )
            return redirect("document_access", doc_id=document.pk)
        except grants.GrantRefused as refused:
            error = refused.message
    else:
        error = "Please check the form and try again."
    return render(request, "vault/document_access.html", _access_context(document, error=error), status=400)


@gated(SHARE)
def document_revoke(request, document, grant_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    grants.revoke_access(document=document, grant_id=grant_id, by=request.user, request=request)
    return redirect("document_access", doc_id=document.pk)
