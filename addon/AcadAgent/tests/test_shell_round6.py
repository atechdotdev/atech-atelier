"""Round-6 WS-SHELL items R148 and R155, headless.

    R148  the round-5 GUI-pass fix in shell.py: FreeCAD's style sheet reload
          re-shows a closed document's dead MDI sub-window AFTER restyle()
          has returned, so restyle() queues one more hide
          (QTimer.singleShot(0, _hide_dead_subwindows)), and a reload that
          keeps the mode (no restyle at all) is caught by
          _on_window_event(). Each path is checked on its own with the other
          switched off, and each has a sabotage case built from the shipped
          source with the fix line removed. The deferred pass must also be
          harmless once the main window is gone.
    R155  a tilted Atech board is framed from the module side: in the real
          bundled freecadcmd, with the real board and two seated modules,
          module_face_direction() gives a camera that looks AGAINST the
          module normal (dot < 0) at 0, +-15, 90, -90 and 165 deg. The
          sabotage run (placement ignored: the old world-box rule) looks at
          the back at -15 and 165 deg - measured, the D50 regression shape.
          The same holds when the tilt is on an App::Part holding the board
          and modules (review: before the global placement was used, 165
          deg in a Part looked at the back).

    QT_QPA_PLATFORM=offscreen dist/build/squashfs-root/usr/bin/python \\
        -m unittest discover -s addon/AcadAgent/tests -p 'test_shell_round6.py' -v
"""
import inspect
import json
import os
import subprocess
import tempfile
import textwrap
import types
import unittest

import _shell_fakes as F
from PySide6 import QtCore, QtWidgets

from test_shell_lifecycle import ShellCase

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
PROJECTS = os.path.normpath(os.path.join(ADDON, "..", "..", "projects"))
DEFER = "QTimer.singleShot(0, _hide_dead_subwindows)"


def _without_line(func, needle):
    """`func` recompiled with every source line containing `needle` removed:
    the sabotage build of a fix, from the shipped source, not a copy."""
    src = textwrap.dedent(inspect.getsource(func))
    kept = [ln for ln in src.splitlines() if needle not in ln]
    assert len(kept) < len(src.splitlines()), "sabotage removed nothing"
    ns = {}
    exec("\n".join(kept), func.__globals__, ns)        # noqa: S102
    return ns[func.__name__]


def _alive(obj):
    import shiboken6
    return shiboken6.isValid(obj)


# ------------------------------------------------------------------ R148
class _DeadCase(ShellCase):
    def setUp(self):
        super().setUp()
        self.mdi = self.mw.centralWidget()
        self.live = self.mdi.subWindowList()[0]
        self.orig_restyle = self.shell.restyle
        self.orig_event = self.shell._on_window_event

    def tearDown(self):
        self.shell.restyle = self.orig_restyle
        self.shell._on_window_event = self.orig_event
        super().tearDown()

    def dead(self, show=True):
        """FreeCAD's leftover: a widgetless QMdiSubWindow child of the MDI
        viewport, out of subWindowList()."""
        d = QtWidgets.QMdiSubWindow(self.mdi.viewport())
        d.setGeometry(0, 0, 400, 300)
        if show:
            d.show()
        self.assertIsNone(d.widget())
        self.assertNotIn(d, self.mdi.subWindowList(), "precondition")
        return d


class TestRestyleDeferredPass(_DeadCase):
    """The reload re-shows the dead sub-window after restyle() returned:
    only the deferred pass can hide it before the 3 s safety tick. The
    event path is switched off so this checks restyle() alone."""

    def reload_after_restyle(self):
        self.shell.install()
        F.pump(30)
        self.shell._S["watch"].unwatch_all()       # isolate restyle()
        d = self.dead(show=False)
        self.shell.restyle()
        d.show()                   # Std_ReloadStyleSheet, after restyle()
        self.assertTrue(d.isVisible(), "precondition: re-shown after restyle")
        F.pump(30)                 # well under the 3 s tick
        return d

    def test_hidden_on_the_next_loop_pass_never_deleted(self):
        d = self.reload_after_restyle()
        self.assertTrue(_alive(d), "FreeCAD's object was deleted")
        self.assertFalse(d.isVisible())
        self.assertTrue(self.live.isVisible(), "a live sub-window was hidden")

    def test_a_subwindow_holding_a_view_survives_the_deferred_pass(self):
        self.shell.install()
        F.pump(30)
        held = QtWidgets.QMdiSubWindow(self.mdi.viewport())
        held.setWidget(QtWidgets.QLabel("view"))
        self.shell.restyle()
        held.show()
        F.pump(30)
        self.assertTrue(held.isVisible())

    def test_sabotage_without_the_deferred_pass_it_stays_visible(self):
        self.shell.restyle = _without_line(self.orig_restyle, DEFER)
        d = self.reload_after_restyle()
        print("\nR148 sabotage (no deferred pass): dead visible=%s"
              % d.isVisible())
        self.assertTrue(d.isVisible(), "the deferred pass is not load-bearing")


class TestWindowEventPass(_DeadCase):
    """A reload that keeps the mode runs no restyle(): the StyleChange on
    the main window is what hides the dead sub-window."""

    def reload_keeping_mode(self):
        self.shell.install()
        F.pump(30)
        calls = []
        self.shell.restyle = lambda: calls.append(1)
        d = self.dead()
        APP.sendEvent(self.mw, QtCore.QEvent(QtCore.QEvent.StyleChange))
        F.pump(30)
        self.assertEqual(calls, [], "precondition: the mode did not change")
        return d

    def test_style_change_without_restyle_hides_it(self):
        d = self.reload_keeping_mode()
        self.assertTrue(_alive(d))
        self.assertFalse(d.isVisible())
        self.assertTrue(self.live.isVisible())

    def test_sabotage_without_the_event_hide_it_stays_visible(self):
        # the watcher binds the callback at install(): patch before it
        self.shell._on_window_event = _without_line(
            self.orig_event, "_hide_dead_subwindows()")
        d = self.reload_keeping_mode()
        print("\nR148 sabotage (no event hide): dead visible=%s"
              % d.isVisible())
        self.assertTrue(d.isVisible(), "the event hide is not load-bearing")


class TestDeferredPassAfterTeardown(unittest.TestCase):
    """restyle()'s queued pass may fire after the window is destroyed."""

    def setUp(self):
        import shiboken6
        self.mw = F.build_main_window()
        self.fc, self.gui = F.install_fakes(self.mw)
        from acadagent import shell
        self.shell = shell
        shiboken6.delete(self.mw)
        self.assertFalse(_alive(self.mw), "precondition")

    def test_a_dead_main_window_is_zero_not_an_error(self):
        self.assertEqual(self.shell._hide_dead_subwindows(), 0)

    def test_sabotage_unguarded_lookup_raises(self):
        src = textwrap.dedent(inspect.getsource(
            self.shell._hide_dead_subwindows))
        old = ("    try:\n        mw = _mw()\n"
               "        mdi = mw.centralWidget() if mw is not None else None\n")
        assert old in src
        src = src.replace(old, "    mw = _mw()\n    mdi = mw.centralWidget()\n"
                               "    try:\n")
        ns = {}
        exec(src, self.shell._hide_dead_subwindows.__globals__, ns)  # noqa: S102
        with self.assertRaises(RuntimeError):
            ns["_hide_dead_subwindows"]()


# ------------------------------------------------------------------ R155
def _find_freecadcmd():
    try:
        from acadagent import sandbox
        return sandbox.find_freecadcmd()
    except Exception:                                  # noqa: BLE001
        return None


FC = _find_freecadcmd()

# Runs INSIDE freecadcmd (exit 0 even on an exception: explicit markers).
_FC_SCRIPT = r'''
import json, os, sys, traceback
sys.path.insert(0, %(projects)r)
sys.path.insert(0, %(addon)r)
try:
    import FreeCAD as App
    from FreeCAD import Vector, Placement, Rotation
    import atech_ports as ap
    from acadagent import viewport as vp
    sab = os.environ.get("R155_SABOTAGE")
    if sab == "1":
        vp._local_frame = lambda o: None               # the pre-R155 rule
    elif sab == "2":                                   # containers ignored
        vp._global_placement = lambda o: getattr(o, "Placement", None)
    in_part = os.environ.get("R155_IN_PART") == "1"
    out = []
    for deg in (0, 15, -15, 90, -90, 165):
        doc = App.newDocument("R155_%%d" %% (deg + 180))
        board = ap.board_object(doc)
        tilt = Placement(Vector(0, 0, 0), Rotation(Vector(1, 0, 0), deg))
        if not in_part:
            board.Placement = tilt
        mods = [ap.seat(doc, "temp_humidity", 3),
                ap.seat(doc, "screen", (9, 10))]
        # the tilt on the board's own Placement, or on an App::Part that
        # holds the board and its modules (their own placements unchanged)
        parent = Placement()
        if in_part:
            part = doc.addObject("App::Part", "Stand")
            for o in [board] + mods:
                part.addObject(o)
            part.Placement = tilt
            parent = tilt
        doc.recompute()
        # The module normal, measured WITHOUT the code under test: the unit
        # board-centre -> module-centre offset along the board's thinnest
        # local axis, turned by the placement (the Part's, composed by hand
        # here). Local frame: the board mesh with its placement removed.
        local = board.Mesh.copy(); local.Placement = Placement()
        lb = local.BoundBox
        ext = (lb.XLength, lb.YLength, lb.ZLength)
        k = min(range(3), key=lambda i: ext[i])
        e = [0.0, 0.0, 0.0]; e[k] = 1.0
        world = parent.multiply(board.Placement)
        n = world.Rotation.multVec(Vector(*e))
        bc = world.multVec(lb.Center)
        mc = sum((parent.multVec(m.Mesh.BoundBox.Center) for m in mods),
                 Vector()) * 0.5
        if (mc - bc).dot(n) < 0:
            n = -n
        face = vp.module_face_direction(doc)
        look = None
        if face is not None:
            # the camera's own view direction: what look_from() sets
            q = vp.look_quaternion((-face[0], -face[1], -face[2]))
            view = vp.rotate(q, (0.0, 0.0, -1.0))
            look = view[0] * n.x + view[1] * n.y + view[2] * n.z
        out.append({"deg": deg, "normal": [n.x, n.y, n.z], "face": face,
                    "look_dot_normal": look})
        App.closeDocument(doc.Name)
    print("R155_RESULT=" + json.dumps(out))
except Exception:
    traceback.print_exc()
    print("R155_ERROR")
'''


def _run_fc(sabotage=False, in_part=False):
    fd, path = tempfile.mkstemp(suffix="_r155.py")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(_FC_SCRIPT % {"projects": PROJECTS, "addon": ADDON})
    try:
        env = dict(os.environ, R155_SABOTAGE=str(int(sabotage)),
                   R155_IN_PART="1" if in_part else "0")
        env.pop("QT_QPA_PLATFORM", None)
        p = subprocess.run([FC, path], env=env, capture_output=True,
                           text=True, timeout=300, cwd=tempfile.gettempdir())
    finally:
        os.unlink(path)
    text = (p.stdout + p.stderr).replace("\r", "\n")
    for line in text.splitlines():
        if line.startswith("R155_RESULT="):
            return json.loads(line[len("R155_RESULT="):])
    raise AssertionError("freecadcmd gave no result:\n" + text[-3000:])


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class TestTiltedBoardFace(unittest.TestCase):
    """One freecadcmd child at a time (repo rule)."""

    @classmethod
    def setUpClass(cls):
        cls.rows = _run_fc()

    def test_camera_looks_against_the_module_normal_at_every_tilt(self):
        for r in self.rows:
            print("\nR155 deg=%4d normal=(%.3f,%.3f,%.3f) face=%s dot=%s"
                  % (r["deg"], *r["normal"], r["face"], r["look_dot_normal"]))
        bad = [r["deg"] for r in self.rows
               if r["look_dot_normal"] is None or r["look_dot_normal"] >= 0]
        self.assertEqual(bad, [], "camera behind the modules at these tilts")
        self.assertEqual(sorted(r["deg"] for r in self.rows),
                         [-90, -15, 0, 15, 90, 165])

    def test_upright_and_flat_boards_keep_the_old_direction(self):
        by = {r["deg"]: r["face"] for r in self.rows}
        self.assertEqual(tuple(by[0]), (0.6, 1.0, 0.5))
        self.assertEqual(tuple(by[90]), (0.6, -0.6, 1.0))
        self.assertEqual(tuple(by[-90]), (0.6, -0.6, -1.0))

    def test_sabotage_world_box_rule_looks_at_the_back(self):
        rows = _run_fc(sabotage=True)
        bad = sorted(r["deg"] for r in rows
                     if r["look_dot_normal"] is None
                     or r["look_dot_normal"] >= 0)
        print("\nR155 sabotage (placement ignored): back view at %s" % bad)
        self.assertIn(-15, bad, "the placement is not load-bearing")


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class TestTiltedPartFace(unittest.TestCase):
    """R155 review: the tilt on an App::Part holding the board and its
    modules (atech_ports supports meshes in a moved Part). The board's own
    Placement is identity and its Mesh is in the Part's frame, so only the
    GLOBAL placement says which way it faces."""

    @classmethod
    def setUpClass(cls):
        cls.rows = _run_fc(in_part=True)

    def test_camera_looks_against_the_module_normal_in_a_tilted_part(self):
        for r in self.rows:
            print("\nR155 part deg=%4d normal=(%.3f,%.3f,%.3f) face=%s dot=%s"
                  % (r["deg"], *r["normal"], r["face"], r["look_dot_normal"]))
        bad = [r["deg"] for r in self.rows
               if r["look_dot_normal"] is None or r["look_dot_normal"] >= 0]
        self.assertEqual(bad, [], "camera behind the modules at these tilts")

    def test_sabotage_own_placement_only_looks_at_the_back(self):
        rows = _run_fc(sabotage=2, in_part=True)
        bad = sorted(r["deg"] for r in rows
                     if r["look_dot_normal"] is None
                     or r["look_dot_normal"] >= 0)
        print("\nR155 part sabotage (containers ignored): back view at %s"
              % bad)
        self.assertIn(165, bad, "the global placement is not load-bearing")


class TestFaceDirectionFakes(unittest.TestCase):
    """Console stand-ins (no Placement): the world-box rule still applies."""

    def setUp(self):
        F.install_fakes(QtWidgets.QMainWindow())
        from acadagent import viewport
        self.vp = viewport

    def obj(self, role, lo, hi):
        bb = types.SimpleNamespace(XMin=lo[0], YMin=lo[1], ZMin=lo[2],
                                   XMax=hi[0], YMax=hi[1], ZMax=hi[2])
        shape = types.SimpleNamespace(BoundBox=bb, isNull=lambda: False)
        return types.SimpleNamespace(AtechRole=role, Shape=shape)

    def test_no_placement_falls_back_to_world_bounds(self):
        doc = types.SimpleNamespace(Objects=[
            self.obj("board", (0, 0, 0), (100, 3, 60)),
            self.obj("module", (10, -20, 10), (40, -3, 40))])
        self.assertIsNone(self.vp._local_frame(doc.Objects[0]))
        self.assertEqual(self.vp.module_face_direction(doc), (0.6, -1.0, 0.5))


if __name__ == "__main__":
    unittest.main()
