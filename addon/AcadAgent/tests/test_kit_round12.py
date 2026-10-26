"""WS-KIT-CHECKS round 12: checker gaps that let bad products pass, and the
eval harness bugs (showcase baseline, 2026-10-19).

  R240  face_open probes each module along ITS OWN working face in world
        (the library's measured frame rotated by the module's placement),
        not the board's normal. A cabled distance_sensor facing -Y behind a
        window in the front wall read 0 of 169 rays along +Z ("sealed in",
        the correct design FAILED); a DC motor is probed along its shaft.
  R241  every Atech module must be inside the product's body: rays from
        its mesh points along its six axes against the designed parts. A
        module outside the body, sticking out of it, or against an open
        side fails; its working face may look out through an opening,
        flush with it; a motor shaft / USB-C shell standing proud of the
        module's case is left out (it goes through the wall by design).
        The old box test (module inside the union BOX of all parts, only
        when the board is) passed a speaker poking through a side wall and
        a sensor outside the front wall, once another part widened the box.
        The baseline smart_speaker (docs/verification/eval/
        showcasebase_showcase_1/smart_speaker) was re-measured: its speaker
        IS inside the case (x 40.6..80.6 in a case to 83.6); the "outside"
        in full_render.png's cutaway is the oblique view of a module 20.2
        mm tall over a board whose case wall was clipped away.
  R242  the headless ViewObject recorder: a call on the right-hand side,
        Transparency / LineColor / DiffuseColor, chained targets, and any
        other X.ViewObject (a stand-in that records, is truthy, reads back
        and takes hide()/show()).
  R243  run_eval: "cd <ws> && ./check ..." counts as a check call; --tag
        takes underscores; TURN_TIMEOUT_S 3600, FC_TIMEOUT_S 600;
        MAX_FIX_ATTEMPTS is the panel's (read from its source, no Qt), else
        5. fc_build's no_overlap fitness honours model.py INTENDED_OVERLAPS
        as ./check does (never a pair with a seed object).
  R250  face_open (the OPEN probe) stops failing correct designs: a part
        with view Transparency >= 30 passes the rays of an optical module
        (light, screen, distance_sensor) - never a button, speaker,
        microphone or USB-C; intent.json "covers" {part: module | [modules]}
        lets a key cap / lens / light pipe stand in front of that module
        only, and ./check FAILS a declared cover that no ray from the face
        meets within 3 mm, or that names no part / no module; a planar face
        with more than TESS_LOOPS_MAX holes (a grille) is cast against
        exactly (even-odd point-in-face), in face_open AND enclosure (a
        one-piece case with a grille read every module "OUTSIDE"); a face
        sealed on the 13 x 13 grid is re-cast 41 x 41 (a pin-hole grille);
        the sealed-in line names a part within 3 mm as a "covers" fix.
        MAX_PAIRS_OBJECTS 30 -> 120.

SABOTAGE (each gate broken in the code, its tests watched failing, then
restored - 2026-10-19; R250 2026-10-20):
  R250  clear = set() (no see-through): test_good_panel_passes failed;
        see-through for every module: test_glass_does_not_open_a_button
        failed; a valid cover not added to the rays' pass list:
        test_good_panel_passes failed; the 3 mm gap test off:
        test_cover_not_in_front_fails and test_cover_for_one_module_only
        failed; covers_unmatched dropped from face_open_problems:
        test_cover_naming_nothing_fails failed; _tess_holed raising
        SlowToTessellate: both grille tests failed; the 41 x 41 re-cast
        off: test_pin_hole_between_the_coarse_rays failed; enclosure
        leaving the holed Case out (pre-R250): test_grille_over_the_
        speaker_is_judged failed (enclosure lines); the hint's back cast
        off: test_undeclared_cap_seals_and_names_the_fix failed.
  R240  face_open with `wd = None` forced (the board-normal path): the
        cabled-sensor test failed (normal [0, 0, 1], 0 rays open, CHECK
        FAIL "sealed in") and the motor-shaft test failed (face "top").
  R241  enclosure_problems returning []: the poke / outside / open-side
        tests failed (no enclosure line; the box test stays silent);
        _proud_split returning (None, None): the shaft-through-the-wall
        car failed ("dc_motor_p1 sticks out of the product's body").
  R242  visit_Attribute disabled: the stand-in tests failed (AttributeError
        on None); the multi-target branch removed: the chained test failed.
  R243  _CHECK_SEG reverted to "startswith ./check": the cd-form test failed;
        overlaps() ignoring `intended`: the INTENDED_OVERLAPS fitness test
        failed (no_overlap False).

Runs under SYSTEM python; every FreeCAD step is a freecadcmd child, one at
a time (repo rule). FreeCAD-backed classes skip without freecadcmd
(ATECH_REQUIRE_FREECADCMD=1 makes that a failure, as test_agent_kit).

RUN:
    cd addon/AcadAgent/tests && python3 -m unittest test_kit_round12 -v
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
EVAL = os.path.join(HERE, "eval")
if EVAL not in sys.path:
    sys.path.insert(0, EVAL)

import test_agent_kit as tak  # noqa: E402

FC, KIT, PROJECTS = tak.FC, tak.KIT, tak.PROJECTS
REPO = os.path.normpath(os.path.join(tak.ADDON, "..", ".."))
BASE = os.path.join(REPO, "docs", "verification", "eval", "showcasebase_showcase_1")
if KIT not in sys.path:
    sys.path.insert(0, KIT)

import atech_geom  # noqa: E402  (plain python: the AST rewrite needs no FreeCAD)
import run_eval as R  # noqa: E402

REQUEST = "a robot car with a distance sensor and a light"


def check(code, intent=None, request=None):
    """./check on model.py `code` (Atech library on the path) with
    intent.json `intent` and Studio's turn file carrying `request`."""
    ws = tempfile.mkdtemp(prefix="atech-r12-")
    try:
        with open(os.path.join(ws, "model.py"), "w", encoding="utf-8") as fh:
            fh.write(code)
        if intent is not None:
            with open(os.path.join(ws, "intent.json"), "w", encoding="utf-8") as fh:
                json.dump(intent, fh)
        if request is not None:
            with open(os.path.join(ws, ".atech_turn.json"), "w", encoding="utf-8") as fh:
                json.dump({"fix": False, "request": request}, fh)
        env = {"ATECH_CHECK_SCRIPT": os.path.join(ws, "model.py"), "ATECH_CHECK_PNG": "",
               "ATECH_CHECK_PATH": PROJECTS}
        out = tak.fc(os.path.join(KIT, "check.py"), env)
        r = tak.check_json(out)
        r["_last"] = [ln for ln in out.splitlines() if ln.startswith("CHECK ")][-1:]
        return r
    finally:
        shutil.rmtree(ws, ignore_errors=True)


# A car-like product, board FLAT (modules face +Z): USB-C on port 7 (mouth
# +Y), a light on 6, the speaker on (11, 12), a DC motor on 1 (shaft -X,
# through a hole in the -X wall), and a distance sensor CABLED to port 8 at
# the nose facing -Y (r5.md recipe 6.1). A Floor under the board and a Case
# over everything (fitted after the modules) with an opening in front of
# every working face.
CAR = r'''import Part
import atech_ports as ap
from FreeCAD import Vector, Placement, Rotation
SENSOR_WIN = "%(win)s"      # front | top
CASE_Y0 = %(y0)s            # the case's front (outer) y: -139.2 holds the sensor
X1 = %(x1)s                 # the case's +X (outer) x: 83.6 holds the speaker
PLUS_X_WALL = %(xwall)s     # False: the case is open at +X
BUMPER = "%(bumper)s"       # "" | "x" | "y": a bar beyond the case at +X / -Y
L = 5.46
board = ap.board_object(doc)
board.Placement = Placement(Vector(0, 0, L), Rotation(Vector(1, 0, 0), 90))
usb = ap.seat(doc, "usbc", 7)
lamp = ap.seat(doc, "light", 6)
spk = ap.seat(doc, "speaker", (11, 12))
mot = ap.seat(doc, "dc_motor", 1)
eye, rib = ap.cable(doc, "distance_sensor", 8, ap.module_placement(
    "distance_sensor", (30, -131.4, L + 30), face="-Y", cable="-Z"))
W, ROOF = 2.0, 48.2
x0, y1, z0 = -23.4, 3.6, 0.0
outer = Part.makeBox(X1 - x0, y1 - CASE_Y0, ROOF - z0, Vector(x0, CASE_Y0, z0))
inner = Part.makeBox(X1 - x0 - 2 * W + (0 if PLUS_X_WALL else 3 * W),
                     y1 - CASE_Y0 - 2 * W, ROOF - z0 - W, Vector(x0 + W, CASE_Y0 + W, z0))
case = outer.cut(inner).cut(Part.makeBox(X1 - x0, y1 - CASE_Y0, W, Vector(x0, CASE_Y0, z0)))
floor = Part.makeBox(X1 - x0 - 2 * W - 0.2, y1 - CASE_Y0 - 2 * W - 0.2, W,
                     Vector(x0 + W + 0.1, CASE_Y0 + W + 0.1, z0))
cuts = []
lb, sb, ub, eb = ap.bbox(lamp), ap.bbox(spk), ap.bbox(usb), ap.bbox(eye)
cuts.append(Part.makeBox(17, 17, 10, Vector(lb.Center.x - 8.5, lb.Center.y - 8.5, ROOF - 5)))
cuts.append(Part.makeCylinder(17, 10, Vector(sb.Center.x, sb.Center.y, ROOF - 5)))
cuts.append(Part.makeBox(13, 10, 7, Vector(ub.Center.x - 6.5, y1 - 5, ub.Center.z - 3.5)))
if SENSOR_WIN == "front":
    cuts.append(Part.makeBox(12, 10, 8, Vector(eb.Center.x - 6, CASE_Y0 - 1, eb.Center.z - 4)))
else:
    cuts.append(Part.makeBox(12, 8, 10, Vector(eb.Center.x - 6, eb.Center.y - 4, ROOF - 5)))
if CASE_Y0 > eb.YMin:       # the sensor left outside: a slot for its ribbon
    cuts.append(Part.makeBox(18, 10, 42, Vector(eb.Center.x - 9, CASE_Y0 - 1, 1)))
if X1 < sb.XMax:            # the speaker through a hole in the +X wall
    cuts.append(Part.makeBox(10, sb.YLength + 0.4, sb.ZLength + 0.4,
                             Vector(X1 - 5, sb.YMin - 0.2, sb.ZMin - 0.2)))
shaft = [p for p in mot.Mesh.Points if p.x < -20.6]
cy = sum(p.y for p in shaft) / len(shaft)
cz = sum(p.z for p in shaft) / len(shaft)
cuts.append(Part.makeCylinder(3.0, 10, Vector(x0 - 5, cy, cz), Vector(1, 0, 0)))
for c in cuts:
    case = case.cut(c)
# R270: posts from the floor to 0.1 mm under the board hold it (quality
# ./check: "nothing holds the board")
_pb = ap.bbox(board)
floor = floor.fuse([Part.makeBox(3, 3, _pb.ZMin - 0.1 - W + 0.5,
                                 Vector(_pb.XMin + fx * _pb.XLength - 1.5,
                                        _pb.YMin + fy * _pb.YLength - 1.5, W - 0.5))
                    for fx in (0.3, 0.7) for fy in (0.3, 0.7)]).removeSplitter()
doc.addObject("Part::Feature", "Case").Shape = case
doc.addObject("Part::Feature", "Floor").Shape = floor
if BUMPER == "x":
    doc.addObject("Part::Feature", "Bumper").Shape = Part.makeBox(
        2, y1 - CASE_Y0, 10, Vector(sb.XMax + 1.5, CASE_Y0, 0))
elif BUMPER == "y":
    doc.addObject("Part::Feature", "Bumper").Shape = Part.makeBox(
        X1 - x0, 2, 30, Vector(x0, eb.YMin - 3.5, 0))
%(extra)s
'''
GOOD = dict(win="front", y0=-139.2, x1=83.6, xwall=True, bumper="", extra="")
INTENT = {"fitted_after": ["Case"]}
_RUNS = {}
TIMES = {}


def car(**over):
    """./check of the CAR fixture with `over` changed (cached per variant)."""
    v = dict(GOOD, **over)
    key = tuple(sorted(v.items()))
    if key not in _RUNS:
        _RUNS[key] = check(CAR % v, INTENT, REQUEST)
    return _RUNS[key]


def passes_but_fastening(r):
    """R500: the problems other than R441 fastening / R442 holder lines
    ([] = the fixture would CHECK PASS but for those two gates)."""
    return [p for p in r.get("problems") or () if not p.startswith(("fastening: ", "holder: "))]


def row(r, label, key="face_open"):
    src = r.get(key) if key == "face_open" else (r.get("atech_layout") or {}).get(key)
    hit = [x for x in src or [] if x["label"] == label]
    return hit[0] if hit else None


def enclosure_lines(r, label=None):
    return [p for p in r.get("problems") or []
            if ("sticks out of the product" in p or "is OUTSIDE the product" in p
                or "is not enclosed on its" in p)
            and (label is None or p.startswith(label + " "))]


def box_lines(r, label):
    return [p for p in r.get("problems") or []
            if p.startswith(label + " sticks ") and " mm out of the case on " in p]


# ----------------------------------------------------------------- R240
@unittest.skipIf(FC is None, "freecadcmd not found")
class R240WorkingFaceInWorld(unittest.TestCase):

    def test_cabled_sensor_probed_along_its_own_face(self):
        r = car()
        # R500: this fixture is about the working face; its Floor / Case
        # pair is left unfastened (R441 / R442: test_check_gates_r280)
        self.assertEqual(passes_but_fastening(r), [], r.get("problems"))
        s = row(r, "distance_sensor_8")
        self.assertEqual(s["normal"], [0.0, -1.0, 0.0], s)
        self.assertGreater(s["open"], 0, s)
        # a seated module still faces the board's normal (+Z when FLAT)
        self.assertEqual(row(r, "light_p6")["normal"], [0.0, 0.0, 1.0])
        self.assertEqual(row(r, "usbc_p7")["normal"], [0.0, 1.0, 0.0])
        TIMES["R240 face_open (s)"] = r.get("face_open_seconds")

    def test_window_on_the_wrong_side_is_sealed(self):
        r = car(win="top")
        self.assertTrue(r["_last"][0].startswith("CHECK FAIL"), r["_last"])
        bad = r.get("face_open_problems") or []
        self.assertTrue(any(p.startswith("distance_sensor_8 (a sensor) is sealed in")
                            and "(-Y)" in p for p in bad), bad)
        self.assertEqual(row(r, "distance_sensor_8")["open"], 0)

    def test_dc_motor_probed_along_its_shaft(self):
        r = car()
        m = row(r, "dc_motor_p1")
        self.assertEqual(m["face"], "shaft", m)
        self.assertEqual(m["normal"], [-1.0, 0.0, 0.0], m)
        self.assertIsNone(m["kind"])                    # reported, never judged
        # R241: the shaft standing out of the case through its hole is no
        # "sticks out of the case" (MEASURED before: "dc_motor_p1 sticks
        # 5.8 mm out of the case on -x")
        self.assertEqual(box_lines(r, "dc_motor_p1"), [])
        self.assertEqual(enclosure_lines(r, "dc_motor_p1"), [])


# ----------------------------------------------------------------- R241
@unittest.skipIf(FC is None, "freecadcmd not found")
class R241ModulesInsideTheBody(unittest.TestCase):

    def test_enclosed_car_passes(self):
        r = car()
        rows = (r.get("atech_layout") or {}).get("enclosure") or []
        self.assertEqual(len(rows), 5, rows)
        for e in rows:
            self.assertEqual(e["outside"], 0, e)
            self.assertTrue(all(v < atech_geom.ENCLOSE_SIDE_PCT
                                for v in e["side_pct"].values()), e)
        self.assertEqual(enclosure_lines(r), [])

    def test_speaker_poking_through_a_side_wall_fails(self):
        # a bumper beyond the speaker widens the parts' box: the box test is
        # blind to it (the R241 defect), the body test is not
        r = car(x1=70, bumper="x")
        self.assertEqual(box_lines(r, "speaker_p11_12"), [])
        got = enclosure_lines(r, "speaker_p11_12")
        self.assertTrue(got and "sticks out of the product's body" in got[0], r["problems"])
        self.assertIn("+X", got[0])
        self.assertTrue(r["_last"][0].startswith("CHECK FAIL"))

    def test_sensor_outside_the_front_wall_fails(self):
        r = car(y0=-125, bumper="y")
        self.assertEqual(box_lines(r, "distance_sensor_8"), [])
        got = enclosure_lines(r, "distance_sensor_8")
        self.assertTrue(got and "is OUTSIDE the product" in got[0], r["problems"])

    def test_open_side_fails(self):
        r = car(xwall=False)
        got = enclosure_lines(r, "speaker_p11_12")
        self.assertTrue(got and "is not enclosed on its +X side" in got[0], r["problems"])

    def test_intended_overlaps_does_not_excuse_it(self):
        r = car(x1=70, bumper="x",
                extra='INTENDED_OVERLAPS = ["speaker_p11_12", "distance_sensor_8"]')
        self.assertTrue(enclosure_lines(r, "speaker_p11_12"), r["problems"])

    def test_baseline_smart_speaker_is_inside(self):
        src = os.path.join(BASE, "smart_speaker", "model.py")
        if not os.path.isfile(src):
            self.skipTest("baseline smart_speaker not in the tree")
        with open(src, encoding="utf-8") as fh:
            code = fh.read()
        with open(os.path.join(BASE, "smart_speaker", "intent.json"), encoding="utf-8") as fh:
            intent = json.load(fh)
        r = check(code, intent, "a smart speaker")
        e = row(r, "speaker_p9_10", "enclosure")
        self.assertIsNotNone(e, r.get("atech_layout"))
        self.assertEqual(e["outside"], 0, e)
        self.assertEqual(enclosure_lines(r), [])
        TIMES["R241 smart_speaker geometry (s)"] = r.get("geometry_seconds")


# ----------------------------------------------------------------- R242
class _Obj(object):
    ViewObject = None

    def __init__(self, name):
        self.Name = name


def _recorded(code):
    store, counts = {}, {}
    tree = atech_geom.record_view(code, counts)
    env = {atech_geom.VIEW_FN: atech_geom.view_recorder(store), "O": _Obj,
           "color": lambda n: {"rubber": (0.1, 0.1, 0.12)}[n]}
    exec(compile(tree, "model.py", "exec"), env)        # noqa: S102
    return store, counts, env


class R242ViewRecorder(unittest.TestCase):

    def test_call_on_the_right_hand_side(self):
        store, counts, _e = _recorded(
            'o = O("Tyre")\no.ViewObject.ShapeColor = color("rubber")\n')
        self.assertEqual(store["Tyre"]["ShapeColor"], [0.1, 0.1, 0.12])
        self.assertEqual(counts["rewritten"], 1)

    def test_transparency_line_and_diffuse_colour(self):
        store, _c, _e = _recorded(
            'o = O("Lens")\n'
            'o.ViewObject.Transparency = 60\n'
            'o.ViewObject.LineColor = (0.0, 0.0, 0.0)\n'
            'o.ViewObject.DiffuseColor = [(1.0, 0.0, 0.0)] * 2\n')
        self.assertEqual(store["Lens"], {"Transparency": 60, "LineColor": [0.0, 0.0, 0.0],
                                         "DiffuseColor": [[1.0, 0.0, 0.0]] * 2})

    def test_chained_targets(self):
        store, _c, env = _recorded(
            'a, b = O("A"), O("B")\n'
            'x = a.ViewObject.ShapeColor = b.ViewObject.ShapeColor = color("rubber")\n')
        self.assertEqual(store["A"]["ShapeColor"], [0.1, 0.1, 0.12])
        self.assertEqual(store["B"]["ShapeColor"], [0.1, 0.1, 0.12])
        self.assertEqual(env["x"], (0.1, 0.1, 0.12))

    def test_stand_in_view_object(self):
        store, _c, env = _recorded(
            'o = O("Body")\n'
            'if o.ViewObject:\n'
            '    o.ViewObject.LineWidth = 3\n'
            'vo = o.ViewObject\n'
            'vo.Transparency = 20\n'
            'o.ViewObject.hide()\n'
            'o.ViewObject.Proxy = 0\n'
            'o.ViewObject.Anything.goes()\n'
            'back = o.ViewObject.Transparency\n'
            'dflt = O("Other").ViewObject.ShapeColor\n')
        self.assertEqual(store["Body"], {"LineWidth": 3, "Transparency": 20,
                                         "Visibility": False})
        self.assertEqual(env["back"], 20)
        self.assertEqual(env["dflt"], atech_geom.VIEW_DEFAULTS["ShapeColor"])

    def test_real_view_object_is_used_when_there_is_one(self):
        class Real(object):
            pass
        store = {}
        rec = atech_geom.view_recorder(store)
        o = _Obj("X")
        o.ViewObject = Real()
        self.assertIs(rec(o), o.ViewObject)

    def test_line_numbers_stay_the_agents(self):
        tree = atech_geom.record_view('a = 1\nb = O("B")\nb.ViewObject.ShapeColor = '
                                      '(1, 0, 0)\nraise ValueError("x")\n')
        try:
            exec(compile(tree, "model.py", "exec"),     # noqa: S102
                 {atech_geom.VIEW_FN: atech_geom.view_recorder({}), "O": _Obj})
        except ValueError as exc:
            self.assertEqual(exc.__traceback__.tb_next.tb_lineno, 4)


@unittest.skipIf(FC is None, "freecadcmd not found")
class R242ViewRecordedByCheck(unittest.TestCase):

    def test_check_records_a_called_colour(self):
        r = check('import Part\n'
                  'def color(n):\n'
                  '    return {"rubber": (0.1, 0.1, 0.12)}[n]\n'
                  'o = doc.addObject("Part::Feature", "Tyre")\n'
                  'o.Shape = Part.makeCylinder(10, 5)\n'
                  'o.ViewObject.ShapeColor = color("rubber")\n'
                  'o.ViewObject.Transparency = 30\n'
                  'if o.ViewObject is not None:\n'
                  '    o.ViewObject.LineColor = (0.0, 0.0, 0.0)\n')
        self.assertTrue(r["ok"], r.get("error"))
        v = r["objects"][0].get("view") or {}
        self.assertEqual(v.get("ShapeColor"), [0.1, 0.1, 0.12], r["objects"])
        self.assertEqual(v.get("Transparency"), 30)
        self.assertEqual(v.get("LineColor"), [0.0, 0.0, 0.0])


# ----------------------------------------------------------------- R243
class R243Harness(unittest.TestCase):

    def test_check_call_forms(self):
        yes = ["./check", "./check 2>&1 | tail -40",
               'cd /tmp/ws && ./check 2>&1 | grep -E "PROBLEM|CHECK"',
               "cd /tmp/ws && /tmp/ws/check", "sed -i s/a/b/ model.py && ./check",
               "echo go; ./check"]
        no = ["cat ./check", "grep check model.py", "./checker", "check",
              "python3 check.py", "ls", ""]
        for c in yes:
            self.assertTrue(R._is_check_call("Bash", {"command": c}), c)
        for c in no:
            self.assertFalse(R._is_check_call("Bash", {"command": c}), c)
        self.assertFalse(R._is_check_call("Read", {"command": "./check"}))

    def test_tag_takes_underscores(self):
        self.assertTrue(R.TAG_RE.match("showcase_base"))
        self.assertTrue(R.TAG_RE.match("baseline"))
        for bad in ("Showcase", "a_1", "_a", "a__b", "a-b"):
            self.assertFalse(R.TAG_RE.match(bad), bad)
        self.assertEqual(R.resolve_run("showcase_base_showcase_3"),
                         ("showcase_base_showcase_3", "showcase_base_showcase", 3))
        self.assertEqual(R.resolve_run("baseline_extra_2"),
                         ("baseline_extra_2", "baseline_extra", 2))
        self.assertEqual(R.resolve_run("4", "round"), ("round_4", "round", 4))

    def test_timeouts(self):
        self.assertEqual(R.TURN_TIMEOUT_S, 3600)
        self.assertEqual(R.FC_TIMEOUT_S, 600)

    def test_max_fix_attempts_is_the_panels(self):
        d = tempfile.mkdtemp(prefix="atech-r12-panel-")
        try:
            p = os.path.join(d, "panel.py")

            def cap(src, env=None):
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(src)
                return R._panel_max_fix(environ=env or {}, path=p)
            self.assertEqual(cap("class AgentPanel(object):\n    MAX_FIX_ATTEMPTS = 3\n"), 3)
            two = ("class AgentPanel(object):\n"
                   "    FAST_MAX_FIX_ATTEMPTS, QUALITY_MAX_FIX_ATTEMPTS = 2, 7\n")
            self.assertEqual(cap(two), 7)
            self.assertEqual(cap(two, {"ATECH_PROMPT_MODE": "fast"}), 2)
            self.assertEqual(cap("class Other(object):\n    MAX_FIX_ATTEMPTS = 3\n"), 5)
            self.assertEqual(cap("this is not python ("), 5)
            self.assertEqual(R._panel_max_fix(path=os.path.join(d, "missing.py")), 5)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        # the shipped panel's own value (its source, read without Qt)
        self.assertIsInstance(R.MAX_FIX_ATTEMPTS, int)
        self.assertGreaterEqual(R.MAX_FIX_ATTEMPTS, 2)

    def test_showcase_prompts(self):
        with open(os.path.join(EVAL, R.PROMPT_SETS["showcase"]), encoding="utf-8") as fh:
            items = {i["id"]: i for i in json.load(fh)["prompts"]}
        want = {"rc_tank": "an RC tank", "bedside_lamp": "a bedside lamp",
                "alarm_clock": "an alarm clock", "weather_station": "a weather station",
                "desk_fan": "a small desk fan"}
        for k, v in want.items():
            self.assertEqual(items[k]["prompt"], v)
            self.assertTrue(items[k]["expect"]["atech_check"])
        # ids are unique across every set (load_expectations keys on them:
        # the showcase toy car used to replace the core set's toy_car)
        ids = []
        for f in R.PROMPT_SETS.values():
            with open(os.path.join(EVAL, f), encoding="utf-8") as fh:
                ids += [i["id"] for i in json.load(fh)["prompts"]]
        self.assertEqual(len(ids), len(set(ids)), sorted(ids))


OVERLAP_PAIR = ("import Part\nfrom FreeCAD import Vector\n"
                "doc.addObject('Part::Feature', 'Body').Shape = Part.makeBox(20, 20, 20)\n"
                "doc.addObject('Part::Feature', 'Glass').Shape = "
                "Part.makeBox(10, 10, 10, Vector(15, 5, 5))\n"
                "%s\n")


@unittest.skipIf(FC is None, "freecadcmd not found")
class R243FitnessHonoursIntendedOverlaps(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._fc = R.FREECADCMD
        R.FREECADCMD = FC

    @classmethod
    def tearDownClass(cls):
        R.FREECADCMD = cls._fc

    def _build(self, code, seed=None):
        ws = tempfile.mkdtemp(prefix="atech-r12-fit-")
        try:
            with open(os.path.join(ws, "model.py"), "w", encoding="utf-8") as fh:
                fh.write(code)
            b, crash = R.fc_job({"mode": "build", "workspace": ws, "expect": None,
                                 "prompt": "", "seed": seed, "render": None})
            self.assertIsNotNone(b, crash)
            return [c for c in b["fitness"] if c["check"] == "no_overlap"][0]
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_declared_pair_passes_undeclared_fails(self):
        bad = self._build(OVERLAP_PAIR % "")
        self.assertFalse(bad["pass"], bad)
        ok = self._build(OVERLAP_PAIR % 'INTENDED_OVERLAPS = [("Glass", "Body")]')
        self.assertTrue(ok["pass"], ok)
        self.assertEqual(sorted(ok["detail"]["excused_by_intended"][0]["pair"]),
                         ["Body", "Glass"])
        single = self._build(OVERLAP_PAIR % 'INTENDED_OVERLAPS = []\n'
                             'INTENDED_OVERLAPS += ["Glass"]')
        self.assertTrue(single["pass"], single)
        other = self._build(OVERLAP_PAIR % 'INTENDED_OVERLAPS = [("Glass", "Lid")]')
        self.assertFalse(other["pass"], other)
        computed = self._build(OVERLAP_PAIR % 'INTENDED_OVERLAPS = [("Glass", "Bo" + "dy")]')
        self.assertFalse(computed["pass"], computed)
        self.assertIn("not a literal", computed["detail"]["intended_note"])

    def test_never_a_pair_with_a_seed(self):
        code = ("import Part\nfrom FreeCAD import Vector\n"
                "doc.addObject('Part::Feature', 'Stand').Shape = "
                "Part.makeBox(60, 60, 20, Vector(-30, -30, -10))\n"
                "INTENDED_OVERLAPS = [('Stand', 'Clock_Enclosure'), 'Stand']\n")
        ov = self._build(code, seed=os.path.join(EVAL, "seeds", "clock_enclosure.py"))
        self.assertFalse(ov["pass"], ov)


# ----------------------------------------------------------------- R250
# A flat board under one closed Case (roof 28..30): a light on 6 under a
# 12 x 12 roof window, a button on 3 under a 10 mm hole, the speaker on
# (11, 12) under the roof. Variants: LENS_T the Transparency of the Lens
# filling the light's window; BTN "cap" (a key Cap resting 0.1 mm over the
# button, through the hole) | "glass" (a Window disc, Transparency 60,
# filling the hole); GRILLE "over" (169 holes - one face of 170+ loops,
# beyond TESS_LOOPS_MAX - over the speaker) | "off" (the same holes beside
# it) | "pin" (one 1.2 mm hole between the 13 x 13 rays).
PANEL = r"""import Part
import atech_ports as ap
from FreeCAD import Vector, Placement, Rotation
LENS_T, BTN, GRILLE = %(lens_t)s, "%(btn)s", "%(grille)s"
L = 5.46
board = ap.board_object(doc)
board.Placement = Placement(Vector(0, 0, L), Rotation(Vector(1, 0, 0), 90))
lamp = ap.seat(doc, "light", 6)
btn = ap.seat(doc, "button", 3)
spk = ap.seat(doc, "speaker", (11, 12))
lb, kb, sb = ap.bbox(lamp), ap.bbox(btn), ap.bbox(spk)
x0, y0, x1, y1, W, ROOF = -4.0, -124.0, 84.0, 4.0, 2.0, 30.0
case = Part.makeBox(x1 - x0, y1 - y0, ROOF, Vector(x0, y0, 0)).cut(
    Part.makeBox(x1 - x0 - 2 * W, y1 - y0 - 2 * W, ROOF - W + 1, Vector(x0 + W, y0 + W, -1)))
floor = Part.makeBox(x1 - x0 - 2 * W - 0.2, y1 - y0 - 2 * W - 0.2, W,
                     Vector(x0 + W + 0.1, y0 + W + 0.1, 0))
win = Part.makeBox(12, 12, 4, Vector(lb.Center.x - 6, lb.Center.y - 6, ROOF - 3))
hole = Part.makeCylinder(5, 4, Vector(kb.Center.x, kb.Center.y, ROOF - 3))
cuts = [win, hole]
if GRILLE in ("over", "off"):
    gx, gy = (sb.Center.x, sb.Center.y) if GRILLE == "over" else (22.0, -80.0)
    cuts += [Part.makeCylinder(0.8, 4, Vector(gx + 2.6 * (i - 6), gy + 2.6 * (j - 6), ROOF - 3))
             for i in range(13) for j in range(13)]
elif GRILLE == "pin":
    step = (sb.XLength - 2.0) / 12.0
    cuts.append(Part.makeCylinder(0.6, 4, Vector(sb.XMin + 1 + step / 2,
                                                 sb.YMin + 1 + step / 2, ROOF - 3)))
case = case.cut(Part.makeCompound(cuts))
# R270: posts from the floor to 0.1 mm under the board hold it (quality
# ./check: "nothing holds the board")
_pb = ap.bbox(board)
floor = floor.fuse([Part.makeBox(3, 3, _pb.ZMin - 0.1 - W + 0.5,
                                 Vector(_pb.XMin + fx * _pb.XLength - 1.5,
                                        _pb.YMin + fy * _pb.YLength - 1.5, W - 0.5))
                    for fx in (0.3, 0.7) for fy in (0.3, 0.7)]).removeSplitter()
doc.addObject("Part::Feature", "Case").Shape = case
doc.addObject("Part::Feature", "Floor").Shape = floor
lens = doc.addObject("Part::Feature", "Lens")
lens.Shape = Part.makeBox(12, 12, W, Vector(lb.Center.x - 6, lb.Center.y - 6, ROOF - W))
lens.ViewObject.Transparency = LENS_T
if BTN == "cap":
    cap = Part.makeCylinder(7, ROOF - W - 0.1 - (kb.ZMax + 0.1),
                            Vector(kb.Center.x, kb.Center.y, kb.ZMax + 0.1))
    cap = cap.fuse(Part.makeCylinder(4.8, 4, Vector(kb.Center.x, kb.Center.y, ROOF - W - 0.5)))
    doc.addObject("Part::Feature", "Cap").Shape = cap.removeSplitter()
else:
    w = doc.addObject("Part::Feature", "Window")
    w.Shape = Part.makeCylinder(5, W, Vector(kb.Center.x, kb.Center.y, ROOF - W))
    w.ViewObject.Transparency = 60
"""
PANEL_GOOD = dict(lens_t=60, btn="cap", grille="over")
PANEL_REQUEST = "a speaker box with a light and a button"
_PANEL_RUNS = {}


def panel(covers=None, **over):
    """./check of the PANEL fixture (cached per variant)."""
    v = dict(PANEL_GOOD, **over)
    key = (tuple(sorted(v.items())), json.dumps(covers, sort_keys=True))
    if key not in _PANEL_RUNS:
        intent = {"fitted_after": ["Case"]}
        if covers is not None:
            intent["covers"] = covers
        _PANEL_RUNS[key] = check(PANEL % v, intent, PANEL_REQUEST)
    return _PANEL_RUNS[key]


def sealed(r, label):
    return [p for p in r.get("problems") or [] if p.startswith(label + " (a ")
            and " is sealed in" in p]


def cover_lines(r):
    return [p for p in r.get("problems") or [] if '"covers"' in p
            and " is sealed in" not in p]


class R250CoversUnit(unittest.TestCase):
    """Plain python: the intent.json "covers" reader and the view lookup."""

    def test_sanitize_covers(self):
        self.assertEqual(atech_geom.sanitize_covers(None), ({}, []))
        got, bad = atech_geom.sanitize_covers({"Cap_Plus": "button_p2",
                                               "Ring": ["light_p1", "light_p6"]})
        self.assertEqual(got, {"Cap_Plus": ["button_p2"], "Ring": ["light_p1", "light_p6"]})
        self.assertEqual(bad, [])
        got, bad = atech_geom.sanitize_covers({"Cap": 3, "Ok": "button_p2", "E": []})
        self.assertEqual(got, {"Ok": ["button_p2"]})
        self.assertEqual(len(bad), 2, bad)
        self.assertTrue(atech_geom.sanitize_covers(["Cap"])[1])

    def test_part_transparency_sources(self):
        pt = atech_geom.part_transparency
        self.assertEqual(pt({"label": "A", "transparency": 60}), 60)
        self.assertEqual(pt({"label": "A", "view": {"Transparency": 35}}), 35)
        self.assertEqual(pt({"label": "A"}, {"A": {"Transparency": 50}}), 50)
        self.assertEqual(pt({"label": "A"}, {"B": {"Transparency": 50}}), 0)
        self.assertEqual(pt({"label": "A"}), 0)

    def test_recorder_store_is_kept(self):
        store = {}
        atech_geom.view_recorder(store)
        self.assertIs(atech_geom._VIEW_STORE[0], store)


@unittest.skipIf(FC is None, "freecadcmd not found")
class R250FaceOpenCovers(unittest.TestCase):

    def test_good_panel_passes(self):
        r = panel({"Cap": "button_p3"})
        # R500: this fixture is about the working face; its Floor / Case
        # pair is left unfastened (R441 / R442: test_check_gates_r280)
        self.assertEqual(passes_but_fastening(r), [], r.get("problems"))
        b = row(r, "button_p3")
        self.assertGreater(b["open"], 0, b)
        self.assertEqual(b["covered_by"], ["Cap"])
        lamp = row(r, "light_p6")
        self.assertGreater(lamp["open"], 0, lamp)
        self.assertEqual(lamp["see_through"], ["Lens"])
        self.assertEqual(cover_lines(r), [])
        TIMES["R250 face_open panel (s)"] = r.get("face_open_seconds")

    def test_undeclared_cap_seals_and_names_the_fix(self):
        r = panel()
        got = sealed(r, "button_p3")
        self.assertTrue(got, r.get("problems"))
        self.assertIn('"covers": {"Cap": "button_p3"}', got[0])
        self.assertEqual(row(r, "button_p3")["open"], 0)

    def test_cover_not_in_front_fails(self):
        # the Case's roof is 12.5 mm over the button, the Lens over the light
        r = panel({"Cap": "button_p3", "Case": "button_p3", "Lens": "button_p3"})
        lines = cover_lines(r)
        self.assertTrue(any(p.startswith("Case is declared") and "12." in p
                            for p in lines), lines)
        self.assertTrue(any(p.startswith("Lens is declared") and "no ray from the face"
                            in p for p in lines), lines)
        self.assertTrue(r["_last"][0].startswith("CHECK FAIL"), r["_last"])
        self.assertEqual(row(r, "button_p3")["covered_by"], ["Cap"])

    def test_cover_naming_nothing_fails(self):
        r = panel({"Cap": "button_p9", "Ghost": "button_p3"})
        lines = cover_lines(r)
        self.assertTrue(any("button_p9, which is no Atech module" in p for p in lines), lines)
        self.assertTrue(any("names Ghost, which is no part" in p for p in lines), lines)
        self.assertTrue(r["_last"][0].startswith("CHECK FAIL"))

    def test_cover_for_one_module_only(self):
        # the Cap declared over the LIGHT: it is not in front of the light
        # (problem) and it still seals the button
        r = panel({"Cap": "light_p6"})
        self.assertTrue(any(p.startswith("Cap is declared") for p in cover_lines(r)))
        self.assertTrue(sealed(r, "button_p3"), r.get("problems"))

    def test_opaque_lens_seals_the_light(self):
        r = panel({"Cap": "button_p3"}, lens_t=20)
        self.assertTrue(sealed(r, "light_p6"), r.get("problems"))
        self.assertEqual(row(r, "light_p6")["see_through"], [])

    def test_glass_does_not_open_a_button(self):
        r = panel(btn="glass")
        self.assertTrue(sealed(r, "button_p3"), r.get("problems"))
        b = row(r, "button_p3")
        self.assertEqual((b["open"], b["see_through"]), (0, []), b)


@unittest.skipIf(FC is None, "freecadcmd not found")
class R250ManyHoleFace(unittest.TestCase):

    def test_grille_over_the_speaker_is_judged(self):
        r = panel({"Cap": "button_p3"})
        s = row(r, "speaker_p11_12")
        self.assertGreater(s["open"], 0, s)
        self.assertLess(s["open"], s["rays"], s)          # the roof between holes
        self.assertEqual(s["unmeasured"], [], s)
        # the one-piece Case with its 170-loop roof encloses every module
        # (left out before R250: all three read "OUTSIDE the product")
        self.assertEqual(enclosure_lines(r), [])
        self.assertFalse([w for w in r.get("warnings") or [] if "face-open probe" in w],
                         r.get("warnings"))
        self.assertLess(r["face_open_seconds"], 1.5)

    def test_grille_beside_the_speaker_seals_it(self):
        r = panel({"Cap": "button_p3"}, grille="off")
        s = row(r, "speaker_p11_12")
        self.assertEqual(s["open"], 0, s)
        self.assertEqual(s["blocked_by"], "Case", s)
        self.assertTrue(sealed(r, "speaker_p11_12"), r.get("problems"))
        TIMES["R250 face_open 170-loop roof (s)"] = r.get("face_open_seconds")

    def test_pin_hole_between_the_coarse_rays(self):
        r = panel({"Cap": "button_p3"}, grille="pin")
        s = row(r, "speaker_p11_12")
        self.assertGreater(s["open"], 0, s)
        self.assertEqual(s["rays"], atech_geom.FACE_GRID_FINE ** 2, s)
        self.assertFalse(sealed(r, "speaker_p11_12"), r.get("problems"))


# R250 floating() speed: the fixture's verdicts and gaps from the new
# floating() against the pre-R250 algorithm (copied here as REFERENCE),
# plus a timing guard. The shell has many faces (a hollow box carrying
# 40 posts) so the near-face path is taken; every case of the old rules
# is in it: touching, 0.3 mm (not floating), 2 mm in the cavity, 1 mm
# outside, a box INSIDE a post (distance 0), a many-face part 0.8 mm off
# the wall (trimmed, then re-measured exactly), a box far off (boxes
# apart: a lower bound), and a touching pair away from the rest.
FLOAT_SCRIPT = r"""
import json, os, sys, time
sys.path.insert(0, %(kit)r)
import Part, atech_geom as G
from FreeCAD import Vector as V

def REFERENCE(items, gap=G.FLOAT_GAP_MM):
    items = [it for it in items if it.get("shape") is not None]
    boxes = [G.tight(it["shape"]) for it in items]
    out = []
    for i, a in enumerate(items):
        best, exact = None, True
        cands = sorted((G._bb_gap(boxes[i], boxes[j]), j)
                       for j in range(len(items)) if j != i)
        for g, j in cands:
            if g > gap:
                if best is None:
                    best, exact = g, False
                break
            try:
                d, ex = G.distance(a["shape"], items[j]["shape"], limit=gap)
            except Exception:
                best = None
                break
            if d is None or (not ex and d > gap):
                best = None
                break
            best = d if best is None else min(best, d)
            if best <= gap:
                break
        if best is not None and best > gap:
            out.append({"label": a["label"], "gap_mm": round(best, 2), "exact": exact})
    return out

shell = Part.makeBox(120, 80, 40).cut(Part.makeBox(116, 76, 40, V(2, 2, 2)))
# 50 posts: the floor keeps 50 loops, under DIST_LOOPS_MAX (a face of
# more loops is judged by contact only and never accused)
posts = [Part.makeCylinder(1.5, 6, V(10 + 10 * (k %% 10), 12 + 12 * (k // 10), 2))
         for k in range(50)]
shell = shell.fuse(posts)
# a toothed wheel (many faces) 0.8 mm over the post at (60, 36): its box is
# inside the shell's, so it is measured (near faces, then exactly)
gear = Part.makeCylinder(8, 6)
gear = gear.fuse([Part.makeBox(2, 3, 6, V(7.5, -1.5, 0)).rotated(V(0, 0, 0), V(0, 0, 1), 15 * k)
                  for k in range(24)])
gear.translate(V(60, 36, 8.8))
parts = {
    "Shell": shell,
    "Touch": Part.makeBox(5, 5, 5, V(4, 70, 2)),
    "Near": Part.makeBox(5, 5, 5, V(15, 70, 2.3)),
    "Cavity": Part.makeBox(5, 5, 5, V(100, 70, 4)),
    "Outside": Part.makeBox(5, 5, 5, V(-6, 30, 10)),
    "InPost": Part.makeBox(0.5, 0.5, 0.5, V(9.75, 11.75, 4)),
    "Far": Part.makeBox(5, 5, 5, V(300, 0, 0)),
    "PairA": Part.makeBox(5, 5, 5, V(30, 30, 20)),
    "PairB": Part.makeBox(5, 5, 5, V(35, 30, 20)),
    "Gear": gear,
}
items = [{"name": k, "label": k, "shape": v, "role": None} for k, v in parts.items()]
G.tight(shell)                   # boxes warm for both (check.py's overlap stage)
t = time.time(); ref = REFERENCE(items); t_ref = time.time() - t
for st in (G._TESS, G._PREP, G._FACE_BOXES):
    st.clear()
t = time.time(); new = G.floating(items); t_new = time.time() - t
faces = {k: G.n_faces(v) for k, v in parts.items()}
print("FLOAT_R250=" + json.dumps({"ref": ref, "new": new, "t_ref": t_ref,
                                  "t_new": t_new, "faces": faces}))
sys.stdout.flush()
os._exit(0)
"""


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class R250FloatingFast(unittest.TestCase):
    """R250: floating() measured toy_car's 31 parts in 73-85 s (59
    distToShape calls on a 758-face shell); now 2.2 s. Its verdicts must
    not change. SABOTAGE: _near_distance returning (inf, True) for every
    pair -> test_verdicts_unchanged fails (Touch, Near, InPost reported);
    the containment test (_inside_either) off -> InPost reported."""

    @classmethod
    def setUpClass(cls):
        d = tempfile.mkdtemp(prefix="atech-r12-float-")
        try:
            path = os.path.join(d, "float.py")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(FLOAT_SCRIPT % {"kit": KIT})
            out = tak.fc(path)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        line = [ln for ln in out.splitlines() if ln.startswith("FLOAT_R250=")]
        if not line:
            raise AssertionError("no FLOAT_R250 line in:\n" + out[-3000:])
        cls.r = json.loads(line[-1][len("FLOAT_R250="):])
        TIMES["floating new/ref (s)"] = "%.2f/%.2f" % (cls.r["t_new"], cls.r["t_ref"])

    def test_fixture_takes_the_near_face_path(self):
        self.assertGreater(self.r["faces"]["Shell"], 100, self.r["faces"])
        self.assertGreater(self.r["faces"]["Gear"], atech_geom.FLOAT_NEAR_FACES)

    def test_verdicts_unchanged(self):
        # one deliberate change: a body wholly INSIDE another (InPost, in a
        # post of the fused shell) is distance 0 - the old rules read the
        # fused shell's surface only (distToShape on a non-SOLID shape) and
        # called it floating 1.15 mm off it
        key = lambda f: f["label"]
        ref = [f for f in self.r["ref"] if f["label"] != "InPost"]
        self.assertEqual(sorted(self.r["new"], key=key), sorted(ref, key=key))
        got = {f["label"]: f for f in self.r["new"]}
        self.assertEqual(sorted(got), ["Cavity", "Far", "Gear", "Outside"], got)
        self.assertAlmostEqual(got["Cavity"]["gap_mm"], 2.0, places=2)
        self.assertAlmostEqual(got["Outside"]["gap_mm"], 1.0, places=2)
        self.assertFalse(got["Outside"]["exact"])      # boxes 1 mm apart
        self.assertAlmostEqual(got["Gear"]["gap_mm"], 0.8, places=2)
        self.assertTrue(got["Gear"]["exact"])
        self.assertFalse(got["Far"]["exact"])          # boxes apart: a lower bound

    def test_timing_guard(self):
        # the fixture: 10 bodies, one of ~200 faces. The old rules spent
        # most of their time in distToShape on the shell
        self.assertLess(self.r["t_new"], 5.0, self.r)
        self.assertLess(self.r["t_new"], max(0.5, self.r["t_ref"]), self.r)


GRID_SCRIPT = r"""
import json, os, sys
sys.path.insert(0, %(projects)r)
import numpy as np, Part
import atech_ports as ap
from FreeCAD import Vector as V
# many small triangles (a sphere) beside long ones crossing every cell
# (a long fine cylinder: slivers end to end): a spline body's in miniature
def tris(shape, dev):
    pts, fac = shape.tessellate(dev)
    return np.array([[q.x, q.y, q.z] for q in pts])[np.array(fac)]
T = np.concatenate([tris(Part.makeSphere(20, V(60, 0, 0)), 0.05),
                    tris(Part.makeCylinder(20, 120, V(0, 0, 0), V(1, 0, 0)), 0.002)])
P = np.random.default_rng(3).uniform([-5, -25, -25], [125, 25, 25], (20000, 3))
b = ap._RayGrid(T)                 # the library's own GRID_ENTRIES
ap.GRID_ENTRIES = 10 ** 9           # the pre-R250 grid (n = sqrt(m))
a = ap._RayGrid(T)
print("GRID_R250=" + json.dumps({"tris": len(T), "same": bool((a.inside(P) == b.inside(P)).all()),
                                 "entries": int(len(b.cells)), "inside": int(b.inside(P).sum())}))
sys.stdout.flush()
os._exit(0)
"""


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
@unittest.skipUnless(os.path.isfile(os.path.join(PROJECTS, "atech_ports.py")), "no library")
class R250RayGridEntries(unittest.TestCase):
    """R250: atech_ports._RayGrid coarsens its cells until the (cell,
    triangle) entries are <= GRID_ENTRIES x the triangles (20 M entries,
    1 s of argsort, for one toy-car body; ap.check 9.1 -> 5.7 s). Parity
    is the same at any cell size. SABOTAGE: GRID_ENTRIES = 10**9 ->
    test_entries_bounded fails."""

    def test_entries_bounded_and_parity_unchanged(self):
        d = tempfile.mkdtemp(prefix="atech-r12-grid-")
        try:
            path = os.path.join(d, "grid.py")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(GRID_SCRIPT % {"projects": PROJECTS})
            out = tak.fc(path)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        line = [ln for ln in out.splitlines() if ln.startswith("GRID_R250=")]
        self.assertTrue(line, out[-3000:])
        r = json.loads(line[-1][len("GRID_R250="):])
        self.assertTrue(r["same"], r)
        self.assertGreater(r["inside"], 0, r)
        self.assertLessEqual(r["entries"], 12 * r["tris"], r)


def tearDownModule():
    if TIMES:
        print("\n  [round 12] " + ", ".join("%s %s" % kv for kv in sorted(TIMES.items())))


if __name__ == "__main__":
    unittest.main()
