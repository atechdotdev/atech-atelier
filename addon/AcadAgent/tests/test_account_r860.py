"""R860 sign in to Atech Atelier with the atech.dev account (account.py).

  TestFlow    the browser hop end to end against a fake atech.dev on
              127.0.0.1: the page URL, the loopback callback, the code +
              verifier trade (checked the way the backend checks it), the
              user kept, the page the browser lands on; cancel, a wrong
              state, the typed-in code, the timeout
  TestSession refresh near expiry, a refused refresh signs out, offline
              keeps the session, request() retries once on a 401, sign out
  TestVault   the 0600 file fallback (the Keychain itself is not touched)

No real Keychain, browser or atech.dev: a dict vault, a urllib "browser",
and a local HTTP server standing in for the site.
"""
import base64
import hashlib
import http.server
import json
import os
import stat
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from acadagent import account, shop  # noqa: E402


class FakeVault:
    def __init__(self, secret=""):
        self.secret = secret

    def get(self):
        return self.secret

    def set(self, s):
        self.secret = s
        return True

    def delete(self):
        self.secret = ""
        return True


class FakeSite:
    """/api/auth/app/token, /refresh, /logout and /api/account, as the
    backend answers them."""

    def __init__(self):
        self.codes = {}            # code -> challenge
        self.calls = []
        self.refresh_ok = True
        self.access = "access-1"
        site = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, status, body):
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                site.calls.append(("GET", self.path, self.headers.get("Authorization")))
                if self.path == "/api/account":
                    if self.headers.get("Authorization") != "Bearer " + site.access:
                        return self._json(401, {})
                    return self._json(200, {"profile": {"display_name": "David"}})
                self._json(404, {})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
                site.calls.append(("POST", self.path, self.headers.get("Authorization")))
                if self.path == "/api/auth/app/token":
                    want = site.codes.pop(body.get("code"), None)
                    got = base64.urlsafe_b64encode(hashlib.sha256(
                        body.get("verifier", "").encode()).digest()).rstrip(b"=").decode()
                    if want is None or want != got:
                        return self._json(400, {"error": "bad_code", "message": "That sign-in "
                                                "has expired or was already used."})
                    return self._json(200, site.session())
                if self.path == "/api/auth/refresh":
                    if not site.refresh_ok:
                        return self._json(401, {"error": "refresh_failed"})
                    site.access = "access-2"
                    return self._json(200, site.session(refresh="refresh-2"))
                if self.path == "/api/auth/logout":
                    return self._json(204, {})
                self._json(404, {})

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def session(self, refresh="refresh-1"):
        return {"access_token": self.access, "refresh_token": refresh, "expires_in": 3600,
                "user": {"id": "u1", "email": "maker@example.com"}}

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class Base(unittest.TestCase):
    def setUp(self):
        self.site = FakeSite()
        self.addCleanup(self.site.close)
        p = mock.patch.object(shop, "SITE", self.site.url)
        p.start()
        self.addCleanup(p.stop)
        self.stored = {"user": None}
        self.vault = FakeVault()
        self.acct = account.Account(vault=self.vault, store=lambda u: self.stored.update(user=u),
                                    load=lambda: self.stored["user"])


class TestFlow(Base):
    def browser(self, connect=True, state=None, error=None):
        """Opens the Connect page: the site (here) grants a code for the
        page's challenge and sends the browser to the app's callback."""
        self.landed = {}

        def open_url(url):
            u = urllib.parse.urlsplit(url)
            q = dict(urllib.parse.parse_qsl(u.query))
            self.page = (u.path, q)
            code = "code-%d" % len(self.site.codes)
            self.site.codes[code] = q["challenge"]
            back = {"state": state or q["state"]}
            back.update({"error": error} if error else {"code": code})
            if not connect:
                return True

            def go():
                try:
                    with urllib.request.urlopen("http://127.0.0.1:%s/callback?%s" % (
                            q["port"], urllib.parse.urlencode(back)), timeout=10) as r:
                        self.landed = {"status": r.status, "html": r.read().decode()}
                except urllib.error.HTTPError as e:
                    self.landed = {"status": e.code, "html": e.read().decode()}
            threading.Thread(target=go, daemon=True).start()
            return True
        return open_url

    def run_flow(self, **kw):
        got = []
        done = threading.Event()
        flow = account.SignIn(self.acct, opener=self.browser(**kw),
                              done=lambda r: (got.append(r), done.set()), wait_s=kw.get("wait", 10))
        flow.start()
        if kw.get("connect", True):
            self.assertTrue(done.wait(10))
            end = time.time() + 5
            while not self.landed and time.time() < end:
                time.sleep(0.02)
        return flow, got

    def test_signs_in_through_the_browser(self):
        flow, got = self.run_flow()
        self.assertEqual(got, [{"ok": True, "message": "", "cancelled": False}])
        path, q = self.page
        self.assertEqual(path, "/connect/atelier")
        self.assertEqual(set(q), {"challenge", "port", "state", "device"})
        self.assertRegex(q["challenge"], r"^[A-Za-z0-9_-]{43}$")   # what the backend accepts
        self.assertNotIn(flow.verifier, flow.url)                  # the secret never travels
        self.assertEqual(self.vault.secret, "refresh-1")
        self.assertEqual(self.stored["user"], {"id": "u1", "email": "maker@example.com",
                                               "name": "David"})
        self.assertEqual(self.acct.label(), "David")
        self.assertEqual(self.landed["status"], 200)
        self.assertIn("Atech Atelier is signed in", self.landed["html"])
        self.assertNotIn("code-0", self.landed["html"])

    def test_the_listener_closes_after(self):
        flow, _got = self.run_flow()
        port = self.page[1]["port"]
        time.sleep(0.3)
        with self.assertRaises(OSError):
            urllib.request.urlopen("http://127.0.0.1:%s/callback" % port, timeout=2)

    def test_cancel_on_the_page(self):
        _flow, got = self.run_flow(error="cancelled")
        self.assertTrue(got[0]["cancelled"])
        self.assertFalse(self.acct.signed_in())
        self.assertIn("Not signed in", self.landed["html"])

    def test_a_wrong_state_is_ignored(self):
        got = []
        flow = account.SignIn(self.acct, opener=self.browser(state="x" * 32),
                              done=got.append, wait_s=10)
        flow.start()
        end = time.time() + 5
        while not self.landed and time.time() < end:
            time.sleep(0.02)
        self.assertEqual(self.landed["status"], 404)
        self.assertEqual(got, [])                                  # still waiting
        flow.cancel()
        self.assertFalse(self.acct.signed_in())

    def test_the_typed_in_code(self):
        got = []
        flow = account.SignIn(self.acct, opener=self.browser(connect=False), done=got.append,
                              wait_s=10)
        flow.start()
        self.assertEqual(flow.submit_code("  code-0 ")["ok"], True)
        self.assertTrue(self.acct.signed_in())
        self.assertEqual(len(got), 1)

    def test_a_wrong_code_says_why(self):
        flow = account.SignIn(self.acct, opener=self.browser(connect=False), wait_s=10)
        flow.start()
        r = flow.submit_code("nope")
        self.assertFalse(r["ok"])
        self.assertIn("expired or was already used", r["message"])

    def test_times_out(self):
        got = []
        flow = account.SignIn(self.acct, opener=lambda u: True, done=got.append, wait_s=0.2)
        flow.start()
        time.sleep(0.6)
        self.assertIn("timed out", got[0]["message"])


class TestSession(Base):
    def signed_in(self, exp_in=3600):
        self.acct._take(self.site.session())
        self.acct._exp = time.time() + exp_in

    def test_live_token_needs_no_call(self):
        self.signed_in()
        self.assertEqual(self.acct.token(), "access-1")
        self.assertEqual(self.site.calls, [])

    def test_refreshes_near_expiry(self):
        self.signed_in(exp_in=30)
        self.assertEqual(self.acct.token(), "access-2")
        self.assertEqual(self.vault.secret, "refresh-2")           # rotated, kept

    def test_a_refused_refresh_signs_out(self):
        self.signed_in(exp_in=30)
        self.site.refresh_ok = False
        self.assertEqual(self.acct.token(), "")
        self.assertFalse(self.acct.signed_in())
        self.assertEqual(self.vault.secret, "")

    def test_offline_keeps_the_session(self):
        self.signed_in(exp_in=30)
        with mock.patch.object(shop, "SITE", "http://127.0.0.1:9"):
            self.assertEqual(self.acct.token(), "")
        self.assertTrue(self.acct.signed_in())
        self.assertEqual(self.vault.secret, "refresh-1")

    def test_request_retries_once_after_a_401(self):
        self.signed_in()
        self.site.access = "access-rotated-elsewhere"              # the token went stale
        status, body = self.acct.request("GET", "/api/account")
        self.assertEqual(status, 200)                              # refreshed, then 200
        self.assertEqual([c[1] for c in self.site.calls],
                         ["/api/account", "/api/auth/refresh", "/api/account"])

    def test_signed_out_request(self):
        self.assertEqual(self.acct.request("GET", "/api/account"), (401, {}))
        self.assertEqual(self.site.calls, [])

    def test_sign_out(self):
        self.signed_in()
        self.acct.sign_out()
        self.assertFalse(self.acct.signed_in())
        self.assertEqual(self.vault.secret, "")
        self.assertEqual(self.site.calls[-1][:2], ("POST", "/api/auth/logout"))


class TestVault(unittest.TestCase):
    def test_one_token_per_site(self):
        self.assertEqual(account.site_account("https://atech.dev"), account.ACCOUNT)
        self.assertEqual(account.site_account("https://staging.atech.dev"),
                         account.ACCOUNT + "@staging.atech.dev")
        with mock.patch.object(account.shop, "SITE", "https://staging.atech.dev"):
            v = account.Vault()
        self.assertEqual(v.account, account.ACCOUNT + "@staging.atech.dev")
        self.assertTrue(v.path.endswith("account-staging.atech.dev.secret"))
        with mock.patch.object(account.shop, "SITE", "http://localhost:3000"):
            self.assertTrue(account.Vault().path.endswith("account-localhost_3000.secret"))
        with mock.patch.object(account.shop, "SITE", "https://atech.dev"):
            v = account.Vault()
        self.assertEqual(v.account, account.ACCOUNT)    # unchanged for atech.dev
        self.assertTrue(v.path.endswith(os.sep + "account.secret"))
        self.assertEqual(account._user_key(), "account_user")
        self.assertEqual(account.other_site(), "")
        with mock.patch.object(account.shop, "SITE", "https://staging.atech.dev"):
            self.assertEqual(account._user_key(), "account_user@staging.atech.dev")
            self.assertEqual(account.other_site(), "staging.atech.dev")

    def test_file_fallback_is_private(self):
        d = tempfile.mkdtemp(prefix="r860vault_")
        v = account.Vault(path=os.path.join(d, "account.secret"))
        with mock.patch.object(v, "_kind", lambda: "file"):
            self.assertTrue(v.set("refresh-xyz"))
            self.assertEqual(v.get(), "refresh-xyz")
            self.assertEqual(stat.S_IMODE(os.stat(v.path).st_mode), 0o600)
            v.delete()
            self.assertEqual(v.get(), "")

    def test_keychain_secret_is_not_on_the_command_line(self):
        seen = []

        def run(cmd, **kw):
            seen.append((cmd, kw.get("input")))
            return mock.Mock(returncode=0, stdout="refresh-xyz\n")
        v = account.Vault()
        with mock.patch.object(v, "_kind", lambda: "keychain"), \
                mock.patch.object(account.subprocess, "run", run):
            self.assertTrue(v.set("refresh-xyz"))
        add = seen[0]
        self.assertEqual(add[0], ["security", "-i"])
        self.assertIn("refresh-xyz", add[1])
        self.assertTrue(all("refresh-xyz" not in " ".join(c) for c, _ in seen))


if __name__ == "__main__":
    unittest.main()


try:
    from PySide6 import QtWidgets
    _APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
except Exception:                                         # noqa: BLE001
    QtWidgets = None


@unittest.skipIf(QtWidgets is None, "PySide6 not available (run with the bundled python)")
class TestButton(Base):
    def make(self):
        from acadagent import account_ui
        self.opened = []
        return account_ui.AccountButton(None, acct=self.acct, opener=self.opened.append,
                                        background=False)

    def test_signed_out_then_waiting_then_signed_in(self):
        from PySide6 import QtCore
        b = self.make()
        self.assertEqual(b.text(), "Sign in")
        with mock.patch.object(account.SignIn, "start", lambda flow: setattr(flow, "url", "U")):
            b.click()
        self.assertEqual(b.text(), "Waiting for the browser…")
        texts = [a.text() for a in b.menu().actions() if a.text()]
        self.assertEqual(texts, ["Open the page again", "Copy the link", "Paste a code…", "Cancel"])
        # the browser came back: the flow finishes on a thread, the button on Qt's
        self.acct._take(self.site.session())
        self.stored["user"]["name"] = "David"
        b.flow._finish({"ok": True, "message": "", "cancelled": False})
        QtCore.QCoreApplication.processEvents()
        # the fake site is not atech.dev, so the button says which site
        self.assertEqual(b.text(), "David · %s" % account.other_site())
        self.assertIn(account.other_site(), b.toolTip())
        with mock.patch.object(account.shop, "SITE", "https://atech.dev"):
            b.sync()
            self.assertEqual(b.text(), "David")
        texts = [a.text() for a in b.menu().actions() if a.text()]
        self.assertEqual(texts, ["maker@example.com", "Your account on atech.dev", "Builds on atech.dev",
                                 "Atech shop", "About Atech Atelier", "Sign out"])

    def test_cancel(self):
        from PySide6 import QtCore
        b = self.make()
        with mock.patch.object(account.SignIn, "start", lambda flow: None):
            b.sign_in()
        b.cancel()
        QtCore.QCoreApplication.processEvents()
        self.assertEqual(b.text(), "Sign in")

    def test_sign_out(self):
        from PySide6 import QtCore
        self.acct._take(self.site.session())
        b = self.make()
        self.assertEqual(b.text().split(" · ")[0], "David")       # name fetched on start
        b.sign_out()
        QtCore.QCoreApplication.processEvents()
        self.assertEqual(b.text(), "Sign in")
        self.assertEqual(self.vault.secret, "")

    def test_account_page(self):
        self.acct._take(self.site.session())
        b = self.make()
        [a for a in b.menu().actions() if a.text() == "Your account on atech.dev"][0].trigger()
        self.assertEqual(self.opened, [self.site.url + "/account"])
