"""WS-CHAT round 8, headless against the REAL AgentPanel (same fakes as
test_ws_chat_panel / round5-7): R174 (the S51 in-progress line fits the
mono card body; its reason is the card's wrapped note), R176 (the Module
face capture is held the way the user holds the camera), R94 (evidence).

R174 MEASURED in a real Studio, offscreen (dist/test-root, window
1600x960, sidebar 380 px, the Studio's own chat panel settling a board +
Light + Case preview whose only failure is the undeclared slide path):
light and dark alike, mono label 318 px wide, sizeHint 311 px (the widest
line is the 46-char "Case ... mm3" measurement, 311 px; the in-progress
line is 297 px; the old 99-char line needed 655 px); status "preview: in
progress"; the explanation in the wrapped note, 60 px tall = its
heightForWidth (nothing cut).

R176 MEASURED first, headless (freecadcmd, board + Light on port 3):
module-face direction (0.6, 1.0, 0.5); the old capture (look_from, world Z
up) had screen-up (-0.20, -0.34, 0.92), the Modules page's board camera
(projects.board_view_rotation, default "port7") screen-up (-0.16, 0.53,
-0.83): dot -0.91, the thumbnail turned ~180 deg against the live view, as
GUI r7_08 showed. Look directions 43 deg apart (dot 0.73), both from the
modules' side.

R176 + R94 then measured in a real Studio, offscreen (dist/test-root, whose
AcadAgent links this repo; QT_QPA_PLATFORM=offscreen, isolated HOME; Light
coloured #ff00ff; 1 in 9 pixels of 1200x900 sampled):
  - Modules-page camera, capture(MODULE_FACE): camera kept (up . live 1.0,
    look . live 1.0); 2 006 magenta px, same box as a plain capture of the
    live view (396,303)-(537,450).
  - from the isometric corner: turned to the module face (look . -face
    1.0), world Z up as before; 2 088 magenta px.
  - from the port7 camera turned 180 deg about Z (the board's back):
    turned to the face, held Z-down (up . live port7 0.84); 2 089 px.
  - R94: the Studio's own AgentPanel._frame on an Atech document after an
    isometric camera (look -0.58, 0.58, -0.58): camera on the module face
    (look . -face 1.0), state.faced True, module in frame.
  - R94 mesh: the car of the speed plan (14 Part::Feature objects) through
    AgentPanel._frame, triangles counted in the scene graph
    (SoGetPrimitiveCountAction): 18 700 at this profile's defaults, 6 548
    after a preview, 23 452 after the final build (0.2 / 20 deg). The
    speed plan's 11 472 -> 6 396 used ViewProviderPartExt's formula at
    0.5 / 28.5 headless; the preview count agrees within 2.4 %.

RUN (the interpreter that ships):
    QT_QPA_PLATFORM=offscreen dist/build/squashfs-root/usr/bin/python \\
        -m unittest addon/AcadAgent/tests/test_ws_chat_round8.py -v
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import test_chat_robustness as tcr  # noqa: E402  (sets HOME, Qt, settings)
import test_ws_chat_panel as twp  # noqa: E402
import test_ws_chat_round5 as tr5  # noqa: E402
import test_ws_chat_round7 as tr7  # noqa: E402

from PySide6 import QtCore, QtWidgets  # noqa: E402

from acadagent import capture, panel, shell, style  # noqa: E402


def _pure_viewport():
    """viewport.py's pure camera math (look_quaternion, rotate), loaded
    under a private name with stand-in FreeCAD/FreeCADGui modules when the
    real ones are absent (this interpreter has none)."""
    import importlib.util
    import types
    stubs = {}
    for name in ("FreeCAD", "FreeCADGui"):
        if name not in sys.modules:
            stubs[name] = sys.modules[name] = types.ModuleType(name)
    try:
        spec = importlib.util.spec_from_file_location(
            "_r8_viewport", os.path.join(os.path.dirname(capture.__file__),
                                         "viewport.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for name in stubs:
            sys.modules.pop(name, None)

wait_until = tcr.wait_until
_Obj = twp._Obj


# ------------------------------------------------------------------ R174
class TestR174InProgressLineFits(twp.Round3):

    def _doc(self):
        d = tr5._board(modules=[("light", (3,))])
        d.Objects.append(_Obj("Case"))
        return self.fc.add(d)

    def _docked(self, width=1600):
        """The panel docked the way shell.py docks it, at the default
        sidebar width (380 px at >= 1000 px windows)."""
        want = shell.sidebar_width_for(width)
        mw = QtWidgets.QMainWindow()
        mw.setCentralWidget(QtWidgets.QWidget())
        dock = QtWidgets.QDockWidget()
        dock.setTitleBarWidget(QtWidgets.QWidget())
        self.p.setMinimumWidth(min(self.p.minimumWidth(), want))
        dock.setWidget(self.p)
        mw.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock)
        mw.resize(width, 960)
        mw.show()
        mw.resizeDocks([dock], [want], QtCore.Qt.Horizontal)

        def undock():
            mw.hide()
            dock.setWidget(None)
            self.p.setParent(None)
            mw.deleteLater()
        self.addCleanup(undock)
        for _ in range(5):
            QtWidgets.QApplication.processEvents()
        return want

    def test_r174_line_fits_the_card_in_both_themes(self):
        self.viewport()
        want = self._docked()
        out = []
        for mode in ("light", "dark"):
            self.patch(style, "mode", lambda m=mode: m)
            self.p.restyle()
            st = self.turn_state(key="uid-mods-" + mode, doc=self._doc())
            self.p._settle(st, tr7._atech_result(tr7.SLIDE_FAIL), True,
                           "h-" + mode)
            card = self.p._build_card
            for _ in range(5):
                QtWidgets.QApplication.processEvents()
            body = card.body
            self.assertEqual(card.status.text(), "preview: in progress")
            self.assertIn(panel.AgentPanel.SLIDE_PROGRESS_LINE, body.text())
            self.assertLessEqual(len(panel.AgentPanel.SLIDE_PROGRESS_LINE),
                                 47, "no longer than the S49 line that fits")
            self.assertFalse(body.wordWrap())
            # The in-progress lines themselves. The whole label's sizeHint
            # also holds the measurement lines (not R174's): this
            # interpreter's DejaVu Sans Mono draws 7.0 px a character (the
            # Studio's 6.6), so the fixture's 46-char "Case ... mm3" line is
            # 329 px here and 311 px in Studio: the whole label is compared
            # in the real Studio instead (module docstring).
            fm = body.fontMetrics()
            mine = [ln for ln in body.text().split("\n")
                    if ln.startswith("in progress:")]
            self.assertTrue(mine)
            widest = max(fm.horizontalAdvance(ln) for ln in mine)
            self.assertLessEqual(widest, body.width(),
                                 "%s: the in-progress line is clipped" % mode)
            # the reason is in the wrapped note, whole
            self.assertFalse(card.note.isHidden())
            self.assertTrue(card.note.wordWrap())
            self.assertIn("slide path is closed", card.note.text())
            self.assertIn("fitted_after", card.note.text())
            self.assertGreaterEqual(card.note.height(),
                                    card.note.heightForWidth(
                                        card.note.width()))
            out.append((mode, widest, body.width(), card.note.width()))
        print("\n  [R174] sidebar %d px; (mode, in-progress line px, label "
              "px, note px): %s" % (want, out))

    def test_r174_note_clears_when_no_longer_in_progress(self):
        self.viewport()
        st = self.turn_state(key="uid-mods", doc=self._doc())
        self.p._settle(st, tr7._atech_result(tr7.SLIDE_FAIL), True, "h1")
        card = self.p._build_card
        self.assertIn("slide path", card.note.text())
        ok = dict(tr7.SLIDE_FAIL, slide_path="PASS")
        self.p._settle(st, tr7._atech_result(ok), True, "h2")
        self.assertIs(self.p._build_card, card)
        self.assertTrue(card.note.isHidden())
        self.assertEqual(card.note.text(), "")

    def test_r174_caveat_kept_beside_the_explanation(self):
        """R127: the no-bwrap caveat stays for the turn; the explanation
        comes and goes with the in-progress result."""
        self.viewport()
        st = self.turn_state(key="uid-mods", doc=self._doc())
        r = tr7._atech_result(tr7.SLIDE_FAIL)
        r.warning = tr5.TestR127Caveat.CAVEAT
        self.p._settle(st, r, True, "h1")
        note = self.p._build_card.note
        self.assertIn("can still read your files", note.text())
        self.assertIn("slide path is closed", note.text())
        ok = dict(tr7.SLIDE_FAIL, slide_path="PASS")
        self.p._settle(st, tr7._atech_result(ok), True, "h2")
        self.assertIn("can still read your files", note.text())
        self.assertNotIn("slide path", note.text())
        self.assertFalse(note.isHidden())


# ------------------------------------------------------------------ R176
# Measured vectors (module docstring): the module-face direction, and the
# (look, up) of the cameras the user can be holding.
FACE = (0.6, 1.0, 0.5)
PORT7 = ((0.1723, -0.6638, -0.7278), (-0.1465, 0.7133, -0.6854))
ISO = ((-0.5774, 0.5774, -0.5774), (-0.4082, 0.4082, 0.8165))
BACK_PORT7 = ((-0.2158, 0.3535, -0.9102), (0.0068, -0.9316, -0.3634))


class TestR176FaceTurn(unittest.TestCase):

    def test_r176_modules_page_camera_is_kept(self):
        self.assertEqual(capture.face_turn(FACE, PORT7), ("keep", None))

    def test_r176_iso_corner_turns_world_z_up(self):
        self.assertEqual(capture.face_turn(FACE, ISO),
                         ("turn", (0.0, 0.0, 1.0)))

    def test_r176_back_with_z_down_turns_z_down(self):
        self.assertEqual(capture.face_turn(FACE, BACK_PORT7),
                         ("turn", (0.0, 0.0, -1.0)))

    def test_r176_unreadable_camera_turns_world_z_up(self):
        self.assertEqual(capture.face_turn(FACE, None),
                         ("turn", (0.0, 0.0, 1.0)))

    def test_r176_threshold(self):
        """43 deg off the face is facing it; 90 deg (edge-on) is not."""
        dn = capture._unit(FACE)
        on = tuple(-c for c in dn)
        self.assertEqual(capture.face_turn(FACE, (on, (0, 0, 1)))[0], "keep")
        edge = capture._unit((dn[1], -dn[0], 0.0))
        self.assertEqual(capture.face_turn(FACE, (edge, (0, 0, 1)))[0],
                         "turn")


class _OrientView(object):
    def __init__(self):
        self.orient = []

    def setCameraOrientation(self, q):                   # noqa: N802
        self.orient.append(q)


class TestR176FaceModules(unittest.TestCase):
    """capture._face_modules with the view's camera axes patched."""

    def setUp(self):
        self.vp = tr7._FakeViewport().install(self, face=FACE)
        self.saved = capture.user_axes
        self.addCleanup(setattr, capture, "user_axes", self.saved)

    def _run(self, axes):
        capture.user_axes = lambda view: axes
        v = _OrientView()
        capture._face_modules(v, FACE)
        return v

    def test_r176_kept_camera_is_not_turned(self):
        v = self._run(PORT7)
        self.assertEqual(v.orient, [])
        self.assertEqual(self.vp.looks, [])

    def test_r176_z_up_goes_through_look_from(self):
        v = self._run(ISO)
        self.assertEqual(v.orient, [])
        self.assertEqual([lk[0] for lk in self.vp.looks], [FACE])

    def test_r176_z_down_is_held_z_down(self):
        viewport = _pure_viewport()
        self.vp.look_quaternion = viewport.look_quaternion
        v = self._run(BACK_PORT7)
        self.assertEqual(self.vp.looks, [])
        self.assertEqual(len(v.orient), 1)
        q = v.orient[0]
        up = viewport.rotate(q, (0.0, 1.0, 0.0))
        look = viewport.rotate(q, (0.0, 0.0, -1.0))
        dn = capture._unit(FACE)
        self.assertAlmostEqual(sum(a * -b for a, b in zip(look, dn)), 1.0,
                               places=6)
        self.assertLess(up[2], -0.9, "screen-up points down world Z")
        # the Modules page's own screen-up, measured: the same way up
        self.assertGreater(sum(a * b for a, b in zip(up, PORT7[1])), 0.8)


if __name__ == "__main__":
    unittest.main()
