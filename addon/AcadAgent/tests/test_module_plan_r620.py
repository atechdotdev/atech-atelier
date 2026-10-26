"""R620: the MODULE PLAN (the user, 2026-10-26: "mix relevant atech modules
with the 3D cad and use wires to put things like eyes or motors at
different places").

    atech_levels   module_plan=True adds the MODULE PLAN to LEVEL 1's
                   checklist and LEVEL 2's checklist and gate; without it
                   every level's text is unchanged (the pinned sha256s of
                   test_levels_seeded_r280 still hold)
    build          _level_values carries module_plan while products house
                   the board; the quality prompt's design section asks for
                   eyes and motors cabled to their places; the switch
                   "module_plan" takes all of it out

System Python.

RUN
    cd addon/AcadAgent/tests && python3 -m unittest test_module_plan_r620 -v
"""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.dirname(HERE))

from test_quality_mode import _Mode, _flat, build  # noqa: E402

KIT = os.path.join(os.path.dirname(HERE), "acadagent", "agent_kit")
sys.path.insert(0, KIT)
import atech_levels as lv  # noqa: E402


class LevelText(unittest.TestCase):

    def test_plan_in_level_one_and_two_only(self):
        for seed in (None, "toy_car.py"):
            with self.subTest(seed=seed):
                one = _flat(lv.level_text(1, seed=seed, module_plan=True))
                self.assertIn("MODULE PLAN in the brief", one)
                self.assertIn("dc_motor at the wheel", one)
                self.assertIn("ap.cable", one)
                two = lv.level_text(2, seed=seed, module_plan=True)
                self.assertIn("every module in the MODULE PLAN", _flat(two))
                gate = two.split("GATE: ", 1)[1]
                self.assertIn("the cabled ones at their features", gate)
                for n in range(3, lv.COUNT + 1):
                    self.assertEqual(lv.level_text(n, seed=seed, module_plan=True),
                                     lv.level_text(n, seed=seed))

    def test_off_by_default(self):
        for n in range(1, lv.COUNT + 1):
            self.assertNotIn("MODULE PLAN", lv.level_text(n))
            self.assertNotIn("MODULE PLAN", lv.level_message(n, seed="toy_car.py"))

    def test_advance_passes_it_on(self):
        ws = tempfile.mkdtemp(prefix="r620-")
        self.addCleanup(shutil.rmtree, ws, True)
        lv.write(ws, 1, "toy_car.py")
        self.assertIn("MODULE PLAN", lv.advance(ws, module_plan=True))


class Prompt(_Mode):
    MODE = "quality"

    def setUp(self):
        super().setUp()
        self.atech_library()
        self.patch(build, "board_default", lambda: True)

    def _prompt(self, off=None):
        if off is not None:
            os.environ["ATECH_PROMPT_OFF"] = off
        ws = tempfile.mkdtemp(prefix="r620-")
        self.addCleanup(shutil.rmtree, ws, True)
        ladder, seed = build.start_levels(ws, "a little robot", True)
        return _flat(build.quality_prompt(ws, True, ladder, seed))

    def test_on(self):
        self.assertTrue(build._level_values()["module_plan"])
        sp = self._prompt()
        self.assertIn("Mix the Atech modules into the design", sp)
        self.assertIn("MODULE PLAN in the brief", sp)
        self.assertIn("a distance sensor as eyes", sp)

    def test_switch_takes_it_out(self):
        sp = self._prompt(off="module_plan")
        self.assertFalse(build._level_values()["module_plan"])
        self.assertNotIn("Mix the Atech modules", sp)
        self.assertNotIn("MODULE PLAN", sp)

    def test_cad_only_has_no_plan(self):
        self.patch(build, "board_default", lambda: False)
        self.assertFalse(build._level_values()["module_plan"])


if __name__ == "__main__":
    unittest.main()
