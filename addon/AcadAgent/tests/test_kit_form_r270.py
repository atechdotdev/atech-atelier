"""R270: the never-fail body path (atech_form / atech_detail / atech_cad).

    cd addon/AcadAgent/tests && python3 -m unittest test_kit_form_r270

Source checks need no FreeCAD: the new helpers are on the helper card with
the agreed signatures, the R230 card (test_kit_form.AGREED) is unchanged,
cad.cut keeps its strict default, the pure-Python inflection counter.
With freecadcmd (ATECH_FREECADCMD): fc_atech_form.py / fc_atech_detail.py
run their R270 cases (ATECH_*_ONLY=r270), then once per R270 sabotage gate -
each gate switches one new fallback off and its case must FAIL.
"""
import ast
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
sys.path.insert(0, ADDON)

from acadagent import sandbox  # noqa: E402

KIT = sandbox.KIT_DIR
FC = sandbox.find_freecadcmd()

FORM_GATES = ("fillet_all", "fillet_sharp", "fillet_split", "fillet_shrink", "fillet_soften",
              "fillet_unfilleted", "hollow_profile", "hollow_fitted", "hollow_thick",
              "split_lip0", "split_nudge", "offset_polygon", "fair", "tangent", "guard",
              "g1", "cut_optional")
DETAIL_GATES = ("cusp", "local", "guard")


def _tree(name):
    with open(os.path.join(KIT, name), encoding="utf-8") as fh:
        return ast.parse(fh.read())


def _all_names(tree, augmented=True):
    """String literals of `__all__ = [...]` (and `__all__ += [...]`)."""
    out = []
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "__all__"
                                             for t in n.targets):
            out += [e.value for e in n.value.elts]
        elif augmented and isinstance(n, ast.AugAssign) and getattr(
                n.target, "id", None) == "__all__":
            out += [e.value for e in ast.walk(n.value)
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return out


def _fn(tree, name):
    return [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name][0]


def _first_sentence(fn):
    doc = " ".join(ast.get_docstring(fn).split("\n\n")[0].split())
    m = re.match(r"(.+?\.)(\s|$)", doc)
    return m.group(1) if m else doc


class Source(unittest.TestCase):
    """No FreeCAD needed (R270)."""

    def test_new_helpers_and_signatures(self):
        form, detail, cad = _tree("atech_form.py"), _tree("atech_detail.py"), _tree("atech_cad.py")
        self.assertIn("shell_body", _all_names(form))
        # the R230 card list (an Assign) stays exactly what test_kit_form agrees
        self.assertNotIn("shell_body", _all_names(form, augmented=False))
        self.assertIn("inlay", _all_names(detail))
        for tree, name, sig in (
                (form, "shell_body", "side, plan, wall, split_z=None, lip=1.2, fillet=None"),
                (detail, "inlay", "shape, outline, depth=None, flange=0.8"),
                (cad, "cut", "shape, *tools, optional=False"),
                (form, "hollow", "shape, t, open_faces=(), core=None"),
                (form, "split", "body, plane_axis='Z', at=None, lip=0.0, clearance=0.2"),
                (form, "profile_body",
                 "side, plan, spline=True, fillet=None, at=(0, 0, 0), inset=0.0")):
            with self.subTest(helper=name):
                fn = _fn(tree, name)
                self.assertEqual(ast.unparse(fn.args), sig)
                first = _first_sentence(fn)
                self.assertLessEqual(len(first), 170, first)     # build.helper_card's cut
                self.assertGreater(len(first), 40, first)

    def test_helper_card_lists_them(self):
        from acadagent import build
        build._HELPERS = None
        card = build.helper_card()
        text = card if isinstance(card, str) else "\n".join(map(str, card))
        self.assertIn("shell_body(side, plan, wall, split_z=None, lip=1.2, fillet=None)", text)
        self.assertIn("inlay(shape, outline, depth=None, flange=0.8)", text)

    def test_r270_ids_in_the_kit(self):
        for name in ("atech_form.py", "atech_detail.py", "atech_cad.py"):
            with open(os.path.join(KIT, name), encoding="utf-8") as fh:
                self.assertIn("R270", fh.read(), name)

    def test_cut_default_stays_strict(self):
        with open(os.path.join(KIT, "atech_cad.py"), encoding="utf-8") as fh:
            src = fh.read()
        body = src[src.index("def cut(shape, *tools, optional=False):"):]
        body = body[:body.index("\ndef ")]
        self.assertIn("if optional:", body)
        self.assertIn('raise CadError("cut: the tools removed nothing', body)

    def test_count_flips_pure(self):
        # atech_form._count_flips: the inflection counter behind the
        # "outline not fair" NOTE (exec'd alone: the module needs FreeCAD)
        fn = _fn(_tree("atech_form.py"), "_count_flips")
        ns = {}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "atech_form", "exec"), ns)
        count = ns["_count_flips"]
        self.assertEqual(count([], True), 0)
        self.assertEqual(count([1, 1, 1, 1], True), 0)
        self.assertEqual(count([1, 1, -1, -1], False), 1)
        self.assertEqual(count([1, 1, -1, -1], True), 2)           # wraps round
        self.assertEqual(count([1, -1, 1, -1, 1], False), 4)

    def test_guard_is_headless_only(self):
        with open(os.path.join(KIT, "atech_form.py"), encoding="utf-8") as fh:
            src = fh.read()
        ok = src[src.index("def _guard_ok():"):]
        ok = ok[:ok.index("\ndef ")]
        self.assertIn("GuiUp", ok)          # a GUI process is never forked
        self.assertIn('hasattr(os, "fork")', ok)
        self.assertIn("ATECH_FORM_NOFORK", ok)


def fc(script, env, timeout=1500):
    e = dict(os.environ, **env)
    p = subprocess.run([FC, script], env=e, capture_output=True, text=True,
                       timeout=timeout, cwd=tempfile.gettempdir())
    return p.stdout + p.stderr


def _fails(out):
    return "\n".join(l for l in out.splitlines() if l.startswith("FAIL"))


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class FormR270(unittest.TestCase):
    SCRIPT = os.path.join(HERE, "fc_atech_form.py")

    def test_r270_cases(self):
        out = fc(self.SCRIPT, {"ATECH_FORM_ONLY": "r270"})
        self.assertIn("ATECH_FORM_TESTS=0", out, _fails(out) or out[-4000:])

    def test_r270_sabotage_is_caught(self):
        for gate in FORM_GATES:
            with self.subTest(gate=gate):
                out = fc(self.SCRIPT, {"ATECH_FORM_ONLY": "r270", "ATECH_FORM_SABOTAGE": gate})
                self.assertIn("ATECH_FORM_TESTS=", out, out[-2000:])
                self.assertNotIn("ATECH_FORM_TESTS=0", out,
                                 "sabotaged %r gate went unnoticed" % gate)


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class DetailR270(unittest.TestCase):
    SCRIPT = os.path.join(HERE, "fc_atech_detail.py")

    def test_r270_cases(self):
        out = fc(self.SCRIPT, {"ATECH_DETAIL_ONLY": "r270"})
        self.assertIn("ATECH_DETAIL_TESTS=0", out, _fails(out) or out[-4000:])

    def test_r270_sabotage_is_caught(self):
        for gate in DETAIL_GATES:
            with self.subTest(gate=gate):
                out = fc(self.SCRIPT, {"ATECH_DETAIL_ONLY": "r270",
                                       "ATECH_DETAIL_SABOTAGE": gate})
                self.assertIn("ATECH_DETAIL_TESTS=", out, out[-2000:])
                self.assertNotIn("ATECH_DETAIL_TESTS=0", out,
                                 "sabotaged %r gate went unnoticed" % gate)


if __name__ == "__main__":
    unittest.main()
