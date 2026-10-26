"""The showcase examples (R230): toy_car.py, desk_robot.py, smart_speaker.py.

    cd addon/AcadAgent/tests && python3 -m unittest test_kit_examples

Each example builds under agent_kit/check.py exactly as the agent's ./check
runs a workspace: the example copied to model.py, intent.json written from
its INTENT literal, the Atech library on ATECH_CHECK_PATH, the quality-mode
timeout (180 s). Asserted: CHECK PASS, one valid solid per object, the
model run under 180 s. A sabotage run (a block dropped into the speaker's
top) proves the gate can fail. The source checks need no FreeCAD; the
builds skip without freecadcmd (set ATECH_FREECADCMD) or the library.
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

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
sys.path.insert(0, ADDON)

from acadagent import sandbox  # noqa: E402

KIT = sandbox.KIT_DIR
EXAMPLES = os.path.join(KIT, "examples")
PROJECTS = os.path.normpath(os.path.join(ADDON, "..", "..", "projects"))
SHOWCASE = ("toy_car.py", "desk_robot.py", "smart_speaker.py")
BUILD_LIMIT_S = 180.0          # quality mode's build / ./check timeout (sandbox.py)
FC = sandbox.find_freecadcmd()
if FC is None and os.environ.get("ATECH_REQUIRE_FREECADCMD") == "1":
    raise RuntimeError("ATECH_REQUIRE_FREECADCMD=1 but no freecadcmd was found "
                       "(set ATECH_FREECADCMD)")
TIMINGS = {}


def intent_of(path):
    """The example's INTENT = {...} literal (its intent.json)."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "INTENT"
                                                for t in node.targets):
            return ast.literal_eval(node.value)
    return None


def build(example, extra_code=""):
    """Run check.py on a fresh workspace holding the example as model.py.
    Returns (result dict, full output, wall seconds)."""
    ws = tempfile.mkdtemp(prefix="atech-showcase-")
    try:
        src = os.path.join(EXAMPLES, example)
        with open(src, encoding="utf-8") as fh:
            code = fh.read()
        with open(os.path.join(ws, "model.py"), "w", encoding="utf-8") as fh:
            fh.write(code + extra_code)
        with open(os.path.join(ws, "intent.json"), "w", encoding="utf-8") as fh:
            json.dump(intent_of(src), fh)
        env = dict(os.environ,
                   ATECH_CHECK_SCRIPT=os.path.join(ws, "model.py"),
                   ATECH_CHECK_PNG="",                   # no renders: the gate only
                   ATECH_CHECK_PATH=PROJECTS,
                   ATECH_CHECK_TIMEOUT=str(int(BUILD_LIMIT_S)))
        t0 = time.time()
        p = subprocess.run([FC, os.path.join(KIT, "check.py")], env=env, capture_output=True,
                           text=True, timeout=1200, cwd=ws)
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


class ExampleSource(unittest.TestCase):
    """No FreeCAD needed: the files the agent copies are well formed."""

    def test_present_compile_and_intent(self):
        for ex in SHOWCASE:
            with self.subTest(example=ex):
                path = os.path.join(EXAMPLES, ex)
                self.assertTrue(os.path.isfile(path), path)
                with open(path, encoding="utf-8") as fh:
                    src = fh.read()
                tree = ast.parse(src)
                doc = ast.get_docstring(tree) or ""
                self.assertTrue(doc.startswith("Example: "), doc[:60])
                self.assertIn("MEASURED", doc)
                intent = intent_of(path)
                self.assertIsInstance(intent, dict, "no INTENT literal")
                self.assertIn(intent.get("board"), ("flat", "upright"))
                self.assertTrue(intent.get("fitted_after"))
                # real hardware, placed with the library
                self.assertIn("import atech_ports as ap", src)
                self.assertIn('ap.seat(doc, "usbc"', src)
                # never writes intent.json itself (./check fails that)
                self.assertNotIn("intent.json\", \"w", src)

    def test_cabled_hardware_where_the_brief_asks(self):
        # the car's headlights and nose sensor and the robot's screen face
        # are cabled, not seated (the showcase brief, R230)
        want = {"toy_car.py": ('ap.cable(doc, "distance_sensor"', 'ap.cable(doc, "light"'),
                "desk_robot.py": ('ap.cable(doc, "screen"',),
                "smart_speaker.py": ("cad.revolve_profile(",)}
        for ex, needles in want.items():
            with open(os.path.join(EXAMPLES, ex), encoding="utf-8") as fh:
                src = fh.read()
            for n in needles:
                with self.subTest(example=ex, needle=n):
                    self.assertIn(n, src)

    def test_products_reference_present(self):
        ref = os.path.join(KIT, "reference", "ATECH_PRODUCTS.md")
        self.assertTrue(os.path.isfile(ref), ref)
        with open(ref, encoding="utf-8") as fh:
            text = fh.read()
        for ex in SHOWCASE:
            self.assertIn("examples/" + ex, text)
        self.assertNotIn("/private/tmp", text)       # no scratch paths shipped
        # every recipe lists 25+ human-design details and a colour scheme
        recipes = text.split("\n## 7. Recipes")[-1].split("\n## 8.")[0].split("\n### ")[1:]
        self.assertGreaterEqual(len(recipes), 10)
        for r in recipes:
            title = r.splitlines()[0]
            with self.subTest(recipe=title):
                self.assertIn("Human-design details", r)
                self.assertIn("**Colours:**", r)
                nums = [int(t) for t in re.findall(r"(?<![\w.])(\d{1,2})\. ", r)]
                self.assertGreaterEqual(max(nums or [0]), 25, title)


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
@unittest.skipUnless(os.path.isfile(os.path.join(PROJECTS, "atech_ports.py")),
                     "Atech library (projects/atech_ports.py) not found")
class ExampleBuilds(unittest.TestCase):
    """Each example passes ./check with one solid per object, in time."""

    def _check(self, ex):
        res, out, wall = build(ex)
        if res and "LibraryMissing" in (res.get("error") or ""):
            self.skipTest("library code without its data here")
        self.assertIsNotNone(res, out[-3000:])
        TIMINGS[ex] = {"model_s": res.get("run_seconds"), "check_s": round(wall, 1)}
        self.assertTrue(res["ok"], res.get("error"))
        self.assertEqual(verdict(out), "CHECK PASS",
                         "\n".join(ln for ln in out.splitlines()
                                   if ln.startswith(("PROBLEM", "CHECK")))[-3000:])
        self.assertTrue(res["objects"])
        for o in res["objects"]:
            self.assertTrue(o["valid"], o)
            self.assertEqual(o["solids"], 1, o)
        self.assertLess(res["run_seconds"], BUILD_LIMIT_S, "model.py too slow")
        # R250: the WHOLE ./check inside the quality timeout (toy_car took
        # 187 s, floating() alone 85 s) - floating is seconds now
        self.assertLess(wall, BUILD_LIMIT_S, "./check as a whole too slow")
        self.assertLess(res.get("floating_seconds") or 0, 20.0, res.get("floating_seconds"))
        # R250: no OPEN warning about a lens or a key cap (see-through parts
        # and the INTENT "covers" lines), no body left out of the pair tests
        self.assertFalse([w for w in res.get("warnings") or ()
                          if "OPEN" in w or "sealed" in w or "limited to" in w],
                         res.get("warnings"))
        return res

    def test_toy_car(self):
        res = self._check("toy_car.py")
        labels = {o["label"] for o in res["objects"]}
        for want in ("Chassis", "Body_Shell", "Hardtop", "Grille", "Tyre_FL", "Rim_FL"):
            self.assertIn(want, labels)

    def test_desk_robot(self):
        res = self._check("desk_robot.py")
        labels = {o["label"] for o in res["objects"]}
        for want in ("Torso_Front", "Torso_Back", "Head_Front", "Face_Plate", "Arm_L"):
            self.assertIn(want, labels)

    def test_smart_speaker(self):
        res = self._check("smart_speaker.py")
        labels = {o["label"] for o in res["objects"]}
        for want in ("Base", "Shell", "Top", "Light_Ring", "Cap_Plus"):
            self.assertIn(want, labels)

    def test_sabotage_is_caught(self):
        # a block dropped into the speaker's aluminium top: the same gate
        # must FAIL (overlap), so a broken example cannot pass unnoticed
        res, out, _ = build("smart_speaker.py", extra_code=(
            "\no = doc.addObject('Part::Feature', 'Sabotage')\n"
            "o.Shape = Part.makeBox(6, 6, 6, V(CX - 3, CY - 3, TOP - 4))\n"))
        self.assertIsNotNone(res, out[-3000:])
        self.assertTrue(verdict(out).startswith("CHECK FAIL"), verdict(out))
        self.assertIn("Sabotage", verdict(out))


def tearDownModule():
    if TIMINGS:
        print("\nSHOWCASE_TIMINGS=" + json.dumps(TIMINGS, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
