"""WS-CHAT round 9, headless against the REAL AgentPanel and ClaudeRun (the
fakes of test_chat_robustness / test_ws_chat_panel, plus a scripted fake
`claude` that can go quiet): R190 (the chat transcript kept per document
and drawn again on a tab switch), R184 (the stall watchdog), R191 (panel
half: an unchanged fix turn that disputes intent-only misses ends neutral),
R186 (the in-progress explanation is a muted note, the R127 caveat stays a
warning), R187 (the sample crane's own "Try asking" examples).

Each item has a sabotage case: the same scenario with the fix taken out
(restore replaced by clear, the watchdog's event hook removed, the dispute
check off) must fail the item's assertion.

RUN (the interpreter that ships):
    QT_QPA_PLATFORM=offscreen dist/build/squashfs-root/usr/bin/python \\
        -m unittest addon/AcadAgent/tests/test_ws_chat_round9.py -v
"""
import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import test_chat_robustness as tcr  # noqa: E402  (sets HOME, Qt, settings)
import test_ws_chat_panel as twp  # noqa: E402
import test_ws_chat_round5 as tr5  # noqa: E402
import test_ws_chat_round7 as tr7  # noqa: E402

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from acadagent import build, claude_cli, panel, style  # noqa: E402

# A scripted mode for the shared fake: FAKE_SCRIPT is a JSON list of stream
# records and {"sleep": seconds} pauses, replayed in order.
if 'mode == "script"' not in tcr.FAKE:
    tcr.FAKE = tcr.FAKE.replace(
        'elif mode == "weird":',
        'elif mode == "script":\n'
        '    for rec in json.loads(os.environ["FAKE_SCRIPT"]):\n'
        '        if isinstance(rec, dict) and "sleep" in rec:\n'
        '            time.sleep(rec["sleep"])\n'
        '        else:\n'
        '            emit(rec)\n'
        'elif mode == "weird":')

wait_until = tcr.wait_until
_Obj, _Doc = twp._Obj, twp._Doc

TB = ('Traceback (most recent call last):\n'
      '  File "model.py", line 3, in <module>\n'
      'NameError: name \'wall\' is not defined')


class _RecRun(twp._NoRun):
    """A ClaudeRun that never starts a process and records what it was
    asked: the prompt and the workspace (cwd)."""

    runs = []

    def __init__(self, prompt, cwd=None, **k):
        super().__init__(prompt, cwd=cwd, **k)
        _RecRun.runs.append({"prompt": prompt, "cwd": cwd,
                             "sid": k.get("session_id"),
                             "images": list(k.get("images") or ())})

    def requestInterruption(self):                     # noqa: N802
        pass


def _visible(p, cls):
    return [w for w in p.findChildren(cls) if not w.isHidden()]


def _titles(p):
    return [n.spec[0] for n in _visible(p, panel.Notice)]


# ------------------------------------------------------------------ R190
class TestR190TranscriptPerDocument(twp.Round3):

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

    def build_in_a(self):
        """A turn in A whose build fails after the last fix: user bubble,
        Designing card, failed build card, red notice."""
        self.activate(self.a)
        self.send("make a box")
        st = self.p._cur
        with open(os.path.join(st.ws, "model.py"), "w") as fh:
            fh.write("box = wall\n")
        self.patch(build, "start", twp._now(build.Result(
            False, "model.py", error=TB)))
        self.p._attempt = self.p.MAX_FIX_ATTEMPTS     # the last fix
        self.p._on_claude_done("Built a box.", {})
        self.assertFalse(self.p._busy)
        return st

    def fail_in_b(self):
        """A turn in B that stops with the Retry notice."""
        self.activate(self.b)
        self.send("make a lid")
        st = self.p._cur
        self.p._on_claude_failed("the Claude Code run broke: boom")
        self.assertFalse(self.p._busy)
        return st

    def scenario(self):
        """Build in A, switch to B (Welcome), send in B, switch back to A,
        then to B again. Returns what each step showed."""
        seen = {}
        sa = self.build_in_a()
        seen["a0"] = (self.bubbles(), _titles(self.p))
        self.activate(self.b)
        seen["b_welcome"] = (isinstance(self.p._empty, panel.Welcome),
                             self.bubbles(), _titles(self.p))
        sb = self.fail_in_b()
        self.activate(self.a)
        cards = {c.spec[0]: c.status.text()
                 for c in _visible(self.p, panel.ToolCard)}
        seen["a1"] = (self.bubbles(), _titles(self.p), cards)
        self.activate(self.b)
        seen["b1"] = (self.bubbles(), _titles(self.p))
        return sa, sb, seen

    def test_r190_switch_back_shows_each_documents_chat(self):
        sa, sb, seen = self.scenario()
        self.assertIn("make a box", seen["a0"][0])
        self.assertIn("The build still fails", seen["a0"][1])
        # B starts on its Welcome: none of A's chat
        is_welcome, bubbles, titles = seen["b_welcome"]
        self.assertTrue(is_welcome)
        self.assertEqual(bubbles, [])
        self.assertNotIn("The build still fails", titles)
        # back in A: A's bubble, cards (with their status) and notice
        bubbles, titles, cards = seen["a1"]
        self.assertEqual(bubbles, ["make a box"])
        self.assertIn("The build still fails", titles)
        self.assertNotIn("The agent stopped before finishing", titles)
        self.assertEqual(cards.get("Building the model"), "failed")
        self.assertIn("Designing", cards)
        # and B's again
        bubbles, titles = seen["b1"]
        self.assertEqual(bubbles, ["make a lid"])
        self.assertIn("The agent stopped before finishing", titles)
        self.assertNotIn("The build still fails", titles)
        print("\n  [R190] A: %s %s | B: %s %s" % (
            seen["a1"][0], seen["a1"][1], bubbles, titles))

    def test_r190_restored_retry_and_follow_up_go_to_their_own_chat(self):
        sa, sb, _seen = self.scenario()
        # B is on screen: its restored Retry resends B's message in B.
        notice = [n for n in _visible(self.p, panel.Notice)
                  if n.spec[0] == "The agent stopped before finishing"][0]
        before = len(_RecRun.runs)
        notice.buttons[0].click()
        self.assertEqual(len(_RecRun.runs), before + 1)
        run = _RecRun.runs[-1]
        self.assertEqual(run["cwd"], sb.ws)
        self.assertTrue(run["prompt"].startswith("make a lid"))
        self.p._on_stop()
        # A follow-up in A goes to A's workspace.
        self.activate(self.a)
        self.send("and round the edges")
        run = _RecRun.runs[-1]
        self.assertEqual(run["cwd"], sa.ws)
        self.assertNotEqual(sa.ws, sb.ws)
        self.assertEqual(self.bubbles(), ["make a box",
                                          "and round the edges"])
        print("\n  [R190] retry in B -> %s; follow-up in A -> %s" % (
            os.path.basename(sb.ws), os.path.basename(sa.ws)))

    def test_r190_sabotage_clear_instead_of_restore(self):
        """The scenario with the restore replaced by the old clear: A's
        chat is gone after the switch back, so the R190 check fails."""
        self.patch(self.p, "_restore", lambda kept: 0)
        _sa, _sb, seen = self.scenario()
        bubbles, titles, _cards = seen["a1"]
        self.assertNotIn("make a box", bubbles)
        self.assertNotIn("The build still fails", titles)

    def test_r190_running_turn_stays_with_its_document(self):
        self.activate(self.a)
        self.send("make a box")
        self.assertTrue(self.p._busy)
        self.activate(self.b)
        # mid-turn: A's transcript stays on screen, the turn's card with it
        self.assertEqual(self.p._shown_key, "uid-a")
        self.assertEqual(self.bubbles(), ["make a box"])
        self.p._on_claude_done("A box, 20 mm.", {})
        self.assertFalse(self.p._busy)
        self.activate(self.b)          # followed once the turn has ended
        self.assertEqual(self.p._shown_key, "uid-b")
        self.assertEqual(self.bubbles(), [])
        self.activate(self.a)
        self.assertEqual(self.bubbles(), ["make a box", "A box, 20 mm."])

    def test_r190_queued_view_and_budget_continue_stay_with_the_document(self):
        self.activate(self.a)
        sa = self.p._state_for(self.a)
        shot = os.path.join(sa.ws, "view-1.png")
        img = QtGui.QImage(40, 30, QtGui.QImage.Format_RGB32)
        img.fill(QtGui.QColor("#336699"))
        self.assertTrue(img.save(shot))
        self.p.add_shot(shot, "10:00 · Isometric")
        self.assertEqual(self.p._pending_shots, [shot])
        self.activate(self.b)
        self.assertEqual(self.p._pending_shots, [])
        self.assertEqual(_visible(self.p, panel.Shot), [])
        self.activate(self.a)
        self.assertEqual(self.p._pending_shots, [shot])
        self.assertEqual([s.spec for s in _visible(self.p, panel.Shot)],
                         [(shot, "10:00 · Isometric")])
        # the queued view goes with A's next turn
        self.send("what is this?")
        self.assertEqual(_RecRun.runs[-1]["images"], [shot])
        # R101: Continue on a budget notice keeps its own chat, although
        # another document's turn ran in between
        self.p._on_claude_failed("error_max_budget_usd: budget exceeded")
        self.activate(self.b)
        self.send("and in B?")
        sb = self.p._cur
        self.p._on_stop()
        self.assertIs(self.p._cur, sb)
        self.activate(self.a)
        n = [n for n in _visible(self.p, panel.Notice)
             if n.spec[0].startswith("Stopped at")][0]
        n.buttons[0].click()
        self.assertEqual(_RecRun.runs[-1]["cwd"], sa.ws)
        self.assertNotEqual(sa.ws, sb.ws)
        self.p._on_stop()

    def test_r184_retry_resends_the_turns_views(self):
        """A stall Retry sends the views the stalled turn carried; a view
        captured during that turn stays queued for the next message."""
        self.activate(self.a)
        sa = self.p._state_for(self.a)
        shots = []
        for i in (1, 2):
            shot = os.path.join(sa.ws, "view-%d.png" % i)
            img = QtGui.QImage(40, 30, QtGui.QImage.Format_RGB32)
            img.fill(QtGui.QColor("#336699"))
            self.assertTrue(img.save(shot))
            shots.append(shot)
        self.p.add_shot(shots[0], "10:00 · Isometric")
        self.send("what is this?")
        self.assertEqual(_RecRun.runs[-1]["images"], [shots[0]])
        self.p.add_shot(shots[1], "10:01 · Top")     # queued mid-turn
        self.assertTrue(self.p._retry_stalled())
        self.assertEqual(_RecRun.runs[-1]["images"], [shots[0]])
        self.assertEqual(self.p._pending_shots, [shots[1]])
        self.assertEqual(self.p._shot_captions.get(shots[1]), "10:01 · Top")
        self.p._on_stop()

    def test_r190_composer_draft_follows_the_document(self):
        self.fail_in_b()        # puts "make a lid" back in B's box (R23)
        self.assertEqual(self.p.input.toPlainText(), "make a lid")
        self.activate(self.a)
        self.assertEqual(self.p.input.toPlainText(), "")
        self.p.input.setPlainText("half a thought")
        self.activate(self.b)
        self.assertEqual(self.p.input.toPlainText(), "make a lid")
        self.activate(self.a)
        self.assertEqual(self.p.input.toPlainText(), "half a thought")

    def test_r190_new_chat_forgets_the_kept_transcript(self):
        self.build_in_a()
        self.activate(self.b)
        self.activate(self.a)
        self.assertEqual(self.bubbles(), ["make a box"])
        self.p.new_chat()
        self.activate(self.b)
        self.activate(self.a)
        self.assertEqual(self.bubbles(), [])
        self.assertIsInstance(self.p._empty, panel.Welcome)

    def send(self, text):
        self.p.input.setPlainText(text)
        self.p._on_send()


# ------------------------------------------------------------------ R184
class TestR184StallWatchdog(twp.Round3):

    def script(self, records):
        os.environ["FAKE_MODE"] = "script"
        os.environ["FAKE_SCRIPT"] = json.dumps(records)
        self.addCleanup(os.environ.pop, "FAKE_SCRIPT", None)

    def setUp(self):
        super().setUp()
        self.viewport()
        self.doc = self.fc.add(_Doc("Part", "uid-s", [_Obj("Box")]))
        self.patch(panel.AgentPanel, "STALL_AFTER_S", 1.5)

    INIT = {"type": "system", "subtype": "init", "session_id": "sid-stall"}
    RESULT = {"type": "result", "subtype": "success", "result": "done",
              "is_error": False, "duration_ms": 4000}

    @staticmethod
    def text(t):
        return {"type": "assistant",
                "message": {"content": [{"type": "text", "text": t}]}}

    def run_quiet_then_event(self):
        """A stream that goes quiet for 3.5 s, then speaks, then ends."""
        self.script([self.INIT, {"sleep": 3.5}, self.text("Writing it."),
                     {"sleep": 0.8}, self.RESULT])
        self.send("make a box")
        card = self.p._card
        self.assertIsNotNone(card)
        shown = wait_until(lambda: card.stall_text() != "", 6)
        line = card.stall_text()
        visible_btn = not card.stall_btn.isHidden()
        cleared = wait_until(lambda: card.stall_text() == "" or
                             not self.p._busy, 6)
        cleared_mid_turn = cleared and card.stall_text() == "" and \
            self.p._busy
        self.assertTrue(self.idle(10))
        return shown, line, visible_btn, cleared_mid_turn

    def test_r184_quiet_stream_shows_waiting_then_clears(self):
        t0 = time.monotonic()
        shown, line, btn, cleared = self.run_quiet_then_event()
        self.assertTrue(shown, "no waiting line after 1.5 s of silence")
        self.assertIn("waiting on the model", line)
        self.assertTrue(btn, "the waiting line offers Retry")
        self.assertTrue(cleared, "the next event did not clear the line")
        # the run was not killed: its result arrived and is the reply
        self.assertIn("done", self.bubbles())
        print("\n  [R184] %r; cleared by the next event; turn ended "
              "normally after %.1f s" % (line, time.monotonic() - t0))

    def test_r184_sabotage_no_event_hook(self):
        """Without the event hook the line never clears mid-turn."""
        self.patch(self.p, "_heard_then", lambda handler, kind="model":
                   handler)
        self.patch(self.p, "_heard", lambda *a: None)
        self.p._last_event_t = time.monotonic()
        _shown, _line, _btn, cleared = self.run_quiet_then_event()
        self.assertFalse(cleared)

    def test_r184_waiting_on_a_tool_names_it(self):
        self.script([self.INIT, {"type": "assistant", "message": {
            "content": [{"type": "tool_use", "name": "Bash",
                         "input": {"command": "./check"}}]}},
            {"sleep": 3.0}, self.RESULT])
        self.send("check it")
        card = self.p._card
        self.assertTrue(wait_until(lambda: card.stall_text() != "", 6))
        self.assertIn("waiting on Bash ./check", card.stall_text())
        self.assertTrue(self.idle(10))

    def test_r184_retry_resends_in_the_same_chat(self):
        self.script([self.INIT, {"sleep": 30}, self.RESULT])
        self.send("make a box")
        card = self.p._card
        st = self.p._cur
        self.assertTrue(wait_until(lambda: card.stall_text() != "", 6))
        self.p.input.setPlainText("half-typed")
        card.stall_btn.click()
        self.assertTrue(self.p._busy, "the retry is a running turn")
        self.assertIsNot(self.p._card, card)
        self.assertEqual(card.status.text(), "stopped")
        self.assertEqual(card.stall_text(), "", "a stopped card waits on "
                                                "nothing")
        self.assertTrue(card.stall_btn.isHidden())
        self.assertIs(self.p._cur, st)
        self.assertEqual(self.p.input.toPlainText(), "half-typed")
        self.assertTrue(wait_until(lambda: len(self.turns()) >= 2, 5))
        first, second = self.turns()[:2]
        self.assertEqual(second["cwd"], first["cwd"])
        self.assertTrue(second["stdin"].startswith("make a box"))
        self.assertIn("--resume", second["argv"])
        self.p._on_stop()
        self.assertTrue(self.idle(10))

    def send(self, text):
        self.p.input.setPlainText(text)
        self.p._on_send()


class TestR184ActivitySignal(tcr.Base):
    """claude_cli.ClaudeRun.activity: every stream event, the state named."""

    def test_r184_activity_names_what_the_turn_waits_on(self):
        os.environ["FAKE_MODE"] = "script"
        os.environ["FAKE_SCRIPT"] = json.dumps([
            {"type": "system", "subtype": "init", "session_id": "s1"},
            {"type": "system", "subtype": "api_retry", "attempt": 2},
            {"type": "assistant", "message": {"content": [
                {"type": "text", "text": "Checking."},
                {"type": "tool_use", "name": "Bash",
                 "input": {"command": "./check"}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "content": "CHECK PASS"}]}},
            {"type": "stream_event", "event": {"type": "message_start"}},
            {"type": "stream_event", "event": {"type": "message_start"}},
            {"type": "result", "subtype": "success", "result": "ok",
             "is_error": False}])
        self.addCleanup(os.environ.pop, "FAKE_SCRIPT", None)
        run = claude_cli.ClaudeRun("hi", cwd=self.tmp)
        seen, done = [], []
        run.activity.connect(lambda k, d: seen.append((k, d)))
        run.finished_ok.connect(lambda *a: done.append(a))
        run.start()
        self.assertTrue(wait_until(lambda: done, 10))
        wait_until(lambda: not run.isRunning(), 5)
        self.assertEqual(seen, [("model", ""), ("retry", "2"),
                                ("tool", "Bash ./check"), ("model", "")])
        print("\n  [R184] activity: %s" % seen)


# ------------------------------------------------------------------ R191
INTENT_MISS = "slots: 4 stated, 0 found (d_mm 14)"


class TestR191DisputedCheck(twp.Round3):

    def setUp(self):
        super().setUp()
        self.viewport()
        _RecRun.runs = []
        self.patch(claude_cli, "ClaudeRun", _RecRun)

    def result(self, atech_fail=False):
        r = twp._ok_result()
        r.intent_problems = [INTENT_MISS]
        if atech_fail:
            r.atech_verdicts = {"light_p3": {"seated": "FAIL"}}
            r.atech_checked = True
        return r

    def first_turn(self, **kw):
        st = self.turn_state(doc=self.box_doc())
        self.script(st, "holder = 1\n")
        self.patch(build, "start", twp._now(self.result(**kw)))
        self.p._attempt = 0
        self.p._on_claude_done("Built the holder.", {})     # fails: intent
        self.assertEqual(len(_RecRun.runs), 1, "one fix turn sent")
        self.assertTrue(self.p._fix_turn)
        return st

    def unchanged_fix_turn(self, reply="The part already matches: four "
                                       "14 mm rectangular slots."):
        # the agent answers and leaves model.py exactly as it was
        self.p._on_claude_done(reply, {})

    def build_card(self):
        return [c for c in _visible(self.p, panel.ToolCard)
                if c.spec[0] == "Building the model"][-1]

    def test_r191_unchanged_fix_turn_with_intent_only_misses_ends_neutral(
            self):
        st = self.first_turn()
        self.assertEqual(st.failed_intent, [INTENT_MISS])
        self.unchanged_fix_turn()
        self.assertFalse(self.p._busy)
        self.assertEqual(len(_RecRun.runs), 1, "no second fix turn")
        self.assertNotIn("The build still fails", _titles(self.p))
        card = self.build_card()
        self.assertEqual(card.status.text(), "not confirmed")
        self.assertEqual(card.status.objectName(), "StatusIdle")
        self.assertIn("could not confirm", card.body.text())
        self.assertEqual(card.note.objectName(), "ToolInfo")
        self.assertIn("The check could not confirm", card.note.text())
        self.assertIn(INTENT_MISS, card.note.text())
        self.assertIn("The part already matches: four 14 mm rectangular "
                      "slots.", self.bubbles())
        print("\n  [R191] status %r; note %r" % (card.status.text(),
                                                 card.note.text()[:80]))

    def test_r191_sabotage_without_the_dispute_check_ends_red(self):
        """The old path: the same misses go back until 'Tried 2 fixes'."""
        self.patch(self.p, "_disputed_check", lambda: False)
        self.first_turn()
        self.unchanged_fix_turn()
        self.assertEqual(len(_RecRun.runs), 2)
        self.unchanged_fix_turn()
        self.assertIn("The build still fails", _titles(self.p))

    def test_r191_other_failures_still_go_back(self):
        """An Atech FAIL beside the intent miss is a real failure: the
        unchanged fix turn is sent back as before."""
        st = self.first_turn(atech_fail=True)
        self.assertIsNone(st.failed_intent)
        self.unchanged_fix_turn()
        self.assertEqual(len(_RecRun.runs), 2, "the failure went back")
        self.assertEqual(self.build_card().status.text(),
                         "unchanged: still fails")

    def test_r191_changed_script_is_judged_as_usual(self):
        st = self.first_turn()
        self.script(st, "holder = 2\n")     # the agent did change it
        self.unchanged_fix_turn("Widened the slots.")
        self.assertEqual(len(_RecRun.runs), 2, "still short: fix sent")
        self.assertNotEqual(self.build_card().status.text(),
                            "not confirmed")


# ------------------------------------------------------------------ R186
class TestR186InProgressNoteIsMuted(twp.Round3):

    def _doc(self):
        d = tr5._board(modules=[("light", (3,))])
        d.Objects.append(_Obj("Case"))
        return self.fc.add(d)

    def color(self, w):
        w.ensurePolished()
        return w.palette().color(QtGui.QPalette.WindowText).name()

    def test_r186_explanation_muted_caveat_warning(self):
        self.viewport()
        st = self.turn_state(key="uid-mods", doc=self._doc())
        self.p._settle(st, tr7._atech_result(tr7.SLIDE_FAIL), True, "h1")
        card = self.p._build_card
        note = card.note
        t = style.tokens()
        self.assertEqual(card.status.text(), "preview: in progress")
        self.assertEqual(note.objectName(), "ToolInfo")
        self.assertNotIn("⚠", note.text())
        self.assertIn("slide path is closed", note.text())
        self.assertEqual(self.color(note), QtGui.QColor(t["muted"]).name())
        self.assertNotEqual(self.color(note), QtGui.QColor(t["warn"]).name())
        # R127: the caveat alone keeps the warning style
        ok = dict(tr7.SLIDE_FAIL, slide_path="PASS")
        r = tr7._atech_result(ok)
        r.warning = tr5.TestR127Caveat.CAVEAT
        self.p._settle(st, r, True, "h2")
        self.assertEqual(note.objectName(), "ToolWarn")
        self.assertTrue(note.text().startswith("⚠"))
        self.assertEqual(self.color(note), QtGui.QColor(t["warn"]).name())
        # both: the warning, with the explanation in the muted colour
        self.p._settle(st, tr7._atech_result(tr7.SLIDE_FAIL), True, "h3")
        self.assertEqual(note.objectName(), "ToolWarn")
        self.assertIn('<span style="color:%s">A module' % t["muted"],
                      note.text())
        print("\n  [R186] explanation %s (muted %s), caveat %s (warn %s)" % (
            "ToolInfo", t["muted"], "ToolWarn", t["warn"]))


# ------------------------------------------------------------------ R187
class TestR187CraneSuggestions(twp.Round3):

    CRANE = ["base_plate", "slew_ring_gear", "turret_deck", "lattice_jib",
             "hoist_pinion", "hoist_wheel", "hook_block", "counterweight"]

    def setUp(self):
        super().setUp()
        vp = self.viewport()
        vp.crane_parts = lambda: ["/x/%s.brep" % n for n in self.CRANE]

    def prompts(self):
        return [r.text() for r in self.p._empty.rows]

    def test_r187_sample_crane_gets_crane_examples(self):
        self.fc.add(_Doc("SampleCrane", "uid-c",
                         [_Obj(n) for n in self.CRANE]))
        self.p.refresh_doc_pill(force=True)
        self.assertEqual(self.p._empty_kind, "crane")
        ps = self.prompts()
        self.assertEqual(ps, list(panel.AgentPanel.CRANE_PROMPTS))
        self.assertFalse(any("walls" in p or "mounting holes" in p
                             for p in ps), ps)
        self.assertTrue(all("crane" in p or "jib" in p for p in ps), ps)
        print("\n  [R187] crane: %s" % ps)

    def test_r187_crane_saved_under_another_name(self):
        self.fc.add(_Doc("MyCrane", "uid-c2",
                         [_Obj(n) for n in self.CRANE] + [_Obj("Extra")]))
        self.p.refresh_doc_pill(force=True)
        self.assertEqual(self.p._empty_kind, "crane")

    def test_r187_other_documents_unchanged(self):
        self.fc.add(_Doc("Part", "uid-p", [_Obj("Body"), _Obj("hook_block")]))
        self.p.refresh_doc_pill(force=True)
        self.assertEqual(self.p._empty_kind, "doc")
        self.assertIn("Make the walls 1 mm thicker", self.prompts())


if __name__ == "__main__":
    unittest.main()
