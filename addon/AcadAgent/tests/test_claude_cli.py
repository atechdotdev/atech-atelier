"""Contract tests for acadagent.claude_cli — the DEFAULT chat engine.

WHY THIS FILE EXISTS
    Claude Code is the default engine (engine.DEFAULT), yet until R46 the only
    parser under test was the non-default opencode one (test_client_parse).
    Nothing pinned how a `claude -p ... --output-format stream-json` stream
    becomes panel signals: the missing CLI, the not-logged-in record, an exit
    0 with no result, stderr big enough to fill a pipe.

HOW IT TESTS
    A FAKE `claude` — a tiny Python script written to a temp dir — replays a
    fixture on stdout, writes chosen stderr, records its argv and a few env
    vars, and exits with a chosen code. ClaudeRun.run() is called directly
    (synchronously, no thread), and its signals are recorded.

    PySide6 is replaced by a small functional stub (Signal with connect/emit,
    QThread with a `finished` signal), and claude_cli is loaded as a private
    copy under that stub. So this runs under plain system Python in CI, and a
    stub installed by another test file cannot leak in or out.

THE FIXTURES ARE MEASURED, NOT INVENTED
    LIVE_OK and LIVE_NOT_LOGGED_IN are records from real runs of claude
    2.1.232 on 2026-09-25, trimmed to the keys claude_cli reads plus the ones
    that disambiguate them (large arrays like `tools`/`usage` dropped; every
    value kept is verbatim):
        claude -p "Reply with exactly: PARSER_OK" --output-format stream-json
               --verbose --permission-mode manual --tools ""
        HOME=<empty dir> claude -p "hi" --output-format stream-json --verbose
    Two facts the live capture taught, both pinned below:
      - a `rate_limit_event` record precedes `system/init`;
      - NOT LOGGED IN arrives as subtype "success" with is_error true, after a
        synthetic assistant text "Not logged in · Please run /login", and the
        CLI exits 1. is_error must win over subtype.
    TOOL_USE is constructed from the documented shape (module docstring of
    claude_cli), not captured — marked as such.

RUN
    python3 -m unittest addon/AcadAgent/tests/test_claude_cli.py -v
"""
import importlib.util
import json
import os
import shutil
import stat
import sys
import tempfile
import threading
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.environ.get("ATECH_ADDON_DIR") or os.path.dirname(HERE)
PKG_DIR = os.path.join(ADDON, "acadagent")


# ------------------------------------------------------------ PySide6 stub
class _Bound(object):
    def __init__(self):
        self._slots = []

    def connect(self, fn):
        self._slots.append(fn)

    def emit(self, *args):
        for fn in list(self._slots):
            fn(*args)


class _Signal(object):
    """Descriptor: one _Bound per instance, like a Qt SignalInstance."""

    def __init__(self, *types_):
        self._name = None

    def __set_name__(self, owner, name):
        self._name = name

    def __get__(self, obj, owner):
        if obj is None:
            return self
        key = "_sig_" + self._name
        bound = obj.__dict__.get(key)
        if bound is None:
            bound = obj.__dict__[key] = _Bound()
        return bound


class _QObject(object):
    def __init__(self, *a, **k):
        pass


class _QThread(_QObject):
    finished = _Signal()

    def wait(self, *a):
        return True

    def isRunning(self):
        return False


def _stub_modules():
    core = types.ModuleType("PySide6.QtCore")
    core.Signal = _Signal
    core.QThread = _QThread
    core.QObject = _QObject
    core.Qt = types.SimpleNamespace(ToolTipRole=3)
    core.QTimer = types.SimpleNamespace(singleShot=lambda *a, **k: None)
    widgets = types.ModuleType("PySide6.QtWidgets")
    widgets.QDialog = _QObject
    root = types.ModuleType("PySide6")
    root.QtCore = core
    root.QtWidgets = widgets
    return {"PySide6": root, "PySide6.QtCore": core,
            "PySide6.QtWidgets": widgets}


_LOADED = {}


def load_acadagent(*submodules):
    """A private copy of the acadagent package, imported under the PySide6
    stub. Returns the package; submodules are attributes on it.

    Private (package name `acadagent_stubbed`) so it never collides with a
    real `acadagent` import or with another test file's stub.
    """
    name = "acadagent_stubbed"
    saved = {k: sys.modules.get(k) for k in _stub_modules()}
    sys.modules.update(_stub_modules())
    try:
        pkg = _LOADED.get(name)
        if pkg is None:
            spec = importlib.util.spec_from_file_location(
                name, os.path.join(PKG_DIR, "__init__.py"),
                submodule_search_locations=[PKG_DIR])
            pkg = importlib.util.module_from_spec(spec)
            sys.modules[name] = pkg
            spec.loader.exec_module(pkg)
            _LOADED[name] = pkg
        for sub in submodules:
            importlib.import_module("%s.%s" % (name, sub))
        return pkg
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


_PKG = load_acadagent("settings", "claude_cli")
cli = _PKG.claude_cli
# Never read the developer's real ~/.config/acadagent/settings.json (it may
# name a claude_path). Every test starts from "no settings file".
_PKG.settings.CONFIG_DIR = tempfile.mkdtemp(prefix="acadagent-cfg-")
_PKG.settings.CONFIG_PATH = os.path.join(_PKG.settings.CONFIG_DIR,
                                         "settings.json")


# --------------------------------------------------------------- fixtures
SID = "0292cf1b-a159-480d-83df-7a91f1f815b1"
LIVE_OK = [
    {"type": "rate_limit_event",
     "rate_limit_info": {"status": "allowed", "rateLimitType": "five_hour"},
     "session_id": SID},
    {"type": "system", "subtype": "init", "session_id": SID,
     "permissionMode": "manual", "claude_code_version": "2.1.232"},
    {"type": "assistant", "session_id": SID, "parent_tool_use_id": None,
     "message": {"model": "claude-opus-5", "type": "message",
                 "role": "assistant",
                 "content": [{"type": "text", "text": "PARSER_OK"}]}},
    {"type": "result", "subtype": "success", "is_error": False,
     "terminal_reason": "completed", "api_error_status": None,
     "result": "PARSER_OK", "session_id": SID, "num_turns": 1},
]

SID_NL = "4218d6c2-f4a2-4266-8622-7ee8bc428f7e"
NOT_LOGGED_IN = "Not logged in · Please run /login"
LIVE_NOT_LOGGED_IN = [
    {"type": "system", "subtype": "init", "session_id": SID_NL,
     "permissionMode": "default"},
    {"type": "assistant", "session_id": SID_NL,
     "error": "authentication_failed", "is_api_error_message": True,
     "message": {"model": "<synthetic>", "role": "assistant",
                 "type": "message",
                 "content": [{"type": "text", "text": NOT_LOGGED_IN}]}},
    {"type": "result", "subtype": "success", "is_error": True,
     "terminal_reason": "api_error", "api_error_status": None,
     "result": NOT_LOGGED_IN, "session_id": SID_NL, "num_turns": 1},
]
LIVE_NOT_LOGGED_IN_EXIT = 1

# CONSTRUCTED (documented shape, not a live capture).
TOOL_USE = [
    {"type": "system", "subtype": "init", "session_id": "s-tool"},
    {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Write",
         "input": {"file_path": "/home/u/Atech Atelier/agent/chat-1/model.py",
                   "content": "import Part\n"}},
        {"type": "tool_use", "name": "Bash",
         "input": {"command": "ls   -la\n  /tmp"}},
        {"type": "text", "text": "Built a box."}]}},
    {"type": "user", "message": {"content": [
        {"type": "tool_result", "content": "ok"}]}},
    {"type": "result", "subtype": "success", "is_error": False,
     "result": "Built a box.", "session_id": "s-tool"},
]


def ndjson(records, junk=()):
    lines = [json.dumps(r) for r in records]
    for pos, text in junk:
        lines.insert(pos, text)
    return "\n".join(lines) + "\n"


FAKE = r'''#!%(py)s
import json, os, sys
if len(sys.argv) > 1 and sys.argv[1] == "--version":
    sys.stdout.write(os.environ.get("FAKE_CLAUDE_VERSION", "") + "\n")
    sys.exit(0)
if sys.argv[1:3] == ["auth", "status"]:
    sys.stdout.write(os.environ.get("FAKE_CLAUDE_AUTH", ""))
    sys.exit(int(os.environ.get("FAKE_CLAUDE_EXIT", "0")))
if sys.argv[1:] == ["--help"]:
    sys.stdout.write(os.environ.get("FAKE_CLAUDE_HELP", "") + "\n")
    sys.exit(0)
# R35: the prompt arrives on stdin, not argv.
stdin = "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()
spf = None
if "--append-system-prompt-file" in sys.argv:
    p = sys.argv[sys.argv.index("--append-system-prompt-file") + 1]
    with open(p, encoding="utf-8") as fh:
        spf = {"text": fh.read(), "mode": oct(os.stat(p).st_mode & 0o777),
               "dir_mode": oct(os.stat(os.path.dirname(p)).st_mode & 0o777),
               "path": p}
rec = os.environ.get("FAKE_CLAUDE_RECORD")
if rec:
    with open(rec, "w", encoding="utf-8") as fh:
        json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(),
                   "stdin": stdin, "spf": spf,
                   "env": {k: os.environ.get(k) for k in
                           ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH")}},
                  fh)
err = int(os.environ.get("FAKE_CLAUDE_STDERR_BYTES", "0") or 0)
if err:
    sys.stderr.write("E" * err)
    sys.stderr.flush()
sys.stderr.write(os.environ.get("FAKE_CLAUDE_STDERR", ""))
fx = os.environ.get("FAKE_CLAUDE_FIXTURE")
if fx:
    with open(fx, encoding="utf-8") as fh:
        sys.stdout.write(fh.read())
sys.stdout.flush()
slp = float(os.environ.get("FAKE_CLAUDE_SLEEP_AFTER", "0") or 0)
if slp:
    import time
    time.sleep(slp)
sys.exit(int(os.environ.get("FAKE_CLAUDE_EXIT", "0")))
'''


class _Env(object):
    """Set env vars for one test and restore them."""

    def __init__(self):
        self._saved = {}

    def set(self, key, value):
        if key not in self._saved:
            self._saved[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    def restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._saved = {}


class FakeClaudeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fake-claude-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        self.exe = os.path.join(self.bin, "claude")
        with open(self.exe, "w", encoding="utf-8") as fh:
            fh.write(FAKE % {"py": sys.executable})
        os.chmod(self.exe, os.stat(self.exe).st_mode | stat.S_IXUSR)
        self.record = os.path.join(self.tmp, "record.json")
        self.env = _Env()
        self.env.set("FAKE_CLAUDE_RECORD", self.record)
        for k in ("FAKE_CLAUDE_FIXTURE", "FAKE_CLAUDE_EXIT",
                  "FAKE_CLAUDE_STDERR", "FAKE_CLAUDE_STDERR_BYTES",
                  "FAKE_CLAUDE_HELP", "FAKE_CLAUDE_SLEEP_AFTER"):
            self.env.set(k, None)
        # Never let the developer's real ~/.local/bin/claude answer.
        self._find = cli.find_claude
        cli.find_claude = lambda: self.exe

    def tearDown(self):
        cli.find_claude = self._find
        self.env.restore()

    def fixture(self, text, exit_code=0, stderr=""):
        path = os.path.join(self.tmp, "fixture.ndjson")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        self.env.set("FAKE_CLAUDE_FIXTURE", path)
        self.env.set("FAKE_CLAUDE_EXIT", str(exit_code))
        self.env.set("FAKE_CLAUDE_STDERR", stderr)

    def turn(self, timeout=30, **kwargs):
        """Run one ClaudeRun synchronously; return the recorded signals."""
        kwargs.setdefault("cwd", self.tmp)
        run = cli.ClaudeRun(kwargs.pop("prompt", "hello"), **kwargs)
        got = {"session": [], "text": [], "tool": [], "ok": [], "failed": []}
        run.started_session.connect(lambda s: got["session"].append(s))
        run.text.connect(lambda t: got["text"].append(t))
        run.tool.connect(lambda n, a: got["tool"].append((n, a)))
        run.finished_ok.connect(lambda t, r: got["ok"].append((t, r)))
        run.failed.connect(lambda why: got["failed"].append(why))
        th = threading.Thread(target=run.run, daemon=True)
        th.start()
        th.join(timeout)
        self.assertFalse(th.is_alive(), "ClaudeRun.run() hung for %ss" % timeout)
        got["run"] = run
        return got

    def recorded(self):
        with open(self.record, encoding="utf-8") as fh:
            return json.load(fh)


# ------------------------------------------------------------------ tests
class TestLiveSuccess(FakeClaudeCase):

    def test_success_stream_becomes_one_reply(self):
        self.fixture(ndjson(LIVE_OK))
        got = self.turn()
        self.assertEqual(got["failed"], [])
        self.assertEqual(got["session"], [SID])
        self.assertEqual(got["text"], ["PARSER_OK"])
        self.assertEqual(len(got["ok"]), 1)
        final, record = got["ok"][0]
        self.assertEqual(final, "PARSER_OK")
        self.assertIs(record["is_error"], False)
        self.assertEqual(got["run"].session_id, SID)

    def test_rate_limit_event_is_ignored(self):
        """The live stream opens with rate_limit_event; it carries a
        session_id but is not init, and must not start a session twice."""
        self.fixture(ndjson(LIVE_OK))
        got = self.turn()
        self.assertEqual(len(got["session"]), 1)

    def test_non_json_lines_are_skipped_not_fatal(self):
        self.fixture(ndjson(LIVE_OK, junk=[(0, "Warning: something"),
                                           (3, "{not json"), (4, "")]))
        got = self.turn()
        self.assertEqual(got["failed"], [])
        self.assertEqual(got["ok"][0][0], "PARSER_OK")

    def test_nonzero_exit_after_a_success_record_is_still_the_record(self):
        """The result record, not the exit code, is the verdict."""
        self.fixture(ndjson(LIVE_OK), exit_code=3)
        got = self.turn()
        self.assertEqual(got["failed"], [])
        self.assertEqual(got["ok"][0][0], "PARSER_OK")


class TestFailures(FakeClaudeCase):

    def test_not_logged_in_fails_with_the_cli_message(self):
        self.fixture(ndjson(LIVE_NOT_LOGGED_IN),
                     exit_code=LIVE_NOT_LOGGED_IN_EXIT)
        got = self.turn()
        self.assertEqual(got["ok"], [], "is_error must win over subtype=success")
        self.assertEqual(got["failed"], [NOT_LOGGED_IN])

    def test_is_error_without_text_falls_back_to_stderr(self):
        rec = {"type": "result", "subtype": "error_during_execution",
               "is_error": True, "result": ""}
        self.fixture(ndjson([rec]), exit_code=1, stderr="API Error: 529\n")
        got = self.turn()
        self.assertEqual(got["failed"], ["API Error: 529"])

    def test_is_error_without_text_or_stderr_says_so(self):
        rec = {"type": "result", "is_error": True}
        self.fixture(ndjson([rec]), exit_code=1)
        got = self.turn()
        self.assertEqual(got["failed"], ["claude reported an error"])

    def test_exit_zero_without_result_is_not_success(self):
        self.fixture(ndjson(LIVE_OK[:3]), exit_code=0)
        got = self.turn()
        self.assertEqual(got["ok"], [])
        self.assertEqual(got["failed"], ["claude exited 0 without a result"])
        self.assertEqual(got["text"], ["PARSER_OK"])

    def test_crash_reports_exit_code_and_stderr(self):
        self.fixture("", exit_code=2, stderr="error: unknown option '--bogus'\n")
        got = self.turn()
        self.assertEqual(got["ok"], [])
        self.assertEqual(len(got["failed"]), 1)
        self.assertIn("exited 2", got["failed"][0])
        self.assertIn("unknown option '--bogus'", got["failed"][0])

    def test_missing_cli_fails_before_spawning(self):
        cli.find_claude = lambda: None
        self.fixture(ndjson(LIVE_OK))
        got = self.turn()
        self.assertEqual(got["ok"], [])
        self.assertEqual(got["failed"],
                         ["the `claude` CLI was not found on this system"])
        self.assertFalse(os.path.exists(self.record), "nothing may be spawned")

    def test_unstartable_binary_is_reported(self):
        broken = os.path.join(self.tmp, "not-executable")
        with open(broken, "w") as fh:
            fh.write("")
        cli.find_claude = lambda: broken
        got = self.turn()
        self.assertEqual(len(got["failed"]), 1)
        self.assertTrue(got["failed"][0].startswith("could not start claude:"),
                        got["failed"][0])

    def test_large_stderr_does_not_hang_the_turn(self):
        """stderr goes to a file: 256 KB would block a pipe nobody drains."""
        self.fixture(ndjson(LIVE_OK))
        self.env.set("FAKE_CLAUDE_STDERR_BYTES", str(256 * 1024))
        got = self.turn(timeout=20)
        self.assertEqual(got["ok"][0][0], "PARSER_OK")

    def test_cancel_reports_cancelled_not_success(self):
        self.fixture(ndjson(LIVE_OK))
        run = cli.ClaudeRun("x", cwd=self.tmp)
        failed, ok = [], []
        run.failed.connect(failed.append)
        run.finished_ok.connect(lambda *a: ok.append(a))
        run.cancel()
        run.run()
        self.assertEqual(failed, ["cancelled"])
        self.assertEqual(ok, [])
        self.assertFalse(os.path.exists(self.record),
                         "a turn cancelled before spawn must not spawn")


class TestToolUse(FakeClaudeCase):

    def test_tool_use_blocks_become_tool_signals(self):
        self.fixture(ndjson(TOOL_USE))
        got = self.turn()
        self.assertEqual(got["tool"], [("Write", "model.py"),
                                       ("Bash", "ls -la /tmp")])
        self.assertEqual(got["text"], ["Built a box."])
        self.assertEqual(got["ok"][0][0], "Built a box.")


class TestArgvAndEnv(FakeClaudeCase):

    def test_default_argv(self):
        self.fixture(ndjson(LIVE_OK))
        self.turn(prompt="make a box")
        rec = self.recorded()
        argv = rec["argv"]
        # R35: the prompt is on stdin; argv carries no free text.
        self.assertEqual(argv[:4], ["-p", "--output-format",
                                    "stream-json", "--verbose"])
        self.assertNotIn("make a box", argv)
        self.assertEqual(rec["stdin"], "make a box")
        i = argv.index("--permission-mode")
        self.assertEqual(argv[i + 1], "manual")
        self.assertNotIn("--resume", argv)
        self.assertNotIn("--model", argv)

    def test_resume_model_and_extra_args_in_order(self):
        self.fixture(ndjson(LIVE_OK))
        self.turn(session_id="sess-1", model="opus", permission_mode="acceptEdits",
                  extra_args=["--append-system-prompt", "SYS", "--add-dir", "/w"])
        argv = self.recorded()["argv"]
        self.assertEqual(argv[argv.index("--resume") + 1], "sess-1")
        self.assertEqual(argv[argv.index("--model") + 1], "opus")
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "acceptEdits")
        self.assertEqual(argv[-4:], ["--append-system-prompt", "SYS",
                                     "--add-dir", "/w"])

    def test_only_existing_images_are_named(self):
        img = os.path.join(self.tmp, "view.png")
        with open(img, "wb") as fh:
            fh.write(b"\x89PNG")
        self.fixture(ndjson(LIVE_OK))
        self.turn(prompt="what is this", images=[img, "/nope/missing.png", ""])
        prompt = self.recorded()["stdin"]
        self.assertTrue(prompt.startswith("what is this\n"))
        self.assertIn(img, prompt)
        self.assertNotIn("missing.png", prompt)

    def test_no_real_images_leaves_prompt_untouched(self):
        self.fixture(ndjson(LIVE_OK))
        self.turn(prompt="plain", images=["/nope.png"])
        self.assertEqual(self.recorded()["stdin"], "plain")

    def test_cwd_is_the_workspace(self):
        ws = os.path.join(self.tmp, "ws")
        os.makedirs(ws)
        self.fixture(ndjson(LIVE_OK))
        self.turn(cwd=ws)
        self.assertEqual(os.path.realpath(self.recorded()["cwd"]),
                         os.path.realpath(ws))

    def test_appimage_python_env_is_stripped_for_the_child(self):
        self.env.set("PYTHONHOME", "/appimage/usr")
        self.env.set("PYTHONPATH", "/appimage/usr/lib")
        self.env.set("LD_LIBRARY_PATH", "/appimage/usr/lib")
        self.fixture(ndjson(LIVE_OK))
        self.turn()
        env = self.recorded()["env"]
        self.assertEqual(env, {"PYTHONHOME": None, "PYTHONPATH": None,
                               "LD_LIBRARY_PATH": None})

    def test_unknown_permission_mode_is_refused(self):
        # MEASURED in claude_cli: "default" is not a valid CLI choice.
        for bad in ("default", "yolo"):
            with self.assertRaises(ValueError):
                cli.ClaudeRun("x", permission_mode=bad)


class TestRobustStream(FakeClaudeCase):
    """R19 regressions: odd-but-valid JSON must not break the turn."""

    def test_non_dict_json_lines_are_skipped(self):
        self.fixture(ndjson(LIVE_OK, junk=[(1, "null"), (2, "[1, 2]"),
                                           (3, '"a string"'), (4, "42")]))
        got = self.turn()
        self.assertEqual(got["failed"], [])
        self.assertEqual(got["ok"][0][0], "PARSER_OK")

    def test_malformed_assistant_records_are_skipped(self):
        recs = [LIVE_OK[1],
                {"type": "assistant", "message": None},
                {"type": "assistant", "message": {"content": [None, 3, "x"]}},
                {"type": "assistant", "message": {"content": [
                    {"type": "text", "text": 7}]}},
                LIVE_OK[2], LIVE_OK[3]]
        self.fixture(ndjson(recs))
        got = self.turn()
        self.assertEqual(got["text"], ["PARSER_OK"])
        self.assertEqual(got["ok"][0][0], "PARSER_OK")

    def test_every_path_emits_exactly_one_outcome(self):
        for text, code in ((ndjson(LIVE_OK), 0),
                           (ndjson(LIVE_NOT_LOGGED_IN), 1),
                           ("", 0), ("garbage\n", 9)):
            self.fixture(text, exit_code=code)
            got = self.turn()
            self.assertEqual(len(got["ok"]) + len(got["failed"]), 1,
                             "fixture %r exit %d" % (text[:30], code))

    def test_api_retry_then_error_reads_as_offline(self):
        # CONSTRUCTED from the shape claude_cli documents for offline runs.
        recs = [{"type": "system", "subtype": "init", "session_id": "s"}]
        recs += [{"type": "system", "subtype": "api_retry",
                  "error": "ENOTFOUND api.anthropic.com"}] * 3
        recs += [{"type": "result", "subtype": "error_during_execution",
                  "is_error": True}]
        self.fixture(ndjson(recs), exit_code=1)
        got = self.turn()
        self.assertEqual(len(got["failed"]), 1)
        self.assertIn("could not reach the Claude API (retried 3 times",
                      got["failed"][0])
        self.assertEqual(cli.classify_failure(got["failed"][0]), cli.OFFLINE)


class _Isolated(unittest.TestCase):
    """HOME, PATH, settings and the known install list point at a temp tree,
    so neither the developer's real claude nor /usr/local/bin/claude can
    answer."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="find-claude-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)
        self.env = _Env()
        self.env.set("HOME", self.home)
        self.env.set("PATH", os.path.join(self.tmp, "empty-path"))
        self.env.set("FAKE_CLAUDE_RECORD", None)
        self._known = cli.KNOWN_LOCATIONS
        cli.KNOWN_LOCATIONS = tuple(p for p in self._known
                                    if p.startswith("~/"))
        # DEFAULT_BIN is expanded at import time, from the real HOME.
        self._default = getattr(cli, "DEFAULT_BIN", None)
        cli.DEFAULT_BIN = os.path.join(self.home, ".local", "bin", "claude")
        self._shell = cli._SHELL_FOUND
        cli._SHELL_FOUND = ""          # probed, nothing found
        cli._VERSIONS.clear()
        self._cfg = _PKG.settings.CONFIG_PATH
        _PKG.settings.CONFIG_PATH = os.path.join(self.tmp, "settings.json")

    def tearDown(self):
        cli.KNOWN_LOCATIONS = self._known
        cli.DEFAULT_BIN = self._default
        cli._SHELL_FOUND = self._shell
        cli._VERSIONS.clear()
        _PKG.settings.CONFIG_PATH = self._cfg
        self.env.restore()

    def _exe(self, rel, executable=True):
        path = os.path.join(self.home, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(FAKE % {"py": sys.executable})
        os.chmod(path, 0o755 if executable else 0o644)
        return path

    def _configure(self, claude_path):
        with open(_PKG.settings.CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump({"claude_path": claude_path}, fh)


class TestFind(_Isolated):

    def test_nothing_installed_is_none(self):
        self.assertIsNone(cli.find_claude())
        self.assertFalse(cli.available())
        self.assertIsNone(cli.version())
        self.assertEqual(cli.auth_status(), (None, "not found"))

    def test_native_installer_location(self):
        exe = self._exe(".local/bin/claude")
        self.assertEqual(cli.find_claude(), exe)
        self.assertTrue(cli.available())

    def test_non_executable_candidate_is_skipped(self):
        self._exe(".local/bin/claude", executable=False)
        self.assertIsNone(cli.find_claude())

    def test_path_is_a_fallback(self):
        d = os.path.join(self.tmp, "pathdir")
        os.makedirs(d)
        exe = os.path.join(d, "claude")
        with open(exe, "w") as fh:
            fh.write("#!/bin/sh\n")
        os.chmod(exe, 0o755)
        self.env.set("PATH", d)
        self.assertEqual(cli.find_claude(), exe)

    def test_newest_nvm_node_wins(self):
        self._exe(".nvm/versions/node/v9.11.2/bin/claude")
        new = self._exe(".nvm/versions/node/v22.3.1/bin/claude")
        self._exe(".nvm/versions/node/v18.20.0/bin/claude")
        self.assertEqual(cli.find_claude(), new)

    def test_configured_path_wins(self):
        self._exe(".local/bin/claude")
        chosen = self._exe("tools/my-claude")
        self._configure(chosen)
        self.assertEqual(cli.find_claude(), chosen)

    def test_wrong_configured_path_is_not_replaced(self):
        """The user chose a path; another claude is not silently used."""
        self._exe(".local/bin/claude")
        self._configure(os.path.join(self.home, "nope", "claude"))
        self.assertIsNone(cli.find_claude())


class TestVersionAndAuth(_Isolated):

    def setUp(self):
        super().setUp()
        self.exe = self._exe(".local/bin/claude")

    def test_version_is_the_cli_output(self):
        self.env.set("FAKE_CLAUDE_VERSION", "2.1.232 (Claude Code)")
        self.assertEqual(cli.version(), "2.1.232 (Claude Code)")

    def test_empty_version_is_none_not_a_guess(self):
        self.env.set("FAKE_CLAUDE_VERSION", "")
        self.assertIsNone(cli.version())

    def test_auth_logged_out_measured_shape(self):
        # MEASURED shape per claude_cli.auth_status docstring (2.1.232).
        self.env.set("FAKE_CLAUDE_AUTH",
                     '{"loggedIn": false, "authMethod": "none"}')
        self.env.set("FAKE_CLAUDE_EXIT", "1")
        self.assertEqual(cli.auth_status(), (False, "none"))

    def test_auth_logged_in(self):
        self.env.set("FAKE_CLAUDE_AUTH",
                     '{"loggedIn": true, "authMethod": "claude.ai"}')
        self.assertEqual(cli.auth_status(), (True, "claude.ai"))

    def test_unreadable_auth_is_unknown_not_logged_in(self):
        for out in ("", "Usage: claude ...", '{"other": 1}', "[]"):
            self.env.set("FAKE_CLAUDE_AUTH", out)
            logged_in, _ = cli.auth_status()
            self.assertIsNone(logged_in, "output %r" % out)


class TestClassify(unittest.TestCase):

    def test_live_not_logged_in_is_auth(self):
        self.assertEqual(cli.classify_failure(NOT_LOGGED_IN), cli.AUTH)

    def test_cancelled(self):
        self.assertEqual(cli.classify_failure("cancelled"), cli.CANCELLED)

    def test_unknown_stays_other(self):
        for msg in ("", None, "claude exited 2 without a result",
                    "the Claude Code run broke: KeyError: 'x'"):
            self.assertEqual(cli.classify_failure(msg), cli.OTHER, msg)

class TestSummarise(unittest.TestCase):

    def test_known_keys(self):
        s = cli._summarise
        self.assertEqual(s({"command": "echo  hi\n there"}), "echo hi there")
        self.assertEqual(s({"file_path": "/a/Atech Atelier/x/model.py"}), "model.py")
        self.assertEqual(s({"path": "/a/b/"}), "b")
        self.assertEqual(s({"pattern": "*.py"}), "*.py")

    def test_fallbacks(self):
        s = cli._summarise
        self.assertEqual(s(None), "")
        self.assertEqual(s({"b": 1, "a": 2}), '{"a": 2, "b": 1}')
        self.assertEqual(s(42), "42")

    def test_truncates_to_limit(self):
        out = cli._summarise({"command": "x" * 500}, limit=20)
        self.assertEqual(len(out), 20)
        self.assertTrue(out.endswith("…"))

    def test_never_raises(self):
        class Bad(object):
            def __str__(self):
                raise RuntimeError("no")
        self.assertEqual(cli._summarise(Bad()), "")
        self.assertEqual(cli._summarise({"x": object()}), "")


if __name__ == "__main__":
    unittest.main()
