"""Wave-1 integration (R380-R387), headless: the workstreams' pieces wired
into the shell, the picker and the chat panel.

    R380  View bar tools: Measure + Section (measure.py) and Colour,
          Exploded view, Export for print, Share image (export_tools.py)
          in two groups; a narrow bar moves the less used ones into a
          "More tools" menu; M / Shift+S press the same buttons.
    R381  Right-click menu of the 3D view and the tree: Hide / Isolate /
          Show all / See-through, Colour, Measure, Section, and an "Export
          and share" submenu, on the Atech workbench only.
    R382  Document events: an exploded view is put back before a save;
          a file opened from disk gets its hand-edit baseline once.
    R383  The fallback start page's "New" card uses the named-project flow.
    R384  navbar.activate_document matches the window by document Name
          (through shell.activate_document), not by a title prefix.
    R385  Home project cards have a menu: Open, Rename, Duplicate, Show in
          Finder, Move to Trash (asks first).
    R386  The chat header shows the unsaved dot.
    R387  Agent builds: hand edits captured before, re-applied after
          (export_tools), measurements re-measured after a final build.

Each block has a sabotage test: the wiring broken on purpose, the check
seen to fail.

    cd addon/AcadAgent/tests && QT_QPA_PLATFORM=offscreen \\
      ".../Atech Atelier.app/Contents/Resources/bin/python" \\
      -m unittest test_integration_r380 -v
"""
import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

_TMP = tempfile.mkdtemp(prefix="atech-r380-")
os.environ["HOME"] = os.path.join(_TMP, "home")
os.makedirs(os.environ["HOME"], exist_ok=True)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import _shell_fakes as F  # noqa: E402
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

# The real chat panel, imported before the shell tests swap in stubs.
from acadagent import panel as real_panel  # noqa: E402
from acadagent import export_tools, inspect_tools  # noqa: E402

from test_shell_lifecycle import ShellCase  # noqa: E402
from test_shell_round12 import FakeView  # noqa: E402

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _replaced(func, old, new):
    """`func` recompiled from its shipped source with `old` replaced by
    `new`: the sabotage build of a fix."""
    import inspect
    import textwrap
    src = textwrap.dedent(inspect.getsource(func))
    assert old in src, "sabotage changed nothing"
    ns = {}
    exec(src.replace(old, new), func.__globals__, ns)   # noqa: S102
    return ns[func.__name__]


class Case(ShellCase):
    def setUp(self):
        super().setUp()
        self.view = FakeView()
        self.gui.ActiveDocument = types.SimpleNamespace(ActiveView=self.view)
        self.gui.Selection = types.SimpleNamespace(getSelection=lambda: [])
        self.ran = []
        self.gui.runCommand = lambda name, *a: self.ran.append((name,) + a)
        self.shell._TOOLS.clear()
        self.shell.register_builtin_tools()

    def tearDown(self):
        self.shell._TOOLS.clear()
        self.shell.register_builtin_tools()
        super().tearDown()

    def bar(self):
        self.shell.install()
        F.pump(30)
        return self.shell._S["overlay"].bar


# ------------------------------------------------------------------ R380
class TestR380ViewBarTools(Case):
    # R700/R701 added Show and hide and Dimensions, and moved Exploded
    # view in with the ways of looking.
    # R800: Edit shapes (manual_edit.py) sits after Dimensions.
    # R810/R811: Simulate after Exploded view, Make assembly video last.
    KEYS = ["measure", "section", "show", "explode", "simulate", "dims", "shape",
            "colour", "export", "share", "video"]

    def test_six_tools_in_order_with_names_and_icons(self):
        bar = self.bar()
        keys = [w.property("atechTool") for w in bar.tools()]
        self.assertEqual(keys, self.KEYS)
        names = [w.accessibleName() for w in bar.tools()]
        self.assertEqual(names, ["Measure", "Section view", "Show and hide",
                                 "Exploded view", "Simulate", "Dimensions",
                                 "Edit shapes", "Colour",
                                 "Export for print", "Save a share image",
                                 "Make assembly video"])
        for w in bar.tools():
            self.assertEqual(w.objectName(), "VBtn")
            self.assertTrue(w.toolTip())
            self.assertFalse(w.icon().isNull(), w.accessibleName())
        self.assertTrue(bar.tools()[0].isCheckable(), "Measure toggles")

    def test_two_groups_split_by_a_line(self):
        bar = self.bar()
        bar.set_level(0)
        self.assertTrue(bar._group_sep.isVisibleTo(bar))
        lay = bar.tool_slot
        order = [lay.itemAt(i).widget() for i in range(lay.count())]
        i_sep = order.index(bar._group_sep)
        self.assertEqual([w.property("atechTool") for w in order[:i_sep]],
                         ["measure", "section", "show", "explode", "simulate"])

    def levels(self, bar):
        out = {}
        for lvl in range(bar.MAX_LEVEL + 1):
            bar.set_level(lvl)
            bar.adjustSize()
            out[lvl] = (bar.sizeHint().width(), list(bar.dropped_tools()),
                        bar.btn_more_tools.isVisibleTo(bar))
        bar.set_level(0)
        return out

    def check_narrow(self, bar):
        """True when narrowing the bar moves tools into More tools and
        each level is narrower than the last."""
        lv = self.levels(bar)
        widths = [lv[i][0] for i in sorted(lv)]
        return (lv[0][1] == [] and not lv[0][2]
                and lv[1][1] == ["dims", "share", "video"] and lv[1][2]
                and lv[2][1] == ["explode", "simulate", "dims", "shape", "colour",
                                 "export", "share", "video"]
                and all(a > b for a, b in zip(widths, widths[1:])))

    def test_narrow_bar_moves_tools_into_more_tools(self):
        bar = self.bar()
        self.assertTrue(self.check_narrow(bar), self.levels(bar))
        bar.set_level(3)
        for k in ("measure", "section"):
            self.assertTrue(bar._tool_widgets[k].isVisibleTo(bar))
        self.assertFalse(bar._group_sep.isVisibleTo(bar),
                         "no line after the last visible group")

    def test_sabotage_without_level_rules_nothing_moves(self):
        bar = self.bar()
        with mock.patch.object(self.shell.ViewBar, "_apply_tool_level",
                               lambda self: None):
            self.assertFalse(self.check_narrow(bar))

    def test_more_tools_menu_presses_the_dropped_button(self):
        s = self.shell
        hits = []

        def make(view_bar):
            b = QtWidgets.QPushButton("")
            b.setAccessibleName("Save a share image")
            b.clicked.connect(lambda: hits.append(1))
            return b
        s.register_view_tool("share", make, label="Save a share image")
        bar = self.bar()
        bar.set_level(1)
        self.assertEqual(bar._fill_more_tools(),
                         ["Dimensions", "Save a share image", "Make assembly video"])
        acts = {a.text(): a for a in bar.more_menu.actions()}
        acts["Save a share image"].trigger()
        self.assertEqual(hits, [1])

    def test_m_and_shift_s_press_the_bar_buttons(self):
        s = self.shell
        bar = self.bar()
        pressed = []
        for k in ("measure", "section"):
            w = bar._tool_widgets[k]
            w.toggled.disconnect()          # the cards need a real 3D view
            w.clicked.connect(lambda _=False, k=k: pressed.append(k))
        s._shortcut_fn("measure")()
        s._shortcut_fn("section")()
        self.assertEqual(pressed, ["measure", "section"])
        self.assertEqual(self.ran, [], "FreeCAD's own commands not run")

    def test_without_a_bar_m_runs_freecads_measure(self):
        s = self.shell
        self.assertFalse(s.installed())
        s._shortcut_fn("measure")()
        s._shortcut_fn("section")()
        self.assertEqual(self.ran, [("Std_Measure",), ("Std_ToggleClipPlane",)])

    def test_sabotage_click_tool_off_falls_back_to_freecad(self):
        s = self.shell
        self.bar()
        with mock.patch.object(s, "click_tool", lambda k: False):
            s._shortcut_fn("measure")()
        self.assertEqual(self.ran, [("Std_Measure",)],
                         "with the press broken, M is FreeCAD's measure")

    def test_restyle_recolours_the_tool_icons(self):
        bar = self.bar()
        before = bar._tool_widgets["export"].icon().cacheKey()
        self.shell.restyle()
        self.assertNotEqual(bar._tool_widgets["export"].icon().cacheKey(),
                            before)


# ------------------------------------------------------------------ R381
class FakeWB(object):
    def __init__(self):
        self.menus = []

    def appendContextMenu(self, name, items):          # noqa: N802
        self.menus.append((name, list(items) if not isinstance(items, str)
                           else [items]))


class TestR381ContextMenu(Case):
    def flat(self, wb):
        return [c for name, items in wb.menus if name == "" for c in items]

    def test_view_menu_items(self):
        wb = FakeWB()
        self.assertTrue(self.shell.context_menu(wb, "View", gui=False))
        root = self.flat(wb)
        for c in ("Atech_Hide", "Atech_Isolate", "Atech_ShowAll",
                  "Atech_SeeThrough", "Atech_Colour", "Atech_Measure",
                  "Atech_Section"):
            self.assertIn(c, root)
        sub = dict(wb.menus)[self.shell.EXPORT_MENU]
        self.assertEqual(sub, ["Atech_ExportForPrint", "Atech_ExplodedView",
                               "Atech_BillOfMaterials", "Atech_ShareImage",
                               "Atech_ReviewSheet"])

    def test_tree_menu_and_other_recipients(self):
        wb = FakeWB()
        self.assertTrue(self.shell.context_menu(wb, "Tree", gui=False))
        root = self.flat(wb)
        self.assertIn("Atech_Hide", root)
        self.assertIn("Atech_Colour", root)
        self.assertNotIn("Atech_Measure", root)
        wb2 = FakeWB()
        self.assertFalse(self.shell.context_menu(wb2, "Selection", gui=False))
        self.assertEqual(wb2.menus, [])

    def test_sabotage_without_inspect_commands_hide_is_missing(self):
        wb = FakeWB()
        with mock.patch.object(inspect_tools, "CONTEXT_COMMANDS", []):
            self.shell.context_menu(wb, "View", gui=False)
        self.assertNotIn("Atech_Hide", self.flat(wb))

    def test_installed_on_the_workbench_and_removed(self):
        s = self.shell

        class WB(FakeWB):
            pass
        wb = WB()
        self.gui.getWorkbench = lambda name: wb
        self.gui.listCommands = lambda: []
        added = []
        self.gui.addCommand = lambda cid, cmd: added.append((cid, cmd))
        s.install()
        self.assertTrue(callable(getattr(wb, "ContextMenu", None)))
        with mock.patch.object(inspect_tools, "register_commands", lambda: None):
            wb.ContextMenu("View")
        self.assertIn("Atech_Measure", self.flat(wb))
        self.assertEqual(len(added), 9)          # R700 added Dimensions...
        s.uninstall()
        self.assertFalse(hasattr(wb, "ContextMenu"))

    def test_a_class_with_its_own_context_menu_is_left_alone(self):
        class Own(FakeWB):
            def ContextMenu(self, recipient):           # noqa: N802
                return "own"
        wb = Own()
        self.assertFalse(self.shell._install_context_menu(wb))
        self.assertEqual(wb.ContextMenu("View"), "own")

    def test_commands_need_a_document(self):
        s = self.shell
        self.assertFalse(s.command_enabled("export", None))
        self.assertTrue(s.command_enabled("export", object()))
        self.assertFalse(s.command_enabled("colour", object(), []))
        self.assertTrue(s.command_enabled("colour", object(), [1]))
        cmd = s._AtechCommand("Export", "tip", "export")
        self.assertFalse(cmd.IsActive(), "no document open")
        self.assertEqual(cmd.GetResources()["MenuText"], "Export")

    def test_menu_actions_reach_the_tools(self):
        s = self.shell
        bar = self.bar()
        hits = []
        for k in ("export",):
            w = bar._tool_widgets[k]
            w.clicked.disconnect()
            w.clicked.connect(lambda _=False, k=k: hits.append(k))
        s.run_command_action("export")
        self.assertEqual(hits, ["export"])
        # R720: the menu's "Exploded view (E)" toggles like the bar and E
        # (no separate slider window with its own state)
        with mock.patch.object(export_tools, "toggle_explode") as tx, \
                mock.patch.object(export_tools, "ExplodeDialog") as xd:
            s.run_command_action("explode")
        tx.assert_called_once()
        xd.assert_not_called()
        with mock.patch.object(export_tools, "BomDialog") as bom:
            s.run_command_action("bom")
        bom.assert_called_once()


# ------------------------------------------------------------------ R382
class TestR382DocEvents(Case):
    def test_exploded_view_put_back_before_save(self):
        doc = types.SimpleNamespace(Name="D", FileName="")
        obs = self.shell._DocObserver(lambda: None)
        with mock.patch.object(export_tools, "restore_exploded") as rest:
            obs.slotStartSaveDocument(doc, "/tmp/x.FCStd")
        rest.assert_called_once_with(doc)

    def test_sabotage_without_the_save_slot_nothing_is_put_back(self):
        class Old(self.shell._DocObserver):
            def slotStartSaveDocument(self, doc, _f=None):  # noqa: N802
                return None
        with mock.patch.object(export_tools, "restore_exploded") as rest:
            Old(lambda: None).slotStartSaveDocument(object(), "x")
        rest.assert_not_called()

    def test_baseline_once_per_opened_file(self):
        s = self.shell
        s._BASED.clear()
        doc = types.SimpleNamespace(Name="D", FileName="/p/a.FCStd")
        with mock.patch.object(export_tools, "ensure_base",
                               return_value=["Lid"]) as eb:
            self.assertEqual(s._note_opened(doc), ["Lid"])
            self.assertIsNone(s._note_opened(doc))
        eb.assert_called_once_with(doc)


# ------------------------------------------------------------- R383/R384
def old_navbar_activate(mdi, label):
    """The pre-R384 navbar rule: the first window titled '<label> :'."""
    for sw in mdi.subWindowList():
        t = sw.windowTitle()
        if t.startswith(label + " :") or t.startswith(label + " "):
            return sw
    return None


class TestR384Picker(Case):
    def setup_two(self):
        self.shell.install()
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
        return mdi, a, b

    def test_picker_switch_matches_the_document_name(self):
        from acadagent import navbar
        mdi, a, b = self.setup_two()
        self.assertTrue(navbar.activate_document("Same001"))
        self.assertIs(mdi.activeSubWindow(), b)
        self.assertTrue(navbar.activate_document("Same"))
        self.assertIs(mdi.activeSubWindow(), a)

    def test_sabotage_the_old_title_rule_picks_the_wrong_copy(self):
        mdi, a, b = self.setup_two()
        self.assertIsNot(old_navbar_activate(mdi, "Same"), b,
                         "the old rule cannot reach Same001")

    def test_fallback_new_card_uses_the_named_flow(self):
        s = self.shell
        from acadagent import navbar
        page = s.EmptyView()
        calls = []
        with mock.patch.object(navbar, "new_project_flow",
                               lambda parent=None: calls.append(1)):
            page.cards[1].clicked.emit()
        self.assertEqual(calls, [1])


# ------------------------------------------------------------------ R385
class TestR385HomeCardMenu(Case):
    PATH = "/projects/Rover.FCStd"

    def card(self):
        return self.shell.ProjectCard({"path": self.PATH, "name": "Rover",
                                       "mtime": 0})

    def test_menu_entries(self):
        m = self.card().menu()
        texts = [a.text() for a in m.actions() if not a.isSeparator()]
        self.assertEqual(texts, ["Open", "Rename…", "Duplicate",
                                 "Show in Finder", "Move to Trash…"])

    def test_actions_call_the_store_with_the_path(self):
        s = self.shell
        from acadagent import projects_store as ps
        with mock.patch.object(ps, "rename_project", return_value="/n") as rn, \
                mock.patch.object(ps, "duplicate_project", return_value="/d") as dp, \
                mock.patch.object(ps, "reveal_in_finder") as rv, \
                mock.patch.object(s, "open_project_path") as op:
            self.assertEqual(s.home_card_action(
                "rename", self.PATH, ask=lambda *a: "Rover 2"), "/n")
            rn.assert_called_once_with(self.PATH, "Rover 2")
            self.assertIsNone(s.home_card_action(
                "rename", self.PATH, ask=lambda *a: None))
            self.assertEqual(s.home_card_action("duplicate", self.PATH), "/d")
            dp.assert_called_once_with(self.PATH)
            s.home_card_action("reveal", self.PATH)
            rv.assert_called_once_with(self.PATH)
            s.home_card_action("open", self.PATH)
            op.assert_called_once_with(self.PATH)

    def check_trash_asks(self, fn):
        from acadagent import projects_store as ps
        with mock.patch.object(ps, "trash_project") as tr:
            fn("trash", self.PATH, confirm=lambda *a: False)
            refused = not tr.called
            fn("trash", self.PATH, confirm=lambda *a: True)
            done = tr.call_count == 1
        return refused and done

    def test_trash_asks_first(self):
        self.assertTrue(self.check_trash_asks(self.shell.home_card_action))

    def test_sabotage_without_the_question_trash_is_immediate(self):
        broken = _replaced(self.shell.home_card_action, "if not confirm(",
                           "if False and not confirm(")
        self.assertFalse(self.check_trash_asks(broken))

    def test_store_error_is_said_in_words(self):
        s = self.shell
        from acadagent import projects_store as ps
        said = []
        with mock.patch.object(ps, "duplicate_project",
                               side_effect=ps.ProjectError("No room.")), \
                mock.patch.object(s, "_notify",
                                  lambda t, b, exc=None: said.append(b)):
            self.assertIsNone(s.home_card_action("duplicate", self.PATH))
        self.assertEqual(said, ["No room."])


# ------------------------------------------------------------- R386/R387
class Doc(object):
    Name = "D"
    Label = "Rover"
    Objects = []
    FileName = ""


class PanelCase(unittest.TestCase):
    def setUp(self):
        sys.modules["acadagent.panel"] = real_panel
        self.p = real_panel.AgentPanel()
        t0 = QtCore.QElapsedTimer()
        t0.start()
        while self.p._backend_state == "checking" and t0.elapsed() < 10000:
            F.pump(20)

    def tearDown(self):
        try:
            from acadagent import claude_cli
            claude_cli.ClaudeRun.shutdown_all(2000)
        except Exception:                              # noqa: BLE001
            pass
        for t in self.p.findChildren(QtCore.QThread):
            t.wait(5000)
        self.p.deleteLater()
        F.pump(20)


class TestR386UnsavedDot(PanelCase):
    def show(self, modified):
        doc = Doc()
        with mock.patch.object(self.p, "_active_document", lambda: doc), \
                mock.patch.object(real_panel.projects_store, "is_modified",
                                  lambda d: modified):
            self.p.refresh_doc_pill(force=True)
        return self.p.doc_unsaved.isVisibleTo(self.p)

    def test_dot_follows_the_unsaved_state(self):
        self.assertTrue(self.show(True))
        self.assertEqual(self.p.doc_name.accessibleDescription(),
                         "Unsaved changes")
        self.assertEqual(self.p.doc_unsaved.accessibleName(), "Unsaved changes")
        self.assertFalse(self.show(False))
        self.assertEqual(self.p.doc_name.text(), "Rover", "name unchanged")

    def test_signature_changes_with_the_unsaved_state(self):
        doc = Doc()
        sigs = []
        for mod in (False, True):
            with mock.patch.object(real_panel.projects_store, "is_modified",
                                   lambda d, m=mod: m):
                sigs.append(self.p._doc_signature(doc))
        self.assertNotEqual(sigs[0], sigs[1])

    def test_sabotage_signature_without_the_flag_misses_the_change(self):
        doc = Doc()
        sigs = []
        for mod in (False, True):
            with mock.patch.object(real_panel.projects_store, "is_modified",
                                   lambda d, m=mod: m), \
                    mock.patch.object(real_panel.AgentPanel, "_unsaved",
                                      staticmethod(lambda d: False)):
                sigs.append(self.p._doc_signature(doc))
        self.assertEqual(sigs[0], sigs[1])


class _Res(object):
    def __init__(self, ok=True):
        self.ok = ok
        self.error = ""


class _Pending(object):
    def __init__(self, res):
        self.res = res

    def poll(self):
        return self.res


class TestR387BuildHooks(PanelCase):
    def run_build(self, ok=True, preview=False):
        p, doc, order = self.p, Doc(), []
        state = types.SimpleNamespace(ws=_TMP, key="k", good_hash=None)
        p._cur = state
        p._doc_was_closed = lambda s: False
        p._state_doc = lambda s: doc
        p._activate_state_doc = lambda s: None
        p._script_hash = lambda ws: "h"
        p._build_advanced = lambda: None

        def start(st, files, pv):
            order.append("build")
            return _Pending(_Res(ok))
        p._start = start
        p._settle = lambda *a: order.append("settle")
        with mock.patch.object(export_tools, "capture_overrides",
                               lambda d: order.append("capture")), \
                mock.patch.object(export_tools, "reapply_overrides",
                                  lambda d: order.append("reapply")):
            from acadagent import measure
            with mock.patch.object(measure, "refresh",
                                   lambda d: order.append("remeasure")):
                p._run_build(["model.py"], preview=preview, send_fix=False)
                F.pump(20)
        return order

    def test_final_build_order(self):
        self.assertEqual(self.run_build(),
                         ["capture", "build", "reapply", "settle", "remeasure"])

    def test_preview_reapplies_but_does_not_remeasure(self):
        self.assertEqual(self.run_build(preview=True),
                         ["capture", "build", "reapply", "settle"])

    def test_failed_build_reapplies_nothing(self):
        self.assertEqual(self.run_build(ok=False),
                         ["capture", "build", "settle"])

    def test_sabotage_without_reapply_hand_edits_are_lost(self):
        with mock.patch.object(real_panel.AgentPanel, "_reapply_hand_edits",
                               lambda self, s, preview=False: None):
            order = self.run_build()
        self.assertNotIn("reapply", order)


def tearDownModule():
    shutil.rmtree(_TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
