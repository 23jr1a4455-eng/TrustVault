#!/usr/bin/env python3
"""A judge in a box: logs in as different people and tries to reach documents it should not.

Standard library only (no installs). Run it against YOUR OWN site, local or live:

    python scripts/attack_check.py --base http://127.0.0.1:8000 --proxy-header
    python scripts/attack_check.py --base https://your-app.onrender.com --include-upload --include-revocation

The password for the demo accounts comes from the ATTACK_PASSWORD environment variable.
Exit code 0 = every check passed, 1 = at least one FAILED.
"""

import argparse
import hashlib
import http.client
import io
import os
import re
import sys
import uuid
import zipfile
from urllib.parse import quote, urlencode, urlsplit

METHODS = ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"]
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))


class Response:
    def __init__(self, status, headers, body, cookies):
        self.status, self.headers, self.body, self.cookies = status, headers, body, cookies

    @property
    def text(self):
        return self.body.decode("utf-8", "replace")

    def digest(self):
        return (self.status, hashlib.sha256(self.body).hexdigest())


class Client:
    def __init__(self, base, proxy_header=False):
        parts = urlsplit(base)
        self.https = parts.scheme == "https"
        self.host, self.port = parts.hostname, parts.port or (443 if self.https else 80)
        self.netloc = parts.netloc
        self.proxy_header = proxy_header
        self.jar = {}

    def request(self, method, path, data=None, headers=None, body=None, referer=None):
        conn_class = http.client.HTTPSConnection if self.https else http.client.HTTPConnection
        conn = conn_class(self.host, self.port, timeout=30)
        sent = {"User-Agent": "trustvault-attack-check", **(headers or {})}
        if self.jar:
            sent["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.jar.items())
        if self.proxy_header:
            sent["X-Forwarded-Proto"] = "https"
        if referer:  # Django insists on a same-site Referer for HTTPS form posts
            sent["Referer"] = f"https://{self.netloc}{referer}"
        if data is not None:
            body = urlencode(data)
            sent["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            conn.request(method, path, body=body, headers=sent)
            raw = conn.getresponse()
            content = raw.read()
            headers_out = {k.lower(): v for k, v in raw.getheaders()}
            set_cookies = [v for k, v in raw.getheaders() if k.lower() == "set-cookie"]
        finally:
            conn.close()
        for cookie in set_cookies:
            name, _, rest = cookie.partition("=")
            value = rest.split(";", 1)[0]
            if value == "" or "max-age=0" in cookie.lower():
                self.jar.pop(name, None)
            else:
                self.jar[name] = value
        return Response(raw.status, headers_out, content, set_cookies)

    def token(self, page="/documents/"):
        found = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', self.request("GET", page).text)
        return found.group(1) if found else ""

    def post(self, path, data=None, page="/documents/", **kwargs):
        fields = dict(data or {})
        fields["csrfmiddlewaretoken"] = self.token(page)
        return self.request("POST", path, data=fields, referer=page, **kwargs)

    def login(self, username, password):
        page = "/login/"
        form = self.request("GET", page)
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', form.text)
        return self.request("POST", page, data={"username": username, "password": password,
                                               "csrfmiddlewaretoken": token.group(1) if token else ""}, referer=page)


def person(base, proxy, name, password):
    client = Client(base, proxy)
    reply = client.login(name, password)
    if reply.status != 302:
        sys.exit(f"Could not sign in as {name} (status {reply.status}). Is ATTACK_PASSWORD right and the user seeded?")
    return client


def find_document(client, title_start):
    page = client.request("GET", "/documents/").text
    found = re.search(r'href="/documents/([0-9a-f-]{36})/">' + re.escape(title_start), page)
    return found.group(1) if found else None


def doc_routes(doc_id):
    d = f"/documents/{doc_id}/"
    return [d, d + "download/", d + "edit/", d + "delete/", d + "replace/", d + "restore/", d + "access/",
            d + "access/grant/", d + "access/suggest/", d + "access/1/revoke/", d + "access/suggestions/1/accept/",
            d + "access/suggestions/1/reject/", d + "history/"]


ADMIN_ROUTES = ["/activity/", "/activity/flags/", "/activity/verify/", "/users/", "/users/1/disable/", "/users/1/enable/"]


def suite_anonymous(base, proxy, doc_id, title):
    print("\n== Not signed in ==")
    anon = Client(base, proxy)
    check("health check answers", anon.request("GET", "/health/").status == 200)
    bad = []
    for path in doc_routes(doc_id) + ADMIN_ROUTES + ["/documents/new/", "/documents/", "/documents/trash/"]:
        for method in ("GET", "POST"):
            reply = anon.request(method, path)
            if reply.status in (200, 500) or title.encode() in reply.body:
                bad.append(f"{method} {path} -> {reply.status}")
    check("no document or admin page is reachable without signing in", not bad, "; ".join(bad[:3]))
    check("Django admin is not exposed", anon.request("GET", "/admin/").status == 404)
    leaks = [p for p in ("/.env", "/.git/HEAD", "/manage.py", "/requirements.txt", "/db.sqlite3",
                         "/trustvault/settings.py", "/static/../trustvault/settings.py", "/static/%2e%2e/manage.py")
             if anon.request("GET", p).status == 200]
    check("no source, secret or database files are served", not leaks, ", ".join(leaks))
    check("a forged Host header is refused", anon.request("GET", "/login/", headers={"Host": "evil.example"}).status == 400)
    login = anon.request("GET", "/login/")
    for header, expected in (("x-content-type-options", "nosniff"), ("x-frame-options", "DENY"),
                             ("referrer-policy", "same-origin"), ("cross-origin-resource-policy", "same-origin")):
        check(f"login page sends {header}", login.headers.get(header) == expected, login.headers.get(header))
    csp = login.headers.get("content-security-policy", "")
    check("login page sends a strict Content-Security-Policy", "default-src 'none'" in csp and "frame-ancestors 'none'" in csp)
    check("login page sends Permissions-Policy", "camera=()" in login.headers.get("permissions-policy", ""))
    cookie = " ".join(login.cookies).lower()
    secure_site = Client(base, proxy).https or proxy
    check("CSRF cookie is SameSite", "samesite" in cookie)
    if secure_site:
        check("CSRF cookie is Secure", "secure" in cookie)
        check("HSTS is on", "max-age" in login.headers.get("strict-transport-security", ""))
    check("a POST without a CSRF token is refused", anon.request("POST", "/login/", data={"username": "x", "password": "y"}).status == 403)
    gone = anon.request("GET", "/no-such-page-xyz/")
    check("404 page leaks nothing", gone.status == 404 and "URLconf" not in gone.text and "Traceback" not in gone.text)


def suite_stranger(base, proxy, password, doc_id, title):
    print("\n== Signed in, but NOT granted (sunil, anita, meena) ==")
    ghost = str(uuid.uuid4())
    for name in ("sunil", "anita", "meena"):
        who = person(base, proxy, name, password)
        who.token()  # an attacker first loads any page to get a valid CSRF token
        armed = {"X-CSRFToken": who.jar.get("csrftoken", "")}
        problems = []
        for route in doc_routes(doc_id):
            twin = route.replace(doc_id, ghost)
            for method in METHODS:
                real = who.request(method, route, headers=armed, referer=route)
                fake = who.request(method, twin, headers=armed, referer=twin)
                if real.status != 404:
                    problems.append(f"{method} {route} -> {real.status}")
                elif real.digest() != fake.digest():
                    problems.append(f"{method} {route} differs from a missing document")
        check(f"{name}: every document route gives the same 404 as a document that does not exist", not problems, "; ".join(problems[:3]))
        listing = who.request("GET", "/documents/?q=Salary").text
        check(f"{name}: search shows nothing of the document", title not in listing)
        check(f"{name}: search counts do not include hidden documents",
              not re.search(r"\b[1-9]\d* documents? found", who.request("GET", "/documents/?owner=priya").text)
              or name == "anita")
    sunil = person(base, proxy, "sunil", password)
    variants = [f"/documents/{doc_id}", f"//documents/{doc_id}/", f"/documents/{doc_id}//", f"/documents/{doc_id}/download",
                f"/documents/{doc_id.upper()}/", f"/documents/{doc_id}/download/?x=1", f"/documents/./{doc_id}/download/",
                f"/documents/{doc_id}/download/%00", f"/documents/{doc_id}%2fdownload/", f"/documents/{doc_id}/download/..;/"]
    leaked = []
    for path in variants:
        reply = sunil.request("GET", path)
        if reply.status in (301, 302) and reply.headers.get("location", "").startswith("/"):
            reply = sunil.request("GET", reply.headers["location"])
        if reply.status == 200 or b"%PDF-" in reply.body:
            leaked.append(f"{path} -> {reply.status}")
    check("sunil: path tricks (slashes, case, dots, encodings) never reach the file", not leaked, "; ".join(leaked))
    tricks = [{"X-Original-URL": "/documents/new/"}, {"X-HTTP-Method-Override": "DELETE"}, {"X-Forwarded-For": "127.0.0.1"},
              {"X-Forwarded-Host": "evil.example"}, {"Range": "bytes=0-10"}, {"X-Rewrite-URL": f"/documents/{doc_id}/"}]
    check("sunil: spoofed headers do not open the download",
          all(sunil.request("GET", f"/documents/{doc_id}/download/", headers=h).status == 404 for h in tricks))
    sunil.token()
    armed = {"X-CSRFToken": sunil.jar.get("csrftoken", "")}
    check("sunil: administrator pages are refused (with a valid CSRF token)",
          all(sunil.request(m, p, headers=armed, referer=p).status == 404 for p in ADMIN_ROUTES for m in ("GET", "POST")))
    owner = person(base, proxy, "anita", password)
    check("anita (another owner): cannot see the history of Priya's document",
          owner.request("GET", f"/documents/{doc_id}/history/").status == 404)


def suite_authorised(base, proxy, password, doc_id, title):
    print("\n== Allowed people (ravi has read access, priya owns, meena is admin) ==")
    ravi = person(base, proxy, "ravi", password)
    page = ravi.request("GET", f"/documents/{doc_id}/")
    check("ravi can open the document he was granted", page.status == 200 and title in page.text)
    check("document pages are never cached", "no-store" in page.headers.get("cache-control", ""))
    download = ravi.request("GET", f"/documents/{doc_id}/download/")
    check("ravi can download it", download.status == 200 and download.body.startswith(b"%PDF-"))
    check("the download is an attachment", download.headers.get("content-disposition", "").startswith("attachment"))
    check("the download is sandboxed", "sandbox" in download.headers.get("content-security-policy", ""))
    check("the download is not sniffable and not cached", download.headers.get("x-content-type-options") == "nosniff"
          and "no-store" in download.headers.get("cache-control", ""))
    check("ravi (read only) cannot edit, delete or share it",
          all(ravi.post(p, {"title": "x"}, page=f"/documents/{doc_id}/").status == 404 for p in (f"/documents/{doc_id}/edit/", f"/documents/{doc_id}/delete/", f"/documents/{doc_id}/access/grant/")))
    priya = person(base, proxy, "priya", password)
    check("priya (owner) can open it", priya.request("GET", f"/documents/{doc_id}/").status == 200)
    admin = person(base, proxy, "meena", password)
    check("meena (admin) can read the activity log", admin.request("GET", "/activity/").status == 200)
    check("the activity log shows refused attempts", "refused" in admin.request("GET", "/activity/?group=denied").text)
    check("meena (admin) still cannot open the document", admin.request("GET", f"/documents/{doc_id}/").status == 404)
    owner_only = [priya.request("GET", p).status for p in ("/activity/", "/users/")]
    check("priya (owner) cannot see admin pages", owner_only == [404, 404])


def suite_inputs(base, proxy, password, doc_id):
    print("\n== Hostile input ==")
    priya = person(base, proxy, "priya", password)
    # owner and parameter pollution on the edit form must not change the owner
    priya.post(f"/documents/{doc_id}/edit/", {"title": "Salary letter - Ravi (demo)", "owner": "999", "owner_id": "999", "role": "admin"},
               page=f"/documents/{doc_id}/")
    check("extra fields (owner, role) in a form are ignored", priya.request("GET", f"/documents/{doc_id}/").status == 200)
    statuses = []
    for path in ("/documents/%ff/", "/documents/?page=abc", "/documents/?page=99999999999999999999", "/documents/?q=" + "A" * 6000,
                 "/documents/?date_from=%00", "/documents/?q=%27%20OR%201%3D1--"):
        reply = priya.request("GET", path)
        statuses.append((path[:30], reply.status, "Traceback" in reply.text or "Exception" in reply.text))
    check("odd search and address input never causes a server error", all(s < 500 and not t for _, s, t in statuses), str(statuses))
    garbage = priya.request("POST", "/documents/new/", body=b"--x\r\nbroken", referer="/documents/new/",
                            headers={"Content-Type": "multipart/form-data; boundary=x", "X-CSRFToken": priya.jar.get("csrftoken", "")})
    check("a broken upload request gives a clean error, not a crash", garbage.status < 500 and "Traceback" not in garbage.text, str(garbage.status))
    for target in ("https://evil.example/", "//evil.example/"):
        fresh = Client(base, proxy)
        form = fresh.request("GET", "/login/")
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', form.text).group(1)
        reply = fresh.request("POST", "/login/?next=" + quote(target, safe=""), data={"username": "kiran", "password": password, "csrfmiddlewaretoken": token}, referer="/login/")
        where = reply.headers.get("location", "")
        check(f"login does not redirect to {target}", reply.status == 302 and not where.startswith(("http", "//")), where)


def tiny_pdf():
    return b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def office_zip(extra=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<x/>")
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return buffer.getvalue()


def multipart(fields, filename, content, token):
    boundary = "----attackcheck" + uuid.uuid4().hex
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="csrfmiddlewaretoken"\r\n\r\n{token}\r\n'.encode()]
    for key, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def upload(client, filename, content, path="/documents/new/", fields=None):
    token = client.token("/documents/")
    body, headers = multipart(fields or {"title": "attack-check " + uuid.uuid4().hex[:6]}, filename, content, token)
    return client.request("POST", path, body=body, headers=headers, referer=path)


def suite_uploads(base, proxy, password):
    print("\n== Uploads (creates one temporary document, then deletes it) ==")
    priya = person(base, proxy, "priya", password)
    ravi = person(base, proxy, "ravi", password)
    check("a viewer cannot upload", upload(ravi, "x.pdf", tiny_pdf()).status == 404)
    refused = {
        "a program renamed .pdf": ("invoice.pdf", b"MZ\x90\x00 program"),
        "an HTML page": ("page.html", b"<script>alert(1)</script>"),
        "an SVG with a script": ("image.svg", b"<svg onload=alert(1)>"),
        "a macro-enabled Word file": ("macro.docm", office_zip({"word/vbaProject.bin": b"m"})),
        "a docx that contains macros": ("macro.docx", office_zip({"word/vbaProject.bin": b"m"})),
        "a zip bomb": ("bomb.docx", office_zip({"word/big.xml": b"0" * (60 * 1024 * 1024)})),
        "a zip with a path-traversal entry": ("trav.docx", office_zip({"../../evil.txt": b"x"})),
    }
    for label, (name, content) in refused.items():
        reply = upload(priya, name, content)
        check(f"upload of {label} is refused", reply.status in (400, 413), str(reply.status))
    reply = upload(priya, "..\\..\\etc\\pass\twd.pdf", tiny_pdf(), fields={"title": "<b>attack-check</b>"})
    check("a hostile file name and title are accepted only in cleaned form", reply.status == 302, str(reply.status))
    if reply.status != 302:
        return None
    new_id = re.search(r"/documents/([0-9a-f-]{36})/", reply.headers["location"]).group(1)
    page = priya.request("GET", f"/documents/{new_id}/").text
    check("the title is shown escaped", "<b>attack-check</b>" not in page and "&lt;b&gt;" in page)
    download = priya.request("GET", f"/documents/{new_id}/download/")
    disposition = download.headers.get("content-disposition", "")
    check("the stored file name has no folders or control characters", "passwd.pdf" in disposition and "\\" not in disposition and "/" not in disposition, disposition)
    check("a stranger cannot download the new file", person(base, proxy, "sunil", password).request("GET", f"/documents/{new_id}/download/").status == 404)
    return new_id


def suite_revocation(base, proxy, password, new_id):
    print("\n== Revocation ==")
    priya = person(base, proxy, "priya", password)
    sunil = person(base, proxy, "sunil", password)
    base_path = f"/documents/{new_id}/"
    check("before the grant, sunil is refused", sunil.request("GET", base_path).status == 404)
    priya.post(base_path + "access/grant/", {"username": "sunil", "level": "read"}, page=base_path + "access/")
    check("after the grant, sunil can open it", sunil.request("GET", base_path).status == 200)
    check("and download it", sunil.request("GET", base_path + "download/").status == 200)
    access = priya.request("GET", base_path + "access/").text
    grant = re.search(r"/access/(\d+)/revoke/", access)
    check("the owner sees the grant", grant is not None)
    if grant:
        priya.post(base_path + f"access/{grant.group(1)}/revoke/", page=base_path + "access/")
    check("on the very next request after revoking, sunil is refused", sunil.request("GET", base_path).status == 404)
    check("and cannot download", sunil.request("GET", base_path + "download/").status == 404)
    check("and it is gone from his search", "0 documents found" in sunil.request("GET", "/documents/?q=attack-check").text)


def cleanup(base, proxy, password, new_id):
    if new_id:
        priya = person(base, proxy, "priya", password)
        priya.post(f"/documents/{new_id}/delete/", page=f"/documents/{new_id}/")
        check("cleanup: the temporary document is deleted", priya.request("GET", f"/documents/{new_id}/").status == 404)


def suite_throttle(base, proxy, password):
    print("\n== Login throttling (uses an invented user name) ==")
    victim = "attack-check-" + uuid.uuid4().hex[:6]
    client = Client(base, proxy)
    codes = [client.login(victim, "wrong-password-" + str(i)).status for i in range(7)]
    check("repeated failed sign-ins are slowed down (429)", 429 in codes, str(codes))
    check("a real user is not locked out by it", Client(base, proxy).login("ravi", password).status == 302)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", required=True, help="for example http://127.0.0.1:8000")
    parser.add_argument("--proxy-header", action="store_true", help="local runs: pretend to be the HTTPS proxy")
    parser.add_argument("--include-upload", action="store_true")
    parser.add_argument("--include-revocation", action="store_true", help="implies --include-upload")
    parser.add_argument("--include-throttle", action="store_true")
    args = parser.parse_args()
    password = os.environ.get("ATTACK_PASSWORD")
    if not password:
        sys.exit("Set ATTACK_PASSWORD to the demo accounts' password first.")
    base, proxy = args.base.rstrip("/"), args.proxy_header
    ravi = person(base, proxy, "ravi", password)
    title = "Salary letter - Ravi (demo)"
    doc_id = find_document(ravi, title)
    if not doc_id:
        sys.exit("Could not find the seeded salary letter. Run the seed command first.")
    print(f"Target: {base}   document under attack: {doc_id}")
    suite_anonymous(base, proxy, doc_id, title)
    suite_stranger(base, proxy, password, doc_id, title)
    suite_authorised(base, proxy, password, doc_id, title)
    suite_inputs(base, proxy, password, doc_id)
    new_id = None
    if args.include_upload or args.include_revocation:
        new_id = suite_uploads(base, proxy, password)
    if args.include_revocation and new_id:
        suite_revocation(base, proxy, password, new_id)
    cleanup(base, proxy, password, new_id)
    if args.include_throttle:
        suite_throttle(base, proxy, password)
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)} passed, {len(failed)} FAILED")
    for name, _, detail in failed:
        print(f"  FAILED: {name}  {detail}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
