"""WS-CHAT round 5, headless against the REAL AgentPanel (same fakes as
test_ws_chat_panel): R127 (no-bwrap caveat on the build card), R132 (the
Welcome fits above the composer at 900x600; it opens at its heading),
R133 (board-aware "Try asking"), R138 (capture without camera animation;
the ask lands in the active document's chat).

RUN (the interpreter that ships):
    QT_QPA_PLATFORM=offscreen dist/build/squashfs-root/usr/bin/python \\
        -m unittest addon/AcadAgent/tests/test_ws_chat_round5.py -v

R138's capture half was also measured in a real Studio (dist/test-root,
QT_QPA_PLATFORM=offscreen, isolated HOME; board + Light on port 3 added
through the Modules page; viewAxonometric + viewRear still animating when
the capture starts; pixels differing > 30 from the gradient's row colour,
1 in 9 sampled of 1200x900): before, Isometric 5 213 / Front 29 992 /
Right 0 / Top 0; after, 21 408 / 35 742 / 3 542 / 2 189.
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

from PySide6 import QtCore, QtWidgets  # noqa: E402

from acadagent import build, capture, panel, shell, vision  # noqa: E402

wait_until = tcr.wait_until
_Doc, _Obj = twp._Doc, twp._Obj

#: The chat panel's height in a 900x600 Studio window. MEASURED on
#: shots/r4_42_small_chat.png (the GUI pass of round 4): the panel runs from
#: y=110 (under the Chat/Model/Modules tabs) to y=572 (above the status
#: bar), 462 px, in a 300 px sidebar (shell.sidebar_width_for(900)).
PANEL_900x600 = (shell.sidebar_width_for(900), 462)


def _board(name="Mods", uid="uid-mods", modules=()):
    b = _Obj("motherboard", typeid="Mesh::Feature", shape=False)
    b.AtechRole = "board"
    objs = [b]
    for mod, ports in modules:
        m = _Obj("%s_p%s" % (mod, ports[0]), typeid="Mesh::Feature",
                 shape=False)
        m.AtechRole = "module"
        m.AtechModule = mod
        m.AtechPorts = list(ports)
        objs.append(m)
    return _Doc(name, uid, objs)


# ------------------------------------------------------------------ R127
class TestR127Caveat(twp.Round3):

    CAVEAT = ("Designs are built without bubblewrap (bwrap) here: the design "
              "script has no network and a scratch home folder, but it can "
              "still read your files by their full path. Install bubblewrap "
              "to hide them.")

    def test_r127_warning_reaches_the_card_and_stays(self):
        self.viewport()
        st = self.turn_state(doc=self.box_doc())
        res = twp._ok_result()
        res.warning = self.CAVEAT
        self.p._settle(st, res, True, None)
        card = self.p._build_card
        self.assertFalse(card.note.isHidden())
        self.assertIn("can still read your files", card.note.text())
        self.assertTrue(card.note.wordWrap(), "a sentence wraps, not clips")
        # The warning is set once per session per mode (build.
        # isolation_warning): the next preview of the turn has none, and
        # the card keeps saying it.
        self.p._settle(st, twp._ok_result(vol=2000.0), True, None)
        self.assertIs(self.p._build_card, card)
        self.assertIn("can still read your files", card.note.text())
        print("\n  [R127] card note: %r" % card.note.text()[:70])

    def test_r127_no_warning_no_note(self):
        self.viewport()
        st = self.turn_state(doc=self.box_doc())
        self.p._settle(st, twp._ok_result(), False, None)
        self.assertTrue(self.p._build_card.note.isHidden())

    def test_r127_isolation_warning_is_what_sets_it(self):
        # The producer, measured: once per mode, "" after, None for bwrap.
        saved = set(build._WARNED)
        build._WARNED.clear()
        try:
            first = build.isolation_warning("unshare")
            again = build.isolation_warning("unshare")
            self.assertIn("bubblewrap", first)
            self.assertEqual(again, "")
            self.assertEqual(build.isolation_warning("bwrap"), "")
        finally:
            build._WARNED.clear()
            build._WARNED.update(saved)


# ------------------------------------------------------------------ R132
class TestR132Fit(twp.Round3):

    def _show(self, size):
        w, h = size
        self.p.setMinimumWidth(min(self.p.minimumWidth(), w))    # shell.py
        self.p.resize(w, h)
        self.p.show()
        for _ in range(5):
            tcr.APP.processEvents()
        self.addCleanup(self.p.hide)

    def _settle(self):
        wait_until(lambda: False, 0.25)

    def _measure(self):
        """(cards shown, bottom of the last shown card, viewport height,
        title top, scroll value) in viewport coordinates."""
        w = self.p._empty
        vp = self.p.scroll.viewport()
        shown = [r for r in w.rows if not r.isHidden()]
        last = shown[-1]
        bottom = last.mapTo(vp, QtCore.QPoint(0, last.height())).y()
        top = w.findChild(QtWidgets.QLabel, "Hello").mapTo(
            vp, QtCore.QPoint(0, 0)).y()
        return (len(shown), bottom, vp.height(), top,
                self.p.scroll.verticalScrollBar().value())

    def _assert_fits(self, tag):
        n, bottom, vh, top, val = self._measure()
        self.assertGreaterEqual(n, 1, tag)
        self.assertLessEqual(bottom, vh, "%s: last card cut off at the "
                             "composer (%d > %d)" % (tag, bottom, vh))
        self.assertGreaterEqual(top, 0, "%s: heading scrolled away" % tag)
        self.assertEqual(val, 0, tag)
        return n, bottom, vh

    def test_r132_every_welcome_fits_at_900x600(self):
        out = []
        self._show(PANEL_900x600)
        docs = [None, _Doc("Part", "uid-p", [_Obj("Body")]), _board(),
                _board("Mods2", "uid-m2", [("light", (3,))])]
        for doc in docs:
            if doc is not None:
                self.fc.add(doc)
            else:
                self.fc.mod.ActiveDocument = None
            self.p.refresh_doc_pill(force=True)
            self._settle()
            kind = self.p._empty_kind
            n, bottom, vh = self._assert_fits(str(kind))
            out.append((kind if isinstance(kind, str) else kind[0], n,
                        bottom, vh, self.p._empty.compact))
        print("\n  [R132] 900x600 (panel %dx%d): (welcome, cards shown, "
              "last card bottom, space above the composer, compact) %s"
              % (PANEL_900x600 + (out,)))

    def test_r132_tall_window_shows_all_three(self):
        self._show((PANEL_900x600[0], 900))
        self.fc.add(_Doc("Part", "uid-p", [_Obj("Body")]))
        self.p.refresh_doc_pill(force=True)
        self._settle()
        n, _b, _v = self._assert_fits("tall")
        self.assertEqual(n, 3)
        self.assertFalse(self.p._empty.compact)
        # And back: shrinking refits, growing restores.
        self.p.resize(PANEL_900x600[0], 400)
        self._settle()
        self._assert_fits("shrunk")
        self.p.resize(PANEL_900x600[0], 900)
        self._settle()
        self.assertEqual(self._measure()[0], 3)

    def test_r132_closing_the_document_shows_the_heading(self):
        # A panel so short that even the compact Welcome scrolls: the old
        # _add scrolled to the bottom, the heading out of sight.
        self._show((PANEL_900x600[0], 300))
        doc = self.fc.add(_Doc("Part", "uid-p", [_Obj("Body")]))
        self.p.refresh_doc_pill(force=True)
        self._settle()
        bar = self.p.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())             # the user scrolled down
        self.fc.close(doc)
        self.p.refresh_doc_pill(force=True)
        self._settle()
        self.assertEqual(self.p._empty_kind, "nodoc")
        w = self.p._empty
        top = w.findChild(QtWidgets.QLabel, "Hello").mapTo(
            self.p.scroll.viewport(), QtCore.QPoint(0, 0)).y()
        self.assertEqual(bar.value(), 0)
        self.assertGreaterEqual(top, 0)
        print("\n  [R132] after closing the document: scroll %d of %d, "
              "heading at y=%d" % (bar.value(), bar.maximum(), top))


# ------------------------------------------------------------------ R133
class TestR133BoardExamples(twp.Round3):

    def prompts(self):
        return [r.text() for r in self.p._empty.rows]

    def test_r133_board_document(self):
        self.fc.add(_board())
        self.p.refresh_doc_pill(force=True)
        self.assertEqual(self.p._empty_kind, "board")
        ps = self.prompts()
        self.assertFalse(any("walls" in p for p in ps), ps)
        self.assertTrue(all("board" in p or "module" in p for p in ps), ps)

    def test_r133_names_the_seated_modules_and_follows_them(self):
        doc = self.fc.add(_board(modules=[("light", (3,))]))
        self.p.refresh_doc_pill(force=True)
        self.assertEqual(self.p._empty_kind, ("modules", ("light",)))
        self.assertIn("over the light", self.prompts()[0])
        # Seating a second module swaps the examples while the transcript
        # is empty.
        b = _board(modules=[("button", (5,))]).Objects[1]
        doc.Objects.append(b)
        self.p.refresh_doc_pill()
        self.assertEqual(self.p._empty_kind,
                         ("modules", ("light", "button")))
        self.assertIn("over the light and the button", self.prompts()[0])
        # Clicking an example fills the input (R73).
        self.p._empty.rows[1].click()
        self.assertEqual(self.p.input.toPlainText(), self.prompts()[1])
        print("\n  [R133] board + light + button: %s" % self.prompts())

    def test_r133_plain_document_keeps_the_part_examples(self):
        self.fc.add(_Doc("Part", "uid-p", [_Obj("Body")]))
        self.p.refresh_doc_pill(force=True)
        self.assertEqual(self.p._empty_kind, "doc")
        self.assertIn("Make the walls 1 mm thicker", self.prompts())


# ------------------------------------------------------------------ R138
class _View(object):
    """A 3D view that animates standard-view turns unless told not to, and
    records the animation state at every call capture() makes."""

    def __init__(self, fail_save=False):
        self.anim = True
        self.calls = []
        self.fail_save = fail_save

    def isAnimationEnabled(self):                       # noqa: N802
        return self.anim

    def setAnimationEnabled(self, on):                  # noqa: N802
        self.anim = bool(on)

    def stopAnimating(self):                            # noqa: N802
        self.calls.append(("stop", self.anim))

    def viewIsometric(self):                            # noqa: N802
        self.calls.append(("iso", self.anim))

    def fitAll(self):                                   # noqa: N802
        self.calls.append(("fit", self.anim))

    def saveImage(self, path, w, h, bg):                # noqa: N802
        self.calls.append(("save", self.anim))
        if self.fail_save:
            raise RuntimeError("no GL")
        with open(path, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n" + b"0" * 32)


class TestR138Capture(twp.Case):

    def _gui(self, view):
        gui = types.ModuleType("FreeCADGui")
        gui.ActiveDocument = types.SimpleNamespace(ActiveView=view)
        saved = sys.modules.get("FreeCADGui")
        sys.modules["FreeCADGui"] = gui
        self.addCleanup(lambda: sys.modules.__setitem__("FreeCADGui", saved)
                        if saved else sys.modules.pop("FreeCADGui", None))

    def test_r138_no_animation_while_pointing_fitting_saving(self):
        v = _View()
        self._gui(v)
        path = os.path.join(self.tmp, "iso.png")
        self.assertEqual(capture.capture(path=path), path)
        kinds = [c[0] for c in v.calls]
        self.assertEqual(kinds, ["stop", "iso", "fit", "save"])
        self.assertTrue(all(not on for _k, on in v.calls), v.calls)
        self.assertTrue(v.anim, "the user's setting is restored")

    def test_r138_restored_when_the_save_fails(self):
        v = _View(fail_save=True)
        self._gui(v)
        with self.assertRaises(capture.CaptureError):
            capture.capture(path=os.path.join(self.tmp, "x.png"))
        self.assertTrue(v.anim)

    def test_r138_user_setting_off_stays_off(self):
        v = _View()
        v.anim = False
        self._gui(v)
        capture.capture(path=os.path.join(self.tmp, "y.png"))
        self.assertFalse(v.anim)


class TestR138ActiveDocChat(twp.Case):

    def _fake_capture(self):
        shots = []

        def fake_c2p(p, view_name=None, **_k):
            path = p.capture_path()
            with open(path, "wb") as fh:
                fh.write(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
            p.add_shot(path, view_name)
            shots.append(path)
            return path
        self.patch(capture, "capture_to_panel", fake_c2p)
        return shots

    def test_r138_ask_lands_in_the_active_documents_chat(self):
        hex_doc = self.fc.add(_Doc("HexKeys", "uid-hex", [_Obj("Keys")]))
        os.environ["FAKE_SID"] = "sid-hex"
        self.send("a hex key holder")
        self.assertTrue(self.idle())
        hex_state = self.p._docs["uid-hex"]
        self.assertIn("a hex key holder", self.bubbles())
        # A leftover "Add view" of the HexKeys chat, not yet sent.
        stale = self.p.capture_path()
        with open(stale, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
        self.p.add_shot(stale, "HexKeys")
        self.assertIn(stale, self.p._pending_shots)

        mods = self.fc.add(_board())                # the user moves on
        self.assertIsNot(self.fc.mod.ActiveDocument, hex_doc)
        shots = self._fake_capture()
        os.environ["FAKE_SID"] = "sid-mods"
        self.assertTrue(vision.ask_in_chat(panel=self.p))
        self.assertTrue(self.idle())

        mods_state = self.p._docs[mods.Uid]
        t = self.turns()[-1]
        self.assertEqual(t["cwd"], mods_state.ws)
        self.assertNotIn("--resume", t["argv"], "not HexKeys' session")
        self.assertEqual(os.path.dirname(shots[0]), mods_state.ws)
        self.assertIn(shots[0], t["stdin"])
        self.assertNotIn(stale, t["stdin"], "the other chat's capture")
        # The transcript on screen is Mods' chat now.
        self.assertNotIn("a hex key holder", self.bubbles())
        self.assertIn(vision.DEFAULT_QUESTION, self.bubbles())
        self.assertEqual(self.p._shown_key, mods.Uid)
        # HexKeys keeps its own chat: workspace and Claude session.
        self.assertIs(self.p._docs["uid-hex"], hex_state)
        self.assertEqual(hex_state.sid, "sid-hex")
        self.assertEqual(mods_state.sid, "sid-mods")
        print("\n  [R138] ask on Mods: cwd=%s (Mods' chat), HexKeys sid kept"
              % os.path.basename(t["cwd"]))

    def test_r138_same_document_keeps_its_transcript(self):
        self.fc.add(_Doc("Part", "uid-same", [_Obj("Body")]))
        self.send("a box")
        self.assertTrue(self.idle())
        self._fake_capture()
        self.assertTrue(vision.ask_in_chat(panel=self.p))
        self.assertTrue(self.idle())
        self.assertIn("a box", self.bubbles())

    def test_r138_first_chat_without_a_document_keeps_its_transcript(self):
        # No document: the chat builds into a new one (rekeyed, R17). The
        # transcript is still that chat's.
        self.p._shown_key = panel.NO_DOC
        self.p._has_messages = True
        st = panel.ChatState(panel.NO_DOC, None, build.new_workspace())
        self.p._docs[panel.NO_DOC] = st
        doc = self.fc.add(_Doc("Unnamed", "uid-new"))
        self.p._rekey(st, doc.Name)
        self.assertEqual(self.p._shown_key, "uid-new")
        self.assertFalse(self.p._follow_active_doc())

    def test_r138_never_mid_turn(self):
        self.fc.add(_Doc("A", "uid-a"))
        self.p._shown_key = "uid-a"
        self.p._has_messages = True
        self.p.say("hello", role="user")
        self.fc.add(_Doc("B", "uid-b"))
        self.p._busy = True
        try:
            self.assertFalse(self.p._follow_active_doc())
            self.assertIn("hello", self.bubbles())
        finally:
            self.p._busy = False

    def test_r138_view_of_the_active_doc_queued_mid_turn_is_kept(self):
        # A view of B captured while A's turn ran was queued behind that
        # turn. B's next message clears A's transcript but keeps B's view.
        self.fc.add(_Doc("A", "uid-a"))
        self.p._shown_key = "uid-a"
        self.p._has_messages = True
        self.p.say("hello", role="user")
        a_view = self.p.capture_path()
        with open(a_view, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
        self.p.add_shot(a_view, "A view")
        self.fc.add(_Doc("B", "uid-b"))
        self.p._busy = True
        try:
            b_view = self.p.capture_path()
            with open(b_view, "wb") as fh:
                fh.write(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
            self.p.add_shot(b_view, "B view")
        finally:
            self.p._busy = False
        self.assertTrue(self.p._follow_active_doc())
        self.assertEqual(self.p._pending_shots, [b_view])
        self.assertNotIn("hello", self.bubbles())
        shots = [w for w in self.p.findChildren(panel.Shot)
                 if not w.isHidden()]
        self.assertEqual(len(shots), 1)


if __name__ == "__main__":
    unittest.main()
