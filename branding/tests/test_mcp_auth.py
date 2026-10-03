#!/usr/bin/env python3
"""R10 prep: the optional FreeCADMCP guard patch really refuses the attack.

Applies the vendored pristine addon + patches/ + optional/0002 into a temp
dir with `patch`, imports the PATCHED rpc_server/auth.py (it has no FreeCAD
dependency), serves a real XML-RPC server with its handler on a free port,
and fires the requests a web page and a legitimate client would send.

    python3 branding/tests/test_mcp_auth.py        -> MCP_AUTH_TESTS_OK
"""
import http.client
import importlib.util
import os
import shutil
import socketserver
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
import xmlrpc.client
from xmlrpc.server import SimpleXMLRPCServer

HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.join(os.path.dirname(HERE), "vendor", "freecad-mcp")


def _patched_tree(dst, optional=True):
    shutil.copytree(os.path.join(VENDOR, "addon"), os.path.join(dst, "addon"))
    # Same selection as build_appimage.sh: *.patch, filename order.
    def _series(d):
        d = os.path.join(VENDOR, d)
        return sorted(os.path.join(d, p) for p in os.listdir(d)
                      if p.endswith(".patch"))
    series = _series("patches") + (_series("optional") if optional else [])
    for p in series:
        with open(p, "rb") as fh:
            subprocess.run(["patch", "-p1", "-s", "--no-backup-if-mismatch",
                            "-d", dst], stdin=fh, check=True)
    return os.path.join(dst, "addon", "FreeCADMCP", "rpc_server")


class _Server(socketserver.ThreadingMixIn, SimpleXMLRPCServer):
    daemon_threads = True


class Guard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="mcp_auth_")
        rpc = _patched_tree(cls.tmp)
        spec = importlib.util.spec_from_file_location(
            "atech_mcp_auth", os.path.join(rpc, "auth.py"))
        cls.auth = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.auth)
        cls.userdir = os.path.join(cls.tmp, "userdata")
        cls.token = cls.auth.load_or_create_token(cls.userdir)
        cls.srv = _Server(("127.0.0.1", 0), allow_none=True, logRequests=False,
                          requestHandler=cls.auth.GuardedRequestHandler)
        cls.port = cls.srv.server_address[1]
        cls.srv.atech_token = cls.token
        cls.srv.atech_hosts = cls.auth.allowed_hosts(cls.port)
        cls.ran = []
        cls.srv.register_function(lambda code: cls.ran.append(code) or "ran",
                                  "execute_code")
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    BODY = xmlrpc.client.dumps(("open('/tmp/pwned','w')",),
                               "execute_code").encode()

    def _post(self, headers, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = {"Host": "127.0.0.1:%d" % self.port}
        h.update(headers)
        c.request("POST", "/", body=self.BODY if body is None else body,
                  headers={k: v for k, v in h.items() if v is not None})
        r = c.getresponse()
        r.read()
        c.close()
        return r.status

    def setUp(self):
        del self.ran[:]

    # ---- the attack from the audit: a page POSTs text/plain, no preflight
    def test_text_plain_rejected(self):
        st = self._post({"Content-Type": "text/plain",
                         self.auth.TOKEN_HEADER: self.token})
        self.assertEqual(st, 415)
        self.assertEqual(self.ran, [])

    def test_origin_rejected_even_with_token(self):
        st = self._post({"Content-Type": "text/xml",
                         "Origin": "https://evil.example",
                         self.auth.TOKEN_HEADER: self.token})
        self.assertEqual(st, 403)
        self.assertEqual(self.ran, [])

    def test_rebound_host_rejected(self):
        st = self._post({"Content-Type": "text/xml",
                         "Host": "evil.example:%d" % self.port,
                         self.auth.TOKEN_HEADER: self.token})
        self.assertEqual(st, 403)
        self.assertEqual(self.ran, [])

    def test_missing_token_rejected(self):
        self.assertEqual(self._post({"Content-Type": "text/xml"}), 401)
        self.assertEqual(self.ran, [])

    def test_wrong_token_rejected(self):
        st = self._post({"Content-Type": "text/xml",
                         self.auth.TOKEN_HEADER: "x" * 43})
        self.assertEqual(st, 401)
        self.assertEqual(self.ran, [])

    # ---- the legitimate client still works, so the guard is not a wall
    def test_client_with_token_served(self):
        px = xmlrpc.client.ServerProxy(
            "http://127.0.0.1:%d" % self.port, allow_none=True,
            headers=[(self.auth.TOKEN_HEADER, self.token)])
        self.assertEqual(px.execute_code("1+1"), "ran")
        self.assertEqual(self.ran, ["1+1"])

    def test_client_without_token_fails(self):
        px = xmlrpc.client.ServerProxy("http://127.0.0.1:%d" % self.port)
        with self.assertRaises(xmlrpc.client.ProtocolError) as cm:
            px.execute_code("1+1")
        self.assertEqual(cm.exception.errcode, 401)

    # ---- the token file
    def test_token_file_is_0600_and_stable(self):
        p = self.auth.token_path(self.userdir)
        self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)
        self.assertGreaterEqual(len(self.token), 32)
        self.assertEqual(self.auth.load_or_create_token(self.userdir), self.token)

    def test_loose_token_file_tightened(self):
        d = tempfile.mkdtemp(dir=self.tmp)
        t = self.auth.load_or_create_token(d)
        os.chmod(self.auth.token_path(d), 0o644)
        self.assertEqual(self.auth.load_or_create_token(d), t)
        self.assertEqual(stat.S_IMODE(os.stat(self.auth.token_path(d)).st_mode),
                         0o600)

    def test_symlink_token_refused(self):
        d = tempfile.mkdtemp(dir=self.tmp)
        os.symlink("/etc/hostname", self.auth.token_path(d))
        with self.assertRaises(PermissionError):
            self.auth.load_or_create_token(d)


class Series(unittest.TestCase):
    def test_default_series_has_no_guard(self):
        """The default build applies patches/ only: the guard stays opt-in
        until the owner decides (R10 is needs_user_decision)."""
        tmp = tempfile.mkdtemp(prefix="mcp_series_")
        try:
            rpc = _patched_tree(tmp, optional=False)
            self.assertFalse(os.path.exists(os.path.join(rpc, "auth.py")))
            with open(os.path.join(rpc, "settings.py"), encoding="utf-8") as fh:
                src = fh.read()
            self.assertIn('"auto_start_rpc": False', src)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=1).result
    ok = r.wasSuccessful() and r.testsRun > 0
    print("MCP_AUTH_TESTS_OK" if ok else "MCP_AUTH_TESTS_FAILED")
    sys.exit(0 if ok else 1)
