"""R830: the Sesame walker - an open design refitted for the Atech board.

  TestParts      (no FreeCAD) agent_kit/third_party/sesame carries every part
                 parts.json lists, the Apache-2.0 LICENSE and a NOTICE that
                 credits Sesame and says what was changed; the example uses
                 only those parts.
  TestFreeCAD    under freecadcmd:
                   - every upstream part loads as one valid solid;
                   - ap.cable(..., smooth=True) follows the example's
                     routes between the head's floor and the lid (sabotage:
                     the default, scaled tangents, swings through the floor);
                   - check.py's "imported" intent: the imported parts are
                     not judged for walls (sabotage: without it the upstream
                     femur's 0.3 mm wall fails) and a screw's head recess is
                     never a wall.
  The example itself is built and must CHECK PASS with every other example
  (test_kit_examples_r500.R500Builds).

    QT_QPA_PLATFORM=offscreen ATECH_FREECADCMD=<freecadcmd> \
        ATECH_ARTIFACTS=<repo>/models <bundled python> -m unittest -v test_sesame_r830
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
sys.path.insert(0, ADDON)

from acadagent import sandbox  # noqa: E402

KIT = sandbox.KIT_DIR
PARTS = os.path.join(KIT, "third_party", "sesame")
EXAMPLE = os.path.join(KIT, "examples", "sesame_atech.py")
PROJECTS = os.path.normpath(os.path.join(ADDON, "..", "..", "projects"))
FC = sandbox.find_freecadcmd()


def read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


class TestParts(unittest.TestCase):
    def test_every_listed_part_is_there(self):
        info = json.loads(read(os.path.join(PARTS, "parts.json")))
        names = sorted(info["parts"])
        self.assertEqual(len(names), 20, names)            # 19 parts + the original cover
        for n in names:
            self.assertTrue(os.path.isfile(os.path.join(PARTS, n + ".brep.gz")), n)
        self.assertEqual(info["step_sha256"],
                         "b6ae8936df90d85d4d6f6b24ea53bd387bd0508da2090fdbc535227d5feb9be0")

    def test_licence_and_credit(self):
        lic = read(os.path.join(PARTS, "LICENSE"))
        self.assertIn("Apache License", lic)
        self.assertIn("Version 2.0", lic)
        notice = read(os.path.join(PARTS, "NOTICE.md"))
        for needle in ("Dorian Todd", "github.com/dorianborian/sesame-robot",
                       "3f76b5f37ac9f9efd3953e50b4beee86e6e88acf", "Changes made"):
            self.assertIn(needle, notice)

    def test_example_uses_only_shipped_parts(self):
        import ast
        src = read(EXAMPLE)
        tree = ast.parse(src)
        upstream = next(n for n in tree.body if isinstance(n, ast.Assign)
                        and getattr(n.targets[0], "id", None) == "UPSTREAM")
        self.assertIn("UPSTREAM", src)
        intent = next(n for n in tree.body if isinstance(n, ast.Assign)
                      and getattr(n.targets[0], "id", None) == "INTENT")
        imported = ast.literal_eval(intent.value)["imported"]
        for n in imported:
            self.assertTrue(os.path.isfile(os.path.join(PARTS, n + ".brep.gz")), n)
        self.assertEqual(len(imported), 19)
        self.assertTrue(upstream)


FC_SCRIPT = r'''
import os, sys, json, gzip, math
sys.path.insert(0, os.environ["R830_PROJECTS"]); sys.path.insert(0, os.environ["R830_KIT"])
import FreeCAD as App, Part
from FreeCAD import Vector as V, Placement, Rotation
import atech_ports as ap
out = {}
parts = os.environ["R830_PARTS"]
bad = []
for f in sorted(os.listdir(parts)):
    if f.endswith(".brep.gz"):
        s = Part.Shape()
        with gzip.open(os.path.join(parts, f), "rt") as fh:
            s.importBrepFromString(fh.read())
        if len(s.Solids) != 1 or not s.isValid():
            if f != "top_cover.brep.gz":             # the original cover: 2 solids
                bad.append(f)
out["bad_parts"] = bad
# smooth=True follows the example's 8- and 9-waypoint routes between the
# head's floor and the lid; the default (tangents scaled by the whole
# chord) overshoots them
import ast
src = open(os.environ["R830_EXAMPLE"]).read()
route = ast.literal_eval(next(n for n in ast.parse(src).body if isinstance(n, ast.Assign)
                              and getattr(n.targets[0], "id", None) == "ROUTE").value)
for smooth in (True, False):
    doc = App.newDocument("C%d" % smooth)
    b = ap.board_object(doc)
    rot = Rotation(V(0, 0, 1), 180).multiply(Rotation(V(1, 0, 0), 90))
    b.Placement = Placement(V(), rot); bb = ap.bbox(b)
    b.Placement = Placement(V(-(bb.XMin + bb.XMax) / 2, -8 - (bb.YMin + bb.YMax) / 2, 79.9478 - bb.ZMin), rot)
    try:
        m, rs = ap.cable(doc, "screen", (10, 11), ap.module_placement(
            "screen", (0.0, -78.2673, 81.1005), face="-Y", cable="-Z"), via=route, smooth=smooth)
        out["zmax_%s" % smooth] = round(max(r.Shape.BoundBox.ZMax for r in rs), 2)
        out["zmin_%s" % smooth] = round(min(r.Shape.BoundBox.ZMin for r in rs), 2)
        out["xmin_%s" % smooth] = round(min(r.Shape.BoundBox.XMin for r in rs), 2)
        out["ymin_%s" % smooth] = round(min(r.Shape.BoundBox.YMin for r in rs), 2)
        out["common_%s" % smooth] = round(rs[0].Shape.common(rs[1].Shape).Volume, 3)
        out["len_%s" % smooth] = [round(float(r.AtechCableLength), 1) for r in rs]
    except Exception as exc:
        out["zmax_%s" % smooth] = "error: %s" % exc
sys.stdout.write("\nR830=" + json.dumps(out) + "\n"); sys.stdout.flush()
os._exit(0)
'''


def run_fc(script, env_extra):
    d = tempfile.mkdtemp(prefix="atech-r830-")
    p = os.path.join(d, "r830.py")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(script)
    env = dict(os.environ, R830_PROJECTS=PROJECTS, R830_KIT=KIT, R830_PARTS=PARTS,
               R830_EXAMPLE=EXAMPLE, **env_extra)
    r = subprocess.run([FC, p], env=env, capture_output=True, text=True, timeout=600)
    text = r.stdout + r.stderr
    k = text.rfind("R830=")
    if k < 0:
        raise AssertionError("no result line:\n" + text[-3000:])
    return json.loads(text[k + 5:].split("\n", 1)[0])


def check_example(intent_edit=None):
    """./check on the example in a fresh workspace; intent_edit(dict)
    changes intent.json first. Returns the verdict line."""
    import ast
    src = read(EXAMPLE)
    tree = ast.parse(src)
    intent = ast.literal_eval(next(n for n in tree.body if isinstance(n, ast.Assign)
                                   and getattr(n.targets[0], "id", None) == "INTENT").value)
    if intent_edit:
        intent_edit(intent)
    ws = tempfile.mkdtemp(prefix="atech-r830-ws-")
    with open(os.path.join(ws, "model.py"), "w", encoding="utf-8") as fh:
        fh.write(src)
    with open(os.path.join(ws, "intent.json"), "w", encoding="utf-8") as fh:
        json.dump(intent, fh)
    env = dict(os.environ, ATECH_CHECK_SCRIPT=os.path.join(ws, "model.py"), ATECH_CHECK_PNG="",
               ATECH_CHECK_PATH=PROJECTS, ATECH_CHECK_TIMEOUT="300")
    p = subprocess.run([FC, os.path.join(KIT, "check.py")], env=env, capture_output=True,
                       text=True, timeout=900, cwd=ws)
    lines = [ln for ln in (p.stdout + p.stderr).splitlines() if ln.startswith(("CHECK", "PROBLEM"))]
    return lines


def library_present():
    return bool(os.environ.get("ATECH_ARTIFACTS")) or os.path.isdir(
        os.path.normpath(os.path.join(ADDON, "..", "..", "models", "stl")))


@unittest.skipIf(not FC, "bundled freecadcmd not found (set ATECH_FREECADCMD)")
@unittest.skipUnless(library_present(), "Atech module library not found (set ATECH_ARTIFACTS)")
class TestFreeCAD(unittest.TestCase):
    def test_parts_and_smooth_ribbons(self):
        r = run_fc(FC_SCRIPT, {})
        self.assertEqual(r["bad_parts"], [])
        # smooth: under the lid (inner face z 93.3), over the head's floor
        # (z 66) and the two ribbons apart; the default swings through the
        # head's floor (MEASURED: down to z 53) or does not build
        self.assertIsInstance(r["zmax_True"], float, r)
        self.assertLess(r["zmax_True"], 93.3, r)
        self.assertGreater(r["zmin_True"], 66.0, r)
        self.assertEqual(r["common_True"], 0.0, r)
        self.assertLess(r["zmin_False"] if isinstance(r["zmin_False"], float) else -1, 66.0, r)

    def test_imported_parts_are_not_judged_for_walls(self):
        lines = check_example()
        self.assertEqual(lines[-1], "CHECK PASS", "\n".join(lines))

    def test_sabotage_without_imported_the_upstream_walls_fail(self):
        lines = check_example(lambda i: i.pop("imported"))
        self.assertTrue(lines[-1].startswith("CHECK FAIL"), lines[-1])
        self.assertTrue(any("femur_" in ln and "wall only" in ln for ln in lines), "\n".join(lines))
        self.assertFalse(any(ln.startswith("PROBLEM Screw_") for ln in lines), "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
