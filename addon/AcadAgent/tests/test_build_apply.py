"""build.apply and friends — the half of the default chat path that turns an
agent turn into geometry.

THREE LAYERS, ONE FILE
    1. PURE tests (any Python, CI): snapshot/changed, failures(), Result,
       new_workspace, system_prompt, runner.measure on fake shapes. They load
       a private copy of the package under the PySide6 stub from
       test_claude_cli.
    2. HEADLESS tests (only inside the bundled freecadcmd): build.apply,
       adopt and document_brief against real FreeCAD documents, including
       the R11 / R15 / R16 reproductions from docs/prd/release_prd.md.
    3. A LAUNCHER (system Python, when freecadcmd is found): runs this file
       under freecadcmd and asserts the printed SENTINEL line.

WHY A SENTINEL AND NOT THE EXIT CODE
    freecadcmd exits 0 even when the script raised (MEASURED, see CLAUDE.md).
    So the headless run prints exactly one line
        BUILD_APPLY_SENTINEL result=<PASS|FAIL> run=.. failures=.. ...
    as its LAST act, and the launcher treats a missing line as a failure: a
    crash before the end cannot look like a pass.

HEADLESS vs GUI
    The GUI gives every document an undo stack; a headless document starts
    with UndoMode 0 (MEASURED 2026-09-25 in the bundled freecadcmd: UndoMode
    0, abortTransaction restores nothing). build.apply's rollback relies on
    transactions, so every document here gets UndoMode = 1 — the GUI's
    setting — before use. gui_build_apply.py is the older in-GUI variant.

KNOWN BUGS (R11, R15, R16) — expected failures
    WS-BUILD cannot touch build.py this round, so these reproductions assert
    the CORRECT behaviour and are marked @known_bug: they fail today (counted
    as expected failures). When the fix lands they pass, which unittest
    reports as an UNEXPECTED SUCCESS and the sentinel reports as FAIL, so the
    marker has to be removed deliberately. An error that is not an
    AssertionError inside a known-bug test (the scenario itself broke) is
    NOT allowed to hide as an expected failure: it is counted in
    harness_errors and fails the run.

RUN
    python3 -m unittest addon/AcadAgent/tests/test_build_apply.py -v
        pure tests + the launcher (skipped when freecadcmd is absent)
    ATECH_BUILD_APPLY_MAIN=1 <freecadcmd> addon/AcadAgent/tests/test_build_apply.py
        the headless suite directly; read the SENTINEL line
    ATECH_FREECADCMD=<path>   freecadcmd to launch (default: the repo's
                              dist/build/squashfs-root/usr/bin/freecadcmd)
    ATECH_ADDON_DIR=<dir>     test another copy of the addon (sabotage runs)
"""
import functools
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
ADDON = os.environ.get("ATECH_ADDON_DIR") or os.path.dirname(HERE)
sys.path.insert(0, HERE)

from test_claude_cli import load_acadagent  # noqa: E402

try:
    import FreeCAD                                     # noqa: F401
    IN_FREECAD = True
except ImportError:
    IN_FREECAD = False

SENTINEL = "BUILD_APPLY_SENTINEL"
HARNESS_ERRORS = []

_STUB = load_acadagent("build", "runner")
pbuild = _STUB.build          # pure-test copy, PySide6 stubbed
prunner = _STUB.runner


def known_bug(rid):
    """Expected failure for a documented bug — but only an AssertionError
    counts. Anything else is a broken scenario and fails the run."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(self):
            try:
                fn(self)
            except AssertionError:
                raise
            except BaseException as exc:               # noqa: BLE001
                HARNESS_ERRORS.append("%s %s: %s: %s" % (
                    rid, fn.__name__, type(exc).__name__, exc))
                raise
        wrapper.known_bug = rid
        return unittest.expectedFailure(wrapper)
    return deco


# ======================================================================
# 1. PURE
# ======================================================================
class TestSnapshotChanged(unittest.TestCase):

    def setUp(self):
        self.ws = tempfile.mkdtemp(prefix="atech-ws-")
        self.addCleanup(shutil.rmtree, self.ws, True)

    def touch(self, name, mtime=None, text="x"):
        path = os.path.join(self.ws, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path

    def test_snapshot_sees_only_what_apply_can_use(self):
        for n in ("model.py", "a.step", "B.STL", "c.brep", "notes.txt",
                  "helper.py", "d.iges"):
            self.touch(n)
        self.assertEqual(sorted(pbuild.snapshot(self.ws)),
                         ["B.STL", "a.step", "c.brep", "d.iges", "model.py"])

    def test_snapshot_of_missing_dir_is_empty(self):
        self.assertEqual(pbuild.snapshot(os.path.join(self.ws, "gone")), {})

    def test_changed_reports_rewrites_and_new_files(self):
        self.touch("model.py", mtime=1000)
        self.touch("old.step", mtime=1000)
        before = pbuild.snapshot(self.ws)
        self.assertEqual(pbuild.changed(self.ws, before), [])
        self.touch("model.py", mtime=2000)
        self.touch("new.brep", mtime=2000)
        self.assertEqual(pbuild.changed(self.ws, before),
                         ["model.py", "new.brep"])

    def test_changed_from_empty_snapshot_is_everything(self):
        self.touch("model.py")
        self.assertEqual(pbuild.changed(self.ws, {}), ["model.py"])


class TestFailures(unittest.TestCase):
    """failures() decides what goes back to the agent as 'fix this'."""

    def test_good_result_is_empty(self):
        r = pbuild.Result(True, "model.py", measurements=[
            {"label": "A", "valid": True, "solids": 1}])
        self.assertEqual(pbuild.failures(r), "")

    def test_invalid_shape_is_reported(self):
        r = pbuild.Result(True, "model.py", measurements=[
            {"label": "A", "valid": False, "solids": 1}])
        self.assertEqual(pbuild.failures(r), "A: 1 solids, valid=False")

    def test_no_solid_is_reported(self):
        r = pbuild.Result(True, "model.py", measurements=[
            {"name": "Face", "label": None, "valid": True, "solids": 0}])
        self.assertEqual(pbuild.failures(r), "Face: 0 solids, valid=True")

    def test_several_solids_are_legitimate(self):
        """MEASURED in build.py: flagging solids != 1 failed a correct car."""
        r = pbuild.Result(True, "model.py", measurements=[
            {"label": "Headlights", "valid": True, "solids": 2}])
        self.assertEqual(pbuild.failures(r), "")

    def test_all_problems_are_joined(self):
        r = pbuild.Result(True, "model.py", measurements=[
            {"label": "A", "valid": False, "solids": 1},
            {"label": "B", "valid": True, "solids": 1},
            {"label": "C", "valid": True, "solids": 0}])
        self.assertEqual(pbuild.failures(r),
                         "A: 1 solids, valid=False; C: 0 solids, valid=True")

    def test_unmeasured_is_not_reported_as_broken(self):
        """None means 'could not measure' (P1): not the same as invalid."""
        r = pbuild.Result(True, "model.py", measurements=[
            {"label": "A", "valid": None, "solids": None}])
        self.assertEqual(pbuild.failures(r), "")


class TestResult(unittest.TestCase):

    def test_record_tracks_created_by_default(self):
        r = pbuild.Result(True, "model.py", ["Box", "Cyl"], doc="D",
                          labels={"Box": "Box", "Cyl": "Pin"})
        self.assertEqual(r.record(), {"doc": "D", "names": ["Box", "Cyl"],
                                      "labels": {"Box": "Box", "Cyl": "Pin"}})

    def test_record_excludes_untracked(self):
        r = pbuild.Result(True, "model.py", ["Board", "Case"], doc="D",
                          tracked=["Case"])
        self.assertEqual(r.record()["names"], ["Case"])

    def test_record_is_a_copy(self):
        r = pbuild.Result(True, "model.py", ["Box"], doc="D")
        rec = r.record()
        rec["names"].append("X")
        self.assertEqual(r.tracked, ["Box"])


class TestWorkspaceAndPrompt(unittest.TestCase):

    def test_new_workspace_is_fresh_and_unique(self):
        if IN_FREECAD:
            self.skipTest("inside FreeCAD the root is the FreeCAD user dir")
        home = tempfile.mkdtemp(prefix="atech-home-")
        self.addCleanup(shutil.rmtree, home, True)
        saved = os.environ.get("HOME")
        os.environ["HOME"] = home
        try:
            a = pbuild.new_workspace()
            b = pbuild.new_workspace()
        finally:
            if saved is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = saved
        self.assertNotEqual(a, b)
        for p in (a, b):
            self.assertTrue(os.path.isdir(p))
            self.assertEqual(os.listdir(p), [])
            self.assertTrue(p.startswith(os.path.join(home, ".local", "share")),
                            p)
            self.assertEqual(os.path.basename(os.path.dirname(p)), "agent")

    def test_system_prompt_names_the_script_path(self):
        ws = "/tmp/some ws/chat-1"
        text = pbuild.system_prompt(ws)
        self.assertIn("%s/%s" % (ws, pbuild.SCRIPT), text)
        self.assertIn("doc", text)


class _Shape(object):
    def __init__(self, valid=True, solids=1, volume=1000.0, area=600.0,
                 box=(10, 10, 10), explode=False):
        self._valid, self.Solids = valid, [object()] * solids
        self.Volume, self.Area = volume, area
        self._explode = explode
        self.BoundBox = types.SimpleNamespace(
            XLength=box[0], YLength=box[1], ZLength=box[2])

    def isValid(self):
        if self._explode:
            raise RuntimeError("OCC says no")
        return self._valid


class TestMeasurePure(unittest.TestCase):

    def test_measures_off_the_shape(self):
        o = types.SimpleNamespace(Name="Box", Label="Plate", Shape=_Shape())
        m = prunner.measure(o)
        self.assertEqual((m["name"], m["label"], m["volume_mm3"], m["solids"],
                          m["valid"], m["bbox_bound"]),
                         ("Box", "Plate", 1000.0, 1, True, [10, 10, 10]))
        self.assertIsNone(m["reason"])

    def test_no_shape_is_none_with_reason(self):
        m = prunner.measure(types.SimpleNamespace(Name="G", Label="G"))
        self.assertIsNone(m["volume_mm3"])
        self.assertIn("no Shape", m["reason"])

    def test_measurement_error_is_none_not_a_guess(self):
        o = types.SimpleNamespace(Name="X", Label="X",
                                  Shape=_Shape(explode=True))
        m = prunner.measure(o)
        self.assertIsNone(m["volume_mm3"])
        self.assertIsNone(m["valid"])
        self.assertIn("OCC says no", m["reason"])


# ======================================================================
# 2. HEADLESS (inside freecadcmd only)
# ======================================================================
BOX = ("import Part\no = doc.addObject('Part::Feature', '%s')\n"
       "o.Shape = Part.makeBox(%s, 10, 10)\n")


@unittest.skipUnless(IN_FREECAD, "needs FreeCAD (run under freecadcmd)")
class _Headless(unittest.TestCase):

    def setUp(self):
        if ADDON not in sys.path:
            sys.path.insert(0, ADDON)
        from acadagent import build, runner
        self.build, self.runner = build, runner
        self.ws = self.scratch()
        self.docs = []

    def tearDown(self):
        for n in list(FreeCAD.listDocuments()):
            if n in self.docs:
                FreeCAD.closeDocument(n)

    # helpers ------------------------------------------------------------
    def scratch(self):
        """A temp dir removed after tearDown has closed the documents."""
        path = tempfile.mkdtemp(prefix="atech-build-test-")
        self.addCleanup(shutil.rmtree, path, True)
        return path

    def fresh(self, name):
        if name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(name)
        doc = FreeCAD.newDocument(name)
        doc.UndoMode = 1            # what the GUI gives every document
        FreeCAD.setActiveDocument(doc.Name)
        self.docs.append(doc.Name)
        return doc

    def write(self, code, ws=None):
        with open(os.path.join(ws or self.ws, self.build.SCRIPT), "w",
                  encoding="utf-8") as fh:
            fh.write(code)

    def apply(self, previous=None, ws=None, files=None):
        return self.build.apply(ws or self.ws, files or [self.build.SCRIPT],
                                previous)

    def precondition(self, cond, what):
        """A scenario that did not set up is a broken test, never an
        expected failure: raise something that is not AssertionError."""
        if not cond:
            raise RuntimeError("precondition failed: %s" % what)

    def user_box(self, doc, name, size=5):
        import Part
        o = doc.addObject("Part::Feature", name)
        o.Shape = Part.makeBox(size, size, size)
        doc.recompute()
        return o


class TestApplyHeadless(_Headless):

    def test_nothing_to_apply_is_none(self):
        self.fresh("BA_None")
        self.assertIsNone(self.build.apply(self.ws, ["notes.txt"], None))

    def test_simple_build_is_measured(self):
        d = self.fresh("BA_Simple")
        self.write(BOX % ("Plate", 20))
        r = self.apply()
        self.assertTrue(r.ok, r.error)
        self.assertEqual(r.doc, d.Name)
        self.assertEqual([m["label"] for m in r.measurements], ["Plate"])
        self.assertAlmostEqual(r.measurements[0]["volume_mm3"], 2000, 3)
        self.assertEqual(self.build.failures(r), "")
        o = d.getObject(r.created[0])
        self.assertTrue(o.AtechAgentBuilt)
        self.assertEqual(o.AtechAgentScript, BOX % ("Plate", 20))

    def test_sys_exit_is_caught_and_rolled_back(self):
        d = self.fresh("BA_Exit")
        self.write("import sys, Part\ndoc.addObject('Part::Feature','Stray')"
                   ".Shape=Part.makeBox(1,1,1)\nsys.exit(0)\n")
        r = self.apply()
        self.assertFalse(r.ok)
        self.assertIn("SystemExit", r.error)
        self.assertIsNone(d.getObject("Stray"))

    def test_raising_script_is_fully_rolled_back(self):
        d = self.fresh("BA_Raise")
        self.user_box(d, "Keep", 3)
        self.write("doc.removeObject('Keep')\nraise RuntimeError('boom')\n")
        r = self.apply()
        self.assertFalse(r.ok)
        self.assertIn("boom", r.error)
        self.assertIsNotNone(d.getObject("Keep"))

    def test_script_that_adds_nothing_fails_with_advice(self):
        d = self.fresh("BA_Empty")
        self.write("x = 1\n")
        r = self.apply()
        self.assertFalse(r.ok)
        self.assertIn("added nothing", r.error)
        self.assertEqual(d.Objects, [])

    def test_face_only_result_is_flagged_by_failures(self):
        """A build that 'succeeds' with no solid must go back to the agent.
        This is the check the R46 sabotage run breaks."""
        self.fresh("BA_Face")
        self.write("import Part\ndoc.addObject('Part::Feature','Sheet')"
                   ".Shape = Part.makePlane(10, 10)\n")
        r = self.apply()
        self.assertTrue(r.ok, r.error)
        self.assertEqual(r.measurements[0]["solids"], 0)
        self.assertEqual(self.build.failures(r), "Sheet: 0 solids, valid=True")

    def test_builds_stay_in_the_chat_document(self):
        a = self.fresh("BA_A")
        self.write(BOX % ("Plate", 20))
        r1 = self.apply()
        self.assertTrue(r1.ok and r1.doc == "BA_A", r1.error)
        b = self.fresh("BA_B")
        self.user_box(b, "Plate", 5)
        FreeCAD.setActiveDocument("BA_B")
        self.write(BOX % ("Plate", 30))
        r2 = self.apply(r1.record())
        self.assertTrue(r2.ok, r2.error)
        self.assertEqual(r2.doc, "BA_A")
        self.assertAlmostEqual(b.getObject("Plate").Shape.Volume, 125, 6)
        self.assertEqual(len([o for o in a.Objects
                              if o.Label.startswith("Plate")]), 1)

    def test_user_feature_on_agent_body_keeps_its_input(self):
        a = self.fresh("BA_Dep")
        self.write(BOX % ("Plate", 20))
        r1 = self.apply()
        base = a.getObject(r1.created[0])
        cut = a.addObject("Part::Cut", "UserCut")
        cut.Base = base
        tool = self.user_box(a, "UserTool", 2)
        cut.Tool = tool
        a.recompute()
        self.write(BOX % ("Plate", 40))
        r2 = self.apply(r1.record())
        self.assertTrue(r2.ok, r2.error)
        self.assertIsNotNone(cut.Base)
        self.assertEqual(cut.Base.Name, base.Name)
        self.assertEqual(r2.kept, ["Plate"])

    def test_sketch_design_measures_only_the_end_result(self):
        self.fresh("BA_Sketch")
        self.write("""import Part, Sketcher
from FreeCAD import Vector
sk = doc.addObject('Sketcher::SketchObject', 'Sk')
pts = [Vector(0,0,0), Vector(20,0,0), Vector(20,10,0), Vector(0,10,0)]
for i in range(4):
    sk.addGeometry(Part.LineSegment(pts[i], pts[(i+1) % 4]))
doc.recompute()
ext = doc.addObject('Part::Extrusion', 'Ext')
ext.Base = sk
ext.Dir = Vector(0, 0, 5)
ext.Solid = True
""")
        r = self.apply()
        self.assertTrue(r.ok, r.error)
        self.assertEqual(self.build.failures(r), "")
        self.assertEqual([m["label"] for m in r.measurements], ["Ext"])
        self.assertAlmostEqual(r.measurements[0]["volume_mm3"], 1000, 3)

    def test_labels_restored_exactly(self):
        d = self.fresh("BA_Label")
        self.write(BOX % ("Gear1", 10))
        r1 = self.apply()
        self.assertEqual(d.getObject(r1.created[0]).Label, "Gear1")
        self.write(BOX % ("Gear1", 12))
        r2 = self.apply(r1.record())
        self.assertEqual(d.getObject(r2.created[0]).Label, "Gear1")

    def test_stl_and_step_exports_import(self):
        import Mesh
        import Part
        self.fresh("BA_Import")
        stl = os.path.join(self.ws, "part.stl")
        Mesh.Mesh(Part.makeBox(10, 10, 10).tessellate(0.1)).write(stl)
        r = self.apply(files=["part.stl"])
        self.assertTrue(r is not None and r.ok, r and r.error)
        self.fresh("BA_Step")
        step = os.path.join(self.ws, "part.step")
        Part.makeCylinder(5, 10).exportStep(step)
        r = self.apply(files=["part.step"])
        self.assertTrue(r is not None and r.ok, r and r.error)
        self.assertAlmostEqual(r.measurements[0]["volume_mm3"],
                               3.141592653589793 * 250, 1)

    def test_undo_restores_the_previous_build(self):
        """Harness check for the R15 undo scenario: headless undo works."""
        d = self.fresh("BA_Undo")
        self.write(BOX % ("Plate", 20))
        r1 = self.apply()
        self.write(BOX % ("Plate", 30))
        r2 = self.apply(r1.record())
        self.assertTrue(r2.ok, r2.error)
        self.assertGreaterEqual(d.UndoCount, 1)
        d.undo()
        # S24 keeps object Names across rebuilds, so undo is checked on the
        # geometry: the first build's 20 mm plate (2000 mm3) is back.
        o = d.getObject(r1.created[0])
        self.assertIsNotNone(o)
        self.assertAlmostEqual(o.Shape.Volume, 2000.0, 3)

    def test_document_brief_lists_measured_solids(self):
        d = self.fresh("BA_Brief")
        self.user_box(d, "Cube", 10)
        text = self.build.document_brief(d)
        self.assertIn("Open document: BA_Brief", text)
        self.assertIn("Cube: volume 1000.0 mm3", text)
        self.write(BOX % ("Plate", 20))
        self.apply()
        self.assertIn("built by model.py", self.build.document_brief(d))

    def test_measure_reports_the_two_solid_fuse_trap(self):
        """A non-intersecting fuse is valid AND two solids (CLAUDE.md)."""
        import Part
        d = self.fresh("BA_Trap")
        o = d.addObject("Part::Feature", "Pair")
        o.Shape = Part.makeBox(1, 1, 1).fuse(
            Part.makeBox(1, 1, 1, FreeCAD.Vector(5, 0, 0)))
        m = self.runner.measure(o)
        self.assertEqual((m["valid"], m["solids"]), (True, 2))

    def test_studio_written_script_round_trips_through_a_file(self):
        d = self.fresh("BA_Round")
        self.write(BOX % ("Case", 10))
        r = self.apply()
        self.assertTrue(r.ok, r.error)
        path = os.path.join(self.ws, "round.FCStd")
        d.saveAs(path)
        FreeCAD.closeDocument(d.Name)
        g = FreeCAD.openDocument(path)
        g.UndoMode = 1
        self.docs.append(g.Name)
        ws2 = self.scratch()
        prev = self.build.adopt(g, ws2)
        self.assertIsNotNone(prev)
        with open(os.path.join(ws2, self.build.SCRIPT), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), BOX % ("Case", 10))
        r2 = self.apply(prev, ws=ws2)
        self.assertTrue(r2.ok, r2.error)
        self.assertEqual([o.Label for o in g.Objects], ["Case"])


class TestKnownBugs(_Headless):
    """docs/prd/release_prd.md R11, R15, R16 — reproductions, not fixes."""

    def test_R11_untrusted_file_script_is_not_adopted(self):
        import Part
        marker = os.path.join(self.ws, "PWNED")
        src = self.fresh("R11_Src")
        o = src.addObject("Part::Feature", "Planted")
        o.Shape = Part.makeBox(4, 4, 4)
        o.addProperty("App::PropertyBool", "AtechAgentBuilt", "Atech", "")
        o.addProperty("App::PropertyString", "AtechAgentScript", "Atech", "")
        o.AtechAgentBuilt = True
        o.AtechAgentScript = (
            "open(%r, 'w').write('pwned')\n" % marker) + BOX % ("Planted", 4)
        path = os.path.join(self.ws, "shared.FCStd")
        src.saveAs(path)
        FreeCAD.closeDocument(src.Name)
        doc = FreeCAD.openDocument(path)
        doc.UndoMode = 1
        self.docs.append(doc.Name)
        self.precondition(getattr(doc.getObject("Planted"),
                                  "AtechAgentBuilt", False),
                          "flag survived save/reopen")
        ws2 = self.scratch()
        prev = self.build.adopt(doc, ws2)
        written = os.path.exists(os.path.join(ws2, self.build.SCRIPT))
        if written:                  # what the chat does on the next build
            self.build.apply(ws2, [self.build.SCRIPT], prev)
        ran = os.path.exists(marker)
        self.assertFalse(written or ran,
                         "adopt wrote the file's script=%s, script ran=%s"
                         % (written, ran))

    def test_R15_reused_object_name_is_not_deleted(self):
        d = self.fresh("R15_Name")
        self.write(BOX % ("Box", 10))
        r1 = self.apply()
        self.precondition(r1.ok and r1.created == ["Box"], "agent built Box")
        d.removeObject("Box")                     # user deletes the build
        user = d.addObject("Part::Box", "Box")    # FreeCAD reuses the Name
        d.recompute()
        self.precondition(user.Name == "Box", "Name reused: %s" % user.Name)
        self.write(BOX % ("Plate", 20))
        r2 = self.apply(r1.record())
        self.precondition(r2.ok, "second build ran: %s" % r2.error)
        survivor = d.getObject("Box")
        self.assertTrue(survivor is not None
                        and survivor.TypeId == "Part::Box",
                        "the user's Part::Box was deleted by the next build")

    def test_R15_reused_document_name_is_not_touched(self):
        d = self.fresh("Unnamed")
        self.write(BOX % ("Box", 10))
        r1 = self.apply()
        self.precondition(r1.ok and r1.doc == "Unnamed", "built in Unnamed")
        FreeCAD.closeDocument("Unnamed")
        d2 = self.fresh("Unnamed")               # File > New reuses the Name
        self.precondition(d2.Name == "Unnamed", "doc Name reused")
        self.user_box(d2, "Box", 5)
        self.write(BOX % ("Plate", 20))
        r2 = self.apply(r1.record())
        self.precondition(r2.ok, "second build ran: %s" % r2.error)
        box = d2.getObject("Box")
        self.assertTrue(box is not None and box.Label == "Box"
                        and abs(box.Shape.Volume - 125) < 1e-6,
                        "the new document's user Box was removed/relabelled")

    def test_R15_undo_then_rebuild_leaves_one_design(self):
        d = self.fresh("R15_Undo")
        self.write(BOX % ("Plate", 20))
        r1 = self.apply()
        self.write(BOX % ("Plate", 30))
        r2 = self.apply(r1.record())
        self.precondition(r1.ok and r2.ok, "two builds")
        d.undo()
        self.precondition(d.getObject(r1.created[0]) is not None,
                          "undo restored build 1")
        self.write(BOX % ("Plate", 40))
        r3 = self.apply(r2.record())
        self.precondition(r3.ok, "third build ran: %s" % r3.error)
        built = [o.Label for o in d.Objects
                 if getattr(o, "AtechAgentBuilt", False)]
        self.assertEqual(len(built), 1,
                         "designs after undo + rebuild: %s" % built)

    def test_R16_script_deleting_user_objects_is_not_success(self):
        d = self.fresh("R16_Wipe")
        d.addObject("Part::Box", "UserBox")
        d.recompute()
        self.write("for o in list(doc.Objects):\n"
                   "    doc.removeObject(o.Name)\n" + BOX % ("New", 5))
        r = self.apply()
        self.assertFalse(r.ok, "a build that deleted UserBox reported ok")
        self.assertIsNotNone(d.getObject("UserBox"))


# ======================================================================
# 3. LAUNCHER (system Python)
# ======================================================================
def _freecadcmd():
    cand = os.environ.get("ATECH_FREECADCMD") or os.path.join(
        REPO, "dist", "build", "squashfs-root", "usr", "bin", "freecadcmd")
    return cand if os.path.isfile(cand) and os.access(cand, os.X_OK) else None


def run_headless(freecadcmd, timeout=600):
    """Run this file under freecadcmd; return (sentinel dict or None, log).

    The child gets a scratch HOME, so FreeCAD's config and user-data writes
    never touch the owner's running Studio.
    """
    home = tempfile.mkdtemp(prefix="atech-fc-home-")
    env = dict(os.environ)
    for k in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
              "PYTHONPATH", "PYTHONHOME"):
        env.pop(k, None)
    env.update(HOME=home, ATECH_BUILD_APPLY_MAIN="1", ATECH_ADDON_DIR=ADDON,
               QT_QPA_PLATFORM="offscreen")
    try:
        out = subprocess.run([freecadcmd, os.path.abspath(__file__)],
                             capture_output=True, text=True, timeout=timeout,
                             env=env, stdin=subprocess.DEVNULL, cwd=home)
        log = (out.stdout or "") + (out.stderr or "")
    finally:
        shutil.rmtree(home, ignore_errors=True)
    lines = [l for l in log.splitlines() if l.startswith(SENTINEL + " ")]
    if not lines:
        return None, log
    return dict(kv.split("=", 1) for kv in lines[-1].split()[1:]), log


@unittest.skipIf(IN_FREECAD, "already inside FreeCAD")
class TestHeadlessUnderFreecadcmd(unittest.TestCase):

    def test_headless_suite_passes(self):
        exe = _freecadcmd()
        if exe is None:
            self.skipTest("freecadcmd not found (set ATECH_FREECADCMD)")
        started = time.time()
        sentinel, log = run_headless(exe)
        tail = "\n".join(log.splitlines()[-60:])
        self.assertIsNotNone(sentinel,
                             "no %s line: the headless run crashed (freecadcmd "
                             "exit code is meaningless)\n%s" % (SENTINEL, tail))
        self.assertEqual(sentinel.get("result"), "PASS",
                         "%s\n%s" % (sentinel, tail))
        self.assertGreater(int(sentinel.get("headless_run", "0")), 0,
                           "the FreeCAD tests did not run")
        sys.stderr.write("\n[freecadcmd %.1fs] %s\n" % (
            time.time() - started,
            " ".join("%s=%s" % kv for kv in sorted(sentinel.items()))))


# ======================================================================
def main():
    """Headless entry: run everything, print the SENTINEL last."""
    loader = unittest.TestLoader()
    pure = [TestSnapshotChanged, TestFailures, TestResult,
            TestWorkspaceAndPrompt, TestMeasurePure]
    headless = [TestApplyHeadless, TestKnownBugs]
    suite = unittest.TestSuite()
    for cls in pure + headless:
        suite.addTests(loader.loadTestsFromTestCase(cls))
    n_headless = sum(loader.loadTestsFromTestCase(c).countTestCases()
                     for c in headless)
    try:
        result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(
            suite)
        bad = (len(result.failures) + len(result.errors)
               + len(result.unexpectedSuccesses) + len(HARNESS_ERRORS))
        for e in HARNESS_ERRORS:
            print("HARNESS_ERROR %s" % e)
        for t, tb in result.expectedFailures:
            # Show WHY each known bug still reproduces: the assertion line.
            why = [l for l in tb.strip().splitlines() if l.strip()][-1]
            print("XFAIL %s: %s" % (t.id().rsplit(".", 1)[-1], why))
        for t in result.unexpectedSuccesses:
            print("XPASS %s -> the bug is fixed: remove @known_bug" % t.id())
        xfail = ",".join(sorted(
            re.sub(r".*\.test_(R\d+)_.*", r"\1", t.id())
            for t, _ in result.expectedFailures))
        print("%s result=%s run=%d headless_run=%d failures=%d errors=%d "
              "skipped=%d xfail=%d xpass=%d harness_errors=%d xfail_ids=%s"
              % (SENTINEL, "PASS" if bad == 0 else "FAIL", result.testsRun,
                 n_headless if IN_FREECAD else 0, len(result.failures),
                 len(result.errors), len(result.skipped),
                 len(result.expectedFailures),
                 len(result.unexpectedSuccesses), len(HARNESS_ERRORS),
                 xfail or "-"))
    except BaseException as exc:                       # noqa: BLE001
        print("%s result=FAIL crashed=%s" % (SENTINEL, type(exc).__name__))
    sys.stdout.flush()


if IN_FREECAD and os.environ.get("ATECH_BUILD_APPLY_MAIN") == "1":
    main()
elif __name__ == "__main__":
    unittest.main()
