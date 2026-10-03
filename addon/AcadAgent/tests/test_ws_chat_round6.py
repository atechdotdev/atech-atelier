"""WS-CHAT round 6, headless against the REAL AgentPanel (same fakes as
test_ws_chat_panel / round5): R142 (captures follow the chat width),
R143 (first-run view with the sign-in notice opens at its heading), R144
(a closed / switched-away document's chat leaves the screen), R145 (Ask
about this view looks at a board's module face), R146 (empty-document
examples, warning-coloured caveat), R153 (the view answer renders
Markdown), S49 (a draft short of intent.json only is "in progress").

R145 was also measured in a real Studio, offscreen (dist/test-root, whose
AcadAgent links this repo; QT_QPA_PLATFORM=offscreen, isolated HOME; the
board + a Light seated on port 3 with atech_ports.seat; the Light coloured
#ff00ff because its own colour is the board's; pixels r>120, b>120, g<90,
1 in 9 sampled of 1200x900): capture.capture(view_name="Isometric") 0 of
120 000, capture.capture(view_name=capture.MODULE_FACE) 1 180 of 120 000
(module_face_direction (0.6, 1.0, 0.5): the camera on the +Y module side).

RUN (the interpreter that ships):
    QT_QPA_PLATFORM=offscreen dist/build/squashfs-root/usr/bin/python \\
        -m unittest addon/AcadAgent/tests/test_ws_chat_round6.py -v
"""
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import test_chat_robustness as tcr  # noqa: E402  (sets HOME, Qt, settings)
import test_ws_chat_panel as twp  # noqa: E402
import test_ws_chat_round5 as tr5  # noqa: E402

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from acadagent import build, capture, engine, panel, style, vision  # noqa: E402

wait_until = tcr.wait_until
_Doc, _Obj = twp._Doc, twp._Obj
PANEL_900x600 = tr5.PANEL_900x600          # (300, 462), measured in round 4

TABLE_ANSWER = ("**What it is:** a 60 x 40 mm box.\n\n"
                "| part | size |\n|---|---|\n| lid | 60 x 40 |\n"
                "| body | 60 x 40 x 20 |\n")


def _png(path, w=1200, h=900, colour="#3366cc"):
    img = QtGui.QImage(w, h, QtGui.QImage.Format_RGB32)
    img.fill(QtGui.QColor(colour))
    assert img.save(path)
    return path


class _Shown(twp.Round3):
    """A panel shown at a given size, laid out for real."""

    def show_at(self, size):
        w, h = size
        self.p.setMinimumWidth(min(self.p.minimumWidth(), w))    # shell.py
        self.p.resize(w, h)
        self.p.show()
        self.addCleanup(self.p.hide)
        self.settle()

    @staticmethod
    def settle(secs=0.25):
        wait_until(lambda: False, secs)

    def widths(self):
        """(content width, viewport width, widest child's right edge in
        viewport coordinates)."""
        vp = self.p.scroll.viewport()
        right = 0
        for i in range(self.p.stream.count()):
            w = self.p.stream.itemAt(i).widget()
            if w is None or w.isHidden():
                continue
            right = max(right, w.mapTo(vp, QtCore.QPoint(w.width(), 0)).x())
        return self.p.scroll.widget().width(), vp.width(), right


# ------------------------------------------------------------------ R142
class TestR142CaptureWidth(_Shown):

    def fill(self):
        self.fc.add(_Doc("Part", "uid-p", [_Obj("Body")]))
        self.p.add_shot(_png(os.path.join(self.tmp, "v.png")),
                        "Part - Isometric view - 10:00:00")
        self.p.say("Make the walls 1 mm thicker and add four mounting holes",
                   role="user")
        self.p.say(TABLE_ANSWER)

    def test_r142_content_fits_the_viewport_at_900x600(self):
        self.show_at(PANEL_900x600)
        self.fill()
        self.settle()
        content, vpw, right = self.widths()
        self.assertLessEqual(content, vpw, "content wider than the chat")
        self.assertLessEqual(right, vpw, "a card runs past the right edge")
        img = self.p.findChildren(panel.Shot)[0].image
        self.assertIsInstance(img, panel.FitPixmap)
        self.assertLessEqual(img.shown_width(), img.width())
        user = [b for b in self.p.findChildren(panel.Bubble)
                if b.label.objectName() == "UserBubble"][0]
        self.assertLessEqual(user.label.width(), user.width())
        print("\n  [R142] 900x600 (panel %dx%d): content %d, viewport %d, "
              "right edge %d; capture shown %d px in a %d px label"
              % (PANEL_900x600 + (content, vpw, right, img.shown_width(),
                                  img.width())))

    def test_r142_rescales_on_resize(self):
        self.show_at(PANEL_900x600)
        self.fill()
        self.settle()
        img = self.p.findChildren(panel.Shot)[0].image
        narrow = img.shown_width()
        self.p.resize(520, 462)
        self.settle()
        wide = img.shown_width()
        self.assertGreater(wide, narrow, "did not grow with the chat")
        content, vpw, right = self.widths()
        self.assertLessEqual(content, vpw)
        self.assertLessEqual(right, vpw)
        self.p.resize(PANEL_900x600[0], 462)
        self.settle()
        self.assertEqual(img.shown_width(), narrow, "did not shrink back")
        content, vpw, right = self.widths()
        self.assertLessEqual(content, vpw)
        self.assertLessEqual(right, vpw)
        # The height follows the aspect ratio (1200x900 -> 3:4).
        self.assertAlmostEqual(img.heightForWidth(400), 300, delta=1)
        print("\n  [R142] capture %d px at a 300 px panel, %d px at 520 px, "
              "%d px back at 300" % (narrow, wide, img.shown_width()))

    def test_r142_never_scaled_up_past_its_pixels(self):
        small = panel.FitPixmap(QtGui.QPixmap(_png(
            os.path.join(self.tmp, "s.png"), 120, 90)))
        small.resize(400, small.heightForWidth(400))
        self.settle(0.05)
        self.assertEqual(small.shown_width(), 120)
        self.assertEqual(small.heightForWidth(400), 90)


# ------------------------------------------------------------------ R143
class TestR143FirstRun(_Shown):

    def signed_out(self):
        self.patch(engine, "current", lambda: engine.CLAUDE)
        self.p._unavailable_kind = "auth"
        self.p._connected = False
        self.fc.mod.ActiveDocument = None

    def heading_top(self):
        return self.p._empty.findChild(QtWidgets.QLabel, "Hello").mapTo(
            self.p.scroll.viewport(), QtCore.QPoint(0, 0)).y()

    def test_r143_new_chat_with_the_sign_in_notice_opens_at_the_heading(self):
        self.show_at(PANEL_900x600)
        self.signed_out()
        bar = self.p.scroll.verticalScrollBar()
        self.p.new_chat()
        self.settle(0.5)
        self.assertEqual(self.p._empty_kind, "nodoc")
        self.assertIn("Sign in to Claude Code", self.titles())
        self.assertEqual(bar.value(), 0, "scrolled to the bottom")
        self.assertGreaterEqual(self.heading_top(), 0)
        self.assertEqual(self.p._empty.title.text(), "What are we building?")
        # The pills (Sample crane / New / Open) are in view, and so is the
        # notice's Retry, now that the examples made room.
        vp = self.p.scroll.viewport()
        pills = [b for b in self.p._empty.findChildren(QtWidgets.QPushButton)
                 if b.objectName() == "NoticeBtn"]
        self.assertTrue(pills)
        for b in pills:
            self.assertLessEqual(b.mapTo(vp, QtCore.QPoint(0, b.height())).y(),
                                 vp.height(), b.text())
        notice = self.notices()[0]
        retry = [b for b in notice.buttons if b.text() == "Retry"][0]
        retry_bottom = retry.mapTo(vp, QtCore.QPoint(0, retry.height())).y()
        shown = sum(1 for r in self.p._empty.rows if not r.isHidden())
        print("\n  [R143] 900x600 signed out: scroll %d of %d, heading at "
              "y=%d, %d example(s) shown, Retry bottom %d of %d"
              % (bar.value(), bar.maximum(), self.heading_top(), shown,
                 retry_bottom, vp.height()))
        self.assertLessEqual(retry_bottom, vp.height(), "Retry out of reach")

    def test_r143_too_short_for_everything_still_opens_at_the_heading(self):
        # A panel so short that the notice cannot fit under the Welcome
        # even without its examples: the heading wins, scroll 0 (the old
        # code followed the bottom here).
        self.show_at((PANEL_900x600[0], 260))
        self.signed_out()
        bar = self.p.scroll.verticalScrollBar()
        self.p.new_chat()
        self.settle(0.5)
        self.assertGreater(bar.maximum(), 0, "nothing to scroll: no test")
        self.assertEqual(bar.value(), 0)
        self.assertGreaterEqual(self.heading_top(), 0)
        print("\n  [R143] 300x260 signed out: scroll %d of %d"
              % (bar.value(), bar.maximum()))

    def test_r143_connected_keeps_an_example(self):
        self.show_at(PANEL_900x600)
        self.fc.mod.ActiveDocument = None
        self.p._connected = True
        self.p.new_chat()
        self.settle(0.3)
        self.assertGreaterEqual(
            sum(1 for r in self.p._empty.rows if not r.isHidden()), 1)
        self.assertEqual(self.p.scroll.verticalScrollBar().value(), 0)


# ------------------------------------------------------------------ R144
class TestR144FollowOnClose(_Shown):

    def chat_on(self, doc):
        self.p._shown_key = doc.Uid
        self.p._has_messages = True
        self.p._clear_empty()
        self.p.say("a hex key holder", role="user")
        self.p.add_shot(_png(os.path.join(self.tmp, "a.png")), "A view")

    def test_r144_closing_the_document_clears_its_chat(self):
        doc = self.fc.add(_Doc("Atech_Project", "uid-ap", [_Obj("Case")]))
        self.p.refresh_doc_pill(force=True)
        st = panel.ChatState("uid-ap", doc.Name, build.new_workspace())
        self.p._docs["uid-ap"] = st
        self.chat_on(doc)
        self.fc.close(doc)
        self.p.refresh_doc_pill()
        self.assertEqual(self.p.doc_name.text(), "No document")
        self.assertNotIn("a hex key holder", self.bubbles())
        self.assertFalse([s for s in self.p.findChildren(panel.Shot)
                          if not s.isHidden()])
        self.assertEqual(self.p._empty_kind, "nodoc")
        self.assertEqual(self.p._pending_shots, [])
        # The chat itself is kept for when the document comes back.
        self.assertIs(self.p._docs.get("uid-ap"), st)

    def test_r144_the_poll_alone_follows(self):
        doc = self.fc.add(_Doc("A", "uid-a", [_Obj("Box")]))
        self.p.refresh_doc_pill(force=True)
        self.chat_on(doc)
        self.fc.close(doc)
        # No explicit call: the 800 ms document poll does it.
        self.assertTrue(wait_until(
            lambda: "a hex key holder" not in self.bubbles(), 3))
        self.assertEqual(self.p._empty_kind, "nodoc")

    def test_r144_active_document_change(self):
        a = self.fc.add(_Doc("A", "uid-a", [_Obj("Box")]))
        self.p.refresh_doc_pill(force=True)
        self.chat_on(a)
        self.fc.add(_Doc("B", "uid-b", [_Obj("Cyl")]))
        self.p.refresh_doc_pill()
        self.assertNotIn("a hex key holder", self.bubbles())
        self.assertEqual(self.p._shown_key, "uid-b")
        self.assertEqual(self.p._empty_kind, "doc")

    def test_r144_never_mid_turn_then_right_after(self):
        doc = self.fc.add(_Doc("A", "uid-a", [_Obj("Box")]))
        self.p.refresh_doc_pill(force=True)
        self.chat_on(doc)
        self.p._busy = True
        self.fc.close(doc)
        self.p.refresh_doc_pill()
        self.assertIn("a hex key holder", self.bubbles(), "cleared mid-turn")
        self.p._busy = False
        # Same document signature as the last poll: still followed.
        self.p.refresh_doc_pill()
        self.assertNotIn("a hex key holder", self.bubbles())

    def test_r144_same_document_keeps_its_chat(self):
        doc = self.fc.add(_Doc("A", "uid-a", [_Obj("Box")]))
        self.p.refresh_doc_pill(force=True)
        self.chat_on(doc)
        doc.Objects.append(_Obj("Lid"))         # the signature changes
        self.p.refresh_doc_pill()
        self.assertIn("a hex key holder", self.bubbles())


# ------------------------------------------------------------------ R145
class _FaceView(tr5._View):
    def viewIsometric(self):                            # noqa: N802
        self.calls.append(("iso", self.anim))


class TestR145ModuleFace(twp.Case):

    def setUp(self):
        super().setUp()
        import acadagent
        vp = types.ModuleType("acadagent.viewport")
        vp.face = (0.6, 1.0, 0.5)
        vp.looks = []
        vp.module_face_direction = lambda doc: vp.face
        vp.look_from = lambda x, y, z, v=None: \
            vp.looks.append(((x, y, z), v)) or True
        self.vp = vp
        saved = sys.modules.get("acadagent.viewport")
        sys.modules["acadagent.viewport"] = vp
        had, old = hasattr(acadagent, "viewport"), \
            getattr(acadagent, "viewport", None)
        acadagent.viewport = vp

        def restore():
            if saved is not None:
                sys.modules["acadagent.viewport"] = saved
            else:
                sys.modules.pop("acadagent.viewport", None)
            if had:
                acadagent.viewport = old
            else:
                delattr(acadagent, "viewport")
        self.addCleanup(restore)
        self.view = _FaceView()
        gui = types.ModuleType("FreeCADGui")
        gui.ActiveDocument = types.SimpleNamespace(ActiveView=self.view)
        saved_gui = sys.modules.get("FreeCADGui")
        sys.modules["FreeCADGui"] = gui
        self.addCleanup(lambda: sys.modules.__setitem__(
            "FreeCADGui", saved_gui) if saved_gui else
            sys.modules.pop("FreeCADGui", None))

    def test_r145_board_document_asks_for_the_module_face(self):
        self.fc.add(tr5._board(modules=[("light", (3,))]))
        self.assertEqual(vision.views_for(), (capture.MODULE_FACE,))
        self.fc.add(_Doc("Part", "uid-p", [_Obj("Body")]))
        self.assertEqual(vision.views_for(), ("Isometric",))

    def test_r145_capture_turns_to_the_face_not_isometric(self):
        self.fc.add(tr5._board(modules=[("light", (3,))]))
        path = capture.capture(path=os.path.join(self.tmp, "f.png"),
                               view_name=capture.MODULE_FACE)
        self.assertTrue(os.path.isfile(path))
        kinds = [c[0] for c in self.view.calls]
        self.assertNotIn("iso", kinds)
        self.assertEqual(kinds, ["stop", "fit", "save"])
        self.assertEqual(self.vp.looks, [((0.6, 1.0, 0.5), self.view)])
        # The camera sits on the modules' (+Y) side.
        self.assertGreater(self.vp.looks[0][0][1], 0)

    def test_r145_board_without_modules_keeps_the_camera(self):
        self.fc.add(tr5._board())
        self.vp.face = None
        capture.capture(path=os.path.join(self.tmp, "k.png"),
                        view_name=capture.MODULE_FACE)
        self.assertEqual(self.vp.looks, [])
        self.assertNotIn("iso", [c[0] for c in self.view.calls])

    def test_r145_ask_in_chat_on_a_board(self):
        self.fc.add(tr5._board(modules=[("light", (3,))]))
        asked = []

        def fake_c2p(p, view_name=None, **_k):
            asked.append(view_name)
            return None                     # "could not capture": no turn
        self.patch(capture, "capture_to_panel", fake_c2p)
        self.assertFalse(vision.ask_in_chat(panel=self.p))
        self.assertEqual(asked, [capture.MODULE_FACE])


# ------------------------------------------------------------------ R146
class TestR146Polish(twp.Round3):

    def test_r146_empty_document_gets_part_examples(self):
        doc = self.fc.add(_Doc("Unnamed", "uid-e", []))
        self.p.refresh_doc_pill(force=True)
        self.assertEqual(self.p._empty_kind, "empty")
        ps = [r.text() for r in self.p._empty.rows]
        self.assertFalse(any("thicker" in p or "volume and mass" in p
                             for p in ps), ps)
        self.assertIn("Make a 60 x 40 x 20 mm box with 2 mm walls", ps)
        # The first solid swaps in the part examples.
        doc.Objects.append(_Obj("Box"))
        self.p.refresh_doc_pill()
        self.assertEqual(self.p._empty_kind, "doc")
        self.assertIn("Make the walls 1 mm thicker",
                      [r.text() for r in self.p._empty.rows])

    def test_r146_caveat_in_the_warning_colour(self):
        self.viewport()
        st = self.turn_state(doc=self.box_doc())
        res = twp._ok_result()
        res.warning = tr5.TestR127Caveat.CAVEAT
        self.p._settle(st, res, True, None)
        note = self.p._build_card.note
        self.assertEqual(note.objectName(), "ToolWarn")
        note.ensurePolished()
        got = note.palette().color(QtGui.QPalette.WindowText).name()
        self.assertEqual(got, QtGui.QColor(style.tokens()["warn"]).name())
        body = self.p._build_card.body
        body.ensurePolished()
        self.assertNotEqual(
            got, body.palette().color(QtGui.QPalette.WindowText).name())
        print("\n  [R146] caveat colour %s (warn token %s)"
              % (got, style.tokens()["warn"]))


# ------------------------------------------------------------------ R153
def _rendered(label):
    """(bold fragments, QTextTable count) of a rich-text label."""
    doc = QtGui.QTextDocument()
    doc.setHtml(label.text())
    bold = []
    block = doc.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and \
                    frag.charFormat().fontWeight() >= QtGui.QFont.Bold:
                bold.append(frag.text())
            it += 1
        block = block.next()
    tables = [f for f in doc.rootFrame().childFrames()
              if isinstance(f, QtGui.QTextTable)]
    return bold, len(tables)


class TestR153Markdown(twp.Case):

    def test_r153_bubble_renders_bold_and_one_table(self):
        b = panel.Bubble(TABLE_ANSWER, "agent")
        self.assertTrue(b.markdown)
        self.assertEqual(b.label.textFormat(), QtCore.Qt.RichText)
        bold, tables = _rendered(b.label)
        self.assertIn("What it is:", bold)
        self.assertEqual(tables, 1)
        self.assertNotIn("**", b.label.text())

    def test_r153_bold_without_a_table(self):
        # D61: the view answer had **bold** and no table: it stayed raw.
        b = panel.Bubble("**What it is:** a phone stand.\n\n- one part\n"
                         "- no overlap", "agent")
        bold, tables = _rendered(b.label)
        self.assertEqual((bold, tables), (["What it is:"], 0))
        self.assertNotIn("**", b.label.text())

    def test_r153_plain_prose_untouched(self):
        text = "Built a 60 x 40 x 20 mm box.\nVolume 12 345 mm3."
        b = panel.Bubble(text, "agent")
        self.assertFalse(b.markdown)
        self.assertEqual(b.label.text(), text)
        u = panel.Bubble("make it **bold**", "user")
        self.assertEqual(u.label.text(), "make it **bold**")

    def test_r153_single_line_breaks_kept(self):
        # Review: GFM joins single newlines into one paragraph, so
        # "**Volume:** 12\n**Mass:** 3" ran together once rendered.
        b = panel.Bubble("Built the box.\n**Volume:** 12 mm3\n**Mass:** 3 g",
                         "agent")
        doc = QtGui.QTextDocument()
        doc.setHtml(b.label.text())
        self.assertEqual(doc.toPlainText().split("\n"),
                         ["Built the box.", "Volume: 12 mm3", "Mass: 3 g"])
        # Code fences are left alone.
        self.assertEqual(panel.md_hard_breaks("```\nx = 1\ny = 2\n```"),
                         "```\nx = 1\ny = 2\n```")

    def test_r153_table_right_after_a_line_still_a_table(self):
        # Review: Qt's parser needs a blank line before a table; measured
        # 0 tables for "Here:\n| a | b |..." before md_hard_breaks.
        b = panel.Bubble("**Parts**\nHere:\n| part | size |\n|---|---|\n"
                         "| lid | 60 |\nafter", "agent")
        bold, tables = _rendered(b.label)
        self.assertEqual((bold[0], tables), ("Parts", 1))

    def test_r153_html_stays_literal(self):
        b = panel.Bubble("**Use** the <port> field", "agent")
        self.assertIn("&lt;port&gt;", b.label.text())

    def test_r153_ask_about_view_answer_through_the_chat(self):
        self.fc.add(_Doc("Part", "uid-p", [_Obj("Body")]))
        self.fixture([
            {"type": "system", "subtype": "init", "session_id": "s-v"},
            {"type": "result", "subtype": "success", "is_error": False,
             "result": TABLE_ANSWER, "duration_ms": 1000}])

        def fake_c2p(p, view_name=None, **_k):
            path = _png(p.capture_path(), 120, 90)
            p.add_shot(path, view_name)
            return path
        self.patch(capture, "capture_to_panel", fake_c2p)
        self.assertTrue(vision.ask_in_chat(panel=self.p))
        self.assertTrue(self.idle())
        answers = [b for b in self.p.findChildren(panel.Bubble)
                   if b.label.objectName() == "AgentText" and b.markdown]
        self.assertEqual(len(answers), 1)
        bold, tables = _rendered(answers[0].label)
        self.assertIn("What it is:", bold)
        self.assertEqual(tables, 1)
        print("\n  [R153] view answer: bold %r, %d QTextTable" % (bold, tables))


# ------------------------------------------------------------------ S49
def _intent_result(vol=1000.0):
    r = twp._ok_result(vol=vol)
    r.intent_problems = ["overall size: you intended 60 mm, Atelier measured "
                         "50 mm"]
    return r


class TestS49PreviewIntent(twp.Round3):

    def test_s49_intent_only_preview_is_in_progress(self):
        self.viewport()
        st = self.turn_state(doc=self.box_doc())
        failed0 = self.p.stats["previews_failed"]
        self.p._settle(st, _intent_result(), True, "h1")
        card = self.p._build_card
        self.assertEqual(card.status.text(), "preview: in progress")
        self.assertEqual(card.status.objectName(), "StatusIdle")
        self.assertIn("not at the intent.json targets yet", card.body.text())
        self.assertEqual(self.p.stats["previews_failed"], failed0)
        self.assertEqual(self.p._preview_error, "")

    def test_s49_a_real_problem_still_fails_the_preview(self):
        self.viewport()
        st = self.turn_state(doc=self.box_doc())
        r = _intent_result()
        r.measurements[0] = dict(r.measurements[0], valid=False)
        self.p._settle(st, r, True, "h1")
        self.assertEqual(self.p._build_card.status.text(),
                         "preview: check failed")
        self.assertIn("valid=False", self.p._preview_error)

    def test_s49_end_of_turn_still_enforces_intent(self):
        self.viewport()
        st = self.turn_state(doc=self.box_doc())
        self.script(st)
        jobs = []
        self.patch(build, "start", self._counting(_intent_result(), jobs))
        sent = []
        self.patch(self.p, "_send_fix", sent.append)
        self.p._run_build(["model.py"], preview=True)
        self.assertTrue(wait_until(lambda: self.p._pending is None, 3))
        self.assertEqual(self.p._build_card.status.text(),
                         "preview: in progress")
        self.p._applied = build.snapshot(st.ws)
        self.p._on_claude_done("Built a box.", {})
        self.assertTrue(self.idle(5))
        self.assertEqual(len(jobs), 1, "the unchanged script was rebuilt")
        self.assertEqual(self.p._build_card.status.text(), "check failed")
        self.assertEqual(len(sent), 1)
        self.assertIn("you intended 60 mm", sent[0])
        self.assertNotIn("Built a box.", self.bubbles(), "reply not demoted")
        print("\n  [S49] preview 'preview: in progress'; end of turn "
              "'check failed', fix sent (%d build)" % len(jobs))

    def test_s49_met_by_the_final_script(self):
        self.viewport()
        st = self.turn_state(doc=self.box_doc())
        self.script(st)
        jobs = []
        self.patch(build, "start", self._counting(_intent_result(), jobs))
        self.p._run_build(["model.py"], preview=True)
        self.assertTrue(wait_until(lambda: self.p._pending is None, 3))
        self.p._applied = build.snapshot(st.ws)
        self.script(st, "x = 2\n")          # the agent finishes the design
        self.patch(build, "start", self._counting(twp._ok_result(), jobs))
        sent = []
        self.patch(self.p, "_send_fix", sent.append)
        self.p._on_claude_done("Built a box.", {})
        self.assertTrue(self.idle(5))
        self.assertEqual(len(jobs), 2)
        self.assertEqual(self.p._build_card.status.text(), "1 built")
        self.assertEqual(sent, [])
        self.assertIn("Built a box.", self.bubbles())

    @staticmethod
    def _counting(res, jobs):
        def start(*a, **k):
            jobs.append((a, k))
            return build.PendingBuild(res)
        return start


if __name__ == "__main__":
    unittest.main()
