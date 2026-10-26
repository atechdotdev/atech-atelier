"""R440-R444 (WS4): archetype, fastening, holder, exact-overlap and pilot gates.
R600: the archetype "gate" is a NOTE line only (never a WARNING or a
PROBLEM): the user, 2026-10-26, "it overfits too much to be a box now".

    cd addon/AcadAgent/tests && python3 -m unittest test_check_gates_r280

Round 1 shipped a sealed car, a blank-faced robot, a slab speaker and a
postage-stamp handheld under CHECK PASS or near it; housings sat on each
other with nothing joining them, cabled modules hung on their ribbons, a
sampled overlap flipped PASS / FAIL between runs and cad.screw_boss drilled
a pilot the thread could not bite. Each gate below has a passing fixture
and the same fixture broken (SABOTAGE), which must fail - or, for the
exact overlap, a tessellation-only overlap that must NOT fail.

  R440  atech_geom.ARCHETYPE_GATES / archetype_problems (quality mode)
  R441  atech_geom.fastening: housing parts that meet must be joined
  R442  atech_geom.cable_holders: a cabled module held on two sides
  R443  atech_geom.overlaps: a sampled hit under 5 % confirmed exactly
  R444  cad.screw_boss drills 0.85 d; the pilot gate is a PROBLEM; the
        screw's overlap with the pilot it bites in is the thread (a NOTE)

Plain-python cases need nothing; FreeCAD-backed ones skip without freecadcmd
(ATECH_FREECADCMD), library-backed ones without the Atech library; the
product examples are built with their own request (ExamplesWithRequests:
every seed must CHECK PASS under these gates - WS1 / WS2 fix the example,
never the threshold).
"""
import ast
import json
import os
import re
import sys
import tempfile
import shutil
import subprocess
import unittest
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import test_agent_kit as tak  # noqa: E402
import test_check_gates_r270 as r270  # noqa: E402

FC, KIT, PROJECTS = tak.FC, tak.KIT, tak.PROJECTS
if KIT not in sys.path:
    sys.path.insert(0, KIT)

import atech_geom  # noqa: E402  (plain python: no FreeCAD at import)

HAVE_LIB = os.path.isfile(os.path.join(PROJECTS, "atech_ports.py"))
ARTIFACTS = os.environ.get("ATECH_ARTIFACTS") or os.path.normpath(
    os.path.join(tak.ADDON, "..", "..", "models"))
LIB_ENV = {"ATECH_ARTIFACTS": ARTIFACTS}
fc_json, run_check, last = r270.fc_json, r270.run_check, r270.last


# ------------------------------------------------------- plain python
class ArchetypeTable(unittest.TestCase):
    """R440: the gate table keys on build.ARCHETYPES' own categories."""

    def test_same_labels_and_words_as_build(self):
        sys.path.insert(0, tak.ADDON)
        try:
            from acadagent import build
        except Exception as exc:                        # noqa: BLE001
            self.skipTest("acadagent.build not importable: %s" % exc)
        want = [(lab, tuple(words)) for lab, words, _rule in build.ARCHETYPES]
        got = [(lab, tuple(words)) for lab, words, _gate in atech_geom.ARCHETYPE_GATES]
        self.assertEqual(got, want)

    def test_request_words_pick_the_first_row(self):
        of = atech_geom.archetype_of
        self.assertEqual(of("a toy car"), ("vehicle", "vehicle"))
        self.assertEqual(of("a robot car with lights"), ("vehicle", "vehicle"))
        self.assertEqual(of("a little desk robot"), ("robot or character", "robot"))
        self.assertEqual(of("an alarm clock"), ("clock", "clock"))
        self.assertEqual(of("a desk fan"), ("fan", "fan"))
        self.assertEqual(of("a handheld game console"), ("handheld", "handheld"))
        self.assertEqual(of("a weather station"), ("weather station", None))
        self.assertEqual(of("a bedside lamp"), ("lamp", "lamp"))
        self.assertEqual(of("a box for screws"), (None, None))
        self.assertEqual(of("a cartridge"), (None, None))       # "car" in a word

    def test_fast_mode_never_fails(self):
        r = atech_geom.archetype_problems([], [], "a box")
        self.assertEqual((r["archetype"], r["problems"]), (None, []))
        r = atech_geom.archetype_problems([], [], "a weather station")
        self.assertEqual(r["problems"], [])
        self.assertIn("no measured gate", r["notes"][0])

    def test_r600_check_never_warns_on_the_archetype(self):
        """R600: check.py adds the archetype's NOTE lines only - never its
        warnings or problems (read from source: no FreeCAD here)."""
        src = open(os.path.join(KIT, "check.py"), encoding="utf-8").read()
        body = src[src.index("def _archetype("):src.index("def _fastening(")]
        self.assertNotIn('res.setdefault("warnings", []).extend', body)
        self.assertNotIn('res["warnings"]', body)
        self.assertIn('res.setdefault("notes", []).extend(r["notes"])', body)


# -------------------------------------------- FreeCAD fixture prelude
PRE = r'''
import json, math, Part, FreeCAD, Mesh, atech_geom as G
from FreeCAD import Vector as V, Placement, Rotation
def axes(o):
    r = o.Placement.Rotation
    return [[round(c, 6) for c in r.multVec(V(*e))] for e in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
def mod(o):
    return {"label": o.Label, "name": o.Name, "mesh": o.Mesh, "axes": axes(o),
            "module": str(getattr(o, "AtechModule", "") or "") or None,
            "role": getattr(o, "AtechRole", None)}
def part(label, shape, rgb=None, tr=None, cable=False):
    view = {}
    if rgb is not None:
        view["ShapeColor"] = list(rgb)
    if tr is not None:
        view["Transparency"] = tr
    return {"label": label, "shape": shape, "view": view, "cable": cable}
def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))
def cyl(r, at, h, d=(0, 0, 1)):
    return Part.makeCylinder(r, h, V(*at), V(*d))
BLUE, WHITE, BLACK, SMOKE = (0.12, 0.42, 0.86), (0.93, 0.93, 0.91), (0.1, 0.1, 0.11), (0.2, 0.22, 0.25)
def gate(parts, mods, req):
    r = G.archetype_problems(parts, mods, req, mode="quality")
    # R500: a miss is never a PROBLEM; R600: never a WARNING either - one
    # NOTE line. "problems" here are the gate's misses, "hard" what would
    # block and "warn" what would warn - both always empty
    return {"problems": r["misses"], "hard": r["problems"], "warn": r["warnings"],
            "notes": r["notes"], "facts": r["facts"]}
out = {}
'''


def fc(code, timeout=900):
    return fc_json(PRE + code + '\nprint("R270JSON=" + json.dumps(out, default=str))\n',
                   env=LIB_ENV, timeout=timeout)


# ------------------------------------------------- (R440) archetypes
HANDHELD = r'''
import atech_ports as ap
doc = FreeCAD.newDocument("hh")
board = ap.board_object(doc)
board.Placement = Placement(V(), Rotation(V(1, 0, 0), 90))      # flat: modules up (+Z)
scr = ap.seat(doc, "screen", (11, 12))
doc.recompute()
bb, sb = board.Mesh.BoundBox, scr.Mesh.BoundBox
mods = [mod(board), mod(scr)]
X0, X1, Y0, Y1 = bb.XMin - 45, bb.XMax + 45, bb.YMin - 12, bb.YMax + 12
ZT = sb.ZMax + 0.5
def build(gw, gh, z0):
    body = box(X0, X1, Y0, Y1, z0, ZT).cut(
        box(sb.XMin - 0.5, sb.XMax + 0.5, sb.YMin - 0.5, sb.YMax + 0.5, sb.ZMin - 0.5, ZT + 1))
    cx, cy = sb.Center.x, sb.Center.y
    glass = box(cx - gw / 2, cx + gw / 2, cy - gh / 2, cy + gh / 2, ZT, ZT + 1.0)
    return [part("Front", body, BLUE), part("Cover_Glass", glass, SMOKE, 50)]
W, H = X1 - X0, Y1 - Y0
out["big"] = gate(build(0.75 * W, 0.8 * H, bb.ZMin - 3), mods, "a handheld game console")
out["stamp"] = gate(build(sb.XLength + 1, sb.YLength + 1, bb.ZMin - 3), mods,
                    "a handheld game console")
out["brick"] = gate(build(0.75 * W, 0.8 * H, ZT - 40), mods, "a handheld game console")
out["fast"] = G.archetype_problems(build(sb.XLength + 1, sb.YLength + 1, bb.ZMin - 3), mods,
                                   "a handheld game console", mode="fast")["problems"]
'''

ROBOT = r'''
import atech_ports as ap
doc = FreeCAD.newDocument("rb")
board = ap.board_object(doc)
doc.recompute()
def build(zs, visor):
    for o in list(doc.Objects):
        if o.Name != board.Name:
            doc.removeObject(o.Name)
    pl = ap.module_placement("screen", (300, -24, zs), face="-Y")
    scr, _c = ap.cable(doc, "screen", (11, 12), pl)
    doc.recompute()
    sb = scr.Mesh.BoundBox
    body = box(255, 345, -30, 30, 0, 160).cut(
        box(sb.XMin - 1, sb.XMax + 1, sb.YMin - 1, sb.YMax + 1, sb.ZMin - 1, sb.ZMax + 1))
    cx, cz = sb.Center.x, sb.Center.z
    parts = [part("Torso", body, WHITE)]
    if visor:
        body = body.cut(box(cx - 30, cx + 30, -31, sb.YMin, cz - 18, cz + 18))
        parts = [part("Torso", body, WHITE),
                 part("Visor", box(cx - 30, cx + 30, -30.5, -29.5, cz - 18, cz + 18), SMOKE, 50)]
    else:
        body = body.cut(box(cx - 10, cx + 10, -31, sb.YMin, cz - 6, cz + 6))
        parts = [part("Torso", body, WHITE)]
    return parts, [mod(board), mod(scr)]
p, m = build(125, True)
out["face"] = gate(p, m, "a little desk robot")
p, m = build(125, False)
out["blank"] = gate(p, m, "a little desk robot")
p, m = build(40, True)
out["low"] = gate(p, m, "a little desk robot")
'''

SPEAKER = r'''
def build(H, n_holes):
    shell = cyl(50, (0, 0, 0), H).cut(cyl(48, (0, 0, 2), H - 4))
    cut = [cyl(1.5, (x * 4.5, y * 4.5, H - 3), 4) for x in range(-9, 10) for y in range(-9, 10)
           if (x * 4.5) ** 2 + (y * 4.5) ** 2 < 40 ** 2][:n_holes]
    return [part("Shell", shell.cut(Part.makeCompound(cut)), WHITE)]
out["grille"] = gate(build(60, 999), [], "a smart speaker")
out["pinholes"] = gate(build(60, 12), [], "a smart speaker")
out["slab"] = gate(build(18, 999), [], "a smart speaker")
'''

VEHICLE = r'''
def build(L, W, ys, label="Wheel"):
    body = box(0, W, 0, L, 10, 40)
    ps = [part("Body", body, BLUE)]
    for i, y in enumerate(ys):
        for x, side in ((-6, "L"), (W, "R")):
            ps.append(part("%s_%d%s" % (label, i, side), cyl(10, (x, y, 10), 6, (1, 0, 0)), BLACK))
    return ps
out["car"] = gate(build(200, 80, (25, 175)), [], "a toy car")
out["box"] = gate(build(110, 90, (20, 90)), [], "a toy car")
out["stance"] = gate(build(200, 80, (80, 120)), [], "a toy car")
out["nowheels"] = gate(build(200, 80, (25, 175), label="Disc"), [], "a toy car")
out["boat"] = gate([part("Hull", box(0, 60, 0, 200, 0, 30), BLUE)], [], "a toy boat")
'''

LAMP = r'''
def build(col_h, globe_z, foot_r=40):
    foot = cyl(foot_r, (0, 0, 0), 10)
    col = cyl(15, (0, 0, 10), col_h)
    globe = Part.makeSphere(30, V(0, 0, globe_z))
    return [part("Base", foot, BLACK), part("Column", col, WHITE),
            part("Globe", globe, WHITE, 40)]
out["lamp"] = gate(build(200, 240), [], "a bedside lamp")
out["jar"] = gate(build(40, 80, foot_r=60), [], "a bedside lamp")
out["low_light"] = gate(build(200, 40), [], "a bedside lamp")
'''

CLOCK = r'''
def build(dw, dh):
    body = box(-60, 60, -20, 20, 0, 80)
    dial = box(-dw / 2, dw / 2, -21, -20, 40 - dh / 2, 40 + dh / 2)
    return [part("Case", body, WHITE), part("Dial", dial, BLACK)]
out["clock"] = gate(build(100, 70), [], "an alarm clock")
out["label"] = gate(build(30, 20), [], "an alarm clock")
'''

FAN = r'''
def build(r_open):
    housing = box(-75, 75, -20, 20, 0, 150).cut(cyl(r_open, (0, -21, 75), 36, (0, 1, 0)))
    blades = cyl(r_open - 3, (0, 0, 75), 2, (0, 1, 0))           # 3 mm tip clearance
    return [part("Housing", housing, WHITE), part("Fan_Blades", blades, BLUE)]
out["fan"] = gate(build(65), [], "a desk fan")
out["vents"] = gate(build(30), [], "a desk fan")
# R504: a desk fan's foot stands 40 mm forward of the guard - the guard's
# front is measured over the rotor, so a SOLID guard is still closed
foot = part("Foot", box(-60, 60, -60, 20, -12, 0), WHITE)
closed = box(-75, 75, -21, -20, 0, 150)
out["fan_foot"] = gate(build(65) + [foot], [], "a desk fan")
out["closed_foot"] = gate(build(65) + [foot, part("Guard_Front", closed, WHITE)], [], "a desk fan")
# R440 (WS1's bug): a CABLED dc_motor whose shaft faces -Y while its +u
# (module_placement's face) is +Z - the library names the shaft's proud
# face "out"; the gate must look along the shaft, not down from +u
import atech_ports as ap
doc = FreeCAD.newDocument("fan")
board = ap.board_object(doc)
motor, _c = ap.cable(doc, "dc_motor", 1, ap.module_placement("dc_motor", (0, 10, 75), face="+Z",
                                                             cable="+Y"))
doc.recompute()
mods = [mod(board), mod(motor)]
out["motor_dir"] = [round(float(x), 3) for x in G._module_dir(mods[1], ("shaft", "out"))]
# R500: "shaft" alone (the old ask) still finds it through proud_mm; with no
# face word the +u comes back - the wrong way for the blades (SABOTAGE)
out["motor_dir_shaft"] = [round(float(x), 3) for x in G._module_dir(mods[1], "shaft")]
out["motor_dir_up"] = [round(float(x), 3) for x in G._module_dir(mods[1])]
# R500: the old word alone ("shaft", which the library never names) falls
# back to the proud face; no word at all is +u (SABOTAGE: the wrong view)
out["motor_dir_shaft"] = [round(float(x), 3) for x in G._module_dir(mods[1], ("shaft",))]
out["motor_dir_up"] = [round(float(x), 3) for x in G._module_dir(mods[1])]
out["fan_motor"] = gate(build(65), mods, "a desk fan")
out["vents_motor"] = gate(build(30), mods, "a desk fan")
'''


@unittest.skipIf(FC is None or not HAVE_LIB, "freecadcmd or the Atech library not found")
class ArchetypeGates(unittest.TestCase):
    """R440: each measured archetype gate - the passing fixture, then the
    same fixture broken (SABOTAGE)."""

    def ok(self, r):
        self.assertEqual(r["problems"], [], r)
        self.assertEqual(r["hard"], [], r)
        self.assertEqual(r["warn"], [], r)
        self.assertTrue(r["notes"] and r["notes"][0].startswith("ARCHETYPE "), r)

    def bad(self, r, *needles):
        self.assertTrue(r["problems"], r)
        self.assertEqual(r["hard"], [], "R500: an archetype miss must never be a PROBLEM")
        self.assertEqual(r["warn"], [], "R600: an archetype miss must never be a WARNING")
        joined = " | ".join(r["problems"])
        self.assertTrue(joined.startswith("ARCHETYPE "), joined)
        # R600: the miss is one NOTE line, a design note
        self.assertEqual(len(r["notes"]), 1, r["notes"])
        self.assertTrue(r["notes"][0].endswith("(a design note, not a gate)"), r["notes"])
        for n in needles:
            self.assertIn(n, joined)
            self.assertIn(n, r["notes"][0])

    def test_handheld_screen_region_and_grip_thickness(self):
        r = fc(HANDHELD)
        self.ok(r["big"])
        self.assertGreaterEqual(r["big"]["facts"]["screen_share"], 0.30)
        # SABOTAGE: the bezel / glass shrunk to the screen - a postage stamp
        self.bad(r["stamp"], "postage stamp", "at least")
        self.assertLess(r["stamp"]["facts"]["screen_share"], 0.30)
        # SABOTAGE: a 40 mm brick
        self.bad(r["brick"], "thick where held")
        self.assertEqual(r["fast"], [])                     # fast mode: no PROBLEM

    def test_robot_face_window(self):
        r = fc(ROBOT)
        self.ok(r["face"])
        self.assertGreaterEqual(r["face"]["facts"]["window_mm"], 35)
        self.bad(r["blank"], "wide", "blank-faced")         # SABOTAGE: 20 mm window
        self.bad(r["low"], "up the robot")                  # SABOTAGE: screen in the belly

    def test_speaker_height_and_grille(self):
        r = fc(SPEAKER)
        self.ok(r["grille"])
        self.assertGreaterEqual(r["grille"]["facts"]["grille_top_share"], 0.15)
        self.bad(r["pinholes"], "grille's open area")       # SABOTAGE: 12 holes
        self.bad(r["slab"], "slab")                         # SABOTAGE: 18 mm tall

    def test_vehicle_length_and_stance(self):
        r = fc(VEHICLE)
        self.ok(r["car"])
        self.bad(r["box"], "box on wheels")
        self.bad(r["stance"], "wheels sit at")
        self.bad(r["nowheels"], "no wheel or track")
        self.ok(r["boat"])

    def test_lamp_clock_fan(self):
        r = fc(LAMP)
        self.ok(r["lamp"])
        self.bad(r["jar"], "jar")
        self.bad(r["low_light"], "no light in the top third")
        r = fc(CLOCK)
        self.ok(r["clock"])
        self.bad(r["label"], "the dial is")
        r = fc(FAN)
        self.ok(r["fan"])
        self.bad(r["vents"], "guard opening")
        # a cabled motor facing -Y: measured along its shaft
        self.assertEqual(r["motor_dir"], [0.0, -1.0, 0.0])
        self.assertEqual(r["motor_dir_shaft"], [0.0, -1.0, 0.0])         # R500
        self.assertNotEqual(r["motor_dir_up"], [0.0, -1.0, 0.0])         # R500 SABOTAGE
        self.assertEqual(r["motor_dir_shaft"], [0.0, -1.0, 0.0])
        self.assertNotEqual(r["motor_dir_up"], [0.0, -1.0, 0.0])        # SABOTAGE
        # R504: the foot in front does not open a solid guard
        self.ok(r["fan_foot"])
        self.bad(r["closed_foot"], "guard opening")
        self.assertLess(r["closed_foot"]["facts"]["guard_share"], 0.2)
        self.ok(r["fan_motor"])
        self.assertGreaterEqual(r["fan_motor"]["facts"]["guard_share"], 0.5)
        self.bad(r["vents_motor"], "guard opening")


# ------------------------------------------------- (R441) fastening
FASTEN = r'''
import atech_cad as cad
def case_lid():
    case = box(0, 60, 0, 40, 0, 30).cut(box(2, 58, 2, 38, 2, 31))
    lid = box(0, 60, 0, 40, 30, 32).fuse(box(2.2, 57.8, 2.2, 37.8, 27, 30)).removeSplitter()
    return case, lid
case, lid = case_lid()
out["lip_only"] = G.fastening([part("Case", case), part("Lid", lid)])
lid2, case2 = cad.screw_through(lid, case, (8, 8, 32), size="M3", ribs=0)
lid2, case2 = cad.screw_through(lid2, case2, (52, 32, 32), size="M3", ribs=0)
screws = [part("Screw_%d" % i, cad.screw("csk_phillips", "M3", 10, at=at, axis="-Z"))
          for i, at in enumerate(((8, 8, 32), (52, 32, 32)), 1)]
out["screwed"] = G.fastening([part("Case", case2), part("Lid", lid2)] + screws)
# SABOTAGE: the same body with its screws removed (bosses and holes stay)
out["no_screws"] = G.fastening([part("Case", case2), part("Lid", lid2)])
# a shell captured between a base and a top screwed to each other
base = box(0, 60, 0, 60, 0, 3)
shell = box(0, 60, 0, 60, 3, 40).cut(box(3, 57, 3, 57, 3, 40))
top = box(0, 60, 0, 60, 40, 43)
post = box(28, 32, 28, 32, 3, 40)
scr = part("Screw_1", cyl(1.4, (30, 30, -0.5), 44))
out["stack"] = G.fastening([part("Base", base), part("Shell", shell),
                            part("Top", top.fuse(post).removeSplitter()), scr])
# a peg of the lid (r 1.5) in a 3.2 bore of the case's rim: a pin
peg_lid = lid.fuse(cyl(1.5, (5, 5, 21), 6)).removeSplitter()
case_b = case.fuse(box(2, 8, 2, 8, 2, 27)).removeSplitter().cut(cyl(1.6, (5, 5, 20), 7.5))
out["pinned"] = G.fastening([part("Case", case_b), part("Lid", peg_lid)])
'''


@unittest.skipIf(FC is None, "freecadcmd not found")
class FasteningGate(unittest.TestCase):
    """R441: housing parts that meet must be joined - a screw through
    both, a snap / clip or a pin; a lip alone is not enough."""

    def test_lip_screws_capture_pin(self):
        r = fc(FASTEN)
        self.assertEqual(sorted(r["lip_only"]["housing"]), ["Case", "Lid"])
        self.assertEqual(r["lip_only"]["loose"], [{"part": "Lid", "meets": ["Case"]}])
        txt = atech_geom.fastening_text(r["lip_only"]["loose"][0])
        self.assertIn("nothing joins them", txt)
        self.assertIn("cad.snap_fit_pair(Case, Lid)", txt)
        self.assertEqual(r["screwed"]["loose"], [], r["screwed"])
        self.assertTrue(any("Screw_" in j[2] for j in r["screwed"]["joined"]))
        # SABOTAGE: screws removed - the bosses and holes alone join nothing
        self.assertEqual([x["part"] for x in r["no_screws"]["loose"]], ["Lid"])
        # the shell between a screwed base and top is clamped
        self.assertEqual(r["stack"]["loose"], [], r["stack"])
        self.assertEqual(r["pinned"]["loose"], [], r["pinned"])
        self.assertTrue(any("pin" in j[2] for j in r["pinned"]["joined"]))


# ---------------------------------------------------- (R442) holders
HOLDER = r'''
import atech_ports as ap
doc = FreeCAD.newDocument("hd")
board = ap.board_object(doc)
pl = ap.module_placement("light", (200, -20, 30), face="-Y")
light, cables = ap.cable(doc, "light", 6, pl)
doc.recompute()
lb = light.Mesh.BoundBox
mods = [mod(board), mod(light)]
cab = {light.Name}
shell = box(160, 240, -40, 40, 0, 60).cut(box(162, 238, -38, 38, 2, 58))
shell = shell.cut(box(lb.XMin - 1, lb.XMax + 1, -41, -37, lb.ZMin - 1, lb.ZMax + 1))
lens = box(lb.XMin - 1, lb.XMax + 1, -40, lb.YMin - 0.2, lb.ZMin - 1, lb.ZMax + 1)
rib = box(lb.XMin, lb.XMax, lb.YMax + 0.2, lb.YMax + 2.2, lb.ZMin, lb.ZMax)
cable_parts = [part(c.Label, c.Shape, cable=True) for c in cables]
out["held"] = G.cable_holders([part("Shell", shell), part("Lens", lens, tr=60),
                               part("Rib", rib)] + cable_parts, mods, cab)
# SABOTAGE: the rib behind it removed - the lens alone (one side)
out["lens_only"] = G.cable_holders([part("Shell", shell), part("Lens", lens, tr=60)]
                                   + cable_parts, mods, cab)
# SABOTAGE: floating free in the shell
out["free"] = G.cable_holders([part("Shell", shell)] + cable_parts, mods, cab)
cr = box(lb.XMin - 3, lb.XMax + 3, lb.YMin - 3, lb.YMax + 3, lb.ZMin - 3, lb.ZMin - 0.2)
out["cradle"] = G.cable_holders([part("Shell", shell), part("Light_Cradle", cr)]
                                + cable_parts, mods, cab)
'''


@unittest.skipIf(FC is None or not HAVE_LIB, "freecadcmd or the Atech library not found")
class HolderGate(unittest.TestCase):
    """R442: a CABLED module needs material within 0.5 mm on two sides,
    or a cradle; a seated one is the board's (board_retention)."""

    def test_two_sides_or_cradle(self):
        r = fc(HOLDER)
        held = r["held"][0]
        self.assertTrue(held["held"], held)
        self.assertGreaterEqual(len(held["sides"]), 2)
        self.assertIn("Lens", sum(held["sides"].values(), []))
        self.assertIn("Rib", sum(held["sides"].values(), []))
        one = r["lens_only"][0]
        self.assertFalse(one["held"], one)                  # SABOTAGE
        self.assertEqual(list(one["sides"].values()), [["Lens"]])
        self.assertIn("held on 1 side only", atech_geom.holder_text(one))
        free = r["free"][0]
        self.assertFalse(free["held"], free)                # SABOTAGE: floating free
        self.assertIn("nothing at all", atech_geom.holder_text(free))
        self.assertTrue(r["cradle"][0]["held"])
        self.assertEqual(r["cradle"][0]["cradle"], "Light_Cradle")


# ----------------------------------------------- (R443) exact overlap
OVERLAP = r'''
import numpy as np
def uv_sphere(r, c, n=48, m=96):
    P = [(c[0], c[1], c[2] + r)]
    for i in range(1, n):
        t = math.pi * i / n
        for j in range(m):
            f = 2 * math.pi * j / m
            P.append((c[0] + r * math.sin(t) * math.cos(f), c[1] + r * math.sin(t) * math.sin(f),
                      c[2] + r * math.cos(t)))
    P.append((c[0], c[1], c[2] - r))
    F = []
    for j in range(m):
        F.append((0, 1 + j, 1 + (j + 1) % m))
    for i in range(n - 2):
        a, b = 1 + i * m, 1 + (i + 1) * m
        for j in range(m):
            k = (j + 1) % m
            F += [(a + j, b + j, b + k), (a + j, b + k, a + k)]
    last = len(P) - 1
    a = 1 + (n - 2) * m
    for j in range(m):
        F.append((a + j, last, a + (j + 1) % m))
    return Mesh.Mesh([[P[i] for i in f] for f in F])
# a cup: its floor's top at z = 5, the whole sensor inside its box (so
# every mesh vertex is tested, and few of them are inside)
cup = box(-30, 30, -30, 30, 0, 20).cut(box(-25, 25, -25, 25, 5, 21))
def sensor(poke):
    # a coarse ball whose lowest vertex (its pole) is `poke` mm into the
    # floor, and a finer one in the air beside it (one module mesh)
    a = uv_sphere(5.0, (-10, 0, 10.0 - poke), n=12, m=24)
    b = uv_sphere(5.0, (10, 0, 12.0), n=24, m=48)
    me = Mesh.Mesh(a)
    me.addMesh(b)
    return me
def run(poke):
    items = [{"name": "P", "label": "Cup", "shape": cup, "role": None},
             {"name": "M", "label": "Sensor", "mesh": sensor(poke), "role": "module"}]
    return [G.overlaps(items)[0] for _k in range(3)]
out["mesh_touch"] = run(0.03)              # 0.03 mm deep at one vertex: ~0.002 mm3
# fast mode keeps the sampled verdict (R443 is quality mode's)
out["mesh_touch_fast"] = G.overlaps([{"name": "P", "label": "Cup", "shape": cup, "role": None},
                                     {"name": "M", "label": "Sensor", "mesh": sensor(0.03),
                                      "role": "module"}], confirm=False)[0]
out["mesh_real"] = run(0.6)                # a 0.6 mm deep cap: a real overlap
# a heavy (mesh-derived) solid, the same two ways
def heavy(poke):
    me = uv_sphere(5.0, (0, 0, 10.0 - poke), n=40, m=80)
    sh = Part.Shape()
    sh.makeShapeFromMesh(me.Topology, 0.01)
    return Part.makeSolid(Part.makeShell(sh.Faces))
for k, poke in (("heavy_touch", 0.02), ("heavy_real", 0.6)):
    so = heavy(poke)
    out[k + "_is_heavy"] = G.heavy(so)
    items = [{"name": "P", "label": "Cup", "shape": cup, "role": None},
             {"name": "S", "label": "Dome", "shape": so, "role": None}]
    out[k] = [G.overlaps(items)[0] for _k in range(2)]
'''


@unittest.skipIf(FC is None, "freecadcmd not found")
class ExactOverlap(unittest.TestCase):
    """R443: a sampled overlap hit on under 5 % of its points is confirmed
    by an exact volume (> 0.01 mm3) before it is reported - every run the
    same verdict."""

    def test_tessellation_touch_passes_real_overlap_fails(self):
        r = fc(OVERLAP)
        # a pole vertex 0.03 mm into the plate: a few sampled points
        # inside, ~0 mm3 - must NOT fail, on every run
        self.assertEqual(r["mesh_touch"], [[], [], []], r["mesh_touch"])
        # ...which the sampled test alone reports (what R443 removes)
        self.assertEqual(len(r["mesh_touch_fast"]), 1, r["mesh_touch_fast"])
        self.assertNotIn("confirmed", r["mesh_touch_fast"][0])
        # SABOTAGE: a 0.6 mm deep cap is reported, confirmed, the same
        # three times
        real = r["mesh_real"]
        self.assertTrue(real[0], real)
        self.assertEqual(real[0], real[1])
        self.assertEqual(real[1], real[2])
        h = real[0][0]
        self.assertLess(h["mesh_points_inside"],
                        atech_geom.CONFIRM_SHARE * h["mesh_points_tested"], h)
        self.assertEqual(h["confirmed"], "exact depths", h)
        self.assertGreater(h["volume_mm3"], 0.5, h)        # a ~5 mm3 cap
        self.assertIn("confirmed", atech_geom.overlap_text(h))
        self.assertTrue(r["heavy_touch_is_heavy"] and r["heavy_real_is_heavy"])
        self.assertEqual(r["heavy_touch"], [[], []], r["heavy_touch"])
        self.assertTrue(r["heavy_real"][0], r)
        self.assertEqual(r["heavy_real"][0], r["heavy_real"][1])


# ------------------------------------------------ (R444) screw pilots
PILOT = r'''
import atech_cad as cad
case = Part.makeBox(20, 20, 12).cut(Part.makeBox(16, 16, 12, V(2, 2, 2)))
rows = {}
for size, d in (("M2", 2.0), ("M2.5", 2.5), ("M3", 3.0)):
    boss = cad.screw_boss(case, (10, 10, 9), "-Z", size, ribs=0)
    screw = cad.screw("socket", size, 6, at=(10, 10, 9.5), axis="-Z")
    rows[size] = G.screw_pilots([{"label": "Screw_1", "shape": screw},
                                 {"label": "Boss", "shape": boss}])[0]
    hits = [{"a": "Boss", "b": "Screw_1", "volume_mm3": round(boss.common(screw).Volume, 3)}]
    rows[size + "_thread"] = G.thread_engagement(hits, [{"label": "Screw_1", "shape": screw},
                                                       {"label": "Boss", "shape": boss}])
# SABOTAGE: a screw driven through a solid rib (no pilot) is no thread
rib = Part.makeBox(20, 20, 12).cut(Part.makeBox(16, 16, 12, V(2, 2, 2))).fuse(
    Part.makeBox(4, 4, 7, V(8, 8, 2)))
screw = cad.screw("socket", "M2.5", 6, at=(10, 10, 9.5), axis="-Z")
hits = [{"a": "Rib", "b": "Screw_1", "volume_mm3": round(rib.common(screw).Volume, 3)}]
rows["rib_thread"] = G.thread_engagement(hits, [{"label": "Screw_1", "shape": screw},
                                                {"label": "Rib", "shape": rib}])
out = rows
'''

SCREWED_MODEL = r'''import Part
import atech_cad as cad
from FreeCAD import Vector as V
case = Part.makeBox(30, 30, 20).cut(Part.makeBox(26, 26, 20, V(2, 2, 2)))
lid = Part.makeBox(30, 30, 3, V(0, 0, 20))
lid, case = cad.screw_through(lid, case, (6, 6, 23), size="M3", ribs=0)
lid, case = cad.screw_through(lid, case, (24, 24, 23), size="M3", ribs=0)
doc.addObject("Part::Feature", "Case").Shape = case
doc.addObject("Part::Feature", "Lid").Shape = lid
for i, at in enumerate(((6, 6, 23), (24, 24, 23)), 1):
    doc.addObject("Part::Feature", "Screw_%d" % i).Shape = cad.screw(
        "csk_phillips", "M3", 10, at=at, axis="-Z")
'''


@unittest.skipIf(FC is None, "freecadcmd not found")
class ThreadFormingPilot(unittest.TestCase):
    """R444: cad.screw_boss drills ~0.85 d; the screw's overlap with it is
    the thread (excused); a pilot of d is a PROBLEM in quality mode."""

    def test_kit_boss_pilot_bites(self):
        r = fc(PILOT)
        for size, pd in (("M2", 1.7), ("M2.5", 2.1), ("M3", 2.5)):
            row = r[size]
            self.assertEqual(row["verdict"], "bites", row)
            self.assertAlmostEqual(row["pilot_mm"], pd, places=2)
            kept, excused = r[size + "_thread"]
            self.assertEqual(kept, [], r[size + "_thread"])
            self.assertEqual(len(excused), 1)
        # SABOTAGE: through a solid rib - not a thread, still an overlap
        kept, excused = r["rib_thread"]
        self.assertEqual(len(kept), 1, r["rib_thread"])
        self.assertEqual(excused, [])

    def test_check_passes_the_kit_screw_and_fails_a_nominal_pilot(self):
        res, out = run_check(SCREWED_MODEL, {}, "a box with a screwed lid")
        self.assertFalse([p for p in res["problems"] if "OVERLAP" in p or "pilot" in p],
                         res["problems"])
        self.assertTrue(any(n.startswith("thread engagement") for n in res["notes"]),
                        res["notes"])
        self.assertTrue(res.get("fastening") and not res["fastening"]["loose"],
                        res.get("fastening"))
        self.assertEqual(last(out), "CHECK PASS", res["problems"])
        # SABOTAGE: the pilots opened to the screw's own 3 mm
        bad = SCREWED_MODEL.replace(
            'doc.addObject("Part::Feature", "Case").Shape = case',
            'for at in ((6, 6), (24, 24)):\n'
            '    case = case.cut(Part.makeCylinder(1.5, 18, V(at[0], at[1], 2.5)))\n'
            'doc.addObject("Part::Feature", "Case").Shape = case')
        res, out = run_check(bad, {}, "a box with a screwed lid")
        self.assertTrue(any("spins loose" in p for p in res["problems"]), res["problems"])
        self.assertTrue(last(out).startswith("CHECK FAIL"))
        res, out = run_check(bad, {}, "a box with a screwed lid",
                             env={"ATECH_PROMPT_MODE": "fast"})
        self.assertFalse(any("spins loose" in p for p in res["problems"]))
        self.assertTrue(any("spins loose" in w for w in res["warnings"]))


# ----------------------------------------- the gates in a real ./check
LID_MODEL = r'''import Part
from FreeCAD import Vector as V
case = Part.makeBox(60, 40, 30).cut(Part.makeBox(56, 36, 30, V(2, 2, 2)))
lid = Part.makeBox(60, 40, 2, V(0, 0, 30)).fuse(Part.makeBox(55.6, 35.6, 3, V(2.2, 2.2, 27)))
doc.addObject("Part::Feature", "Case").Shape = case
doc.addObject("Part::Feature", "Lid").Shape = lid.removeSplitter()
'''


@unittest.skipIf(FC is None, "freecadcmd not found")
class GatesInCheck(unittest.TestCase):
    """The new stages run in ./check: quality mode fails, fast mode warns."""

    def test_unfastened_lid(self):
        res, out = run_check(LID_MODEL, {}, "a box with a lid")
        self.assertTrue(any(p.startswith("fastening: Lid meets Case") for p in res["problems"]),
                        res["problems"])
        self.assertTrue(last(out).startswith("CHECK FAIL"))
        res, out = run_check(LID_MODEL, {}, "a box with a lid", env={"ATECH_PROMPT_MODE": "fast"})
        self.assertFalse(any(p.startswith("fastening:") for p in res["problems"]))
        self.assertTrue(any(w.startswith("fastening:") for w in res["warnings"]))


# ------------------------------------- the product seeds, with requests
def _request(path):
    with open(path, encoding="utf-8") as fh:
        doc = ast.get_docstring(ast.parse(fh.read())) or ""
    m = re.match(r'\s*Example:\s*"([^"]+)"', doc)
    return m.group(1) if m else None


def _seeds():
    folder = os.path.join(KIT, "examples")
    out = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(".py") and name != "atech_case.py":
            req = _request(os.path.join(folder, name))
            if req:
                out.append((name, req))
    return out


def _build_seed(name, req):
    import test_kit_examples as tke
    ws = tempfile.mkdtemp(prefix="atech-r280-seed-")
    try:
        src = os.path.join(KIT, "examples", name)
        with open(src, encoding="utf-8") as fh:
            code = fh.read()
        with open(os.path.join(ws, "model.py"), "w", encoding="utf-8") as fh:
            fh.write(code)
        with open(os.path.join(ws, "intent.json"), "w", encoding="utf-8") as fh:
            json.dump(tke.intent_of(src), fh)
        with open(os.path.join(ws, ".atech_turn.json"), "w", encoding="utf-8") as fh:
            json.dump({"fix": False, "request": req}, fh)
        env = dict(os.environ, ATECH_CHECK_SCRIPT=os.path.join(ws, "model.py"),
                   ATECH_CHECK_PNG="", ATECH_CHECK_PATH=PROJECTS,
                   ATECH_CHECK_TIMEOUT=str(int(tke.BUILD_LIMIT_S)), **LIB_ENV)
        p = subprocess.run([FC, os.path.join(KIT, "check.py")], env=env, capture_output=True,
                           text=True, timeout=1500, cwd=ws)
        out = p.stdout + p.stderr
        return tak.check_json(out), out
    finally:
        shutil.rmtree(ws, ignore_errors=True)


@unittest.skipIf(FC is None or not HAVE_LIB, "freecadcmd or the Atech library not found")
class ExamplesWithRequests(unittest.TestCase):
    """Every product seed (examples/*.py with an 'Example: "<request>"'
    docstring) under ./check with its own request: CHECK PASS, its
    archetype NOTE printed. A seed that fails here is fixed in the seed
    (WS1 / WS2), never by moving a threshold."""

    def test_every_seed_passes_its_archetype(self):
        seeds = _seeds()
        self.assertTrue(seeds)
        with ThreadPoolExecutor(max_workers=min(5, len(seeds))) as ex:
            got = list(ex.map(lambda s: (s,) + _build_seed(*s), seeds))
        for (name, req), res, out in got:
            with self.subTest(example=name, request=req):
                arch = atech_geom.archetype_of(req)[0]
                if arch is not None:
                    self.assertTrue(any(n.startswith("ARCHETYPE ") for n in res["notes"]),
                                    res["notes"])
                # R500: never a PROBLEM; R600: never a WARNING
                self.assertFalse([p for p in res["problems"] if p.startswith("ARCHETYPE ")])
                self.assertFalse([w for w in res.get("warnings", [])
                                  if w.startswith("ARCHETYPE ")])
                self.assertEqual(last(out), "CHECK PASS", res["problems"])


if __name__ == "__main__":
    unittest.main()
