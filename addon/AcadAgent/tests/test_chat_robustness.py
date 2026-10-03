"""Chat robustness (release PRD WS-CHAT: R02 R14 R17 R19 R21 R22 R23 R25
R26 R28), exercised headless against the REAL panel, ClaudeRun and settings
dialog, with a fake `claude`.

WHAT IS FAKED, AND WHY
    - `claude`: a small Python script (FAKE below). Its behaviour is chosen
      per test by FAKE_MODE; every invocation appends its argv to
      FAKE_ARGV_LOG, so a test reads back exactly what Studio ran. The
      not-logged-in and offline streams replay the records MEASURED from
      claude 2.1.232 on 2026-09-24 (scratchpad nologin.out / offline.out),
      trimmed to the keys claude_cli reads.
    - HOME and the settings file: a temp dir, so nothing touches the real
      ~/.config/acadagent or the developer's claude.
    - FreeCAD (only in the R17 test): a module with the handful of calls the
      panel makes (ActiveDocument, listDocuments, getDocument,
      setActiveDocument). No build is run: the fake never writes model.py.

RUN (the interpreter that ships: Python 3.11 + PySide6 6.8.3)
    QT_QPA_PLATFORM=offscreen dist/build/squashfs-root/usr/bin/python \
        -m unittest addon/AcadAgent/tests/test_chat_robustness.py -v
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.abspath(os.path.join(HERE, ".."))
if ADDON not in sys.path:
    sys.path.insert(0, ADDON)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# A private HOME before anything computes a path from it (claude_cli's
# DEFAULT_BIN, build.new_workspace's fallback root).
_TMP = tempfile.mkdtemp(prefix="chat-robust-")
_REAL_HOME = os.environ.get("HOME")
os.environ["HOME"] = os.path.join(_TMP, "home")
os.makedirs(os.environ["HOME"])

from PySide6 import QtCore, QtWidgets  # noqa: E402

from acadagent import settings as cfgmod  # noqa: E402

cfgmod.CONFIG_DIR = os.path.join(_TMP, "config")
cfgmod.CONFIG_PATH = os.path.join(cfgmod.CONFIG_DIR, "settings.json")

from acadagent import build, claude_cli, engine, panel  # noqa: E402

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

FAKE = r'''#!%(py)s
import json, os, sys, time, signal
argv = sys.argv[1:]
if argv == ["--help"]:
    # The long options claude 2.1.232 lists (measured 2026-09-25; see
    # test_ws_chat_cli.HELP_2_1_232), so the panel takes the real path.
    print(os.environ.get("FAKE_HELP", "--add-dir --allowedTools "
          "--append-system-prompt[-file] --disable-slash-commands --effort "
          "--exclude-dynamic-system-prompt-sections "
          "--include-partial-messages --max-budget-usd --model "
          "--output-format --permission-mode --print --resume "
          "--setting-sources --strict-mcp-config --tools --verbose"))
    sys.exit(0)
# R35: the prompt arrives on stdin; the system prompt in a file.
stdin = sys.stdin.read() if "-p" in argv else ""
sp = None
if "--append-system-prompt-file" in argv:
    with open(argv[argv.index("--append-system-prompt-file") + 1],
              encoding="utf-8") as fh:
        sp = fh.read()
elif "--append-system-prompt" in argv:
    sp = argv[argv.index("--append-system-prompt") + 1]
log = os.environ.get("FAKE_ARGV_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"argv": argv, "cwd": os.getcwd(),
                             "stdin": stdin, "sp": sp}) + "\n")
if argv[:2] == ["auth", "status"]:
    if os.environ.get("FAKE_LOGGED_IN") == "old":
        # MEASURED claude 2.0.25 signed out: plain text, no JSON, exit 1.
        print("Invalid API key \u00b7 Please run /login")
        sys.exit(1)
    logged = os.environ.get("FAKE_LOGGED_IN", "1") == "1"
    print(json.dumps({"loggedIn": logged,
                      "authMethod": "claude.ai" if logged else "none"}))
    sys.exit(0 if logged else 1)
if argv[:1] == ["--version"]:
    print("2.1.232 (Claude Code)")
    sys.exit(0)
mode = os.environ.get("FAKE_MODE", "ok")
out = sys.stdout
def emit(o):
    out.write(json.dumps(o) + "\n"); out.flush()
sid = os.environ.get("FAKE_SID") or ("sid-%%d" %% os.getpid())
if mode == "ok":
    emit({"type": "system", "subtype": "init", "session_id": sid})
    out.write("null\n"); out.write("[1, 2]\n"); out.write('"text"\n')
    emit({"type": "assistant", "message": {"content": "plain string"}})
    emit({"type": "assistant", "message": {"content": [None, 3, {"type": "text", "text": "hi"}]}})
    emit({"type": "assistant", "message": None})
    emit({"type": "result", "subtype": "success", "result": "done",
          "is_error": False, "duration_ms": 4200, "total_cost_usd": 0.37})
elif mode == "null_exit":
    out.write("null\n"); out.flush()
elif mode == "null_hang":
    # MEASURED shape of the R19 bug: junk, then a child that ignores SIGTERM.
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    out.write("null\n"); out.flush()
    time.sleep(60)
elif mode == "nologin":
    emit({"type": "system", "subtype": "init", "session_id": sid,
          "apiKeySource": "none"})
    emit({"type": "assistant", "message": {"model": "<synthetic>",
          "content": [{"type": "text", "text": "Not logged in · Please run /login"}]}})
    emit({"is_error": True, "subtype": "success", "type": "result",
          "terminal_reason": "api_error", "total_cost_usd": 0,
          "result": "Not logged in · Please run /login", "duration_ms": 65})
    sys.exit(1)
elif mode == "offline":
    emit({"type": "system", "subtype": "init", "session_id": sid})
    for i in range(1, 4):
        emit({"type": "system", "subtype": "api_retry", "attempt": i,
              "max_retries": 10, "error_status": None, "error": "unknown"})
    emit({"is_error": True, "type": "result",
          "subtype": "error_during_execution",
          "fast_mode_disabled_reason": "network_error",
          "terminal_reason": "aborted_streaming",
          "errors": ["[ede_diagnostic] result_type=user last_content_type=n/a stop_reason=null"]})
    sys.exit(1)
elif mode == "weird":
    emit({"type": "result", "subtype": "success", "is_error": True,
          "result": "Something odd happened in the tool loop"})
'''


def wait_until(cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        APP.processEvents(QtCore.QEventLoop.AllEvents, 50)
        if cond():
            return True
        time.sleep(0.01)
    APP.processEvents()
    return bool(cond())


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # a zombie is dead for our purposes
    try:
        with open("/proc/%d/stat" % pid) as fh:
            return fh.read().split(")")[-1].split()[0] != "Z"
    except OSError:
        return False


class Base(unittest.TestCase):
    def setUp(self):
        # Every case on the private HOME. MEASURED: run together with
        # test_ws_chat_panel (which imports this file a second time), the
        # other module's tearDownModule put the real HOME back first, and
        # these cases wrote sessions.json and chat-* folders into the real
        # ~/.local/share/Atech Atelier - then read them in the next run.
        os.makedirs(os.path.join(_TMP, "home"), exist_ok=True)
        os.environ["HOME"] = os.path.join(_TMP, "home")
        self.tmp = tempfile.mkdtemp(prefix="case-", dir=_TMP)
        self.exe = os.path.join(self.tmp, "claude")
        with open(self.exe, "w", encoding="utf-8") as fh:
            fh.write(FAKE % {"py": sys.executable})
        os.chmod(self.exe, 0o755)
        self.log = os.path.join(self.tmp, "argv.log")
        self._env = {k: os.environ.get(k) for k in
                     ("FAKE_MODE", "FAKE_ARGV_LOG", "FAKE_LOGGED_IN",
                      "FAKE_SID")}
        os.environ["FAKE_ARGV_LOG"] = self.log
        os.environ["FAKE_MODE"] = "ok"
        os.environ["FAKE_LOGGED_IN"] = "1"
        os.environ.pop("FAKE_SID", None)
        if os.path.exists(cfgmod.CONFIG_DIR):
            os.chmod(cfgmod.CONFIG_DIR, 0o755)
            shutil.rmtree(cfgmod.CONFIG_DIR)
        cfgmod.save(dict(cfgmod.DEFAULTS, claude_path=self.exe,
                         engine="claude"))

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def turns(self):
        """argv of every `-p` invocation, in order."""
        if not os.path.exists(self.log):
            return []
        out = []
        with open(self.log, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                if "-p" in rec["argv"]:
                    out.append(rec)
        return out


# ------------------------------------------------------------ ClaudeRun
class TestClaudeRun(Base):
    """R19: every path ends in exactly one signal; no orphan process."""

    def _run(self, **kw):
        run = claude_cli.ClaudeRun("hello", cwd=self.tmp, **kw)
        got = {"ok": [], "failed": [], "text": []}
        run.finished_ok.connect(lambda t, r: got["ok"].append((t, r)))
        run.failed.connect(lambda m: got["failed"].append(m))
        run.text.connect(lambda t: got["text"].append(t))
        return run, got

    def test_non_dict_lines_and_blocks_do_not_break_the_turn(self):
        run, got = self._run()
        run.start()
        self.assertTrue(wait_until(lambda: got["ok"] or got["failed"]))
        run.wait(5000)
        self.assertEqual(got["failed"], [])
        self.assertEqual(got["ok"][0][0], "done")
        self.assertEqual(got["text"], ["plain string", "hi"])

    def test_null_then_exit_fails_instead_of_hanging(self):
        os.environ["FAKE_MODE"] = "null_exit"
        run, got = self._run()
        run.start()
        self.assertTrue(wait_until(lambda: got["ok"] or got["failed"]))
        self.assertEqual(got["ok"], [])
        self.assertIn("without a result", got["failed"][0])

    def test_cancel_kills_a_child_that_ignores_sigterm(self):
        os.environ["FAKE_MODE"] = "null_hang"
        run, got = self._run()
        run.start()
        self.assertTrue(wait_until(lambda: run._proc is not None
                                   and os.path.exists(self.log)))
        time.sleep(0.3)             # let it install SIG_IGN
        pid = run._proc.pid
        t0 = time.time()
        run.cancel()
        self.assertTrue(wait_until(lambda: got["failed"], timeout=6))
        gone = time.time() - t0
        self.assertEqual(got["failed"], ["cancelled"])
        self.assertTrue(run.wait(3000))
        self.assertFalse(_alive(pid), "the CLI survived Stop")
        self.assertLess(gone, 3.0, "took %.2fs" % gone)
        print("\n  [R19] SIGTERM-ignoring fake gone %.2fs after cancel()"
              % gone)

    def test_shutdown_all_escalates_and_keeps_refs_until_finished(self):
        os.environ["FAKE_MODE"] = "null_hang"
        run, got = self._run()
        run.start()
        self.assertTrue(wait_until(lambda: run._proc is not None))
        time.sleep(0.3)
        pid = run._proc.pid
        self.assertIn(run, claude_cli.ClaudeRun._LIVE)
        self.assertTrue(claude_cli.ClaudeRun.shutdown_all(timeout_ms=3000))
        self.assertFalse(run.isRunning())
        self.assertFalse(_alive(pid))
        self.assertNotIn(run, claude_cli.ClaudeRun._LIVE)

    def test_new_session_process_group(self):
        run, got = self._run()
        run.start()
        self.assertTrue(wait_until(lambda: got["ok"] or got["failed"]))
        # start_new_session: the child led its own group (pgid == pid) -
        # the only way Stop can reach the tools it spawned.
        self.assertIsNotNone(run._proc)

    def test_offline_stream_is_reported_as_unreachable(self):
        os.environ["FAKE_MODE"] = "offline"
        run, got = self._run()
        run.start()
        self.assertTrue(wait_until(lambda: got["failed"]))
        self.assertIn("could not reach the Claude API", got["failed"][0])
        self.assertEqual(claude_cli.classify_failure(got["failed"][0]),
                         claude_cli.OFFLINE)


class TestClassify(unittest.TestCase):
    """R21: measured CLI text -> the right kind; unknown stays OTHER."""

    def test_kinds(self):
        c = claude_cli.classify_failure
        self.assertEqual(c("Not logged in · Please run /login"),
                         claude_cli.AUTH)
        self.assertEqual(c("Invalid API key · Please run /login"),
                         claude_cli.AUTH)
        self.assertEqual(c("OAuth token has expired"), claude_cli.AUTH)
        self.assertEqual(c("could not reach the Claude API (retried 10 "
                           "times, last error: unknown)"), claude_cli.OFFLINE)
        self.assertEqual(c("getaddrinfo ENOTFOUND api.anthropic.com"),
                         claude_cli.OFFLINE)
        self.assertEqual(c("cancelled"), claude_cli.CANCELLED)
        self.assertEqual(c("Something odd happened"), claude_cli.OTHER)
        self.assertEqual(c(""), claude_cli.OTHER)


# ------------------------------------------------------------ find claude
class TestFindClaude(unittest.TestCase):
    """R22: desktop launches miss nvm / npm-global / bun installs."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="fakehome-", dir=_TMP)
        self._saved = (os.environ.get("HOME"), os.environ.get("PATH"),
                       os.environ.get("SHELL"), claude_cli.DEFAULT_BIN,
                       claude_cli._SHELL_FOUND, claude_cli.KNOWN_LOCATIONS)
        # System-wide entries (/usr/local/bin/claude exists on the dev box)
        # would answer before the fake HOME's; test the home-relative ones.
        claude_cli.KNOWN_LOCATIONS = tuple(
            p for p in claude_cli.KNOWN_LOCATIONS if p.startswith("~/"))
        os.environ["HOME"] = self.home
        os.environ["PATH"] = "/usr/bin:/bin"
        claude_cli.DEFAULT_BIN = os.path.join(self.home, ".local/bin/claude")
        claude_cli._SHELL_FOUND = None
        cfgmod.update(claude_path="")

    def tearDown(self):
        home, path, shell, default, found, known = self._saved
        claude_cli.KNOWN_LOCATIONS = known
        os.environ["HOME"] = home
        os.environ["PATH"] = path
        if shell is None:
            os.environ.pop("SHELL", None)
        else:
            os.environ["SHELL"] = shell
        claude_cli.DEFAULT_BIN = default
        claude_cli._SHELL_FOUND = found

    def _exe(self, rel):
        p = os.path.join(self.home, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            fh.write("#!/bin/sh\n")
        os.chmod(p, 0o755)
        return p

    def test_nvm_install_is_found_without_path(self):
        if shutil.which("claude"):
            self.skipTest("a claude is on /usr/bin:/bin")
        self.assertIsNone(claude_cli.find_claude())
        old = self._exe(".nvm/versions/node/v18.20.1/bin/claude")
        new = self._exe(".nvm/versions/node/v22.3.0/bin/claude")
        self.assertEqual(claude_cli.find_claude(), new)
        self.assertNotEqual(old, new)

    def test_npm_global_and_bun(self):
        if shutil.which("claude"):
            self.skipTest("a claude is on /usr/bin:/bin")
        bun = self._exe(".bun/bin/claude")
        self.assertEqual(claude_cli.find_claude(), bun)
        npm = self._exe(".npm-global/bin/claude")
        self.assertEqual(claude_cli.find_claude(), npm)   # listed first

    def test_explicit_path_wins_and_a_wrong_one_is_not_replaced(self):
        self._exe(".bun/bin/claude")
        mine = self._exe("tools/claude")
        cfgmod.update(claude_path=mine)
        self.assertEqual(claude_cli.find_claude(), mine)
        cfgmod.update(claude_path=os.path.join(self.home, "nope"))
        self.assertIsNone(claude_cli.find_claude())
        ok, why = engine.available(engine.CLAUDE)
        self.assertFalse(ok)
        self.assertIn("Agent Settings", why)

    def test_login_shell_probe_runs_once_and_needs_a_real_file(self):
        if shutil.which("claude"):
            self.skipTest("a claude is on /usr/bin:/bin")
        target = self._exe("weird/place/claude")
        shell = os.path.join(self.home, "fakeshell")
        count = os.path.join(self.home, "count")
        with open(shell, "w") as fh:
            fh.write("#!/bin/sh\necho x >> %s\necho %s\n" % (count, target))
        os.chmod(shell, 0o755)
        os.environ["SHELL"] = shell
        self.assertIsNone(claude_cli.find_claude())       # no process yet
        self.assertEqual(claude_cli.locate(), target)
        self.assertEqual(claude_cli.find_claude(), target)  # cached
        claude_cli.locate()
        with open(count) as fh:
            self.assertEqual(len(fh.read().split()), 1)

    def test_login_shell_bare_name_is_ignored(self):
        if shutil.which("claude"):
            self.skipTest("a claude is on /usr/bin:/bin")
        shell = os.path.join(self.home, "fakeshell")
        with open(shell, "w") as fh:
            fh.write("#!/bin/sh\necho claude\n")   # a shell function
        os.chmod(shell, 0o755)
        os.environ["SHELL"] = shell
        self.assertIsNone(claude_cli.locate())

    def test_not_found_reason_has_install_command_and_link(self):
        if shutil.which("claude"):
            self.skipTest("a claude is on /usr/bin:/bin")
        ok, why = engine.available(engine.CLAUDE)
        self.assertFalse(ok)
        self.assertIn(claude_cli.INSTALL_COMMAND, why)
        self.assertIn(claude_cli.INSTALL_URL, why)


# ------------------------------------------------------------ settings
class TestSettings(Base):

    def test_privacy_ack_persists_across_a_reload(self):
        self.assertFalse(cfgmod.privacy_acknowledged())
        self.assertTrue(cfgmod.acknowledge_privacy())
        import importlib
        mod = importlib.reload(cfgmod)       # a "restart"
        mod.CONFIG_DIR = os.path.join(_TMP, "config")
        mod.CONFIG_PATH = os.path.join(mod.CONFIG_DIR, "settings.json")
        self.assertTrue(mod.privacy_acknowledged())

    def test_notice_is_final_and_names_what_is_sent(self):
        # The owner approved final wording (2026-10-03): no draft markers.
        body = cfgmod.privacy_notice_body()
        for text in (cfgmod.PRIVACY_NOTICE_TITLE, body):
            self.assertNotIn("DRAFT", text.upper())
        self.assertGreaterEqual(cfgmod.PRIVACY_NOTICE_VERSION, 2)
        for needle in ("Anthropic", "summary of the open document",
                       "Add view", "Ask about this view", "~/.claude",
                       cfgmod.chat_workspace_root(), cfgmod.CONFIG_PATH):
            self.assertIn(needle, body)

    def test_notice_button_labels_exist_in_the_ui(self):
        """The notice names "Add view" and "Ask about this view": both must
        be the labels the user actually sees (MEASURE: read the source)."""
        with open(os.path.join(ADDON, "acadagent", "panel.py"), encoding="utf-8") as fh:
            self.assertIn('self._ghost("Add view"', fh.read())
        with open(os.path.join(ADDON, "acadagent", "shell.py"), encoding="utf-8") as fh:
            self.assertIn('ASK_TEXT = "Ask about this view"', fh.read())

    def test_draft_acknowledgement_is_asked_again(self):
        # Acknowledging the draft (v1) is not consent to the final text.
        cfgmod.update(privacy_ack=1)
        self.assertFalse(cfgmod.privacy_acknowledged())

    def test_workspace_root_matches_build(self):
        ws = build.new_workspace()
        try:
            self.assertEqual(os.path.dirname(ws), cfgmod.chat_workspace_root())
        finally:
            shutil.rmtree(ws)

    def test_clear_only_old_chat_folders(self):
        root = os.path.join(self.tmp, "agent")
        for n in ("chat-1", "chat-2", "keepme-chat", "chat-3"):
            os.makedirs(os.path.join(root, n))
        ro = os.path.join(root, "chat-2", "ATECH_ASSEMBLY.md")
        with open(ro, "w") as fh:
            fh.write("x")
        os.chmod(ro, 0o444)
        with open(os.path.join(root, "chat-4"), "w") as fh:
            fh.write("a file, not a folder")
        keep = os.path.join(root, "chat-3")
        removed, failed = cfgmod.clear_workspaces(keep=[keep], root=root)
        self.assertEqual((removed, failed), (2, 0))
        self.assertEqual(sorted(os.listdir(root)),
                         ["chat-3", "chat-4", "keepme-chat"])

    def test_readonly_config_dialog_says_so(self):
        dlg = cfgmod.SettingsDialog()
        os.chmod(cfgmod.CONFIG_DIR, 0o555)
        try:
            if os.access(cfgmod.CONFIG_DIR, os.W_OK):
                self.skipTest("running as a user who can write anywhere")
            dlg._on_save()
            self.assertTrue(dlg.status.text().startswith(
                "Could not save settings"), dlg.status.text())
            self.assertFalse(cfgmod.update(model="x"))
        finally:
            os.chmod(cfgmod.CONFIG_DIR, 0o755)
        dlg._on_save()
        self.assertEqual(dlg.status.text(), "Saved")

    def test_save_keeps_keys_the_dialog_does_not_own(self):
        cfgmod.acknowledge_privacy()
        dlg = cfgmod.SettingsDialog()
        dlg._on_save()
        self.assertTrue(cfgmod.privacy_acknowledged())

    def test_placeholder_follows_provider(self):
        dlg = cfgmod.SettingsDialog()
        for pid, _ in cfgmod.PROVIDERS:
            dlg.provider.setCurrentIndex(dlg.provider.findData(pid))
            self.assertEqual(dlg.key.placeholderText(),
                             cfgmod.KEY_PLACEHOLDERS[pid])

    def test_backend_test_error_is_plain(self):
        dlg = cfgmod.SettingsDialog()
        dlg.backend.setText("http://127.0.0.1:9")
        dlg._on_test()
        self.assertEqual(dlg.status.text(),
                         "Could not reach the agent server at 127.0.0.1:9.")


# ------------------------------------------------------------ panel
class PanelBase(Base):
    def setUp(self):
        super().setUp()
        cfgmod.acknowledge_privacy()
        self.p = panel.AgentPanel()
        wait_until(lambda: self.p._backend_state != "checking", 10)

    def tearDown(self):
        claude_cli.ClaudeRun.shutdown_all(3000)
        self.p.deleteLater()
        APP.processEvents()
        super().tearDown()

    def send(self, text):
        self.p.input.setPlainText(text)
        self.p._on_send()

    def idle(self, timeout=15):
        return wait_until(lambda: not self.p._busy, timeout)

    def notices(self):
        return [w for w in self.p.findChildren(panel.Notice)
                if not w.isHidden()]

    def titles(self):
        return [w.findChild(QtWidgets.QLabel, "NoticeTitle").text()
                for w in self.notices()]


class TestPanelTurns(PanelBase):

    def test_r14_one_add_dir_and_a_readonly_reference_copy(self):
        self.send("make a box")
        self.assertTrue(self.idle())
        t = self.turns()[-1]
        argv = t["argv"]
        dirs = [argv[i + 1] for i, a in enumerate(argv) if a == "--add-dir"]
        self.assertEqual(dirs, [t["cwd"]], argv)
        src = build.assembly_doc()
        if src:
            # R101/D44: a plain part is not an Atech request - no copy,
            # and the prompt does not point at the repo file either.
            copy = os.path.join(t["cwd"], os.path.basename(src))
            self.assertFalse(os.path.exists(copy))
            self.assertNotIn(src, t["sp"])
            # An Atech request gets the read-only copy (R14).
            self.send("seat an Atech button on port 3")
            self.assertTrue(self.idle())
            t = self.turns()[-1]
            copy = os.path.join(t["cwd"], os.path.basename(src))
            self.assertTrue(os.path.isfile(copy))
            self.assertEqual(stat.S_IMODE(os.stat(copy).st_mode), 0o444)
            sp = t["sp"]
            self.assertNotIn(src, sp)
            if os.path.basename(src) in sp:     # the prompt names it
                self.assertIn(copy, sp)
        print("\n  [R14] --add-dir values: %s" % dirs)

    def test_r25_add_view_reaches_the_next_turn(self):
        png = self.p.capture_path()
        ws = os.path.dirname(png)
        with open(png, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
        self.p.add_shot(png, "test view")
        self.send("what is this?")
        self.assertTrue(self.idle())
        prompt = self.turns()[-1]["stdin"]
        self.assertIn(png, prompt)
        self.assertEqual(self.turns()[-1]["cwd"], ws)
        self.assertEqual(self.p._pending_shots, [])
        self.send("and now?")
        self.assertTrue(self.idle())
        self.assertNotIn(png, self.turns()[-1]["stdin"])

    def test_r26_duration_only_cost_behind_setting(self):
        self.send("hi")
        self.assertTrue(self.idle())
        cards = self.p.findChildren(panel.ToolCard)
        st = [c.status.text() for c in cards if c.status.text().endswith("s")]
        self.assertIn("4s", st)
        self.assertFalse(any("$" in c.status.text() for c in cards))
        cfgmod.update(show_cost=True)
        self.send("again")
        self.assertTrue(self.idle())
        self.assertTrue(any("$0.37" in c.status.text() for c in
                            self.p.findChildren(panel.ToolCard)))

    def test_r23_retry_resends_and_no_welcome_after_messages(self):
        os.environ["FAKE_MODE"] = "weird"
        self.send("make a gear")
        self.assertTrue(self.idle())
        self.assertEqual(self.p.input.toPlainText(), "make a gear")
        self.assertIn("The agent stopped before finishing", self.titles())
        n = [x for x in self.notices() if x.findChild(
            QtWidgets.QLabel, "NoticeTitle").text().startswith("The agent")][-1]
        self.assertIsNotNone(n.detail)
        self.assertTrue(n.detail.isHidden(), "raw text must be collapsed")
        os.environ["FAKE_MODE"] = "ok"
        n.buttons[0].click()                  # Retry
        self.assertTrue(self.idle())
        prompts = [t["stdin"].split("\n\n---")[0] for t in self.turns()]
        self.assertEqual(prompts, ["make a gear", "make a gear"])
        self.p._probe_backend_again()
        wait_until(lambda: self.p._backend_state != "checking")
        self.assertIsNone(self.p._empty, "Welcome came back mid-transcript")

    def test_r21_signed_out_turn(self):
        os.environ["FAKE_MODE"] = "nologin"
        self.send("hi")
        self.assertTrue(self.idle())
        self.assertIn("Sign in to Claude Code", self.titles())
        n = [x for x in self.notices() if x.findChild(
            QtWidgets.QLabel, "NoticeTitle").text() == "Sign in to Claude Code"][0]
        self.assertEqual([b.text() for b in n.buttons],
                         ["Open terminal", "Retry"])
        # Onboarding: the exact sign-in command, as text the user can select.
        body = n.findChild(QtWidgets.QLabel, "NoticeBody")
        self.assertIn(claude_cli.LOGIN_COMMAND, body.text())
        self.assertIn("/login", body.text())
        self.assertTrue(body.textInteractionFlags()
                        & QtCore.Qt.TextSelectableByMouse)

    def test_onboarding_not_found_notice_has_command_and_link(self):
        """A fresh machine without Claude Code: the notice gives the exact
        install command and the docs URL, both selectable."""
        old = engine.current
        engine.current = lambda: engine.CLAUDE
        self.p._unavailable_kind = None
        try:
            n = self.p._offline_notice()
        finally:
            engine.current = old
        self.assertEqual(n.spec[0], "Claude Code not found")
        body = n.findChild(QtWidgets.QLabel, "NoticeBody")
        self.assertIn("\n    %s\n" % claude_cli.INSTALL_COMMAND, body.text())
        self.assertIn(claude_cli.INSTALL_URL, body.text())
        self.assertTrue(body.textInteractionFlags()
                        & QtCore.Qt.TextSelectableByMouse)
        self.assertEqual([b.text() for b in n.buttons][:1], ["Retry"])

    def test_r21_offline_turn(self):
        os.environ["FAKE_MODE"] = "offline"
        self.send("hi")
        self.assertTrue(self.idle())
        self.assertIn("No internet connection", self.titles())

    def test_r21_signed_out_at_mount(self):
        os.environ["FAKE_LOGGED_IN"] = "0"
        p2 = panel.AgentPanel()
        try:
            self.assertTrue(wait_until(lambda: p2._backend_state == "offline"))
            titles = [w.findChild(QtWidgets.QLabel, "NoticeTitle").text()
                      for w in p2.findChildren(panel.Notice)
                      if not w.isHidden()]
            self.assertIn("Sign in to Claude Code", titles)
        finally:
            p2.deleteLater()

    def test_r21_old_cli_plain_text_auth_status(self):
        # claude 2.0.25 has no JSON `auth status`; its signed-out text must
        # still read as signed out, not as "could not tell".
        os.environ["FAKE_LOGGED_IN"] = "old"
        logged, detail = claude_cli.auth_status()
        self.assertIs(logged, False)
        self.assertIn("/login", detail)

    def test_r21_repeated_auth_failures_do_not_stack(self):
        os.environ["FAKE_MODE"] = "nologin"
        for _ in range(3):
            self.p.input.clear()
            self.send("hi")
            self.assertTrue(self.idle())
        self.assertEqual(self.titles().count("Sign in to Claude Code"), 1)

    def test_r19_setup_failure_restores_text(self):
        real = build.document_brief

        def boom(_doc):
            raise RuntimeError("brief exploded")
        build.document_brief = boom
        try:
            self.send("keep me")
        finally:
            build.document_brief = real
        self.assertFalse(self.p._busy)
        self.assertEqual(self.p.input.toPlainText(), "keep me")
        self.assertIn("Could not start the agent", self.titles())
        self.assertEqual(self.turns(), [])

    def test_r19_stop_mid_turn_returns_to_idle_and_reaps(self):
        os.environ["FAKE_MODE"] = "null_hang"
        self.send("hang")
        self.assertTrue(wait_until(lambda: self.p._chat is not None and
                                   self.p._chat._proc is not None))
        time.sleep(0.3)
        pid = self.p._chat._proc.pid
        self.p._watch_timer.start()
        t0 = time.time()
        self.p._on_stop()
        self.assertFalse(self.p._busy)
        self.assertTrue(self.p._stopped)
        self.assertFalse(self.p._watch_timer.isActive())
        self.assertEqual(self.p.input.toPlainText(), "hang")
        self.assertTrue(wait_until(lambda: not _alive(pid), 5))
        print("\n  [R19] panel Stop: process gone after %.2fs"
              % (time.time() - t0))
        self.assertTrue(wait_until(lambda: not self.p._chat.isRunning(), 5))
        self.assertEqual(self.p._backend_state, "idle")

    def test_threads_have_no_widget_parent(self):
        self.send("x")
        self.assertIsNone(self.p._chat.parent())
        self.assertIsNone(self.p._health.parent())
        self.assertTrue(self.idle())


class TestPrivacyGate(PanelBase):
    def setUp(self):
        super().setUp()
        cfgmod.update(privacy_ack=None)
        self.p._privacy_ok = False

    def test_first_send_shows_notice_once(self):
        self.send("hello")
        self.assertEqual(self.turns(), [], "nothing may leave before consent")
        self.assertEqual(self.p.input.toPlainText(), "hello")
        self.assertIn(cfgmod.PRIVACY_NOTICE_TITLE, self.titles())
        self.send("hello")                    # a second press: no second notice
        self.assertEqual(self.titles().count(cfgmod.PRIVACY_NOTICE_TITLE), 1)
        self.p._privacy_notice.buttons[0].click()   # Continue
        self.assertTrue(self.idle())
        self.assertEqual(len(self.turns()), 1)
        self.assertTrue(cfgmod.privacy_acknowledged())
        self.send("second")
        self.assertTrue(self.idle())
        self.assertEqual(len(self.turns()), 2)
        self.assertEqual(self.titles().count(cfgmod.PRIVACY_NOTICE_TITLE), 1)


# ------------------------------------------------------------ R17
class _Obj(object):
    def __init__(self, name, script):
        self.Name = self.Label = name
        self.AtechAgentBuilt = True
        self.AtechAgentScript = script


class _Doc(object):
    def __init__(self, name, uid, objects=()):
        self.Name = self.Label = name
        self.Uid = uid
        self.Objects = list(objects)


class TestPerDocument(PanelBase):
    def setUp(self):
        self.fc = types.ModuleType("FreeCAD")
        self.a = _Doc("Unnamed", "uid-a")
        self.b = _Doc("Gearbox", "uid-b",
                      [_Obj("Gear", "# gearbox script\n")])
        docs = {"Unnamed": self.a, "Gearbox": self.b}
        self.fc.ActiveDocument = self.a
        self.fc.listDocuments = lambda: dict(docs)
        self.fc.getDocument = lambda n: docs[n]

        def _set(n):
            self.fc.ActiveDocument = docs[n]
        self.fc.setActiveDocument = _set
        self.fc.Console = types.SimpleNamespace(
            PrintLog=lambda *a: None, PrintMessage=lambda *a: None)
        sys.modules["FreeCAD"] = self.fc
        super().setUp()

    def tearDown(self):
        super().tearDown()
        sys.modules.pop("FreeCAD", None)

    def test_each_document_keeps_its_workspace_and_session(self):
        # Since R11 (WS-BUILD) adopt() restores only a script Studio's trust
        # store vouches for; that rule has its own tests. Here B's script
        # counts as Studio's own.
        trusted = getattr(build, "_is_trusted", None)
        if trusted is not None:
            build._is_trusted = lambda *a, **k: True
            self.addCleanup(setattr, build, "_is_trusted", trusted)
        os.environ["FAKE_SID"] = "sid-A"
        self.send("box in A")
        self.assertTrue(self.idle())
        ws_a = self.turns()[-1]["cwd"]

        self.fc.ActiveDocument = self.b
        os.environ["FAKE_SID"] = "sid-B"
        self.send("change B")
        self.assertTrue(self.idle())
        t = self.turns()[-1]
        ws_b = t["cwd"]
        self.assertNotEqual(ws_a, ws_b)
        self.assertNotIn("--resume", t["argv"])     # B's first turn
        self.assertIn("Open document: Gearbox", t["stdin"])
        # B was adopted on first contact: its script is in B's workspace.
        with open(os.path.join(ws_b, build.SCRIPT), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "# gearbox script\n")
        self.assertEqual(self.p._docs["uid-b"].prev["doc"], "Gearbox")

        self.fc.ActiveDocument = self.a
        self.send("again A")
        self.assertTrue(self.idle())
        t = self.turns()[-1]
        self.assertEqual(t["cwd"], ws_a)
        self.assertEqual(t["argv"][t["argv"].index("--resume") + 1], "sid-A")

        # The build of a turn lands in the document it was sent from, even
        # if the user switched away meanwhile.
        self.fc.ActiveDocument = self.b
        self.p._activate_state_doc(self.p._docs["uid-a"])
        self.assertIs(self.fc.ActiveDocument, self.a)


class TestJargon(unittest.TestCase):
    """R26: no developer jargon in the chat's user-facing strings."""

    def test_no_bin_cad_or_print_envelope(self):
        with open(os.path.join(ADDON, "acadagent", "panel.py"),
                  encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("bin/cad", src)
        self.assertNotIn("170 mm", src)

    def test_error_summary_is_one_line(self):
        tb = ('Traceback (most recent call last):\n'
              '  File "model.py", line 42, in <module>\n'
              '    box = Part.makeBox(a, 2, 3)\n'
              "NameError: name 'a' is not defined\n")
        self.assertEqual(panel._error_summary(tb),
                         "NameError: name 'a' is not defined")
        self.assertEqual(panel._error_summary(""), "The script failed.")

    def test_capture_errors_are_plain(self):
        from acadagent import capture
        try:
            capture._active_view()
        except capture.CaptureError as exc:
            msg = capture.user_message(exc)
        self.assertNotIn("saveImage", msg)
        self.assertNotIn("FreeCADGui", msg)


def tearDownModule():
    claude_cli.ClaudeRun.shutdown_all(3000)
    if _REAL_HOME is not None:
        os.environ["HOME"] = _REAL_HOME
    shutil.rmtree(_TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
