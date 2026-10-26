"""R600: the quality prompt is DESIGN-FIRST and lean (the user, 2026-10-26:
"I think it overfits too much to be a box now").

Launch run 2 (docs/verification/eval/launch_launch_2): the weather
station's main body was a rounded slab; the toy car agent spent its whole
level reading check.py / atech_geom.py and grepping "ARCHETYPE", "vehicle"
and "size_mm" to pass the gates and never designed anything; the rendered
system prompt was about 57 KB of layered rules.

    R600  the order of emphasis: 1. DESIGN THE PRODUCT, NOT A CASE (the
          silhouette from what the product is; the Atech hardware INSIDE,
          a minimum pocket, never the outline; a bounding-box-plus-wall
          body or a slab is a failure; the board orientation suits the
          form; modules cabled where the design needs them), 2. FIT THE
          REAL HARDWARE (hard constraints, atech_fit's numbers), 3. DETAIL
          AND FINISH. "Never read check.py or atech_geom.py". The seeded
          example is hardware / fit code to keep, its silhouette
          redesigned freely. No archetype minimums, no "a plain product is
          shippable", no ARCHETYPE GATE.
    R601  the budget: an electronics quality turn's prompt is at most
          PROMPT_MAX characters (both the design levels and the one-turn
          variant), with the panel's REFERENCE FILES lines on top.

Each rule has a sabotage case. System Python with the stubbed package of
test_claude_cli (the API card stubbed at its full 4000-character cap); the
real render (the bundled freecadcmd and the Atech library) runs when
ATECH_FREECADCMD and ATECH_ARTIFACTS point at them.

RUN
    cd addon/AcadAgent/tests && python3 -m unittest test_design_first_r600 -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from test_quality_mode import _Mode, _flat, build  # noqa: E402

HW_ENV = "ATECH_HARDWARE_MODE"
#: R601: the most characters an electronics quality turn's prompt may have.
PROMPT_MAX = 32000
#: What panel._turn_args appends (the REFERENCE FILES lines and the
#: traceback note: about 450 characters with the eval's long paths).
PANEL_SUFFIX = 700

DESIGN_FIRST = [
    ("design head", "1. DESIGN THE PRODUCT, NOT A CASE"),
    ("from the product", "Its silhouette, proportions, stance and character "
                         "come from what it is and from the user's words"),
    ("car", "A car is long and low with a wheel at each corner, arches over "
            "them, a nose, a cabin and a tail"),
    ("lamp", "a lamp has a base, an arm and a shade"),
    ("inside", "The Atech board and modules live INSIDE and never set the "
               "outer shape"),
    ("pocket", "the hardware sets a minimum inner pocket, nothing more"),
    ("box is a failure", "A body that is the board's bounding box plus a "
                         "wall, or a slab, is a failure"),
    ("orientation", "Choose the board orientation to suit the form"),
    ("not the board", "not the form to suit the board"),
    ("cable", "Put modules where the design needs them with ap.cable"),
    ("fit head", "2. FIT THE REAL HARDWARE - hard constraints"),
    ("board held", "BOARD HELD, NO RATTLE"),
    ("modules retained", "MODULES RETAINED"),
    ("faces open", "WORKING FACES OPEN"),
    ("usb-c", "USB-C REACHABLE"),
    ("cables", "CABLES IN CHANNELS"),
    ("printable", "PRINTABLE: each part has one flat bed face"),
    ("desk", "rests at z = 0"),
    ("detail head", "3. DETAIL AND FINISH"),
    ("never read the checker", "Never read check.py or atech_geom.py: "
                               "./check's output says what fails and how to "
                               "fix it."),
]
SEEDED = [
    ("seed: keep", "KEEP its hardware and fit code"),
    ("seed: redesign", "REDESIGN the silhouette freely for this request"),
]
#: What pushed toward boxes or checker-gaming, removed by R600.
GONE = ["A plain product that meets all of that is shippable",
        "ARCHETYPE FIRST", "ARCHETYPE GATE", "with its minimum size",
        "1.8-2.5 x the width", "40 % of the height", "40 % of the front face",
        "60 % of the front", "height 1.2 x the width", "RESTYLE it",
        "restyle here", "THE FIT PROCEDURE", "reference/kit/check.py",
        "reference/kit/atech_geom.py"]
ORDER = ["design head", "fit head", "detail head"]


def misses(prompt, seeded=False):
    flat = _flat(prompt)
    out = [n for n, needle in DESIGN_FIRST + (SEEDED if seeded else [])
           if _flat(needle) not in flat]
    out += ["gone: " + g for g in GONE if _flat(g) in flat]
    if not out:
        at = [flat.index(_flat(dict(DESIGN_FIRST)[n])) for n in ORDER]
        if at != sorted(at):
            out.append("order")
    return out


class _Electronics(_Mode):
    MODE = "quality"

    def setUp(self):
        super().setUp()
        self._hw = os.environ.get(HW_ENV)
        os.environ[HW_ENV] = "electronics"
        self.patch(build, "library_available", lambda refresh=False: True)
        # the generated card at its full cap: the worst case for the budget
        self.patch(build, "_generated_card",
                   lambda: ("ATECH API CARD (stub)\n" + "x" * 75 + "\n") * 50)
        self.patch(build, "assembly_doc", lambda: None)
        self.patch(build, "kit_reference", lambda name: True)
        build._CARD = None
        self.tmp = tempfile.mkdtemp(prefix="r600-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        if self._hw is None:
            os.environ.pop(HW_ENV, None)
        else:
            os.environ[HW_ENV] = self._hw
        super().tearDown()

    def level_prompt(self, request="I want a car"):
        ws = tempfile.mkdtemp(dir=self.tmp)
        ladder, seed = build.start_levels(ws, request, True)
        return build.quality_prompt(ws, True, ladder, seed), seed

    def one_turn_prompt(self, request="I want a car"):
        os.environ["ATECH_PROMPT_OFF"] = "levels"
        try:
            ws = tempfile.mkdtemp(dir=self.tmp)
            return build.system_prompt(ws, request=request, atech=True)
        finally:
            os.environ.pop("ATECH_PROMPT_OFF", None)


class TestR600DesignFirst(_Electronics):

    def test_r600_both_variants_are_design_first(self):
        self.assertTrue(build.board_default())
        sp, seed = self.level_prompt()
        self.assertEqual(seed, "toy_car.py")
        self.assertEqual(misses(sp, seeded=True), [])
        self.assertEqual(misses(self.one_turn_prompt()), [])
        self.assertNotRegex(sp, r"\{[a-z_]+\}")

    def test_r600_every_seeded_product_is_design_first(self):
        for request in ("a little desk robot", "a desk lamp",
                        "a weather station", "a smart speaker",
                        "a handheld game console"):
            with self.subTest(request=request):
                sp, seed = self.level_prompt(request)
                self.assertTrue(seed, request)
                self.assertEqual(misses(sp, seeded=True), [])

    def test_r600_archetype_words_are_inspiration_only(self):
        flat = _flat(self.level_prompt()[0])
        self.assertIn("Design words by category (inspiration, never rules)",
                      flat)
        self.assertIn("- Design note (advisory, never a gate): vehicle - "
                      "long and low", flat)
        gate = flat[flat.index("GATE: "):][:400]
        self.assertNotIn("Design note", gate)

    def test_r600_sabotage_hardware_half_deleted(self):
        self.patch(build, "HW_DESIGN", "")
        miss = misses(self.level_prompt()[0])
        for name in ("inside", "pocket", "box is a failure", "orientation",
                     "cable"):
            self.assertIn(name, miss)

    def test_r600_sabotage_checker_line_deleted(self):
        self.assertIn("Never read check.py or atech_geom.py",
                      build.QUALITY_PROMPT)
        self.patch(build, "QUALITY_PROMPT", build.QUALITY_PROMPT.replace(
            "Never read check.py or atech_geom.py", ""))
        self.assertIn("never read the checker", misses(self.level_prompt()[0]))

    def test_r600_sabotage_shippable_line_back(self):
        self.patch(build, "ATECH_FIT_HEAD", build.ATECH_FIT_HEAD + (
            "A plain product that meets all of that is shippable.\n"))
        self.assertIn("gone: A plain product that meets all of that is "
                      "shippable", misses(self.level_prompt()[0]))

    def test_r600_sabotage_fit_before_design(self):
        t = build.QUALITY_PROMPT
        a, b = t.index("1. DESIGN THE PRODUCT"), t.index("{fit_head}")
        moved = t[:a] + "{fit_head}" + t[a:b] + t[b + len("{fit_head}"):]
        self.patch(build, "QUALITY_PROMPT", moved)
        self.assertIn("order", misses(self.level_prompt()[0]))


class TestR601Budget(_Electronics):

    def test_r601_electronics_turn_within_the_budget(self):
        lv, _seed = self.level_prompt()
        one = self.one_turn_prompt()
        sys.stderr.write("\n  [R601] levels %d chars, one-turn %d (+%d panel)"
                         "\n" % (len(lv), len(one), PANEL_SUFFIX))
        self.assertLessEqual(len(lv) + PANEL_SUFFIX, PROMPT_MAX)
        self.assertLessEqual(len(one) + PANEL_SUFFIX, PROMPT_MAX)

    def test_r601_sabotage_a_long_essay_breaks_it(self):
        self.patch(build, "REAL_WORLD", build.REAL_WORLD + "x" * 20000 + "\n")
        self.assertGreater(len(self.level_prompt()[0]) + PANEL_SUFFIX,
                           PROMPT_MAX)


FC = os.environ.get("ATECH_FREECADCMD")
ARTIFACTS = os.environ.get("ATECH_ARTIFACTS")
RENDER = r'''
import json, os, sys, tempfile
sys.path.insert(0, %(addon)r)
from acadagent import build, settings
settings.CONFIG_DIR = tempfile.mkdtemp(prefix="r600-cfg-")
settings.CONFIG_PATH = os.path.join(settings.CONFIG_DIR, "settings.json")
import FreeCAD as App
out = {}
for off in ("", "levels"):
    os.environ["ATECH_PROMPT_OFF"] = off
    build._CARD = None
    ws = tempfile.mkdtemp(prefix="r600-ws-")
    sp = build.system_prompt(ws, request="I want a car", atech=True,
                             doc=App.newDocument("Unnamed"))
    out[off or "levels_on"] = {"len": len(sp), "text": sp,
                               "board_default": build.board_default()}
print("R600JSON=" + json.dumps(out))
'''


@unittest.skipUnless(FC and ARTIFACTS and os.path.exists(FC),
                     "ATECH_FREECADCMD / ATECH_ARTIFACTS not set")
class TestR601RealRender(unittest.TestCase):
    """The real prompt for "I want a car" in CAD + electronics mode: the
    bundled freecadcmd, the real kit, card and library."""

    def test_r601_real_car_prompt(self):
        d = tempfile.mkdtemp(prefix="r600-fc-")
        try:
            p = os.path.join(d, "render.py")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(RENDER % {"addon": os.path.dirname(HERE)})
            env = dict(os.environ, ATECH_HARDWARE_MODE="electronics",
                       ATECH_PROMPT_MODE="quality", HOME=d)
            r = subprocess.run([FC, p], env=env, capture_output=True,
                               text=True, timeout=600, cwd=d)
            line = [ln for ln in (r.stdout + r.stderr).splitlines()
                    if ln.startswith("R600JSON=")]
            self.assertTrue(line, (r.stdout + r.stderr)[-3000:])
            got = json.loads(line[-1][len("R600JSON="):])
        finally:
            shutil.rmtree(d, ignore_errors=True)
        for key, row in got.items():
            with self.subTest(variant=key):
                self.assertTrue(row["board_default"])
                sys.stderr.write("\n  [R601] real %s: %d chars\n"
                                 % (key, row["len"]))
                self.assertLessEqual(row["len"] + PANEL_SUFFIX, PROMPT_MAX)
                self.assertEqual(misses(row["text"],
                                        seeded=key == "levels_on"), [])
                self.assertIn("ATECH API CARD (generated; mm)", row["text"])
                self.assertIn("FIT NUMBERS.", row["text"])


if __name__ == "__main__":
    unittest.main()
