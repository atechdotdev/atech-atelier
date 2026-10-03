"""Contract tests for acadagent.engine and acadagent.settings (the parts that
decide whether the DEFAULT chat path can even start).

Pure: runs under system Python with the PySide6 stub from test_claude_cli,
against a private copy of the package. Settings are redirected to a temp
file; the developer's real ~/.config/acadagent is never read or written.

WHAT IS PINNED
    - an unknown or missing engine falls back to the default (claude);
    - select() refuses an unknown engine and does not write the file;
    - available() answers from a measured fact: a real executable for
      claude, a socket that actually accepts for opencode;
    - settings.load() survives a corrupt settings.json (R46 names it).

REGRESSIONS PINNED
    A settings.json that is valid JSON but not an object (`null`, `42`,
    `[1]`) used to raise TypeError out of dict.update in load() (measured on
    the 2026-09-24 tree); the settings workstream fixed it on 2026-09-25.
    These tests keep it fixed.

KNOWN DEFECT (expected failure, engine.py is not this workstream's file)
    engine.current() raises TypeError for an unhashable "engine" value
    such as ["claude"]. expectedFailure: the fix turns it into an
    unexpected success, which fails the run until the marker is removed.

RUN
    python3 -m unittest addon/AcadAgent/tests/test_engine.py -v
"""
import json
import os
import shutil
import socket
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_claude_cli import FAKE, _Env, load_acadagent  # noqa: E402

_PKG = load_acadagent("settings", "claude_cli", "engine")
engine = _PKG.engine
settings = _PKG.settings
cli = _PKG.claude_cli


class _Cfg(unittest.TestCase):
    """Settings in a temp dir; claude lookups pinned per test."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="acadagent-engine-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self._dir, self._path = settings.CONFIG_DIR, settings.CONFIG_PATH
        settings.CONFIG_DIR = os.path.join(self.tmp, "cfg")
        settings.CONFIG_PATH = os.path.join(settings.CONFIG_DIR,
                                            "settings.json")
        self._find, self._version = cli.find_claude, cli.version
        self.env = _Env()

    def tearDown(self):
        settings.CONFIG_DIR, settings.CONFIG_PATH = self._dir, self._path
        cli.find_claude, cli.version = self._find, self._version
        self.env.restore()

    def write_raw(self, text):
        os.makedirs(settings.CONFIG_DIR, exist_ok=True)
        with open(settings.CONFIG_PATH, "w", encoding="utf-8") as fh:
            fh.write(text)

    def write(self, cfg):
        self.write_raw(json.dumps(cfg))


class TestSettingsLoad(_Cfg):

    def test_missing_file_is_defaults(self):
        self.assertEqual(settings.load(), settings.DEFAULTS)

    def test_load_returns_a_copy(self):
        settings.load()["provider"] = "mutated"
        self.assertEqual(settings.DEFAULTS["provider"], "anthropic")

    def test_values_override_defaults(self):
        self.write({"engine": "opencode", "model": "m"})
        cfg = settings.load()
        self.assertEqual(cfg["engine"], "opencode")
        self.assertEqual(cfg["model"], "m")
        self.assertEqual(cfg["backend_url"], settings.DEFAULTS["backend_url"])

    def test_truncated_json_is_defaults(self):
        self.write_raw('{"engine": "opencode", ')
        self.assertEqual(settings.load(), settings.DEFAULTS)

    def test_binary_garbage_is_defaults(self):
        os.makedirs(settings.CONFIG_DIR, exist_ok=True)
        with open(settings.CONFIG_PATH, "wb") as fh:
            fh.write(b"\xff\xfe\x00garbage")
        self.assertEqual(settings.load(), settings.DEFAULTS)

    def test_json_string_is_defaults(self):
        self.write_raw('"just a string"')
        self.assertEqual(settings.load(), settings.DEFAULTS)

    def test_json_null_is_defaults(self):
        self.write_raw("null")
        self.assertEqual(settings.load(), settings.DEFAULTS)

    def test_json_number_is_defaults(self):
        self.write_raw("42")
        self.assertEqual(settings.load(), settings.DEFAULTS)

    def test_json_list_is_defaults(self):
        self.write_raw("[1, 2]")
        self.assertEqual(settings.load(), settings.DEFAULTS)

    def test_save_then_load_round_trips(self):
        path = settings.save({"engine": "api", "model": "x Ø"})
        self.assertEqual(path, settings.CONFIG_PATH)
        self.assertEqual(settings.load()["model"], "x Ø")


class TestEngineSelection(_Cfg):

    def test_default_is_claude(self):
        self.assertEqual(engine.DEFAULT, engine.CLAUDE)
        self.assertEqual(engine.current(), engine.CLAUDE)

    def test_unknown_engine_falls_back(self):
        for bad in ("gpt-agent", "", None, 0):
            self.write({"engine": bad})
            self.assertEqual(engine.current(), engine.DEFAULT, repr(bad))

    def test_corrupt_file_falls_back(self):
        self.write_raw("{{{")
        self.assertEqual(engine.current(), engine.DEFAULT)

    def test_falsy_engine_value_falls_back(self):
        for bad in ([], {}, False):
            self.write({"engine": bad})
            self.assertEqual(engine.current(), engine.DEFAULT, repr(bad))

    def test_unhashable_engine_value_falls_back(self):
        """Regression: a hand-edited {"engine": ["claude"]} used to make
        `name in {...}` raise TypeError in current(), which every chat send
        and the settings dialog call (measured 2026-09-25). Fixed in
        engine.py (WS-CHAT, release round 1); the expectedFailure marker was
        removed when it became an unexpected success."""
        self.write({"engine": ["claude"]})
        try:
            got = engine.current()
        except TypeError as exc:
            self.fail("engine.current() raised %r" % exc)
        self.assertEqual(got, engine.DEFAULT)

    def test_select_persists_and_keeps_other_keys(self):
        self.write({"model": "keep-me"})
        self.assertEqual(engine.select(engine.OPENCODE), engine.OPENCODE)
        cfg = settings.load()
        self.assertEqual(cfg["engine"], engine.OPENCODE)
        self.assertEqual(cfg["model"], "keep-me")
        # R24: a dev engine is read back only when dev engines are offered.
        self.env.set("ATECH_DEV_ENGINES", None)
        self.assertEqual(engine.current(), engine.CLAUDE)
        self.env.set("ATECH_DEV_ENGINES", "1")
        self.assertEqual(engine.current(), engine.OPENCODE)

    def test_r24_public_build_offers_claude_code_only(self):
        self.env.set("ATECH_DEV_ENGINES", None)
        self.assertEqual([e[0] for e in engine.offered()], [engine.CLAUDE])
        self.env.set("ATECH_DEV_ENGINES", "1")
        self.assertEqual([e[0] for e in engine.offered()],
                         [e[0] for e in engine.ENGINES])
        self.assertEqual(len(engine.offered()), 3)

    def test_select_unknown_raises_and_writes_nothing(self):
        with self.assertRaises(ValueError):
            engine.select("nope")
        self.assertFalse(os.path.exists(settings.CONFIG_PATH))

    def test_labels_and_provider_axis(self):
        self.assertEqual(engine.label(engine.CLAUDE), "Claude Code")
        self.assertEqual(engine.label("zzz"), "zzz")
        self.assertFalse(engine.uses_provider(engine.CLAUDE))
        self.assertTrue(engine.uses_provider(engine.OPENCODE))
        self.assertTrue(engine.uses_provider(engine.API))


class TestAvailability(_Cfg):

    def test_claude_present(self):
        exe = os.path.join(self.tmp, "claude")
        with open(exe, "w", encoding="utf-8") as fh:
            fh.write(FAKE % {"py": sys.executable})
        os.chmod(exe, 0o755)
        cli.find_claude = lambda *a, **k: exe
        self.assertEqual(engine.available(engine.CLAUDE), (True, ""))

    def test_claude_missing_says_what_to_do(self):
        cli.find_claude = lambda *a, **k: None
        ok, why = engine.available(engine.CLAUDE)
        self.assertFalse(ok)
        self.assertIn("claude", why)
        self.assertTrue(why.strip(), "an unavailable engine must say why")

    def test_opencode_listening_socket(self):
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        try:
            port = srv.getsockname()[1]
            self.write({"backend_url": "http://127.0.0.1:%d/api" % port})
            self.assertEqual(engine.available(engine.OPENCODE), (True, ""))
        finally:
            srv.close()

    def test_opencode_closed_port_names_host_and_port(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()                        # nothing listens there now
        self.write({"backend_url": "http://127.0.0.1:%d" % port})
        ok, why = engine.available(engine.OPENCODE)
        self.assertFalse(ok)
        self.assertIn("127.0.0.1:%d" % port, why)

    def test_api_needs_a_configured_key(self):
        self.assertFalse(engine.available(engine.API)[0])
        self.write({"api_key_set": True})
        self.assertEqual(engine.available(engine.API), (True, ""))

    def test_unknown_engine_is_unavailable(self):
        ok, why = engine.available("warp-drive")
        self.assertFalse(ok)
        self.assertIn("warp-drive", why)

    def test_split(self):
        self.assertEqual(engine._split("http://h:1234/x"), ("h", 1234))
        self.assertEqual(engine._split("http://h/x"), ("h", 4096))
        self.assertEqual(engine._split("h:bad"), ("h", 4096))
        self.assertEqual(engine._split("127.0.0.1:9"), ("127.0.0.1", 9))


class TestStatusLine(_Cfg):

    def test_ready_line_carries_version(self):
        cli.find_claude = lambda *a, **k: "/fake/claude"
        cli.version = lambda *a, **k: "2.1.232 (Claude Code)"
        self.assertEqual(engine.status_line(), "Claude Code 2.1.232 — ready")

    def test_unavailable_line_carries_reason(self):
        cli.find_claude = lambda *a, **k: None
        line = engine.status_line()
        self.assertTrue(line.startswith("Claude Code — unavailable: "), line)


if __name__ == "__main__":
    unittest.main()
