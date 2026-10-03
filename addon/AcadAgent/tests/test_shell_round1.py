"""Regression tests for the round-1 GUI fixes in shell.py (release PRD R50):

    R47  switching to Part segfaulted: _restore_topbar passed
         QApplication.style() (a QStyleSheetStyle under a theme) to
         menuBar().setStyle(), and the freed proxy style was used later.
         Fixed: setStyle(None) and the proxy kept alive for the session.
    R48  the empty Tasks overlay strip covered the model when the first
         document opened: FreeCAD shows the Tasks overlay when a 3D view
         appears, AFTER install() synced with no view.
    R49  Part came back without the Model tree: install() ran before the main
         window was shown and recorded isVisible() == False for the dock.

Runs the real shell.py against _shell_fakes.py, like test_shell_lifecycle:

    QT_QPA_PLATFORM=offscreen dist/build/squashfs-root/usr/bin/python \
        -m unittest discover -s addon/AcadAgent/tests -p 'test_shell_*.py' -v

The R47 switch loop runs in a CHILD interpreter: a segfault there must fail
one test, not kill the whole run. The child prints a sentinel as its last
act; the test requires the sentinel AND exit code 0.
"""
import os
import subprocess
import sys
import textwrap
import unittest

import _shell_fakes as F
from PySide6 import QtCore, QtWidgets

from test_shell_lifecycle import ShellCase

HERE = os.path.dirname(os.path.abspath(__file__))

# The switch loop of the R47 GUI measurement, headless: an app-wide style
# sheet (so QApplication.style() is a QStyleSheetStyle, as under a theme),
# repeated activate/deactivate, then the two calls that crashed on the freed
# proxy - a grab() and a menu shown from the menubar.
_R47_CHILD = textwrap.dedent(r'''
    import os, sys
    sys.path.insert(0, %(here)r)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import _shell_fakes as F
    from PySide6 import QtCore, QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setStyleSheet("QMenuBar { padding: 1px; } QMenu { padding: 1px; }")
    mw = F.build_main_window(n_toolbars=6)
    F.install_fakes(mw)
    F.install_panel_stubs()
    from acadagent import shell
    if os.environ.get("R47_SABOTAGE"):
        # the pre-fix line, to prove this child can observe the defect
        orig = shell._restore_topbar
        def old(mw_, tb):
            st = tb.get("style")
            tb = dict(tb, style=None)
            orig(mw_, tb)
            if st is not None:
                mw_.menuBar().setStyle(QtWidgets.QApplication.style())
        shell._restore_topbar = old
    mb = mw.menuBar()
    menu = QtWidgets.QMenu("Edit", mb)     # held here: a menu FreeCAD owns
    menu.addAction("Undo")
    mb.addMenu(menu)
    for i in range(8):
        shell.install()
        F.pump(20)
        shell.uninstall()
        F.pump(20)
        app.processEvents()
        mb.grab()
        menu.popup(mb.mapToGlobal(QtCore.QPoint(4, 4)))
        F.pump(10)
        menu.hide()
    print("R47_SWITCH_LOOP_OK", mb.testAttribute(QtCore.Qt.WA_SetStyle), flush=True)
    for p in F.FakePanel.instances:
        p.worker.stop = True
        p.worker.wait(2000)
    shell.teardown()
    os._exit(0)
''')


def _run_child(extra_env=None):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", **(extra_env or {}))
    return subprocess.run([sys.executable, "-c", _R47_CHILD % {"here": HERE}],
                          env=env, capture_output=True, text=True, timeout=120)


# ------------------------------------------------------------------ R47
class TestR47MenubarStyle(ShellCase):
    def test_uninstall_clears_the_menubar_style_instead_of_setting_app_style(self):
        """setStyle(None) clears WA_SetStyle; setStyle(QApplication.style())
        (the crashing line) sets it. Both leave mb.style() looking the same,
        so the attribute is what tells them apart."""
        s = self.shell
        mb = self.mw.menuBar()
        self.assertFalse(mb.testAttribute(QtCore.Qt.WA_SetStyle))
        s.install()
        proxy = s._S["topbar"]["style"]
        self.assertIsNotNone(proxy, "install did not set the menubar proxy style")
        self.assertTrue(mb.testAttribute(QtCore.Qt.WA_SetStyle))
        s.uninstall()
        F.pump(20)
        self.assertFalse(mb.testAttribute(QtCore.Qt.WA_SetStyle),
                         "menubar still carries an explicit style after uninstall")

    def test_proxy_style_outlives_uninstall(self):
        s = self.shell
        styles = []
        for _ in range(3):
            s.install()
            styles.append(s._S["topbar"]["style"])
            s.uninstall()
            F.pump(20)
        kept = s._KEEP.get("old_styles", [])
        for st in styles:
            self.assertIn(st, kept, "proxy style dropped: menus may still use it")
            st.name()                    # RuntimeError if the C++ side was freed

    def test_switch_loop_under_an_app_style_sheet_does_not_crash(self):
        p = _run_child()
        self.assertEqual(p.returncode, 0, "child died (%s):\n%s" % (
            p.returncode, (p.stdout + p.stderr)[-2000:]))
        self.assertIn("R47_SWITCH_LOOP_OK False", p.stdout,
                      "sentinel missing:\n%s" % (p.stdout + p.stderr)[-2000:])

    def test_sabotage_is_observable(self):
        """The pre-fix line leaves WA_SetStyle set, so the check above can
        fail. MEASURED 2026-09-25: offscreen Qt does NOT segfault on the old
        line (exit 0, sentinel "True"); only the real xcb session did. So
        the attribute is what bites headless, and the child's exit code
        guards any crash the fakes can reproduce."""
        p = _run_child({"R47_SABOTAGE": "1"})
        # Positive evidence only: the sabotaged child must either report the
        # attribute set ("True") or die by a signal. A child that failed to
        # import (rc 1, no sentinel) proves nothing and must fail here.
        self.assertTrue("R47_SWITCH_LOOP_OK True" in p.stdout or p.returncode < 0,
                        "sabotage not observed (rc %s):\n%s" % (
                            p.returncode, (p.stdout + p.stderr)[-2000:]))


# ------------------------------------------------------------------ R48
class TestR48TasksStripOnFirstDocument(ShellCase):
    def _overlay_tasks(self):
        T = type("Gui::OverlayTabWidget", (QtWidgets.QTabWidget,), {})
        box = T(self.mw)
        box.setObjectName("OverlayRight")
        tasks = self.mw.findChild(QtWidgets.QDockWidget, "Tasks")
        split = QtWidgets.QSplitter(box)
        tasks.setParent(split)
        box.addTab(QtWidgets.QWidget(), "Tasks")
        return box

    def test_overlay_appearing_with_no_dialog_is_collapsed_once(self):
        box = self._overlay_tasks()
        box.hide()                       # startup: no 3D view, no strip
        s = self.shell
        s.install()
        s._tick()
        self.gui.commands.clear()
        box.show()                       # the first document opens a 3D view
        s._tick()
        self.assertEqual(self.gui.commands, ["Std_DockOverlayToggleRight"],
                         "empty Tasks strip left over the model")
        # FreeCAD may ignore/undo the toggle; a panel that STAYS shown is not
        # a new transition, so idle ticks must not loop the command.
        for _ in range(20):
            s._tick()
        self.assertEqual(self.gui.commands, ["Std_DockOverlayToggleRight"])

    def test_overlay_appearing_during_a_dialog_is_left_open(self):
        box = self._overlay_tasks()
        box.hide()
        s = self.shell
        s.install()
        self.gui.dialog[0] = True        # a task dialog is running
        s._tick()
        self.gui.commands.clear()
        box.show()
        s._tick()
        self.assertEqual(self.gui.commands, [])

    def test_reappearing_after_a_collapse_is_collapsed_again(self):
        box = self._overlay_tasks()
        box.hide()
        s = self.shell
        s.install()
        s._tick()
        box.show()
        s._tick()                        # collapse #1 (fake: we hide it)
        box.hide()
        s._tick()
        self.gui.commands.clear()
        box.show()                       # second document, new view
        s._tick()
        self.assertEqual(self.gui.commands, ["Std_DockOverlayToggleRight"])


# ------------------------------------------------------------------ R49
class TestR49ModelTreeBeforeShow(ShellCase):
    def _md(self):
        return self.mw.findChild(QtWidgets.QDockWidget, "Model")

    def test_install_before_the_window_is_shown_keeps_the_model_dock(self):
        md = self._md()
        self.mw.hide()                   # Activated() at startup: not shown yet
        self.assertFalse(md.isVisible())
        self.assertFalse(md.isHidden())
        s = self.shell
        for _ in range(3):               # each re-install must not re-record False
            s.install()
            F.pump(10)
            s.uninstall()
            F.pump(10)
        self.mw.show()
        F.pump(20)
        self.assertTrue(md.isVisible(), "Part came back without the Model tree")
        self.assertIs(md.widget(), self.model_tree())

    def test_a_dock_the_user_hid_stays_hidden(self):
        md = self._md()
        md.hide()
        s = self.shell
        s.install()
        s.uninstall()
        F.pump(20)
        self.assertFalse(md.isVisible())
        self.assertTrue(md.isHidden())


if __name__ == "__main__":
    unittest.main()
