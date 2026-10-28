"""Round-12 WS W2 (home + navigation), headless: R300-R310.

    R300  macOS-safe chrome: the wordmark ("Atech Atelier"), Terminal and
          Settings move into the sidebar head where the native menu bar
          draws no corner widgets; the R280 hardware switch is really built
          (shell.py used navbar without importing it at module level).
    R301  Parts is a collapsible panel ABOVE the chat, not a page instead
          of it; Cmd+P toggles it.
    R302  Switching projects by document Name (pick_subwindow /
          activate_document), the picker following FreeCAD document events
          instead of an 800 ms poll.
    R303  View bar: fit selection, Rear/Left/Bottom, perspective, wireframe,
          full-screen 3D, and a tool slot for Measure / Section / Export.
    R304  Navigation style setting: the user's choice is kept, a style set
          in FreeCAD's Preferences while Atech runs is adopted, never
          overwritten.
    R305  First-run orbit / pan / zoom card over the 3D view.
    R306  Theme Light / Dark / System.
    R307  Shortcuts (Cmd+L, Cmd+1/2, Cmd+P, M, Shift+S, Cmd+Shift+A,
          Cmd+Shift+F, Cmd+/) and the shortcut sheet.
    R308  Home: project grid (projects_store or recent files), search,
          examples, newest first, real-path dedupe, 100 projects < 1 s.
    R309  Drag-and-drop / open of FCStd, STEP, STL, 3MF.
    R310  "Start from an example": toy car, desk robot, smart speaker.

Each block has a sabotage test: the fix broken on purpose, the check seen
to fail.

    cd addon/AcadAgent/tests && QT_QPA_PLATFORM=offscreen \\
      ".../Atech Atelier.app/Contents/Resources/bin/python" \\
      -m unittest test_shell_round12 -v
"""
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import types
import unittest
import zipfile
from unittest import mock

import _shell_fakes as F
from PySide6 import QtCore, QtGui, QtTest, QtWidgets

from test_shell_lifecycle import ShellCase, VIEW, MAINWIN

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
OWN = "User parameter:BaseApp/Preferences/Mod/AcadAgent"
RECENT = "User parameter:BaseApp/Preferences/RecentFiles"
REPO = os.path.abspath(os.path.join(F.ADDON, "..", ".."))
FREECADCMD = os.environ.get("ATECH_FREECADCMD") or os.path.join(
    REPO, "dist", "build-macos-arm64", "Atech Atelier.app", "Contents",
    "Resources", "bin", "freecadcmd")


def _without_line(func, needle):
    """`func` recompiled from its shipped source with every line holding
    `needle` removed: the sabotage build of a fix."""
    src = textwrap.dedent(inspect.getsource(func))
    kept = [ln for ln in src.splitlines() if needle not in ln]
    assert len(kept) < len(src.splitlines()), "sabotage removed nothing"
    ns = {}
    exec("\n".join(kept), func.__globals__, ns)        # noqa: S102
    return ns[func.__name__]


class FakeView:
    """The bits of View3DInventorPy the view bar calls."""

    def __init__(self):
        self.calls = []
        self.cam = "Orthographic"

    def getCameraType(self):                           # noqa: N802
        return self.cam

    def setCameraType(self, t):                        # noqa: N802
        self.cam = t
        self.calls.append(("setCameraType", t))

    def __getattr__(self, name):
        if name.startswith("view") or name in ("fitAll", "stopAnimating",
                                               "startAnimating"):
            return lambda *a: self.calls.append((name,) + a)
        raise AttributeError(name)


def png_bytes(w=40, h=20, color="#cc3d28"):
    img = QtGui.QImage(w, h, QtGui.QImage.Format_ARGB32)
    img.fill(QtGui.QColor(color))
    buf = QtCore.QBuffer()
    buf.open(QtCore.QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def make_fcstd(path, hardware=False, thumb=True):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Document.xml", "<Document><Property name=\"%s\"/></Document>"
                   % ("AtechRole" if hardware else "Label"))
        if thumb:
            z.writestr("thumbnails/Thumbnail.png", png_bytes())
    return path


class Case(ShellCase):
    """ShellCase plus a 3D view, a selection and recorded commands."""

    def setUp(self):
        super().setUp()
        self.view = FakeView()
        self.gui.ActiveDocument = types.SimpleNamespace(ActiveView=self.view)
        self.gui.Selection = types.SimpleNamespace(getSelection=lambda: [])
        self.ran = []
        self.gui.runCommand = lambda name, *a: self.ran.append((name,) + a)
        self.tmp = tempfile.mkdtemp(prefix="atech-r12-")
        self.shell._TOOLS.clear()
        os.environ.pop("ATECH_SIDEBAR_CHROME", None)

    def tearDown(self):
        self.shell._TOOLS.clear()
        os.environ.pop("ATECH_SIDEBAR_CHROME", None)
        super().tearDown()
        shutil.rmtree(self.tmp, ignore_errors=True)


# ------------------------------------------------------------------ R300
class TestR300Chrome(Case):
    def test_sidebar_chrome_decision(self):
        s = self.shell
        self.assertTrue(s.sidebar_chrome(self.mw, {"ATECH_SIDEBAR_CHROME": "1"}))
        self.assertFalse(s.sidebar_chrome(self.mw, {"ATECH_SIDEBAR_CHROME": "0"}))
        # offscreen: no native menu bar, so the top bar keeps them
        self.assertEqual(s.sidebar_chrome(self.mw, {}),
                         self.mw.menuBar().isNativeMenuBar())

    def test_native_menu_bar_moves_brand_terminal_settings_to_sidebar(self):
        os.environ["ATECH_SIDEBAR_CHROME"] = "1"
        s = self.shell
        s.install()
        F.pump(30)
        body = s._S["body"]
        self.assertTrue(body.brand.isVisible())
        self.assertEqual(body.brand_word.text(), "Atech Atelier")
        for b, name in ((body.btn_terminal, "Terminal"),
                        (body.btn_settings, "Settings")):
            self.assertTrue(b.isVisible(), name)
            self.assertEqual(b.accessibleName(), name)
        # on the picker row
        self.assertIs(body.btn_terminal.parentWidget(),
                      (body.picker_row or body.picker).parentWidget())
        texts = [a.text() for a in body.btn_settings.menu().actions()]
        self.assertIn("Agent settings…", texts)
        self.assertIn("Appearance & navigation…", texts)
        self.assertIn("Keyboard shortcuts", texts)
        self.assertIn("Switch workbench", texts)

    def test_linux_keeps_the_top_bar_and_a_lean_sidebar(self):
        os.environ["ATECH_SIDEBAR_CHROME"] = "0"
        s = self.shell
        s.install()
        F.pump(30)
        body = s._S["body"]
        # R721: the brand row stays for the All projects button; the
        # wordmark is the top bar's
        self.assertFalse(body.brand_word.isVisible())
        self.assertFalse(body.brand_mark.isVisible())
        self.assertFalse(body.btn_terminal.isVisible())
        word = s._S["topbar"]["left"].findChild(QtWidgets.QLabel, "Wordmark")
        self.assertEqual(word.text(), "Atech Atelier")
        gear = [b for b, n in s._S["topbar"]["btns"] if n == "settings"][0]
        self.assertIsNotNone(gear.menu(), "the top-bar gear opens the menu")

    def test_hardware_switch_is_built(self):
        body = self.shell.Sidebar(QtWidgets.QWidget(), None)
        self.assertIsNotNone(body.hw_switch, "R280 switch missing")
        self.assertEqual(body.hw_switch.objectName(), "HardwareSwitch")
        body.deleteLater()

    def test_sabotage_without_module_navbar_the_switch_is_missing(self):
        saved = self.shell.navbar
        del self.shell.navbar                   # the pre-fix module globals
        try:
            self.assertIsNone(self.shell._hardware_switch())
        finally:
            self.shell.navbar = saved

    def test_sabotage_pre_r300_nothing_moves_to_the_sidebar(self):
        os.environ["ATECH_SIDEBAR_CHROME"] = "1"
        with mock.patch.object(self.shell, "sidebar_chrome",
                               lambda *a, **k: False):
            self.shell.install()
            F.pump(30)
            body = self.shell._S["body"]
            self.assertFalse(body.brand_word.isVisible(),
                             "the R300 check could not fail")


# ------------------------------------------------------------------ R301
class TestR301Parts(Case):
    def test_parts_open_above_the_chat(self):
        s = self.shell
        s.install()
        F.pump(30)
        body = s._S["body"]
        self.assertFalse(body.model_page.isVisible())
        body.show_page(body.PAGE_MODEL)
        F.pump(30)
        self.assertTrue(body.model_page.isVisible())
        self.assertTrue(body.chat.isVisible(), "chat must stay on screen")
        self.assertLess(body.model_page.geometry().top(),
                        body.chat.geometry().top(), "parts above the chat")
        self.assertTrue(body.btn_parts.isChecked())
        self.assertTrue(body.parts_toggle.isChecked())
        # the chat page keeps Parts as it was (a notice must not close it)
        s.show_chat()
        F.pump(10)
        self.assertTrue(body.model_page.isVisible())
        body.btn_parts.click()
        F.pump(10)
        self.assertFalse(body.model_page.isVisible())
        self.assertTrue(body.chat.isVisible())
        self.assertEqual(body.page(), body.PAGE_CHAT)

    def test_cmd_p_toggles_and_leaves_modules(self):
        s = self.shell
        s.install()
        body = s._S["body"]
        s.show_modules()
        F.pump(10)
        s._shortcut_fn("parts")()
        F.pump(10)
        self.assertEqual(body.page(), body.PAGE_MODEL)
        s._shortcut_fn("parts")()
        self.assertEqual(body.page(), body.PAGE_CHAT)

    def test_sabotage_parts_never_shown(self):
        s = self.shell
        orig = s.Sidebar.set_parts_open
        s.Sidebar.set_parts_open = _without_line(
            orig, "self.model_page.setVisible(on)")
        try:
            s.install()
            body = s._S["body"]
            body.show_page(body.PAGE_MODEL)
            F.pump(20)
            self.assertFalse(body.model_page.isVisible(), "sabotage had no effect")
        finally:
            s.Sidebar.set_parts_open = orig


# ------------------------------------------------------------------ R302
class _Sub:
    def __init__(self, title, doc):
        self._t, self.doc = title, doc

    def windowTitle(self):                             # noqa: N802
        return self._t


def old_prefix_match(subs, label):
    """navbar.activate_document's pre-R302 rule, as data."""
    for sw in subs:
        t = sw.windowTitle()
        if t.startswith(label + " :") or t.startswith(label + " "):
            return sw
    return None


class TestR302Switch(Case):
    def subs(self):
        return [_Sub("Part : 1", "Part"), _Sub("Part : 1", "Part001"),
                _Sub("Other : 1", "Other")]

    def test_pick_by_name_not_label(self):
        subs = self.subs()
        asked = []

        def doc_of(sw):
            asked.append(sw)
            return sw.doc
        got = self.shell.pick_subwindow(subs, "Part001", "Part", doc_of)
        self.assertIs(got, subs[1])
        self.assertNotIn(subs[2], asked, "label matches are asked first")
        self.assertIsNone(self.shell.pick_subwindow(subs, "Nope", "X",
                                                    lambda sw: sw.doc))

    def test_sabotage_label_prefix_picks_the_wrong_window(self):
        subs = self.subs()
        self.assertIsNot(old_prefix_match(subs, "Part"), subs[1])

    def test_activate_document_in_a_real_mdi(self):
        s = self.shell
        s.install()
        mdi = self.mw.centralWidget()
        a = mdi.addSubWindow(QtWidgets.QWidget())
        b = mdi.addSubWindow(QtWidgets.QWidget())
        for sw in (a, b):
            sw.setWindowTitle("Same : 1")
            sw.show()
        names = {a: "Same", b: "Same001"}
        docs = {n: types.SimpleNamespace(Name=n, Label="Same")
                for n in names.values()}
        self.fc.getDocument = lambda n: docs[n]
        self.fc.setActiveDocument = lambda n: None
        self.gui.activeDocument = lambda: types.SimpleNamespace(
            Document=docs[names[mdi.activeSubWindow()]]) \
            if mdi.activeSubWindow() in names else None
        mdi.setActiveSubWindow(a)
        self.assertTrue(s.activate_document("Same001"))
        self.assertIs(mdi.activeSubWindow(), b)
        self.assertTrue(s.activate_document("Same"))
        self.assertIs(mdi.activeSubWindow(), a)

    def test_picker_follows_document_events_not_a_poll(self):
        obs = []
        self.fc.addDocumentObserver = obs.append
        self.fc.removeDocumentObserver = obs.remove
        s = self.shell
        s.install()
        F.pump(50)                      # let the install's own refreshes run
        body = s._S["body"]
        timers = [t for t in body.findChildren(QtCore.QTimer)
                  if t.interval() == 800]
        self.assertEqual(timers, [], "the 800 ms picker poll is gone")
        # the shell's own observer, once (board_look's restyle adds its own)
        obs[:] = [o for o in obs if isinstance(o, s._DocObserver)]
        self.assertEqual(len(obs), 1)
        doc = types.SimpleNamespace(Name="A", Label="Gearbox", FileName="")
        self.fc.listDocuments = lambda: {"A": doc}
        self.fc.ActiveDocument = doc
        obs[0].slotRelabelDocument(doc)
        F.pump(20)
        self.assertEqual(body.picker.text(), "Gearbox")
        s.uninstall()
        self.assertEqual(obs, [], "observer removed on deactivate")

    def test_sabotage_without_the_observer_the_picker_is_stale(self):
        obs = []
        self.fc.addDocumentObserver = obs.append
        s = self.shell
        with mock.patch.object(s, "_hook_docs", lambda: False):
            s.install()
        F.pump(50)
        body = s._S["body"]
        doc = types.SimpleNamespace(Name="A", Label="Gearbox", FileName="")
        self.fc.listDocuments = lambda: {"A": doc}
        self.fc.ActiveDocument = doc
        for o in obs:
            o.slotRelabelDocument(doc)
        F.pump(20)
        self.assertNotEqual(body.picker.text(), "Gearbox")


# ------------------------------------------------------------------ R303
class TestR303ViewBar(Case):
    def bar(self):
        self.shell.install()
        F.pump(30)
        return self.shell._S["overlay"].bar

    def test_new_buttons_have_names(self):
        bar = self.bar()
        names = {b.accessibleName() for b in bar.findChildren(QtWidgets.QPushButton)}
        for n in ("Fit all", "Fit selection", "More views", "Perspective",
                  "Wireframe", "Full-screen 3D", "Spin", "Ask about this view"):
            self.assertIn(n, names)

    def test_rear_left_bottom_reach_the_view(self):
        bar = self.bar()
        acts = {a.text(): a for a in bar.views_menu.actions()}
        for label, call in (("Rear", "viewRear"), ("Left", "viewLeft"),
                            ("Bottom", "viewBottom")):
            acts[label].trigger()
            self.assertEqual(self.view.calls[-1], (call,))

    def test_fit_selection_perspective_wireframe(self):
        bar = self.bar()
        fits = []
        with mock.patch.object(self.viewport, "fit_all", lambda: fits.append(1)):
            bar.btn_fit_sel.click()             # nothing selected: fit all
        self.assertEqual(fits, [1])
        self.gui.Selection = types.SimpleNamespace(getSelection=lambda: [1])
        bar.btn_fit_sel.click()
        self.assertEqual(self.ran[-1], ("Std_ViewFitSelection",))
        bar.btn_persp.click()
        self.assertEqual(self.view.cam, "Perspective")
        bar.btn_persp.click()
        self.assertEqual(self.view.cam, "Orthographic")
        bar.btn_wire.click()
        self.assertEqual(self.ran[-1], ("Std_DrawStyle", 2))
        bar.btn_wire.click()
        self.assertEqual(self.ran[-1], ("Std_DrawStyle", 0))

    def test_camera_state_follows_the_active_view(self):
        bar = self.bar()
        self.view.cam = "Perspective"
        bar.sync_view()
        self.assertTrue(bar.btn_persp.isChecked())
        self.view.cam = "Orthographic"
        bar.sync_view()
        self.assertFalse(bar.btn_persp.isChecked())

    def test_full_screen_hides_the_sidebar_and_chat_brings_it_back(self):
        bar = self.bar()
        dock = self.shell._S["dock"]
        bar.btn_full.click()
        F.pump(10)
        self.assertFalse(dock.isVisible())
        self.assertTrue(bar.btn_full.isChecked())
        self.shell.show_chat()
        F.pump(10)
        self.assertTrue(dock.isVisible())
        self.assertFalse(bar.btn_full.isChecked())

    def test_tool_slot_order_and_late_registration(self):
        s = self.shell
        bar = self.bar()
        for k in ("export", "measure", "section"):
            s.register_view_tool(k, lambda k=k: QtWidgets.QPushButton(k.title()),
                                 label=k.title())
        self.assertEqual([w.text() for w in bar.tools()],
                         ["Measure", "Section", "Export"])
        self.assertEqual(bar.tools()[0].objectName(), "VBtn")
        self.assertTrue(bar._tool_sep.isVisibleTo(bar))
        s.unregister_view_tool("section")
        self.assertEqual([w.text() for w in bar.tools()], ["Measure", "Export"])

    def test_factory_gets_the_bar_and_restyle_hook_runs(self):
        s = self.shell
        seen, styled = [], []

        def make(view_bar):             # the shape of measure.make_measure_button
            seen.append(view_bar)
            return QtWidgets.QPushButton("Measure")
        s.register_view_tool("measure", make, restyle=styled.append)
        bar = self.bar()
        self.assertIs(seen[0], bar)
        s.restyle()
        self.assertIs(styled[-1], bar.tools()[0])

    def test_tools_registered_before_install_are_mounted(self):
        s = self.shell
        s.register_view_tool("measure", lambda: QtWidgets.QPushButton("Measure"))
        bar = self.bar()
        self.assertEqual([w.text() for w in bar.tools()], ["Measure"])

    def test_narrow_bar_drops_secondary_last(self):
        bar = self.bar()
        bar.set_level(3)
        self.assertFalse(bar.btn_persp.isVisibleTo(bar))
        self.assertTrue(bar.btn_views.isVisibleTo(bar), "views stay reachable")
        self.assertTrue(bar.btn_fit.isVisibleTo(bar))

    def idle_places(self):
        self.shell.install()
        F.pump(200)
        ov = self.shell._S["overlay"]
        n, orig = [0], ov.place

        def place(force=True):
            n[0] += 1
            return orig(force)
        ov.place = place
        F.pump(300)
        return n[0]

    def test_idle_overlay_does_not_spin(self):
        self.assertEqual(self.idle_places(), 0)

    def test_sabotage_counting_animation_children_spins(self):
        def old_filter(ov, obj, ev):           # the pre-fix eventFilter
            t = ev.type()
            if t in ov._EVENTS or (obj in ov._boxes and t in ov._BOX_EVENTS):
                ov._queue()
            return False
        with mock.patch.object(self.shell.Overlay, "eventFilter", old_filter):
            n = self.idle_places()
        print("\nR303 sabotage: %d idle place() calls in 300 ms" % n)
        if n == 0:
            self.skipTest("this platform's style starts no animations")
        self.assertGreater(n, 0)

    def test_sabotage_without_tool_order_the_slot_is_alphabetical(self):
        s = self.shell
        with mock.patch.object(s, "TOOL_ORDER", ()):
            bar = self.bar()
            for k in ("measure", "section", "export"):
                s.register_view_tool(k, lambda k=k: QtWidgets.QPushButton(k.title()))
            self.assertNotEqual([w.text() for w in bar.tools()],
                                ["Measure", "Section", "Export"])


# ------------------------------------------------------------------ R304
class TestR304NavStyle(Case):
    def test_choice_written_and_preferences_change_adopted(self):
        vp, v = self.viewport, self.fc.ParamGet(VIEW)
        v.SetString("NavigationStyle", "Gui::CADNavigationStyle")   # theirs
        vp.set_nav_style("blender", live=False)
        vp.apply_view_theme()
        self.shell.install()
        self.assertEqual(v.GetString("NavigationStyle"),
                         "Gui::BlenderNavigationStyle")
        # the user picks Touchpad in FreeCAD's Preferences while in Atech
        v.SetString("NavigationStyle", "Gui::TouchpadNavigationStyle")
        self.shell.restyle()                       # a theme flip re-applies
        self.assertEqual(v.GetString("NavigationStyle"),
                         "Gui::TouchpadNavigationStyle", "overwritten")
        self.assertEqual(vp.nav_style(), "Gui::TouchpadNavigationStyle")
        self.shell.uninstall()
        self.assertEqual(v.GetString("NavigationStyle"),
                         "Gui::CADNavigationStyle", "theirs given back")
        # next activation: their restored value is not mistaken for a change
        vp.apply_view_theme()
        self.assertEqual(v.GetString("NavigationStyle"),
                         "Gui::TouchpadNavigationStyle")

    def test_live_set_from_the_panel(self):
        vp, v = self.viewport, self.fc.ParamGet(VIEW)
        self.shell.install()
        self.shell._set_nav("Gui::InventorNavigationStyle")
        self.assertEqual(v.GetString("NavigationStyle"),
                         "Gui::InventorNavigationStyle")
        self.assertEqual(vp.nav_info()["label"], "OpenInventor")
        with self.assertRaises(ValueError):
            vp.set_nav_style("nonsense")

    def test_four_styles_offered(self):
        self.assertEqual([s["label"] for s in self.viewport.NAV_STYLES],
                         ["Gesture", "Blender", "Touchpad", "OpenInventor"])
        self.assertEqual(self.viewport.nav_style(), self.viewport.NAV_STYLE)
        panel = self.shell.appearance_panel()
        self.assertEqual(len(panel.nav_buttons), 4)
        self.assertTrue(panel.nav_buttons["Gui::GestureNavigationStyle"].isChecked())
        panel.deleteLater()

    def test_sabotage_without_adoption_the_choice_is_overwritten(self):
        vp, v = self.viewport, self.fc.ParamGet(VIEW)
        with mock.patch.object(vp, "_adopt_user_nav", lambda *a: False):
            vp.apply_view_theme()
            v.SetString("NavigationStyle", "Gui::TouchpadNavigationStyle")
            vp.apply_view_theme()
            self.assertNotEqual(v.GetString("NavigationStyle"),
                                "Gui::TouchpadNavigationStyle")


# ------------------------------------------------------------------ R305
class TestR305OrbitHint(Case):
    def test_first_run_card_then_never_again(self):
        s = self.shell
        s.install()
        F.pump(30)
        hint = s._S["overlay"].hint
        self.assertTrue(hint.isVisible(), "a document is open: show the card")
        labels = [w.text() for w in hint.findChildren(QtWidgets.QLabel)]
        self.assertIn("Orbit", labels)
        self.assertTrue(any("Drag with the left button" in t for t in labels))
        hint.btn_ok.click()
        s._S["overlay"].place()
        self.assertFalse(hint.isVisible())
        s.uninstall()
        s.install()
        F.pump(30)
        self.assertFalse(s._S["overlay"].hint.isVisible())
        s._show_hint_again()
        self.assertTrue(s._S["overlay"].hint.isVisible())

    def test_card_follows_the_style(self):
        self.viewport.set_nav_style("blender", live=False)
        self.shell.install()
        F.pump(20)
        labels = [w.text() for w in
                  self.shell._S["overlay"].hint.findChildren(QtWidgets.QLabel)]
        self.assertTrue(any("middle button" in t for t in labels), labels)

    def test_sabotage_seen_flag_not_saved(self):
        s = self.shell
        with mock.patch.object(self.viewport, "set_orbit_hint_seen",
                               lambda seen=True: False):
            s.install()
            F.pump(20)
            s._S["overlay"].hint.btn_ok.click()
            s.uninstall()
            s.install()
            F.pump(20)
            self.assertTrue(s._S["overlay"].hint.isVisible())


# ------------------------------------------------------------------ R306
class TestR306Theme(Case):
    def test_dark_choice_moves_freecads_theme(self):
        st, g = self.style, self.fc.ParamGet(MAINWIN)
        g.SetString("Theme", "Atech Atelier Light")
        g.SetString("StyleSheet", "AtechLight.qss")
        self.assertEqual(st.apply_theme_choice("dark", reload=True), "dark")
        self.assertEqual(g.GetString("Theme"), "Atech Atelier Dark")
        self.assertEqual(g.GetString("StyleSheet"), "AtechDark.qss")
        self.assertIn(("Std_ReloadStyleSheet",), self.ran)
        self.assertEqual(st.mode(), "dark")
        self.assertEqual(st.theme_choice(), "dark")

    def test_own_style_sheet_is_kept(self):
        g = self.fc.ParamGet(MAINWIN)
        g.SetString("StyleSheet", "Mine.qss")
        self.style.apply_theme_choice("light", reload=False)
        self.assertEqual(g.GetString("StyleSheet"), "Mine.qss")

    def test_system_follows_the_os(self):
        st, g = self.style, self.fc.ParamGet(MAINWIN)
        g.SetString("Theme", "Atech Atelier Light")
        self.fc.ParamGet(OWN).SetString(st.THEME_KEY, "system")
        with mock.patch.object(st, "system_mode", lambda: "dark"):
            self.assertEqual(st.mode(), "dark")
            self.shell.install()
            self.assertEqual(self.shell._S["mode"], "dark")
        with mock.patch.object(st, "system_mode", lambda: "light"):
            self.shell._on_color_scheme()
            self.assertEqual(self.shell._S["mode"], "light")
            self.assertEqual(g.GetString("Theme"), "Atech Atelier Light")

    def test_unchosen_keeps_the_old_rule(self):
        g = self.fc.ParamGet(MAINWIN)
        g.SetString("Theme", "Atech Atelier Dark")
        with mock.patch.object(self.style, "system_mode", lambda: "light"):
            self.assertEqual(self.style.mode(), "dark")

    def test_panel_switches_theme(self):
        self.shell.install()
        panel = self.shell.appearance_panel()
        panel.theme.set_index(1, emit=True)          # Dark
        self.assertEqual(self.style.theme_choice(), "dark")
        self.assertEqual(self.shell._S["mode"], "dark")
        panel.deleteLater()

    def test_sabotage_without_the_system_branch_mode_ignores_the_os(self):
        st = self.style
        self.fc.ParamGet(MAINWIN).SetString("Theme", "Atech Atelier Light")
        self.fc.ParamGet(OWN).SetString(st.THEME_KEY, "system")
        with mock.patch.object(st, "system_mode", lambda: "dark"), \
                mock.patch.object(st, "theme_choice", lambda: ""):
            self.assertEqual(st.mode(), "light")


# ------------------------------------------------------------------ R307
class TestR307Shortcuts(Case):
    def press(self, key, mods=QtCore.Qt.NoModifier, target=None):
        self.mw.activateWindow()
        self.mw.raise_()
        F.pump(20)
        QtTest.QTest.keyClick(target or self.mw, key, mods)
        F.pump(20)

    def test_all_shortcuts_installed(self):
        s = self.shell
        s.install()
        keys = {i: sc.key().toString() for i, sc in s._S["shortcuts"].items()}
        self.assertEqual(keys["focus_chat"], "Ctrl+L")
        self.assertEqual(keys["tab_cad"], "Ctrl+1")
        self.assertEqual(keys["tab_modules"], "Ctrl+2")
        self.assertEqual(keys["parts"], "Ctrl+P")
        self.assertEqual(keys["measure"], "M")
        self.assertEqual(keys["section"], "Shift+S")
        self.assertEqual(keys["ask"], "Ctrl+Shift+A")
        self.assertEqual(keys["sheet"], "Ctrl+/")
        s.uninstall()
        self.assertNotIn("shortcuts", s._S)

    def test_clashing_menu_key_is_lent_and_given_back(self):
        menu = self.mw.menuBar().addMenu("File2")
        act = menu.addAction("Print")
        act.setShortcut(QtGui.QKeySequence("Ctrl+P"))
        s = self.shell
        s.install()
        self.assertEqual(act.shortcut().toString(), "")
        s.uninstall()
        self.assertEqual(act.shortcut().toString(), "Ctrl+P")

    def test_keys_fire_and_letters_still_type(self):
        s = self.shell
        s.install()
        body = s._S["body"]
        self.press(QtCore.Qt.Key_2, QtCore.Qt.ControlModifier)
        if body.page() != body.PAGE_MODULES:
            self.skipTest("offscreen platform delivered no shortcut events")
        self.press(QtCore.Qt.Key_1, QtCore.Qt.ControlModifier)
        self.assertEqual(body.page(), body.PAGE_CHAT)
        self.press(QtCore.Qt.Key_M)
        self.assertIn(("Std_Measure",), self.ran)
        hits = []
        s.register_view_tool("section", run=lambda: hits.append(1))
        self.press(QtCore.Qt.Key_S, QtCore.Qt.ShiftModifier)
        self.assertEqual(hits, [1])
        # typing an m in a text field is text, not Measure
        self.ran.clear()
        edit = QtWidgets.QLineEdit()
        body.chat.layout() or QtWidgets.QVBoxLayout(body.chat)
        body.chat.layout().addWidget(edit)
        edit.show()
        edit.setFocus()
        F.pump(20)
        QtTest.QTest.keyClick(edit, QtCore.Qt.Key_M)
        F.pump(20)
        self.assertEqual(edit.text(), "m")
        self.assertNotIn(("Std_Measure",), self.ran)

    def test_sabotage_a_clash_left_in_place_fires_nothing(self):
        menu = self.mw.menuBar().addMenu("File2")
        act = menu.addAction("Print")
        act.setShortcut(QtGui.QKeySequence("Ctrl+2"))
        s = self.shell
        s.install()
        body = s._S["body"]
        self.press(QtCore.Qt.Key_2, QtCore.Qt.ControlModifier)
        if body.page() != body.PAGE_MODULES:
            self.skipTest("offscreen platform delivered no shortcut events")
        body.show_page(body.PAGE_CHAT)
        act.setShortcut(QtGui.QKeySequence("Ctrl+2"))     # sabotage: clash back
        self.press(QtCore.Qt.Key_2, QtCore.Qt.ControlModifier)
        self.assertEqual(body.page(), body.PAGE_CHAT, "ambiguous key still fired")

    def test_focus_chat(self):
        s = self.shell
        s.install()
        chat = s.chat_panel()
        chat.input = QtWidgets.QLineEdit(chat)
        chat.input.show()
        s._shortcut_fn("focus_chat")()
        F.pump(20)
        self.assertIs(APP.focusWidget(), chat.input)

    def test_shortcut_sheet(self):
        s = self.shell
        s.install()
        dlg = s.open_shortcut_sheet()
        F.pump(20)
        texts = [w.text() for w in dlg.findChildren(QtWidgets.QLabel)]
        for t in ("Measure", "Section view", "Show these shortcuts",
                  "Fit selection", "Orbit", "KEYBOARD SHORTCUTS".title()):
            self.assertTrue(any(t.lower() == x.lower() for x in texts), t)
        self.assertIn(s.key_text("Ctrl+L"), texts)
        dlg.close()


# ------------------------------------------------------------------ R308
class TestR308Home(Case):
    def store(self, rows=None, boom=False):
        mod = types.ModuleType("acadagent.projects_store")

        def list_projects():
            if boom:
                raise RuntimeError("store broken")
            return rows or []
        mod.list_projects = list_projects
        import acadagent
        return mock.patch.dict(sys.modules, {"acadagent.projects_store": mod}), \
            mock.patch.object(acadagent, "projects_store", mod, create=True)

    def no_store(self):
        import acadagent
        patches = [mock.patch.dict(sys.modules, {"acadagent.projects_store": None})]
        if hasattr(acadagent, "projects_store"):
            patches.append(mock.patch.object(acadagent, "projects_store", None))
        return patches

    def test_normalize_dedupes_sorts_and_drops_missing(self):
        a = make_fcstd(os.path.join(self.tmp, "a.FCStd"))
        b = make_fcstd(os.path.join(self.tmp, "b.FCStd"))
        link = os.path.join(self.tmp, "link.FCStd")
        os.symlink(a, link)
        rows = self.shell.normalize_projects([
            {"path": a, "mtime": 100}, {"path": link, "mtime": 300},
            {"path": b, "modified": 200, "electronics": True},
            {"path": os.path.join(self.tmp, "gone.FCStd"), "mtime": 999}])
        self.assertEqual([os.path.basename(r["path"]) for r in rows],
                         ["b.FCStd", "a.FCStd"])
        self.assertTrue(rows[0]["electronics"])

    def test_sabotage_without_realpath_the_same_file_shows_twice(self):
        a = make_fcstd(os.path.join(self.tmp, "a.FCStd"))
        link = os.path.join(self.tmp, "link.FCStd")
        os.symlink(a, link)
        with mock.patch.object(self.shell.os.path, "realpath", lambda p: p):
            rows = self.shell.normalize_projects([{"path": a}, {"path": link}])
        self.assertEqual(len(rows), 2)

    def test_fallback_reads_recent_files_with_thumbnail_and_chip(self):
        a = make_fcstd(os.path.join(self.tmp, "robot.FCStd"), hardware=True)
        b = make_fcstd(os.path.join(self.tmp, "vase.FCStd"), thumb=False)
        grp = self.fc.ParamGet(RECENT)
        grp.SetString("MRU0", a)
        grp.SetString("MRU1", b)
        grp.SetString("MRU2", a)
        patches = self.no_store()
        for p in patches:
            p.start()
        try:
            home = self.shell.HomeView()
            home.resize(1000, 700)
            home.restyle()
            self.assertEqual(home.source, "recent")
            names = {c.row["name"]: c for c in home.project_cards}
            self.assertEqual(sorted(names), ["robot", "vase"])
            self.assertTrue(names["robot"].chip.isVisibleTo(names["robot"]))
            self.assertFalse(names["vase"].chip.isVisibleTo(names["vase"]))
            self.assertIsNotNone(names["robot"].thumbnail())
            self.assertIsNone(names["vase"].thumbnail())
            self.assertEqual(names["robot"].accessibleName(), "Open project robot")
            self.assertIs(home.grid.itemAtPosition(0, 0).widget(), home.new_card)
        finally:
            for p in patches:
                p.stop()

    def test_store_rows_are_used_and_a_broken_store_falls_back(self):
        a = make_fcstd(os.path.join(self.tmp, "a.FCStd"))
        p1, p2 = self.store([{"path": a, "name": "Lamp", "mtime": time.time()}])
        with p1, p2:
            rows, src = self.shell.home_projects()
        self.assertEqual((src, rows[0]["name"]), ("store", "Lamp"))
        p1, p2 = self.store(boom=True)
        with p1, p2:
            rows, src = self.shell.home_projects()
        self.assertEqual(src, "recent")

    def test_search_filters(self):
        paths = [make_fcstd(os.path.join(self.tmp, n + ".FCStd"))
                 for n in ("Desk lamp", "Robot arm", "Lamp shade")]
        p1, p2 = self.store([{"path": p} for p in paths])
        with p1, p2:
            home = self.shell.HomeView()
            home.resize(1000, 700)
            home.show()
            F.pump(10)
            home.search.setText("lamp")
            shown = [c.row["name"] for c in home.project_cards if c.isVisible()]
            self.assertEqual(sorted(shown), ["Desk lamp", "Lamp shade"])
            home.search.setText("zzz")
            self.assertIn("No project matches", home.note.text())
            home.close()

    def test_examples_and_product_name(self):
        home = self.shell.HomeView()
        keys = [c.example_key for c in home.example_cards]
        self.assertEqual(keys, ["toy_car", "desk_robot", "smart_speaker"])
        self.assertEqual(home.title.text(), "Atech Atelier")
        home.restyle()
        self.assertTrue(home.credit.text().startswith("Atech Atelier"))

    def test_home_is_the_empty_state(self):
        mdi = self.mw.centralWidget()
        for sw in mdi.subWindowList():
            sw.close()
        F.pump(20)
        self.shell.install()
        F.pump(30)
        ov = self.shell._S["overlay"]
        self.assertIsInstance(ov.empty, self.shell.HomeView)
        self.assertTrue(ov.empty.isVisible())
        self.assertFalse(ov.bar.isVisible())

    def test_hundred_projects_under_a_second(self):
        paths = [make_fcstd(os.path.join(self.tmp, "p%03d.FCStd" % i),
                            hardware=i % 3 == 0) for i in range(100)]
        rows = [{"path": p, "mtime": 1000 + i} for i, p in enumerate(paths)]
        self.shell._PEEK.clear()
        p1, p2 = self.store(rows)
        with p1, p2:
            t0 = time.time()
            home = self.shell.HomeView()
            home.resize(1200, 800)
            home.restyle()
            home.show()
            F.pump(1)
            dt = time.time() - t0
        print("\nR308 Home with 100 projects: %.3f s" % dt)
        self.assertEqual(len(home.project_cards), 100)
        self.assertEqual(home.project_cards[0].row["name"], "p099")
        self.assertLess(dt, 1.0)
        home.close()

    def test_edited_text(self):
        e = self.shell.edited_text
        self.assertEqual(e(1000, 1030), "Edited just now")
        self.assertEqual(e(1000, 1000 + 600), "Edited 10 min ago")
        self.assertEqual(e(1000, 1000 + 7200), "Edited 2 h ago")
        self.assertEqual(e(1000, 1000 + 90000), "Edited yesterday")
        self.assertEqual(e(1000, 1000 + 3 * 86400), "Edited 3 days ago")


# ------------------------------------------------------------------ R309
class _Doc:
    def __init__(self, name):
        self.Name, self.Label, self.FileName = name, name, ""

    def recompute(self):
        pass


class TestR309Open(Case):
    def setUp(self):
        super().setUp()
        self.inserted, self.opened, self.docs = [], [], {}

        def new_doc(name="Unnamed"):
            d = _Doc(name)
            self.docs[name] = d
            self.fc.ActiveDocument = d
            return d
        self.fc.newDocument = new_doc
        self.fc.listDocuments = lambda: dict(self.docs)
        self.gui.insert = lambda path, name: self.inserted.append((path, name))
        self.gui.open = lambda path: self.opened.append(path)
        # R391: a .FCStd opens with FreeCAD.openDocument (FreeCADGui.open
        # ignores .FCStd in FreeCAD 1.1.3), so record that path too
        self.fc.openDocument = lambda path, *a: self.opened.append(path)

    def file(self, name):
        p = os.path.join(self.tmp, name)
        if name.lower().endswith(".fcstd"):
            return make_fcstd(p)
        with open(p, "w") as fh:
            fh.write("solid x\nendsolid x\n")
        return p

    def test_droppable(self):
        files = [self.file(n) for n in ("a.FCStd", "b.step", "c.STL", "d.3mf",
                                        "e.txt", "f.stp")]
        got = [os.path.basename(p) for p in self.shell.droppable(
            files + [os.path.join(self.tmp, "missing.step")])]
        self.assertEqual(got, ["a.FCStd", "b.step", "c.STL", "d.3mf", "f.stp"])

    def test_mesh_and_step_become_new_projects(self):
        s = self.shell
        for n in ("bracket.step", "case.stl", "lid.3mf"):
            name = s.open_path(self.file(n))
            stem = os.path.splitext(n)[0]
            self.assertEqual(self.docs[name].Label, stem)
            self.assertEqual(self.inserted[-1], (os.path.join(self.tmp, n), name))
        self.assertEqual(s._doc_name_for("3 way-valve"), "_3_way_valve")

    def test_fcstd_opens_or_switches(self):
        p = self.file("hub.FCStd")
        self.shell.open_path(p)
        self.assertEqual(self.opened, [p])
        d = self.fc.newDocument("Hub")
        d.FileName = p
        with mock.patch.object(self.shell, "activate_document") as act:
            self.shell.open_project_path(p)
        act.assert_called_once_with("Hub")
        self.assertEqual(self.opened, [p], "already open: switched, not reopened")

    def drop_event(self, paths, kind=QtCore.QEvent.Drop):
        md = QtCore.QMimeData()
        md.setUrls([QtCore.QUrl.fromLocalFile(p) for p in paths])
        self._mimes = getattr(self, "_mimes", []) + [md]   # the event does not own it
        if kind == QtCore.QEvent.Drop:
            return QtGui.QDropEvent(QtCore.QPointF(5, 5), QtCore.Qt.CopyAction, md,
                                    QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
        return QtGui.QDragEnterEvent(QtCore.QPoint(5, 5), QtCore.Qt.CopyAction, md,
                                     QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)

    def test_drop_on_the_window(self):
        s = self.shell
        s.install()
        p = self.file("gear.3mf")
        enter = self.drop_event([p], QtCore.QEvent.DragEnter)
        self.assertTrue(s._S["drops"].eventFilter(self.mw, enter))
        self.assertTrue(enter.isAccepted())
        ev = self.drop_event([p, self.file("notes.txt")])
        self.assertTrue(s._S["drops"].eventFilter(self.mw, ev))
        F.pump(20)
        self.assertEqual([os.path.basename(x) for x, _n in self.inserted], ["gear.3mf"])
        # a drop that is not ours goes on to FreeCAD
        self.assertFalse(s._S["drops"].eventFilter(
            self.mw, self.drop_event([self.file("x.txt")])))

    def test_drop_on_home(self):
        home = self.shell.HomeView()
        p = self.file("arm.step")
        home.dropEvent(self.drop_event([p]))
        self.assertEqual(self.inserted[-1][0], p)

    def test_sabotage_without_3mf_it_is_not_opened(self):
        p = self.file("gear.3mf")
        with mock.patch.object(self.shell, "IMPORT_EXT",
                               (".step", ".stp", ".stl")):
            self.assertEqual(self.shell.open_paths([p]), [])
        self.assertEqual(self.inserted, [])


# ------------------------------------------------------------------ R310
class _Pending:
    def __init__(self, ok=True):
        self.n = 0
        self.ok = ok

    def poll(self):
        self.n += 1
        if self.n < 2:
            return None
        return types.SimpleNamespace(ok=self.ok, error="boom")


class TestR310Examples(Case):
    def setUp(self):
        super().setUp()
        self.docs = {}

        def new_doc(name="Unnamed"):
            d = _Doc(name)
            d.Uid = "uid-" + name
            self.docs[name] = d
            return d
        self.fc.newDocument = new_doc
        self.started = []
        b = types.ModuleType("acadagent.build")
        b.SCRIPT = "model.py"
        b.new_workspace = lambda: tempfile.mkdtemp(dir=self.tmp)
        b.prepare_workspace = lambda ws, reset_intent=True, doc=None: []
        b._doc_key = lambda d: d.Uid

        self.ok = True

        def start(ws, files, previous=None, **kw):
            self.started.append((ws, files, previous))
            return _Pending(self.ok)
        b.start = start
        import acadagent
        self.patches = [mock.patch.dict(sys.modules, {"acadagent.build": b}),
                        mock.patch.object(acadagent, "build", b, create=True)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        super().tearDown()

    def test_example_builds_into_a_new_project(self):
        s = self.shell
        s.install()
        fits = []
        with mock.patch.object(self.viewport, "iso_and_fit", lambda: fits.append(1)):
            pending = s.open_example("toy_car")
            self.assertIsNotNone(pending)
            ws, files, prev = self.started[0]
            self.assertEqual(files, ["model.py"])
            doc = self.docs["Toy_car"]
            self.assertEqual(doc.Label, "Toy car")
            self.assertEqual(prev, {"uid": "uid-Toy_car"})
            with open(os.path.join(ws, "model.py")) as fh, \
                    open(s.example_path("toy_car")) as src:
                self.assertEqual(fh.read(), src.read())
            with open(os.path.join(ws, "intent.json")) as fh:
                self.assertEqual(json.load(fh)["board"], "flat")
            F.pump(600)
        self.assertEqual(fits, [1], "framed once built")
        self.assertEqual(s._EXAMPLE_RUNS, [])

    def test_all_three_examples_exist(self):
        for k in ("toy_car", "desk_robot", "smart_speaker"):
            self.assertTrue(self.shell.example_path(k), k)
            self.assertIsNotNone(self.shell._example_intent(self.shell.example_path(k)))

    def test_chat_panel_can_take_over(self):
        s = self.shell
        s.install()
        got = []
        s.chat_panel().start_from_example = lambda path, title: got.append((path, title))
        s.open_example("smart_speaker")
        self.assertEqual(got[0][1], "Smart speaker")
        self.assertEqual(self.started, [])

    def test_failed_build_is_a_notice(self):
        s = self.shell
        s.install()
        self.ok = False
        s.open_example("desk_robot")
        F.pump(600)
        self.assertEqual(s.chat_panel().notices[-1][0],
                         "The desk robot example did not build")

    def test_sabotage_missing_example_says_so(self):
        s = self.shell
        s.install()
        with mock.patch.object(s, "example_path", lambda k: None):
            self.assertIsNone(s.open_example("toy_car"))
        self.assertEqual(s.chat_panel().notices[-1][0], "Example not available")
        self.assertEqual(self.started, [])


# --------------------------------------------- real FreeCAD (headless)
FC_SCRIPT = r'''
import os, sys, zipfile
import FreeCAD
out = sys.argv[-1] if sys.argv[-1].endswith(".dir") else os.environ["R12_OUT"]
d = FreeCAD.newDocument("HW")
b = d.addObject("Part::Box", "Board")
b.addProperty("App::PropertyString", "AtechRole", "Atech")
b.AtechRole = "board"
d.recompute()
d.saveAs(os.path.join(out, "hw.FCStd"))
p = FreeCAD.newDocument("Plain")
p.addObject("Part::Box", "Box")
p.recompute()
p.saveAs(os.path.join(out, "plain.FCStd"))
print("R12_SAVED_OK")
'''


@unittest.skipUnless(os.path.isfile(FREECADCMD), "no freecadcmd")
class TestR308RealFCStd(unittest.TestCase):
    """The Electronics chip reads a .FCStd that FreeCAD itself saved."""

    def test_atech_role_detected_in_a_saved_file(self):
        out = tempfile.mkdtemp(prefix="atech-r12-fc-")
        script = os.path.join(out, "save.py")
        with open(script, "w") as fh:
            fh.write(FC_SCRIPT)
        env = dict(os.environ, R12_OUT=out,
                   ATECH_ARTIFACTS=os.path.join(REPO, "models"))
        p = subprocess.run([FREECADCMD, script], env=env, capture_output=True,
                           text=True, timeout=300)
        text = p.stdout + p.stderr
        if "R12_SAVED_OK" not in text:
            self.fail("freecadcmd did not save:\n" + text[-2000:])
        from acadagent import shell
        shell._PEEK.clear()
        self.assertTrue(shell._fcstd_peek(os.path.join(out, "hw.FCStd"))[1])
        self.assertFalse(shell._fcstd_peek(os.path.join(out, "plain.FCStd"))[1])
        shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
