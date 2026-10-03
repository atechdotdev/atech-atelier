"""Tests for the agent kit (atech_cad, check.py, examples) and sandbox.py.

Runs under SYSTEM python (pytest or plain `python3 test_agent_kit.py`); every
FreeCAD step runs in the bundled freecadcmd as a child, one at a time (repo
rule). Skips when freecadcmd is missing. Set ATECH_FREECADCMD to point at a
different build.

What is pinned (release PRD S08, S09, S11, R12):
  S08  every atech_cad helper against a closed-form volume, and the sabotage
       run proves the suite can fail
  S09  check.py: JSON line, error line numbers, headless patch, timeout, PNG
  S11  each shipped example builds under check.py: ok, 1 solid per object
  R12  sandbox: builds in a child, BREPs import back with the same volume,
       a `while True` is killed at the timeout while the caller's loop keeps
       ticking, scratch HOME, no network, no view of the real home (bwrap)
"""
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
sys.path.insert(0, ADDON)

from acadagent import sandbox  # noqa: E402

KIT = sandbox.KIT_DIR
PROJECTS = os.path.normpath(os.path.join(ADDON, "..", "..", "projects"))
FC = sandbox.find_freecadcmd()
try:
    EXAMPLES = sorted(f for f in os.listdir(os.path.join(KIT, "examples")) if f.endswith(".py"))
except OSError:
    # Guarded (R63): a missing examples dir must fail KitFiles below, not
    # crash the import and take the whole CI run down with it.
    EXAMPLES = []
TIMINGS = {}
# CI has no freecadcmd, so the FreeCAD classes skip there. A release run sets
# ATECH_REQUIRE_FREECADCMD=1 so a missing freecadcmd FAILS instead.
if FC is None and os.environ.get("ATECH_REQUIRE_FREECADCMD") == "1":
    raise RuntimeError("ATECH_REQUIRE_FREECADCMD=1 but no freecadcmd was found "
                       "(set ATECH_FREECADCMD)")


def fc(script, env=None, timeout=300):
    e = dict(os.environ, **(env or {}))
    p = subprocess.run([FC, script], env=e, capture_output=True, text=True,
                       timeout=timeout, cwd=tempfile.gettempdir())
    return p.stdout + p.stderr


def check_json(text):
    for line in reversed(text.splitlines()):
        if line.startswith("ATECH_CHECK="):
            return json.loads(line[len("ATECH_CHECK="):])
    raise AssertionError("no ATECH_CHECK line in:\n" + text[-3000:])


def run_check(code, extra_env=None):
    ws = tempfile.mkdtemp(prefix="atech-kit-test-")
    try:
        with open(os.path.join(ws, "model.py"), "w", encoding="utf-8") as fh:
            fh.write(code)
        env = {"ATECH_CHECK_SCRIPT": os.path.join(ws, "model.py"),
               "ATECH_CHECK_PNG": ""}
        env.update(extra_env or {})
        return check_json(fc(os.path.join(KIT, "check.py"), env))
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def workspace(code):
    ws = tempfile.mkdtemp(prefix="atech-sbx-test-")
    with open(os.path.join(ws, "model.py"), "w", encoding="utf-8") as fh:
        fh.write(code)
    return ws


class KitFiles(unittest.TestCase):
    """No FreeCAD needed: what CI can check about the kit (R63)."""

    def test_kit_files_present_and_compile(self):
        for name in ("atech_cad.py", "check.py"):
            path = os.path.join(KIT, name)
            self.assertTrue(os.path.isfile(path), path)
            with open(path, encoding="utf-8") as fh:
                compile(fh.read(), path, "exec")

    def test_examples_present_and_compile(self):
        self.assertTrue(EXAMPLES, "no examples in %s" % os.path.join(KIT, "examples"))
        for ex in EXAMPLES:
            path = os.path.join(KIT, "examples", ex)
            with open(path, encoding="utf-8") as fh:
                compile(fh.read(), path, "exec")

    def test_S60_wedge_on_the_helper_card(self):
        # build.helper_card() lists the FunctionDefs named in __all__ with
        # their real signature and first docstring sentence (read by ast):
        # wedge must be one, its sizes named
        import ast
        with open(os.path.join(KIT, "atech_cad.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        names = [e.value for n in tree.body if isinstance(n, ast.Assign)
                 and any(getattr(t, "id", None) == "__all__" for t in n.targets)
                 for e in n.value.elts]
        self.assertIn("wedge", names)
        fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "wedge"]
        self.assertEqual(ast.unparse(fn[0].args),
                         "x, y, z, top_x=0.0, top_y=None, at=(0, 0, 0), top_at=None")
        first = " ".join(ast.get_docstring(fn[0]).split("\n\n")[0].split())
        self.assertLessEqual(len(first), 170, first)       # the card's cut
        self.assertIn("makeWedge", first)

    def test_find_freecadcmd_is_none_or_executable(self):
        self.assertTrue(FC is None or (os.path.isfile(FC) and os.access(FC, os.X_OK)), FC)


BOX = ("import Part\n"
       "doc.addObject('Part::Feature', 'Block').Shape = Part.makeBox(10, 20, 30)\n")


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class AtechCad(unittest.TestCase):
    def test_helpers_closed_form(self):
        out = fc(os.path.join(HERE, "fc_atech_cad.py"))
        self.assertIn("ATECH_CAD_TESTS=0", out, out[-4000:])

    def test_sabotage_is_caught(self):
        out = fc(os.path.join(HERE, "fc_atech_cad.py"), {"ATECH_CAD_SABOTAGE": "1"})
        self.assertIn("ATECH_CAD_TESTS=", out)
        self.assertNotIn("ATECH_CAD_TESTS=0", out, "sabotaged hole() went unnoticed")


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class Check(unittest.TestCase):
    def test_examples_build(self):
        png_dir = tempfile.mkdtemp(prefix="atech-kit-png-")
        try:
            for ex in EXAMPLES:
                with self.subTest(example=ex):
                    png = os.path.join(png_dir, ex + ".png")
                    env = {"ATECH_CHECK_SCRIPT": os.path.join(KIT, "examples", ex),
                           "ATECH_CHECK_PNG": png}
                    if ex.startswith("atech_"):
                        # S38: the Atech example needs the module library
                        if not os.path.isfile(os.path.join(PROJECTS, "atech_ports.py")):
                            continue
                        env["ATECH_CHECK_PATH"] = PROJECTS
                    t0 = time.time()
                    r = check_json(fc(os.path.join(KIT, "check.py"), env))
                    if ex.startswith("atech_") and "LibraryMissing" in (r.get("error") or ""):
                        continue            # library code without its data here
                    TIMINGS["check " + ex] = round(time.time() - t0, 2)
                    self.assertTrue(r["ok"], r.get("error"))
                    self.assertEqual(r["warnings"], [])
                    self.assertTrue(r["objects"])
                    for o in r["objects"]:
                        self.assertTrue(o["valid"], o)
                        self.assertEqual(o["solids"], 1, o)
                    self.assertTrue(os.path.getsize(png) > 10000, "PNG empty")
        finally:
            shutil.rmtree(png_dir, ignore_errors=True)

    def test_error_line_numbers(self):
        r = run_check("import Part\nx = 1\nraise ValueError('boom')\n")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error_lines"][-1], {"line": 3, "code": "raise ValueError('boom')"})
        self.assertIn("boom", r["error"])

    def test_syntax_error_line(self):
        r = run_check("import Part\n\ndef f(:\n    pass\n")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error_lines"][-1]["line"], 3, r)

    def test_added_nothing(self):
        r = run_check("import Part\ns = Part.makeBox(1, 1, 1)\n")
        self.assertFalse(r["ok"])
        self.assertIn("added no shape", r["error"])

    def test_measures_tight_bbox_and_warns_two_solids(self):
        r = run_check("import Part\n"
                      "c = Part.makeCompound([Part.makeBox(10,10,10),"
                      " Part.makeBox(10,10,10, App.Vector(20,0,0))])\n"
                      "doc.addObject('Part::Feature', 'Pair').Shape = c\n")
        self.assertTrue(r["ok"], r.get("error"))
        o = r["objects"][0]
        self.assertEqual((o["solids"], o["size"]), (2, [30.0, 10.0, 10.0]))
        self.assertAlmostEqual(o["volume_mm3"], 2000.0, places=3)
        self.assertTrue(any("2 separate solids" in w for w in r["warnings"]))

    def test_headless_patch_for_colours(self):
        r = run_check(BOX + "doc.getObject('Block').ViewObject.ShapeColor = (1.0, 0.0, 0.0)\n")
        self.assertTrue(r["ok"], r.get("error"))
        self.assertTrue(r["headless_patched"])

    def test_timeout_stops_endless_loop(self):
        t0 = time.time()
        r = run_check("x = 0\nwhile True:\n    x += 1\n", {"ATECH_CHECK_TIMEOUT": "2"})
        self.assertFalse(r["ok"])
        self.assertTrue(r["timed_out"])
        self.assertIn(r["error_lines"][-1]["line"], (2, 3))
        self.assertLess(time.time() - t0, 30)

    def test_timeout_not_swallowed_by_except_exception(self):
        # ScriptTimeout is a BaseException: `except Exception` cannot eat it.
        r = run_check("import time\nwhile True:\n    try:\n        time.sleep(0.01)\n"
                      "    except Exception:\n        pass\n",
                      {"ATECH_CHECK_TIMEOUT": "2"})
        self.assertFalse(r["ok"])
        self.assertTrue(r["timed_out"])
        self.assertIn(r["error_lines"][-1]["line"], (4, 5, 6))

    def test_watchdog_when_every_exception_is_swallowed(self):
        # No CPU is burnt, so RLIMIT_CPU would never fire: the wall-clock
        # watchdog must still end the run with a result line.
        t0 = time.time()
        r = run_check("import time\nwhile True:\n    try:\n        time.sleep(0.01)\n"
                      "    except BaseException:\n        pass\n",
                      {"ATECH_CHECK_TIMEOUT": "2"})
        self.assertFalse(r["ok"])
        self.assertTrue(r["timed_out"])
        self.assertLess(time.time() - t0, 40)

    def test_kit_importable_from_model(self):
        r = run_check("import atech_cad as cad\n"
                      "doc.addObject('Part::Feature', 'B').Shape = cad.rounded_box(10, 10, 10, 2)\n")
        self.assertTrue(r["ok"], r.get("error"))


KIT_ROUND4 = r"""import numpy as np, Part, Mesh, MeshPart
import atech_cad as cad, atech_geom as g
V = App.Vector
out = {}
# R114(b): a numpy int radius is a number
b = cad.rounded_box(20, 20, 20, 0)
f = cad.fillet_safe(b, np.int64(2), cad.edges_parallel(b, "Z"))
out["np_int_fillet"] = [cad.last_reason(), f.Volume < b.Volume]
# R114(a): two coaxial blind bores of one diameter are two bores ...
c = Part.makeCylinder(10, 40)
c = cad.hole(c, at=(0, 0, 40), axis="-Z", d=5, depth=15)
c = cad.hole(c, at=(0, 0, 0), axis="+Z", d=5, depth=15)
out["coupler"] = [x["blind"] for x in g.bores(c)]
# ... and one hole through both walls of a hollow box stays ONE hole
box = cad.rounded_box(30, 30, 30, 0)
box = cad.shell(box, 2, cad.faces_at(box, "+Z"))
box = cad.hole(box, at=(0, 15, 15), axis="+X", d=4, through=True)
out["through_both_walls"] = [x["d_mm"] for x in g.bores(box) if abs(x["d_mm"] - 4) < 0.01]
# S40: a cut that leaves a stray sliver raises; a real split does not
bar = Part.makeBox(50, 10, 10)
try:
    cad.cut(bar, Part.makeBox(1, 12, 12, V(47, -1, -1)))
    out["stray"] = "no error"
except cad.CadError as e:
    out["stray"] = str(e)
out["halves"] = len(cad.cut(bar, Part.makeBox(1, 12, 12, V(24.5, -1, -1))).Solids)
try:
    cad.rounded_box(8, 20, 10, 6)
except cad.CadError as e:
    out["rbox"] = str(e)
# R126 / R114(c): the desk, with the exact shift
mesh = lambda s: MeshPart.meshFromShape(Shape=s, LinearDeflection=0.5)
board = {"label": "Board", "mesh": mesh(Part.makeBox(60, 2, 100, V(0, 0, 5)))}
def lay(parts):
    return g.atech_layout([{"label": l, "shape": s} for l, s in parts], board, [])
out["below"] = lay([("Case", Part.makeBox(70, 12, 110, V(-5, -5, -0.27)))])
out["floats"] = lay([("Case", Part.makeBox(70, 12, 110, V(-5, -5, 0.6)))])
out["rests"] = lay([("Case", Part.makeBox(70, 12, 110, V(-5, -5, 0)))])
out["unrelated"] = lay([("Case", Part.makeBox(70, 12, 110, V(-5, -5, 0))),
                        ("Bracket", Part.makeBox(10, 10, 10, V(500, 0, -10)))])
out["board_only"] = lay([("Bracket", Part.makeBox(10, 10, 10, V(500, 0, -10)))])
print("ROUND4=" + __import__("json").dumps(out, default=str))
doc.addObject("Part::Feature", "B").Shape = b
"""


def _round4(r):
    line = [l for l in (r.get("stdout") or "").splitlines() if l.startswith("ROUND4=")]
    if not line:
        raise AssertionError("no ROUND4 line: %s" % r.get("error"))
    return json.loads(line[-1][len("ROUND4="):])


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class Round4Kit(unittest.TestCase):
    """R114 R126 S37 S39 S40 against the real kernel."""

    @classmethod
    def setUpClass(cls):
        cls.r = run_check(KIT_ROUND4)
        cls.out = _round4(cls.r)

    def test_R114b_numpy_int_radius(self):
        self.assertEqual(self.out["np_int_fillet"], [None, True])

    def test_R114a_coaxial_blind_bores_are_two(self):
        self.assertEqual(self.out["coupler"], [True, True])

    def test_R114a_hole_across_a_cavity_is_one(self):
        self.assertEqual(self.out["through_both_walls"], [4.0])

    def test_S40_stray_sliver_raises_real_split_does_not(self):
        self.assertIn("stray", self.out["stray"])
        self.assertEqual(self.out["halves"], 2)
        self.assertIn("use r=3.9 or less", self.out["rbox"])

    def test_R126_exact_shift_both_ways(self):
        below, _f = self.out["below"]
        self.assertEqual(len(below), 1, below)
        self.assertIn("below the desk", below[0])
        self.assertIn("by +0.27 mm in Z", below[0])
        floats, _f = self.out["floats"]
        self.assertEqual(len(floats), 1, floats)
        self.assertIn("by -0.60 mm in Z", floats[0])
        self.assertEqual(self.out["rests"][0], [])

    def test_R114c_unrelated_part_not_judged(self):
        probs, facts = self.out["unrelated"]
        self.assertEqual(probs, [])
        self.assertEqual(facts["unrelated_parts"], ["Bracket"])
        self.assertEqual(self.out["board_only"][0], [])

    def _ws_check(self, ws, png=True):
        env = {"ATECH_CHECK_SCRIPT": os.path.join(ws, "model.py"),
               "ATECH_CHECK_PNG": os.path.join(ws, "check.png") if png else ""}
        t0 = time.time()
        text = fc(os.path.join(KIT, "check.py"), env)
        return check_json(text), text, time.time() - t0

    def test_S39_no_render_on_a_failed_check(self):
        ws = workspace(BOX + "doc.addObject('Part::Feature', 'Other').Shape = "
                             "Part.makeBox(10, 20, 30, App.Vector(5, 0, 0))\n")
        try:
            with open(os.path.join(ws, "check.png"), "wb") as fh:
                fh.write(b"stale")
            r, text, secs = self._ws_check(ws)
            self.assertTrue(r["problems"], r)
            self.assertIsNone(r["png"])
            self.assertIn("render_skipped", r)
            self.assertIn("PNG not drawn", text)
            self.assertFalse(os.path.exists(os.path.join(ws, "check.png")))
            TIMINGS["S39 failed check, no render (s)"] = round(secs, 2)
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_S37_intent_changed_between_checks(self):
        ws = workspace(BOX)
        try:
            with open(os.path.join(ws, "intent.json"), "w") as fh:
                json.dump({"size_mm": [10, 20, 30], "single_body": True}, fh)
            r1, _t, _s = self._ws_check(ws, png=False)
            self.assertEqual(r1["problems"], [])
            # same content, other key order and spacing: not a change
            with open(os.path.join(ws, "intent.json"), "w") as fh:
                fh.write('{"single_body": true,  "size_mm": [10, 20, 30]}')
            r2, _t, _s = self._ws_check(ws, png=False)
            self.assertEqual(r2["problems"], [])
            # edited to match another measurement: INTENT CHANGED
            with open(os.path.join(ws, "intent.json"), "w") as fh:
                json.dump({"size_mm": [10, 20, 31], "single_body": True}, fh)
            r3, text, _s = self._ws_check(ws, png=False)
            self.assertTrue(any(p.startswith("INTENT CHANGED") for p in r3["problems"]),
                            r3["problems"])
            self.assertTrue(text.strip().splitlines()[-1].startswith("CHECK FAIL: INTENT CHANGED"))
            # deleted: still a change
            os.unlink(os.path.join(ws, "intent.json"))
            r4, _t, _s = self._ws_check(ws, png=False)
            self.assertTrue(any("was deleted" in p for p in r4["problems"]), r4["problems"])
        finally:
            shutil.rmtree(ws, ignore_errors=True)


KIT_ROUND5 = r"""import time, json, random, Part, MeshPart
import atech_geom as g
V = App.Vector
out = {}
# R129: a HEAVY solid (a fine sphere mesh made solid, thousands of planar
# faces) - the class of shape that stalled the dogfood harness 10 min
sph = Part.makeSphere(20)
m = MeshPart.meshFromShape(Shape=sph, LinearDeflection=0.02, AngularDeflection=0.08,
                           Relative=False)
sh = Part.Shape(); sh.makeShapeFromMesh(m.Topology, 0.01)
heavy = Part.makeSolid(sh)
out["faces"] = g.n_faces(heavy)
out["heavy"] = g.heavy(heavy)
random.seed(7)
pts = [V(random.uniform(-25, 25), random.uniform(-25, 25), random.uniform(-25, 25))
       for _ in range(1500)]
pts = [p for p in pts if abs(p.Length - 20) > 0.2]      # judged analytically
t = time.time(); got = g.points_inside(heavy, pts); out["inside_s"] = time.time() - t
out["inside_n"] = len(pts)
out["inside_wrong"] = sum(1 for p, k in zip(pts, got) if k != (p.Length < 20))
# a LIGHT curved shape with many points: the hybrid equals OCCT's own answer
cyl = Part.makeCylinder(10, 20)
cp = [V(random.uniform(-12, 12), random.uniform(-12, 12), random.uniform(-2, 22))
      for _ in range(600)] + [V(10.0, 0, 5), V(9.995, 0, 5), V(0, 0, 20.0)]
exact = [bool(cyl.isInside(p, 0.01, False)) for p in cp]
out["light_mismatch"] = sum(1 for a, b in zip(exact, g.points_inside(cyl, cp)) if a != b)
# distance: sampled upper bound for a box 0.3 mm above the sphere's top
d, ex = g.distance(heavy, Part.makeBox(4, 4, 4, V(-2, -2, 20.3)), limit=0.5)
out["dist"] = [round(d, 3), ex]
# fragments: a cube sunk into the sphere touches it; one 4 mm off it is a stray
t = time.time()
out["frag_touch"] = g.fragments(Part.makeCompound([heavy, Part.makeBox(2, 2, 2, V(-1, -1, 19.5))]))
out["frag_apart"] = g.fragments(Part.makeCompound([heavy, Part.makeBox(2, 2, 2, V(14, 14, 14))]))
out["frag_s"] = time.time() - t
# overlaps / floating with the heavy solid, a light box and a mesh
mesh = MeshPart.meshFromShape(Shape=Part.makeBox(6, 6, 6, V(-3, -3, 16)), LinearDeflection=0.5)
items = [{"name": "H", "label": "H", "shape": heavy, "role": None},
         {"name": "B", "label": "B", "shape": Part.makeBox(4, 4, 4, V(-2, -2, 20.3)), "role": None},
         {"name": "M", "label": "M", "mesh": mesh, "role": "module"}]
t = time.time(); out["overlaps"] = g.overlaps(items)[0]; out["overlaps_s"] = time.time() - t
t = time.time(); out["floating"] = g.floating(items); out["floating_s"] = time.time() - t
# a many-faced B-REP (a plate with 2 100+ round holes) is NOT heavy: its
# tessellation took 113-117 s where OCCT's common() takes 0.2 s (review)
# (extruded from a face with the hole wires - no boolean, cheap to build)
holes = [Part.Wire(Part.makeCircle(0.6, V(4 + i * 1.95, 4 + j * 1.95, 0)))
         for i in range(48) for j in range(48)]
outer = Part.Wire(Part.makePolygon([V(0, 0, 0), V(100, 0, 0), V(100, 100, 0),
                                    V(0, 100, 0), V(0, 0, 0)]))
plate = Part.Face([outer] + holes).extrude(V(0, 0, 10))
out["brep_faces"] = g.n_faces(plate)
out["brep_heavy"] = g.heavy(plate)
pl = [{"name": "P", "label": "P", "shape": plate, "role": None},
      {"name": "L", "label": "L", "shape": Part.makeBox(100, 100, 2, V(0, 0, 9.95)), "role": None}]
t = time.time(); out["brep_overlaps"] = g.overlaps(pl)[0]; out["brep_s"] = time.time() - t
# R129: its tessellation would take minutes - the wall probe leaves it out
# (and says so) instead of stalling ./check (it took 37 s inside thin_walls)
out["plate_loops"] = g.busiest_face_loops(plate)
out["plate_slow"] = g.tess_slow(plate)
t = time.time(); w = g.thin_walls([{"label": "P", "shape": plate}]); out["plate_walls_s"] = time.time() - t
out["plate_walls"] = w["parts"]
print("ROUND5=" + json.dumps(out, default=str))
doc.addObject("Part::Feature", "B").Shape = Part.makeBox(1, 1, 1)
"""

# R137 (D54, s5a2b): board + two modules in a case open at both X ends,
# closed by two flush end caps. PLUG > 0 adds a press-fit plug that much too
# wide for the opening: it collides with the case walls.
ATECH_CLOSED = r"""import Part
import atech_ports as ap
import atech_cad as cad
from FreeCAD import Vector, Placement, Rotation
W, C, PLUG = 2.0, 2.5, %(plug)r
board = ap.board_object(doc)


def seat_all(lift):
    board.Placement = Placement(Vector(0, 0, lift), Rotation())
    return [ap.seat(doc, "button", 1), ap.seat(doc, "temp_humidity", 6)]


mods = seat_all(0)
low = cad.bound_of(board, *mods).ZMin
for m in mods:
    ap.remove(doc, m.AtechPorts[0])
mods = seat_all(W + C - low)
bb = cad.bound_of(board, *mods)
x0, y0, z0 = bb.XMin - W - C, bb.YMin - W - C, bb.ZMin - W - C
LX, LY, LZ = (bb.XLength + 2 * (W + C), bb.YLength + 2 * (W + C),
              bb.ZLength + 2 * (W + C))
case = cad.rounded_box(LX, LY, LZ, 0, at=(x0, y0, z0))
case = cad.shell(case, W, cad.faces_at(case, "+X") + cad.faces_at(case, "-X"))
doc.addObject("Part::Feature", "Case").Shape = case
for name, xp, px in (("End_Cap_L", x0 - W, x0 - 0.5), ("End_Cap_R", x0 + LX, x0 + LX - 3.0)):
    cap = Part.makeBox(W, LY, LZ, Vector(xp, y0, z0))
    if PLUG:
        plug = Part.makeBox(3.5, LY - 2 * W + 2 * PLUG, LZ - 2 * W + 2 * PLUG,
                            Vector(px, y0 + W - PLUG, z0 + W - PLUG))
        plug = cad.cut(plug, Part.makeBox(5.5, LY - 2 * W - 2.0, LZ - 2 * W - 2.0,
                                          Vector(px - 1, y0 + W + 1.0, z0 + W + 1.0)))
        cap = cad.fuse_one(cap, plug)
    doc.addObject("Part::Feature", name).Shape = cap
"""

# R141 (D53, s4a2b): a wall plate 6 mm beyond the board + speaker in X,
# starting at their lowest point: the bottom margin is 0 mm, not 6.
ATECH_PLATE = r"""import Part
import atech_ports as ap
import atech_cad as cad
board = ap.board_object(doc)
spk = ap.seat(doc, "speaker", (9, 10))
bb = cad.bound_of(board, spk)
doc.addObject("Part::Feature", "Wall_Plate").Shape = Part.makeBox(
    bb.XLength + 12, 4, bb.ZLength + 4, App.Vector(bb.XMin - 6, bb.YMin - 12.5, bb.ZMin))
"""


def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class Round5Kit(unittest.TestCase):
    """R129 R135 R137 R141 against the real kernel."""

    def _ws_check(self, ws, atech=False, extra=None):
        env = {"ATECH_CHECK_SCRIPT": os.path.join(ws, "model.py"), "ATECH_CHECK_PNG": ""}
        env.update(extra or {})
        if atech:
            if not os.path.isfile(os.path.join(PROJECTS, "atech_ports.py")):
                self.skipTest("no Atech library here")
            env["ATECH_CHECK_PATH"] = PROJECTS
        text = fc(os.path.join(KIT, "check.py"), env)
        r = check_json(text)
        if atech and "LibraryMissing" in (r.get("error") or ""):
            self.skipTest("Atech library code without its data here")
        return r, text

    def _atech(self, code, intent, extra=None):
        ws = workspace(code)
        try:
            if intent is not None:
                with open(os.path.join(ws, "intent.json"), "w") as fh:
                    json.dump(intent, fh)
            return self._ws_check(ws, atech=True, extra=extra)
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    # ---------------------------------------------------------------- R129
    def test_R129_heavy_solid_is_fast_and_right(self):
        r = run_check(KIT_ROUND5)
        line = [l for l in (r.get("stdout") or "").splitlines() if l.startswith("ROUND5=")]
        self.assertTrue(line, r.get("error"))
        out = json.loads(line[-1][len("ROUND5="):])
        self.assertTrue(out["heavy"], out["faces"])
        self.assertEqual(out["inside_wrong"], 0, out)
        self.assertEqual(out["light_mismatch"], 0, out)
        d, exact = out["dist"]
        self.assertFalse(exact)                     # sampled, said so
        self.assertTrue(0.29 <= d <= 0.5, d)        # an upper bound on 0.3
        self.assertIsNone(out["frag_touch"])
        self.assertIsNotNone(out["frag_apart"])
        self.assertEqual(out["floating"], [])       # B is 0.3 mm from H
        # the mesh cube M (z 16 .. 22) sits inside H's top, and B (z 20.3 ..
        # 24.3) runs 1.7 mm down into M: 4 x 4 x 1.7 = 27.2 mm3. R214: that
        # was missed while only M's vertices were tested inside B (none of
        # M's corners is in B); B's own samples inside M find it
        self.assertEqual([(h["a"], h["b"]) for h in out["overlaps"]],
                         [("H", "M"), ("B", "M")])
        self.assertIn("mesh_points_inside", out["overlaps"][0])
        for k in ("inside_s", "frag_s", "overlaps_s", "floating_s"):
            TIMINGS["R129 %s (faces %d)" % (k, out["faces"])] = round(out[k], 3)
            self.assertLess(out[k], 5.0, (k, out[k]))   # was minutes (0.3 s/point)
        # a many-faced B-rep stays exact (OCCT): a volume, fast
        self.assertGreater(out["brep_faces"], 2000)
        self.assertFalse(out["brep_heavy"])
        self.assertEqual(len(out["brep_overlaps"]), 1, out["brep_overlaps"])
        self.assertIn("volume_mm3", out["brep_overlaps"][0])
        TIMINGS["R129 brep_overlaps_s (faces %d)" % out["brep_faces"]] = round(out["brep_s"], 3)
        self.assertLess(out["brep_s"], 5.0)
        self.assertEqual(out["plate_loops"], 48 * 48 + 1)
        self.assertTrue(out["plate_slow"])
        self.assertIn("seconds to tessellate", out["plate_walls"][0]["skipped"])
        self.assertLess(out["plate_walls_s"], 1.0)
        TIMINGS["R129 wall probe on the 2 304-hole plate (s)"] = round(out["plate_walls_s"], 3)

    # ---------------------------------------------------------------- R135
    def test_R135_model_py_cannot_delete_or_rewrite_the_record(self):
        rm = BOX + ("import os\nws = os.path.dirname(os.environ['ATECH_CHECK_SCRIPT'])\n"
                    "p = os.path.join(ws, '.intent_first.json')\n")
        ws = workspace(rm + "os.remove(p)\n")
        try:
            with open(os.path.join(ws, "intent.json"), "w") as fh:
                json.dump({"size_mm": [10, 20, 30]}, fh)
            first = _read(os.path.join(ws, "intent.json"))
            r, text = self._ws_check(ws)
            self.assertTrue(any(p.startswith("INTENT CHANGED") and "deleted" in p
                                for p in r["problems"]), r["problems"])
            rec = os.path.join(ws, ".intent_first.json")
            self.assertEqual(_read(rec), first)       # put back
            self.assertEqual(os.stat(rec).st_mode & 0o777, 0o444)
            # rewritten (chmod first): caught and restored too
            with open(os.path.join(ws, "model.py"), "w") as fh:
                fh.write(rm + "os.chmod(p, 0o644)\nopen(p, 'w').write('{}')\n")
            r, _t = self._ws_check(ws)
            self.assertTrue(any("rewrote" in p for p in r["problems"]), r["problems"])
            self.assertEqual(_read(rec), first)
            # deleted, then model.py raises: still put back, still reported
            with open(os.path.join(ws, "model.py"), "w") as fh:
                fh.write(rm + "os.remove(p)\nraise ValueError('after the delete')\n")
            r, text = self._ws_check(ws)
            self.assertFalse(r["ok"])
            self.assertIn("INTENT CHANGED", text.strip().splitlines()[-1])
            self.assertEqual(_read(rec), first)
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_R135_intent_edited_by_the_first_run_is_caught(self):
        # the record is taken BEFORE model.py runs: a first check whose
        # model.py rewrites intent.json fails
        ws = workspace(BOX + ("import os, json\nws = os.path.dirname("
                              "os.environ['ATECH_CHECK_SCRIPT'])\n"
                              "json.dump({'size_mm': [1, 2, 3]}, open(os.path.join("
                              "ws, 'intent.json'), 'w'))\n"))
        try:
            with open(os.path.join(ws, "intent.json"), "w") as fh:
                json.dump({"size_mm": [10, 20, 30]}, fh)
            r, _t = self._ws_check(ws)
            self.assertTrue(any(p.startswith("INTENT CHANGED") for p in r["problems"]),
                            r["problems"])
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    # ---------------------------------------------------------------- R137
    def test_R137_closed_case_with_declared_caps_passes(self):
        r, text = self._atech(ATECH_CLOSED % {"plug": 0.0},
                              {"board": "upright", "fitted_after": ["End_Cap_L", "End_Cap_R"]})
        self.assertTrue(r["ok"], r.get("error"))
        # R212: the fixture's caps are flat plates on the case ends - they
        # only touch, and that alone fails now; nothing else does
        self.assertEqual(sorted(p.split(" - ")[0] for p in r["problems"]),
                         ["joint: End_Cap_L only touches Case",
                          "joint: End_Cap_R only touches Case"], r["problems"])
        self.assertEqual(r["fitted_after"], ["End_Cap_L", "End_Cap_R"])
        self.assertIn("CHECK FAIL: joint: End_Cap_L only touches Case", text[-1500:])
        for label, v in r["atech_check"].items():
            self.assertEqual(v["slide_path"], "PASS", (label, v))

    def test_R137_undeclared_caps_fail_slide_path(self):
        r, _t = self._atech(ATECH_CLOSED % {"plug": 0.0}, {"board": "upright"})
        self.assertTrue(any("slide_path FAIL" in p for p in r["problems"]), r["problems"])

    def test_R137_colliding_cap_still_fails_with_the_volume(self):
        r, _t = self._atech(ATECH_CLOSED % {"plug": 0.02},
                            {"board": "upright", "fitted_after": ["End_Cap_L", "End_Cap_R"]})
        vols = [h.get("volume_mm3") for h in r["overlaps"]]
        self.assertEqual(len(vols), 2, r["overlaps"])
        self.assertTrue(all(v and v > 1.0 for v in vols), vols)
        self.assertTrue(any(p.startswith("OVERLAP Case and End_Cap_L overlap by")
                            for p in r["problems"]), r["problems"])
        self.assertFalse(any("slide_path FAIL" in p for p in r["problems"]), r["problems"])

    def test_R137_S50_unbuilt_fitted_after_name_is_a_note(self):
        # S50: a name model.py has not built (yet) is a NOTE, not a failure
        # of the first check; "fitted_after_missing" carries it to Studio,
        # which fails the turn if the part never appears
        r, text = self._atech(ATECH_CLOSED % {"plug": 0.0},
                              {"board": "upright", "fitted_after": ["End_Cap_L", "Lid"]})
        self.assertEqual(r["fitted_after_missing"], ["Lid"])
        self.assertFalse(any("fitted_after" in p for p in r["problems"]), r["problems"])
        self.assertTrue(any("fitted_after names Lid" in n and "Atelier fails the turn" in n
                            for n in r["notes"]), r["notes"])
        self.assertIn("NOTE intent.json fitted_after names Lid", text)
        self.assertEqual(r["fitted_after"], ["End_Cap_L"])
        # Studio's own build (the sandboxed child, ATECH_CHECK_OUT) still
        # FAILS on it: the turn must not pass with the part never built
        out = tempfile.mkdtemp(prefix="atech-out-test-")
        try:
            r, text = self._atech(ATECH_CLOSED % {"plug": 0.0},
                                  {"board": "upright", "fitted_after": ["End_Cap_L", "Lid"]},
                                  {"ATECH_CHECK_OUT": out})
        finally:
            shutil.rmtree(out, ignore_errors=True)
        self.assertEqual(r["fitted_after_missing"], ["Lid"])
        self.assertTrue(any("fitted_after names Lid: not a part model.py built" in p
                            for p in r["problems"]), r["problems"])

    # ---------------------------------------------------------------- R141
    def test_R141_margins_are_measured_per_side(self):
        r, text = self._atech(ATECH_PLATE, None)
        lay = r["atech_layout"]
        spk = [m for m in lay["margins"] if m["label"].startswith("speaker")]
        self.assertEqual(len(spk), 1, lay["margins"])
        self.assertEqual(spk[0]["part"], "Wall_Plate")
        self.assertEqual(spk[0]["mm"]["+x"], 6.0)
        together = lay["margins_all"][0]["mm"]
        self.assertEqual((together["-x"], together["+x"], together["-z"]), (6.0, 6.0, 0.0))
        self.assertIn("MARGIN board + modules together inside Wall_Plate's outline: "
                      "-X 6.0 +X 6.0", text)


sys.path.insert(0, KIT)
import atech_geom  # noqa: E402  (FreeCAD is imported inside its functions)
sys.path.remove(KIT)


class IntentRules(unittest.TestCase):
    """R151 without FreeCAD: which intent.json edits follow the user."""

    def test_request_numbers(self):
        n = atech_geom.request_numbers("an enclosure 80 x 50 x 30 mm, 2,5 mm walls, 3 cm feet")
        for v in (80, 50, 30, 2.5, 3, 30.0):
            self.assertIn(float(v), n)
        self.assertIn(50.8, [round(x, 3) for x in atech_geom.request_numbers('a 2" knob')])
        self.assertIn(30.0, atech_geom.request_numbers("80x50x30"))

    def test_R152_request_names(self):
        names = atech_geom.request_names
        self.assertTrue(names("light", "A nightlight with a window over the light"))
        self.assertFalse(names("light", "a lightweight case, highlight the edges"))
        self.assertTrue(names("button", "press to ring"))
        self.assertFalse(names("button", "a pressure sensor box"))
        self.assertIsNone(names("light", None))

    def test_R168_request_size(self):
        rs = atech_geom.request_size
        self.assertEqual(rs("Electronics enclosure 80 x 50 x 30 mm outside"),
                         ([80.0, 50.0, 30.0], "80 x 50 x 30 mm"))
        self.assertEqual(rs("a box with snap-fit lid 80x60x40")[0], [80.0, 60.0, 40.0])
        self.assertEqual(rs("a box 8 x 5 x 3 cm")[0], [80.0, 50.0, 30.0])
        self.assertIsNone(rs("a case for a 85 x 56 x 17 mm board"))
        self.assertIsNone(rs("a box, inside 80 x 50 x 30"))
        self.assertEqual(rs("80 x 50 x 30 mm outside, room for a 60 x 40 x 10 board")[0],
                         [80.0, 50.0, 30.0])
        self.assertIsNone(rs("a 80 x 50 x 30 box and a 20 x 20 x 10 box"))
        self.assertIsNone(rs("a phone stand"))
        self.assertIsNone(rs(None))
        # review r7: a bare "in" before a word is not inches, a unitless
        # count is not a size, a Raspberry Pi's size is not the case's
        self.assertEqual(rs("a box 80 x 50 x 30 in PLA")[0], [80.0, 50.0, 30.0])
        self.assertEqual([round(v, 1) for v in rs("a box 3 x 2 x 1 in")[0]],
                         [76.2, 50.8, 25.4])
        self.assertEqual(round(rs("a box 3 x 2 x 1 inches")[0][0], 1), 76.2)
        self.assertIsNone(rs("a 2 x 3 x 4 grid of cubes"))
        self.assertIsNone(rs("rpi4 case, the pi is 85 x 56 x 17"))

    def test_R169_container_names(self):
        ck = atech_geom.container_kind
        self.assertEqual(ck("Inner_Pot"), "container")
        self.assertEqual(ck("MugBody"), "container")
        self.assertEqual(ck("Enclosure_Box"), "maybe")
        self.assertIsNone(ck("Pot_Lid"))
        self.assertIsNone(ck("Potentiometer_Knob"))
        self.assertIsNone(ck("Suction_Cup"))
        self.assertIsNone(ck("Pot_Knob"))

    def test_user_values_only(self):
        ok = atech_geom.user_values_only
        req = "an enclosure 80 x 50 x 30"
        self.assertTrue(ok(b'{"size_mm": [80, 50, 32]}', b'{"size_mm": [80, 50, 30]}', req))
        self.assertTrue(ok(b'{"size_mm": [80, 50, 32]}', b'{"size_mm": [30, 80, 50]}', req))
        self.assertFalse(ok(b'{"size_mm": [80, 50, 32]}', b'{"size_mm": [80, 50, 31]}', req))
        self.assertFalse(ok(b'{"size_mm": [80, 50, 32], "single_body": true}',
                            b'{"size_mm": [80, 50, 30]}', req))          # key removed
        self.assertFalse(ok(b'{"single_body": true}', b'{"single_body": false}', req))
        self.assertTrue(ok(b'{"board": "upright"}', b'{"board": "flat"}',
                           "the board lying flat"))
        self.assertFalse(ok(b'{"size_mm": [80, 50, 32]}', b'{"size_mm": [80, 50, 30]}', ""))
        # no loophole: a tolerance widened to a number from the message, or a
        # target number dropped, does not follow the user
        self.assertFalse(ok(b'{"size_mm": [80, 50, 32]}',
                            b'{"size_mm": [80, 50, 32], "tolerance_mm": 30}', req))
        self.assertFalse(ok(b'{"size_mm": [80, 50, 32], "tolerance_mm": 1}',
                            b'{"size_mm": [80, 50, 32], "tolerance_mm": 50}', req))
        self.assertTrue(ok(b'{"size_mm": [80, 50, 32], "tolerance_mm": 1}',
                           b'{"size_mm": [80, 50, 32], "tolerance_mm": 2}',
                           req + ", tolerance 2 mm"))
        self.assertFalse(ok(b'{"size_mm": [80, 50, 32]}', b'{"size_mm": [80, 50]}', req))


INTENT_BOX = ("import Part\n"
              "doc.addObject('Part::Feature', 'Enclosure').Shape = "
              "Part.makeBox(80, 50, %g)\n")


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class Round6Kit(unittest.TestCase):
    """R128 R151 R152 R154 S48 against the real kernel."""

    def _check(self, ws, env=None, atech=False):
        e = {"ATECH_CHECK_SCRIPT": os.path.join(ws, "model.py"), "ATECH_CHECK_PNG": ""}
        if atech:
            if not os.path.isfile(os.path.join(PROJECTS, "atech_ports.py")):
                self.skipTest("no Atech library here")
            e["ATECH_CHECK_PATH"] = PROJECTS
        e.update(env or {})
        text = fc(os.path.join(KIT, "check.py"), e)
        r = check_json(text)
        if atech and "LibraryMissing" in (r.get("error") or ""):
            self.skipTest("Atech library code without its data here")
        return r, text

    @staticmethod
    def _intent(ws, size):
        with open(os.path.join(ws, "intent.json"), "w") as fh:
            json.dump({"size_mm": size, "single_body": True}, fh)

    # ---------------------------------------------------------------- R151
    def test_R151_user_turn_may_follow_the_user(self):
        """D59: the draft wrote 32 for the user's 30; correcting intent.json to
        30 within the same user turn passes - no INTENT CHANGED."""
        ws = workspace(INTENT_BOX % 32)
        try:
            self.assertTrue(atech_geom.start_turn(
                ws, "Make an enclosure 80 x 50 x 30 mm", fix=False))
            self._intent(ws, [80, 50, 32])
            r1, _t = self._check(ws)
            self.assertEqual(r1["problems"], [], r1["problems"])
            # the agent reads the request again: 30, not 32
            self._intent(ws, [80, 50, 30])
            with open(os.path.join(ws, "model.py"), "w") as fh:
                fh.write(INTENT_BOX % 30)
            r2, text = self._check(ws)
            self.assertNotIn("INTENT CHANGED", text)
            self.assertEqual(text.strip().splitlines()[-1], "CHECK PASS", text[-1500:])
            self.assertEqual(r2["objects"][0]["size"], [80.0, 50.0, 30.0])  # measures 30
            # any other value is the agent's to set in its own turn too
            self._intent(ws, [80, 50, 34])
            r3, text = self._check(ws)
            self.assertNotIn("INTENT CHANGED", text)
            # S54: 34 is no size the user's message gives - the miss is a
            # NOTE, and the user's own 30 is still measured (and met)
            self.assertEqual(r3["problems"], [], r3["problems"])
            self.assertTrue(any(n.startswith("overall size: you intended 34 mm")
                                for n in r3["notes"]), r3["notes"])
            with open(os.path.join(ws, "model.py"), "w") as fh:
                fh.write(INTENT_BOX % 27)
            r4, text = self._check(ws)          # the 34 miss is a note; 30 is not met
            self.assertTrue(any("the user asked for 30 mm, Atelier measured 27 mm" in p
                                for p in r4["problems"]), r4["problems"])
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_R151_fix_turn_is_frozen_except_for_the_users_values(self):
        ws = workspace(INTENT_BOX % 32)
        try:
            atech_geom.start_turn(ws, "Make an enclosure 80 x 50 x 30 mm", fix=False)
            self._intent(ws, [80, 50, 32])
            r, _t = self._check(ws)
            self.assertEqual(r["problems"], [])
            # Studio's fix turn: the record is the target the build was judged by
            atech_geom.start_turn(ws, "The build failed ... Fix model.py and write it "
                                      "again.", fix=True)
            self.assertEqual(atech_geom.read_turn(ws)["request"],
                             "Make an enclosure 80 x 50 x 30 mm")
            self._intent(ws, [80, 50, 33])          # not the user's value
            r, text = self._check(ws)
            bad = [p for p in r["problems"] if p.startswith("INTENT CHANGED")]
            self.assertTrue(bad, r["problems"])
            self.assertIn("fix turn", bad[0])
            self.assertIn("the user's message wins over intent.json", bad[0])
            self.assertTrue(text.strip().splitlines()[-1].startswith("CHECK FAIL: INTENT CHANGED"))
            # the user's own number is always accepted, and becomes the record
            self._intent(ws, [80, 50, 30])
            with open(os.path.join(ws, "model.py"), "w") as fh:
                fh.write(INTENT_BOX % 30)
            r, text = self._check(ws)
            self.assertNotIn("INTENT CHANGED", text)
            self.assertEqual(text.strip().splitlines()[-1], "CHECK PASS", text[-1500:])
            self.assertEqual(json.loads(_read(os.path.join(ws, ".intent_first.json")))
                             ["size_mm"], [80, 50, 30])
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_R151_model_py_cannot_touch_intent_or_the_turn_file(self):
        code = INTENT_BOX % 30 + (
            "import os, json\nws = os.path.dirname(os.environ['ATECH_CHECK_SCRIPT'])\n")
        ws = workspace(code + "json.dump({'size_mm': [1, 2, 3]}, open(os.path.join(ws, "
                              "'intent.json'), 'w'))\n")
        try:
            atech_geom.start_turn(ws, "an enclosure 80 x 50 x 30", fix=False)
            self._intent(ws, [80, 50, 30])
            r, _t = self._check(ws)
            self.assertTrue(any(p.startswith("INTENT CHANGED: model.py wrote intent.json")
                                for p in r["problems"]), r["problems"])
            turn = _read(os.path.join(ws, atech_geom.TURN))
            with open(os.path.join(ws, "model.py"), "w") as fh:
                fh.write(code + "p = os.path.join(ws, '.atech_turn.json')\nos.chmod(p, 0o644)\n"
                                "open(p, 'w').write('{\"fix\": false}')\n")
            self._intent(ws, [80, 50, 30])
            r, _t = self._check(ws)
            self.assertTrue(any("rewrote .atech_turn.json" in p for p in r["problems"]),
                            r["problems"])
            self.assertEqual(_read(os.path.join(ws, atech_geom.TURN)), turn)   # put back
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    # ---------------------------------------------------------------- R128
    def _context(self, roles=None):
        """A context folder holding the user's 20 mm box as a BREP (written
        by check.py's own ATECH_CHECK_OUT export) and its JSON index."""
        ctx = tempfile.mkdtemp(prefix="atech-ctx-test-")
        ws = workspace("import Part\ndoc.addObject('Part::Feature', 'UserBox').Shape = "
                       "Part.makeBox(20, 20, 20)\n")
        try:
            self._check(ws, {"ATECH_CHECK_OUT": ctx})
        finally:
            shutil.rmtree(ws, ignore_errors=True)
        item = {"name": "UserBox", "label": "UserBox",
                "brep": os.path.join(ctx, "UserBox.brep")}
        if roles is not None:
            item["role"] = roles
        with open(os.path.join(ctx, "context.json"), "w") as fh:
            json.dump([item], fh)
        return ctx

    STAND = ("import Part\nfrom FreeCAD import Vector\n"
             "assert doc.getObject('UserBox') is not None, 'NO CONTEXT'\n"
             "doc.addObject('Part::Feature', 'Stand').Shape = "
             "Part.makeBox(10, 10, 10, Vector(%s, 0, 0))\n%s")

    def test_R128_check_fails_on_the_users_object(self):
        ctx = self._context()
        env = {"ATECH_CHECK_CONTEXT": os.path.join(ctx, "context.json")}
        try:
            # R156: a declared pair with the user's object still fails
            for x, extra, want in ((5, "", 1000.0), (19, "", 100.0), (25, "", None),
                                   (5, "INTENDED_OVERLAPS = [('Stand', 'UserBox')]\n", 1000.0)):
                with self.subTest(x=x, declared=bool(extra)):
                    ws = workspace(self.STAND % (x, extra))
                    try:
                        r, text = self._check(ws, env)
                    finally:
                        shutil.rmtree(ws, ignore_errors=True)
                    self.assertTrue(r["ok"], r.get("error"))
                    last = text.strip().splitlines()[-1]
                    if want is None:
                        self.assertEqual(last, "CHECK PASS", text[-1500:])
                        continue
                    self.assertIn("Stand and UserBox overlap by %s mm3" % want, last)
                    self.assertIn("UserBox is the USER's object", last)
                    hit = [h for h in r["overlaps"] if h.get("user")]
                    self.assertEqual(hit[0]["user"], "UserBox")
                    self.assertEqual(hit[0]["volume_mm3"], want)
            # the user's object is never reported floating, never a result
            self.assertEqual([o["label"] for o in r["objects"]], ["Stand"])
        finally:
            shutil.rmtree(ctx, ignore_errors=True)

    def test_R128_roles_and_studio_child(self):
        ws = workspace(self.STAND % (5, ""))
        try:
            # tagged as construction (a boolean's input): not compared
            ctx = self._context(roles="context")
            r, text = self._check(ws, {"ATECH_CHECK_CONTEXT": os.path.join(ctx, "context.json")})
            self.assertEqual(text.strip().splitlines()[-1], "CHECK PASS", text[-1500:])
            shutil.rmtree(ctx, ignore_errors=True)
            # tagged "user": compared, also in Studio's build child
            ctx = self._context(roles="user")
            out = tempfile.mkdtemp(prefix="atech-out-test-")
            r, text = self._check(ws, {"ATECH_CHECK_CONTEXT": os.path.join(ctx, "context.json"),
                                       "ATECH_CHECK_OUT": out})
            self.assertIn("Stand and UserBox overlap by 1000.0 mm3", text.strip().splitlines()[-1])
            shutil.rmtree(ctx, ignore_errors=True)
            # untagged in Studio's build child: Studio's user_overlaps judges it
            ctx = self._context()
            r, text = self._check(ws, {"ATECH_CHECK_CONTEXT": os.path.join(ctx, "context.json"),
                                       "ATECH_CHECK_OUT": out})
            self.assertEqual([h for h in r["overlaps"] if h.get("user")], [])
            shutil.rmtree(ctx, ignore_errors=True)
            shutil.rmtree(out, ignore_errors=True)
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    # ---------------------------------------------------------------- R152
    def test_R152_light_sealed_in_vs_window_over_it(self):
        """D60: the "window over the light" cut in the end lid leaves the
        light's face 0 % open - a PROBLEM when the request names a light;
        the window in the wall in front of the face opens it."""
        req = "A closed nightlight box with a window over the light, USB-C power"
        runs = {}
        for where in ("lid", "front"):
            ws = workspace(NIGHTLIGHT % {"window": where, "usb": "lid"})
            try:
                with open(os.path.join(ws, "intent.json"), "w") as fh:
                    json.dump({"board": "upright", "fitted_after": ["Lid"]}, fh)
                atech_geom.start_turn(ws, req, fix=False)
                runs[where] = self._check(ws, atech=True)
            finally:
                shutil.rmtree(ws, ignore_errors=True)
        r, text = runs["lid"]
        light = [f for f in r["face_open"] if f["module"] == "light"][0]
        self.assertEqual((light["open"], light["rays"], light["kind"]), (0, 169, "light"))
        self.assertEqual(atech_geom.normal_text(light["normal"]), "+Y")
        self.assertTrue(any("is sealed in" in p and "asks for a light" in p
                            for p in r["problems"]), r["problems"])
        self.assertIn("OPEN light_p2 (a light): 0 of 169 rays from its working face (+Y)", text)
        # R164: the USB-C module is judged along its socket mouth (-X on a
        # left-edge port), where the lid's slot is
        usb = [f for f in r["face_open"] if f["module"] == "usbc"][0]
        self.assertEqual((usb["kind"], usb["face"]), ("USB-C socket", "socket"))
        self.assertEqual(atech_geom.normal_text(usb["normal"]), "-X")
        self.assertGreater(usb["open"], 0)
        r, text = runs["front"]
        light = [f for f in r["face_open"] if f["module"] == "light"][0]
        self.assertGreater(light["open"], 0)
        self.assertFalse(any("sealed in" in p for p in r["problems"]), r["problems"])
        TIMINGS["R152 face_open (s)"] = r.get("face_open_seconds")

    # ---------------------------------------------------------------- R154
    def test_R154_wall_probe(self):
        shell = ("import Part, atech_cad as cad\nb = Part.makeBox(40, 30, 20)\n"
                 "doc.addObject('Part::Feature', 'Tray').Shape = "
                 "cad.shell(b, 2, cad.faces_at(b, '+Z'))\n")
        thin = ("import Part\ndoc.addObject('Part::Feature', 'Ring').Shape = "
                "Part.makeCylinder(30, 12).cut(Part.makeCylinder(29.6, 12))\n")
        r = run_check(shell)
        m = r["walls"]["min"]
        self.assertAlmostEqual(m["mm"], 2.0, delta=0.05)
        self.assertEqual(r["warnings"], [])
        self.assertTrue(r["walls"]["complete"])
        r = run_check(thin)
        m = r["walls"]["min"]
        self.assertTrue(0.3 < m["mm"] < 0.5, m)
        self.assertTrue(any("0.4" in w and "below 0.8 mm" in w for w in r["warnings"]),
                        r["warnings"])
        self.assertEqual(r["problems"], [])                # a warning, never a failure
        TIMINGS["R154 thin ring probe (s)"] = r["walls"]["seconds"]

    # ----------------------------------------------------------------- S48
    def test_S48_rounded_box_says_which_side(self):
        r = run_check("import atech_cad as cad\n"
                      "doc.addObject('Part::Feature', 'P').Shape = "
                      "cad.rounded_box(100, 100, 6, 6, edges='all')\n")
        self.assertFalse(r["ok"])
        err = r["error"].strip().splitlines()[-1]
        for s in ("z = 6 mm", "use r=2.9 or less", "edges='vertical'", "never clamped"):
            self.assertIn(s, err)


# D60 (dogfood shift 3, t1a2): board upright, light on port 2 and USB-C on
# port 5, a closed case open at -X behind a screwed end lid. window="lid" is
# the agent's build (both openings in the lid); window="front" also cuts a
# window in the +Y wall in front of the light's face.
NIGHTLIGHT = r"""import Part
import atech_ports as ap
import atech_cad as cad
from FreeCAD import Vector, Placement, Rotation
W, C = 2.0, 2.5
board = ap.board_object(doc)


def seat_all(lift):
    board.Placement = Placement(Vector(0, 0, lift), Rotation())
    return [ap.seat(doc, "light", 2), ap.seat(doc, "usbc", 5)]


mods = seat_all(0)
low = cad.bound_of(board, *mods).ZMin
for m in mods:
    ap.remove(doc, m.AtechPorts[0])
mods = seat_all(W + C - low)
bb = cad.bound_of(board, *mods)
X0, Y0, Z0 = bb.XMin - W - C, bb.YMin - W - C, bb.ZMin - W - C
LX, LY, LZ = bb.XLength + 2 * (W + C), bb.YLength + 2 * (W + C), bb.ZLength + 2 * (W + C)
case = cad.rounded_box(LX, LY, LZ, 3.0, at=(X0, Y0, Z0))
case = cad.shell(case, W, cad.faces_at(case, "-X"))
lbb, ubb = ap.bbox(mods[0]), ap.bbox(mods[1])
if %(window)r == "front":
    case = cad.cut(case, Part.makeBox(lbb.XLength - 4, W + 1, lbb.ZLength - 4,
                                      Vector(lbb.XMin + 2, Y0 + LY - W - 0.5, lbb.ZMin + 2)))
if %(usb)r == "cover":      # D64: the "USB-C slot" over the module's cover (+Y)
    case = cad.cut(case, Part.makeBox(ubb.XLength - 5, W + 1, ubb.ZLength - 10,
                                      Vector(ubb.XMin + 2.5, Y0 + LY - W - 0.5, ubb.ZMin + 5)))
doc.addObject("Part::Feature", "Case").Shape = case
lid = cad.rounded_box(W, LY, LZ, 0.0, at=(X0 - W, Y0, Z0))
cuts = [Part.makeBox(W + 2, 7.0, 15.0, Vector(X0 - W - 1, lbb.Center.y - 3.5,
                                              lbb.Center.z - 7.5))]
if %(usb)r == "lid":        # in the end lid, in front of the socket mouth
    cuts.append(Part.makeBox(W + 2, 12.0, 7.0, Vector(X0 - W - 1, ubb.Center.y - 6.0,
                                                      ubb.Center.z - 3.5)))
lid = cad.cut(lid, cuts)
doc.addObject("Part::Feature", "Lid").Shape = lid
"""


# ---------------------------------------------------------------- round 7
# D62 (dogfood t1p2): the screw-top jar. The lid's 16 grip flutes (R 1.2 at
# the skirt's outer radius 32.4) reach R 31.2, past the thread groove's crest
# at R 31.6: they break through the skirt, leaving slivers.
JAR = r"""import Part
from FreeCAD import Vector
import atech_cad as cad
OD, H, WALL, PITCH, TURNS, CLEAR = 60.0, 50.0, 2.0, 3.0, 1.5, 0.4
THREAD_D, THREAD_Z0, LID_TOP, LID_SKIRT, LID_WALL, LID_GAP = 1.2, 42.0, 2.5, 12.0, 2.0, 0.3
GRIP_N, GRIP_R = 16, 1.2
R = OD / 2.0


def helical_rib(r_base, height, extra=0.0):
    # the agent's own call, kept for fidelity (TRAPS: makeLongHelix is not
    # the helix makeHelix is; the D62 lid was built with it)
    spine = Part.Wire(Part.makeLongHelix(PITCH, height, r_base, 0, False))
    half = PITCH / 2.0 - 0.25 + extra
    pts = [Vector(r_base - 0.8, 0, -half), Vector(r_base + THREAD_D + extra, 0, 0),
           Vector(r_base - 0.8, 0, half), Vector(r_base - 0.8, 0, -half)]
    return spine.makePipeShell([Part.Wire(Part.makePolygon(pts))], True, True)


r_lid_i = R + CLEAR
r_lid_o = r_lid_i + LID_WALL
lid_z0 = H + LID_GAP - LID_SKIRT
groove = helical_rib(R, THREAD_Z0 + PITCH * TURNS - lid_z0, CLEAR)
groove.rotate(Vector(0, 0, 0), Vector(0, 0, 1), -360.0 * (THREAD_Z0 - lid_z0) / PITCH)
groove.translate(Vector(0, 0, lid_z0))
flute = Part.makeCylinder(GRIP_R, LID_SKIRT + LID_TOP, Vector(r_lid_o, 0, lid_z0))
tools = [Part.makeCylinder(r_lid_i, LID_SKIRT, Vector(0, 0, lid_z0)), groove]
tools += cad.polar_pattern(flute, GRIP_N)
lid = cad.cut(Part.makeCylinder(r_lid_o, LID_SKIRT + LID_TOP, Vector(0, 0, lid_z0)), tools)
doc.addObject("Part::Feature", "Jar_Lid").Shape = lid
"""

# R168 (D65, c3p1): an 80 x 50 x 30 enclosure whose lid sits proud on top
# (z 30..34 over a 30 mm box) or flush in a 4 mm rebate (z 26..30).
BOX_AND_LID = r"""import Part, atech_cad as cad
from FreeCAD import Vector
box = Part.makeBox(80, 50, %(box_h)g)
box = cad.shell(box, 2, cad.faces_at(box, "+Z"))
doc.addObject("Part::Feature", "Enclosure_Box").Shape = box
doc.addObject("Part::Feature", "Enclosure_Lid").Shape = Part.makeBox(
    80, 50, 4, Vector(0, 0, %(lid_z)g))
"""

# R169 (D66, c3p2): an inner pot (Ø100 x 60, 2 mm walls) closed on top by a
# solid Ø106 x 4 disc, or by a ring; the mug is the round-6 shape
# (a shelled cylinder and a handle).
POT = r"""import Part, atech_cad as cad
from FreeCAD import Vector
pot = Part.makeCylinder(50, 60)
pot = cad.shell(pot, 2, cad.faces_at(pot, "+Z"))
rim = Part.makeCylinder(53, 4, Vector(0, 0, 56))
if %(ring)r:
    rim = rim.cut(Part.makeCylinder(48, 4, Vector(0, 0, 56)))
pot = cad.fuse_one(pot, rim)
pot = cad.hole(pot, (0, 0, 2), "-Z", 8.0, through=True)       # the wick hole
doc.addObject("Part::Feature", "Inner_Pot").Shape = pot
"""
MUG = r"""import Part, atech_cad as cad
from FreeCAD import Vector
mug = Part.makeCylinder(40, 95)
mug = cad.shell(mug, 4, cad.faces_at(mug, "+Z"))
handle = Part.makeTorus(22, 5, Vector(42, 0, 50), Vector(0, 1, 0))
handle = handle.cut(Part.makeCylinder(39, 95))
doc.addObject("Part::Feature", "Mug").Shape = cad.fuse_one(mug, handle)
"""

# R170 (D67, c4p2): three Ø6 channels along Y, open upward through 4.5 mm
# push-in slots (SLOT) or closed bores
CLIP = r"""import Part
from FreeCAD import Vector
body = Part.makeBox(34, 40, 12)
for x in (7, 17, 27):
    body = body.cut(Part.makeCylinder(3, 40, Vector(x, 0, 6), Vector(0, 1, 0)))
    if %(slot)r:
        body = body.cut(Part.makeBox(4.5, 40, 7, Vector(x - 2.25, 0, 6)))
doc.addObject("Part::Feature", "Cable_Clip").Shape = body.removeSplitter()
"""

# R164: the socket mouth of a USB-C module on a left-edge and a right-edge
# port, measured by the probe from the mesh
SOCKETS = r"""import json
import atech_ports as ap, atech_geom as g
board = ap.board_object(doc)
_t, bn = g.board_tilt(board.Mesh)
out = {}
for port in (1, 11):
    m = ap.seat(doc, "usbc", port)
    axes = [list(m.Placement.Rotation.multVec(App.Vector(*e))) for e in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
    d, pts = g.socket_face(m.Mesh, bn, axes)
    bb = m.Mesh.BoundBox
    out[port] = {"dir": g.normal_text(d), "slide": list(m.AtechSlideAxis),
                 "mouth_x": [float(pts[:, 0].min()), float(pts[:, 0].max())],
                 "module_x": [bb.XMin, bb.XMax]}
light = ap.seat(doc, "light", 2)
out["light"] = g.socket_face(light.Mesh, bn)[0]
print("R164=" + json.dumps(out))
"""


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class Round7Kit(unittest.TestCase):
    """R129 R154 R156 R164 R168 R169 R170 S52 against the real kernel."""

    def _check(self, code, intent=None, request=None, env=None, atech=False):
        ws = workspace(code)
        try:
            if intent is not None:
                with open(os.path.join(ws, "intent.json"), "w") as fh:
                    json.dump(intent, fh)
            if request is not None:
                atech_geom.start_turn(ws, request, fix=False)
            e = {"ATECH_CHECK_SCRIPT": os.path.join(ws, "model.py"), "ATECH_CHECK_PNG": ""}
            if atech:
                if not os.path.isfile(os.path.join(PROJECTS, "atech_ports.py")):
                    self.skipTest("no Atech library here")
                e["ATECH_CHECK_PATH"] = PROJECTS
            e.update(env or {})
            text = fc(os.path.join(KIT, "check.py"), e)
            r = check_json(text)
            if atech and "LibraryMissing" in (r.get("error") or ""):
                self.skipTest("Atech library code without its data here")
            self.assertTrue(r["ok"], r.get("error"))
            return r, text.strip().splitlines()[-1]
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    # ---------------------------------------------------------------- R164
    def test_R164_socket_mouth_from_the_mesh(self):
        ws = workspace(SOCKETS + "doc.addObject('Part::Feature', 'B').Shape = "
                                 "__import__('Part').makeBox(1, 1, 1, App.Vector(0, 0, -50))\n")
        try:
            r = check_json(fc(os.path.join(KIT, "check.py"), {
                "ATECH_CHECK_SCRIPT": os.path.join(ws, "model.py"), "ATECH_CHECK_PNG": "",
                "ATECH_CHECK_PATH": PROJECTS}))
        finally:
            shutil.rmtree(ws, ignore_errors=True)
        if "LibraryMissing" in (r.get("error") or "") or "No module named 'atech_ports'" in (
                r.get("error") or ""):
            self.skipTest("no Atech library here")
        line = [l for l in (r.get("stdout") or "").splitlines() if l.startswith("R164=")]
        self.assertTrue(line, r.get("error"))
        out = json.loads(line[-1][5:])
        # left edge: the module slides in along +X, its mouth faces -X and is
        # the module's -X extreme; right edge the mirror
        self.assertEqual(out["1"]["dir"], "-X")
        self.assertEqual(out["1"]["slide"], [1.0, 0.0, 0.0])
        self.assertAlmostEqual(out["1"]["mouth_x"][0], out["1"]["module_x"][0], places=3)
        self.assertEqual(out["11"]["dir"], "+X")
        self.assertAlmostEqual(out["11"]["mouth_x"][1], out["11"]["module_x"][1], places=3)
        self.assertIsNone(out["light"])            # nothing stands out: no socket

    def test_R164_usb_slot_over_the_cover_fails_along_the_socket(self):
        """D64 (c2a2): the slot cut over the module's cover, the end lid over
        the socket - FAIL naming -X; the slot in the lid in front of the
        socket passes."""
        req = "A closed nightlight with a window over the light and an opening for the USB-C plug"
        intent = {"board": "upright", "fitted_after": ["Lid"]}
        r, last = self._check(NIGHTLIGHT % {"window": "front", "usb": "cover"}, intent, req,
                              atech=True)
        usb = [f for f in r["face_open"] if f["module"] == "usbc"][0]
        self.assertEqual((usb["open"], atech_geom.normal_text(usb["normal"])), (0, "-X"))
        self.assertEqual(usb["blocked_by"], "Lid")
        self.assertIn("usbc_p5 (a USB-C socket) is sealed in: 0 of 169 rays from its "
                      "socket mouth (-X)", last)
        self.assertIn("not over the module's cover", last)
        r, last = self._check(NIGHTLIGHT % {"window": "front", "usb": "lid"}, intent, req,
                              atech=True)
        # R212: the fixture's Lid is a flat plate on the case end - it only
        # touches, which alone fails now; the socket is not a problem
        self.assertEqual(_not_joint(r), [], r["problems"])
        usb = [f for f in r["face_open"] if f["module"] == "usbc"][0]
        self.assertGreater(usb["open"], 0)
        # a request that names no USB: reported, not judged
        r, last = self._check(NIGHTLIGHT % {"window": "front", "usb": "cover"}, intent,
                              "A closed nightlight with a window over the light", atech=True)
        self.assertEqual(_not_joint(r), [], r["problems"])

    # ---------------------------------------------------------------- R168
    def test_R168_request_size_over_all_parts(self):
        """D65: intent.json split into per-part sizes; the user's 30 mm is
        measured over box + lid together (S52: naming the lid)."""
        req = "An electronics enclosure 80 x 50 x 30 mm outside with a separate lid"
        intent = {"parts": [{"name": "Enclosure_Box", "size_mm": [80, 50, 30]},
                            {"name": "Enclosure_Lid", "size_mm": [80, 50, 4]}]}
        r, last = self._check(BOX_AND_LID % {"box_h": 30, "lid_z": 30}, intent, req)
        self.assertTrue(last.startswith("CHECK FAIL: overall size from the request "
                                        "(\"80 x 50 x 30 mm\""), last)
        for s in ("the user asked for 30 mm, Atelier measured 34 mm (4 mm over)",
                  "the Z extent, 0.00 .. 34.00 mm", "Enclosure_Lid sets the top end (34.00)",
                  "Enclosure_Box the bottom end (0.00)", "Change that extent by 4 mm"):
            self.assertIn(s, last)
        # flush: the lid on a 26 mm box makes the 30 mm (a 'snap-fit' is no fit
        # of something else)
        r, last = self._check(BOX_AND_LID % {"box_h": 26, "lid_z": 26}, intent, req)
        # R212: the fixture's lid is a flat plate lying on the box - only
        # touching fails now; the size does not
        self.assertEqual(_not_joint(r), [], r["problems"])
        # the proud lid on the D65 numbers: box 28 + lid 4 = 32 vs 30
        r, last = self._check(BOX_AND_LID % {"box_h": 28, "lid_z": 28}, intent, req)
        self.assertIn("Atelier measured 32 mm (2 mm over) - the Z extent", last)
        # a top-level size_mm is compared (once), over all parts as before;
        # the request is the fallback when intent.json gives none (R151:
        # the user's turn may still correct the agent's own reading)
        r, last = self._check(BOX_AND_LID % {"box_h": 30, "lid_z": 30},
                              {"size_mm": [80, 50, 30]}, req)
        self.assertEqual(len(r["problems"]), 1, r["problems"])
        self.assertTrue(r["problems"][0].startswith("overall size: you intended 30 mm"))
        # no intent.json at all: the request's size still holds
        r, last = self._check(BOX_AND_LID % {"box_h": 30, "lid_z": 30}, None, req)
        self.assertIn("the user asked for 30 mm, Atelier measured 34 mm", last)

    # ---------------------------------------------------------------- R169
    def test_R169_container_open_probe(self):
        req = "a self-watering planter with an inner pot"
        r, last = self._check(POT % {"ring": False}, None, req)
        c = r["containers"][0]
        self.assertEqual((c["label"], c["open"], c["blocked_z"]), ("Inner_Pot", False, [56.0, 60.0]))
        self.assertIn("Inner_Pot is closed from above: rays straight down the middle of it "
                      "stop at z 56.00 .. 60.00 mm", last)
        r, last = self._check(POT % {"ring": True}, None, req)
        self.assertEqual(last, "CHECK PASS", r["problems"])
        self.assertTrue(r["containers"][0]["open"])
        self.assertAlmostEqual(r["containers"][0]["depth_mm"], 58.0, delta=0.05)
        r, last = self._check(MUG, None, "mug with handle")
        self.assertEqual(last, "CHECK PASS", r["problems"])
        self.assertTrue(r["containers"][0]["open"])
        # a wall planter lying on its side opens to the front (round-6
        # hex_planter): open from -Y, not a failure
        r, last = self._check("import Part, atech_cad as cad\nb = Part.makeBox(60, 40, 50)\n"
                              "doc.addObject('Part::Feature', 'Wall_Planter').Shape = "
                              "cad.shell(b, 3, cad.faces_at(b, '-Y'))\n", None, "wall planter")
        self.assertEqual(last, "CHECK PASS", r["problems"])
        self.assertEqual((r["containers"][0]["open"], r["containers"][0]["side"]), (True, "-Y"))
        # an ambiguous name ("box") closed on top is a warning, never a failure
        r, last = self._check("import Part\ndoc.addObject('Part::Feature', 'Box').Shape = "
                              "Part.makeBox(20, 20, 20)\n", None, "a box")
        self.assertEqual(last, "CHECK PASS")
        self.assertTrue(any("Box is closed from above" in w for w in r["warnings"]))
        TIMINGS["R169 container probe (s)"] = r.get("containers_seconds")

    # ---------------------------------------------------------------- R170
    def test_R170_slotted_channels_are_channels(self):
        req = "a desk cable clip with three 6 mm push-in cable channels"
        r, last = self._check(CLIP % {"slot": True}, {"holes": {"count": 3, "d_mm": 6}}, req)
        self.assertEqual(last, "CHECK PASS", r["problems"])
        note = [n for n in r["notes"] if n.startswith("holes:")]
        self.assertTrue(note, r["notes"])
        self.assertIn("0 closed hole(s) and 3 round channel(s) open along their length "
                      "(3 x diameter 6 mm (262.8 deg of arc))", note[0])
        # declared as slots: no note, no problem
        r, last = self._check(CLIP % {"slot": True}, {"slots": {"count": 3, "d_mm": 6}}, req)
        self.assertEqual(last, "CHECK PASS", r["problems"])
        self.assertFalse([n for n in r["notes"] if n.startswith("holes:")])
        # closed bores still count as holes, and are not slots
        r, last = self._check(CLIP % {"slot": False}, {"holes": {"count": 3, "d_mm": 6}}, req)
        self.assertEqual(last, "CHECK PASS", r["problems"])
        r, last = self._check(CLIP % {"slot": False}, {"slots": {"count": 3, "d_mm": 6}}, req)
        self.assertIn("slots: you intended 3 x diameter 6 mm round channel(s) open along "
                      "their length, Atelier found 0", last)
        # a miss names what was measured
        r, last = self._check(CLIP % {"slot": True}, {"holes": {"count": 3, "d_mm": 5}}, req)
        self.assertIn("round channels open along their length (slots), not holes: "
                      "3 x diameter 6 mm", last)

    # ---------------------------------------------------------------- R156
    def test_R156_intended_overlaps_never_excuse_the_users_object(self):
        ctx = tempfile.mkdtemp(prefix="atech-ctx-test-")
        seed = workspace("import Part\ndoc.addObject('Part::Feature', 'UserBox').Shape = "
                         "Part.makeBox(20, 20, 20)\n")
        try:
            fc(os.path.join(KIT, "check.py"), {"ATECH_CHECK_SCRIPT": os.path.join(seed, "model.py"),
                                              "ATECH_CHECK_PNG": "", "ATECH_CHECK_OUT": ctx})
            with open(os.path.join(ctx, "context.json"), "w") as fh:
                json.dump([{"name": "UserBox", "label": "UserBox", "role": "user",
                            "brep": os.path.join(ctx, "UserBox.brep")}], fh)
            env = {"ATECH_CHECK_CONTEXT": os.path.join(ctx, "context.json")}
            stand = ("import Part\nfrom FreeCAD import Vector\n"
                     "doc.addObject('Part::Feature', 'Stand').Shape = "
                     "Part.makeBox(30, 30, 10, Vector(-5, -5, %s))\n%s")
            for decl in ("INTENDED_OVERLAPS = [('Stand', 'UserBox')]\n",
                         "INTENDED_OVERLAPS = ['Stand']\n", "INTENDED_OVERLAPS = ['UserBox']\n"):
                with self.subTest(decl=decl):
                    r, last = self._check(stand % (5, decl), env=env)
                    self.assertIn("Stand and UserBox overlap by 4000.0 mm3", last)
                    self.assertIn("INTENDED_OVERLAPS does not excuse an overlap with the "
                                  "user's object", last)
                    self.assertTrue([h for h in r["overlaps"] if h.get("declared")])
            # a seated contact: 0.1 mm clearance, or touching line on line
            for z in ("20.1", "20"):
                with self.subTest(z=z):
                    r, last = self._check(stand % (z, "INTENDED_OVERLAPS = [('Stand', "
                                                     "'UserBox')]\n"), env=env)
                    self.assertEqual(last, "CHECK PASS", r["problems"])
            # the round-6 stand: its copy of the clock and the stand itself
            # inside the user's clock (benchmark: 29,809 and 122,218 mm3)
            r6 = os.path.join(ADDON, "..", "..", "docs", "verification", "eval",
                              "round_extra_6", "stand_for_existing_part", "model.py")
            seed_clock = os.path.join(ADDON, "tests", "eval", "seeds", "clock_enclosure.py")
            if os.path.isfile(r6) and os.path.isfile(seed_clock):
                ctx2 = tempfile.mkdtemp(prefix="atech-ctx-test-")
                try:
                    fc(os.path.join(KIT, "check.py"), {"ATECH_CHECK_SCRIPT": seed_clock,
                                                      "ATECH_CHECK_PNG": "",
                                                      "ATECH_CHECK_OUT": ctx2})
                    with open(os.path.join(ctx2, "context.json"), "w") as fh:
                        json.dump([{"name": "Clock_Enclosure", "label": "Clock_Enclosure",
                                    "role": "user",
                                    "brep": os.path.join(ctx2, "Clock_Enclosure.brep")}], fh)
                    with open(r6, encoding="utf-8") as fh:
                        code = fh.read()
                    r, last = self._check(code, env={"ATECH_CHECK_CONTEXT": os.path.join(
                        ctx2, "context.json")})
                    self.assertIn("Desk_Stand and Clock_Enclosure overlap by 29809.", last)
                    self.assertIn("Clock_Seated and Clock_Enclosure overlap by 122217.", last)
                finally:
                    shutil.rmtree(ctx2, ignore_errors=True)
        finally:
            shutil.rmtree(ctx, ignore_errors=True)
            shutil.rmtree(seed, ignore_errors=True)

    # ---------------------------------------------------------------- R154
    def test_R154_jar_lid_flute_breakthrough(self):
        r, last = self._check(JAR)
        m = r["walls"]["min"]
        self.assertLess(m["mm"], 0.8, m)
        self.assertEqual(last, "CHECK PASS")                 # a warning, never a failure
        self.assertTrue(any("Jar_Lid: a wall only" in w and "below 0.8 mm" in w
                            for w in r["warnings"]), r["warnings"])
        TIMINGS["R154 jar lid probe (s)"] = r["walls"]["seconds"]
        TIMINGS["R154 jar lid thinnest (mm)"] = m["mm"]


# R181 (D69, dogfood S5-4 c4a1b): the doorbell-remote case with two 3 mm
# light-pipe holes in its +Y (front) face, verbatim from the session's
# model.py; %(through)s is the agent's `True` or the kit's "wall".
C4A1B = r"""import Part
import atech_ports as ap
import atech_cad as cad
from FreeCAD import Vector, Placement, Rotation

W, C = 2.0, 1.0
EXT = 3.0
LP_D, LP_DX, LP_UP = 3.0, 12.0, 7.0
board = ap.board_object(doc)


def seat_all(lift):
    board.Placement = Placement(Vector(0, 0, lift), Rotation())
    return [ap.seat(doc, "button", 3), ap.seat(doc, "speaker", (9, 10))]


mods = seat_all(0)
low = cad.bound_of(board, *mods).ZMin
for m in mods:
    ap.remove(doc, m.AtechPorts[0])
mods = seat_all(W + C - low)
bb = cad.bound_of(board, *mods)
case = cad.rounded_box(bb.XLength + 2 * (W + C + EXT), bb.YLength + 2 * (W + C),
                       bb.ZLength + 2 * (W + C), 0,
                       at=(bb.XMin - W - C - EXT, bb.YMin - W - C, bb.ZMin - W - C))
case = cad.shell(case, W, cad.faces_at(case, "+X") + cad.faces_at(case, "-X"))
cb = case.BoundBox
bt = ap.bbox(mods[0])
for dx in (-LP_DX / 2, LP_DX / 2):
    case = cad.hole(case, (0.5 * (bt.XMin + bt.XMax) + dx, cb.YMax,
                           bt.ZMax + LP_UP), "-Y", LP_D, through=%(through)s)
doc.addObject("Part::Feature", "Case").Shape = case
import atech_geom, json
bs = [b for b in atech_geom.bores(case) if abs(b["d_mm"] - 3) < 0.01]
print("C4=" + json.dumps({"bores": len(bs), "openings": sum(b["walls"] for b in bs),
                          "y_max": cb.YMax}))
"""

# R181 without the Atech library: an open-top 60 x 40 x 30 box, 2 mm walls,
# two d=3 holes from its +Y face.
HOLLOW = r"""import Part, atech_cad as cad
b = Part.makeBox(60, 40, 30)
case = cad.shell(b, 2, cad.faces_at(b, "+Z"))
for x in (10, 22):
    case = cad.hole(case, (x, 40, 15), "-Y", 3, through=%(through)s)
doc.addObject("Part::Feature", "Case").Shape = case
"""

# R183 (D67 jar, dogfood S4-5 c5p2): a jar whose Ø47.6 mouth (2 mm neck
# wall) sits over its wider Ø56 body cavity - open top, floor 2 mm.
JAR_NECK = r"""import atech_cad as cad
jar = cad.revolve([(0, 0), (30, 0), (30, 40), (25.8, 40), (25.8, 50), (23.8, 50),
                   (23.8, 38), (28, 38), (28, 2), (0, 2)])
doc.addObject("Part::Feature", "Jar_Body").Shape = jar
"""

# R177: a desk stand whose wedge base reaches z = -12 (a 70 x 40 block
# standing on z = -12 .. 30)
BELOW = r"""import Part
from FreeCAD import Vector
doc.addObject("Part::Feature", "Stand").Shape = Part.makeBox(70, 40, 42, Vector(0, 0, -12))
"""

# S54: a rocket body with 4 fin-pin holes of d 4 declared but not cut
ROCKET = r"""import Part
doc.addObject("Part::Feature", "Rocket").Shape = Part.makeCylinder(15, 120)
"""


def _not_joint(r):
    """The problems other than R212's "only touches" lines."""
    return [p for p in r["problems"] if not (p.startswith("joint: ")
                                             and " only touches " in p)]


def _ast_const(path, name):
    """A module-level string constant, read with ast (no import)."""
    import ast
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    return None


class IntentRuleWording(unittest.TestCase):
    """R170 remainder: ./check and Studio word an intent miss the same way."""

    def test_R170_intent_rule_is_studios_fix_rule(self):
        kit = _ast_const(os.path.join(KIT, "atech_geom.py"), "INTENT_RULE")
        studio = _ast_const(os.path.join(ADDON, "acadagent", "build.py"), "INTENT_FIX_RULE")
        self.assertIsNotNone(studio)
        self.assertEqual(kit, studio)
        self.assertNotIn("until the build meets it", kit)
        self.assertIn("decide which side is wrong", kit)

    def test_S54_request_states(self):
        for req, want in (("L-bracket 60mm wide with 4 M5 holes", True),
                          ("spur gear m1.5 24 teeth 8mm bore", True),
                          ("a lid held by two M3 screws", True),
                          ("three round 6 mm cable channels", True),
                          ("rocket", False), ("toy car", False),
                          ("a screw-top jar with grip flutes", False)):
            self.assertEqual(atech_geom.request_states(req, "holes"), want, req)

    def test_R177_stands_on_desk(self):
        for req, want in (("It should hold the clock leaning back 15 degrees and stand "
                           "on a desk.", True),
                          ("phone stand with cable hole", True),
                          ("desk organizer with 3 pen slots", True),
                          ("headphone hook that clamps a 25mm desk", False),
                          ("A desk-edge cable clip", False), ("hex wall planter", False),
                          ("mug with handle", False)):
            self.assertEqual(atech_geom.stands_on_desk(req), want, req)


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class Round8Kit(unittest.TestCase):
    """R177 R181 R183 S54 S56 against the real kernel."""

    _check = Round7Kit._check

    # ---------------------------------------------------------------- R181
    def test_R181_hollow_case_wall_hole_vs_through(self):
        req = "a box with two 3 mm holes in the front face"
        intent = {"holes": {"count": 2, "d_mm": 3}}
        r, last = self._check(HOLLOW % {"through": "True"}, intent, req)
        self.assertEqual(last, "CHECK PASS")                 # a warning, not a failure
        w = [x for x in r["warnings"] if "goes through 2 walls" in x]
        self.assertEqual(len(w), 2, r["warnings"])
        self.assertIn("the -Y wall (y 0.00 .. 2.00) and the +Y wall (y 38.00 .. 40.00)", w[0])
        self.assertIn('through="wall"', w[0])
        r, last = self._check(HOLLOW % {"through": '"wall"'}, intent, req)
        self.assertEqual(last, "CHECK PASS", r["problems"])
        self.assertFalse(r.get("wall_crossings"), r.get("wall_crossings"))
        self.assertFalse([x for x in r["warnings"] if "walls" in x])
        # the request asks for it: no warning
        r, last = self._check(HOLLOW % {"through": "True"}, intent,
                              "a box with two 3 mm holes all the way through")
        self.assertFalse(r.get("wall_crossings"))

    def test_R181_c4a1b_light_pipe_holes(self):
        req = ("make it 10 mm narrower and add two 3 mm light-pipe holes in the front "
               "face above the button")
        intent = {"board": "upright", "holes": {"count": 2, "d_mm": 3.0}}
        out = {}
        for through in ("True", '"wall"'):
            r, last = self._check(C4A1B % {"through": through}, intent, req, atech=True)
            line = [l for l in (r.get("stdout") or "").splitlines() if l.startswith("C4=")]
            self.assertTrue(line, r.get("error"))
            out[through] = (json.loads(line[-1][3:]), r, last)
        c4, r, last = out["True"]
        self.assertEqual((c4["bores"], c4["openings"]), (2, 4))   # 2 holes, 4 wall openings
        w = [x for x in r["warnings"] if x.startswith("Case: the diameter 3 mm hole along Y")]
        self.assertEqual(len(w), 2, r["warnings"])
        self.assertIn("goes through 2 walls, the -Y wall (y ", w[0])     # the back wall
        c4, r, last = out['"wall"']
        self.assertEqual((c4["bores"], c4["openings"]), (2, 2))   # the front wall only
        self.assertFalse(r.get("wall_crossings"))
        self.assertFalse([x for x in r["warnings"] if "goes through" in x], r["warnings"])

    # ---------------------------------------------------------------- R183
    def test_R183_jar_mouth_is_not_a_hole(self):
        r, last = self._check(JAR_NECK, {"holes": {"count": 0}}, "a screw-top jar")
        self.assertEqual(last, "CHECK PASS", r["problems"])
        self.assertFalse([n for n in r["notes"] if n.startswith("holes:")], r["notes"])
        # no request at all (an older Studio): the mouth rule alone
        r, last = self._check(JAR_NECK, {"holes": {"count": 0}})
        self.assertEqual(last, "CHECK PASS", r["problems"])
        # a real hole in the jar's floor still counts
        r, last = self._check(JAR_NECK.replace(
            'doc.addObject', 'jar = cad.hole(jar, (0, 0, 0), "+Z", 5, through="wall")\n'
            'doc.addObject'), {"holes": {"count": 0}}, "a jar with a drain hole")
        self.assertIn("holes: you intended 0, Atelier found 1 (all closed hole diameters "
                      "found: [5.0]; blind cavities and container mouths, not counted: "
                      "[47.6, 56.0])", last)

    # ---------------------------------------------------------------- R177
    def test_R177_below_the_desk(self):
        req = "a stand for my clock that stands on a desk"
        r, last = self._check(BELOW, None, req)
        self.assertTrue(last.startswith("CHECK FAIL: Stand (z min -12.00 mm) below the desk"),
                        last)
        self.assertIn("raise the design by 12.00 mm in Z", last)
        self.assertEqual(r["desk"]["z_min_mm"], -12.0)
        for other in ("a headphone hook that clamps a 25 mm desk", "a block"):
            r, last = self._check(BELOW, None, other)
            self.assertEqual(last, "CHECK PASS", (other, r["problems"]))
        # the eval stands: r7 extra FAILs with its z min named; the phone
        # stands of r6 (backrest corner at z -0.10) and r7 pass
        ev = os.path.join(ADDON, "..", "..", "docs", "verification", "eval")
        seed_clock = os.path.join(ADDON, "tests", "eval", "seeds", "clock_enclosure.py")
        r7 = os.path.join(ev, "round_extra_7", "stand_for_existing_part", "model.py")
        if os.path.isfile(r7) and os.path.isfile(seed_clock):
            ctx = tempfile.mkdtemp(prefix="atech-ctx-test-")
            try:
                fc(os.path.join(KIT, "check.py"), {"ATECH_CHECK_SCRIPT": seed_clock,
                                                  "ATECH_CHECK_PNG": "",
                                                  "ATECH_CHECK_OUT": ctx})
                with open(os.path.join(ctx, "context.json"), "w") as fh:
                    json.dump([{"name": "Clock_Enclosure", "label": "Clock_Enclosure",
                                "role": "user",
                                "brep": os.path.join(ctx, "Clock_Enclosure.brep")}], fh)
                with open(r7, encoding="utf-8") as fh:
                    code = fh.read()
                r, last = self._check(code, None, (
                    "Design a desk stand for the existing Clock_Enclosure in this "
                    "document. It should hold the clock leaning back 15 degrees and "
                    "stand on a desk. Show the clock seated in the stand."),
                    env={"ATECH_CHECK_CONTEXT": os.path.join(ctx, "context.json")})
                self.assertTrue(last.startswith(
                    "CHECK FAIL: Clock_Desk_Stand (z min -18.99 mm) below the desk"), last)
            finally:
                shutil.rmtree(ctx, ignore_errors=True)
        for rnd in ("round_6", "round_7"):
            path = os.path.join(ev, rnd, "phone_stand", "model.py")
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as fh:
                code = fh.read()
            r, last = self._check(code, None, "phone stand with cable hole")
            self.assertEqual(last, "CHECK PASS", (rnd, r["problems"]))

    # ---------------------------------------------------------------- S54
    def test_S54_targets_the_request_never_states_are_notes(self):
        intent = {"size_mm": [30, 30, 140], "holes": {"count": 4, "d_mm": 4}}
        r, last = self._check(ROCKET, intent, "rocket")
        self.assertEqual(last, "CHECK PASS", r["problems"])
        notes = " ".join(r["notes"])
        self.assertIn("holes: you intended 4 x diameter 4 mm, Atelier found 0", notes)
        self.assertIn("the user's message names no holes", notes)
        self.assertIn("140 mm is not a size the user's message gives", notes)
        # the same misses on a request that states them stay PROBLEMS
        r, last = self._check(ROCKET, intent, "a 140 mm rocket with 4 fin-pin holes")
        self.assertIn("holes: you intended 4 x diameter 4 mm, Atelier found 0", last)
        self.assertIn("overall size: you intended 140 mm, Atelier measured 120 mm", last)
        self.assertIn(atech_geom.INTENT_RULE, r["warnings"])
        # count right, only a diameter the user never gave differs: a note
        plate = ("import Part\nfrom FreeCAD import Vector\nb = Part.makeBox(40, 20, 5)\n"
                 "for x in (10, 30):\n"
                 "    b = b.cut(Part.makeCylinder(1.25, 5, Vector(x, 10, 0)))\n"
                 "doc.addObject('Part::Feature', 'Lid').Shape = b\n")
        r, last = self._check(plate, {"holes": {"count": 2, "d_mm": 3.2}},
                              "a lid held by two M3 screws")
        self.assertEqual(last, "CHECK PASS", r["problems"])
        self.assertTrue([n for n in r["notes"] if "the count matches" in n], r["notes"])
        r, last = self._check(plate, {"holes": {"count": 2, "d_mm": 3.2}},
                              "a lid held by two M3 screws in 3.2 mm holes")
        self.assertIn("holes: you intended 2 x diameter 3.2 mm, Atelier found 0", last)

    # ---------------------------------------------------------------- S56
    def test_S56_library_limits_named(self):
        # the round-7 previews: hex_planter's plate r=6 on a 4 mm side, the
        # self-watering planter's slot cutter r = SLOT_W / 2
        r = run_check("import atech_cad as cad\n"
                      "doc.addObject('Part::Feature', 'P').Shape = "
                      "cad.rounded_box(100, 4, 150, 6.0, at=(-50, -30, 0))\n")
        self.assertFalse(r["ok"])
        err = r["error"].strip().splitlines()[-1]
        for s in ("r=6 must be < 2", "y = 4 mm", "use r=1.9 or less", "edges='y'"):
            self.assertIn(s, err)
        r, last = self._check("import atech_cad as cad\n"
                              "slot = cad.rounded_box(24, 5, 12, 5 / 2, at=(14, -2.5, 20))\n"
                              "doc.addObject('Part::Feature', 'Slot').Shape = slot\n")
        self.assertEqual(last, "CHECK PASS", r["problems"])
        self.assertEqual(r["objects"][0]["solids"], 1)


# R191 (D74): the S6-3 toothbrush holder - 80 x 30 x 20, four 14 mm
# notches 15 deep from the front (-Y), through top to bottom: vol 31200.0
TOOTHBRUSH = r"""import Part
from FreeCAD import Vector
b = Part.makeBox(80, 30, 20)
for x in (4.8, 23.6, 42.4, 61.2):
    b = b.cut(Part.makeBox(14, 15, 20, Vector(x, 0, 0)))
doc.addObject("Part::Feature", "Toothbrush_Holder").Shape = b.removeSplitter()
"""

# R192 (D73): the S6-2 phone cradle, 83 x 17 x 38: a 75 x 9 pocket z 8..38
# walled on all four sides, 2 mm lips at z 35..38 leave a 5 mm mouth
CRADLE = r"""import Part
from FreeCAD import Vector
def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, Vector(x0, y0, z0))
top = %(top)s
s = box(-41.5, 41.5, -8.5, 8.5, 0, top).cut(box(-37.5, 37.5, -4.5, 4.5, 8, top + 1))
if %(lips)s:
    s = s.fuse([box(-37.5, 37.5, 2.5, 4.5, top - 3, top),
                box(-37.5, 37.5, -4.5, -2.5, top - 3, top)])
if %(open_end)s:
    s = s.cut(box(37, 42, -4.5, 4.5, 8, top - 3))
if %(front)s:
    s = s.cut(box(-33.5, 33.5, -9, -4, 12, top + 1))
doc.addObject("Part::Feature", "Cradle").Shape = s.removeSplitter()
"""


def cradle(top=38, lips=True, open_end=False, front=False):
    return CRADLE % {"top": top, "lips": lips, "open_end": open_end, "front": front}


# R194: a keycap-like shell 18 -> 14 over 8 (a 14.04 deg taper) whose
# inside is offset 1.46 mm sideways: normal to the wall 1.46 cos(14.04 deg)
# = 1.4164; and a straight shell with 1.2 walls
KEYCAP = r"""import atech_cad as cad
import Part
from FreeCAD import Vector
out = cad.wedge(18, 18, 8, top_x=14, top_y=14)
inn = cad.wedge(18 - 2.92, 18 - 2.92, 6.8, top_x=14.6 - 2.92, top_y=14.6 - 2.92,
                at=(1.46, 1.46, 0))
doc.addObject("Part::Feature", "Keycap").Shape = cad.cut(out, inn)
s = Part.makeBox(18, 18, 8, Vector(30, 0, 0)).cut(Part.makeBox(15.6, 15.6, 6.8,
                                                                 Vector(31.2, 1.2, 0)))
doc.addObject("Part::Feature", "Straight").Shape = s
"""

# R189: a closed 80 x 70 x 40 box (2 mm walls) with a Ø50 speaker hole in
# its top face - a hole, not a container's mouth (50 / 70 = 0.71)
SPEAKER_BOX = r"""import Part, atech_cad as cad
from FreeCAD import Vector
b = Part.makeBox(80, 70, 40).cut(Part.makeBox(76, 66, 36, Vector(2, 2, 2)))
b = cad.hole(b, (40, 35, 40), "-Z", %(d)s, through="wall")
doc.addObject("Part::Feature", "Speaker_Box").Shape = b
"""


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class Round9Kit(unittest.TestCase):
    """R189 R191 R192 R194 S58 (S60's wedge is in fc_atech_cad.py) against
    the real kernel."""

    _check = Round7Kit._check

    # ---------------------------------------------------------------- R191
    def test_R191_rectangular_slots(self):
        req = ("a toothbrush holder 80 x 30 x 20 mm with four 14 mm slots 15 mm deep "
               "from the front")
        size = [80, 30, 20]
        r, last = self._check(TOOTHBRUSH, {"size_mm": size,
                                           "slots": {"count": 4, "w_mm": 14}}, req)
        self.assertEqual(r["objects"][0]["volume_mm3"], 31200.0)
        self.assertEqual(last, "CHECK PASS", r["problems"])
        self.assertFalse([n for n in r["notes"] if n.startswith("slots")], r["notes"])
        # with the depth: measured 15 from the front
        r, last = self._check(TOOTHBRUSH, {"size_mm": size, "slots": {
            "count": 4, "w_mm": 14, "depth_mm": 15}}, req)
        self.assertEqual(last, "CHECK PASS", r["problems"])
        self.assertFalse([n for n in r["notes"] if n.startswith("slots")], r["notes"])
        # a count or a depth it cannot confirm: a NOTE (CANNOT DETERMINE), never a miss
        for spec in ({"count": 5, "w_mm": 14}, {"count": 4, "w_mm": 14, "depth_mm": 10}):
            r, last = self._check(TOOTHBRUSH, {"size_mm": size, "slots": spec}, req)
            self.assertEqual(last, "CHECK PASS", (spec, r["problems"]))
            note = [n for n in r["notes"] if n.startswith("slots")]
            self.assertTrue(note and "CANNOT DETERMINE" in note[0], (spec, r["notes"]))
        self.assertIn("4 x 14 mm wide, 15 deep (x 4.8 .. 18.8, x 23.6 .. 37.6", note[0])
        # declared the D74 way (d_mm): a NOTE naming the notches, not a FAIL
        r, last = self._check(TOOTHBRUSH, {"size_mm": size,
                                           "slots": {"count": 4, "d_mm": 14}}, req)
        self.assertEqual(last, "CHECK PASS", r["problems"])
        note = [n for n in r["notes"] if n.startswith("slots")]
        self.assertTrue(note, r["notes"])
        self.assertIn("4 open rectangular notch(es) 14 mm wide", note[0])
        self.assertIn('"w_mm": 14', note[0])
        # the round-channel reading still fails a part with neither (R170)
        r, last = self._check("import Part\ndoc.addObject('Part::Feature', 'B').Shape = "
                              "Part.makeBox(80, 30, 20)\n",
                              {"slots": {"count": 4, "d_mm": 14}}, req)
        self.assertIn("slots: you intended 4 x diameter 14 mm round channel(s)", last)
        r, last = self._check(TOOTHBRUSH, {"slots": {"count": 4, "w_mm": "wide"}}, req)
        self.assertIn('slots must be {"count": n, "d_mm": d}', last)

    # ---------------------------------------------------------------- R192
    def test_R192_held_object_reaches_its_seat(self):
        req = "a tripod mount cradle for my 75 x 9 mm phone, 30 mm deep"
        intent = {"holds": {"size_mm": [75, 9, 30], "enters": "+Z"}}
        # D73 as built: lips to 5 mm over a pocket walled on all sides
        r, last = self._check(cradle(), intent, req)
        self.assertTrue(last.startswith("CHECK FAIL: Cradle: the held object (holds "
                                        "75 x 9 x 30 mm) cannot reach its seat"), last)
        self.assertIn("going in from +Z it stops at z 38.00: the narrowest mouth on the "
                      "way in is 75.00 x 5.00 mm (X x Y", last)
        self.assertIn("room for it behind that (z 8.00 .. 35.00)", last)
        self.assertEqual(r["holds"]["verdict"], "BLOCKED")
        # the lips over a pocket the phone fits under (z 8..38), ends closed:
        # flagged; one end open: it slides in from +X - passes, with a
        # WARNING that +Z (as declared) is blocked
        r, last = self._check(cradle(top=41), intent, req)
        self.assertIn("cannot reach its seat", last)
        r, last = self._check(cradle(top=41, open_end=True), intent, req)
        self.assertEqual(last, "CHECK PASS", r["problems"])
        self.assertEqual((r["holds"]["verdict"], r["holds"]["way"]["dir"]), ("PASS", "+X"))
        w = [x for x in r["warnings"] if "cannot go in from +Z as intent.json says" in x]
        self.assertTrue(w and "it does go in from +X" in w[0], r["warnings"])
        # declared the way it really goes in: no warning
        r, last = self._check(cradle(top=41, open_end=True),
                              {"holds": {"size_mm": [75, 9, 30], "enters": "+X"}}, req)
        self.assertEqual(last, "CHECK PASS", r["problems"])
        self.assertFalse([x for x in r["warnings"] if "held object" in x], r["warnings"])
        # front-only lips (a window in the front wall, no lips over the top):
        # it drops in from above through a 9 mm mouth
        r, last = self._check(cradle(lips=False, front=True), intent, req)
        self.assertEqual(last, "CHECK PASS", r["problems"])
        self.assertEqual(r["holds"]["way"]["dir"], "+Z")
        self.assertEqual(r["holds"]["way"]["mouth"][1:], [75.0, 9.0])
        # no holds in intent: no probe
        r, last = self._check(cradle(), {}, req)
        self.assertEqual(last, "CHECK PASS", r["problems"])
        self.assertNotIn("holds", r)
        r, last = self._check(cradle(), {"holds": {"size_mm": [75, 9]}}, req)
        self.assertIn("holds must be", last)
        # review: lips leaving an 8 mm mouth for the 9 mm phone slip past the
        # voxels (1 mm cells) - the exact mouth makes it a WARNING, never a
        # silent pass
        snap = cradle().replace("2.5, 4.5, top - 3", "4.0, 4.5, top - 3").replace(
            "-4.5, -2.5, top - 3", "-4.5, -4.0, top - 3")
        r, last = self._check(snap, intent, req)
        self.assertEqual(r["holds"]["verdict"], "TIGHT", r["holds"])
        w = [x for x in r["warnings"] if "mouth narrower than itself" in x]
        self.assertTrue(w and "75.00 x 8.00 mm" in w[0], r["warnings"])
        # review: a part too big for the voxel budget is never a silent pass
        r, last = self._check(
            "import Part\nfrom FreeCAD import Vector\ndoc.addObject('Part::Feature', "
            "'Tray').Shape = Part.makeBox(300, 300, 300).cut(Part.makeBox(280, 280, 300, "
            "Vector(10, 10, 10)))\n", {"holds": {"size_mm": [9, 9, 9], "enters": "+Z"}}, req)
        self.assertEqual(r["holds"]["verdict"], "CANNOT DETERMINE", r["holds"])
        self.assertTrue([n for n in r["notes"] if n.startswith("holds: CANNOT DETERMINE")],
                        r["notes"])

    # ---------------------------------------------------------------- S58
    def test_S58_solid_lid_plug_is_a_note(self):
        ev = os.path.join(ADDON, "..", "..", "docs", "verification", "eval")
        seen = {}
        for rnd in ("round_8", "round_7"):
            path = os.path.join(ev, rnd, "snap_box", "model.py")
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as fh:
                code = fh.read()
            r, last = self._check(code, {"size_mm": [80, 60, 40]},
                                  "a snap-fit box 80 x 60 x 40 mm")
            self.assertEqual(last, "CHECK PASS", (rnd, r["problems"]))
            seen[rnd] = [n for n in r["notes"] if "a solid plug" in n]
        if not seen:
            self.skipTest("no snap_box eval outputs in this checkout")
        if "round_8" in seen:
            self.assertEqual(len(seen["round_8"]), 1, seen)
            self.assertTrue(seen["round_8"][0].startswith(
                "Lid fills 93 % of its 80 x 60 x 11 mm box (49,088 of 52,800 mm3)"),
                seen["round_8"])
        if "round_7" in seen:
            self.assertEqual(seen["round_7"], [])             # 18,099 mm3: a ring lip
        # a flat plate lid is not a plug
        r, last = self._check("import Part\ndoc.addObject('Part::Feature', 'Lid').Shape = "
                              "Part.makeBox(80, 60, 3)\n")
        self.assertFalse([n for n in r["notes"] if "a solid plug" in n], r["notes"])

    # ---------------------------------------------------------------- R194
    def test_R194_side_walls_measured_normal_to_the_wall(self):
        r, last = self._check(KEYCAP, {"wall_mm": 1.2}, "a keycap with 1.2 mm walls")
        self.assertEqual(last, "CHECK PASS", r["problems"])
        side = {p["label"]: p.get("side") for p in r["walls"]["parts"]}
        want = 1.46 * math.cos(math.atan(2.0 / 8.0))              # 1.4164
        self.assertAlmostEqual(side["Keycap"]["mm"], want, delta=0.01)
        self.assertAlmostEqual(side["Keycap"]["lo"], want, delta=0.01)
        self.assertAlmostEqual(side["Keycap"]["hi"], want, delta=0.01)
        self.assertEqual((side["Straight"]["mm"], side["Straight"]["lo"],
                          side["Straight"]["hi"]), (1.2, 1.2, 1.2))
        notes = [n for n in r["notes"] if "side walls measure" in n]
        self.assertEqual(len(notes), 1, r["notes"])              # the keycap only
        self.assertTrue(notes[0].startswith("Keycap: its side walls measure 1.42 mm"),
                        notes)
        # review: the bars between a flat lid's vent slots (4.5 wide in a
        # 3 mm plate, eval r7 rpi4_case) are not side walls - no note
        vent = ("import Part\nfrom FreeCAD import Vector\ns = Part.makeBox(92, 63, 3)\n"
                "for i in range(6):\n"
                "    s = s.cut(Part.makeBox(26, 3.5, 5, Vector(14, 11.5 + 8 * i, -1)))\n"
                "doc.addObject('Part::Feature', 'Case_Lid').Shape = s\n")
        r, last = self._check(vent, {"wall_mm": 2.5}, "a lid with 2.5 mm walls")
        side = {p["label"]: p.get("side") for p in r["walls"]["parts"]}
        self.assertIsNone(side["Case_Lid"], side)
        self.assertFalse([n for n in r["notes"] if "side walls measure" in n], r["notes"])

    # ---------------------------------------------------------------- R189
    def test_R189_demoted_size_miss_reported_once(self):
        intent = {"size_mm": [30, 30, 140]}
        # the request gives 150: its own miss on Z is the one report
        r, last = self._check(ROCKET, intent, "a 30 x 30 x 150 mm rocket")
        self.assertIn("overall size from the request", last)
        self.assertNotIn("you intended 140", last)
        self.assertFalse([n for n in r["notes"] if "140 mm is not a size" in n], r["notes"])
        # the request's size is met on Z: the demoted note stays (once)
        r, last = self._check(ROCKET, intent, "a 30 x 30 x 120 mm rocket")
        self.assertEqual(last, "CHECK PASS", r["problems"])
        self.assertEqual(len([n for n in r["notes"] if "140 mm is not a size" in n]), 1,
                         r["notes"])

    def test_R189_hole_in_a_closed_box_face_is_a_hole(self):
        req = "a closed speaker box 80 x 70 x 40 mm with a speaker hole in the top"
        r, last = self._check(SPEAKER_BOX % {"d": 50}, {"holes": {"count": 1}}, req)
        self.assertEqual(last, "CHECK PASS", r["problems"])
        # the jar's neck (Ø47.6 in Ø51.6, 0.92) stays a mouth: R183's test
        # (test_R183_jar_mouth_is_not_a_hole) pins that side


# R202 (D77): the dogfood S6-5 c5n hinged box as the agent built it (model.py
# verbatim but for the pin axis's Y, PY): a 60 x 40 x 25 box, 2 mm walls,
# three Ø6 knuckles on one X axis at z 22. PY = W - KR puts the axis 3 mm
# inside the back face (y 37): the lid's rear strip hits the back wall.
HINGE = r"""import Part
from FreeCAD import Vector
import atech_cad as cad
L, W, H = 60.0, 40.0, 25.0
T = 2.0
LID_T = 2.0
RIM = H - LID_T
KR = 3.0
KW = 10.0
CL = 0.3
PIN_D = 2.0
PY, PZ = %(py)s, H - KR
X0 = L / 2.0 - 1.5 * KW
box = Part.makeBox(L, W, RIM)
box = cad.cut(box, Part.makeBox(L - 2 * T, W - 2 * T, RIM - T, Vector(T, T, T)))
box = cad.fuse_one(box,
                   Part.makeCylinder(KR, KW, Vector(X0, PY, PZ), Vector(1, 0, 0)),
                   Part.makeCylinder(KR, KW, Vector(X0 + 2 * KW, PY, PZ), Vector(1, 0, 0)))
box = cad.cut(box, Part.makeBox(KW, 2 * KR, KR + LID_T,
                                Vector(X0 + KW, PY - KR, PZ - KR)))
lid = Part.makeBox(L, W, LID_T, Vector(0, 0, RIM))
lid = cad.cut(lid, Part.makeBox(3 * KW + 2 * CL, 2 * KR + CL, LID_T,
                                Vector(X0 - CL, PY - KR - CL, RIM)))
lid = cad.fuse_one(lid,
                   Part.makeCylinder(KR, KW - 2 * CL, Vector(X0 + KW + CL, PY, PZ), Vector(1, 0, 0)),
                   Part.makeBox(KW - 2 * CL, KR + 4.0, LID_T,
                                Vector(X0 + KW + CL, PY - KR - 4.0, RIM)))
pin = Part.makeCylinder(PIN_D / 2.0, 3 * KW + 2 * T, Vector(X0 - T, PY, PZ), Vector(1, 0, 0))
box = cad.cut(box, pin)
lid = cad.cut(lid, pin)
doc.addObject("Part::Feature", "Box").Shape = box
doc.addObject("Part::Feature", "Lid").Shape = lid
"""


def hinge_motion(y, d=(-1, 0, 0), rng=(0, 90), part="Lid"):
    return {"motion": [{"part": part, "axis": [[0, y, 22], list(d)], "range_deg": list(rng)}]}


# R129: distance() on a light B-rep with a face of many loops (a plate with
# k round holes, made by a real cut - valid, the holes empty) against a lid
# lying ON it and one 0.3 mm above it
KIT_ROUND10 = r"""import time, json, Part
import atech_geom as g
V = App.Vector
out = {}
n = %(n)d
s = 94.0 / n
plate = Part.makeBox(100, 100, 10).cut(Part.makeCompound(
    [Part.makeCylinder(0.6, 12, V(4 + i * s, 4 + j * s, -1)) for i in range(n) for j in range(n)]))
out["loops"] = g.busiest_face_loops(plate)
out["valid"] = plate.isValid()
on = Part.makeBox(100, 100, 2, V(0, 0, 10))
above = Part.makeBox(100, 100, 2, V(0, 0, 10.3))
far = Part.makeBox(5, 5, 5, V(0, 0, 50))
for k, o in (("on", on), ("above", above), ("far", far)):
    t = time.time(); d = g.distance(plate, o, limit=2.0); out[k] = [d[0], d[1], time.time() - t]
    t = time.time(); out[k + "_touch"] = [g.touching(plate, o), time.time() - t]
items = [{"name": "P", "label": "P", "shape": plate}, {"name": "A", "label": "A", "shape": above}]
t = time.time(); out["floating"] = g.floating(items); out["floating_s"] = time.time() - t
t = time.time()
out["frag_on"] = g.fragments(Part.makeCompound([plate, Part.makeBox(1, 1, 1, V(50, 50, 10))]))
out["frag_apart"] = g.fragments(Part.makeCompound([plate, Part.makeBox(1, 1, 1, V(50, 50, 10.5))]))
out["frag_s"] = time.time() - t
print("ROUND10=" + json.dumps(out, default=str))
doc.addObject("Part::Feature", "B").Shape = Part.makeBox(1, 1, 1)
"""


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class Round10Kit(unittest.TestCase):
    """R202 S62 R129 against the real kernel (S61's snap_fit_pair is in
    fc_atech_cad.py)."""

    _check = Round7Kit._check

    # ---------------------------------------------------------------- R202
    def test_R202_hinge_axis_inside_the_back_face_fails_at_5_deg(self):
        r, last = self._check(HINGE % {"py": "W - KR"}, hinge_motion(37))
        self.assertTrue(last.startswith("CHECK FAIL: motion: Lid cannot turn 0 .. 90 deg "
                                        "about the axis through (0, 37, 22) along (-1, 0, "
                                        "0): it hits Box at 5 deg - 10."), last)
        row = r["motion"]["parts"][0]
        self.assertEqual((row["verdict"], row["blocked_at"], row["by"]), ("BLOCKED", 5.0, "Box"))
        self.assertAlmostEqual(row["volume_mm3"], 10.2, delta=0.1)   # D77: 10.2 mm3
        self.assertEqual(r["motion_problems"], [p for p in r["problems"]
                                                if p.startswith("motion")])
        self.assertIn("Move the axis ON or OUTSIDE", last)
        # sabotage: the same bad hinge with the sweep not asked for passes
        # every other check - the sweep is what catches it
        r, last = self._check(HINGE % {"py": "W - KR"}, {})
        self.assertEqual(last, "CHECK PASS", r["problems"])
        self.assertNotIn("motion", r)

    def test_R202_hinge_axis_on_or_outside_the_back_face_opens(self):
        for py, y in (("W", 40), ("W + 1.0", 41)):
            r, last = self._check(HINGE % {"py": py}, hinge_motion(y))
            self.assertEqual(last, "CHECK PASS", (py, r["problems"]))
            row = r["motion"]["parts"][0]
            self.assertEqual((row["verdict"], row["positions"], row["step_deg"]),
                             ("PASS", 19, 5.0), row)
        # declared the wrong way round: blocked at once, and the other way
        # is named as clear
        r, last = self._check(HINGE % {"py": "W"}, hinge_motion(40, d=(1, 0, 0)))
        self.assertIn("it hits Box at 5 deg", last)
        self.assertIn("Turned the other way (-5 deg) it is clear: if that is the way it "
                      "opens, reverse the axis direction in intent.json", last)
        # 12 deg is cut in equal steps of at most 5 (3 x 4 deg, 4 positions)
        r, last = self._check(HINGE % {"py": "W"}, hinge_motion(40, rng=(0, 12)))
        self.assertEqual(last, "CHECK PASS", r["problems"])
        row = r["motion"]["parts"][0]
        self.assertEqual((row["positions"], row["step_deg"]), (4, 4.0))

    def test_R202_declaration_errors(self):
        r, last = self._check(HINGE % {"py": "W"}, hinge_motion(40, part="Door"))
        self.assertEqual(last, "CHECK PASS", r["problems"])
        self.assertTrue([n for n in r["notes"] if n.startswith(
            "motion: no part labelled Door to sweep (the parts are: Box, Lid)")], r["notes"])
        out = tempfile.mkdtemp(prefix="atech-kit-out-")
        try:
            r, last = self._check(HINGE % {"py": "W"}, hinge_motion(40, part="Door"),
                                  env={"ATECH_CHECK_OUT": out})
        finally:
            shutil.rmtree(out, ignore_errors=True)
        self.assertIn("motion: no part labelled Door", last)   # Studio's build fails
        self.assertTrue(r["motion_problems"])
        r, last = self._check(HINGE % {"py": "W"},
                              {"motion": [{"part": "Lid", "axis": [0, 40, 22]}]})
        self.assertIn("intent.json motion must be [{", last)
        # NaN (json.load accepts it) is malformed, not a crash that turns the
        # sweep into a "could not run" warning
        r, last = self._check(HINGE % {"py": "W"}, {"motion": [
            {"part": "Lid", "axis": [[0, 40, 22], [-1, 0, 0]],
             "range_deg": [0, float("nan")]}]})
        self.assertIn("intent.json motion must be [{", last)
        self.assertFalse([w for w in r["warnings"] if "could not run" in w], r["warnings"])

    # ---------------------------------------------------------------- S62
    def test_S62_channel_wrap_line(self):
        ev = os.path.join(ADDON, "..", "..", "docs", "verification", "eval")
        got, got_text = {}, {}
        for rnd in ("round_9", "round_8"):
            path = os.path.join(ev, rnd, "cable_clip", "model.py")
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as fh:
                code = fh.read()
            ws = workspace(code)
            try:
                atech_geom.start_turn(ws, "cable clip for 6mm cable", fix=False)
                text = fc(os.path.join(KIT, "check.py"), {
                    "ATECH_CHECK_SCRIPT": os.path.join(ws, "model.py"), "ATECH_CHECK_PNG": ""})
            finally:
                shutil.rmtree(ws, ignore_errors=True)
            got[rnd], got_text[rnd] = check_json(text), text
        if not got:
            self.skipTest("no cable_clip eval outputs in this checkout")
        if "round_9" in got:
            r = got["round_9"]
            self.assertEqual([(c["d_mm"], c["wrap_deg"], c["axis"]) for c in r["channels"]],
                             [(6.4, 180.0, "X")])
            w = [x for x in r["warnings"] if "wraps 180 deg" in x]
            self.assertTrue(w and "under 240 deg, so a cable or rod pressed in is not "
                            "held" in w[0], r["warnings"])
            self.assertIn("\nCHANNEL Cable_Clip: a 6.4 mm round channel along X wraps "
                          "180 deg (x -5 .. 5)\n", got_text["round_9"])
        if "round_8" in got:
            r = got["round_8"]
            wraps = [c["wrap_deg"] for c in r["channels"]]
            self.assertEqual(len(wraps), 1, r["channels"])
            self.assertGreaterEqual(wraps[0], 240.0)            # 271.6: it holds
            self.assertFalse([x for x in r["warnings"] if "under 240 deg" in x])
            self.assertNotIn("wraps 180 deg", got_text["round_8"])
        # an obround slot's two round ends (180 deg each) are a slot, not two
        # channels; a fillet (90 deg) is not a channel
        slot = ("import Part, atech_cad as cad\nfrom FreeCAD import Vector\n"
                "p = Part.makeBox(40, 20, 4)\n"
                "s = cad.rounded_box(20, 6, 6, 2.99, at=(10, 7, -1))\n"
                "doc.addObject('Part::Feature', 'Clip_Plate').Shape = cad.cut(p, s)\n")
        r, last = self._check(slot, None, "a clip plate with a slot")
        self.assertEqual(last, "CHECK PASS", r["problems"])
        self.assertNotIn("channels", r)
        # a cable EXIT notch through a 2 mm wall wraps 180 deg: its line is
        # printed, but a notch is not a grip - no "not held" warning
        notch = ("import Part\nfrom FreeCAD import Vector as V\n"
                 "w = Part.makeBox(40, 2, 20)\n"
                 "n = Part.makeCylinder(3, 2, V(20, 0, 12), V(0, 1, 0)).fuse("
                 "Part.makeBox(6, 2, 10, V(17, 0, 12)))\n"
                 "doc.addObject('Part::Feature', 'Wall').Shape = w.cut(n).removeSplitter()\n")
        r, last = self._check(notch, None, "a wall with a cable exit notch")
        self.assertEqual([(c["d_mm"], c["wrap_deg"]) for c in r["channels"]], [(6.0, 180.0)])
        self.assertFalse([x for x in r["warnings"] if "under 240 deg" in x], r["warnings"])

    # ---------------------------------------------------------------- R129
    def test_R129_many_loop_plate_distance_is_fast(self):
        r = run_check(KIT_ROUND10 % {"n": 20})
        line = [l for l in (r.get("stdout") or "").splitlines() if l.startswith("ROUND10=")]
        self.assertTrue(line, r.get("error"))
        out = json.loads(line[-1][len("ROUND10="):])
        self.assertTrue(out["valid"])
        self.assertEqual(out["loops"], 20 * 20 + 1)
        # contact is exact (section): on = 0.0; apart = None (not measured)
        self.assertEqual(out["on"][:2], [0.0, True])
        self.assertEqual(out["above"][:2], [None, True])
        self.assertEqual(out["far"][:2], [None, True])
        self.assertEqual([out["on_touch"][0], out["above_touch"][0], out["far_touch"][0]],
                         [True, False, False])
        self.assertEqual(out["floating"], [])       # 0.3 apart: never accused
        # a 1 mm3 cube ON the plate touches it (one body); 0.5 mm above it
        # is a stray fragment
        self.assertIsNone(out["frag_on"])
        self.assertIsNotNone(out["frag_apart"])
        self.assertLess(out["frag_s"], 2.0)
        for k in ("on", "above", "far"):
            TIMINGS["R129 distance %s, 400-hole plate (s)" % k] = round(out[k][2], 3)
            self.assertLess(out[k][2], 1.0, (k, out[k]))      # distToShape: 27 s
            self.assertLess(out[k + "_touch"][1], 1.0, (k, out[k + "_touch"]))
        self.assertLess(out["floating_s"], 1.0)


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class Sandbox(unittest.TestCase):
    def test_build_and_import_roundtrip(self):
        with open(os.path.join(KIT, "examples", "enclosure.py"), encoding="utf-8") as fh:
            ws = workspace(fh.read())
        try:
            t0 = time.time()
            r = sandbox.run(ws, timeout=60)
            TIMINGS["sandbox enclosure (%s)" % r.isolation] = round(time.time() - t0, 2)
            self.assertTrue(r.ok, r.error)
            self.assertEqual(sorted(o["label"] for o in r.objects), ["Enclosure", "Lid"])
            for o in r.objects:
                self.assertTrue(os.path.getsize(o["brep"]) > 0)
                self.assertTrue(o["brep"].startswith(os.path.join(ws, sandbox.OUT_SUBDIR)))
            # Not in the top level: build.snapshot must not see sandbox output.
            self.assertEqual(sorted(os.listdir(ws)), [sandbox.OUT_SUBDIR, "model.py"])
            # Import the BREPs back in freecadcmd via sandbox.import_result.
            probe = os.path.join(ws, "probe.py")
            with open(probe, "w", encoding="utf-8") as fh:
                fh.write(
                    "import json, os, sys\n"
                    "sys.path.insert(0, %r)\n"
                    "import FreeCAD\n"
                    "from acadagent import sandbox\n"
                    "rep = json.load(open(os.path.join(%r, 'result.json')))\n"
                    "res = sandbox.Result(True, objects=rep['objects'])\n"
                    "doc = FreeCAD.newDocument('Imp')\n"
                    "made = sandbox.import_result(doc, res)\n"
                    "print('IMPORTED=' + json.dumps({o.Label: [round(o.Shape.Volume, 2),"
                    " len(o.Shape.Solids), o.Shape.isValid()] for o in made}))\n"
                    "sys.stdout.flush(); os._exit(0)\n" % (ADDON, r.out_dir))
            out = fc(probe)
            line = [x for x in out.splitlines() if x.startswith("IMPORTED=")]
            self.assertTrue(line, out[-2000:])
            got = json.loads(line[0][len("IMPORTED="):])
            for o in r.objects:
                self.assertEqual(got[o["label"]][1:], [1, True])
                self.assertAlmostEqual(got[o["label"]][0], o["volume_mm3"], places=1)
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_failure_reports_line(self):
        ws = workspace("import Part\n\nPart.makeBox(1, 1, 0)\n")
        try:
            r = sandbox.run(ws, timeout=30)
            self.assertFalse(r.ok)
            self.assertEqual(r.report["error_lines"][-1]["line"], 3)
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_hard_hang_is_killed_and_caller_keeps_ticking(self):
        # The script disables check.py's own alarm, so only the parent's
        # kill can stop it - the worst case.
        ws = workspace("import signal\nsignal.signal(signal.SIGALRM, signal.SIG_IGN)\n"
                       "while True:\n    pass\n")
        try:
            job = sandbox.Job(ws, timeout=3).start()
            pid = job.proc.pid
            worst, last = 0.0, time.time()
            while job.poll() is None:            # what a QTimer does in Studio
                time.sleep(0.01)
                now = time.time()
                worst, last = max(worst, now - last), now
            r = job.result
            TIMINGS["hang: killed after"] = r.seconds
            TIMINGS["hang: worst caller tick gap (s)"] = round(worst, 3)
            self.assertFalse(r.ok)
            self.assertTrue(r.timed_out, r.error)
            self.assertLess(r.seconds, 3 + 5 + 3)
            self.assertLess(worst, 0.25, "caller loop blocked %.3fs" % worst)
            time.sleep(0.3)
            with self.assertRaises(ProcessLookupError):
                os.killpg(pid, 0)                # the whole group is gone
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_scratch_home_and_no_network(self):
        real_home = os.path.realpath(os.path.expanduser("~"))
        # Under bwrap the real home is a tmpfs: only the folders bound back in
        # (the FreeCAD install, the kit) exist there. Everything else in it -
        # dotfiles, ~/.ssh - must be invisible by its absolute path too.
        bound = [os.path.realpath(p) for p in (FC, KIT, tempfile.gettempdir())]
        hidden = []
        if sandbox.isolation() == "bwrap":
            for e in sorted(os.listdir(real_home)):
                p = os.path.join(real_home, e)
                if not any(b == p or b.startswith(p + os.sep) for b in bound):
                    hidden.append(p)
            self.assertTrue(hidden)
        code = (
            "import os, socket, Part\n"
            "leaks = []\n"
            "if os.path.realpath(os.path.expanduser('~')) == %r: leaks.append('HOME')\n"
            "if os.path.exists(os.path.expanduser('~/.ssh')): leaks.append('~/.ssh')\n"
            "try:\n"
            "    socket.create_connection(('1.1.1.1', 53), timeout=3).close()\n"
            "    leaks.append('network')\n"
            "except OSError:\n"
            "    pass\n"
            "for p in %r:\n"
            "    if os.path.exists(p): leaks.append(p)\n"
            "if leaks: raise RuntimeError('LEAK ' + ','.join(leaks))\n"
            "doc.addObject('Part::Feature', 'B').Shape = Part.makeBox(1, 1, 1)\n"
            % (real_home, hidden))
        ws = workspace(code)
        try:
            r = sandbox.run(ws, timeout=30)
            if sandbox.isolation() == "none":
                self.skipTest("no bwrap/unshare on this machine")
            self.assertTrue(r.ok, r.error)
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_host_network_reachable_control(self):
        # Control for the test above: outside the sandbox the same probe
        # connects, so "no network" is the sandbox's doing (skip if offline).
        try:
            socket.create_connection(("1.1.1.1", 53), timeout=3).close()
        except OSError:
            self.skipTest("host is offline; network isolation not provable here")

    def test_missing_script(self):
        ws = tempfile.mkdtemp(prefix="atech-sbx-test-")
        try:
            r = sandbox.run(ws)
            self.assertFalse(r.ok)
            self.assertIn("no model.py", r.error)
        finally:
            shutil.rmtree(ws, ignore_errors=True)


def tearDownModule():
    if TIMINGS:
        print("\nAGENT_KIT_TIMINGS=" + json.dumps(TIMINGS))


if __name__ == "__main__":
    unittest.main(verbosity=2)
