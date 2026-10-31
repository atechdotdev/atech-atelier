"""R810/R811: the user, 2026-10-28: "make the logo go back to home page;
make the exploded view easier to navigate; have a button to create an
assemble video; have a button for creating simulation".

  TestFreeCAD   fc_view_tools_r810.py under freecadcmd + offscreen Qt, on a
                real document: the exploded view keeps the board, cables
                and cabled modules still, slides a seated module out of its
                port, stacks parts in layers; its card opens whenever the
                design is apart, steps through the parts, switches mode and
                puts every part back; Simulate finds the motor, the wheel
                and the tyre it turns (not the body), the light and the
                sensor, turns only those about the shaft, is put back by a
                save / an exploded view, writes a URDF (one continuous
                joint, unique geom names, valid binary STLs, masses); the
                video button calls the panel's make_video. Two sabotage
                runs (no coaxial parts, cables exploded) must fail.
  TestHome      the logo always goes Home (a second click no longer takes
                you back into the project); the top bar's logo too.
  TestRegistry  Simulate and Make assembly video are view-bar tools.

    cd addon/AcadAgent/tests
    python3 -m unittest -v test_view_tools_r810    (TestFreeCAD)
    QT_QPA_PLATFORM=offscreen /Applications/FreeCAD.app/Contents/Resources/bin/python \\
        -m unittest -v test_view_tools_r810          (all, with PySide6)
"""
import inspect
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
if ADDON not in sys.path:
    sys.path.insert(0, ADDON)

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets
    APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
except ImportError:
    QtWidgets = None


def _fc():
    try:
        from acadagent import sandbox
        return sandbox.find_freecadcmd()
    except Exception:                                      # noqa: BLE001
        return os.environ.get("ATECH_FREECADCMD")


FC = _fc()


def _run(sabotage=""):
    home = tempfile.mkdtemp(prefix="atech-r810-")
    env = {"HOME": home, "FREECAD_USER_HOME": home, "PATH": "/usr/bin:/bin",
           "QT_QPA_PLATFORM": "offscreen", "R810_ADDON": ADDON,
           "R810_SABOTAGE": sabotage}
    if os.environ.get("ATELIER_MUJOCO_DIR"):       # R813: a real physics run too
        env["ATELIER_MUJOCO_DIR"] = os.environ["ATELIER_MUJOCO_DIR"]
    p = subprocess.run([FC, os.path.join(HERE, "fc_view_tools_r810.py")], env=env,
                       cwd=home, capture_output=True, text=True, timeout=300)
    line = [ln for ln in (p.stdout + p.stderr).splitlines()
            if ln.startswith("VIEW_TOOLS_RESULT=")]
    if not line:
        raise AssertionError((p.stdout + p.stderr)[-2000:])
    return json.loads(line[-1].split("=", 1)[1])


@unittest.skipIf(FC is None, "freecadcmd not found (set ATECH_FREECADCMD)")
class TestFreeCAD(unittest.TestCase):
    def test_all_checks(self):
        r = _run()
        failed = [k for k, v in r["checks"].items() if not v]
        self.assertTrue(r["ok"], (failed, r["errors"]))
        self.assertGreaterEqual(len(r["checks"]), 50)

    def test_sabotage_no_coaxial_parts(self):
        r = _run("no_coaxial")
        self.assertFalse(r["checks"]["plan_motor_drives_wheel_and_tyre"])

    def test_sabotage_same_signs(self):
        r = _run("same_signs")
        self.assertFalse(r["checks"]["mjcf_car_sides_drive_together"])

    @unittest.skipUnless(os.environ.get("ATELIER_MUJOCO_DIR"),
                         "set ATELIER_MUJOCO_DIR to an installed MuJoCo")
    def test_physics_runs(self):
        r = _run()
        self.assertTrue(r["checks"].get("physics_shaft_turns"), r["errors"])

    def test_sabotage_cables_exploded(self):
        r = _run("explode_cables")
        self.assertFalse(r["checks"]["explode_electronics_stay"])


@unittest.skipIf(QtWidgets is None, "PySide6 not installed")
class TestHome(unittest.TestCase):
    def setUp(self):
        from acadagent import shell
        self.shell = shell
        shell._HOME["on"] = False

    def tearDown(self):
        self.shell._HOME["on"] = False

    def _click(self, w):
        for t in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonRelease):
            ev = QtGui.QMouseEvent(t, QtCore.QPointF(3, 3), QtCore.QPointF(3, 3),
                                   QtCore.Qt.LeftButton, QtCore.Qt.LeftButton,
                                   QtCore.Qt.NoModifier)
            QtWidgets.QApplication.sendEvent(w, ev)

    def test_logo_always_goes_home(self):
        s = self.shell
        logo = QtWidgets.QLabel("logo")
        f = s._ClickFilter(s.go_home, logo)
        logo.installEventFilter(f)
        self._click(logo)
        self.assertTrue(s.home_open())
        self._click(logo)
        self.assertTrue(s.home_open(), "a second click must not leave Home")

    def test_sabotage_toggle_leaves_home(self):
        s = self.shell
        logo = QtWidgets.QLabel("logo")
        f = s._ClickFilter(s.toggle_home, logo)
        logo.installEventFilter(f)
        self._click(logo)
        self._click(logo)
        self.assertFalse(s.home_open())

    def test_sidebar_and_topbar_logos_use_go_home(self):
        s = self.shell
        self.assertIn("_ClickFilter(go_home, self.brand)", inspect.getsource(s.Sidebar))
        self.assertIn("_ClickFilter(go_home, w)", inspect.getsource(s._build_topbar))

    def test_go_home_leaves_full_screen(self):
        s = self.shell
        seen = []
        old = s.focus_view, s.set_focus_view
        s.focus_view = lambda: True
        s.set_focus_view = lambda on: seen.append(on)
        try:
            s.go_home()
        finally:
            s.focus_view, s.set_focus_view = old
        self.assertEqual(seen, [False])
        self.assertTrue(s.home_open())


@unittest.skipIf(QtWidgets is None, "PySide6 not installed")
class TestRegistry(unittest.TestCase):
    def test_tools_on_the_bar(self):
        from acadagent import shell
        for k in ("simulate", "video"):
            self.assertIn(k, shell.TOOL_ORDER)
            self.assertIn(k, [x for g in shell.TOOL_GROUPS for x in g])
            self.assertIn(k, shell.TOOL_DROP_LEVEL)
        keys = shell.register_builtin_tools()
        self.assertIn("simulate", keys)
        self.assertIn("video", keys)
        self.assertIn("simulate", shell._TOOLS)

    def test_simulate_button(self):
        from acadagent import simulate
        b = simulate.view_bar_button(None, gui=False)
        self.assertEqual(b.objectName(), "VBtn")
        self.assertEqual(b.accessibleName(), "Simulate")
        self.assertTrue(b.isCheckable())


if __name__ == "__main__":
    unittest.main()
