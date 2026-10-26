"""agent_kit/atech_form.py (R230): sculpted-body helpers.

    cd addon/AcadAgent/tests && python3 -m unittest test_kit_form

Runs fc_atech_form.py inside the bundled freecadcmd (closed-form volumes,
validity, timings) plus its sabotage run, and checks the re-export pattern
atech_cad.py uses (`from atech_form import *` at its END) in both import
orders. Skips without freecadcmd (set ATECH_FREECADCMD); the source checks
need no FreeCAD.
"""
import ast
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
FORM = os.path.join(KIT, "atech_form.py")
FC = sandbox.find_freecadcmd()
if FC is None and os.environ.get("ATECH_REQUIRE_FREECADCMD") == "1":
    raise RuntimeError("ATECH_REQUIRE_FREECADCMD=1 but no freecadcmd was found "
                       "(set ATECH_FREECADCMD)")

AGREED = {
    "spline_wire": "points, closed=True, plane='XZ'",
    "rounded_rect_wire": "w, h, r, center=(0, 0, 0), normal='Z'",
    "profile_body": "side, plan, spline=True, fillet=None, at=(0, 0, 0), inset=0.0",
    "loft": "sections, ruled=False, closed=False, solid=True",
    "extrude_profile": "wire_or_points, height, taper_deg=0, direction='+Z'",
    "hollow": "shape, t, open_faces=(), core=None",
    "pipe": "path_pts, r=None, profile=None, spline=True, frenet=False, caps='round'",
    "revolve_profile": "points_xz, angle=360, spline=False, axis='Z', at=(0, 0, 0)",
    "mirror": "shape, plane='XZ', through=(0, 0, 0)",
    "symmetric": "shape, plane='XZ', through=(0, 0, 0)",
    "mirror_pair": "shape, plane='XZ', through=(0, 0, 0)",
    "split": "body, plane_axis='Z', at=None, lip=0.0, clearance=0.2",
}


def fc(script, env=None, timeout=600):
    e = dict(os.environ, **(env or {}))
    p = subprocess.run([FC, script], env=e, capture_output=True, text=True,
                       timeout=timeout, cwd=tempfile.gettempdir())
    return p.stdout + p.stderr


class FormSource(unittest.TestCase):
    """No FreeCAD needed (R230)."""

    def setUp(self):
        with open(FORM, encoding="utf-8") as fh:
            self.src = fh.read()
        self.tree = ast.parse(self.src)

    def test_agreed_signatures_on_the_card(self):
        names = [e.value for n in self.tree.body if isinstance(n, ast.Assign)
                 and any(getattr(t, "id", None) == "__all__" for t in n.targets)
                 for e in n.value.elts]
        self.assertEqual(sorted(names), sorted(AGREED))
        fns = {n.name: n for n in self.tree.body if isinstance(n, ast.FunctionDef)}
        for name, sig in AGREED.items():
            with self.subTest(helper=name):
                self.assertEqual(ast.unparse(fns[name].args), sig)
                # build.helper_card(): first sentence = up to the first ". ",
                # cut at 170 chars - it must be whole
                doc = " ".join(ast.get_docstring(fns[name]).split("\n\n")[0].split())
                m = re.match(r"(.+?\.)(\s|$)", doc)
                first = m.group(1) if m else doc
                self.assertLessEqual(len(first), 170, first)

    def test_no_atech_cad_import_at_module_top(self):
        # atech_cad does `from atech_form import *` at its end: a top-level
        # `import atech_cad` here would run half-built (R230)
        for n in self.tree.body:
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                mods = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module]
                self.assertNotIn("atech_cad", mods)


REEXPORT = r'''
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, %(tmp)r)
sys.path.insert(1, %(kit)r)
first = %(first)r
if first == "form":
    import atech_form
import atech_cad as cad
import atech_form as form
ok = all(getattr(cad, n, None) is getattr(form, n) for n in form.__all__)
try:
    cad.rounded_rect_wire(10, 10, 6)
    raised = "no"
except cad.CadError:
    raised = "CadError"
except Exception as exc:
    raised = type(exc).__name__
b = cad.profile_body([(0, 0), ("line", (10, 0)), ("line", (10, 5)), ("line", (0, 5))],
                     [(0, -2), ("line", (10, -2)), ("line", (10, 2)), ("line", (0, 2))],
                     spline=False)
print("REEXPORT ok=%%s raised=%%s vol=%%.3f" %% (ok, raised, b.Volume))
'''


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class Form(unittest.TestCase):
    def test_helpers_closed_form(self):
        out = fc(os.path.join(HERE, "fc_atech_form.py"))
        self.assertIn("ATECH_FORM_TESTS=0", out, out[-4000:])

    def test_sabotage_is_caught(self):
        # "1": extrude_profile 5 % short; the rest are the R250 gates
        for gate in ("1", "coremin", "corefallback", "rimwall", "nudge"):
            with self.subTest(gate=gate):
                out = fc(os.path.join(HERE, "fc_atech_form.py"),
                         {"ATECH_FORM_SABOTAGE": gate})
                self.assertIn("ATECH_FORM_TESTS=", out, out[-2000:])
                self.assertNotIn("ATECH_FORM_TESTS=0", out,
                                 "sabotaged %r gate went unnoticed" % gate)

    def test_reexport_from_atech_cad_both_orders(self):
        # the pattern atech_cad.py adopts: `from atech_form import *` as its
        # LAST line - on a scratch copy, so this holds before and after
        tmp = tempfile.mkdtemp(prefix="atech-form-reexport-")
        try:
            with open(os.path.join(KIT, "atech_cad.py"), encoding="utf-8") as fh:
                src = fh.read()
            if "from atech_form import *" not in src:
                src += "\nfrom atech_form import *  # noqa: F401,F403,E402\n"
            with open(os.path.join(tmp, "atech_cad.py"), "w", encoding="utf-8") as fh:
                fh.write(src)
            for first in ("cad", "form"):
                with self.subTest(first=first):
                    script = os.path.join(tmp, "probe_%s.py" % first)
                    with open(script, "w", encoding="utf-8") as fh:
                        fh.write(REEXPORT % {"tmp": tmp, "kit": KIT, "first": first})
                    out = fc(script, timeout=120)
                    self.assertIn("REEXPORT ok=True raised=CadError vol=200.000", out,
                                  out[-3000:])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
