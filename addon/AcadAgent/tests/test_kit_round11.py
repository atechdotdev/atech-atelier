"""WS-KIT-CHECKS round 11: ./check (agent_kit/check.py + atech_geom.py).

  R214  a cap whose snap hook reaches the board at its -X end (board edge at
        x 0) is reported as overlapping the motherboard mesh (D80: End_Cap_L
        26.5 mm3 into the board, card green). Cause measured: the solid-vs-
        mesh test only sampled the MESH's vertices inside the solid, every
        19th of the board's 28 034 - none under the hook. Now the vertices
        are taken from the solid's box first, and the solid's own surface
        samples are tested inside the mesh (ray parity).
  R213  intent.json "mates": a reference plate (thickness, hole grid,
        where its front face is) built by ./check; a part sharing volume
        with it fails, naming the volume, depth and place - pegs in their
        holes pass. Sabotage: pegs wider than the holes fail.
  R212  a part whose only contact with the others is a face touch fails
        ("only touches"); a lipped cap and the kit's snap_fit_pair caps
        pass; the lipped cap with its lip removed (sabotage) fails.
  S65   the holes line says how coaxial bores through several knuckles of
        one body are counted (r10 hinged_box_lid).

Runs under SYSTEM python; every FreeCAD step is a freecadcmd child, one at
a time (repo rule). Skips without freecadcmd (ATECH_REQUIRE_FREECADCMD=1
makes that a failure, as test_agent_kit).

RUN:
    python3 -m unittest addon/AcadAgent/tests/test_kit_round11.py -v
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import test_agent_kit as tak  # noqa: E402

FC, KIT, PROJECTS = tak.FC, tak.KIT, tak.PROJECTS
REPO = os.path.normpath(os.path.join(tak.ADDON, "..", ".."))
R10X = os.path.join(REPO, "docs", "verification", "eval", "round_extra_10")
TIMES = {}


def check(code, intent=None, request=None, atech=False):
    """./check on model.py `code` with intent.json `intent` and, when
    given, Studio's turn file carrying the user's `request`."""
    ws = tempfile.mkdtemp(prefix="atech-r11-")
    try:
        with open(os.path.join(ws, "model.py"), "w", encoding="utf-8") as fh:
            fh.write(code)
        if intent is not None:
            with open(os.path.join(ws, "intent.json"), "w", encoding="utf-8") as fh:
                json.dump(intent, fh)
        if request is not None:
            with open(os.path.join(ws, ".atech_turn.json"), "w", encoding="utf-8") as fh:
                json.dump({"fix": False, "request": request}, fh)
        env = {"ATECH_CHECK_SCRIPT": os.path.join(ws, "model.py"), "ATECH_CHECK_PNG": ""}
        if atech:
            env["ATECH_CHECK_PATH"] = PROJECTS
        out = tak.fc(os.path.join(KIT, "check.py"), env)
        r = tak.check_json(out)
        r["_last"] = [ln for ln in out.splitlines() if ln.startswith("CHECK ")][-1:]
        return r
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------- R212
# A 60 x 40 x 30 case, 2 mm walls, open at its +X end; an End_Cap closing
# it: a flat 2 mm plate on the end, or that plate with a lip 3 mm into the
# opening (0.15 mm clearance all round).
CASE_END = r"""import Part, atech_cad as cad
from FreeCAD import Vector
b = Part.makeBox(60, 40, 30)
case = cad.shell(b, 2, cad.faces_at(b, "+X"))
cap = Part.makeBox(2, 40, 30, Vector(60, 0, 0))
if %(lip)s:
    c = 0.15
    ring = cad.cut(Part.makeBox(3, 36 - 2 * c, 26 - 2 * c, Vector(57, 2 + c, 2 + c)),
                   Part.makeBox(3, 32 - 2 * c, 22 - 2 * c, Vector(57, 4 + c, 4 + c)))
    cap = cad.fuse_one(cap, ring)
doc.addObject("Part::Feature", "Case").Shape = case
doc.addObject("Part::Feature", "End_Cap").Shape = cap
"""

# The r7 nightlight's way (round_extra_7/atech_nightlight_closed): a flat
# 2 mm lid on the open end, screwed - M3 clearance holes (3.2) over two
# bosses with 2.5 pilot holes 10 deep. A fastened joint, not a touch.
SCREWED = r"""import Part, atech_cad as cad
from FreeCAD import Vector
b = Part.makeBox(60, 40, 30)
case = cad.shell(b, 2, cad.faces_at(b, "+X"))
case = cad.fuse_one(case, *[Part.makeCylinder(4.5, 12, Vector(48, 20, z), Vector(1, 0, 0))
                            for z in (6.4, 23.6)])
lid = Part.makeBox(2, 40, 30, Vector(60, 0, 0))
for z in (6.4, 23.6):
    case = cad.hole(case, (60, 20, z), "-X", 2.5, depth=10.0)
    lid = cad.hole(lid, (62, 20, z), "-X", 3.2, through=True)
doc.addObject("Part::Feature", "Case").Shape = case
doc.addObject("Part::Feature", "Lid").Shape = lid
"""

# The kit's own snap-fit pair: an 80 x 50 x 30 box, a 2 mm lid on top.
SNAP = r"""import Part, atech_cad as cad
from FreeCAD import Vector
b = Part.makeBox(80, 50, 30)
case = cad.shell(b, 2, cad.faces_at(b, "+Z"))
lid = Part.makeBox(80, 50, 2, Vector(0, 0, 30))
case, lid = cad.snap_fit_pair(case, lid, count=4)
doc.addObject("Part::Feature", "Case").Shape = case
doc.addObject("Part::Feature", "Lid").Shape = lid
"""


@unittest.skipIf(FC is None, "freecadcmd not found")
class R212JointEngagement(unittest.TestCase):

    def test_flat_plate_only_touches_fails_named(self):
        r = check(CASE_END % {"lip": False}, request="a case with a push-fit end cap")
        bad = r.get("joint_problems") or []
        self.assertEqual(r["_last"][0][:10], "CHECK FAIL", r["_last"])
        self.assertTrue(any(p.startswith("joint: End_Cap only touches Case") for p in bad),
                        bad)
        self.assertTrue(any("push/snap fit" in p for p in bad), bad)
        self.assertIn(bad[0], r["problems"])
        # the cap falls off, not the case: the case is not named as well
        self.assertFalse(any(p.startswith("joint: Case") for p in bad), bad)
        TIMES["R212 flat plate joints (s)"] = r.get("joints_seconds")

    def test_screwed_flat_lid_passes(self):
        r = check(SCREWED)
        self.assertEqual(r.get("joint_problems"), [], r.get("joint_problems"))
        lid = [j for j in r["joints"] if j["part"] == "Lid"][0]
        self.assertEqual(lid["engaged"], "Case")
        self.assertIn("coaxial bores", lid["fastened"])
        # sabotage: the same lid with its screw holes moved off the bosses
        r = check(SCREWED.replace("(62, 20, z)", "(62, 12, z)"))
        self.assertTrue(any(p.startswith("joint: Lid only touches Case")
                            for p in r.get("joint_problems") or []), r["problems"])

    def test_lipped_cap_passes(self):
        r = check(CASE_END % {"lip": True}, request="a case with a push-fit end cap")
        self.assertEqual(r.get("joint_problems"), [], r.get("joint_problems"))
        self.assertEqual(r["_last"], ["CHECK PASS"], r["problems"])
        cap = [j for j in r["joints"] if j["part"] == "End_Cap"][0]
        self.assertEqual(cap["engaged"], "Case")
        self.assertGreaterEqual(cap["depth_mm"], 2.9)       # the 3 mm lip
        TIMES["R212 lipped cap joints (s)"] = r.get("joints_seconds")

    def test_sabotage_remove_the_lip_fails(self):
        # the same file as the passing lipped cap, its lip switched off
        code = (CASE_END % {"lip": True}).replace("if True:", "if False:")
        self.assertNotEqual(code, CASE_END % {"lip": True})
        r = check(code)
        self.assertTrue(any(p.startswith("joint: End_Cap only touches Case")
                            for p in r.get("joint_problems") or []), r["problems"])

    def test_snap_fit_pair_caps_pass(self):
        r = check(SNAP, request="a box with a snap-fit lid")
        self.assertEqual(r.get("joint_problems"), [], r.get("joint_problems"))
        lid = [j for j in r["joints"] if j["part"] == "Lid"][0]
        self.assertEqual(lid["engaged"], "Case")
        self.assertEqual(r["_last"], ["CHECK PASS"], r["problems"])

    def test_hinged_box_lid_lip_engages(self):
        r = check(_read(os.path.join(R10X, "hinged_box_lid", "model.py")))
        self.assertEqual(r.get("joint_problems"), [], r.get("joint_problems"))


# --------------------------------------------------------------- R213
# A pegboard hook against a 1/4 in pegboard (6.35 mm thick, 1/4 in holes on
# a 25.4 mm grid, front face at y = 0 looking +Y, a hole centred on x 0,
# z 0): a 20 x 4 x 40 back plate on the front face, two pegs in the holes at
# z 0 and z -25.4, an 8 x 8 arm out along +Y between them. %(root)s is
# where the arm starts in y: 0 at the board face, -4.9 the D79 hook (its
# root 4.9 mm into the board); %(peg)s the peg diameter.
HOOK = r"""import Part, atech_cad as cad
from FreeCAD import Vector
back = Part.makeBox(20, 4, 40, Vector(-10, 0, -32))
pegs = [Part.makeCylinder(%(peg)s / 2.0, 9, Vector(0, -9, z), Vector(0, 1, 0))
        for z in (0.0, -25.4)]
arm = Part.makeBox(8, 50 - (%(root)s), 8, Vector(-4, %(root)s, -16))
doc.addObject("Part::Feature", "Hook").Shape = cad.fuse_one(back, arm, *pegs)
"""
BOARD = {"mates": [{"name": "pegboard", "thickness_mm": 6.35, "hole_d_mm": 6.35,
                    "pitch_mm": 25.4, "face": "+Y", "hole_at": [0, 0, 0]}]}


@unittest.skipIf(FC is None, "freecadcmd not found")
class R213Mates(unittest.TestCase):

    def test_d79_arm_root_in_the_board_fails_with_volume_and_place(self):
        r = check(HOOK % {"root": -4.9, "peg": 6.0}, BOARD)
        bad = r.get("mates_problems") or []
        self.assertEqual(len(bad), 1, r["problems"])
        self.assertIn("mates: Hook runs 4.90 mm into the pegboard", bad[0])
        self.assertIn("313.60 mm3 shared", bad[0])          # 8 x 8 x 4.9
        self.assertIn("y -4.90 .. 0.00", bad[0])
        row = r["mates"][0]["parts"][0]
        self.assertEqual(row["verdict"], "FAIL")
        self.assertEqual(row["at"], [0.0, -2.45, -12.0])
        self.assertEqual(r["_last"][0][:10], "CHECK FAIL")
        TIMES["R213 failing hook mates (s)"] = r.get("mates_seconds")

    def test_arm_from_the_board_face_passes(self):
        r = check(HOOK % {"root": 0.0, "peg": 6.0}, BOARD)
        self.assertEqual(r.get("mates_problems"), [], r.get("mates_problems"))
        row = r["mates"][0]["parts"][0]
        self.assertEqual(row["verdict"], "PASS")
        self.assertEqual(row["volume_mm3"], 0.0)
        self.assertEqual(row["pegs_in_holes"], 2)
        self.assertEqual(row["gap_mm"], 0.0)              # rests on its face
        self.assertEqual(r["_last"], ["CHECK PASS"], r["problems"])
        TIMES["R213 passing hook mates (s)"] = r.get("mates_seconds")

    def test_sabotage_pegs_wider_than_the_holes_fail(self):
        # proves the holes are not a blanket excuse: Ø7 pegs in Ø6.35 holes
        r = check(HOOK % {"root": 0.0, "peg": 7.0}, BOARD)
        bad = r.get("mates_problems") or []
        self.assertEqual(len(bad), 1, r["problems"])
        self.assertIn("mates: Hook runs 6.35 mm into the pegboard", bad[0])

    def test_malformed_mates_names_the_form(self):
        r = check(HOOK % {"root": 0.0, "peg": 6.0}, {"mates": {"thickness_mm": 6.35}})
        self.assertTrue(any("mates must be" in p for p in r["problems"]), r["problems"])

    def test_check_names_the_key_build_reads(self):
        # build.kit_reads_intent_key("mates") reads it from the kit source
        sys.path.insert(0, tak.ADDON)
        from acadagent import build
        self.assertTrue(build.kit_reads_intent_key("mates"))


# --------------------------------------------------------------- R214
def _doorbell(pad):
    code = _read(os.path.join(R10X, "atech_doorbell_remote", "model.py"))
    old = "BEAM_L, PAD = 8.0, 9.0"
    assert old in code
    return code.replace(old, "BEAM_L, PAD = 8.0, %r" % pad)


@unittest.skipIf(FC is None, "freecadcmd not found")
@unittest.skipUnless(os.path.isfile(os.path.join(PROJECTS, "atech_ports.py")),
                     "atech_ports not found")
class R214CapHookIntoBoard(unittest.TestCase):
    INTENT = {"board": "upright", "fitted_after": ["End_Cap_L", "End_Cap_R"]}

    def test_cap_hook_into_the_board_fails(self):
        # the r10 doorbell with no free space at the X ends (PAD 0): End_Cap_L's
        # snap beams run into the board at its x 0 edge - 20.1 mm3 by a
        # common() with the board mesh made solid (measured once by hand,
        # 23 s; ./check does not pay that)
        r = check(_doorbell(0.0), self.INTENT, atech=True)
        hits = [h for h in r["overlaps"] if {h["a"], h["b"]} == {"End_Cap_L", "motherboard"}]
        self.assertEqual(len(hits), 1, r["overlaps"])
        self.assertGreater(hits[0]["mesh_points_inside"], 0)
        self.assertLess(hits[0]["at"][0], 8.0)            # at the -X end
        self.assertTrue(any(p.startswith("OVERLAP End_Cap_L and motherboard")
                            for p in r["problems"]), r["problems"])
        self.assertFalse(any("End_Cap_R" in p for p in r["problems"]), r["problems"])
        TIMES["R214 failing doorbell check (s)"] = r["seconds"]
        TIMES["R214 failing doorbell geometry (s)"] = r["geometry_seconds"]

    def test_r10_doorbell_still_passes(self):
        r = check(_doorbell(9.0), self.INTENT, atech=True)
        self.assertEqual(r["overlaps"], [])
        self.assertEqual(r["_last"], ["CHECK PASS"], r["problems"])
        TIMES["R214 r10 doorbell check (s)"] = r["seconds"]
        TIMES["R214 r10 doorbell geometry (s)"] = r["geometry_seconds"]


# ---------------------------------------------------------------- S65
@unittest.skipIf(FC is None, "freecadcmd not found")
class S65CoaxialHoles(unittest.TestCase):

    def test_hinged_box_lid_holes_line_names_the_coaxial_count(self):
        hb = os.path.join(R10X, "hinged_box_lid")
        r = check(_read(os.path.join(hb, "model.py")),
                  json.loads(_read(os.path.join(hb, "intent.json"))))
        lines = [n for n in r["notes"] + r["problems"] if n.startswith("holes:")]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn(lines[0], r["notes"])                 # counted: a NOTE
        self.assertIn("coaxial bores are counted ONCE per body and axis", lines[0])
        self.assertIn("Box: diameter 2 mm along X through 2 walls/knuckles "
                      "(1 hole, 2 openings)", lines[0])
        self.assertIn("counted per knuckle (per opening) that is 3", lines[0])
        self.assertEqual(r["_last"], ["CHECK PASS"], r["problems"])

    def test_a_real_miss_still_fails_and_says_how_it_counted(self):
        hb = os.path.join(R10X, "hinged_box_lid")
        intent = json.loads(_read(os.path.join(hb, "intent.json")))
        intent["holes"] = {"count": 5, "d_mm": 2.0}
        r = check(_read(os.path.join(hb, "model.py")), intent)
        bad = [p for p in r["problems"] if p.startswith("holes:")]
        self.assertEqual(len(bad), 1, r["problems"])
        self.assertIn("coaxial bores are counted ONCE per body and axis", bad[0])


def tearDownModule():
    if TIMES:
        print("\nR11 kit timings: " + json.dumps(TIMES, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
