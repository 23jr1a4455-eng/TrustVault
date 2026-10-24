from django.http import HttpResponse, HttpResponseBadRequest
from django.urls import Resolver404, resolve

from vault.authorization import EDIT, authorize, authorize_upload
from vault.services import audit
from vault.services import uploads

CONTENT_SECURITY_POLICY = (
    "default-src 'none'; style-src 'self'; img-src 'self'; form-action 'self'; "
    "frame-ancestors 'none'; base-uri 'none'"
)
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"


class GenericNotFoundMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code == 404:
            response.content = b"Not found."
            response.headers["Content-Type"] = "text/plain; charset=utf-8"
            response.headers.pop("Content-Length", None)
        return response


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        response.headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        return response


def _authorize_and_audit_oversized_upload(request, reason):
    try:
        match = resolve(request.path_info)
    except Resolver404:
        return

    document_id = None
    if match.url_name == "document_upload":
        authorize_upload(request.user, request)
    elif match.url_name == "document_replace":
        document = authorize(request.user, match.kwargs["doc_id"], EDIT, request=request)
        document_id = document.pk
    else:
        return

    audit.record(
        actor=request.user,
        action="document.upload_rejected",
        allowed=False,
        document_id=document_id,
        request=request,
        detail={"reason": reason},
    )
    request._upload_rejection_logged = True


class UploadRequestSizeLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in {"POST", "PUT", "PATCH"} and request.content_type == "multipart/form-data":
            raw_length = request.META.get("CONTENT_LENGTH")
            if raw_length:
                try:
                    content_length = int(raw_length)
                except ValueError:
                    _authorize_and_audit_oversized_upload(request, "invalid_length")
                    return HttpResponseBadRequest("Invalid request body length.")
                if content_length < 0:
                    _authorize_and_audit_oversized_upload(request, "invalid_length")
                    return HttpResponseBadRequest("Invalid request body length.")
                if content_length > uploads.MAX_UPLOAD_BYTES + uploads.MAX_MULTIPART_OVERHEAD_BYTES:
                    _authorize_and_audit_oversized_upload(request, "too_large")
                    return HttpResponse("Request body too large.", status=413)

        response = self.get_response(request)
        if getattr(request, "upload_too_large", False):
            if not getattr(request, "_upload_rejection_logged", False):
                _authorize_and_audit_oversized_upload(request, "too_large")
            return HttpResponse("Request body too large.", status=413)
        return response
