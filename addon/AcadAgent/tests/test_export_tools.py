"""W4 editing, export and sharing (R340-R347): acadagent/export_tools.py and
capture.share_image / share_sheet.

    cd addon/AcadAgent/tests
    python3 -m unittest test_export_tools                       # pure parts
    QT_QPA_PLATFORM=offscreen "<bundle>/Contents/Resources/bin/python" \\
        -m unittest test_export_tools                           # + widgets

The FreeCAD parts run in the bundled freecadcmd (ATECH_FREECADCMD, else
dist/build-macos-arm64/...): the toy car example is built once with
agent_kit/check.py (ATECH_CHECK_OUT -> one BREP per part, cached in the
temp folder by the example's hash) and exported to STL, 3MF and STEP; the
files are read back and their volumes must agree with the exact solids to
0.5 %. Each feature has a sabotage test: the feature broken on purpose
must make its check fail.
"""
import csv
import hashlib
import io
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
REPO = os.path.normpath(os.path.join(ADDON, "..", ".."))
sys.path.insert(0, ADDON)

from acadagent import export_tools as et  # noqa: E402

KIT = os.path.join(ADDON, "acadagent", "agent_kit")
BUNDLE = os.path.join(REPO, "dist", "build-macos-arm64", "Atech Atelier.app", "Contents",
                      "Resources", "bin")
FC = os.environ.get("ATECH_FREECADCMD") or os.path.join(BUNDLE, "freecadcmd")
if not os.path.isfile(FC):
    FC = None

try:
    from PySide6 import QtWidgets
    HAVE_QT = True
except Exception:                                         # noqa: BLE001
    HAVE_QT = False


# ------------------------------------------------------------------ fakes
class FakeVO(object):
    def __init__(self, color=(0.8, 0.8, 0.8), transparency=0):
        self.ShapeColor = tuple(color) + (0.0,)
        self.Transparency = transparency


class FakeShape(object):
    def __init__(self, volume=1000.0, area=600.0, bb=(0, 0, 0, 10, 10, 10)):
        self.Volume, self.Area = volume, area
        self.Solids = [self]
        self._bb = bb

    def isNull(self):
        return False


class FakeObj(object):
    def __init__(self, label, agent=True, color=(0.8, 0.8, 0.8), placement=et.IDENTITY,
                 shape=None, **props):
        self.Label = label
        self.Name = label
        self.TypeId = "Part::Feature"
        if agent:
            self.AtechAgentBuilt = True
        self.ViewObject = FakeVO(color)
        self.Visibility = True
        self.Placement = tuple(placement)
        self.Shape = shape or FakeShape()
        self.InList = []
        for k, v in props.items():
            setattr(self, k, v)


class FakeDoc(object):
    def __init__(self, objs=()):
        self.Objects = list(objs)
        self.PropertiesList = ["Label"]
        self.Label = "Fake"

    def addProperty(self, typ, name, group, tip):
        self.PropertiesList.append(name)
        setattr(self, name, "")

    def setEditorMode(self, *a):
        pass

    def getObject(self, name):
        return next((o for o in self.Objects if o.Name == name), None)

    def recompute(self):
        pass


YELLOW = (0.98, 0.78, 0.10)
RED = (0.80, 0.11, 0.10)
MOVE = (5.0, 0.0, 2.0, 0.0, 0.0, math.sin(math.pi / 8), math.cos(math.pi / 8))   # 45 deg about Z


def build(doc, colours):
    """An agent build: the previous build's parts go, new ones with the
    same labels come, in the build's own colours; then reapply."""
    doc.Objects = [o for o in doc.Objects if not getattr(o, "AtechAgentBuilt", False)
                   or getattr(o, "AtechRole", None)]
    for label, c in colours.items():
        doc.Objects.append(FakeObj(label, color=c))
    return et.reapply_overrides(doc)


def user_edits(doc):
    body = doc.getObject("Body")
    body.ViewObject.ShapeColor = RED + (0.0,)
    doc.getObject("Lid").Visibility = False
    doc.getObject("Knob").Placement = MOVE


def assert_edits_survive(test, doc):
    """Body red, Lid hidden, Knob moved after a rebuild."""
    test.assertEqual(tuple(round(c, 2) for c in doc.getObject("Body").ViewObject.ShapeColor[:3]),
                     RED)
    test.assertFalse(doc.getObject("Lid").Visibility)
    test.assertTrue(et.pl_same(doc.getObject("Knob").Placement, MOVE))
    test.assertEqual(tuple(round(c, 2) for c in doc.getObject("Wheel").ViewObject.ShapeColor[:3]),
                     (0.2, 0.2, 0.2))


BUILD = {"Body": YELLOW, "Lid": (0.9, 0.9, 0.9), "Knob": (0.1, 0.1, 0.1), "Wheel": (0.2, 0.2, 0.2)}


# ======================================================================
class Palette(unittest.TestCase):
    """R341: the colour menu's palette is cad.color's MATERIALS."""

    def test_palette_is_materials(self):
        with open(os.path.join(KIT, "atech_detail.py"), encoding="utf-8") as fh:
            src = fh.read()
        block = src[src.index("MATERIALS = {"):src.index("}\n", src.index("MATERIALS = {"))]
        keys = [ln.split('"')[1] for ln in block.splitlines()[1:] if '"' in ln]
        pal = et.palette()
        self.assertEqual([p[0] for p in pal], keys)
        by = {p[0]: p for p in pal}
        self.assertEqual(by["toy_yellow"][2], YELLOW)
        self.assertEqual(by["glass"][3], 60)
        self.assertEqual(by["led_red"][1], "LED red")
        self.assertEqual(et.colour_name(YELLOW), "Toy yellow")
        self.assertEqual(et.colour_name((0.5, 0.25, 0.0)), "#804000")

    def test_sabotage_unparsed_palette_detected(self):
        et._PALETTE = None
        try:
            with mock.patch.object(et, "KIT_DIR", "/nonexistent"):
                pal = et.palette()
            self.assertNotIn("glass", [p[0] for p in pal])   # the fallback, not MATERIALS
        finally:
            et._PALETTE = None


class PlacementMath(unittest.TestCase):
    def test_mul_inv(self):
        a = (1.0, 2.0, 3.0, 0.0, 0.0, math.sin(0.3), math.cos(0.3))
        self.assertTrue(et.pl_same(et.pl_mul(a, et.pl_inv(a)), et.IDENTITY))
        b = et.pl_mul(MOVE, a)
        self.assertTrue(et.pl_same(et.pl_mul(b, et.pl_inv(a)), MOVE))
        # 45 deg about Z turns +X onto (cos45, sin45)
        x = et._qrot(MOVE[3:], (1, 0, 0))
        self.assertAlmostEqual(x[0], math.sqrt(0.5))
        self.assertAlmostEqual(x[1], math.sqrt(0.5))


class Overrides(unittest.TestCase):
    """R340: hand edits on agent parts survive a rebuild."""

    def setUp(self):
        self.doc = FakeDoc([FakeObj("motherboard", agent=True, AtechRole="board")])
        build(self.doc, BUILD)

    def test_edits_survive_rebuild_and_brief(self):
        user_edits(self.doc)
        rec = et.capture_overrides(self.doc)
        self.assertEqual(sorted(rec), ["Body", "Knob", "Lid"])
        self.assertIn(et.DOC_PROP, self.doc.PropertiesList)
        applied = build(self.doc, BUILD)
        self.assertEqual(sorted(applied), ["Body", "Knob", "Lid"])
        assert_edits_survive(self, self.doc)
        # a second rebuild without new edits keeps them (base = build values)
        et.capture_overrides(self.doc)
        build(self.doc, BUILD)
        assert_edits_survive(self, self.doc)
        brief = et.overrides_for_brief(self.doc)
        self.assertIn('"Body": colour Signal red', brief)
        self.assertIn('"Lid": hidden', brief)
        self.assertIn("turned 45.0 deg about (0.00, 0.00, 1.00)", brief)
        self.assertIn("moved by (5.00, 0.00, 2.00) mm", brief)

    def test_reverted_edit_is_dropped_and_missing_part_kept(self):
        user_edits(self.doc)
        et.capture_overrides(self.doc)
        build(self.doc, BUILD)
        self.doc.getObject("Lid").Visibility = True          # the user shows it again
        et.capture_overrides(self.doc)
        self.assertNotIn("Lid", et.overrides(self.doc))
        build(self.doc, {k: v for k, v in BUILD.items() if k != "Body"})
        self.assertIn("Body", et.overrides(self.doc))
        self.assertIn("(not in the current build)", et.overrides_for_brief(self.doc))

    def test_hardware_and_user_objects_not_recorded(self):
        board = self.doc.getObject("motherboard")
        board.Visibility = False
        self.doc.Objects.append(FakeObj("Mine", agent=False))
        self.doc.getObject("Mine").Visibility = False
        self.assertEqual(et.capture_overrides(self.doc), {})
        self.assertEqual(et.overrides_for_brief(self.doc), "")

    def test_colour_menu_records_immediately(self):
        n = et.set_colour(self.doc, [self.doc.getObject("Wheel")], color=RED, transparency=30)
        self.assertEqual(n, 1)
        self.assertEqual(et.overrides(self.doc)["Wheel"]["transparency"], 30)
        build(self.doc, BUILD)
        w = self.doc.getObject("Wheel")
        self.assertEqual(w.ViewObject.Transparency, 30)
        et.reset_colour(self.doc, [w])
        self.assertNotIn("Wheel", et.overrides(self.doc))
        self.assertEqual(tuple(round(c, 2) for c in w.ViewObject.ShapeColor[:3]), (0.2, 0.2, 0.2))

    def test_sabotage_no_reapply_fails(self):
        user_edits(self.doc)
        et.capture_overrides(self.doc)
        with mock.patch.object(et, "_apply_view", lambda o, rec: []):
            build(self.doc, BUILD)
        with self.assertRaises(AssertionError):
            assert_edits_survive(self, self.doc)

    def test_sabotage_capture_skipped_fails(self):
        user_edits(self.doc)
        build(self.doc, BUILD)               # the integrator forgot capture_overrides
        with self.assertRaises(AssertionError):
            assert_edits_survive(self, self.doc)


class ThreeMF(unittest.TestCase):
    """R342: the 3MF writer keeps colours (and transparency as alpha)."""
    CUBE = ([(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0),
             (0, 0, 10), (10, 0, 10), (10, 10, 10), (0, 10, 10)],
            [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
             (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)])

    def write(self, path):
        lifted = ([(x, y, z + 20) for x, y, z in self.CUBE[0]], self.CUBE[1])
        return et.write_3mf([("Body & co", self.CUBE, YELLOW, 0),
                             ("Lens", lifted, (0.62, 0.78, 0.88), 60),
                             ("Plain", self.CUBE, None, 0)], path)

    def test_roundtrip_colours_volume(self):
        d = tempfile.mkdtemp()
        try:
            objs = et.read_3mf(self.write(os.path.join(d, "t.3mf")))
            self.assertEqual([o["name"] for o in objs], ["Body & co", "Lens", "Plain"])
            self.assertEqual(objs[0]["color"], "#FAC71AFF")
            self.assertEqual(objs[1]["color"], "#9EC7E066")
            self.assertIsNone(objs[2]["color"])
            self.assertAlmostEqual(et.mesh_volume(objs[0]["points"], objs[0]["tris"]), 1000.0)
        finally:
            shutil.rmtree(d)

    def test_sabotage_colourless_writer_detected(self):
        d = tempfile.mkdtemp()
        try:
            real = et.write_3mf
            with mock.patch.object(et, "write_3mf", lambda items, p: real(
                    [(n, m, None, t) for n, m, _c, t in items], p)):
                objs = et.read_3mf(self.write(os.path.join(d, "t.3mf")))
            self.assertIsNone(objs[0]["color"])               # the check above would fail
        finally:
            shutil.rmtree(d)


class PrintPrepPure(unittest.TestCase):
    """R343 overhangs on plain triangle lists; R344 slicers."""

    def test_overhang(self):
        cube = ThreeMF.CUBE
        over, tot = et.overhangs(cube)
        self.assertEqual(over, 0.0)                           # bottom on the bed
        self.assertAlmostEqual(tot, 600.0)
        lifted = ([(x, y, z + 5) for x, y, z in cube[0]], cube[1])
        self.assertAlmostEqual(et.overhangs(lifted)[0], 100.0)  # a floating bottom
        # sabotage: a wrong limit (cos of the angle sign flipped) flags the top too
        cos = math.cos
        with mock.patch.object(et.math, "cos", lambda a: -cos(a)):
            self.assertGreater(et.overhangs(cube)[0], 0.0)

    def test_rotation_to_down(self):
        for n in ((1, 0, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1), (0.6, 0, 0.8)):
            q = et._rotation_to_down(n)
            v = et._qrot(q, n)
            self.assertAlmostEqual(v[2], -1.0, places=6, msg=n)

    def test_find_and_open_slicer(self):
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "BambuStudio.app"))
            os.makedirs(os.path.join(d, "Other.app"))
            found = et.find_slicers([d])
            self.assertEqual([s["name"] for s in found], ["Bambu Studio"])
            os.makedirs(os.path.join(d, "PrusaSlicer.app"))
            self.assertEqual([s["name"] for s in et.find_slicers([d])],
                             ["Bambu Studio", "PrusaSlicer"])
            ran = []
            cmd = et.open_in_slicer(["/x/a.3mf"], found[0], runner=ran.append)
            self.assertEqual(cmd, ["open", "-a", os.path.join(d, "BambuStudio.app"), "/x/a.3mf"])
            self.assertEqual(ran, [cmd])
            with mock.patch.object(et, "SLICERS", ()):          # sabotage: nothing detected
                self.assertEqual(et.find_slicers([d]), [])
        finally:
            shutil.rmtree(d)


def bom_doc():
    sh = lambda v, a: FakeShape(v, a)                      # noqa: E731
    objs = [FakeObj("Body_Shell", color=YELLOW, shape=sh(86066.9, 30000)),
            FakeObj("Tyre_FL", color=(0.1, 0.1, 0.11), shape=sh(13137.9, 5000)),
            FakeObj("Tyre_FR", color=(0.1, 0.1, 0.11), shape=sh(13137.9, 5000)),
            FakeObj("Tyre_Spare", color=(0.1, 0.1, 0.11), shape=sh(13137.9, 5000)),
            FakeObj("motherboard", AtechRole="board"),
            FakeObj("light_6", AtechRole="module", AtechModule="light", AtechPorts=[6]),
            FakeObj("dc_motor_p1", AtechRole="module", AtechModule="dc_motor", AtechPorts=[1]),
            FakeObj("light_6_cable_p6", AtechCableModule="light_6", AtechCablePort=6,
                    AtechCableLength=30.66)]
    return FakeDoc(objs)


class Bom(unittest.TestCase):
    """R346."""

    def test_bom_rows_and_csv(self):
        b = et.bom(bom_doc())
        rows = {r["part"]: r for r in b["printed"]}
        self.assertEqual(rows["Tyre"]["count"], 3)
        self.assertEqual(rows["Tyre"]["colour"], "Rubber")
        self.assertEqual(rows["Body_Shell"]["volume_cm3"], 86.07)
        self.assertAlmostEqual(rows["Body_Shell"]["mass_g"], 106.7)
        hw = [(r["kind"], r["name"], r["ports"], r["length_mm"]) for r in b["hardware"]]
        self.assertEqual(hw, [("Board", "Atech board", "", None),
                              ("Module", "Dc motor", "1", None),
                              ("Module", "Light", "6", None),
                              ("Cable", "Cable to Light", "6", 30.7)])
        rows = list(csv.reader(io.StringIO(et.bom_csv(b))))
        self.assertEqual(rows[0][:3], ["Section", "Item", "Count"])
        self.assertIn(["Printed", "Tyre", "3", "13.14", "16.3", "Rubber", "", "",
                       "Tyre_FL; Tyre_FR; Tyre_Spare"], rows)
        self.assertIn(["Atech hardware", "Cable to Light", "1", "", "", "", "6", "30.7",
                       "light_6_cable_p6"], rows)

    def test_sabotage_no_grouping_detected(self):
        with mock.patch.object(et, "round", create=True, side_effect=lambda v, n=0: id(object())):
            b = et.bom(bom_doc())
        self.assertNotIn(3, [r["count"] for r in b["printed"]])


@unittest.skipUnless(HAVE_QT, "PySide6 not available (run with the bundled python)")
class Widgets(unittest.TestCase):
    """R341/R342/R346 widgets and the shell factories, offscreen."""

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.doc = FakeDoc()
        build(self.doc, BUILD)

    def test_colour_menu(self):
        sel = [self.doc.getObject("Body")]
        m = et.ColourMenu(None, lambda: self.doc, lambda: sel)
        self.assertEqual(len(m.swatches), len(et.palette()))
        self.assertEqual(m.swatches[0].accessibleName(), "Rubber")
        names = [s.accessibleName() for s in m.swatches]
        m.swatches[names.index("Signal red")].click()
        self.assertEqual(tuple(round(c, 2) for c in sel[0].ViewObject.ShapeColor[:3]), RED)
        self.assertEqual(et.overrides(self.doc)["Body"]["color"], list(RED))
        m.transparency_slider.setValue(40)
        m.transparency_slider.sliderReleased.emit()
        self.assertEqual(sel[0].ViewObject.Transparency, 40)
        self.assertEqual(m.transparency_slider.accessibleName(), "Transparency")
        m.reset_action.trigger()
        self.assertEqual(tuple(round(c, 2) for c in sel[0].ViewObject.ShapeColor[:3]), YELLOW)
        self.assertNotIn("Body", et.overrides(self.doc))

    def test_export_dialog_defaults(self):
        d = et.ExportDialog(None, lambda: self.doc, lambda: [], slicers_fn=lambda: [])
        o = d.options()
        self.assertEqual(o, {"fmt": "3MF", "scope": "product", "quality": "Fine",
                             "include_atech": False, "lay_flat": False})
        parts = [b for b in d.scope.buttons() if b.property("key") == "parts"][0]
        parts.click()
        self.assertTrue(d.options()["lay_flat"])
        self.assertEqual(d.btn_export.accessibleName(), "Export")
        self.assertIn("CC BY-NC", d.atech.text())
        with mock.patch.object(et, "export_for_print", return_value={
                "files": ["/tmp/x.3mf"], "parts": ["Body"], "left_out": ["motherboard"],
                "skipped": [], "volumes": {}}) as ex:
            d2 = et.ExportDialog(None, lambda: self.doc, lambda: [],
                                 save_name=lambda f, s: "/tmp/x",
                                 slicers_fn=lambda: [{"name": "PrusaSlicer", "path": "/A/P.app"}],
                                 opener=lambda c: None)
            res = d2.do_export()
        self.assertEqual(ex.call_args.kwargs["include_atech"], False)
        self.assertEqual(res["files"], ["/tmp/x.3mf"])
        self.assertIn("Left out 1 Atech part", d2.status.text())
        self.assertEqual([b.text() for b in d2.slicer_buttons], ["Open in PrusaSlicer"])

    def test_bom_dialog_csv(self):
        out = os.path.join(tempfile.mkdtemp(), "b.csv")
        d = et.BomDialog(None, bom_doc, save_name=lambda: out)
        self.assertEqual(d.table.rowCount(), len(d.bom["printed"]) + len(d.bom["hardware"]))
        self.assertEqual(d.table.item(0, 0).text(), "Body_Shell")
        self.assertEqual(d.save_csv(), out)
        with open(out, encoding="utf-8") as fh:
            self.assertIn("Cable to Light", fh.read())

    def test_factories(self):
        btns = et.view_bar_buttons(None, lambda: self.doc, lambda: [])
        self.assertEqual(sorted(btns), ["colour", "explode", "export", "share"])
        for b in btns.values():
            self.assertEqual(b.objectName(), "VBtn")
            self.assertTrue(b.accessibleName())
            self.assertTrue(b.icon().isNull())
        et.restyle_buttons(btns)
        self.assertFalse(any(b.icon().isNull() for b in btns.values()))
        acts = et.menu_actions(None, lambda: self.doc, lambda: [])
        self.assertEqual([a.text() for a in acts],
                         ["Colour", "Export for print...", "Exploded view (E)",
                          "Bill of materials...", "Save share image", "Save review sheet"])
        self.assertIsNotNone(acts[0].menu())


# ======================================================================
# FreeCAD: the toy car, real files
# ======================================================================
FC_SCRIPT = r'''
import sys, os, json, math, time
R = os.environ["W4_REPO"]; OUT = os.environ["W4_BREPS"]; DST = os.environ["W4_DST"]
MODE = os.environ.get("W4_MODE", "all")
sys.path.insert(0, R + "/projects"); sys.path.insert(0, R + "/addon/AcadAgent")
import FreeCAD as App, Part
from acadagent import export_tools as et, capture
res = json.load(open(OUT + "/result.json"))
doc = App.newDocument("ToyCar")
colours = {}
for o in res["objects"]:
    f = doc.addObject("Part::Feature", o["name"]); f.Label = o["label"]
    f.Shape = Part.read(o["brep"])
    if "_cable_p" in o["name"]:
        f.addProperty("App::PropertyString", "AtechCableModule", "Atech", "")
        f.AtechCableModule = o["name"].split("_cable_p")[0]
    else:
        f.addProperty("App::PropertyBool", "AtechAgentBuilt", "Atech", "")
        f.AtechAgentBuilt = True
    v = o.get("view") or {}
    if "ShapeColor" in v:
        colours[o["label"]] = (v["ShapeColor"], v.get("Transparency", 0))
import atech_ports as ap
ap.board_object(doc)
doc.recompute()
out = {}

def put(k, v):
    out[k] = v

if MODE in ("all", "sabotage_step", "sabotage_step_safe", "sabotage_mesh"):
    if MODE in ("sabotage_step", "sabotage_step_safe"):
        et.step_safe = lambda s: s
    if MODE == "sabotage_step":
        et._step_complete = lambda p, w: True
    if MODE == "sabotage_mesh":
        et.MESH_RETRIES = ((1.0, 1.0),)
        et.MESH_VOLUME_TOL = 1e9
    fmts = ("STEP",) if MODE.startswith("sabotage_step") else ("STL", "3MF") if MODE == "sabotage_mesh" \
        else ("STL", "3MF", "STEP")
    for fmt in fmts:
        r = et.export_for_print(doc, DST + "/car", fmt=fmt, colours=colours)
        exact = sum(r["volumes"].values())
        put(fmt, {"exact": exact, "back": et.reimport_volume(r["files"][0]),
                  "parts": r["parts"], "left_out": r["left_out"], "file": r["files"][0]})
if MODE == "all":
    objs = et.read_3mf(out["3MF"]["file"])
    put("3mf_colours", {o["name"]: o["color"] for o in objs})
    # one file per part, STL: every part read back alone
    r = et.export_for_print(doc, DST + "/parts", fmt="STL", scope="parts", colours=colours)
    per = {}
    for f, lab in zip(r["files"], r["parts"]):
        per[lab] = (r["volumes"][lab], et.reimport_volume(f))
    put("per_part", per)
    # Atech parts on request (3MF holds the board mesh)
    r = et.export_for_print(doc, DST + "/withhw", fmt="3MF", include_atech=True, colours=colours)
    put("with_atech", {"parts": r["parts"], "left_out": r["left_out"]})
    # STEP of the selection keeps names
    sel = [doc.getObject("Chassis"), doc.getObject("Rim_FL")]
    r = et.export_for_print(doc, DST + "/sel", fmt="STEP", scope="selection", selection=sel)
    s = Part.Shape(); s.read(r["files"][0])
    put("sel_step", {"solids": len(s.Solids), "vol": s.Volume, "exact": sum(r["volumes"].values())})
    # print prep
    rows = et.print_report([doc.getObject(n) for n in ("Chassis", "Body_Shell", "Tyre_FL")])
    put("prep", rows)
    flat, info = et.orient_for_print(doc.getObject("Tyre_FL").Shape)
    put("tyre_flat", {"zmin": flat.BoundBox.ZMin, "info": info})
    # exploded view: moves, then every placement back exactly
    et.reapply_overrides(doc)          # the build's values recorded
    before = {o.Name: o.Placement.copy() for o in doc.Objects if hasattr(o, "Placement")}
    ex = et.Exploder(doc)
    ex.set_factor(1.0)
    moved = [o.Name for o in ex.objs if not o.Placement.isSame(before[o.Name], 1e-9)]
    board_kept = doc.getObject("motherboard").Placement.isSame(before["motherboard"], 1e-9)
    et.capture_overrides(doc)          # a build mid-explode: restored, not recorded
    back = all(o.Placement.isSame(before[o.Name], 1e-9) for o in doc.Objects
               if hasattr(o, "Placement"))
    put("explode", {"moved": len(moved), "n": len(ex.objs), "board_kept": board_kept,
                    "restored": back, "recorded": et.overrides(doc)})
    # overrides with real placements, saved in the file
    hard = doc.getObject("Hardtop")
    hard.Placement = App.Placement(App.Vector(0, 0, 30), App.Rotation(App.Vector(1, 0, 0), 20))
    doc.getObject("Grille").Visibility = False
    et.capture_overrides(doc)
    p = DST + "/car.FCStd"
    doc.saveAs(p)
    App.closeDocument(doc.Name)
    doc = App.openDocument(p)
    for n in ("Hardtop", "Grille"):            # the rebuild: same labels, the build's values
        o = doc.getObject(n)
        lab, sh = o.Label, o.Shape.copy()
        sh.Placement = App.Placement()         # the build's own placement
        doc.removeObject(n)
        f = doc.addObject("Part::Feature", n + "New"); f.Label = lab; f.Shape = sh
        f.addProperty("App::PropertyBool", "AtechAgentBuilt", "Atech", ""); f.AtechAgentBuilt = True
    applied = et.reapply_overrides(doc)
    h = doc.getObject("HardtopNew")
    put("reapply", {"applied": applied, "z": h.Placement.Base.z,
                    "angle": math.degrees(h.Placement.Rotation.Angle),
                    "grille_visible": doc.getObject("GrilleNew").Visibility,
                    "brief": et.overrides_for_brief(doc)})
    # share image without a GUI: review.py's hero, 1920 x 1080
    t = time.time()
    img = capture.share_image(doc, out_dir=DST, clipboard=False)
    from PIL import Image
    put("share", {"path": img, "size": Image.open(img).size, "s": time.time() - t})
    bom = et.bom(doc)
    put("bom", {"printed": sum(r["count"] for r in bom["printed"]),
                "hw": [r["kind"] for r in bom["hardware"]]})
if MODE in ("all", "sabotage_view"):
    # the widgets on a real document: ExplodeDialog, clipboard
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    if MODE == "sabotage_view":
        et.Exploder.restore = lambda self: None
        capture.copy_image_to_clipboard = lambda p: False
    doc = App.ActiveDocument
    before = {o.Name: o.Placement.copy() for o in doc.Objects if hasattr(o, "Placement")}
    dlg = et.ExplodeDialog(None, lambda: doc)
    dlg.show()
    dlg.slider.setValue(100)
    moved = sum(1 for o in doc.Objects if hasattr(o, "Placement")
                and not o.Placement.isSame(before[o.Name], 1e-9))
    dlg.close()
    back = all(o.Placement.isSame(before[o.Name], 1e-9) for o in doc.Objects
               if hasattr(o, "Placement"))
    app.clipboard().clear()
    img = capture.share_image(doc, out_dir=DST, clipboard=True)
    clip = app.clipboard().image()
    put("dialog", {"moved": moved, "restored": back, "accessible": dlg.slider.accessibleName(),
                   "clip": [clip.width(), clip.height()], "img": img})
sys.stdout.write("\nW4RES=" + json.dumps(out, default=str) + "\n")
sys.stdout.flush()
os._exit(0)
'''


def toycar_breps():
    """The toy car built by check.py with ATECH_CHECK_OUT, cached by hash."""
    src = os.path.join(KIT, "examples", "toy_car.py")
    with open(src, "rb") as fh:
        h = hashlib.sha1(fh.read()).hexdigest()[:12]
    out = os.path.join(tempfile.gettempdir(), "atech-w4-toycar-%s" % h)
    if os.path.isfile(os.path.join(out, "result.json")) and \
            os.path.isfile(os.path.join(out, "Chassis.brep")):
        return out
    import test_kit_examples as tke
    ws = tempfile.mkdtemp(prefix="atech-w4-ws-")
    os.makedirs(out, exist_ok=True)
    try:
        shutil.copy(src, os.path.join(ws, "model.py"))
        with open(os.path.join(ws, "intent.json"), "w", encoding="utf-8") as fh:
            json.dump(tke.intent_of(src), fh)
        env = dict(os.environ, ATECH_CHECK_SCRIPT=os.path.join(ws, "model.py"),
                   ATECH_CHECK_PNG="", ATECH_CHECK_PATH=os.path.join(REPO, "projects"),
                   ATECH_CHECK_TIMEOUT="300", ATECH_CHECK_OUT=out,
                   ATECH_ARTIFACTS=os.environ.get("ATECH_ARTIFACTS",
                                                  os.path.join(REPO, "models")))
        subprocess.run([FC, os.path.join(KIT, "check.py")], env=env, cwd=ws,
                       capture_output=True, text=True, timeout=1200)
    finally:
        shutil.rmtree(ws, ignore_errors=True)
    if not os.path.isfile(os.path.join(out, "Chassis.brep")):
        raise unittest.SkipTest("the toy car did not build (no BREPs in %s)" % out)
    return out


def run_fc(mode="all"):
    dst = tempfile.mkdtemp(prefix="atech-w4-exp-")
    script = os.path.join(dst, "w4_fc.py")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(FC_SCRIPT)
    env = dict(os.environ, W4_REPO=REPO, W4_BREPS=toycar_breps(), W4_DST=dst, W4_MODE=mode,
               ATECH_ARTIFACTS=os.environ.get("ATECH_ARTIFACTS", os.path.join(REPO, "models")))
    p = subprocess.run([FC, script], env=env, capture_output=True, text=True, timeout=1800)
    text = p.stdout + p.stderr
    k = text.rfind("W4RES=")              # FreeCAD's progress lines have no newline
    if k >= 0:
        return json.loads(text[k + len("W4RES="):].split("\n", 1)[0]), dst
    raise AssertionError("no result line:\n" + text[-3000:])


def rel(a, b):
    return abs(a - b) / b


@unittest.skipIf(FC is None, "bundled freecadcmd not found (set ATECH_FREECADCMD)")
class ToyCarFreeCAD(unittest.TestCase):
    """The PRD acceptance: STL / 3MF / STEP of the toy car within 0.5 %."""

    @classmethod
    def setUpClass(cls):
        cls.res, cls.dst = run_fc("all")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dst, ignore_errors=True)

    def test_volumes_within_half_percent(self):
        for fmt in ("STL", "3MF", "STEP"):
            r = self.res[fmt]
            with self.subTest(fmt=fmt):
                self.assertEqual(len(r["parts"]), 29)
                self.assertLess(rel(r["back"], r["exact"]), 0.005, r)
        print("\nW4 VOLUMES " + " ".join("%s %.1f/%.1f (%.3f %%)" % (
            f, self.res[f]["back"], self.res[f]["exact"],
            100 * rel(self.res[f]["back"], self.res[f]["exact"])) for f in ("STL", "3MF", "STEP")))

    def test_per_part_volumes(self):
        for lab, (exact, back) in self.res["per_part"].items():
            with self.subTest(part=lab):
                self.assertLess(rel(back, exact), 0.005)

    def test_atech_left_out_by_default(self):
        r = self.res["STL"]
        self.assertIn("motherboard", r["left_out"])
        self.assertIn("light_6_cable_p6", r["left_out"])
        self.assertNotIn("motherboard", r["parts"])
        w = self.res["with_atech"]
        self.assertIn("motherboard", w["parts"])
        self.assertEqual(w["left_out"], [])

    def test_3mf_colours(self):
        c = self.res["3mf_colours"]
        self.assertEqual(c["Body_Shell"], "#FAC71AFF")          # toy_yellow
        self.assertEqual(c["Windscreen"], "#33384080")          # smoked, 50 %
        self.assertEqual(c["Tyre_FL"], "#1A1A1CFF")             # rubber

    def test_selection_step(self):
        s = self.res["sel_step"]
        self.assertEqual(s["solids"], 2)
        self.assertLess(rel(s["vol"], s["exact"]), 0.005)

    def test_print_prep(self):
        rows = {r["label"]: r for r in self.res["prep"]}
        self.assertEqual(rows["Chassis"]["turned_deg"], 0.0)    # already flat-bottomed
        self.assertGreater(rows["Chassis"]["flat_face_mm2"], 10000)
        self.assertEqual(rows["Tyre_FL"]["turned_deg"], 90.0)   # on its side face
        self.assertTrue(any("0.8 mm" in f for f in rows["Body_Shell"]["flags"]))
        self.assertTrue(any("45 deg" in f for f in rows["Body_Shell"]["flags"]))
        self.assertAlmostEqual(self.res["tyre_flat"]["zmin"], 0.0, places=6)

    def test_exploded_view_display_only(self):
        e = self.res["explode"]
        self.assertGreater(e["moved"], 20)
        self.assertTrue(e["board_kept"])
        self.assertTrue(e["restored"])
        self.assertEqual(e["recorded"], {})

    def test_overrides_in_file_survive_rebuild(self):
        r = self.res["reapply"]
        self.assertEqual(sorted(r["applied"]), ["Grille", "Hardtop"])
        self.assertAlmostEqual(r["z"], 30.0, places=6)
        self.assertAlmostEqual(r["angle"], 20.0, places=6)
        self.assertFalse(r["grille_visible"])
        self.assertIn('"Grille": hidden', r["brief"])

    def test_share_image_headless(self):
        s = self.res["share"]
        self.assertEqual(s["size"], [1920, 1080])
        self.assertTrue(os.path.basename(s["path"]).startswith("car image "), s["path"])

    def test_explode_dialog_and_clipboard(self):
        d = self.res["dialog"]
        self.assertGreater(d["moved"], 20)
        self.assertTrue(d["restored"])
        self.assertEqual(d["accessible"], "How far apart")
        self.assertEqual(d["clip"], [1920, 1080])

    def test_bom_on_car(self):
        b = self.res["bom"]
        self.assertEqual(b["printed"], 29)
        self.assertEqual(b["hw"], ["Board", "Cable", "Cable", "Cable"])


@unittest.skipIf(FC is None, "bundled freecadcmd not found (set ATECH_FREECADCMD)")
class ToyCarSabotage(unittest.TestCase):
    """The volume check catches the two real export faults it was built on."""

    def test_sabotage_step_both_guards_off_fails_volume(self):
        # step_safe and the face-count check off: the chassis and the body
        # shell come back as open shells, far beyond 0.5 %
        res, dst = run_fc("sabotage_step")
        shutil.rmtree(dst, ignore_errors=True)
        self.assertGreater(rel(res["STEP"]["back"], res["STEP"]["exact"]), 0.005)

    def test_step_face_check_alone_rescues(self):
        # only step_safe off: write_step's face count re-writes as B-splines
        res, dst = run_fc("sabotage_step_safe")
        shutil.rmtree(dst, ignore_errors=True)
        self.assertLess(rel(res["STEP"]["back"], res["STEP"]["exact"]), 0.005)

    def test_sabotage_view_no_restore_no_clipboard(self):
        res, dst = run_fc("sabotage_view")
        shutil.rmtree(dst, ignore_errors=True)
        self.assertFalse(res["dialog"]["restored"])
        self.assertEqual(res["dialog"]["clip"], [0, 0])

    def test_sabotage_single_pass_mesh_fails_volume(self):
        res, dst = run_fc("sabotage_mesh")
        shutil.rmtree(dst, ignore_errors=True)
        for fmt in ("STL", "3MF"):
            self.assertGreater(rel(res[fmt]["back"], res[fmt]["exact"]), 0.005, fmt)


if __name__ == "__main__":
    unittest.main()
