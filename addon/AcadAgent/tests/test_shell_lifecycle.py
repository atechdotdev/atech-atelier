"""The Atech shell's lifecycle, headless: R18, R27, R30, R31, R32, R33, R34, S03.

Runs the real shell.py / chrome.py / viewport.py / style.py against the fakes
in _shell_fakes.py (a FreeCAD-shaped QMainWindow, an in-memory parameter
store, a chat panel that owns a RUNNING QThread parented to itself).

    QT_QPA_PLATFORM=offscreen dist/build/squashfs-root/usr/bin/python \
        -m unittest discover -s addon/AcadAgent/tests -p 'test_shell_*.py' -v

Use the AppImage's interpreter: system python3 has no PySide6.
"""
import os
import subprocess
import sys
import textwrap
import unittest

import _shell_fakes as F
from PySide6 import QtCore, QtGui, QtWidgets

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

TOOLBARS = "User parameter:BaseApp/MainWindow/Toolbars"
VIEW = "User parameter:BaseApp/Preferences/View"
MAINWIN = "User parameter:BaseApp/Preferences/Main" + "Window"


class ShellCase(unittest.TestCase):
    def setUp(self):
        self.mw = F.build_main_window()
        self.fc, self.gui = F.install_fakes(self.mw)
        F.install_panel_stubs()
        from acadagent import chrome, shell, viewport, style
        self.shell, self.chrome, self.viewport, self.style = \
            shell, chrome, viewport, style
        shell._S.clear()
        shell._KEEP.clear()
        shell._ICON_DIR[:] = []
        style._LOGO_CACHE.clear()
        # FreeCAD's measured defaults on this profile
        tb = self.fc.ParamGet(TOOLBARS)
        for n in ("File", "Edit", "View", "Workbench"):
            tb.SetBool(n, True)
        tb.SetBool("Macro", False)          # the user hid this one
        self.mw.findChild(QtWidgets.QToolBar, "Macro").hide()

    def tearDown(self):
        s = self.shell
        s.uninstall()
        for p in F.FakePanel.instances:
            p.worker.stop = True
            p.worker.wait(2000)
        s.teardown()
        F.FakePanel.instances.clear()
        self.mw.close()
        self.mw.deleteLater()
        F.pump(20)

    def model_tree(self):
        return self.mw.findChild(QtWidgets.QTreeWidget, "ModelTree")


# ------------------------------------------------------------------ R18
class TestWorkbenchSwitch(ShellCase):
    def test_ten_switches_keep_chat_thread_and_model(self):
        s = self.shell
        s.install()
        chat = s.chat_panel()
        worker = chat.worker
        md = self.mw.findChild(QtWidgets.QDockWidget, "Model")
        for _ in range(10):
            s.uninstall()
            F.pump(30)                      # deleteLater would run here
            self.assertTrue(worker.isRunning(), "worker died on a switch")
            self.assertIs(md.widget(), self.model_tree(),
                          "Model tree not handed back on deactivate")
            self.assertFalse(s._KEEP["dock"].isVisible())
            s.install()
            F.pump(30)
            self.assertIs(s.chat_panel(), chat, "chat rebuilt on a switch")
            self.assertIs(s._KEEP["body"].model_widget, self.model_tree())
        self.assertEqual(len(F.FakePanel.instances), 1)

    def test_teardown_joins_the_worker_first(self):
        s = self.shell
        s.install()
        worker = s.chat_panel().worker
        self.assertTrue(worker.isRunning())
        self.assertTrue(s.teardown(2000))
        self.assertFalse(worker.isRunning())
        self.assertEqual(s._KEEP, {})

    def test_teardown_keeps_sidebar_when_a_worker_will_not_stop(self):
        s = self.shell
        s.install()
        worker = s.chat_panel().worker
        worker.deaf = True
        self.assertFalse(s.teardown(300))
        F.pump(30)
        self.assertTrue(worker.isRunning())
        self.assertIn("dock", s._KEEP, "parent of a running thread deleted")
        worker.deaf = False

    def test_failed_install_hands_the_model_back(self):
        s = self.shell
        orig = s._build_topbar

        def boom(mw):
            raise RuntimeError("simulated failure mid-install")
        s._build_topbar = boom
        try:
            with self.assertRaises(RuntimeError):
                s.install()
        finally:
            s._build_topbar = orig
        md = self.mw.findChild(QtWidgets.QDockWidget, "Model")
        self.assertIs(md.widget(), self.model_tree())
        self.assertFalse(s.installed())
        self.assertTrue(md.toggleViewAction().isEnabled())

    def test_overlay_is_deleted_on_uninstall(self):
        s = self.shell
        s.install()
        ov = s._S["overlay"]
        s.uninstall()
        F.pump(30)
        with self.assertRaises(RuntimeError):
            ov.objectName()                  # C++ side gone: no leak


class TestQThreadAbortPattern(unittest.TestCase):
    """The bug shape itself, in a child process: deleting the parent of a
    running QThread aborts. Proves the lifecycle test above is asking the
    right question (the fake worker IS such a thread)."""

    def test_naive_parent_delete_aborts(self):
        code = textwrap.dedent("""
            from PySide6 import QtCore, QtWidgets
            app = QtWidgets.QApplication([])
            class T(QtCore.QThread):
                def run(self):
                    while True: self.msleep(10)
            w = QtWidgets.QWidget(); t = T(w); t.start()
            w.deleteLater()
            QtCore.QTimer.singleShot(100, app.quit); app.exec()
            print("SURVIVED", flush=True)
        """)
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        r = subprocess.run([sys.executable, "-c", code], env=env,
                           capture_output=True, text=True, timeout=60)
        self.assertNotIn("SURVIVED", r.stdout)
        self.assertIn("Destroyed while thread", r.stderr)


# ------------------------------------------------------------------ R30
class TestToolbarRestore(ShellCase):
    def pollute(self):
        # what FreeCAD's ToolBarManager::saveState writes while we hide
        grp = self.fc.ParamGet(TOOLBARS)
        for n in ("File", "Edit", "View", "Workbench", "Macro"):
            grp.SetBool(n, False)

    def test_uninstall_writes_the_snapshot_back(self):
        s = self.shell
        s.install()
        F.pump(600)
        self.pollute()
        s.uninstall()
        grp = self.fc.ParamGet(TOOLBARS)
        for n in ("File", "Edit", "View", "Workbench"):
            self.assertTrue(grp.GetBool(n), n)
        self.assertFalse(grp.GetBool("Macro"), "user-hidden bar was shown")
        self.assertFalse(self.chrome.saved_snapshot())

    def test_quit_inside_atech_then_next_session(self):
        s = self.shell
        s.install()
        F.pump(200)
        self.pollute()
        s._on_quit()                          # aboutToQuit, still in Atech
        grp = self.fc.ParamGet(TOOLBARS)
        self.assertTrue(grp.GetBool("File"))
        self.assertFalse(grp.GetBool("Macro"))
        # Nothing writes the group after aboutToQuit, so the write-back is
        # final and the snapshot goes: kept, it would go stale.
        self.assertIsNone(self.chrome.saved_snapshot())
        # next session starts in Part; the user shows Macro, hides Edit
        s._S.clear()
        self.chrome._ACTIVE[0] = False
        grp.SetBool("Macro", True)
        grp.SetBool("Edit", False)
        s.install()
        s.uninstall()
        self.assertTrue(grp.GetBool("File"))
        self.assertTrue(grp.GetBool("Macro"), "stale snapshot undid the user")
        self.assertFalse(grp.GetBool("Edit"), "stale snapshot undid the user")

    def test_crash_inside_atech_recovers_next_session(self):
        s = self.shell
        s.install()
        F.pump(200)
        self.pollute()                        # FreeCAD persisted our False
        # crash: no uninstall, no aboutToQuit; next session enters Atech
        s._S.clear()
        self.chrome._ACTIVE[0] = False
        self.assertIsNotNone(self.chrome.saved_snapshot())
        s.install()
        s.uninstall()
        grp = self.fc.ParamGet(TOOLBARS)
        self.assertTrue(grp.GetBool("File"))
        self.assertFalse(grp.GetBool("Macro"))

    def test_corner_selector_comes_back(self):
        s = self.shell
        mb = self.mw.menuBar()
        sel = mb.cornerWidget(QtCore.Qt.TopRightCorner)
        s.install()
        self.assertIsNot(mb.cornerWidget(QtCore.Qt.TopRightCorner), sel)
        s.uninstall()
        self.assertIs(mb.cornerWidget(QtCore.Qt.TopRightCorner), sel)
        self.assertFalse(sel.isHidden())

    def test_no_hide_after_uninstall(self):
        s = self.shell
        s.install()
        s.uninstall()
        bar = self.mw.findChild(QtWidgets.QToolBar, "File")
        bar.show()
        F.pump(700)                          # the old deferred hide timers
        self.chrome.hide_now()
        self.assertTrue(bar.isVisible())

    def test_toolbar_rehidden_on_show_event(self):
        s = self.shell
        s.install()
        F.pump(50)
        bar = self.mw.findChild(QtWidgets.QToolBar, "Edit")
        bar.show()                           # FreeCAD re-showing it
        F.pump(50)
        self.assertFalse(bar.isVisible())


# ------------------------------------------------------------------ R31
class TestViewPrefs(ShellCase):
    def test_user_navigation_survives_activation(self):
        v = self.fc.ParamGet(VIEW)
        v.SetString("NavigationStyle", "Gui::BlenderNavigationStyle")
        v.SetInt("AntiAliasing", 0)
        self.viewport.apply_view_theme()     # InitGui.Activated
        self.shell.install()
        self.assertEqual(v.GetString("NavigationStyle"),
                         self.viewport.NAV_STYLE)       # Atech default, kept
        self.shell.uninstall()
        self.assertEqual(v.GetString("NavigationStyle"),
                         "Gui::BlenderNavigationStyle")
        self.assertEqual(v.GetInt("AntiAliasing", 99), 0)
        keys = {n for _k, n, _v in (v.GetContents() or [])}
        self.assertNotIn("OrbitStyle", keys, "absent key must stay absent")
        self.assertNotIn("Gradient", keys)
        self.assertIsNone(self.viewport.saved_view_prefs())

    def test_quit_clears_the_snapshot_so_it_cannot_go_stale(self):
        v = self.fc.ParamGet(VIEW)
        v.SetString("NavigationStyle", "Gui::BlenderNavigationStyle")
        self.viewport.apply_view_theme()
        self.shell.install()
        self.shell._on_quit()
        self.assertEqual(v.GetString("NavigationStyle"),
                         "Gui::BlenderNavigationStyle")
        self.assertIsNone(self.viewport.saved_view_prefs())
        # next session, in Part: the user picks another style, then Atech
        self.shell._S.clear()
        self.chrome._ACTIVE[0] = False
        v.SetString("NavigationStyle", "Gui::OpenInventorNavigationStyle")
        self.viewport.apply_view_theme()
        self.shell.install()
        self.shell.uninstall()
        self.assertEqual(v.GetString("NavigationStyle"),
                         "Gui::OpenInventorNavigationStyle")

    def test_restyle_does_not_overwrite_the_snapshot(self):
        v = self.fc.ParamGet(VIEW)
        v.SetString("NavigationStyle", "Gui::OpenInventorNavigationStyle")
        self.viewport.apply_view_theme()
        self.shell.install()
        self.shell.restyle()                 # applies the theme again
        self.shell.uninstall()
        self.assertEqual(v.GetString("NavigationStyle"),
                         "Gui::OpenInventorNavigationStyle")


# ------------------------------------------------------- R32 / S03
class TestTasksAndTick(ShellCase):
    def _overlay_tasks(self, extra_docks=0):
        T = type("Gui::OverlayTabWidget", (QtWidgets.QTabWidget,), {})
        box = T(self.mw)
        box.setObjectName("OverlayRight")
        tasks = self.mw.findChild(QtWidgets.QDockWidget, "Tasks")
        split = QtWidgets.QSplitter(box)
        tasks.setParent(split)
        box.addTab(QtWidgets.QWidget(), "Tasks")
        for i in range(extra_docks):
            box.addTab(QtWidgets.QWidget(), "Report view")
        box.show()
        return box

    def test_idle_ticks_run_no_commands(self):
        box = self._overlay_tasks()
        s = self.shell
        s.install()
        self.gui.commands.clear()
        per_min = 60000 // s.SAFETY_TICK_MS
        for _ in range(per_min):             # 60 s of idle, auto-hide mode
            box.show()                       # the overlay re-shows itself
            s._tick()
        self.assertEqual(self.gui.commands, [])

    def test_toggles_once_per_dialog_transition(self):
        box = self._overlay_tasks()
        s = self.shell
        s.install()
        box.hide()
        self.gui.commands.clear()
        self.gui.dialog[0] = True
        for _ in range(5):
            s._tick()
        self.assertEqual(self.gui.commands, ["Std_DockOverlayToggleRight"])

    def test_shared_panel_is_never_toggled(self):
        box = self._overlay_tasks(extra_docks=1)   # Tasks + Report view
        s = self.shell
        self.gui.commands.clear()
        s.install()
        self.gui.dialog[0] = True
        s._tick()
        self.gui.dialog[0] = False
        s._tick()
        self.assertEqual(self.gui.commands, [])
        self.assertTrue(box.isVisible())

    def test_plain_tasks_dock_state_restored(self):
        tasks = self.mw.findChild(QtWidgets.QDockWidget, "Tasks")
        self.assertTrue(tasks.isVisible())
        self.shell.install()
        self.assertFalse(tasks.isVisible())  # no dialog: collapsed
        self.shell.uninstall()
        self.assertTrue(tasks.isVisible())

    def test_safety_tick_is_slow(self):
        self.shell.install()
        self.assertGreaterEqual(self.shell._S["timer"].interval(), 2000)

    def test_status_mark_hidden_when_added(self):
        self.shell.install()
        pm = QtGui.QPixmap(64, 20)
        pm.fill(QtCore.Qt.black)
        lbl = QtWidgets.QLabel()
        lbl.setPixmap(pm)
        lbl.setFixedWidth(64)
        self.mw.statusBar().addPermanentWidget(lbl)
        F.pump(50)
        self.assertFalse(lbl.isVisible())


# ------------------------------------------------------------------ R33
class TestIconCache(ShellCase):
    def test_per_user_dir_and_no_symlink_follow(self):
        s = self.shell
        d = s._icon_dir()
        self.assertTrue(d.startswith(self.fc.getUserCachePath()), d)
        self.assertNotIn("/tmp/atech-atelier-icons", d)
        victim = os.path.join(d, "..", "victim.txt")
        with open(victim, "w", encoding="utf-8") as fh:
            fh.write("keep me")
        path = os.path.join(d, "x-abcdef.png")
        if os.path.lexists(path):
            os.unlink(path)
        os.symlink(victim, path)
        out = s._icon_file("x", "#abcdef")
        self.assertEqual(out, path)
        self.assertFalse(os.path.islink(path))
        with open(victim, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "keep me")

    def test_planted_file_in_place_of_dir_falls_back(self):
        s = self.shell
        cache = self.fc.getUserCachePath()
        os.makedirs(os.path.join(cache, "AtechAtelier"), exist_ok=True)
        with open(os.path.join(cache, "AtechAtelier", "icons"), "w") as fh:
            fh.write("")
        d = s._icon_dir()
        self.assertTrue(os.path.isdir(d))
        self.assertTrue(os.path.isfile(s._icon_file("x", "#123456")))


# ------------------------------------------------------------------ R34
class TestThemeAndSize(ShellCase):
    def _palette(self, dark):
        pal = QtGui.QPalette()
        c = QtGui.QColor("#1a1a1a" if dark else "#f5f5f5")
        pal.setColor(QtGui.QPalette.Window, c)
        return pal

    def test_mode_from_palette_when_theme_is_silent(self):
        st, mw = self.style, self.fc.ParamGet(MAINWIN)
        old = APP.palette()
        try:
            for theme, dark, want in (("", True, "dark"),
                                      ("FreeCAD Classic", True, "dark"),
                                      ("FreeCAD Classic", False, "light"),
                                      ("Atech Studio Dark", False, "dark"),
                                      ("Atech Atelier Dark", False, "dark"),
                                      ("FreeCAD Light", True, "light")):
                mw.SetString("Theme", theme)
                APP.setPalette(self._palette(dark))
                self.assertEqual(st.mode(), want, (theme, dark))
                self.assertEqual(st.tokens()["base"],
                                 (st.DARK if want == "dark" else st.LIGHT)["base"])
        finally:
            APP.setPalette(old)

    def test_restyle_on_palette_change(self):
        self.fc.ParamGet(MAINWIN).SetString("Theme", "")
        old = APP.palette()
        try:
            APP.setPalette(self._palette(False))
            self.shell.install()
            self.assertEqual(self.shell._S["mode"], "light")
            APP.setPalette(self._palette(True))
            F.pump(50)
            self.assertEqual(self.shell._S["mode"], "dark")
        finally:
            APP.setPalette(old)

    def test_icon_scale_follows_dpr(self):
        self.assertGreaterEqual(self.style.pixel_scale(), 2)
        ic = self.style.icon("x", "#000000", 14, scale=3)
        self.assertEqual(ic.availableSizes()[0].width(), 42)

    def test_cards_wrap_below_700(self):
        self.shell.install()
        ev = self.shell._S["overlay"].empty
        self.assertEqual(ev.columns_for(900), 3)
        self.assertLess(ev.columns_for(600), 3)
        self.assertEqual(ev.columns_for(300), 1)
        ev._layout_cards(ev.columns_for(450))
        self.assertTrue(all(c.height() == 100 for c in ev.cards))

    def test_view_bar_clamped_to_narrow_viewport(self):
        s = self.shell
        s.install()
        dock = s._KEEP["dock"]
        self.mw.resize(760, 700)             # 1280 px @150 % minus sidebar
        F.pump(50)
        ov = s._S["overlay"]
        ov.place()
        vp = ov.mdi.viewport().geometry()
        self.assertLessEqual(ov.bar.width(), max(0, vp.width() - 24),
                             (vp.width(), dock.width()))


# ------------------------------------------------------------------ R27
class TestStartCards(ShellCase):
    def test_reference_failure_becomes_a_notice(self):
        s = self.shell
        s.install()
        orig = self.viewport.crane_parts
        self.viewport.crane_parts = lambda: []
        try:
            s._open_reference()
        finally:
            self.viewport.crane_parts = orig
        notes = s.chat_panel().notices
        self.assertEqual(notes[-1][0], "Sample crane not available")
        self.assertEqual(notes[-1][1],
                         "The sample crane is not included in this installation.")

    def test_new_document_failure_becomes_a_notice(self):
        s = self.shell
        s.install()

        def boom(*a):
            raise OSError("disk full")
        self.fc.newDocument = boom
        s._new_document()
        self.assertEqual(s.chat_panel().notices[-1][0],
                         "Could not create a document")


if __name__ == "__main__":
    unittest.main()
