"""R870: Codex and Cursor as chat engines, beside Claude Code.

WHAT IS PINNED
    check_broker   ./check of an agent in its own sandbox: the client asks,
                   Atelier runs the REAL check text it keeps in memory, the
                   answer comes back; a link planted where the answer goes
                   is replaced, never followed; Stop ends a check in flight
                   and the client gives up.
    codex_cli      the argv (isolation flags, only features this Codex
                   lists, read-only for a view question, every option
                   before `resume`), and the MEASURED event stream (0.162.1)
                   turned into ClaudeRun's signals; signed out = AUTH,
                   retries without a result = OFFLINE.
    cursor_cli     the documented stream (partial deltas, tool calls,
                   result), the permissions file, a prompt that never
                   starts with "-", --resume=<id>, --mode ask, no --force.
    engine         Claude Code, Codex and Cursor are offered; cli() names
                   the module; available() says how to install each.
    settings       each engine's data notice is acknowledged on its own.
    panel          a session id is resumed only by the engine that made it.

RUN (the interpreter that ships: it has PySide6)
    QT_QPA_PLATFORM=offscreen <app>/Contents/Resources/bin/python \\
        -m unittest addon/AcadAgent/tests/test_agent_engines_r870.py -v
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from PySide6 import QtCore  # noqa: E402

from acadagent import (agent_cli, check_broker, claude_cli,  # noqa: E402
                       codex_cli, cursor_cli, engine, settings)

_APP = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])


def _write_exe(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(path, 0o755)
    return path


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="r870-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ws = os.path.join(self.tmp, "ws")
        os.makedirs(self.ws)


def _drive(run, timeout_ms=30000):
    """Run a ClaudeRun-like thread to the end; the signals it sent."""
    ev = []
    for name in ("started_session", "text", "tool", "delta", "tool_failed",
                 "tool_refused", "activity", "message_open", "finished_ok",
                 "failed"):
        getattr(run, name).connect(lambda *a, n=name: ev.append((n,) + a))
    loop = QtCore.QEventLoop()
    run.finished.connect(loop.quit)
    run.start()
    QtCore.QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    run.wait(5000)
    QtCore.QCoreApplication.processEvents()
    return ev


def _only(ev, name):
    return [e[1:] for e in ev if e[0] == name]


# ------------------------------------------------------------- the broker
class TestCheckBroker(_Tmp):

    def start(self, text="echo hello; echo 'CHECK PASS'\n"):
        check_broker.register(self.ws, text)
        b = check_broker.Broker(self.ws, dict(os.environ))
        self.assertTrue(b.start())
        self.addCleanup(b.stop)
        return b

    def client(self, wait=30):
        path = os.path.join(self.ws, "check")
        _write_exe(path, check_broker.client_script(self.ws, wait))
        return subprocess.run([path], capture_output=True, text=True,
                              cwd=self.ws, timeout=60)

    def test_client_gets_the_real_checks_output_and_status(self):
        self.start("echo measured; echo 'CHECK FAIL: too thin'; exit 1\n")
        r = self.client()
        self.assertEqual(r.returncode, 1)
        self.assertIn("measured", r.stdout)
        self.assertTrue(r.stdout.strip().endswith("CHECK FAIL: too thin"))
        left = os.listdir(os.path.join(self.ws, check_broker.DIR))
        self.assertEqual(left, [check_broker.ALIVE])

    def test_pass_exits_zero(self):
        self.start()
        r = self.client()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("CHECK PASS", r.stdout)

    def test_runs_the_registered_text_never_the_file(self):
        """The agent may rewrite ./check; the broker runs what Atelier
        registered."""
        self.start("echo REGISTERED\n")
        path = os.path.join(self.ws, "check")
        r = self.client()
        self.assertIn("REGISTERED", r.stdout)
        os.chmod(path, 0o755)
        evil = os.path.join(self.tmp, "evil-ran")
        with open(os.path.join(self.ws, "evil.sh"), "w") as fh:
            fh.write("touch %s\n" % evil)
        # A request needs no client at all: the broker still runs only
        # the registered text.
        d = os.path.join(self.ws, check_broker.DIR)
        open(os.path.join(d, "req-1-1"), "w").close()
        for _ in range(100):
            if os.path.exists(os.path.join(d, "done-1-1")):
                break
            time.sleep(0.05)
        with open(os.path.join(d, "out-1-1"), "rb") as fh:
            self.assertIn(b"REGISTERED", fh.read())
        self.assertFalse(os.path.exists(evil))

    def test_planted_link_is_replaced_not_followed(self):
        self.start("echo 'CHECK PASS'\n")
        d = os.path.join(self.ws, check_broker.DIR)
        victim = os.path.join(self.tmp, "victim.txt")
        with open(victim, "w") as fh:
            fh.write("precious\n")
        os.symlink(victim, os.path.join(d, "out-7-7"))
        os.symlink(victim, os.path.join(d, "done-7-7"))
        open(os.path.join(d, "req-7-7"), "w").close()
        for _ in range(100):
            st = os.lstat(os.path.join(d, "done-7-7"))
            if not stat.S_ISLNK(st.st_mode):
                break
            time.sleep(0.05)
        with open(victim) as fh:
            self.assertEqual(fh.read(), "precious\n")
        self.assertFalse(os.path.islink(os.path.join(d, "out-7-7")))

    def test_check_folder_that_is_a_link_is_refused(self):
        os.symlink(self.tmp, os.path.join(self.ws, check_broker.DIR))
        check_broker.register(self.ws, "echo x\n")
        b = check_broker.Broker(self.ws)
        self.assertFalse(b.start())
        self.assertFalse(os.path.exists(os.path.join(self.tmp,
                                                     check_broker.ALIVE)))

    def test_no_broker_fails_at_once(self):
        r = self.client()
        self.assertEqual(r.returncode, 1)
        self.assertIn("not taking checks", r.stdout)

    def test_unregistered_folder_says_so(self):
        b = check_broker.Broker(self.ws)
        with check_broker._LOCK:
            check_broker._SCRIPTS.pop(os.path.realpath(self.ws), None)
        self.assertTrue(b.start())
        self.addCleanup(b.stop)
        r = self.client()
        self.assertEqual(r.returncode, 1)
        self.assertIn("no check for this chat", r.stdout)

    def test_stop_kills_the_check_and_the_client_gives_up(self):
        b = self.start("sleep 30; echo late\n")
        path = os.path.join(self.ws, "check")
        _write_exe(path, check_broker.client_script(self.ws, 60))
        proc = subprocess.Popen([path], stdout=subprocess.PIPE, text=True,
                                cwd=self.ws)
        time.sleep(1.5)
        t0 = time.monotonic()
        b.stop()
        out, _ = proc.communicate(timeout=10)
        self.assertLess(time.monotonic() - t0, 8)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("stopped the check", out)

    def test_client_wait_covers_the_real_scripts_stops(self):
        # wrapper_script: lock wait max(120, t + 60), hard stop t + 30.
        self.assertGreater(check_broker.client_wait(180),
                           max(120, 180 + 60) + 180 + 30)


# -------------------------------------------------------------- fake CLIs
FAKE_CODEX = r'''#!/bin/sh
case "$1 $2" in
  "exec --help") cat "$FAKE_HELP"; exit 0 ;;
  "features list") cat "$FAKE_FEATURES"; exit 0 ;;
  "login status") echo "$FAKE_LOGIN"; [ "$FAKE_LOGIN" = "Not logged in" ] && exit 1; exit 0 ;;
esac
printf '%s\n' "$@" > "$FAKE_ARGV"
cat > "$FAKE_STDIN"
cat "$FAKE_OUT"
exit "${FAKE_RC:-0}"
'''

CODEX_HELP = """Usage: codex exec [OPTIONS] [PROMPT]
  -c, --config <key=value>
      --enable <FEATURE>
      --disable <FEATURE>
  -m, --model <MODEL>
  -s, --sandbox <SANDBOX_MODE>
  -C, --cd <DIR>
      --skip-git-repo-check
      --ignore-user-config
      --ignore-rules
      --json
"""
CODEX_FEATURES = """apps                stable   true
hooks               stable   true
multi_agent         stable   true
shell_tool          stable   true
"""

#: MEASURED codex-cli 0.162.1 lines (paths shortened).
CODEX_OK = [
    {"type": "thread.started", "thread_id": "th-1"},
    {"type": "item.completed", "item": {"id": "item_0", "type": "error",
     "message": "Model metadata for `x` not found."}},
    {"type": "turn.started"},
    {"type": "item.started", "item": {"id": "item_1", "type":
     "command_execution", "command": "/bin/zsh -lc ./check",
     "aggregated_output": "", "exit_code": None, "status": "in_progress"}},
    {"type": "item.completed", "item": {"id": "item_1", "type":
     "command_execution", "command": "/bin/zsh -lc ./check",
     "aggregated_output": "x\nCHECK FAIL: too thin\n", "exit_code": 1,
     "status": "completed"}},
    {"type": "item.started", "item": {"id": "item_2", "type": "file_change",
     "changes": [{"path": "/w/model.py", "kind": "update"}],
     "status": "in_progress"}},
    {"type": "item.completed", "item": {"id": "item_2", "type":
     "file_change", "changes": [{"path": "/w/model.py", "kind": "update"}],
     "status": "completed"}},
    {"type": "item.completed", "item": {"id": "item_3", "type":
     "agent_message", "text": "Built a box."}},
    {"type": "turn.completed", "usage": {"input_tokens": 300,
     "cached_input_tokens": 30, "output_tokens": 60}},
]
CODEX_401 = [
    {"type": "thread.started", "thread_id": "th-2"},
    {"type": "turn.started"},
    {"type": "error", "message": "Reconnecting... 2/5 (unexpected status "
     "401 Unauthorized: Missing bearer or basic authentication in header)"},
    {"type": "error", "message": "unexpected status 401 Unauthorized: "
     "Missing bearer or basic authentication in header"},
    {"type": "turn.failed", "error": {"message": "unexpected status 401 "
     "Unauthorized: Missing bearer or basic authentication in header"}},
]


class _FakeCodex(_Tmp):
    def setUp(self):
        super().setUp()
        self.exe = _write_exe(os.path.join(self.tmp, "codex"), FAKE_CODEX)
        files = {"FAKE_HELP": CODEX_HELP, "FAKE_FEATURES": CODEX_FEATURES}
        self.env_keys = {}
        for k, text in files.items():
            p = os.path.join(self.tmp, k.lower())
            with open(p, "w") as fh:
                fh.write(text)
            self.setenv(k, p)
        self.argv_path = os.path.join(self.tmp, "argv")
        self.stdin_path = os.path.join(self.tmp, "stdin")
        self.setenv("FAKE_ARGV", self.argv_path)
        self.setenv("FAKE_STDIN", self.stdin_path)
        self.setenv("FAKE_LOGIN", "Logged in using ChatGPT")
        orig = codex_cli.find
        codex_cli.find = lambda explicit=None: self.exe
        self.addCleanup(setattr, codex_cli, "find", orig)
        agent_cli._HELP.clear()
        codex_cli._FEATURES.clear()
        self.broker_text = "echo 'CHECK PASS'\n"

    def setenv(self, k, v):
        old = os.environ.get(k)
        os.environ[k] = v
        self.addCleanup(lambda: os.environ.__setitem__(k, old) if old
                        is not None else os.environ.pop(k, None))

    def out(self, records, rc=0):
        p = os.path.join(self.tmp, "out.jsonl")
        with open(p, "w") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")
        self.setenv("FAKE_OUT", p)
        self.setenv("FAKE_RC", str(rc))

    def run_turn(self, mode="acceptEdits", sid=None, sp="SYSTEM PROMPT",
                 agent=None):
        run = codex_cli.CodexRun(
            "make a box", cwd=self.ws, session_id=sid, permission_mode=mode,
            system_prompt=sp, agent=agent or {"model": "gpt-5.5",
                                               "effort": "high"})
        ev = _drive(run)
        with open(self.argv_path) as fh:
            argv = fh.read().splitlines()
        return run, ev, argv


class TestCodexRun(_FakeCodex):

    def test_measured_stream_becomes_the_panels_signals(self):
        self.out(CODEX_OK)
        run, ev, _ = self.run_turn()
        self.assertEqual(_only(ev, "started_session"), [("th-1",)])
        self.assertEqual(_only(ev, "tool"), [("Shell", "./check"),
                                             ("Edit", "model.py")])
        self.assertEqual(_only(ev, "tool_failed"),
                         [("Shell", "./check",
                           "exit code 1: CHECK FAIL: too thin")])
        self.assertEqual(_only(ev, "text"), [("Built a box.",)])
        done = _only(ev, "finished_ok")
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0][0], "Built a box.")
        self.assertEqual(done[0][1]["session_id"], "th-1")
        self.assertIn("duration_ms", done[0][1])
        self.assertNotIn("total_cost_usd", done[0][1])
        self.assertEqual(_only(ev, "failed"), [])
        self.assertEqual(run.session_id, "th-1")

    def test_argv_isolates_and_writes_only_in_the_folder(self):
        self.out(CODEX_OK)
        _run, _ev, argv = self.run_turn()
        self.assertEqual(argv[:2], ["exec", "--json"])
        for flag in ("--skip-git-repo-check", "--ignore-user-config",
                     "--ignore-rules"):
            self.assertIn(flag, argv)
        self.assertIn('approval_policy="never"', argv)
        self.assertIn('web_search="disabled"', argv)
        self.assertIn("skills.include_instructions=false", argv)
        disabled = [argv[i + 1] for i, a in enumerate(argv)
                    if a == "--disable"]
        # Only features this Codex lists: an unknown one fails the run.
        self.assertEqual(disabled, ["apps", "hooks", "multi_agent"])
        i = argv.index("--sandbox")
        self.assertEqual(argv[i + 1], "workspace-write")
        self.assertEqual(argv[argv.index("--cd") + 1], self.ws)
        self.assertEqual(argv[argv.index("--model") + 1], "gpt-5.5")
        self.assertIn('model_reasoning_effort="high"', argv)
        self.assertEqual(argv[-1], "-")
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)

    def test_system_prompt_is_a_toml_string_and_the_prompt_on_stdin(self):
        import tomllib
        sp = 'Line "one"\nback\\slash ünïcode\ttab'
        self.out(CODEX_OK)
        _run, _ev, argv = self.run_turn(sp=sp)
        arg = next(a for a in argv if a.startswith("developer_instructions="))
        self.assertEqual(tomllib.loads(arg)["developer_instructions"], sp)
        with open(self.stdin_path) as fh:
            self.assertEqual(fh.read(), "make a box")

    def test_huge_system_prompt_goes_on_stdin(self):
        sp = "x" * (agent_cli.ARG_LIMIT + 10)
        self.out(CODEX_OK)
        _run, _ev, argv = self.run_turn(sp=sp)
        self.assertFalse(any(a.startswith("developer_instructions=")
                             for a in argv))
        with open(self.stdin_path) as fh:
            text = fh.read()
        self.assertTrue(text.startswith("<atelier_instructions>\n" + sp))
        self.assertTrue(text.endswith("make a box"))

    def test_view_question_is_read_only_and_resume_comes_last(self):
        self.out(CODEX_OK)
        _run, _ev, argv = self.run_turn(mode="plan", sid="th-0")
        self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
        self.assertEqual(argv[-3:], ["resume", "th-0", "-"])
        # every option before `resume`
        self.assertTrue(all(not a.startswith("-") or a == "-"
                            for a in argv[argv.index("resume"):]))

    def test_default_permission_mode_is_read_only(self):
        self.out(CODEX_OK)
        _run, _ev, argv = self.run_turn(mode=None)
        self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")

    def test_signed_out_is_auth(self):
        self.out(CODEX_401, rc=1)
        _run, ev, _ = self.run_turn()
        failed = _only(ev, "failed")
        self.assertEqual(len(failed), 1)
        self.assertEqual(claude_cli.classify_failure(failed[0][0]),
                         claude_cli.AUTH)
        self.assertEqual(_only(ev, "finished_ok"), [])

    def test_retries_without_a_result_are_offline(self):
        self.out([{"type": "thread.started", "thread_id": "t"},
                  {"type": "error", "message": "Reconnecting... 1/5 "
                   "(error sending request for url (https://api.openai.com"
                   "/v1/responses))"}], rc=1)
        _run, ev, _ = self.run_turn()
        failed = _only(ev, "failed")
        self.assertEqual(claude_cli.classify_failure(failed[0][0]),
                         claude_cli.OFFLINE)
        self.assertIn(("retry", "1"), _only(ev, "activity"))

    def test_exit_without_a_result_is_not_success(self):
        self.out([{"type": "thread.started", "thread_id": "t"}], rc=0)
        _run, ev, _ = self.run_turn()
        self.assertEqual(_only(ev, "finished_ok"), [])
        self.assertIn("without a result", _only(ev, "failed")[0][0])

    def test_declined_command_is_refused(self):
        self.out([{"type": "thread.started", "thread_id": "t"},
                  {"type": "item.completed", "item": {
                      "id": "i", "type": "command_execution",
                      "command": "rm -rf x", "status": "declined",
                      "exit_code": None}},
                  {"type": "turn.completed", "usage": {}}])
        _run, ev, _ = self.run_turn()
        self.assertEqual(_only(ev, "tool_refused")[0][0], "Shell")

    def test_write_turn_runs_the_broker_and_ends_it(self):
        check_broker.register(self.ws, self.broker_text)
        self.out(CODEX_OK)
        self.run_turn()
        d = os.path.join(self.ws, check_broker.DIR)
        self.assertTrue(os.path.isdir(d))
        self.assertFalse(os.path.exists(os.path.join(d, check_broker.ALIVE)))

    def test_old_codex_without_flags_says_what_was_dropped(self):
        with open(os.environ["FAKE_HELP"], "w") as fh:
            fh.write("  --json\n  --sandbox\n  --cd\n")
        agent_cli._HELP.clear()
        self.out(CODEX_OK)
        run, _ev, argv = self.run_turn()
        self.assertIn("--ignore-user-config", run.dropped)
        self.assertNotIn("--disable", argv)

    def test_auth_status(self):
        self.assertEqual(codex_cli.auth_status()[0], True)
        self.setenv("FAKE_LOGIN", "Not logged in")
        for k in ("CODEX_API_KEY", "OPENAI_API_KEY"):
            self.setenv(k, "")
            os.environ.pop(k)
        self.assertEqual(codex_cli.auth_status()[0], False)
        self.setenv("OPENAI_API_KEY", "sk-test")
        self.assertIsNone(codex_cli.auth_status()[0])

    def test_command_of(self):
        self.assertEqual(codex_cli.command_of("/bin/zsh -lc ./check"),
                         "./check")
        self.assertEqual(codex_cli.command_of(
            "/bin/bash -lc 'ls -la; ./check'"), "ls -la; ./check")
        self.assertEqual(codex_cli.command_of("python3 x.py"), "python3 x.py")
        self.assertEqual(codex_cli.command_of("'unbalanced"), "'unbalanced")


# ------------------------------------------------------------------ Cursor
FAKE_CURSOR = r'''#!/bin/sh
if [ "$1" = "--help" ]; then cat "$FAKE_HELP"; exit 0; fi
if [ "$1" = "status" ]; then echo "$FAKE_STATUS"; exit 0; fi
printf '%s\n' "$@" > "$FAKE_ARGV"
cp .cursor/cli.json "$FAKE_PERMS" 2>/dev/null
cat "$FAKE_OUT"
exit "${FAKE_RC:-0}"
'''
CURSOR_HELP = """  -p, --print
  --output-format <format>
  --stream-partial-output
  --resume [chatId]
  --model <model>
  --mode <mode>
  -f, --force
  --sandbox <mode>
  --trust
  --workspace <path>
"""
#: The documented shapes (docs/cli/reference/output-format).
CURSOR_OK = [
    {"type": "system", "subtype": "init", "apiKeySource": "login",
     "cwd": "/w", "session_id": "chat-1", "model": "Auto",
     "permissionMode": "default"},
    {"type": "user", "message": {"role": "user", "content": [
        {"type": "text", "text": "make a box"}]}, "session_id": "chat-1"},
    {"type": "assistant", "timestamp_ms": 1, "message": {
        "role": "assistant", "content": [{"type": "text", "text": "Let "}]},
     "session_id": "chat-1"},
    {"type": "assistant", "timestamp_ms": 2, "message": {
        "role": "assistant", "content": [{"type": "text", "text": "me"}]},
     "session_id": "chat-1"},
    {"type": "assistant", "timestamp_ms": 3, "model_call_id": "m1",
     "message": {"role": "assistant", "content": [
         {"type": "text", "text": "Let me"}]}, "session_id": "chat-1"},
    {"type": "tool_call", "subtype": "started", "call_id": "c1",
     "tool_call": {"writeToolCall": {"args": {
         "path": "model.py", "fileText": "x", "toolCallId": "c1"}}},
     "session_id": "chat-1"},
    {"type": "tool_call", "subtype": "completed", "call_id": "c1",
     "tool_call": {"writeToolCall": {"args": {"path": "model.py"},
                   "result": {"success": {"path": "/w/model.py",
                                          "linesCreated": 1,
                                          "fileSize": 1}}}},
     "session_id": "chat-1"},
    {"type": "tool_call", "subtype": "started", "call_id": "c2",
     "tool_call": {"shellToolCall": {"args": {"command": "./check"}}},
     "session_id": "chat-1"},
    {"type": "tool_call", "subtype": "completed", "call_id": "c2",
     "tool_call": {"shellToolCall": {"args": {"command": "./check"},
                   "result": {"success": {"exitCode": 1, "stdout":
                                          "CHECK FAIL: thin\n"}}}},
     "session_id": "chat-1"},
    {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "Built a box."}]}, "session_id": "chat-1"},
    {"type": "result", "subtype": "success", "duration_ms": 1234,
     "duration_api_ms": 1234, "is_error": False, "result": "Built a box.",
     "session_id": "chat-1", "request_id": "r"},
]


class _FakeCursor(_FakeCodex):
    def setUp(self):
        super().setUp()
        self.exe = _write_exe(os.path.join(self.tmp, "cursor-agent"),
                              FAKE_CURSOR)
        p = os.path.join(self.tmp, "cursor_help")
        with open(p, "w") as fh:
            fh.write(CURSOR_HELP)
        self.setenv("FAKE_HELP", p)
        self.perms_path = os.path.join(self.tmp, "perms.json")
        self.setenv("FAKE_PERMS", self.perms_path)
        orig = cursor_cli.find
        cursor_cli.find = lambda explicit=None: self.exe
        self.addCleanup(setattr, cursor_cli, "find", orig)

    def run_turn(self, mode="acceptEdits", sid=None, sp="SYSTEM PROMPT",
                 prompt="make a box", agent=None):
        run = cursor_cli.CursorRun(prompt, cwd=self.ws, session_id=sid,
                                   permission_mode=mode, system_prompt=sp,
                                   agent=agent or {})
        ev = _drive(run)
        with open(self.argv_path) as fh:
            argv = fh.read().split("\n")
        return run, ev, argv


class TestCursorRun(_FakeCursor):

    def test_documented_stream_becomes_the_panels_signals(self):
        self.out(CURSOR_OK)
        run, ev, _ = self.run_turn()
        self.assertEqual(_only(ev, "started_session"), [("chat-1",)])
        self.assertEqual(_only(ev, "delta"), [("Let ",), ("Let me",)])
        self.assertEqual(_only(ev, "text"), [("Let me",), ("Built a box.",)])
        self.assertEqual(_only(ev, "tool"), [("Write", "model.py"),
                                             ("Shell", "./check")])
        self.assertEqual(_only(ev, "tool_failed"),
                         [("Shell", "./check",
                           "exit code 1: CHECK FAIL: thin")])
        done = _only(ev, "finished_ok")
        self.assertEqual(done[0][0], "Built a box.")
        self.assertEqual(done[0][1]["duration_ms"], 1234)

    def test_argv_sandboxed_without_force(self):
        self.out(CURSOR_OK)
        _run, _ev, argv = self.run_turn(sid="chat-0",
                                        agent={"model": "gpt-5"})
        self.assertEqual(argv[:4], ["--print", "--output-format",
                                    "stream-json", "--stream-partial-output"])
        self.assertIn("--trust", argv)
        self.assertEqual(argv[argv.index("--workspace") + 1], self.ws)
        self.assertEqual(argv[argv.index("--sandbox") + 1], "enabled")
        self.assertIn("--resume=chat-0", argv)
        self.assertEqual(argv[argv.index("--model") + 1], "gpt-5")
        for bad in ("--force", "-f", "--yolo", "--approve-mcps"):
            self.assertNotIn(bad, argv)
        self.assertNotIn("--mode", argv)

    def test_permissions_file_per_turn(self):
        self.out(CURSOR_OK)
        self.run_turn()
        with open(self.perms_path) as fh:
            perms = json.load(fh)["permissions"]
        self.assertEqual(perms["allow"], ["Read(**)", "Write(**)"])
        self.assertIn("Write(.cursor/**)", perms["deny"])
        self.run_turn(mode="plan")
        with open(self.perms_path) as fh:
            perms = json.load(fh)["permissions"]
        self.assertEqual(perms["allow"], ["Read(**)"])

    def test_view_question_is_ask_mode(self):
        self.out(CURSOR_OK)
        _run, _ev, argv = self.run_turn(mode="plan")
        self.assertEqual(argv[argv.index("--mode") + 1], "ask")

    def test_prompt_carries_the_instructions_and_never_starts_with_dash(self):
        self.out(CURSOR_OK)
        run, _ev, _argv = self.run_turn(sp=None, prompt="-5 mm thinner")
        self.assertFalse(run.argv[-1].startswith("-"))
        self.assertIn("-5 mm thinner", run.argv[-1])
        run, _ev, _argv = self.run_turn(sp="RULES")
        self.assertTrue(run.argv[-1].startswith("<atelier_instructions>\n"
                                                "RULES"))

    def test_huge_prompt_goes_in_a_private_file_removed_after(self):
        self.out(CURSOR_OK)
        sp = "y" * (agent_cli.ARG_LIMIT + 1)
        seen = {}
        orig = cursor_cli.CursorRun._spawn

        def spy(run, argv, text, env=None):
            path = os.path.join(self.ws, cursor_cli.PROMPT_FILE)
            seen["mode"] = stat.S_IMODE(os.stat(path).st_mode)
            with open(path) as fh:
                seen["text"] = fh.read()
            return orig(run, argv, text, env)
        cursor_cli.CursorRun._spawn = spy
        self.addCleanup(setattr, cursor_cli.CursorRun, "_spawn", orig)
        run, _ev, _argv = self.run_turn(sp=sp)
        self.assertEqual(seen["mode"], 0o600)
        self.assertIn(sp, seen["text"])
        self.assertIn(cursor_cli.PROMPT_FILE, run.argv[-1])
        self.assertFalse(os.path.exists(
            os.path.join(self.ws, cursor_cli.PROMPT_FILE)))

    def test_stream_ending_early_fails_with_stderr(self):
        self.out(CURSOR_OK[:2], rc=1)
        _run, ev, _ = self.run_turn()
        self.assertIn("without a result", _only(ev, "failed")[0][0])

    def test_result_error_is_a_failure(self):
        self.out([CURSOR_OK[0], {"type": "result", "subtype": "error",
                                 "is_error": True,
                                 "result": "not authenticated"}], rc=1)
        _run, ev, _ = self.run_turn()
        msg = _only(ev, "failed")[0][0]
        self.assertEqual(claude_cli.classify_failure(msg), claude_cli.AUTH)

    def test_without_mode_flag_a_view_question_is_refused(self):
        with open(os.environ["FAKE_HELP"], "w") as fh:
            fh.write("  --output-format\n  --print\n")
        agent_cli._HELP.clear()
        self.out(CURSOR_OK)
        run = cursor_cli.CursorRun("q", cwd=self.ws, permission_mode="plan")
        ev = _drive(run)
        self.assertIn("--mode", _only(ev, "failed")[0][0])

    def test_auth_status_reads_only_clear_words(self):
        self.setenv("FAKE_STATUS", "Logged in as a@b.c")
        self.assertTrue(cursor_cli.auth_status()[0])
        self.setenv("FAKE_STATUS", "Not logged in")
        self.setenv("CURSOR_API_KEY", "")
        os.environ.pop("CURSOR_API_KEY")
        self.assertFalse(cursor_cli.auth_status()[0])
        self.setenv("FAKE_STATUS", "Endpoint: api2.cursor.sh")
        self.assertIsNone(cursor_cli.auth_status()[0])


class TestCursorShapes(unittest.TestCase):

    def test_tool_of(self):
        self.assertEqual(cursor_cli.tool_of(
            {"readToolCall": {"args": {"path": "a.py"}}})[:2],
            ("Read", {"path": "a.py"}))
        self.assertEqual(cursor_cli.tool_of(
            {"function": {"name": "grep", "arguments": '{"pattern": "x"}'}}
        )[:2], ("grep", {"pattern": "x"}))
        self.assertEqual(cursor_cli.tool_of(
            {"newThingToolCall": {}})[0], "NewThing")
        self.assertEqual(cursor_cli.tool_of(None)[0], "tool")

    def test_judge_result(self):
        j = cursor_cli.judge_result
        self.assertEqual(j({"success": {}})[0], "ok")
        self.assertEqual(j(None)[0], "ok")
        self.assertEqual(j({"rejected": {"reason": "denied"}}),
                         ("refused", "denied"))
        self.assertEqual(j({"error": {"message": "boom"}}),
                         ("failed", "boom"))
        self.assertEqual(j({"success": {"exitCode": 2, "stderr": "bad\n"}}),
                         ("failed", "exit code 2: bad"))


# ------------------------------------------------- engine / settings / panel
class _Cfg(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="r870-cfg-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self._dir, self._path = settings.CONFIG_DIR, settings.CONFIG_PATH
        settings.CONFIG_DIR = self.tmp
        settings.CONFIG_PATH = os.path.join(self.tmp, "settings.json")
        self.addCleanup(setattr, settings, "CONFIG_DIR", self._dir)
        self.addCleanup(setattr, settings, "CONFIG_PATH", self._path)
        self._dev = os.environ.pop(engine.DEV_ENV, None)
        self.addCleanup(lambda: self._dev is not None and
                        os.environ.__setitem__(engine.DEV_ENV, self._dev))


class TestEngines(_Cfg):

    def test_cli_engines_are_offered_and_selectable(self):
        self.assertEqual([e[0] for e in engine.offered()],
                         ["claude", "codex", "cursor"])
        for name, mod in (("claude", claude_cli), ("codex", codex_cli),
                          ("cursor", cursor_cli)):
            engine.select(name)
            self.assertEqual(engine.current(), name)
            self.assertTrue(engine.is_cli())
            self.assertIs(engine.cli(), mod)
            for attr in ("PRODUCT", "VENDOR", "PATH_KEY", "MODEL_KEY",
                         "INSTALL_COMMAND", "INSTALL_URL", "LOGIN_COMMAND",
                         "LOGIN_ARGS", "HAS_EFFORT", "HAS_BUDGET", "find",
                         "locate", "configured_path", "available",
                         "version", "auth_status", "agent_kwargs", "warm",
                         "Run"):
                self.assertTrue(hasattr(mod, attr), (name, attr))
        self.assertFalse(engine.is_cli(engine.OPENCODE))
        with self.assertRaises(ValueError):
            engine.cli(engine.API)

    def test_claude_run_follows_a_replaced_class(self):
        orig = claude_cli.ClaudeRun

        class Fake(orig):
            pass
        claude_cli.ClaudeRun = Fake
        try:
            self.assertIs(claude_cli.Run, Fake)
        finally:
            claude_cli.ClaudeRun = orig
        self.assertIs(claude_cli.Run, orig)

    def test_missing_cli_says_how_to_install(self):
        for name, mod in (("codex", codex_cli), ("cursor", cursor_cli)):
            orig = mod.find
            mod.find = lambda explicit=None: None
            try:
                ok, why = engine.available(name)
            finally:
                mod.find = orig
            self.assertFalse(ok)
            self.assertIn(mod.INSTALL_COMMAND, why)
            self.assertIn(mod.LOGIN_COMMAND, why)

    def test_wrong_explicit_path_is_reported(self):
        settings.save({"codex_path": "/nonexistent/codex"})
        self.assertIsNone(codex_cli.find())
        ok, why = engine.available("codex")
        self.assertFalse(ok)
        self.assertIn("/nonexistent/codex", why)

    def test_models_are_per_engine(self):
        settings.save({"agent_model": "opus", "codex_model": "gpt-5.5",
                       "agent_effort": "low"})
        self.assertEqual(codex_cli.agent_settings()["model"], "gpt-5.5")
        self.assertEqual(codex_cli.agent_settings()["effort"], "low")
        self.assertIsNone(codex_cli.agent_settings()["budget"])
        self.assertIsNone(cursor_cli.agent_settings()["model"])


class TestPrivacyPerEngine(_Cfg):

    def test_each_engine_is_acknowledged_on_its_own(self):
        engine.select("claude")
        self.assertTrue(settings.acknowledge_privacy())
        self.assertTrue(settings.privacy_acknowledged())
        engine.select("codex")
        self.assertFalse(settings.privacy_acknowledged())
        body = settings.privacy_notice_body()
        self.assertIn("OpenAI", body)
        self.assertIn("~/.codex", body)
        self.assertNotIn("Anthropic", body)
        self.assertIn("does not stop the agent reading", body)
        self.assertTrue(settings.acknowledge_privacy())
        self.assertTrue(settings.privacy_acknowledged())
        engine.select("cursor")
        self.assertFalse(settings.privacy_acknowledged())
        self.assertIn("MCP servers", settings.privacy_notice_body())
        engine.select("claude")
        self.assertTrue(settings.privacy_acknowledged())
        self.assertIn("Anthropic", settings.privacy_notice_body())

    def test_claude_notice_and_key_unchanged(self):
        self.assertTrue(settings.privacy_acknowledged(
            {"privacy_ack": settings.PRIVACY_NOTICE_VERSION}))
        self.assertFalse(settings.privacy_acknowledged(
            {"engine": "codex",
             "privacy_ack": settings.PRIVACY_NOTICE_VERSION}))


class TestSessionBelongsToItsEngine(unittest.TestCase):

    def test_sid_engine(self):
        from acadagent import panel
        self.assertEqual(panel._sid_engine({"sid": "x"}), "claude")
        self.assertEqual(panel._sid_engine({"sid_engine": "codex"}), "codex")
        self.assertEqual(panel._sid_engine({"sid_engine": "bogus"}),
                         "claude")
        self.assertEqual(panel._sid_engine(None), "claude")


if __name__ == "__main__":
    unittest.main()
