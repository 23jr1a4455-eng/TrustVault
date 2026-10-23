import hashlib
import io

from django import forms
from django.contrib.auth import logout
from django.contrib.auth import views as auth_views
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.utils import timezone

from vault import throttle
from vault.authorization import DELETE, DOWNLOAD, EDIT, READ, can
from vault.guards import authenticated, gated, public, uploader
from vault.models import Document, DocumentFile
from vault.selectors import readable_documents
from vault.services import audit, uploads


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
    stored = DocumentFile.objects.filter(document=document).only("original_name", "size").first()
    return {
        "document": document,
        "stored_file": stored,
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


def _upload_page(request, form, error=None, status=200):
    return render(request, "vault/document_upload.html", {"form": form, "error": error}, status=status)


@uploader
def document_upload(request):
    if request.method == "GET":
        return _upload_page(request, UploadForm())
    if request.method != "POST":
        return HttpResponseNotAllowed(["GET", "POST"])
    if _declared_length(request) > uploads.MAX_UPLOAD_BYTES + 1_000_000:
        audit.record(actor=request.user, action="document.upload_rejected", allowed=False,
                     request=request, detail={"reason": "too_large"})
        return _upload_page(request, UploadForm(), uploads.MESSAGES["too_large"], status=413)
    form = UploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return _upload_page(request, form, "Please choose a file.", status=400)
    uploaded = form.cleaned_data["file"]
    try:
        if uploaded.size > uploads.MAX_UPLOAD_BYTES:
            raise uploads.UploadRejected("too_large")
        data = uploaded.read()
        info = uploads.inspect_upload(uploaded.name, data)
    except uploads.UploadRejected as problem:
        audit.record(actor=request.user, action="document.upload_rejected", allowed=False,
                     request=request, detail={"reason": problem.code, "size": uploaded.size})
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
