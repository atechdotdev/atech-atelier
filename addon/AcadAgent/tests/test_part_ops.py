"""R880 Add file to design + R885 Edit part (granular edits, agent edits).

  TestGeometry   fc_part_ops.py under freecadcmd: real FreeCAD geometry
                 (skips without ATECH_FREECADCMD / a bundled freecadcmd)
  TestPure       helpers that need no FreeCAD: sub-element names, step
                 words, part_edits.json validation, licences, the rule
  TestWindows    Edit part and Add file windows, offscreen Qt, no FreeCAD
  TestShell      the view bar tool, the F key, the menu commands, drops
  TestBrief      the agent's brief carries imported and editable parts

    QT_QPA_PLATFORM=offscreen python -m unittest -v test_part_ops
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
if ADDON not in sys.path:
    sys.path.insert(0, ADDON)

from acadagent import design_import as di                 # noqa: E402
from acadagent import part_edit as pe                     # noqa: E402
from acadagent import part_ops as po                      # noqa: E402

try:
    from PySide6 import QtWidgets
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
    def test_fc_part_ops(self):
        home = tempfile.mkdtemp(prefix="atech-po-")
        env = {"HOME": home, "FREECAD_USER_HOME": home, "PATH": "/usr/bin:/bin"}
        p = subprocess.run([FC, os.path.join(HERE, "fc_part_ops.py")], env=env,
                           cwd=home, capture_output=True, text=True, timeout=600)
        line = [ln for ln in (p.stdout + p.stderr).splitlines()
                if ln.startswith("PART_OPS_RESULT=")]
        self.assertTrue(line, (p.stdout + p.stderr)[-2000:])
        r = json.loads(line[-1].split("=", 1)[1])
        failed = [k for k, v in r["checks"].items() if not v]
        self.assertTrue(r["ok"], (failed, r["errors"]))
        self.assertGreaterEqual(len(r["checks"]), 60)


class TestPure(unittest.TestCase):
    def test_parse_subs(self):
        self.assertEqual(pe.parse_subs(["Face3", "Edge5", "Edge7", "Vertex1"]),
                         ([3], [5, 7]))
        self.assertEqual(pe.parse_subs(["Body.Face12"]), ([12], []))
        self.assertEqual(pe.parse_subs([]), ([], []))

    def test_describe_step(self):
        self.assertEqual(po.describe_step({"op": "fillet", "radius": 2}), "fillet 2 mm")
        self.assertEqual(po.describe_step({"op": "hole", "diameter": 5, "depth": None}),
                         "hole 5 mm through")
        self.assertEqual(po.describe_step({"op": "hole", "diameter": 3, "depth": 4}),
                         "hole 3 mm 4 mm deep")
        self.assertEqual(po.describe_step({"op": "push_pull", "face": "top",
                                           "distance": -2}), "push face top by 2 mm")
        self.assertEqual(po.describe_step({"op": "cut", "shape": "box"}), "cut box")

    def test_agent_file_validation(self):
        ok = po.parse_agent_file(json.dumps({"edits": [
            {"part": "Lid", "steps": [{"op": "fillet", "edges": "all",
                                       "radius": 1, "m": [0] * 16}]}]}))
        self.assertEqual(ok[0][0], "Lid")
        self.assertNotIn("m", ok[0][1][0])          # Atelier sets the frame
        for bad in ("{", "[]", json.dumps({"edits": [{"steps": []}]}),
                    json.dumps({"edits": [{"part": "A", "steps": [{"op": "rm -rf"}]}]}),
                    json.dumps({"edits": [{"part": "A", "steps": [
                        {"op": "mirror", "plane": "x"}] * (po.AGENT_MAX_STEPS + 1)}]})):
            with self.assertRaises(po.EditRefused, msg=bad):
                po.parse_agent_file(bad)
        one = po.parse_agent_file(json.dumps(
            {"edits": [{"part": "A", "steps": {"op": "mirror", "plane": "x"}}]}))
        self.assertEqual(len(one[0][1]), 1)        # a single step dict is fine

    def test_rule_names_file_and_ops(self):
        r = po.agent_rule()
        self.assertIn(po.AGENT_FILE, r)
        for op in po.OPS:
            self.assertIn(op, r)

    def test_licences(self):
        self.assertEqual(set(di.LICENCE_ORDER), set(di.LICENCES))
        self.assertFalse(di.LICENCES["sdfl"][2])      # not shareable
        self.assertFalse(di.LICENCES["cc-by-nd"][1])  # no remix
        self.assertIsNone(di.strictest_licence([]))

    def test_addable(self):
        d = tempfile.mkdtemp()
        paths = []
        for n in ("a.step", "b.STL", "c.obj", "d.FCStd", "e.dwg"):
            p = os.path.join(d, n)
            open(p, "w").close()
            paths.append(p)
        self.assertEqual([os.path.basename(p) for p in di.addable(paths)],
                         ["a.step", "b.STL", "c.obj"])


@unittest.skipIf(QtWidgets is None, "PySide6 not installed")
class TestWindows(unittest.TestCase):
    def test_part_editor_with_nothing_selected(self):
        d = pe.PartEditor(None)
        try:
            self.assertEqual(d.name.text(), "No part selected")
            for b in (d.btn_pull, d.btn_hole, d.btn_fillet, d.btn_chamfer,
                      d.btn_hollow, d.btn_undo, d.btn_reset):
                self.assertFalse(b.isEnabled(), b.text())
            self.assertFalse(d.agent.isEnabled())
            self.assertTrue(d.btn_convert.isHidden())
            self.assertEqual(set(d.btn_mirror), {"x", "y", "z"})
        finally:
            d.close()

    def test_part_editor_button(self):
        b = pe.view_bar_button(None)
        self.assertEqual(b.accessibleName(), "Edit part")
        from acadagent import style
        self.assertIn(b.property("atech_icon"), style.PATHS)

    def test_add_file_dialog(self):
        d = di.AddFileDialog(None)
        try:
            self.assertFalse(d.ok.isEnabled())
            p = os.path.join(tempfile.mkdtemp(), "part.step")
            open(p, "w").close()
            d.path.setText(p)
            self.assertTrue(d.ok.isEnabled())
            d.units.setCurrentIndex(1)
            d.author.setText("Ana")
            d.licence.setCurrentIndex(di.LICENCE_ORDER.index("cc-by"))
            d.editable.setChecked(True)
            v = d.values()
            self.assertEqual(v["units"], 25.4)
            self.assertEqual(v["source"]["licence"], "cc-by")
            self.assertTrue(v["agent_editable"])
            d.path.setText(p + ".dwg")
            self.assertFalse(d.ok.isEnabled())
        finally:
            d.close()


@unittest.skipIf(QtWidgets is None, "PySide6 not installed")
class TestShell(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from acadagent import shell
        cls.shell = shell

    def test_tool_key_and_commands(self):
        s = self.shell
        self.assertIn(("part", "Edit part"), s.EDIT_TOOLS)
        keys = {k: seq for k, seq, _t, _g in s.SHORTCUTS}
        self.assertEqual(keys.get("part"), "F")
        self.assertEqual(len(set(keys.values())), len(keys))   # no clashes
        cmds = {c[3] for c in s.TOOL_COMMANDS}
        self.assertTrue({"addfile", "part"} <= cmds)
        self.assertIn(".obj", s.IMPORT_EXT)

    def test_drop_adds_to_open_design(self):
        s = self.shell
        d = tempfile.mkdtemp()
        step = os.path.join(d, "a.step")
        proj = os.path.join(d, "b.FCStd")
        for p in (step, proj):
            open(p, "w").close()
        fake = mock.Mock()
        fake.add_dropped.return_value = [mock.Mock(Name="Imported")]
        with mock.patch.object(s, "adds_to_design", return_value=True), \
                mock.patch.object(s, "open_paths", return_value=["B"]) as op, \
                mock.patch.dict(sys.modules, {"acadagent.design_import": fake}), \
                mock.patch("acadagent.design_import", fake, create=True):
            out = s.drop_paths([step, proj])
        fake.add_dropped.assert_called_once_with([step])
        op.assert_called_once_with([proj])
        self.assertEqual(out, ["Imported", "B"])

    def test_view_drop_filter_only_in_the_view_area(self):
        s = self.shell
        area = QtWidgets.QMdiArea()
        inside = QtWidgets.QWidget(area)
        outside = QtWidgets.QWidget()
        d = tempfile.mkdtemp()
        step = os.path.join(d, "a.step")
        proj = os.path.join(d, "b.FCStd")
        for p in (step, proj):
            open(p, "w").close()
        f = s.ViewDropFilter(area)
        with mock.patch.object(s, "adds_to_design", return_value=True), \
                mock.patch.object(s, "_event_paths", return_value=[step, proj]):
            self.assertEqual(f._ours(inside, None), [step])
            self.assertEqual(f._ours(outside, None), [])
        with mock.patch.object(s, "adds_to_design", return_value=False), \
                mock.patch.object(s, "_event_paths", return_value=[step]):
            self.assertEqual(f._ours(inside, None), [])
        with mock.patch.object(s, "adds_to_design", return_value=True), \
                mock.patch.object(s, "_event_paths", return_value=[proj]):
            self.assertEqual(f._ours(inside, None), [])   # FreeCAD opens projects

    def test_drop_on_home_makes_projects(self):
        s = self.shell
        step = os.path.join(tempfile.mkdtemp(), "a.step")
        open(step, "w").close()
        with mock.patch.object(s, "adds_to_design", return_value=False), \
                mock.patch.object(s, "open_paths", return_value=["A"]) as op:
            self.assertEqual(s.drop_paths([step]), ["A"])
        op.assert_called_once_with([step])


class TestBrief(unittest.TestCase):
    def test_sections_and_rule(self):
        from acadagent import build

        class Obj(object):
            pass
        o = Obj()
        o.Label, o.Name = "bracket", "Imported"
        o.AtechImport, o.AtechImportFile = True, "bracket.step"
        o.AtechSourceAuthor, o.AtechSourceLicence, o.AtechSourceUrl = "Ana", "cc-by", ""
        o.AtechAgentEditable = True
        doc = mock.Mock(Objects=[o])
        with mock.patch.object(po, "editable_parts", return_value=[o]), \
                mock.patch.object(po, "brief_lines",
                                  return_value=["bracket: 6 faces", "face 1 flat top"]):
            lines = build._imported_lines(doc)
            rule = build._editable_rule(doc)
        text = "\n".join(lines)
        self.assertIn("IMPORTED", text)
        self.assertIn("bracket: imported from bracket.step, by Ana, CC BY", text)
        self.assertIn("EDITABLE PARTS", text)
        self.assertIn("face 1 flat top", text)
        self.assertIn(po.AGENT_FILE, rule)
        with mock.patch.object(po, "editable_parts", return_value=[]):
            self.assertEqual(build._editable_rule(doc), "")


if __name__ == "__main__":
    unittest.main()
