"""R860 sign in to Atech Atelier with the atech.dev account.

The browser signs in, never Atelier: Sign in opens

    <SITE>/connect/atelier?challenge=..&port=..&state=..&device=..

and listens on http://127.0.0.1:<port>/callback. On that page (signed in to
atech.dev as usual, password or Google) the user presses Connect; the site
hands a one-time code back to this listener, and Atelier trades it, with the
secret only it holds (PKCE: `challenge` is its fingerprint), for a session of
its own at /api/auth/app/token. Backend side: studio backend/p2p/server.py
"app sign-in".

The session's refresh token is kept in the macOS Keychain (Linux: the
keyring through secret-tool, else a file only the user can read); the access
token stays in memory. The account's id, email and name sit in settings
("account_user") so Home can show who is signed in without a network call.

Nothing here touches Qt: the window code (shell.py) calls in from a thread
and relays results with a signal.
"""
import base64
import hashlib
import html
import http.server
import json
import os
import platform
import secrets
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import shop

SERVICE = "dev.atech.Atelier"          # the Keychain item: service + account
ACCOUNT = "atech-account"
CLIENT = "atelier"
WAIT_S = 300                            # how long Sign in waits for the browser
TIMEOUT_S = 15


def _log(msg):
    """The Report view; never a token, a code or a verifier."""
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog("[AcadAgent account] %s\n" % msg)
    except Exception:                                     # noqa: BLE001
        pass


# ===================================================================
# where the refresh token lives
# ===================================================================
def site_account(site=None):
    """The Keychain account for a site's refresh token: ACCOUNT for
    atech.dev, ACCOUNT@<host> for any other ($ATECH_SITE, e.g. staging), so
    a token from a staging sign-in is never sent to atech.dev (nor the
    other way round), and switching sites does not sign the other out."""
    host = urllib.parse.urlsplit(site or shop.SITE).netloc.lower()
    return ACCOUNT if host in ("", "atech.dev") else "%s@%s" % (ACCOUNT, host)


class Vault:
    """The one secret: the refresh token. macOS Keychain, else secret-tool,
    else a 0600 file. The secret goes on stdin, never on a command line
    (another user's `ps` would see it). One per site (site_account)."""

    def __init__(self, service=SERVICE, account=None, path=None):
        self.service, self.account = service, account or site_account()
        name = "account.secret" if self.account == ACCOUNT else \
            "account-%s.secret" % self.account.split("@", 1)[1].replace(":", "_")
        self.path = path or os.path.join(os.path.expanduser("~"), ".config", "acadagent",
                                         name)

    def _kind(self):
        if platform.system() == "Darwin" and shutil.which("security"):
            return "keychain"
        if shutil.which("secret-tool"):
            return "secret-tool"
        return "file"

    def get(self):
        kind = self._kind()
        try:
            if kind == "keychain":
                r = subprocess.run(["security", "find-generic-password", "-s", self.service,
                                    "-a", self.account, "-w"], capture_output=True, text=True,
                                   timeout=TIMEOUT_S)
                return r.stdout.strip() if r.returncode == 0 else ""
            if kind == "secret-tool":
                r = subprocess.run(["secret-tool", "lookup", "service", self.service,
                                    "account", self.account], capture_output=True, text=True,
                                   timeout=TIMEOUT_S)
                return r.stdout.strip() if r.returncode == 0 else ""
            with open(self.path, encoding="utf-8") as fh:
                return fh.read().strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    def set(self, secret):
        if not secret:
            return self.delete()
        kind = self._kind()
        try:
            if kind == "keychain":
                # `security -i` reads its command from stdin: the token is not
                # in argv. -U replaces an older item.
                cmd = 'add-generic-password -U -s "%s" -a "%s" -l "Atech Atelier" -w "%s"\n' % (
                    self.service, self.account, secret.replace('"', ""))
                r = subprocess.run(["security", "-i"], input=cmd, capture_output=True, text=True,
                                   timeout=TIMEOUT_S)
                return r.returncode == 0 and self.get() == secret.replace('"', "")
            if kind == "secret-tool":
                r = subprocess.run(["secret-tool", "store", "--label=Atech Atelier", "service",
                                    self.service, "account", self.account], input=secret,
                                   capture_output=True, text=True, timeout=TIMEOUT_S)
                return r.returncode == 0
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(secret)
            os.chmod(self.path, 0o600)
            return True
        except (OSError, subprocess.SubprocessError) as exc:
            _log("vault set failed: %s" % type(exc).__name__)
            return False

    def delete(self):
        kind = self._kind()
        try:
            if kind == "keychain":
                subprocess.run(["security", "delete-generic-password", "-s", self.service,
                                "-a", self.account], capture_output=True, timeout=TIMEOUT_S)
            elif kind == "secret-tool":
                subprocess.run(["secret-tool", "clear", "service", self.service,
                                "account", self.account], capture_output=True, timeout=TIMEOUT_S)
            elif os.path.exists(self.path):
                os.remove(self.path)
        except (OSError, subprocess.SubprocessError):
            return False
        return True


# ===================================================================
# HTTP to the site (its /api/auth/* reaches the backend)
# ===================================================================
def _post(path, body, token=None, opener=None, timeout=TIMEOUT_S):
    """(status, json) from POST SITE+path; status 0 = no answer."""
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "User-Agent": "AtechAtelier"}
    if token:
        headers["Authorization"] = "Bearer " + token
    return _call(urllib.request.Request(shop.SITE + path, data=json.dumps(body).encode("utf-8"),
                                        method="POST", headers=headers), opener, timeout)


def _call(req, opener=None, timeout=TIMEOUT_S):
    try:
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except Exception:                                 # noqa: BLE001
            return e.code, {}
    except Exception as e:                                # noqa: BLE001
        _log("no answer from %s: %s" % (req.full_url.split("?")[0], type(e).__name__))
        return 0, {}


def _message(body, default):
    d = body.get("detail") if isinstance(body.get("detail"), dict) else body
    m = d.get("message") if isinstance(d, dict) else None
    return m if isinstance(m, str) and m else default


# ===================================================================
# the account
# ===================================================================
class Account:
    """Who is signed in, and a fresh access token on demand. One per app
    (`get()`); thread-safe."""

    def __init__(self, vault=None, opener=None, store=None, load=None):
        self.vault = vault or Vault()
        self.opener = opener
        self._store = store or _store_user
        self._load = load or _stored_user
        self._lock = threading.Lock()
        self._access = ""
        self._exp = 0.0

    # -- who ---------------------------------------------------------- #
    @property
    def user(self):
        """{"id", "email", "name"} or None."""
        u = self._load()
        return u if isinstance(u, dict) and u.get("id") else None

    def signed_in(self):
        return self.user is not None

    def label(self):
        u = self.user or {}
        return u.get("name") or u.get("email") or ""

    # -- the session -------------------------------------------------- #
    def _take(self, s):
        """Keep a session payload: the refresh token in the vault, the
        access token in memory, the user in settings. False when the vault
        would not take it (then nothing is kept)."""
        refresh = s.get("refresh_token") or ""
        if not s.get("access_token") or not refresh or not self.vault.set(refresh):
            return False
        self._access = s["access_token"]
        self._exp = time.time() + max(60, int(s.get("expires_in") or 3600))
        old = self.user or {}
        user = s.get("user") or {}
        self._store({"id": user.get("id", ""), "email": user.get("email", ""),
                     "name": old.get("name", "") if old.get("id") == user.get("id") else ""})
        return True

    def token(self, force=False):
        """A live access token, refreshing when it is within a minute of
        expiry (or `force`). "" when signed out, or offline with no live
        token; a refused refresh signs out."""
        with self._lock:
            if not force and self._access and self._exp - 60 > time.time():
                return self._access
            refresh = self.vault.get() if self.signed_in() else ""
            if not refresh:
                return ""
            status, body = _post("/api/auth/refresh", {"refresh_token": refresh},
                                 opener=self.opener)
            if status == 200 and self._take(body):
                return self._access
            if status in (400, 401):
                _log("the session ended (refresh refused)")
                self._clear()
            return ""

    def request(self, method, path, body=None):
        """(status, json) from the site as this account; one refresh and
        retry on a 401. (401, {}) when signed out."""
        for attempt in (0, 1):
            tok = self.token(force=attempt == 1)
            if not tok:
                return 401, {}
            headers = {"Accept": "application/json", "User-Agent": "AtechAtelier",
                       "Authorization": "Bearer " + tok}
            data = None
            if body is not None:
                data = json.dumps(body).encode("utf-8")
                headers["Content-Type"] = "application/json"
            status, out = _call(urllib.request.Request(shop.SITE + path, data=data, method=method,
                                                       headers=headers), self.opener)
            if status != 401:
                return status, out
        return status, out

    def refresh_profile(self):
        """The account's display name from /api/account, kept with the user.
        Returns the user (or None)."""
        status, body = self.request("GET", "/api/account")
        u = self.user
        if status == 200 and u:
            profile = body.get("profile") or {}
            name = (profile.get("display_name") or "").strip()
            if name != u.get("name"):
                u = dict(u, name=name)
                self._store(u)
        return self.user

    def _clear(self):
        self._access, self._exp = "", 0.0
        self.vault.delete()
        self._store(None)

    def sign_out(self):
        """Ends this app's session on Atech (best effort) and forgets it
        here. The browser's own session is not touched."""
        tok = self._access if self._exp > time.time() else ""
        if tok:
            _post("/api/auth/logout", {}, token=tok, opener=self.opener, timeout=5)
        self._clear()

    # -- sign in ------------------------------------------------------ #
    def redeem(self, code, verifier):
        """{"ok", "message"}: the code the browser brought back + the
        verifier -> this app's session."""
        status, body = _post("/api/auth/app/token", {"code": code, "verifier": verifier},
                             opener=self.opener)
        if status == 200 and self._take(body):
            self.refresh_profile()
            return {"ok": True, "message": ""}
        if status == 200:
            return {"ok": False, "message": "Signed in, but this computer would not keep the "
                                            "session (the Keychain refused it)."}
        if status == 0:
            return {"ok": False, "message": "Could not reach atech.dev. Check your connection."}
        return {"ok": False, "message": _message(body, "Could not sign in. Try again.")}


_ACCOUNT = None


def get():
    global _ACCOUNT
    if _ACCOUNT is None:
        _ACCOUNT = Account()
    return _ACCOUNT


def other_site():
    """The site's host when it is not atech.dev ($ATECH_SITE), else ""."""
    a = site_account()
    return "" if a == ACCOUNT else a.split("@", 1)[1]


def _user_key():
    """Who is signed in is kept per site, like the token (site_account)."""
    host = other_site()
    return "account_user@%s" % host if host else "account_user"


def _stored_user():
    try:
        from . import settings
        return settings.load().get(_user_key())
    except Exception:                                     # noqa: BLE001
        return None


def _store_user(user):
    try:
        from . import settings
        settings.update(**{_user_key(): user})
    except Exception as exc:                              # noqa: BLE001
        _log("store user: %s" % type(exc).__name__)


# ===================================================================
# the browser hop
# ===================================================================
def pkce():
    """(verifier, challenge): the secret, and its S256 fingerprint."""
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge.rstrip(b"=").decode("ascii")


def device_name():
    """"David's MacBook Pro" for the Connect screen; the host name else."""
    name = ""
    if platform.system() == "Darwin":
        try:
            name = subprocess.run(["scutil", "--get", "ComputerName"], capture_output=True,
                                  text=True, timeout=3).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return (name or platform.node() or "this computer")[:60]


#: The Atelier icon (brand/assets/atech_icon-light.svg, generated there).
_ICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64.00 64.00" width="64" height="64" class="icon" role="img" aria-label="Atech Atelier"> <rect x="1" y="1" width="62" height="62" rx="14" fill="#ffffff" stroke="#e5e7eb" stroke-width="1.5"/> <path d="M32,11 32,42.73 31.89,43.52 31.63,44.19 31.27,44.72 30.41,45.55 29.34,46.2 28.15,46.75 26.16,47.42 23.11,48.21 21.11,48.66 19.12,49.17 17.26,49.7 16.07,50.1 14.34,50.78 13.28,51.31 12.62,51.7 11.82,52.23 10.89,53 10.84,52.95 10.96,52.68 16.81,41 18.78,37.15 23.88,26.93 25.92,22.95 31.82,11.13 32,11ZM25.76,33.97 25.72,34.36 25.59,34.89 25.53,35.56 25.28,36.49 25.12,36.89 24.89,37.28 24.7,37.55 24.43,37.81 24.03,38.14 23.24,38.52 22.71,38.66 21.91,38.79 20.85,38.88 22.71,39.12 23.24,39.25 24.03,39.62 24.57,40.04 24.9,40.47 25.14,40.87 25.29,41.27 25.55,42.33 25.61,42.99 25.76,43.78 25.85,42.46 25.99,41.66 26.13,41.13 26.42,40.5 26.82,39.97 27.22,39.62 28.02,39.23 28.55,39.1 30.27,38.88 29.08,38.79 28.28,38.65 27.88,38.52 27.35,38.27 26.82,37.86 26.41,37.28 26.11,36.62 25.87,35.42 25.76,33.97ZM38.77,34.36 38.85,35.42 38.99,36.22 39.26,37.02 39.64,37.68 40.1,38.13 40.76,38.5 41.16,38.64 41.82,38.78 42.76,38.88 41.42,39.11 40.63,39.36 40.23,39.6 39.7,40.07 39.27,40.73 39.01,41.53 38.86,42.33 38.77,43.39 38.62,42.73 38.56,42.19 38.42,41.53 38.28,41.13 37.85,40.34 37.57,40 36.91,39.51 36.25,39.23 35.72,39.1 34.25,38.88 35.32,38.76 36.25,38.54 36.91,38.26 37.44,37.87 37.74,37.55 38.02,37.15 38.26,36.62 38.53,35.69 38.64,34.89 38.7,34.76 38.77,34.36Z" fill="#111827" fill-rule="evenodd"/> </svg>'

_OK = ('<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#fff" stroke-width="3" '
       'stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>')
_NO = ('<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#fff" stroke-width="3" '
       'stroke-linecap="round"><path d="M7 7l10 10M17 7L7 17"/></svg>')

#: The page the browser lands on at the end (served by the listener): the
#: Connect page's look (atech.dev /connect/atelier), not a bare line of text.
_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Atech Atelier</title>
<style>
:root{--bg:#f4f4f5;--card:#fff;--line:#e5e7eb;--text:#0b0b0c;--muted:#5b5f66}
@media(prefers-color-scheme:dark){:root{--bg:#0b0b0c;--card:#17171a;--line:#2a2a2f;--text:#f4f4f5;--muted:#a1a1aa}}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:16px;
background:var(--bg);color:var(--text);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Inter",system-ui,sans-serif}
main{background:var(--card);border:1px solid var(--line);border-radius:24px;padding:36px 32px;
max-width:26rem;width:100%%;text-align:center;box-shadow:0 20px 60px rgba(0,0,0,.08)}
.mark{position:relative;width:64px;height:64px;margin:0 auto 20px}.icon{display:block}
.badge{position:absolute;right:-8px;bottom:-8px;width:30px;height:30px;border-radius:50%%;
display:grid;place-items:center;border:3px solid var(--card);background:%s}
h1{font-size:26px;letter-spacing:-.02em;line-height:1.15;margin:0 0 8px}p{margin:0;color:var(--muted)}
.small{margin-top:18px;font-size:12.5px}
</style></head><body><main><div class="mark">%s<span class="badge">%s</span></div>
<h1>%s</h1><p>%s</p><p class="small">%s</p></main></body></html>"""


class SignIn:
    """One Sign in: the listener on 127.0.0.1, the page in the browser, and
    the trade for a session. `done(result)` is called once, from a thread,
    with {"ok", "message", "cancelled"}."""

    def __init__(self, account=None, opener=None, done=None, wait_s=WAIT_S):
        self.account = account or get()
        self.open_url = opener or shop.open_url
        self.done = done or (lambda r: None)
        self.wait_s = wait_s
        self.verifier, self.challenge = pkce()
        self.state = secrets.token_urlsafe(24)
        self._finished = threading.Event()
        self._server = None
        self.url = ""

    def start(self):
        """Listen, open the browser; returns the page's URL (also for a
        "Copy link" when no browser opens)."""
        flow = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):                    # the code is in the path
                pass

            def do_GET(self):
                u = urllib.parse.urlsplit(self.path)
                q = dict(urllib.parse.parse_qsl(u.query))
                if u.path != "/callback" or not secrets.compare_digest(
                        q.get("state", ""), flow.state) or flow._finished.is_set():
                    return self._page(404, "Nothing here", "Start Sign in from Atech Atelier.")
                if q.get("error"):
                    flow._finish({"ok": False, "cancelled": True, "message": "Sign in was cancelled."})
                    return self._page(200, "Not signed in", "Atech Atelier was not signed in.")
                result = flow.account.redeem(q.get("code", ""), flow.verifier)
                flow._finish(dict(result, cancelled=False))
                if result["ok"]:
                    who = flow.account.label()
                    return self._page(200, "Atech Atelier is signed in",
                                      "As %s. Go back to the app: it is ready." % who, ok=True)
                return self._page(200, "Not signed in", result["message"])

            def _page(self, status, title, text, ok=False):
                body = (_PAGE % ("#16a34a" if ok else "#71717a", _ICON, _OK if ok else _NO,
                                 html.escape(title), html.escape(text),
                                 "You can close this tab." if status == 200 else "")).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        threading.Thread(target=self._timeout, daemon=True).start()
        self.url = "%s/connect/%s?%s" % (shop.SITE, CLIENT, urllib.parse.urlencode({
            "challenge": self.challenge, "port": port, "state": self.state,
            "device": device_name()}))
        self.open_url(self.url)
        return self.url

    def submit_code(self, code):
        """The code typed in instead (the page shows one when the browser
        could not reach this listener)."""
        result = self.account.redeem(code.strip(), self.verifier)
        self._finish(dict(result, cancelled=False))
        return result

    def cancel(self):
        self._finish({"ok": False, "cancelled": True, "message": ""})

    def _timeout(self):
        if not self._finished.wait(self.wait_s):
            self._finish({"ok": False, "cancelled": True,
                          "message": "Sign in timed out. Press Sign in to try again."})

    def _finish(self, result):
        if self._finished.is_set():
            return
        self._finished.set()
        srv, self._server = self._server, None
        if srv is not None:
            # shutdown() waits for serve_forever: not from its own thread
            threading.Thread(target=lambda: (srv.shutdown(), srv.server_close()),
                             daemon=True).start()
        try:
            self.done(result)
        except Exception as exc:                          # noqa: BLE001
            _log("sign-in done handler: %s" % type(exc).__name__)
