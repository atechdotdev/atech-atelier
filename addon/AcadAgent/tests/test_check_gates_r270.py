"""R270 (WS3): checker gates that close round 1's false CHECK PASSes.

    cd addon/AcadAgent/tests && python3 -m unittest test_check_gates_r270

Round 1 (2026-10-20, docs/verification/eval/r1_*) ended turns on CHECK PASS
with sealed headlights, a blind ToF, a buried button and a walled-in USB-C
("a toy car" names none of them), a 0.28 mm wall, a 52 mm bore through both
walls of the body, and a desk robot whose screen sat behind a solid face.
Each gate below has a SABOTAGE case: the input that must fail does, the
input that must pass does.

Plain-python cases need nothing; the FreeCAD-backed ones skip without
freecadcmd (ATECH_FREECADCMD) or the Atech library; the round-1 replays
skip when docs/verification/eval/r1_* is not there.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import test_agent_kit as tak  # noqa: E402

FC, KIT, PROJECTS = tak.FC, tak.KIT, tak.PROJECTS
REPO = os.path.normpath(os.path.join(tak.ADDON, "..", ".."))
EVAL = os.path.join(REPO, "docs", "verification", "eval")
if KIT not in sys.path:
    sys.path.insert(0, KIT)

import atech_geom  # noqa: E402  (plain python: no FreeCAD at import)

HAVE_LIB = os.path.isfile(os.path.join(PROJECTS, "atech_ports.py"))
MARK = "R270JSON="


def row(label, module, kind, open_=0, rays=169, **kw):
    """A face_open row as atech_geom.face_open returns it."""
    r = {"label": label, "module": module, "kind": kind, "face": "top",
         "open": open_, "rays": rays, "open_pct": round(100.0 * open_ / rays, 1),
         "normal": [0.0, -1.0, 0.0], "blocked_by": "Body" if not open_ else None,
         "unmeasured": [], "see_through": [], "covered_by": [], "cover_problems": [],
         "near": []}
    r.update(kw)
    return r


class _Env(object):
    """Set / unset environment variables for a block."""

    def __init__(self, **kv):
        self.kv, self.old = kv, {}

    def __enter__(self):
        for k, v in self.kv.items():
            self.old[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------- (1)
class SealedPlacedModules(unittest.TestCase):
    """(1) A placed module whose kind needs an opening is a PROBLEM when
    sealed, named by the request or not (quality mode)."""

    KINDS = (("light_6", "light", "light"), ("distance_sensor_8", "distance_sensor", "sensor"),
             ("screen_11_12", "screen", "screen"), ("button_2", "button", "button"),
             ("speaker_p12", "speaker", "speaker"), ("mic_p4", "microphone", "sensor"))

    def test_toy_car_request_names_none_yet_each_sealed_module_fails(self):
        rows = [row(l, m, k) for l, m, k in self.KINDS]
        rows.append(row("usbc_p7", "usbc", "USB-C socket", face="socket",
                        normal=[0.0, 1.0, 0.0]))
        bad, warn = atech_geom.face_open_problems(rows, "a toy car", mode="quality")
        for lab, _m, _k in self.KINDS + (("usbc_p7", 0, 0),):
            self.assertTrue(any(p.startswith(lab + " (a ") and "sealed in" in p
                                for p in bad), (lab, bad))
        self.assertTrue(any("you placed it" in p for p in bad), bad)
        self.assertEqual(warn, [])

    def test_sabotage_fast_mode_keeps_the_request_named_rule(self):
        rows = [row(l, m, k) for l, m, k in self.KINDS]
        bad, warn = atech_geom.face_open_problems(rows, "a toy car", mode="fast")
        self.assertEqual(bad, [])
        bad, warn = atech_geom.face_open_problems(rows, None, mode="fast")
        self.assertEqual(bad, [])
        self.assertEqual(len(warn), len(rows))
        # named: a problem in either mode
        bad, _w = atech_geom.face_open_problems([row("light_6", "light", "light")],
                                                "a lamp with a light", mode="fast")
        self.assertTrue(bad and "asks for a light" in bad[0], bad)

    def test_mode_from_environment(self):
        rows = [row("light_6", "light", "light")]
        with _Env(ATECH_PROMPT_MODE=None):
            self.assertTrue(atech_geom.quality_mode())
            self.assertEqual(len(atech_geom.face_open_problems(rows, "a toy car")[0]), 1)
        with _Env(ATECH_PROMPT_MODE="fast"):
            self.assertFalse(atech_geom.quality_mode())
            self.assertEqual(atech_geom.face_open_problems(rows, "a toy car")[0], [])

    def test_covers_entry_exempts(self):
        r = row("button_2", "button", "button", covered_by=["Key_Cap"])
        bad, _w = atech_geom.face_open_problems([r], "a toy car", mode="quality")
        self.assertEqual(bad, [])

    def test_orientation_and_temperature_stay_warnings(self):
        rows = [row("temp_p3", "temp_humidity", "sensor"),
                row("orientation_p10", "orientation", None)]
        bad, warn = atech_geom.face_open_problems(rows, None, mode="quality")
        self.assertEqual(bad, [])
        self.assertEqual(len(warn), 1)          # the temperature sensor (no request)
        bad, warn = atech_geom.face_open_problems(rows, "a toy car", mode="quality")
        self.assertEqual((bad, warn), ([], []))


# ---------------------------------------------------------------- (2)
class OpenFloors(unittest.TestCase):
    """(2) Open, but not enough: screen active area, ToF aperture, sound."""

    def judge(self, r):
        return atech_geom.face_open_problems([r], "x", mode="quality")[0]

    def test_screen_window_must_show_the_active_area(self):
        bad = self.judge(row("screen_11_12", "screen", "screen", 99, active_pct=62.5))
        self.assertTrue(bad and "62.5 % of its 25.6 x 13.5 mm active area" in bad[0], bad)
        self.assertEqual(self.judge(row("screen_11_12", "screen", "screen", 99,
                                        active_pct=100.0)), [])

    def test_tof_needs_a_10x6_aperture(self):
        bad = self.judge(row("distance_sensor_8", "distance_sensor", "sensor", 20,
                             aperture_pct=41.7))
        self.assertTrue(bad and "10 x 6 mm aperture" in bad[0], bad)
        self.assertEqual(self.judge(row("distance_sensor_8", "distance_sensor", "sensor",
                                        20, aperture_pct=100.0)), [])

    def test_sound_modules_need_three_percent(self):
        # the round-1 mic: 1 of 169 coarse rays, 0.9 % on the fine grid
        bad = self.judge(row("microphone_p5_4", "microphone", "sensor", 1, fine_pct=0.9))
        self.assertTrue(bad and "only 0.9 %" in bad[0] and "hear" in bad[0], bad)
        self.assertEqual(self.judge(row("microphone_p5_4", "microphone", "sensor", 1,
                                        fine_pct=4.2)), [])
        # the mic is judged over its port zone mid-plate when measured: the
        # catalogue's 7-hole grille reads ~1 % of the plate, 4.4 % of the zone
        self.assertEqual(self.judge(row("microphone_p5_4", "microphone", "sensor", 1,
                                        zone_pct=4.4)), [])
        bad = self.judge(row("microphone_p5_4", "microphone", "sensor", 9, zone_pct=0.0))
        self.assertTrue(bad and "the middle 12 x 12 mm" in bad[0], bad)
        bad = self.judge(row("speaker_p2", "speaker", "speaker", 3))   # 1.8 %, coarse
        self.assertTrue(bad and "be heard" in bad[0], bad)
        self.assertEqual(self.judge(row("speaker_p2", "speaker", "speaker", 16)), [])

    def test_fast_mode_does_not_judge_floors(self):
        r = row("screen_11_12", "screen", "screen", 99, active_pct=10.0)
        self.assertEqual(atech_geom.face_open_problems([r], "x", mode="fast")[0], [])


# ---------------------------------------------------------------- (3)
class ThroughHolesIntended(unittest.TestCase):

    def test_listing_forms(self):
        f = atech_geom.through_intended
        self.assertFalse(f(None, "Body", 52))
        self.assertFalse(f({}, "Body", 52))
        self.assertTrue(f({"through_holes": ["Body"]}, "Body", 52))
        self.assertFalse(f({"through_holes": ["Chassis"]}, "Body", 52))
        self.assertTrue(f({"through_holes": [52]}, "Body", 52.05))
        self.assertFalse(f({"through_holes": [3]}, "Body", 52))
        self.assertTrue(f({"through_holes": [{"part": "Body", "d_mm": 52}]}, "Body", 52))
        self.assertFalse(f({"through_holes": [{"part": "Body", "d_mm": 3}]}, "Body", 52))
        self.assertFalse(f({"through_holes": [{}]}, "Body", 52))
        self.assertFalse(f({"through_holes": [True]}, "Body", 1))

    def test_pin_bores_stay_warnings(self):
        f = atech_geom.through_is_problem
        self.assertTrue(f({}, "Body", 52))
        self.assertTrue(f(None, "Body", 6.0))
        # SABOTAGE: a 2 mm hinge-pin bore, or a listed one, does not fail
        self.assertFalse(f({}, "Box", 2.0))
        self.assertFalse(f({"through_holes": [52]}, "Body", 52))

    def test_problem_text_names_the_way_out(self):
        b = {"d_mm": 52.0, "axis": "X", "at": [0, -10, 24],
             "wall_spans": [[-34.5, -22.77], [82.77, 94.5]]}
        t = atech_geom.through_problem_text("Body", b)
        self.assertIn("goes through 2 walls", t)
        self.assertIn('"through_holes": ["Body"]', t)
        self.assertNotIn("fine as it is", t)


# ---------------------------------------------------------------- (5)
class TurnClock(unittest.TestCase):

    def setUp(self):
        self.chk = tak._load_check()

    def test_unset_prints_nothing(self):
        self.assertEqual(self.chk.turn_clock(environ={}), [])
        self.assertEqual(self.chk.turn_clock(environ={"ATECH_TURN_T0": "soon"}), [])

    def test_clock_only_no_stage_nudges(self):
        # R500 (the user: "it's about results, not how long it takes"): the
        # clock is plain information - no stage reminder, never "STOP"
        t0 = 1_000_000
        f = lambda s: self.chk.turn_clock(now=t0 + s, environ={"ATECH_TURN_T0": str(t0)})
        self.assertEqual(f(65), ["TURN CLOCK 01:05"])
        self.assertEqual(f(16 * 60 + 5), ["TURN CLOCK 16:05"])
        self.assertEqual(f(41 * 60), ["TURN CLOCK 41:00"])
        self.assertEqual(f(50 * 60), ["TURN CLOCK 50:00"])
        self.assertEqual(f(75 * 60 + 9), ["TURN CLOCK 75:09"])
        self.assertEqual(self.chk.TURN_STAGES, ())
        src = open(self.chk.__file__, encoding="utf-8").read()
        for nudge in ("STOP ADDING", "end on this passing build", "finish the detail list",
                      "should be open now", "past %d min"):
            self.assertNotIn(nudge, src)
        # SABOTAGE: a clock before its start reads 00:00, never negative
        self.assertEqual(f(-30), ["TURN CLOCK 00:00"])


# ------------------------------------------------- (4) fitted_after screws
class FittedAfterScrews(unittest.TestCase):

    def run_fitted(self, want, built, out_dir=None):
        chk = tak._load_check()
        ws = tempfile.mkdtemp(prefix="atech-r270-")
        try:
            with open(os.path.join(ws, "intent.json"), "w") as fh:
                json.dump({"fitted_after": want}, fh)

            class O(object):
                def __init__(self, n):
                    self.Name = self.Label = n
                    self.Shape = object()

            class Doc(object):
                Objects = [O(n) for n in built]
            res = {"script": os.path.join(ws, "model.py"), "warnings": [], "problems": []}
            with _Env(ATECH_CHECK_OUT=out_dir):
                chk._fitted_after(Doc(), res)
            return res
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_missing_screw_is_a_problem(self):
        res = self.run_fitted(["Lid", "Screw_1", "Screw_2"], ["Case", "Lid", "Screw_1"])
        self.assertTrue(any("Screw_2" in p and "fastener" in p for p in res["problems"]),
                        res["problems"])
        self.assertEqual(res["fitted_after_missing_screws"], ["Screw_2"])

    def test_sabotage_other_parts_still_a_note(self):
        res = self.run_fitted(["Lid", "End_Cap"], ["Case", "Lid"])
        self.assertEqual(res["problems"], [])
        self.assertTrue(any("End_Cap" in n for n in res["notes"]))
        res = self.run_fitted(["Screw_1"], ["Case", "Screw_1"])
        self.assertEqual(res["problems"], [])


# ------------------------------------------------- FreeCAD-backed helpers
def fc_json(code, env=None, timeout=600):
    """Run `code` under freecadcmd with the kit + library importable; the
    script prints MARK + json; returns that object."""
    d = tempfile.mkdtemp(prefix="atech-r270-fc-")
    try:
        p = os.path.join(d, "probe.py")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("import sys\nsys.path[:0] = [%r, %r]\n" % (KIT, PROJECTS) + code)
        out = tak.fc(p, env or {}, timeout=timeout)
        for ln in reversed(out.splitlines()):
            if ln.startswith(MARK):
                return json.loads(ln[len(MARK):])
        raise AssertionError("no %s line in:\n%s" % (MARK, out[-3000:]))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def run_check(code, intent=None, request=None, env=None, keep_ws=None):
    """./check on model.py `code`; (result, full output)."""
    ws = keep_ws or tempfile.mkdtemp(prefix="atech-r270-ws-")
    try:
        with open(os.path.join(ws, "model.py"), "w", encoding="utf-8") as fh:
            fh.write(code)
        if intent is not None:
            with open(os.path.join(ws, "intent.json"), "w", encoding="utf-8") as fh:
                json.dump(intent, fh)
        if request is not None:
            with open(os.path.join(ws, ".atech_turn.json"), "w", encoding="utf-8") as fh:
                json.dump({"fix": False, "request": request}, fh)
        e = {"ATECH_CHECK_SCRIPT": os.path.join(ws, "model.py"), "ATECH_CHECK_PNG": "",
             "ATECH_CHECK_PATH": PROJECTS, "ATECH_CHECK_TIMEOUT": "600"}
        e.update(env or {})
        out = tak.fc(os.path.join(KIT, "check.py"), e, timeout=1200)
        return tak.check_json(out), out
    finally:
        if keep_ws is None:
            shutil.rmtree(ws, ignore_errors=True)


def last(out):
    return ([ln for ln in out.splitlines() if ln.startswith("CHECK ")] or [""])[-1]


# ---------------------------------------------------------- (3) walls
WALLS = r'''
import json, Part, atech_geom as G
from FreeCAD import Vector as V
out = {}
for t in (0.3, 0.55, 1.2):
    box = Part.makeBox(40, 30, 20).cut(Part.makeBox(40 - 2 * t, 30 - 2 * t, 20, V(t, t, t)))
    w = G.thin_walls([{"label": "Shell", "shape": box}], budget_s=5)
    bad, rows = G.thin_wall_problems(w, {"Shell": box})
    out[str(t)] = {"min": w["min"]["mm"] if w["min"] else None, "bad": bad, "rows": rows}
# a sliver: one face of a 2 mm wall pocketed down to 0.4 mm over 6 x 6 mm
box = Part.makeBox(40, 30, 20).cut(Part.makeBox(36, 26, 20, V(2, 2, 2)))
box = box.cut(Part.makeBox(6, 1.6, 6, V(10, 0, 8)))
w = G.thin_walls([{"label": "Pocketed", "shape": box}], budget_s=5, samples=20000)
bad, rows = G.thin_wall_problems(w, {"Pocketed": box})
out["pocket"] = {"min": w["min"]["mm"] if w["min"] else None, "bad": bad}
out["exact"] = G.wall_exact(box, (20, 15, 0), (0, 0, 1), span=3.0)
out["exact_thin"] = G.wall_exact(box, (13, 1.6, 11), (0, 1, 0))
out["pocket_detail"] = G.wall_is_detail(box, (13, 1.6, 11), (0, 1, 0), 0.4)
# an embossed stroke: 0.5 wide, 0.5 proud of the 2 mm -Y wall
fin = Part.makeBox(40, 30, 20).cut(Part.makeBox(36, 26, 20, V(2, 2, 2)))
fin = fin.fuse(Part.makeBox(0.5, 0.5, 6, V(15, -0.5, 8))).removeSplitter()
out["fin_exact"] = G.wall_exact(fin, (15, -0.25, 11), (1, 0, 0))
out["fin_detail"] = G.wall_is_detail(fin, (15, -0.25, 11), (1, 0, 0), 0.5)
w = {"parts": [{"label": "Fin", "mm": 0.5, "at": [15, -0.25, 11], "dir": [1, 0, 0]}]}
out["fin_bad"] = G.thin_wall_problems(w, {"Fin": fin})[0]
print("R270JSON=" + json.dumps(out))
'''


@unittest.skipIf(FC is None, "freecadcmd not found")
class ThinWallGate(unittest.TestCase):

    def test_walls_under_0_6_fail_exact_confirmed(self):
        r = fc_json(WALLS)
        self.assertTrue(r["0.3"]["bad"] and "0.30 mm" in r["0.3"]["bad"][0], r["0.3"])
        self.assertTrue(r["0.55"]["bad"], r["0.55"])
        # SABOTAGE: a 1.2 mm shell passes
        self.assertEqual(r["1.2"]["bad"], [])
        self.assertTrue(r["pocket"]["bad"] and "Pocketed" in r["pocket"]["bad"][0], r)
        self.assertAlmostEqual(r["exact"], 2.0, places=2)
        self.assertAlmostEqual(r["exact_thin"], 0.4, places=2)
        # a proud detail (an embossed letter's stroke) is no wall; the
        # pocketed membrane is (SABOTAGE pair)
        self.assertAlmostEqual(r["fin_exact"], 0.5, places=2)
        self.assertTrue(r["fin_detail"])
        self.assertEqual(r["fin_bad"], [])
        self.assertFalse(r["pocket_detail"])


# ------------------------------------------- (3) through-both-walls bore
BORE = r'''import Part
from FreeCAD import Vector as V
body = Part.makeBox(60, 40, 30).cut(Part.makeBox(56, 36, 28, V(2, 2, 2)))
body = body.cut(Part.makeCylinder(5, 70, V(-5, 20, 15), V(1, 0, 0)))
doc.addObject("Part::Feature", "Body").Shape = body
'''


@unittest.skipIf(FC is None, "freecadcmd not found")
class ThroughBothWallsGate(unittest.TestCase):

    def test_unintended_bore_fails_listed_one_warns(self):
        r, out = run_check(BORE, {}, "a box")
        self.assertTrue(any("goes through 2 walls" in p and "through_holes" in p
                            for p in r["problems"]), r["problems"])
        self.assertTrue(last(out).startswith("CHECK FAIL"), last(out))
        # SABOTAGE: listed as intended -> a warning, CHECK PASS
        r, out = run_check(BORE, {"through_holes": ["Body"]}, "a box")
        self.assertFalse(any("goes through 2 walls" in p for p in r["problems"]),
                         r["problems"])
        self.assertTrue(any("goes through 2 walls" in w for w in r["warnings"]))
        self.assertEqual(last(out), "CHECK PASS", r["problems"])
        # fast mode keeps the warning
        r, out = run_check(BORE, {}, "a box", env={"ATECH_PROMPT_MODE": "fast"})
        self.assertEqual(last(out), "CHECK PASS", r["problems"])
        # a 3 mm pin bore through both walls: a warning only
        r, out = run_check(BORE.replace("makeCylinder(5, 70", "makeCylinder(1.5, 70"),
                           {}, "a box")
        self.assertEqual(last(out), "CHECK PASS", r["problems"])
        self.assertTrue(any("goes through 2 walls" in w for w in r["warnings"]))


# -------------------------------------------------------- (4) screw pilots
PILOTS = r'''
import json, Part, atech_geom as G
from FreeCAD import Vector as V
def case_with(pilot):
    c = Part.makeBox(20, 20, 12).cut(Part.makeBox(16, 16, 12, V(2, 2, 2)))
    c = c.fuse(Part.makeCylinder(2.75, 7, V(10, 10, 2))).removeSplitter()
    return c.cut(Part.makeCylinder(pilot / 2.0, 7, V(10, 10, 2.5)))
screw = Part.makeCylinder(1.2, 6, V(10, 10, 3.2))          # M2.5 shank (d - 0.1)
screw = screw.fuse(Part.makeCylinder(2.3, 1.5, V(10, 10, 9.2)))
out = {}
for pd in (2.5, 2.1, 3.6, 2.9):
    rows = G.screw_pilots([{"label": "Screw_1", "shape": screw},
                           {"label": "Case", "shape": case_with(pd)}])
    out[str(pd)] = rows[0]
# a screw tip in nothing: not judged
rows = G.screw_pilots([{"label": "Screw_9", "shape": screw},
                       {"label": "Far", "shape": Part.makeBox(5, 5, 5, V(50, 50, 50))}])
out["none"] = rows[0]
print("R270JSON=" + json.dumps(out))
'''


@unittest.skipIf(FC is None, "freecadcmd not found")
class ScrewPilotGate(unittest.TestCase):

    def test_pilot_sizes(self):
        r = fc_json(PILOTS)
        self.assertEqual((r["2.5"]["verdict"], r["2.5"]["nominal_mm"], r["2.5"]["pilot_mm"]),
                         ("no bite", 2.5, 2.5), r)
        self.assertEqual(r["2.5"]["in"], "Case")
        self.assertEqual(r["2.9"]["verdict"], "no bite")        # a clearance hole
        # SABOTAGE: the thread-forming pilot and the insert pocket pass
        self.assertEqual(r["2.1"]["verdict"], "bites", r)
        self.assertEqual(r["3.6"]["verdict"], "insert", r)
        self.assertEqual(r["none"]["verdict"], "not judged", r)
        self.assertIn("2.1 mm", atech_geom.pilot_text(dict(r["2.5"])))


# --------------------------------------------- (4) board retention (lib)
RETAIN = r'''
import json, Part, atech_geom as G, atech_ports as ap, FreeCAD
from FreeCAD import Vector as V, Placement, Rotation
doc = FreeCAD.newDocument("r270")
board = ap.board_object(doc)
board.Placement = Placement(V(0, 0, 10), Rotation(V(1, 0, 0), 90))
doc.recompute()
bb = board.Mesh.BoundBox
b = {"label": board.Label, "mesh": board.Mesh}
far = Part.makeBox(bb.XLength + 20, bb.YLength + 20, 2, V(bb.XMin - 10, bb.YMin - 10, bb.ZMin - 5))
# the board's PCB underside: the lowest mesh z near the board's middle
ledge = Part.makeBox(6, bb.YLength - 10, 2, V(bb.XMin + 2, bb.YMin + 5, bb.ZMin - 2.2))
out = {"far": G.board_retention([{"label": "Floor", "shape": far}], b),
       "ledge": G.board_retention([{"label": "Floor", "shape": far},
                                   {"label": "Ledge", "shape": ledge}], b)}
print("R270JSON=" + json.dumps(out))
'''


@unittest.skipIf(FC is None or not HAVE_LIB, "freecadcmd or the Atech library not found")
class BoardRetentionGate(unittest.TestCase):

    def test_board_nothing_holds_vs_ledge(self):
        r = fc_json(RETAIN)
        self.assertFalse(r["far"]["retained"], r)
        # SABOTAGE: a ledge 0.2 mm under the board holds it
        self.assertTrue(r["ledge"]["retained"], r)
        self.assertIn("Ledge", r["ledge"]["ledge"] + r["ledge"]["above"])


# ------------------------------------------- (6) scorecard (FreeCAD python)
SCORE = r'''
import json, Part, review
from FreeCAD import Vector as V
def items(n, colours):
    return [{"label": "P%d" % i, "kind": "body", "shape": Part.makeBox(5, 5, 5, V(6 * i, 0, 0)),
             "color": colours[i % len(colours)]} for i in range(n)]
code = "cad.cut(a, b)\nfor i in range(9):\n    s = cad.text(s, 'X', at, n, 3)\ncad.groove_ring(s, 'Z', 3)\n"
thin = review.scorecard(items(5, [(1, 0, 0)]), view_colored={"P%d" % i for i in range(5)},
                        whole=[120, 80, 20], code=code)
rich = review.scorecard(items(14, [(1, 0, 0), (0, 1, 0), (0, 0, 1)]),
                        view_colored={"P%d" % i for i in range(14)},
                        face_open=[{"label": "screen_11_12", "module": "screen", "kind": "screen",
                                    "open": 40, "open_pct": 50.0, "face_mm": [37.5, 17.5],
                                    "blocked_by": "P1", "normal": [0, -1, 0]},
                                   {"label": "light_6", "module": "light", "kind": "light",
                                    "open": 0}],
                        whole=[100, 60, 50], code=code)
uncol = review.scorecard(items(14, [(1, 0, 0), (0, 1, 0), (0, 0, 1)]), view_colored=set())
print("R270JSON=" + json.dumps({"thin": thin, "rich": rich, "uncol": uncol}, default=str))
'''


@unittest.skipIf(FC is None, "freecadcmd not found")
class Scorecard(unittest.TestCase):

    def test_blockout_and_facts(self):
        r = fc_json(SCORE)
        t, k, u = r["thin"], r["rich"], r["uncol"]
        self.assertTrue(t["facts"]["blockout"])
        self.assertTrue(any(l.startswith("BLOCKOUT: this reads as a placeholder")
                            for l in t["lines"]), t["lines"])
        self.assertEqual(t["facts"]["detail_calls"], 3)        # call sites
        self.assertTrue(any("a slab" in l for l in t["lines"]), t["lines"])
        # SABOTAGE: 14 parts in 3 colours is not a blockout
        self.assertFalse(k["facts"]["blockout"], k["lines"])
        self.assertEqual(k["facts"]["sealed"], ["light_6"])
        self.assertEqual(k["facts"]["aspect"], [2.0, 1.2, 1.0])
        self.assertTrue(any("screen screen_11_12: window ~328 mm2" in l for l in k["lines"]),
                        k["lines"])
        # uncoloured parts are no material choice
        self.assertTrue(u["facts"]["blockout"])
        self.assertEqual(u["facts"]["colours"], 0)


# ------------------------------------------- the clock in a real ./check
@unittest.skipIf(FC is None, "freecadcmd not found")
class TurnClockInCheck(unittest.TestCase):

    def test_first_line_and_reminder(self):
        code = "import Part\ndoc.addObject('Part::Feature', 'B').Shape = Part.makeBox(9, 9, 9)\n"
        r, out = run_check(code, env={"ATECH_TURN_T0": str(int(time.time()) - 41 * 60)})
        lines = [ln for ln in out.splitlines() if ln.strip()]
        first = [ln for ln in lines if ln.startswith("TURN CLOCK")]
        self.assertTrue(first and re.match(r"TURN CLOCK 4[12]:\d\d$", first[0]), lines[:5])
        # R500: the clock line only - no stage reminder, printed once
        self.assertEqual(len(first), 1, first)
        self.assertNotIn("TURN CLOCK past", out)
        self.assertNotIn("STOP ADDING", out)
        self.assertEqual(r["turn_clock"], first)
        # the clock comes before anything else check.py says
        self.assertLess(out.index("TURN CLOCK"), out.index("OBJECT B"))
        # SABOTAGE: without the variable, no clock
        r, out = run_check(code, env={"ATECH_TURN_T0": ""})
        self.assertNotIn("TURN CLOCK", out)


# ------------------------------------------- (7) repeat-check pair cache
CACHED = r'''import Part
from FreeCAD import Vector as V
for i in range(%d):
    s = Part.makeSphere(6, V(i * 11.0, 0, 0))
    doc.addObject("Part::Feature", "S%%d" %% i).Shape = s
'''


@unittest.skipIf(FC is None, "freecadcmd not found")
class RepeatCheckCache(unittest.TestCase):

    def test_second_check_reuses_pairs_and_still_sees_a_change(self):
        ws = tempfile.mkdtemp(prefix="atech-r270-cache-")
        try:
            r1, _o = run_check(CACHED % 6, keep_ws=ws)
            self.assertTrue(os.path.isfile(os.path.join(ws, atech_geom.CHECK_CACHE)))
            self.assertEqual(len(r1["overlaps"]), 5)            # neighbours overlap
            r2, _o = run_check(CACHED % 6, keep_ws=ws)
            self.assertGreaterEqual(r2.get("cache_hits", 0), 5)
            self.assertEqual(r2["overlaps"], r1["overlaps"])
            # SABOTAGE: a changed body is measured again (its pair not cached)
            moved = (CACHED % 6) + "doc.getObject('S5').Shape = Part.makeSphere(6, V(80, 0, 0))\n"
            r3, _o = run_check(moved, keep_ws=ws)
            self.assertEqual(len(r3["overlaps"]), 4, r3["overlaps"])
        finally:
            shutil.rmtree(ws, ignore_errors=True)


# ------------------------------------------- round-1 replays (slow)
def r1(name):
    d = os.path.join(EVAL, name)
    sub = [os.path.join(d, x) for x in sorted(os.listdir(d))
           if os.path.isfile(os.path.join(d, x, "model.py"))] if os.path.isdir(d) else []
    return sub[0] if sub else None


def replay(case, src, request):
    """./check of a round-1 model.py; skips when it no longer BUILDS under
    the current kit (a kit change since round 1 - not this gate's verdict)."""
    with open(os.path.join(src, "model.py"), encoding="utf-8") as fh:
        code = fh.read()
    intent = None
    if os.path.isfile(os.path.join(src, "intent.json")):
        with open(os.path.join(src, "intent.json"), encoding="utf-8") as fh:
            intent = json.load(fh)
    r, out = run_check(code, intent, request)
    if r.get("error"):
        case.skipTest("round-1 model.py no longer builds under this kit: %s"
                      % str(r["error"]).strip().splitlines()[-1][:200])
    return r, out


@unittest.skipIf(FC is None or not HAVE_LIB, "freecadcmd or the Atech library not found")
class Round1Replays(unittest.TestCase):

    @unittest.skipIf(r1("r1_showcasetoycar_showcase_1") is None, "no round-1 toy car")
    def test_toy_car_now_fails(self):
        r, out = replay(self, r1("r1_showcasetoycar_showcase_1"), "a toy car")
        self.assertTrue(last(out).startswith("CHECK FAIL"), last(out))
        probs = r["problems"]
        for lab in ("light_6", "light_14", "distance_sensor_8", "button_2", "usbc_p7"):
            self.assertTrue(any(p.startswith(lab + " (a ") and "sealed in" in p
                                for p in probs), (lab, probs))
        # the 0.28 mm wall: MEASURED on the round-1 kit (0.27 exact); a later
        # kit may build that body differently, so here: whatever thin spot
        # the probe confirms under 0.6 mm (and is no proud detail) fails
        thin = [t for t in (r.get("walls") or {}).get("thin") or () if not t["detail"]]
        for t in thin:
            self.assertTrue(any(p.startswith("%s: a wall only %.2f mm" % (
                t["label"], t["exact_mm"])) for p in probs), (t, probs))
        self.assertTrue(any("goes through 2 walls" in p for p in probs), probs)

    @unittest.skipIf(r1("r1_deskrobot_showcase_1") is None, "no round-1 desk robot")
    def test_desk_robot_fails_on_its_sealed_screen(self):
        r, out = replay(self, r1("r1_deskrobot_showcase_1"), "a little desk robot")
        self.assertTrue(any(p.startswith("screen_11_12 (a screen) is sealed in")
                            for p in r["problems"]), r["problems"])


if __name__ == "__main__":
    unittest.main()
