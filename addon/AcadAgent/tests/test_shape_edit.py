"""R800 Edit shapes + R801 Home mode.

  TestGeometry   fc_shape_edit.py under freecadcmd: real FreeCAD geometry
                 (skips without ATECH_FREECADCMD / a bundled freecadcmd)
  TestPure       shape_edit helpers that need no FreeCAD
  TestWindow     the Edit shapes window, offscreen Qt (PySide6), no FreeCAD:
                 builds, has the six shapes, greys out what needs a part
  TestHomeMode   shell.show_home / toggle_home and the overlay's placement

    QT_QPA_PLATFORM=offscreen python -m unittest -v test_shape_edit
"""
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

from acadagent import shape_edit as se                    # noqa: E402

try:
    from PySide6 import QtCore, QtWidgets
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


@unittest.skipIf(FC is None, "freecadcmd not found (set ATECH_FREECADCMD)")
class TestGeometry(unittest.TestCase):
    def test_fc_shape_edit(self):
        home = tempfile.mkdtemp(prefix="atech-se-")
        env = {"HOME": home, "FREECAD_USER_HOME": home, "PATH": "/usr/bin:/bin"}
        p = subprocess.run([FC, os.path.join(HERE, "fc_shape_edit.py")], env=env,
                           cwd=home, capture_output=True, text=True, timeout=300)
        line = [ln for ln in (p.stdout + p.stderr).splitlines()
                if ln.startswith("SHAPE_EDIT_RESULT=")]
        self.assertTrue(line, (p.stdout + p.stderr)[-2000:])
        r = json.loads(line[-1].split("=", 1)[1])
        failed = [k for k, v in r["checks"].items() if not v]
        self.assertTrue(r["ok"], (failed, r["errors"]))
        self.assertGreaterEqual(len(r["checks"]), 30)


class TestPure(unittest.TestCase):
    def test_same_ratio_and_fmt(self):
        self.assertEqual(se.same_ratio((10, 20, 30), 2, 60), (20.0, 40.0, 60.0))
        self.assertEqual(se.fmt_mm(3.0), "3")
        self.assertEqual(se.fmt_mm(3.1), "3.1")

    def test_factors(self):
        self.assertEqual(se.factors((10, 20, 0), (20, 20, 5)), (2.0, 1.0, 1.0))
        with self.assertRaises(se.EditRefused):
            se.factors((10, 10, 10), (0, 10, 10))

    def test_kinds_without_freecad(self):
        class O(object):
            TypeId = "Part::Box"
        self.assertEqual(se.kind(O()), "box")
        o = O()
        o.AtechAgentBuilt = True
        self.assertEqual(se.kind(o), "agent")
        self.assertIn("Dimensions", se.why_not(o))
        o2 = O()
        o2.AtechRole = "module"
        self.assertEqual(se.kind(o2), "hardware")
        self.assertIsNone(se.kind(None))
        self.assertEqual(list(se.SHAPE_ORDER), list(se.SHAPES))


@unittest.skipIf(QtWidgets is None, "PySide6 not installed")
class TestWindow(unittest.TestCase):
    def test_window_builds_with_nothing_selected(self):
        from acadagent import manual_edit
        d = manual_edit.ShapeEditor(None)
        try:
            self.assertEqual(list(d.shape_buttons), list(se.SHAPE_ORDER))
            self.assertEqual(d.name.text(), "No part selected")
            self.assertFalse(any(b.isEnabled() for b in d.size))
            self.assertFalse(any(b.isEnabled() for b in d.pos))
            self.assertFalse(d.btn_combine.isEnabled())
            self.assertFalse(d.btn_ungroup.isEnabled())
            self.assertFalse(d.btn_dims.isVisible())
        finally:
            d.close()
            d.deleteLater()

    def test_view_bar_button(self):
        from acadagent import manual_edit
        b = manual_edit.view_bar_button(None)
        self.assertEqual(b.objectName(), "VBtn")
        self.assertEqual(b.accessibleName(), "Edit shapes")
        self.assertIn("(R)", b.toolTip())


@unittest.skipIf(QtWidgets is None, "PySide6 not installed")
class TestHomeMode(unittest.TestCase):
    def setUp(self):
        from acadagent import shell
        self.shell = shell
        shell._HOME["on"] = False

    def tearDown(self):
        self.shell._HOME["on"] = False
        self.shell._S.pop("overlay", None)

    def test_toggle_flag(self):
        s = self.shell
        self.assertFalse(s.home_open())
        self.assertTrue(s.toggle_home())
        self.assertTrue(s.home_open())
        self.assertFalse(s.toggle_home())
        s.show_home(True)
        s._leave_home()
        self.assertFalse(s.home_open())

    def test_registered_tool_and_shortcuts(self):
        s = self.shell
        self.assertIn(("shape", "Edit shapes"), s.EDIT_TOOLS)
        self.assertIn("shape", s.TOOL_ORDER)
        ids = {sid: key for sid, key, _w, _s in s.SHORTCUTS}
        self.assertEqual(ids.get("shape"), "R")
        self.assertEqual(ids.get("home"), "Ctrl+0")
        keys = [k for _i, k, _w, _s in s.SHORTCUTS]
        self.assertEqual(len(keys), len(set(keys)), "a key bound twice")

    def test_overlay_shows_home_over_an_open_project(self):
        import _shell_fakes as F
        mw = F.build_main_window()
        F.install_fakes(mw)
        F.install_panel_stubs()
        from acadagent import shell
        shell._S.clear()
        shell._KEEP.clear()
        try:
            shell.install()
            F.pump(50)
            ov = shell._S.get("overlay")
            self.assertIsNotNone(ov)
            mdi = ov.mdi
            sub = mdi.addSubWindow(QtWidgets.QWidget())
            sub.show()
            F.pump(30)
            ov.place()
            self.assertFalse(ov.empty.isVisible(), "home hidden while a project shows")
            # R721: a labelled way to Home, and back, in the sidebar
            btn = shell._S["body"].btn_home
            self.assertEqual(btn.text(), "All projects")
            self.assertFalse(btn.isHidden())
            shell.show_home(True)
            F.pump(30)
            self.assertTrue(ov.empty.isVisible(), "home shown in home mode")
            self.assertFalse(ov.bar.isVisible(), "no view bar over home")
            self.assertEqual(btn.text(), "Back to project")
            btn.click()
            F.pump(30)
            self.assertFalse(shell.home_open(), "the button goes back")
            self.assertFalse(ov.empty.isVisible())
            self.assertTrue(ov.bar.isVisible())
            self.assertEqual(btn.text(), "All projects")
            body = shell._S["body"]
            body.set_home_state(True, False)        # no project open at all
            self.assertTrue(btn.isHidden(), "no button when Home is the only page")
            body.set_home_state(False, True)
            self.assertFalse(btn.isHidden())
        finally:
            shell._HOME["on"] = False
            shell.uninstall()
            for p in F.FakePanel.instances:       # as test_shell_lifecycle
                p.worker.stop = True
                p.worker.wait(2000)
            shell.teardown()
            F.FakePanel.instances.clear()
            mw.close()
            mw.deleteLater()
            F.pump(30)

if __name__ == "__main__":
    unittest.main()
