"""WS-CHAT round 10, headless against the REAL AgentPanel and ClaudeRun (the
fakes of test_chat_robustness / test_ws_chat_panel and the scripted fake
`claude` of round 9): R200 (a new chat continues from the design the
document holds; New chat never resets the document being left), R201
(a failed tool call is drawn as failed and the stall line names it), R198
(a quiet OPEN message is the model still working: Stop, no Retry), R199
(a draft typed under a Welcome is kept per document), R203 (a disabled
primary notice button is drawn disabled, light and dark).

Each item has a sabotage case where one can be made: the same scenario with
the fix taken out must fail the item's assertion.

The stall watchdog's 60 s is scaled to 1.5 s here (STALL_AFTER_S); "90 s
of silence" is 2.5 s of it.

RUN (the interpreter that ships):
    QT_QPA_PLATFORM=offscreen dist/build/squashfs-root/usr/bin/python \\
        -m unittest addon/AcadAgent/tests/test_ws_chat_round10.py -v
"""
import hashlib
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import test_chat_robustness as tcr  # noqa: E402  (sets HOME, Qt, settings)
import test_ws_chat_panel as twp  # noqa: E402
import test_ws_chat_round9 as tr9  # noqa: E402  (adds the "script" fake)

from PySide6 import QtGui  # noqa: E402

from acadagent import build, claude_cli, panel, style  # noqa: E402

wait_until = tcr.wait_until
_Obj, _Doc = twp._Obj, twp._Doc
_RecRun = tr9._RecRun
_visible, _titles = tr9._visible, tr9._titles

INIT = {"type": "system", "subtype": "init", "session_id": "sid-r10"}
RESULT = {"type": "result", "subtype": "success", "result": "done",
          "is_error": False, "duration_ms": 4000}
MSG_START = {"type": "stream_event", "event": {"type": "message_start"}}
MSG_STOP = {"type": "stream_event", "event": {"type": "message_stop"}}
# D76, as the session log had it: a Write with `path` for `file_path`.
WRITE = {"type": "assistant", "message": {"content": [
    {"type": "tool_use", "id": "toolu_1", "name": "Write",
     "input": {"path": "intent.json", "content": "{}"}}]}}
WRITE_ERR = {"type": "user", "message": {"content": [
    {"type": "tool_result", "tool_use_id": "toolu_1", "is_error": True,
     "content": "<tool_use_error>InputValidationError: Write failed due to "
                "the following issue:\nThe required parameter `file_path` "
                "is missing\nAn unexpected parameter `path` was provided"
                "</tool_use_error>"}]}}
REASON = "InputValidationError: The required parameter `file_path` is missing"


def _script(records):
    os.environ["FAKE_MODE"] = "script"
    os.environ["FAKE_SCRIPT"] = json.dumps(records)


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------ claude_cli
class TestR198R201Stream(tcr.Base):
    """ClaudeRun: message_open and tool_failed from the stream."""

    def run_script(self, records):
        _script(records)
        self.addCleanup(os.environ.pop, "FAKE_SCRIPT", None)
        run = claude_cli.ClaudeRun("hi", cwd=self.tmp)
        seen = {"open": [], "failed": [], "act": []}
        done = []
        run.message_open.connect(lambda on: seen["open"].append(on))
        run.tool_failed.connect(lambda *a: seen["failed"].append(a))
        run.activity.connect(lambda k, d: seen["act"].append((k, d)))
        run.finished_ok.connect(lambda *a: done.append(a))
        run.start()
        self.assertTrue(wait_until(lambda: done, 10))
        wait_until(lambda: not run.isRunning(), 5)
        return seen

    def test_r201_failed_tool_result_is_reported(self):
        seen = self.run_script([INIT, WRITE, WRITE_ERR, RESULT])
        self.assertEqual(seen["failed"], [("Write", "intent.json", REASON)])
        self.assertIn(("failed", "Write intent.json"), seen["act"])
        print("\n  [R201] tool_failed %s; activity %s" % (seen["failed"],
                                                          seen["act"]))

    def test_r201_ok_tool_result_is_not_a_failure(self):
        ok = {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "toolu_1",
             "content": "File created"}]}}
        seen = self.run_script([INIT, WRITE, ok, RESULT])
        self.assertEqual(seen["failed"], [])
        self.assertNotIn("failed", [k for k, _d in seen["act"]])

    def test_r198_message_open_follows_start_stop_and_retry(self):
        retry = {"type": "system", "subtype": "api_retry", "attempt": 1}
        seen = self.run_script([INIT, MSG_START, retry, MSG_START, MSG_STOP,
                                RESULT])
        self.assertEqual(seen["open"], [True, False, True, False])

    def test_r201_short_error(self):
        self.assertEqual(claude_cli.short_error(
            WRITE_ERR["message"]["content"][0]["content"]), REASON)
        self.assertEqual(claude_cli.short_error(
            [{"type": "text", "text": "Exit code 1\nboom"}]), "Exit code 1")
        self.assertEqual(claude_cli.short_error(None), "error")


# ------------------------------------------------------ stall forms, card
class _Stall(twp.Round3):

    def setUp(self):
        super().setUp()
        self.viewport()
        self.doc = self.fc.add(_Doc("Part", "uid-s", [_Obj("Box")]))
        self.patch(panel.AgentPanel, "STALL_AFTER_S", 1.5)
        self.addCleanup(os.environ.pop, "FAKE_SCRIPT", None)

    def send(self, text):
        self.p.input.setPlainText(text)
        self.p._on_send()

    def stalled(self, records, timeout=8):
        """Send, wait for the stall line; (card, line, retry?, stop?)."""
        _script(records)
        self.send("make a doorbell remote")
        card = self.p._card
        self.assertIsNotNone(card)
        self.assertTrue(wait_until(lambda: card.stall_text() != "", timeout),
                        "no stall line")
        return (card, card.stall_text(), not card.stall_btn.isHidden(),
                not card.stall_stop.isHidden())

    def finish(self):
        self.p._on_stop()
        self.assertTrue(self.idle(10))


class TestR201FailedToolCall(_Stall):

    def test_r201_failed_write_drawn_failed_then_stall_line(self):
        card, line, retry, stop = self.stalled(
            [INIT, WRITE, WRITE_ERR, {"sleep": 30}, RESULT])
        rows = card.body.text().split("\n")
        self.assertEqual(rows[-1], "✗ Write  intent.json · failed: " + REASON)
        self.assertNotIn("Write  intent.json", rows,
                         "the failed call still reads as the current step")
        # after 2.5 s (= 90 s unscaled) of silence
        wait_until(lambda: False, 1.0)
        line = card.stall_text()
        self.assertIn("the last tool call failed (Write intent.json: "
                      "InputValidationError", line)
        self.assertTrue(retry and stop, "the stall line offers Retry + Stop")
        # Stop on the card ends the turn
        card.stall_stop.click()
        self.assertFalse(self.p._busy)
        self.assertEqual(card.status.text(), "stopped")
        self.assertEqual(card.stall_text(), "")
        print("\n  [R201] row %r; stall %r (Retry %s, Stop %s)"
              % (rows[-1], line, retry, stop))
        self.assertTrue(self.idle(10))

    def test_r201_failed_row_kept_across_a_document_switch(self):
        card, _line, _r, _s = self.stalled(
            [INIT, WRITE, WRITE_ERR, {"sleep": 30}, RESULT])
        self.finish()
        other = self.fc.add(_Doc("B", "uid-b", [_Obj("Lid")]))
        self.p.refresh_doc_pill()
        self.fc.mod.ActiveDocument = self.doc
        self.p.refresh_doc_pill()
        bodies = [c.body.text() for c in _visible(self.p, panel.ToolCard)]
        self.assertTrue(any("✗ Write  intent.json · failed" in b
                            for b in bodies), bodies)
        del other

    def test_r201_sabotage_without_the_failure_hook(self):
        """The pre-fix card: the failed Write is the last row, as if it
        were the step in progress."""
        self.patch(self.p, "_on_claude_tool_failed", lambda *a: None)
        card, _line, _r, _s = self.stalled(
            [INIT, WRITE, WRITE_ERR, {"sleep": 30}, RESULT])
        self.assertEqual(card.body.text().split("\n")[-1],
                         "Write  intent.json")
        self.finish()


class TestR198StillWorking(_Stall):

    def test_r198_quiet_open_message_is_still_working(self):
        card, line, retry, stop = self.stalled(
            [INIT, MSG_START, {"sleep": 30}, MSG_STOP, RESULT])
        self.assertIn("still working", line)
        self.assertFalse(retry, "no Retry that would discard the reasoning")
        self.assertTrue(stop)
        print("\n  [R198] open message: %r (Retry %s, Stop %s)"
              % (line, retry, stop))
        self.finish()

    def test_r198_api_retry_keeps_the_retry_form(self):
        retry_rec = {"type": "system", "subtype": "api_retry", "attempt": 2}
        card, line, retry, stop = self.stalled(
            [INIT, MSG_START, retry_rec, {"sleep": 30}, RESULT])
        self.assertIn("the API is being retried (attempt 2)", line)
        self.assertTrue(retry and stop)
        print("\n  [R198] api_retry: %r (Retry %s, Stop %s)"
              % (line, retry, stop))
        self.finish()

    def test_r198_first_event_stall_keeps_the_retry_form(self):
        card, line, retry, _stop = self.stalled([INIT, {"sleep": 30},
                                                 RESULT])
        self.assertIn("waiting on the model", line)
        self.assertTrue(retry)
        self.finish()

    def test_r198_open_message_after_a_failed_call_is_still_working(self):
        card, line, retry, _stop = self.stalled(
            [INIT, WRITE, WRITE_ERR, MSG_START, {"sleep": 30}, RESULT])
        self.assertIn("still working", line)
        self.assertFalse(retry)
        self.finish()

    def test_r198_sabotage_no_open_message_check(self):
        self.patch(self.p, "_still_working", lambda: False)
        card, line, retry, _stop = self.stalled(
            [INIT, MSG_START, {"sleep": 30}, RESULT])
        self.assertNotIn("still working", line)
        self.assertTrue(retry)
        self.finish()


# -------------------------------------------------------------- R200
SCRIPT = ("import Part\n"
          "box = Part.makeBox(40, 30, 20)\n"
          "hole = Part.makeCylinder(1.5, 20, App.Vector(20, 15, 0))\n"
          "show(box.cut(hole), 'Case')\n")


class TestR200NewChatContinues(twp.Round3):

    def setUp(self):
        super().setUp()
        self.viewport()
        _RecRun.runs = []
        self.patch(claude_cli, "ClaudeRun", _RecRun)

    def built_doc(self, trusted=True, name="A", uid="uid-a"):
        """A document holding a body the agent built (a box with a Ø3
        hole): flagged, with its script embedded and - when `trusted` -
        its build id and script sha in the trust store, as build.py
        leaves it after a build."""
        o = _Obj("Case")
        o.AtechAgentBuilt = True
        o.AtechAgentScript = SCRIPT
        o.AtechAgentBuildId = "bid-" + uid
        o.AtechAgentBuild = 1
        doc = self.fc.add(_Doc(name, uid, [o]))
        if trusted:
            build._remember(doc, o.AtechAgentBuildId, SCRIPT, 1)
        return doc

    def activate(self, doc):
        self.fc.mod.ActiveDocument = doc
        self.p.refresh_doc_pill()
        tcr.APP.processEvents()

    def send(self, text):
        self.p.input.setPlainText(text)
        self.p._on_send()

    def turn(self, text, reply="Done."):
        self.send(text)
        self.p._on_claude_done(reply, {})
        self.assertFalse(self.p._busy)

    def model_in(self, ws):
        path = os.path.join(ws, build.SCRIPT)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_r200_new_chat_turn_starts_from_the_embedded_script(self):
        a = self.built_doc()
        self.activate(a)
        self.turn("make a 40 x 30 x 20 case with a 3 mm hole")
        first_ws = _RecRun.runs[-1]["cwd"]
        self.assertTrue(self.p.new_chat())
        st = self.p._docs["uid-a"]
        self.assertNotEqual(st.ws, first_ws)
        self.assertIsNone(self.model_in(st.ws), "adopted before the turn")
        self.send("make the case 4 mm deeper")
        run = _RecRun.runs[-1]
        self.assertEqual(run["cwd"], st.ws)
        got = self.model_in(run["cwd"])
        self.assertIsNotNone(got, "the new chat's workspace has no model.py")
        self.assertEqual(_sha(got), _sha(a.Objects[0].AtechAgentScript))
        self.assertEqual(st.prev["names"], ["Case"])
        self.assertIn("Continuing from the design in this document",
                      _titles(self.p))
        self.p._on_stop()
        print("\n  [R200] new chat ws %s: model.py sha %s == embedded"
              % (os.path.basename(st.ws), _sha(got)[:12]))

    def test_r200_sabotage_without_continue_design(self):
        self.patch(self.p, "_continue_design", lambda *a: False)
        a = self.built_doc()
        self.activate(a)
        self.turn("make a case")
        self.p.new_chat()
        self.send("make the case 4 mm deeper")
        self.assertIsNone(self.model_in(_RecRun.runs[-1]["cwd"]))
        self.p._on_stop()

    def test_r200_untrusted_script_is_not_adopted(self):
        a = self.built_doc(trusted=False, name="U", uid="uid-u")
        self.activate(a)
        self.p.new_chat()
        self.send("make it deeper")
        self.assertIsNone(self.model_in(_RecRun.runs[-1]["cwd"]))
        self.assertNotIn("Continuing from the design in this document",
                         _titles(self.p))
        self.p._on_stop()

    def test_r200_untrusted_newest_never_replaces_older_trusted(self):
        """An older TRUSTED build under a newer UNTRUSTED script: nothing is
        adopted, so the new chat's first build must not replace the trusted
        body it never saw (no previous-build record naming it); the review
        stays reachable."""
        a = self.built_doc(name="M", uid="uid-m")
        o2 = _Obj("Lid")
        o2.AtechAgentBuilt = True
        o2.AtechAgentScript = SCRIPT + "# elsewhere\n"
        o2.AtechAgentBuildId = "bid-foreign"
        o2.AtechAgentBuild = 2
        a.Objects.append(o2)
        self.activate(a)
        self.p.new_chat()
        self.send("make it deeper")
        st = self.p._docs["uid-m"]
        self.assertIsNone(self.model_in(_RecRun.runs[-1]["cwd"]))
        names = (st.prev or {}).get("names") or []
        self.assertNotIn("Case", names, "the next build would replace it")
        self.assertTrue(self.p._needs_review(st))
        self.p._on_stop()

    def test_r200_empty_document_new_chat_says_nothing(self):
        d = self.fc.add(_Doc("Empty", "uid-e", [_Obj("Box")]))
        self.activate(d)
        self.p.new_chat()
        self.send("make a box")
        self.assertIsNone(self.model_in(_RecRun.runs[-1]["cwd"]))
        self.assertNotIn("Continuing from the design in this document",
                         _titles(self.p))
        self.p._on_stop()

    def file_new_then_new_chat(self):
        a = self.built_doc()
        self.activate(a)
        self.turn("make a case with a hole", "A case, 40 x 30 x 20.")
        sa = self.p._docs["uid-a"]
        # File > New: the new document is active, and New chat is pressed
        # before the document poll has followed it.
        n = self.fc.add(_Doc("Unnamed", "uid-n", []))
        self.p.new_chat()
        return a, sa, n

    def test_r200_file_new_then_new_chat_leaves_the_document_left(self):
        a, sa, n = self.file_new_then_new_chat()
        self.assertIs(self.p._docs["uid-a"], sa, "A's ChatState was reset")
        self.assertIn("uid-n", self.p._docs)
        self.assertEqual(self.bubbles(), [])
        self.activate(a)
        self.assertEqual(self.bubbles(), ["make a case with a hole",
                                          "A case, 40 x 30 x 20."])
        self.send("and 4 mm deeper")
        self.assertEqual(_RecRun.runs[-1]["cwd"], sa.ws)
        self.p._on_stop()
        print("\n  [R200] File > New + New chat: A keeps %s and its "
              "transcript" % os.path.basename(sa.ws))

    def test_r200_sabotage_new_chat_without_follow(self):
        """The pre-fix new_chat cleared the transcript on screen without
        keeping it for the document it belonged to."""
        self.patch(self.p, "_follow_active_doc", lambda draft=False: False)
        a, _sa, _n = self.file_new_then_new_chat()
        self.patch(self.p, "_follow_active_doc",
                   panel.AgentPanel._follow_active_doc.__get__(self.p))
        self.activate(a)
        self.assertEqual(self.bubbles(), [])

    def test_r200_running_turn_of_the_document_left_is_not_stopped(self):
        a = self.built_doc()
        self.activate(a)
        self.send("make a case")
        sa = self.p._cur
        self.assertTrue(self.p._busy)
        self.fc.add(_Doc("Unnamed", "uid-n", []))
        self.assertTrue(self.p.new_chat())
        self.assertTrue(self.p._busy, "A's turn was stopped")
        self.assertIs(self.p._cur, sa)
        self.assertIs(self.p._docs["uid-a"], sa)
        self.assertEqual(self.bubbles(), ["make a case"])
        self.p._on_claude_done("A case.", {})
        self.assertFalse(self.p._busy)


# -------------------------------------------------------------- R199
class TestR199WelcomeDraft(twp.Round3):

    def setUp(self):
        super().setUp()
        self.viewport()
        _RecRun.runs = []
        self.patch(claude_cli, "ClaudeRun", _RecRun)
        self.a = self.fc.add(_Doc("A", "uid-a", [_Obj("Box")]))
        self.b = self.fc.add(_Doc("B", "uid-b", [_Obj("Lid")]),
                             active=False)

    def activate(self, doc):
        self.fc.mod.ActiveDocument = doc
        self.p.refresh_doc_pill()
        tcr.APP.processEvents()

    def test_r199_draft_under_a_welcome_survives_a_switch(self):
        self.activate(self.b)
        self.assertIsInstance(self.p._empty, panel.Welcome)
        self.p.input.setPlainText("a lid with a")
        self.activate(self.a)
        self.assertEqual(self.p.input.toPlainText(), "")
        self.activate(self.b)
        self.assertEqual(self.p.input.toPlainText(), "a lid with a")
        self.assertIsInstance(self.p._empty, panel.Welcome)
        self.assertEqual(self.bubbles(), [])
        print("\n  [R199] B's Welcome draft back: %r"
              % self.p.input.toPlainText())

    def test_r199_both_welcome_only(self):
        self.activate(self.a)
        self.p.input.setPlainText("for A")
        self.activate(self.b)
        self.p.input.setPlainText("for B")
        self.activate(self.a)
        self.assertEqual(self.p.input.toPlainText(), "for A")
        self.activate(self.b)
        self.assertEqual(self.p.input.toPlainText(), "for B")


# -------------------------------------------------------------- R203
class TestR203DisabledPrimary(twp.Case):

    def fill(self, btn):
        img = btn.grab().toImage()
        return img.pixelColor(img.width() // 2, 3).name()

    def test_r203_disabled_primary_differs_light_and_dark(self):
        out = {}
        for m in ("light", "dark"):
            self.patch(style, "mode", lambda m=m: m)
            self.p.restyle()
            n = self.p.show_notice("Before you send", "body",
                                   actions=[("Continue", lambda: None),
                                            ("Not now", lambda: None)])
            n.buttons[1].setEnabled(False)
            live = n.buttons[0]
            twin = self.p.show_notice("Before you send", "body",
                                      actions=[("Continue", lambda: None)])
            dead = twin.buttons[0]
            dead.setEnabled(False)
            for b in (live, dead):
                b.resize(b.sizeHint())
                b.ensurePolished()
            t = style.tokens(m)
            on, off = self.fill(live), self.fill(dead)
            self.assertEqual(on, QtGui.QColor(t["btn_bg"]).name(), m)
            self.assertNotEqual(off, on, "%s: disabled looks live" % m)
            self.assertEqual(off, QtGui.QColor(t["line_strong"]).name(), m)
            out[m] = (on, off)
        print("\n  [R203] primary fill enabled/disabled: %s" % out)

    def test_r203_sabotage_without_the_disabled_rule(self):
        """The pre-fix sheet: the disabled primary is filled like a live
        one."""
        self.patch(panel, "PANEL_QSS", "\n".join(
            ln for ln in panel.PANEL_QSS.split("\n")
            if "#NoticeBtn[primary=\"true\"]:disabled" not in ln))
        self.patch(style, "mode", lambda: "light")
        self.p.restyle()
        n = self.p.show_notice("Before you send", "body",
                               actions=[("Continue", lambda: None)])
        btn = n.buttons[0]
        on = self.fill(btn)
        btn.setEnabled(False)
        self.assertEqual(self.fill(btn), on)


if __name__ == "__main__":
    unittest.main()
