"""R700 hand-edited dimensions and R701 Show and hide.

    R700  params.py reads the numbers at the top of model.py and writes
          changed ones back touching only those characters; the panel
          rebuilds them as a new build (apply_dimensions) and the agent's
          brief lists the values the user set; dimensions.py is the window.
    R701  visibility.py: one popover with every part (tick to show),
          Hide / Isolate / See-through / Show all and the explode slider;
          the explode button toggles; H / I / Shift+H / T / E / D keys.

    cd addon/AcadAgent/tests
    python3 -m unittest test_hand_edits_r700                    # pure parts
    QT_QPA_PLATFORM=offscreen "<bundle>/Contents/Resources/bin/python" \\
        -m unittest test_hand_edits_r700                        # + widgets
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
sys.path.insert(0, ADDON)
sys.path.insert(0, HERE)

from acadagent import params  # noqa: E402

try:
    from PySide6 import QtCore, QtWidgets  # noqa: F401
    HAVE_QT = True
except Exception:                                         # noqa: BLE001
    HAVE_QT = False

HINGED = os.path.join(ADDON, "acadagent", "agent_kit", "examples", "hinged_box.py")

SCRIPT = """# A box.
import Part

# --- body ---
L, W, H = 60.0, 40.0, 25.0     # box outside, mm
WALL = 2.0                     # wall thickness
TILT = 12.0                    # lid tilt, degrees
KNUCKLES = 3                   # hinge knuckles
OFFSET = -4.5
FLAG = True                    # not a number
n = 0                          # a counter, bound again below
for i in range(3):
    n += 1
R = L / 2                      # derived, not a literal
box = Part.makeBox(L, W, H)
"""


class TestParamsRead(unittest.TestCase):

    def test_reads_the_block_with_comments_units_and_sections(self):
        ps = {p.name: p for p in params.read(SCRIPT)}
        self.assertEqual(sorted(ps), ["H", "KNUCKLES", "L", "OFFSET", "TILT",
                                      "W", "WALL"])
        self.assertEqual(ps["L"].value, 60.0)
        self.assertEqual(ps["L"].comment, "box outside, mm")
        self.assertEqual(ps["L"].section, "body")
        self.assertEqual(ps["L"].unit, "mm")
        self.assertEqual(ps["TILT"].unit, "deg")
        self.assertEqual(ps["KNUCKLES"].unit, "")
        self.assertTrue(ps["KNUCKLES"].is_int)
        self.assertEqual(ps["OFFSET"].value, -4.5)

    def test_variables_bools_and_expressions_are_not_dimensions(self):
        names = {p.name for p in params.read(SCRIPT)}
        for n in ("n", "i", "FLAG", "R", "box"):
            self.assertNotIn(n, names)

    def test_a_file_description_is_not_a_section(self):
        with open(HINGED, encoding="utf-8") as fh:
            ps = params.read(fh.read())
        self.assertEqual([p.name for p in ps], ["L", "W", "H", "T", "PIN"])
        self.assertEqual({p.section for p in ps}, {""})

    def test_every_example_parses(self):
        d = os.path.dirname(HINGED)
        for f in os.listdir(d):
            if f.endswith(".py"):
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    params.read(fh.read())

    def test_broken_script_has_none(self):
        self.assertEqual(params.read("L = (\n"), [])


class TestParamsWrite(unittest.TestCase):

    def test_only_the_numbers_change(self):
        new = params.write(SCRIPT, {"W": 45, "KNUCKLES": 5, "OFFSET": -3})
        old_lines, new_lines = SCRIPT.splitlines(), new.splitlines()
        changed = [(a, b) for a, b in zip(old_lines, new_lines) if a != b]
        self.assertEqual(len(changed), 3, changed)
        self.assertIn("L, W, H = 60.0, 45.0, 25.0     # box outside, mm", new_lines)
        self.assertIn("KNUCKLES = 5                   # hinge knuckles", new_lines)
        self.assertIn("OFFSET = -3.0", new_lines)
        got = {p.name: p.value for p in params.read(new)}
        self.assertEqual((got["W"], got["KNUCKLES"], got["OFFSET"]), (45.0, 5, -3.0))

    def test_comment_column_kept(self):
        new = params.write(SCRIPT, {"WALL": 12.25})
        line = [ln for ln in new.splitlines() if ln.startswith("WALL")][0]
        old = [ln for ln in SCRIPT.splitlines() if ln.startswith("WALL")][0]
        self.assertEqual(line.index("#"), old.index("#"))

    def test_same_value_and_unknown_names_change_nothing(self):
        self.assertEqual(params.write(SCRIPT, {"L": 60, "R": 1, "nope": 3}), SCRIPT)

    def test_format(self):
        self.assertEqual(params.fmt(60, False), "60.0")
        self.assertEqual(params.fmt(1.75, False), "1.75")
        self.assertEqual(params.fmt(0.1 + 0.2, False), "0.3")
        self.assertEqual(params.fmt(3.0, True), "3")


class TestHandRecord(unittest.TestCase):

    def setUp(self):
        self.ws = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def test_brief_lists_what_the_user_set(self):
        new = params.write(SCRIPT, {"L": 80})
        params.record(self.ws, {"L": 60.0}, {"L": 80})
        lines = params.brief_lines(self.ws, new)
        self.assertIn("by hand", lines[0])
        self.assertEqual(lines[1:], ["- L = 80.0 (was 60.0)"])

    def test_a_value_put_back_is_forgotten(self):
        params.record(self.ws, {"L": 60.0}, {"L": 80})
        params.record(self.ws, {"L": 80.0}, {"L": 60})
        self.assertEqual(params.load_hand(self.ws), {})

    def test_the_agent_changing_it_since_drops_the_line(self):
        params.record(self.ws, {"L": 60.0}, {"L": 80})
        self.assertEqual(params.brief_lines(self.ws, params.write(SCRIPT, {"L": 70})), [])


# ======================================================================
# widgets (offscreen)
# ======================================================================
class _VO(object):
    Transparency = 0


class _Obj(object):
    TypeId = "Part::Feature"

    def __init__(self, doc, name):
        self.Document, self.Name, self.Label = doc, name, name
        self.Shape = object()
        self.Visibility = True
        self.InList = []
        self.ViewObject = _VO()


class _Doc(object):
    def __init__(self, names):
        self.Name = "Doc"
        self.Objects = [_Obj(self, n) for n in names]
        self.txns = []

    def getObject(self, name):
        return next((o for o in self.Objects if o.Name == name), None)

    def openTransaction(self, name):
        self.txns.append(name)

    def commitTransaction(self):
        pass


@unittest.skipUnless(HAVE_QT, "PySide6 not available")
class TestShowHidePopover(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        from acadagent import export_tools, inspect_tools, visibility
        self.et, self.it, self.v = export_tools, inspect_tools, visibility
        self.doc = _Doc(["Body", "Lid", "Pin"])
        self.picked = []
        self.explodes = []
        self._set_explode = export_tools.set_explode
        export_tools.set_explode = lambda doc, f: self.explodes.append(f) or f
        self.d = visibility.ShowHidePopover(
            None, lambda: self.doc, lambda doc, objs: self.picked.append(
                [o.Name for o in objs]))

    def tearDown(self):
        self.et.set_explode = self._set_explode
        self.it._HIDDEN.clear()
        self.it._ISOLATED.clear()
        self.d.deleteLater()

    def item(self, name):
        lw = self.d.list
        return next(lw.item(i) for i in range(lw.count())
                    if lw.item(i).data(QtCore.Qt.UserRole) == name)

    def test_every_part_listed_and_ticked(self):
        self.assertEqual(self.d.list.count(), 3)
        self.assertTrue(all(self.d.list.item(i).checkState() == QtCore.Qt.Checked
                            for i in range(3)))

    def test_untick_hides_and_tick_shows(self):
        self.item("Lid").setCheckState(QtCore.Qt.Unchecked)
        self.assertFalse(self.doc.getObject("Lid").Visibility)
        self.assertEqual(self.doc.txns[-1], "Hide")
        self.assertTrue(self.d.buttons["all"].isEnabled())
        self.item("Lid").setCheckState(QtCore.Qt.Checked)
        self.assertTrue(self.doc.getObject("Lid").Visibility)

    def test_buttons_follow_the_picked_rows(self):
        self.assertFalse(self.d.buttons["hide"].isEnabled())
        self.item("Pin").setSelected(True)
        self.assertEqual(self.picked[-1], ["Pin"])
        self.assertTrue(self.d.buttons["isolate"].isEnabled())
        self.d.buttons["isolate"].click()
        vis = {o.Name: o.Visibility for o in self.doc.Objects}
        self.assertEqual(vis, {"Body": False, "Lid": False, "Pin": True})
        self.assertEqual(self.item("Body").checkState(), QtCore.Qt.Unchecked)
        self.d.buttons["all"].click()
        self.assertTrue(all(o.Visibility for o in self.doc.Objects))

    def test_double_click_isolates_one(self):
        self.d.list.itemDoubleClicked.emit(self.item("Body"))
        self.assertEqual([o.Name for o in self.doc.Objects if o.Visibility], ["Body"])

    def test_slider_explodes(self):
        self.d.slider.setValue(40)
        self.assertEqual(self.explodes[-1], 0.4)


@unittest.skipUnless(HAVE_QT, "PySide6 not available")
class TestDimensionsDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        from acadagent import dimensions
        test = self

        class FakePanel(object):
            applied = []

            def dimensions_target(self):
                return {"params": params.read(SCRIPT), "path": "/x/model.py",
                        "source": SCRIPT}

            def apply_dimensions(self, changes, then=None):
                test.applied.append(changes)
                return True, "Rebuilding."
        self.applied = []
        self.d = dimensions.DimensionsDialog(None, FakePanel)

    def tearDown(self):
        self.d.deleteLater()

    def test_rows_units_and_rebuild_sends_only_changes(self):
        self.assertEqual(sorted(self.d.boxes), ["H", "KNUCKLES", "L", "OFFSET",
                                                "TILT", "W", "WALL"])
        self.assertEqual(self.d.boxes["L"].suffix(), " mm")
        self.assertEqual(self.d.boxes["TILT"].suffix(), "°")
        self.assertIsInstance(self.d.boxes["KNUCKLES"], QtWidgets.QSpinBox)
        self.assertEqual(self.d.btn_apply.text(), "Rebuild")
        self.d.boxes["W"].setValue(45.0)
        self.d.boxes["KNUCKLES"].setValue(4)
        self.assertEqual(self.d.btn_apply.text(), "Rebuild (2 changes)")
        self.assertTrue(self.d.rows["W"][0].text().startswith("●"))
        self.d.btn_apply.click()
        self.assertEqual(self.applied, [{"W": 45.0, "KNUCKLES": 4}])

    def test_reset(self):
        self.d.boxes["L"].setValue(99.0)
        self.d.btn_reset.click()
        self.assertEqual(self.d.boxes["L"].value(), 60.0)
        self.assertEqual(self.d.changes(), {})


@unittest.skipUnless(HAVE_QT, "PySide6 not available")
class TestPanelApplyDimensions(unittest.TestCase):
    """AgentPanel.apply_dimensions against the R500 fake build."""

    @classmethod
    def setUpClass(cls):
        import test_agent_integration_r500 as tai
        cls.tai = tai

    def run_case(self, fn):
        tai = self.tai
        outer = self

        class C(tai.Case):
            def runTest(self):
                fn(self, tai)
        c = C()
        res = unittest.TestResult()
        c.run(res)
        for _t, tb in res.errors + res.failures:
            outer.fail(tb)

    def test_writes_builds_records_and_briefs(self):
        def body(c, tai):
            from acadagent import build, panel
            doc = c.fc.add(tai._UndoDoc("Part", "uid-dim"))
            st = c.turn_state(key="uid-dim", doc=doc)
            calls = c.fake_builds(doc)
            c.p._busy = False
            c.p._cur = None
            c.write(st.ws, build.SCRIPT, SCRIPT)
            ok, msg = c.p.apply_dimensions({"L": 80, "WALL": 2.0})
            c.assertTrue(ok, msg)
            c.assertTrue(tai.wait_until(lambda: c.p._pending is None, 10))
            c.assertEqual(len(calls), 1)
            got = {p.name: p.value for p in params.read(c.read(st.ws))}
            c.assertEqual(got["L"], 80.0)
            with open(os.path.join(st.ws, params.HAND_FILE)) as fh:
                c.assertEqual(json.load(fh), {"L": {"was": 60.0, "now": 80}})
            c.assertIn("- L = 80.0 (was 60.0)", c.p._brief(doc))
            c.assertEqual(len(panel.load_builds(st.ws)["builds"]), 2,
                          "a new build, with the base kept")
            # rebuilt and unchanged: nothing to do
            ok, msg = c.p.apply_dimensions({"L": 80})
            c.assertFalse(ok)
            c.assertIn("Nothing to rebuild", msg)
            # while the agent works: refused, model.py untouched
            c.p._busy = True
            ok, msg = c.p.apply_dimensions({"L": 90})
            c.assertFalse(ok)
            c.assertIn("agent is working", msg)
            c.assertEqual(params.read(c.read(st.ws))[0].value, 80.0)
        self.run_case(body)


class TestShellWiring(unittest.TestCase):

    @unittest.skipUnless(HAVE_QT, "PySide6 not available")
    def test_tools_and_keys(self):
        import _shell_fakes  # noqa: F401  (FreeCAD stubs for shell)
        from acadagent import shell
        for k in ("show", "dims"):
            self.assertIn(k, shell.TOOL_ORDER)
        self.assertIn("show", shell.TOOL_GROUPS[0])
        self.assertEqual(shell.TOOL_DROP_LEVEL["show"], 99)
        keys = {sid: key for sid, key, _t, _s in shell.SHORTCUTS}
        self.assertEqual((keys["hide"], keys["isolate"], keys["show_all"],
                          keys["see_through"], keys["explode"], keys["dims"]),
                         ("H", "I", "Shift+H", "T", "E", "D"))
        self.assertEqual(len(set(keys.values())), len(keys), "no key twice")
        for sid in keys:
            self.assertTrue(callable(shell._shortcut_fn(sid)))


if __name__ == "__main__":
    unittest.main()
