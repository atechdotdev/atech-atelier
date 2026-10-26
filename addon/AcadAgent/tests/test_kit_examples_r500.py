"""R500: EVERY example in agent_kit/examples passes ./check headless.

    cd addon/AcadAgent/tests && python3 -m unittest test_kit_examples_r500

Each example is built as the agent's workspace builds it: the file as
model.py, its INTENT literal as intent.json (none when it has none), the
'Example: "<request>"' of its docstring as the turn's request, the Atech
library on ATECH_CHECK_PATH, the quality-mode timeout (180 s). Asserted:
CHECK PASS, one valid solid per object, the model build well under 180 s
(R500_MODEL_LIMIT_S, default 90), no archetype line as a PROBLEM (R500:
style is a WARNING). Sabotage: the hinged box without its hinge pin fails
R441 (fastening); the lamp without the ribs round its globe light fails
R442 (holder). Skips without freecadcmd (ATECH_FREECADCMD) or the library.
"""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
sys.path.insert(0, ADDON)

from acadagent import sandbox  # noqa: E402

KIT = sandbox.KIT_DIR
EXAMPLES = os.path.join(KIT, "examples")
PROJECTS = os.path.normpath(os.path.join(ADDON, "..", "..", "projects"))
FC = sandbox.find_freecadcmd()
CHECK_TIMEOUT_S = 180
MODEL_LIMIT_S = float(os.environ.get("R500_MODEL_LIMIT_S", "90"))
TIMINGS = {}


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def intent_of(src):
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "INTENT"
                                                for t in node.targets):
            return ast.literal_eval(node.value)
    return None


def request_of(src):
    m = re.match(r'\s*Example:\s*"([^"]+)"', ast.get_docstring(ast.parse(src)) or "")
    return m.group(1) if m else None


def examples():
    return sorted(n for n in os.listdir(EXAMPLES) if n.endswith(".py"))


def build(example, extra_code=""):
    """(result, output, wall s) of ./check on a fresh workspace."""
    ws = tempfile.mkdtemp(prefix="atech-r500-")
    try:
        src = read(os.path.join(EXAMPLES, example))
        with open(os.path.join(ws, "model.py"), "w", encoding="utf-8") as fh:
            fh.write(src + extra_code)
        intent = intent_of(src)
        if intent is not None:
            with open(os.path.join(ws, "intent.json"), "w", encoding="utf-8") as fh:
                json.dump(intent, fh)
        req = request_of(src)
        if req:
            with open(os.path.join(ws, ".atech_turn.json"), "w", encoding="utf-8") as fh:
                json.dump({"fix": False, "request": req}, fh)
        env = dict(os.environ, ATECH_CHECK_SCRIPT=os.path.join(ws, "model.py"),
                   ATECH_CHECK_PNG="", ATECH_CHECK_PATH=PROJECTS,
                   ATECH_CHECK_TIMEOUT=str(CHECK_TIMEOUT_S))
        t0 = time.time()
        p = subprocess.run([FC, os.path.join(KIT, "check.py")], env=env, capture_output=True,
                           text=True, timeout=1500, cwd=ws)
        wall = time.time() - t0
        out = p.stdout + p.stderr
        res = None
        for line in reversed(out.splitlines()):
            if line.startswith("ATECH_CHECK="):
                res = json.loads(line[len("ATECH_CHECK="):])
                break
        return res, out, wall
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def verdict(out):
    lines = [ln for ln in out.splitlines() if ln.startswith("CHECK ")]
    return lines[-1] if lines else ""


class R500Sources(unittest.TestCase):
    def test_every_example_compiles_and_names_its_parts(self):
        names = examples()
        self.assertGreaterEqual(len(names), 16, names)
        for ex in names:
            with self.subTest(example=ex):
                src = read(os.path.join(EXAMPLES, ex))
                compile(src, ex, "exec")
                if "import atech_ports" in src and ex != "atech_case.py":
                    self.assertTrue(request_of(src), "a product seed names its request")
                    self.assertIsInstance(intent_of(src), dict)

    def test_hinged_box_models_its_pin(self):
        src = read(os.path.join(EXAMPLES, "hinged_box.py"))
        self.assertIn('"Hinge_Pin"', src)


@unittest.skipIf(FC is None, "bundled freecadcmd not found (set ATECH_FREECADCMD)")
@unittest.skipUnless(os.path.isfile(os.path.join(PROJECTS, "atech_ports.py")),
                     "Atech library (projects/atech_ports.py) not found")
class R500Builds(unittest.TestCase):

    def test_every_example_passes(self):
        names = examples()
        workers = int(os.environ.get("R500_WORKERS", "4"))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            got = list(pool.map(lambda n: (n,) + build(n), names))
        for ex, res, out, wall in got:
            with self.subTest(example=ex):
                self.assertIsNotNone(res, out[-3000:])
                if "LibraryMissing" in (res.get("error") or ""):
                    continue
                TIMINGS[ex] = {"model_s": res.get("run_seconds"), "check_s": round(wall, 1)}
                self.assertTrue(res["ok"], res.get("error"))
                self.assertEqual(verdict(out), "CHECK PASS",
                                 "\n".join(ln for ln in out.splitlines()
                                           if ln.startswith(("PROBLEM", "CHECK")))[-3000:])
                for o in res["objects"]:
                    self.assertTrue(o["valid"], o)
                    self.assertEqual(o["solids"], 1, o)
                self.assertLess(res["run_seconds"], MODEL_LIMIT_S, "model build too slow")
                self.assertLess(wall, CHECK_TIMEOUT_S, "./check as a whole too slow")
                self.assertFalse([p for p in res.get("problems") or ()
                                  if p.startswith("ARCHETYPE ")])

    def _fails(self, ex, code, *words):
        res, out, _ = build(ex, code)
        self.assertIsNotNone(res, out[-3000:])
        v = verdict(out)
        self.assertTrue(v.startswith("CHECK FAIL"), v)
        for w in words:
            self.assertIn(w, v)

    def test_hinged_box_without_its_pin_fails(self):
        # SABOTAGE: the bore with nothing in it joins nothing (R441)
        self._fails("hinged_box.py", "\ndoc.removeObject('Hinge_Pin')\n", "fastening", "Lid")

    def test_lamp_without_its_light_ribs_fails(self):
        # SABOTAGE: the ribs round the globe light cut away - it hangs on
        # its ribbon (R442)
        self._fails("bedside_lamp.py", (
            "\n_s = doc.getObject('Shell')\n"
            "_s.Shape = _s.Shape.cut(Part.makeBox(tl.XLength + 6, tl.YLength + 6, 30, "
            "V(tl.XMin - 3, tl.YMin - 3, Z_NECK - 1)))\n"), "holder", "light_8")

    def test_car_hardtop_without_its_pegs_fails(self):
        # SABOTAGE: the four pegs under the hardtop's lip cut off - the lip
        # only locates it, it lifts off the tub (R441)
        self._fails("toy_car.py", (
            "\n_h = doc.getObject('Hardtop')\n"
            "for _x in PEG_X:\n    for _y in PEG_YS:\n"
            "        _h.Shape = _h.Shape.cut(Part.makeBox(4, 4, 4.1, V(_x - 2, _y - 2, LIP_Z0 - 4.1)))\n"),
            "fastening", "Hardtop")


HINGE_MOTION = {"motion": [{"part": "Lid", "axis": [[30.0, 40.0, 25.0], [-1.0, 0.0, 0.0]],
                            "range_deg": [0, 90]}]}


def check_ws(code, intent=None):
    """./check on a workspace holding `code` (and `intent` as intent.json)."""
    ws = tempfile.mkdtemp(prefix="atech-r505-")
    try:
        with open(os.path.join(ws, "model.py"), "w", encoding="utf-8") as fh:
            fh.write(code)
        if intent is not None:
            with open(os.path.join(ws, "intent.json"), "w", encoding="utf-8") as fh:
                json.dump(intent, fh)
        env = dict(os.environ, ATECH_CHECK_SCRIPT=os.path.join(ws, "model.py"),
                   ATECH_CHECK_PNG="", ATECH_CHECK_PATH=PROJECTS,
                   ATECH_CHECK_TIMEOUT=str(CHECK_TIMEOUT_S))
        p = subprocess.run([FC, os.path.join(KIT, "check.py")], env=env, capture_output=True,
                           text=True, timeout=600, cwd=ws)
        return verdict(p.stdout + p.stderr)
    finally:
        shutil.rmtree(ws, ignore_errors=True)


@unittest.skipIf(FC is None, "bundled freecadcmd not found (set ATECH_FREECADCMD)")
class R505DeclaredHingeJoins(unittest.TestCase):
    """R505: cad.pin_hinge leaves the pin out (it is bought); a lid that
    intent.json "motion" declares on the axis both parts are bored on is
    joined by its hinge (atech_geom.fastening motions=)."""

    def test_declared_hinge_joins_without_a_modelled_pin(self):
        code = read(os.path.join(EXAMPLES, "hinged_box.py")) + "\ndoc.removeObject('Hinge_Pin')\n"
        self.assertEqual(check_ws(code, HINGE_MOTION), "CHECK PASS")
        # SABOTAGE: no motion declared - the bare bore joins nothing
        v = check_ws(code)
        self.assertTrue(v.startswith("CHECK FAIL") and "fastening" in v, v)
        # SABOTAGE: an axis 20 mm off the bores - not a hinge (and it binds)
        off = {"motion": [dict(HINGE_MOTION["motion"][0], axis=[[30.0, 20.0, 25.0], [-1.0, 0.0, 0.0]])]}
        v = check_ws(code, off)
        self.assertTrue(v.startswith("CHECK FAIL") and "fastening" in v, v)


R506_SCRIPT = r'''import sys, json
sys.path.insert(0, %r)
import Part, FreeCAD
import atech_cad as cad
V = FreeCAD.Vector
# a back (lid) whose inner face ramps up 1 mm over 10 mm, a front (case) above it
lid = Part.makeBox(40, 40, 3)
wedge = Part.makePolygon([V(0, 0, 3), V(40, 0, 3), V(40, 0, 7), V(0, 0, 3)])
lid = cad.fuse_one(lid, Part.Face(wedge).extrude(V(0, 40, 0)))
case = cad.cut(Part.makeBox(40, 40, 20, V(0, 0, 0)), Part.makeBox(36, 36, 18, V(2, 2, 0)))
case.translate(V(0, 0, 7.5))
lid2, case2 = cad.screw_through(lid, case, (20, 20, 0), size="M2", ribs=0)
print("R506=" + json.dumps({"overlap": case2.common(lid).Volume}))
import atech_detail as D
_f = D._frame
D._frame = lambda n, up=None: (V(0, 0, 0), V(0, 0, 0), _f(n, up)[2])     # SABOTAGE: the axis only
try:
    _l, c3 = cad.screw_through(lid, case, (20, 20, 0), size="M2", ribs=0)
    print("R506S=" + json.dumps({"overlap": c3.common(lid).Volume}))
finally:
    D._frame = _f
'''


@unittest.skipIf(FC is None, "bundled freecadcmd not found (set ATECH_FREECADCMD)")
class R506ScrewThroughOnARampedLid(unittest.TestCase):
    """R506: cad.screw_through puts the boss top 0.1 mm over the lid's inner
    face under the whole boss (the handheld at LENGTH 290: a crowned back
    rose under the rim and the column sat 0.26 mm3 in it)."""

    def test_boss_clears_a_ramped_inner_face(self):
        d = tempfile.mkdtemp(prefix="atech-r506-")
        try:
            path = os.path.join(d, "r506.py")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(R506_SCRIPT % KIT)
            p = subprocess.run([FC, path], capture_output=True, text=True, timeout=300)
            out = p.stdout + p.stderr
            got = {}
            for ln in out.splitlines():
                for k in ("R506S=", "R506="):
                    if ln.startswith(k):
                        got[k] = json.loads(ln[len(k):])
                        break
            self.assertIn("R506=", got, out[-2000:])
            self.assertLess(got["R506="]["overlap"], 1e-3)
            # SABOTAGE: measured at the axis only (the old rule) - it overlaps
            self.assertGreater(got["R506S="]["overlap"], 0.01)
        finally:
            shutil.rmtree(d, ignore_errors=True)


def tearDownModule():
    if TIMINGS:
        print("\nR500_TIMINGS=" + json.dumps(TIMINGS, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
