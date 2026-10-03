"""WS-CHAT round 11, headless against the REAL AgentPanel and ClaudeRun:
R215 (the CLI dies with Studio: PR_SET_PDEATHSIG), R216 (a tool call the
CLI refused for want of a permission is drawn as refused; the agent kit is
copied into the chat folder, still one --add-dir), R217 (a turn that keeps
calling tools but never builds says so after BUILD_QUIET_S; a stale
"preview: in progress" does not sit on the build card), R205 (a failed row
is drawn in the theme's failure colour, light and dark, and after a
transcript restore), R210 (a draft typed right after New chat stays with
the document it was typed in).

Each item has a sabotage case: the same scenario with the fix taken out
must fail the item's assertion.

R217 runs on a fake monotonic clock (panel.time is swapped for a module
whose monotonic() the test sets), so "10 minutes" takes no time.

RUN (the interpreter that ships):
    QT_QPA_PLATFORM=offscreen dist/build/squashfs-root/usr/bin/python \\
        -m unittest addon/AcadAgent/tests/test_ws_chat_round11.py -v
"""
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import test_chat_robustness as tcr  # noqa: E402  (sets HOME, Qt, settings)
import test_ws_chat_panel as twp  # noqa: E402
import test_ws_chat_round9 as tr9  # noqa: E402  (adds the "script" fake)

from PySide6 import QtGui, QtWidgets  # noqa: E402

from acadagent import build, claude_cli, panel, style  # noqa: E402

wait_until = tcr.wait_until
_alive = tcr._alive
_Obj, _Doc = twp._Obj, twp._Doc
_RecRun = tr9._RecRun
_visible = tr9._visible
ADDON = tcr.ADDON

INIT = {"type": "system", "subtype": "init", "session_id": "sid-r11"}
RESULT = {"type": "result", "subtype": "success", "result": "done",
          "is_error": False, "duration_ms": 4000}


def _script(records):
    os.environ["FAKE_MODE"] = "script"
    os.environ["FAKE_SCRIPT"] = json.dumps(records)


# ================================================================== R215
#: A CLI stand-in: records its pid, then sleeps. It does NOT ignore
#: SIGTERM (the real claude exits on it; PR_SET_PDEATHSIG sends SIGTERM).
SLEEPER = r'''#!%(py)s
import os, sys, time
with open(os.environ["SLEEPER_PID"], "w") as fh:
    fh.write(str(os.getpid()))
sys.stdin.read()
time.sleep(float(os.environ.get("SLEEPER_FOR", "60")))
'''

#: "Studio" for R215: the real ClaudeRun in a child interpreter, started
#: on its QThread exactly as the panel starts it; then it idles until the
#: test SIGKILLs it.
STUDIO = r'''
import os, sys, time
sys.path.insert(0, %(addon)r)
from PySide6 import QtCore
app = QtCore.QCoreApplication([])
from acadagent import claude_cli
claude_cli.find_claude = lambda: %(exe)r
claude_cli.ClaudeRun.TIE_TO_PARENT = %(tie)r
run = claude_cli.ClaudeRun("hi", cwd=%(cwd)r)
run.start()
end = time.time() + 10
while run._proc is None and time.time() < end:
    time.sleep(0.01)
print("CLI", run._proc.pid if run._proc else -1, flush=True)
time.sleep(120)
'''


class TestR215DiesWithStudio(tcr.Base):

    def sleeper(self, secs=60):
        exe = os.path.join(self.tmp, "sleeper")
        with open(exe, "w", encoding="utf-8") as fh:
            fh.write(SLEEPER % {"py": sys.executable})
        os.chmod(exe, 0o755)
        self.pidfile = os.path.join(self.tmp, "sleeper.pid")
        os.environ["SLEEPER_PID"] = self.pidfile
        os.environ["SLEEPER_FOR"] = str(secs)
        self.addCleanup(os.environ.pop, "SLEEPER_PID", None)
        self.addCleanup(os.environ.pop, "SLEEPER_FOR", None)
        return exe

    def _read_pid(self):
        try:
            with open(self.pidfile) as fh:
                return fh.read()
        except OSError:
            return ""

    def cli_pid(self):
        self.assertTrue(wait_until(self._read_pid, 10))
        return int(self._read_pid())

    def kill_studio(self, tie):
        """Start "Studio" (a child interpreter running ClaudeRun), SIGKILL
        it once the CLI runs; (cli pid, seconds until the CLI was gone or
        None if it outlived the 2 s window)."""
        exe = self.sleeper()
        code = STUDIO % {"addon": ADDON, "exe": exe, "tie": tie,
                         "cwd": self.tmp}
        studio = subprocess.Popen([sys.executable, "-c", code],
                                  stdout=subprocess.PIPE, text=True)
        self.addCleanup(studio.stdout.close)
        self.addCleanup(lambda: studio.poll() is None and studio.kill())
        line = studio.stdout.readline().split()
        self.assertEqual(line[:1], ["CLI"], line)
        pid = self.cli_pid()
        self.assertEqual(int(line[1]), pid)
        self.addCleanup(self._kill_if_alive, pid)
        self.assertTrue(_alive(pid))
        self.assertEqual(os.getpgid(pid), pid, "not its own process group")
        t0 = time.monotonic()
        os.kill(studio.pid, signal.SIGKILL)
        studio.wait(5)
        while time.monotonic() - t0 < 2.0:
            if not _alive(pid):
                return pid, time.monotonic() - t0
            time.sleep(0.01)
        return pid, None

    @staticmethod
    def _kill_if_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def test_r215_cli_gone_within_2s_of_studio_sigkill(self):
        pid, gone = self.kill_studio(tie=True)
        self.assertIsNotNone(gone, "the CLI outlived Studio by > 2 s")
        print("\n  [R215] Studio SIGKILLed: CLI %d gone after %.3f s"
              % (pid, gone))

    def test_r215_sabotage_untied_cli_outlives_studio(self):
        """The pre-fix launch: start_new_session alone - nothing reaches
        the CLI when Studio dies; it is re-parented and keeps running."""
        pid, gone = self.kill_studio(tie=False)
        self.assertIsNone(gone)
        self.assertTrue(_alive(pid))
        print("\n  [R215 sabotage] TIE_TO_PARENT=False: CLI %d still "
              "alive 2 s after Studio was SIGKILLed" % pid)

    def test_r215_stop_still_kills_the_group(self):
        """Stop/Cancel unchanged: SIGTERM to the CLI's own process group."""
        self.assertTrue(claude_cli.ClaudeRun.TIE_TO_PARENT)
        exe = self.sleeper()
        self.patch_find(exe)
        run = claude_cli.ClaudeRun("hi", cwd=self.tmp)
        failed = []
        run.failed.connect(failed.append)
        run.start()
        pid = self.cli_pid()
        self.addCleanup(self._kill_if_alive, pid)
        self.assertEqual(os.getpgid(pid), pid)
        t0 = time.monotonic()
        run.cancel()
        self.assertTrue(wait_until(lambda: failed, 6))
        self.assertEqual(failed, ["cancelled"])
        self.assertTrue(run.wait(3000))
        self.assertFalse(_alive(pid))
        print("\n  [R215] Stop with the tie on: CLI gone, run ended "
              "%.2f s after cancel()" % (time.monotonic() - t0))

    def patch_find(self, exe):
        saved = claude_cli.find_claude
        claude_cli.find_claude = lambda: exe
        self.addCleanup(setattr, claude_cli, "find_claude", saved)

    def test_r215_the_forking_thread_outlives_the_cli(self):
        """PR_SET_PDEATHSIG fires when the THREAD that forked exits. The
        fork is on the run's QThread: sampled every 10 ms, it is running
        at every instant the CLI is alive (the CLI exits on its own after
        1 s, a normal turn)."""
        exe = self.sleeper(secs=1.0)
        self.patch_find(exe)
        run = claude_cli.ClaudeRun("hi", cwd=self.tmp)
        run.start()
        pid = self.cli_pid()
        self.addCleanup(self._kill_if_alive, pid)
        samples = bad = 0
        end = time.monotonic() + 6
        while time.monotonic() < end:
            alive = _alive(pid)
            if not alive:
                break
            samples += 1
            if not run.isRunning():
                bad += 1
            time.sleep(0.01)
        self.assertFalse(_alive(pid))
        self.assertGreater(samples, 50)
        self.assertEqual(bad, 0, "the QThread ended while the CLI ran")
        self.assertTrue(run.wait(5000))
        print("\n  [R215] %d samples with the CLI alive: QThread running "
              "in all of them" % samples)

    def test_r215_measure_the_thread_semantics(self):
        """Why the thread matters, measured: a child tied from a SHORT-LIVED
        thread dies when that thread ends, though the process lives on.
        (Sabotage of the design's assumption: were the fork made on a
        thread that leaves before the CLI, the CLI would be killed.)"""
        exe = self.sleeper()
        tie = claude_cli._pdeathsig_fn()
        self.assertIsNotNone(tie)
        box = {}

        def fork():
            box["p"] = subprocess.Popen([exe], stdin=subprocess.PIPE,
                                        start_new_session=True,
                                        preexec_fn=tie)
            box["p"].stdin.close()
        th = threading.Thread(target=fork)
        th.start()
        th.join()
        p = box["p"]
        self.addCleanup(lambda: p.poll() is None and p.kill())
        self.assertTrue(wait_until(lambda: p.poll() is not None, 3),
                        "the child outlived the thread that forked it")
        self.assertEqual(p.returncode, -signal.SIGTERM)
        print("\n  [R215] forked from a thread that then ended: child "
              "died of signal %d" % -p.returncode)


# ================================================================== R216
READ = {"type": "assistant", "message": {"content": [
    {"type": "tool_use", "id": "toolu_r", "name": "Read",
     "input": {"file_path": "/opt/atech/agent_kit/atech_geom.py"}}]}}
REFUSAL_TEXT = ("Claude requested permissions to read from "
                "/opt/atech/agent_kit/atech_geom.py, but you haven't "
                "granted it yet.")
REFUSED = {"type": "user", "message": {"content": [
    {"type": "tool_result", "tool_use_id": "toolu_r", "is_error": True,
     "content": REFUSAL_TEXT}]},
    "tool_result_meta": [{"id": "toolu_r",
                          "non_execution_kind": "user-rejected"}]}
REASON = ("no permission to read from atech_geom.py (outside this chat's "
          "folder)")


class TestR216Stream(tcr.Base):

    def run_script(self, records):
        _script(records)
        self.addCleanup(os.environ.pop, "FAKE_SCRIPT", None)
        run = claude_cli.ClaudeRun("hi", cwd=self.tmp)
        seen = {"failed": [], "refused": [], "act": []}
        done = []
        run.tool_failed.connect(lambda *a: seen["failed"].append(a))
        run.tool_refused.connect(lambda *a: seen["refused"].append(a))
        run.activity.connect(lambda k, d: seen["act"].append((k, d)))
        run.finished_ok.connect(lambda *a: done.append(a))
        run.start()
        self.assertTrue(wait_until(lambda: done, 10))
        wait_until(lambda: not run.isRunning(), 5)
        return seen

    def test_r216_refusal_is_reported_as_refused(self):
        seen = self.run_script([INIT, READ, REFUSED, RESULT])
        arg = seen["refused"][0][1] if seen["refused"] else None
        self.assertEqual(seen["refused"], [("Read", arg, REASON)])
        self.assertEqual(seen["failed"], [])
        self.assertIn(("failed", ("Read %s" % arg).strip()), seen["act"])
        print("\n  [R216] tool_refused %s" % seen["refused"])

    def test_r216_meta_alone_marks_a_refusal(self):
        rec = json.loads(json.dumps(REFUSED))
        rec["message"]["content"][0]["content"] = "denied"
        seen = self.run_script([INIT, READ, rec, RESULT])
        self.assertEqual(len(seen["refused"]), 1)
        self.assertEqual(seen["failed"], [])

    def test_r216_text_alone_marks_a_refusal(self):
        rec = json.loads(json.dumps(REFUSED))
        del rec["tool_result_meta"]
        seen = self.run_script([INIT, READ, rec, RESULT])
        self.assertEqual(len(seen["refused"]), 1)
        self.assertEqual(seen["failed"], [])

    def test_r216_an_ordinary_error_stays_failed(self):
        rec = json.loads(json.dumps(REFUSED))
        del rec["tool_result_meta"]
        rec["message"]["content"][0]["content"] = "File does not exist."
        seen = self.run_script([INIT, READ, rec, RESULT])
        self.assertEqual(seen["refused"], [])
        self.assertEqual(len(seen["failed"]), 1)

    def test_r216_sabotage_without_refusal_detection(self):
        """The pre-fix reader: every is_error result is a plain failure."""
        saved = claude_cli.is_refusal
        claude_cli.is_refusal = lambda c: False
        self.addCleanup(setattr, claude_cli, "is_refusal", saved)
        rec = json.loads(json.dumps(REFUSED))
        del rec["tool_result_meta"]
        seen = self.run_script([INIT, READ, rec, RESULT])
        self.assertEqual(seen["refused"], [])
        self.assertEqual(len(seen["failed"]), 1)

    def test_r216_short_refusal(self):
        self.assertEqual(claude_cli.short_refusal(REFUSAL_TEXT), REASON)
        self.assertEqual(claude_cli.short_refusal(
            [{"type": "text", "text": REFUSAL_TEXT}]), REASON)
        # No path named: nothing says the chat's folder was the reason.
        self.assertEqual(claude_cli.short_refusal("denied"), "no permission")
        self.assertEqual(claude_cli.short_refusal(object()), "no permission")
        # A command off the allowlist is refused, but not for a folder.
        bash = ("Claude requested permissions to use Bash, but you "
                "haven't granted it yet.")
        self.assertTrue(claude_cli.is_refusal(bash))
        self.assertEqual(claude_cli.short_refusal(bash),
                         "no permission to use Bash")
        self.assertTrue(claude_cli.is_refusal(REFUSAL_TEXT))
        self.assertFalse(claude_cli.is_refusal("Exit code 1"))
        self.assertFalse(claude_cli.is_refusal(None))


class TestR216Panel(tcr.PanelBase):
    """The real panel and ClaudeRun on the scripted fake."""

    def setUp(self):
        super().setUp()
        self.addCleanup(os.environ.pop, "FAKE_SCRIPT", None)

    def refused_row(self):
        _script([INIT, READ, REFUSED, {"sleep": 30}, RESULT])
        self.send("make a box")
        card = self.p._card
        self.assertIsNotNone(card)
        self.assertTrue(wait_until(
            lambda: "Read" in card.body.text(), 10))
        wait_until(lambda: " · refused: " in card.body.text(), 3)
        rows = card.body.text().split("\n")
        self.p._on_stop()
        self.assertTrue(self.idle(10))
        return rows

    def test_r216_refused_row_on_the_card(self):
        rows = self.refused_row()
        last = rows[-1]
        self.assertTrue(last.startswith(panel.FAILED_ROW + "Read"), rows)
        self.assertTrue(last.endswith(" · refused: " + REASON), rows)
        print("\n  [R216] row %r" % last)

    def test_r216_sabotage_without_the_refused_hook(self):
        self.p._on_claude_tool_refused = lambda *a: None
        rows = self.refused_row()
        self.assertNotIn(" · refused: ", rows[-1])
        self.assertTrue(rows[-1].startswith("Read"), rows)

    def test_r216_one_add_dir_and_the_kit_copies_listed(self):
        _script([INIT, RESULT])
        self.send("make a box")
        self.assertTrue(self.idle())
        t = self.turns()[-1]
        argv = t["argv"]
        dirs = [argv[i + 1] for i, a in enumerate(argv) if a == "--add-dir"]
        self.assertEqual(dirs, [t["cwd"]], argv)
        for name in ("atech_geom.py", "check.py"):
            copy = os.path.join(t["cwd"], "reference", "kit", name)
            self.assertTrue(os.path.isfile(copy), copy)
            self.assertEqual(stat.S_IMODE(os.stat(copy).st_mode), 0o444)
            with open(copy, "rb") as a, \
                    open(os.path.join(build.KIT_DIR, name), "rb") as b:
                self.assertEqual(a.read(), b.read())
            self.assertIn(copy, t["sp"])
        self.assertIn("you cannot read that folder", t["sp"])
        print("\n  [R216] --add-dir %s; kit copies in the prompt: %s"
              % (dirs, [ln.strip() for ln in t["sp"].split("\n")
                        if "/reference/kit/" in ln]))

    def test_r216_sabotage_without_the_kit_copy(self):
        self.p.KIT_REFERENCE = ()
        _script([INIT, RESULT])
        self.send("make a box")
        self.assertTrue(self.idle())
        t = self.turns()[-1]
        self.assertNotIn("reference/kit/atech_geom.py", t["sp"])
        self.assertFalse(os.path.exists(os.path.join(
            t["cwd"], "reference", "kit", "atech_geom.py")))


# ================================================================== R217
class _Clock(types.ModuleType):
    """panel.time with a monotonic() the test sets."""

    def __init__(self):
        super().__init__("time")
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def __getattr__(self, name):
        return getattr(time, name)


class _Pending(object):
    """A build.PendingBuild stand-in: in flight until `land()`."""

    def __init__(self):
        self.res = None

    def poll(self):
        return self.res

    def land(self):
        self.res = build.Result(True, build.SCRIPT)

    def cancel(self):
        pass


class TestR217NoBuild(twp.Round3):

    def setUp(self):
        super().setUp()
        self.viewport()
        _RecRun.runs = []
        self.patch(claude_cli, "ClaudeRun", _RecRun)
        self.fc.add(_Doc("Part", "uid-q", [_Obj("Box")]))
        self.clock = _Clock()
        self.patch(panel, "time", self.clock)
        self.patch(self.p, "_settle", lambda *a: None)
        self.patch(self.p, "_start", self._start_build)
        self.pendings = []
        self.send("make a hinge")
        self.assertTrue(self.p._busy)
        self.card = self.p._card
        self.p._tick.stop()             # the test drives the ticks
        self.t0 = self.clock.now

    def _start_build(self, state, files, preview):
        pb = _Pending()
        self.pendings.append(pb)
        return pb

    def tearDown(self):
        try:
            self.p._on_stop()
        except Exception:                              # noqa: BLE001
            pass
        super().tearDown()

    def at(self, secs):
        self.clock.now = self.t0 + secs

    def tool(self, secs, name="Bash", arg="./check"):
        """A tool event at t=secs, and the tick that follows it."""
        self.at(secs)
        self.p._heard("tool", "%s %s" % (name, arg))
        self.p._on_claude_tool(name, arg)
        self.p._check_stall()

    def tick(self, secs):
        self.at(secs)
        self.p._check_stall()
        return self.card.stall_text()

    def quiet(self):
        return self.card.stall_text().startswith(
            "Still working · no new build")

    def build(self, secs, land_after=5):
        """A preview through the real start/landing path."""
        self.at(secs)
        self.p._run_build([build.SCRIPT], preview=True)
        self.assertIsNotNone(self.p._pending)
        self.at(secs + land_after)
        self.pendings[-1].land()
        self.p._poll_build()
        self.assertIsNone(self.p._pending)

    def test_r217_tool_calls_without_a_build_say_so(self):
        seen = {}
        for m in range(0, 11, 2):
            self.tool(m * 60)
            seen[m] = self.card.stall_text()
        for m in (0, 2, 4):
            self.assertEqual(seen[m], "", (m, seen[m]))
        self.assertEqual(seen[6], "Still working · no new build for 6 min")
        self.assertEqual(seen[10], "Still working · no new build for 10 min")
        self.assertFalse(self.card.stall_stop.isHidden(), "Stop offered")
        self.assertTrue(self.card.stall_btn.isHidden(), "no Retry")
        # R184 still works: 90 s of silence after that is the silence
        # line, and the next event takes it off for the no-build line.
        line = self.tick(10 * 60 + 90)
        self.assertIn("with no reply", line)
        self.tool(12 * 60)
        self.assertTrue(self.quiet(), self.card.stall_text())
        print("\n  [R217] 6 min: %r; silence at 11:30: %r"
              % (seen[6], line))

    def test_r217_a_build_clears_it_and_restarts_the_clock(self):
        for m in range(0, 7, 2):
            self.tool(m * 60)
        self.assertTrue(self.quiet())
        # a preview starts: the line goes at once
        self.at(6 * 60 + 10)
        self.p._run_build([build.SCRIPT], preview=True)
        self.assertEqual(self.card.stall_text(), "")
        # in flight for 6 minutes: never "no new build"
        for s in (7 * 60, 9 * 60, 12 * 60):
            self.tool(s)
            self.assertFalse(self.quiet(), s)
        self.at(12 * 60 + 30)
        self.pendings[-1].land()
        self.p._poll_build()
        self.tool(16 * 60)              # 3.5 min after it landed
        self.assertFalse(self.quiet())
        self.tool(18 * 60)              # 5.5 min after it landed
        self.assertEqual(self.card.stall_text(),
                         "Still working · no new build for 5 min")

    def test_r217_building_every_minute_never_shows_it(self):
        lines = []
        for m in range(0, 11):
            if m % 2 == 0:
                self.tool(m * 60)
            self.build(m * 60 + 20)
            lines.append(self.tick(m * 60 + 40))
        self.assertFalse(any(ln.startswith("Still working") for ln in lines),
                         lines)
        self.assertEqual(len(self.pendings), 11)
        print("\n  [R217] 11 previews in 10 min: no no-build line")

    def test_r217_sabotage_build_not_counted(self):
        """With _build_advanced taken out of the start/landing paths, a
        turn that builds every minute reads as one that never builds."""
        self.patch(self.p, "_build_advanced", lambda: None)
        lines = []
        for m in range(0, 11):
            if m % 2 == 0:
                self.tool(m * 60)
            self.build(m * 60 + 20)
            lines.append(self.tick(m * 60 + 40))
        self.assertTrue(any(ln.startswith("Still working") for ln in lines))

    def test_r217_stale_preview_in_progress_is_replaced(self):
        self.build(10)
        bc = self.p._build_card
        bc.set_status(self.p.PREVIEW_IN_PROGRESS, "idle")
        for m in range(2, 9, 2):
            self.tool(m * 60)
        self.assertNotEqual(bc.status.text(), self.p.PREVIEW_IN_PROGRESS)
        self.assertTrue(bc.status.text().startswith("last preview "),
                        bc.status.text())
        print("\n  [R217] build card after 8 min: %r" % bc.status.text())

    def test_r217_sabotage_without_the_check(self):
        self.patch(self.p, "_check_build_quiet", lambda card: None)
        self.build(10)
        bc = self.p._build_card
        bc.set_status(self.p.PREVIEW_IN_PROGRESS, "idle")
        for m in range(2, 11, 2):
            self.tool(m * 60)
        self.assertEqual(self.card.stall_text(), "")
        self.assertEqual(bc.status.text(), self.p.PREVIEW_IN_PROGRESS)

    def test_r217_r184_silence_line_unchanged(self):
        self.tool(0)
        self.assertEqual(self.tick(59), "")
        line = self.tick(90)
        self.assertIn("waiting on Bash ./check · 1m 30s with no reply", line)
        self.assertFalse(self.card.stall_btn.isHidden(), "Retry offered")
        self.tool(100)
        self.assertEqual(self.card.stall_text(), "")


# ================================================================== R205
FAIL_ROW = "✗ Write  intent.json · failed: InputValidationError: boom"


def _near(c, ref, tol=40):
    return (abs(c.red() - ref.red()) + abs(c.green() - ref.green()) +
            abs(c.blue() - ref.blue())) <= tol


def _fail_pixels(label, mode):
    label.ensurePolished()
    label.resize(max(label.sizeHint().width(), 400),
                 label.sizeHint().height())
    img = label.grab().toImage()
    ref = QtGui.QColor(style.tokens(mode)["fail"])
    return sum(1 for y in range(img.height()) for x in range(img.width())
               if _near(img.pixelColor(x, y), ref))


class TestR205FailedRowColour(twp.Round3):

    def card(self, rows):
        c = panel.ToolCard("Designing", "Claude Code", mono=False)
        self.p._add(c)
        for r in rows:
            c.append(r)
        return c

    def theme(self, m):
        self.patch(style, "mode", lambda m=m: m)
        self.p.restyle()

    def test_r205_failed_row_in_the_fail_colour_light_and_dark(self):
        out = {}
        for m in ("light", "dark"):
            self.theme(m)
            bad = self.card(["Write  intent.json"])
            bad.mark_failed("Write  intent.json", "InputValidationError: boom")
            ok = self.card(["Write  intent.json", "Bash  ./check"])
            self.assertEqual(bad.body.text(), FAIL_ROW)  # plain text
            self.assertNotIn("<", bad.body.text())
            n_bad, n_ok = _fail_pixels(bad.body, m), _fail_pixels(ok.body, m)
            self.assertGreater(n_bad, 20, m)
            self.assertEqual(n_ok, 0, m)
            out[m] = (n_bad, n_ok)
        print("\n  [R205] fail-colour pixels failed/normal row: %s" % out)

    def test_r205_theme_flip_redraws_in_the_new_fail_colour(self):
        self.theme("light")
        bad = self.card(["Write  intent.json"])
        bad.mark_failed("Write  intent.json", "boom")
        self.theme("dark")
        self.assertGreater(_fail_pixels(bad.body, "dark"), 20)

    def test_r205_restored_transcript_redraws_it(self):
        self.theme("light")
        a = self.fc.add(_Doc("A", "uid-a", [_Obj("Box")]))
        self.p.refresh_doc_pill()
        self.p._clear_empty()
        self.p._has_messages = True
        c = self.card(["Write  intent.json"])
        c.mark_failed("Write  intent.json", "InputValidationError: boom")
        b = self.fc.add(_Doc("B", "uid-b", [_Obj("Lid")]))
        self.p.refresh_doc_pill()
        self.assertFalse(any(FAIL_ROW in x.body.text()
                             for x in _visible(self.p, panel.ToolCard)))
        self.fc.mod.ActiveDocument = a
        self.p.refresh_doc_pill()
        back = [x for x in _visible(self.p, panel.ToolCard)
                if FAIL_ROW in x.body.text()]
        self.assertEqual(len(back), 1, "the failed row was not restored")
        self.assertIsNot(back[0], c, "not redrawn from the kept data")
        self.assertGreater(_fail_pixels(back[0].body, "light"), 20)
        del b
        print("\n  [R205] restored row %r drawn in fail colour"
              % back[0].body.text())

    def test_r205_sabotage_plain_label(self):
        class Plain(QtWidgets.QLabel):
            def has_failed_rows(self):
                return False

            def render(self):
                pass
        self.patch(panel, "_BodyLabel", Plain)
        self.theme("light")
        bad = self.card(["Write  intent.json"])
        bad.mark_failed("Write  intent.json", "InputValidationError: boom")
        self.assertEqual(_fail_pixels(bad.body, "light"), 0)


# ================================================================== R210
class TestR210NewChatDraft(twp.Round3):

    def setUp(self):
        super().setUp()
        self.viewport()
        _RecRun.runs = []
        self.patch(claude_cli, "ClaudeRun", _RecRun)
        self.a = self.fc.add(_Doc("A", "uid-a", [_Obj("Box")]))
        self.b = self.fc.add(_Doc("B", "uid-b", [_Obj("Lid")]),
                             active=False)

    def activate(self, doc, poll=True):
        self.fc.mod.ActiveDocument = doc
        if poll:
            self.p.refresh_doc_pill()
        tcr.APP.processEvents()

    def scenario(self):
        """A chat on A; New chat; type; B made active and the poll runs
        only then; back to A."""
        self.activate(self.a)
        self.send("make a box")
        self.p._on_claude_done("A box.", {})
        self.assertTrue(self.p.new_chat())
        self.p.input.setPlainText("a lid for the box")
        self.activate(self.b)
        on_b = self.p.input.toPlainText()
        self.activate(self.a)
        return on_b, self.p.input.toPlainText()

    def test_r210_draft_typed_after_new_chat_stays_with_its_document(self):
        on_b, on_a = self.scenario()
        self.assertEqual(on_b, "")
        self.assertEqual(on_a, "a lid for the box")
        print("\n  [R210] after New chat on A: B shows %r, A gets %r back"
              % (on_b, on_a))

    def test_r210_claim_alone_covers_an_unowned_screen(self):
        """_claim_draft: no owner yet when the text is typed (as at start,
        before the first poll) - the document active NOW owns it."""
        self.activate(self.a)
        self.p._shown_key = None
        self.p.input.setPlainText("for A")
        self.assertEqual(self.p._shown_key, "uid-a")
        self.activate(self.b)
        self.assertEqual(self.p.input.toPlainText(), "")
        self.activate(self.a)
        self.assertEqual(self.p.input.toPlainText(), "for A")

    def test_r210_sabotage_pre_fix_new_chat(self):
        """The pre-fix panel: New chat left no owner, and nothing claimed
        the draft - the poll gave it to B and A lost it."""
        self.p.input.textChanged.disconnect(self.p._claim_draft)
        real = self.p.new_chat

        def new_chat():
            ok = real()
            self.p._shown_key = None
            return ok
        self.p.new_chat = new_chat
        on_b, on_a = self.scenario()
        self.assertEqual(on_b, "a lid for the box")
        self.assertEqual(on_a, "")


if __name__ == "__main__":
    unittest.main()
