"""Tests for agent_kit/atech_detail.py, the finish and detail helpers (R230+).

Runs under SYSTEM python (`python3 -m unittest test_kit_detail`); every
FreeCAD step runs in the bundled freecadcmd as a child, one at a time.
Skips the FreeCAD classes when freecadcmd is missing (ATECH_FREECADCMD
points at a build; ATECH_REQUIRE_FREECADCMD=1 makes a missing one fail).

What is pinned:
  R230  the API the agent is shown: every agreed helper in __all__ with
        the agreed signature and a whole first docstring sentence <= 170
        chars (build.helper_card() cuts there); the import works in both
        orders once atech_cad does `from atech_detail import *` at its end
  R231-R245  fc_atech_detail.py: every helper against closed-form volumes,
        counts and measured positions; each sabotage switch breaks one gate
        and the suite must notice
  R240  check.py records `obj.ViewObject.ShapeColor = det.color("rubber")`
        and `... .Transparency = det.transparency("glass")` with the
        evaluated values (Studio applies them)
"""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
sys.path.insert(0, ADDON)

from acadagent import sandbox  # noqa: E402

KIT = sandbox.KIT_DIR
DETAIL = os.path.join(KIT, "atech_detail.py")
FC = sandbox.find_freecadcmd()
if FC is None and os.environ.get("ATECH_REQUIRE_FREECADCMD") == "1":
    raise RuntimeError("ATECH_REQUIRE_FREECADCMD=1 but no freecadcmd was found "
                       "(set ATECH_FREECADCMD)")

# The agreed API (R230): name -> exact ast.unparse of its arguments.
API = {
    "soften": "shape, r, edges=None, min_r=0.3, ladder=(1, 0.6, 0.35), budget_s=8",
    "new_edges": "after, before",
    "groove_ring": "shape, axis, at, w=0.6, depth=0.5",
    "groove_outline": "shape, outline_pts, view='+Y', w=0.6, depth=0.5, both_sides=True",
    "grille": "shape, center, normal, size, kind='hex', hole=3, pitch=4.5, margin=2, "
              "through='wall'",
    "speaker_grille": "shape, center, normal, d, ring_pitch=2.5, hole=1.4, through='wall'",
    "wheel": "d, width, rim_d=None, spokes=5, spoke_style='window', tread='block', "
             "tread_n=40, hub_d=None, bore=None, axis='+Y', at=(0, 0, 0)",
    "text": "shape, text, at, normal, size, depth=0.6, mode='emboss', up=(0, 0, 1), "
            "halign='center', font=None",
    "color": "name",
    "transparency": "name",
    "screw": "kind='socket', size='M3', length=8, at=(0, 0, 0), axis='-Z'",
    "screw_boss": "case, at, axis='-Z', size='M3', h=None, ribs=4, rib_len=None",
    "screw_through": "lid, case, at, size='M3', ribs=4, rib_len=None",
    "button_cap": "d_or_wh, height, dome=0.5, flange=1.0, stem_d=None, at=(0, 0, 0), "
                  "axis='+Z'",
    "lens": "d, h, dome=0.8, at=(0, 0, 0), axis='+Z'",
    "opening_for": "wall, part_or_bbox, clearance=0.2, chamfer=0.3, axis=None",
    "knurl": "shape, axis, center, r, z0, z1, n=60, kind='straight', depth=0.4",
    "foot": "d, h, style='dome', at=(0, 0, 0)",
}


def fc(script, env=None, timeout=600, cwd=None):
    e = dict(os.environ, **(env or {}))
    p = subprocess.run([FC, script], env=e, capture_output=True, text=True,
                       timeout=timeout, cwd=cwd or tempfile.gettempdir())
    return p.stdout + p.stderr


def _tree():
    with open(DETAIL, encoding="utf-8") as fh:
        return ast.parse(fh.read())


class DetailApi(unittest.TestCase):
    """No FreeCAD needed: what CI can check about the file (R230)."""

    def test_compiles(self):
        with open(DETAIL, encoding="utf-8") as fh:
            compile(fh.read(), DETAIL, "exec")

    def test_all_and_signatures(self):
        tree = _tree()
        names = [e.value for n in tree.body if isinstance(n, ast.Assign)
                 and any(getattr(t, "id", None) == "__all__" for t in n.targets)
                 for e in n.value.elts]
        fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        for name, sig in API.items():
            with self.subTest(helper=name):
                self.assertIn(name, names)
                self.assertIn(name, fns)
                self.assertEqual(ast.unparse(fns[name].args), sig)
        self.assertIn("MATERIALS", names)
        # nothing in __all__ that atech_cad already exports (a star import
        # would silently replace atech_cad's own helper)
        with open(os.path.join(KIT, "atech_cad.py"), encoding="utf-8") as fh:
            cad_tree = ast.parse(fh.read())
        cad_names = {e.value for n in cad_tree.body if isinstance(n, ast.Assign)
                     and any(getattr(t, "id", None) == "__all__" for t in n.targets)
                     for e in n.value.elts}
        self.assertFalse(cad_names & set(names), cad_names & set(names))

    def test_card_sentences(self):
        # build.helper_card(): the first sentence, cut at the first ". ", at
        # most 170 chars - it must be the WHOLE sentence and say something
        for node in _tree().body:
            if isinstance(node, ast.FunctionDef) and node.name in API:
                doc = " ".join((ast.get_docstring(node) or "").split("\n\n")[0].split())
                m = re.match(r"(.+?\.)(\s|$)", doc)
                first = m.group(1) if m else doc
                with self.subTest(helper=node.name):
                    self.assertLessEqual(len(first), 170, first)
                    self.assertGreater(len(first), 40, first)
                    self.assertFalse(first.endswith("..."), first)

    def test_top_level_imports_from_atech_cad(self):
        # atech_cad star-imports this file at its END (R230): at import time
        # only names that exist by then may be taken from it
        for node in _tree().body:
            if isinstance(node, ast.ImportFrom) and node.module == "atech_cad":
                got = sorted(a.name for a in node.names)
                self.assertTrue(set(got) <= {"CadError", "V", "measure", "fillet_safe"}, got)


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class AtechDetail(unittest.TestCase):
    def test_helpers_closed_form(self):
        out = fc(os.path.join(HERE, "fc_atech_detail.py"))
        self.assertIn("ATECH_DETAIL_TESTS=0", out,
                      "\n".join(l for l in out.splitlines() if l.startswith("FAIL"))
                      or out[-4000:])

    def test_sabotage_is_caught(self):
        for gate in ("fillet", "hex", "wall", "breach", "overlap", "surface", "meets", "rim",
                     "offset", "probe", "onewall", "workface", "madeaxis", "riblen"):
            with self.subTest(gate=gate):
                out = fc(os.path.join(HERE, "fc_atech_detail.py"),
                         {"ATECH_DETAIL_SABOTAGE": gate})
                self.assertIn("ATECH_DETAIL_TESTS=", out, out[-2000:])
                self.assertNotIn("ATECH_DETAIL_TESTS=0", out,
                                 "sabotaged %r gate went unnoticed" % gate)


IMPORT_PROBE = r'''
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, %(kit)r)
if %(detail_first)r:
    import atech_detail
import atech_cad as cad
import atech_detail as det
print("IMPORT_PROBE=%%s" %% ",".join([
    str(all(hasattr(cad, n) for n in det.__all__)),
    str(cad.CadError is det.CadError),
    str(cad.color("rubber") == det.MATERIALS["rubber"]["ShapeColor"]),
]))
'''


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class ImportPattern(unittest.TestCase):
    """atech_cad.py will end with `from atech_detail import *`: a scratch
    copy of the kit with that line appended imports in both orders."""

    def test_both_orders(self):
        tmp = tempfile.mkdtemp(prefix="atech-detail-import-")
        try:
            for f in ("atech_cad.py", "atech_detail.py"):
                shutil.copy(os.path.join(KIT, f), tmp)
            with open(os.path.join(tmp, "atech_cad.py"), "a", encoding="utf-8") as fh:
                fh.write("\n\nfrom atech_detail import *  # noqa: E402,F401,F403\n")
            for first in (False, True):
                probe = os.path.join(tmp, "probe_%d.py" % first)
                with open(probe, "w", encoding="utf-8") as fh:
                    fh.write(IMPORT_PROBE % {"kit": tmp, "detail_first": first})
                out = fc(probe)
                with self.subTest(detail_first=first):
                    self.assertIn("IMPORT_PROBE=True,True,True", out, out[-2000:])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


COLOR_MODEL = '''import Part
import atech_detail as det
a = doc.addObject("Part::Feature", "Tyre")
a.Shape = Part.makeCylinder(5, 3)
a.ViewObject.ShapeColor = det.color("rubber")
b = doc.addObject("Part::Feature", "Glass")
b.Shape = Part.makeBox(4, 4, 1, App.Vector(20, 0, 0))
b.ViewObject.ShapeColor = det.color("glass")
b.ViewObject.Transparency = det.transparency("glass")
c = doc.addObject("Part::Feature", "Lens")
c.Shape = det.lens(5, 3, at=(40, 0, 0))
c.ViewObject.Transparency = 60
'''


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class ColourRecording(unittest.TestCase):
    def test_R240_color_calls_are_recorded_with_values(self):
        ws = tempfile.mkdtemp(prefix="atech-detail-colour-")
        try:
            with open(os.path.join(ws, "model.py"), "w", encoding="utf-8") as fh:
                fh.write(COLOR_MODEL)
            out = fc(os.path.join(KIT, "check.py"),
                     {"ATECH_CHECK_SCRIPT": os.path.join(ws, "model.py"),
                      "ATECH_CHECK_PNG": ""})
            line = [l for l in out.splitlines() if l.startswith("ATECH_CHECK=")]
            self.assertTrue(line, out[-3000:])
            r = json.loads(line[-1][len("ATECH_CHECK="):])
            self.assertTrue(r["ok"], r.get("error"))
            view = {o["label"]: o.get("view") for o in r["objects"]}
            self.assertEqual(view["Tyre"], {"ShapeColor": [0.10, 0.10, 0.11]})
            self.assertEqual(view["Glass"], {"ShapeColor": [0.62, 0.78, 0.88],
                                             "Transparency": 60})
            self.assertEqual(view["Lens"], {"Transparency": 60})
        finally:
            shutil.rmtree(ws, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
