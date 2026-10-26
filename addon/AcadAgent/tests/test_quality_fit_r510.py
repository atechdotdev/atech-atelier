"""R510-R511: the quality prompt is about results, and it carries the
Atech fit knowledge inline (the user, 2026-10-20).

    R510  "It's about results, not how long it takes": no stage minutes, no
          stop minute, no brief time ("decide, do not deliberate"), no
          "never plan for minutes in silence", no level TIME line or
          "past N min add nothing new" - in the one-turn prompt, the level
          prompt and every level message (build.next_level). The process
          that is not about time stays: stages end on a passing ./check,
          keep the last passing build, one feature per edit, review rounds.
          The panel never ends a turn on time.
    R511  "It should custom fit Atech modules right, and be aware of that
          in context": a quality turn in CAD + electronics mode
          (build.board_default()) carries the fit inline - R600: section 2,
          FIT THE REAL HARDWARE, a compact checklist of hard constraints
          (orient, pocket, board held, modules retained, working faces,
          USB-C, cables, assembly and closing, printable) with
          atech_fit.prompt_values() inline, then atech_fit's FIT NUMBERS
          tables A-D (B: the per-module working faces) after the API card.
          Only CAD mode and fast mode have none of it.

Each item has a sabotage case. System Python, no FreeCAD (the stubbed
package of test_claude_cli), like test_quality_prompt_r270.

RUN
    cd addon/AcadAgent/tests && python3 -m unittest test_quality_fit_r510 -v
"""
import os
import re
import sys
import tempfile
import shutil
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from test_quality_mode import _Mode, _flat, build  # noqa: E402

KIT = os.path.join(os.path.dirname(HERE), "acadagent", "agent_kit")
sys.path.insert(0, KIT)
import atech_fit  # noqa: E402

HW_ENV = "ATECH_HARDWARE_MODE"
#: R600: section 2 of a quality + electronics prompt, and its checklist.
FIT_HEAD = "2. FIT THE REAL HARDWARE - hard constraints"
FIT_ITEMS = ("- ORIENT before any ap.seat", "- POCKET:",
             "- BOARD HELD, NO RATTLE", "- MODULES RETAINED",
             "- WORKING FACES OPEN:", "- USB-C REACHABLE:",
             "- CABLES IN CHANNELS:", "- ASSEMBLY AND CLOSING:",
             "- PRINTABLE:")
TIME_WORDS = ("TURN CLOCK", "add nothing new", "do not deliberate",
              "Decide, do not deliberate", "minutes in silence", "by about",
              "Count the minutes", "TIME: about")


def time_hits(text):
    flat = _flat(text)
    hits = [w for w in TIME_WORDS if w in flat]
    # a bare "<n> min" (the one technical fact "./check slows to 3 min" aside)
    rest = flat.replace("slows to 3 min", "")
    hits += re.findall(r"\b\d+ min\b", rest)
    return hits


class _Fit(_Mode):
    MODE = "quality"

    def setUp(self):
        super().setUp()
        self._hw = os.environ.get(HW_ENV)
        os.environ[HW_ENV] = "electronics"
        self.patch(build, "library_available", lambda refresh=False: True)
        self.patch(build, "_generated_card", lambda: "ATECH API CARD (stub)")
        self.patch(build, "assembly_doc", lambda: None)
        build._CARD = None
        self.tmp = tempfile.mkdtemp(prefix="r510-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        if self._hw is None:
            os.environ.pop(HW_ENV, None)
        else:
            os.environ[HW_ENV] = self._hw
        super().tearDown()

    def ws(self):
        return tempfile.mkdtemp(dir=self.tmp)

    def level_prompt(self, request="a toy car"):
        ws = self.ws()
        ladder, seed = build.start_levels(ws, request, True)
        return build.quality_prompt(ws, True, ladder, seed), ws

    def one_turn_prompt(self, request="a toy car"):
        os.environ["ATECH_PROMPT_OFF"] = "levels"
        try:
            return build.system_prompt(self.ws(), request=request, atech=True)
        finally:
            os.environ.pop("ATECH_PROMPT_OFF", None)


class TestR511FitInline(_Fit):

    def test_r511_present_in_electronics_mode(self):
        self.assertTrue(build.board_default())
        for sp in (self.level_prompt()[0], self.one_turn_prompt()):
            flat = _flat(sp)
            # R600: the procedure is a compact checklist, section 2
            self.assertIn(FIT_HEAD, flat)
            for step in FIT_ITEMS:
                self.assertIn(step, flat)
            # ... after the design, before the detail
            self.assertLess(flat.index("1. DESIGN THE PRODUCT, NOT A CASE"),
                            flat.index(FIT_HEAD))
            self.assertLess(flat.index(FIT_HEAD),
                            flat.index("3. DETAIL AND FINISH"))
            self.assertIn(_flat(atech_fit.render_tables()), flat)
            self.assertIn("B. Working faces", flat)
            for mod in ("screen", "distance_sensor", "light", "button",
                        "speaker", "microphone", "temp_humidity", "dc_motor"):
                self.assertIn("- %s: " % mod, sp)
            self.assertNotRegex(sp, r"\{[a-z_]+\}")

    def test_r511_numbers_come_from_atech_fit(self):
        v = atech_fit.prompt_values()
        flat = _flat(build.atech_fit_section())
        for needle in ("HW + %s per side" % v["slide"],
                       "a printed stop %s mm off every" % v["stop"],
                       "%s r %s through the full wall" % (v["usbc_open"],
                                                         v["usbc_r"]),
                       "in %s mm channels" % v["ribbon_channel"],
                       "within %s mm" % v["backlash_max"],
                       "%s unless intent.json says otherwise" % v["material"]):
            self.assertIn(needle, flat)
        # Sabotage: a changed FIT value shows up in the prompt - it is
        # rendered from atech_fit, never typed.
        saved = atech_fit.FIT["stop"]
        atech_fit.FIT["stop"] = (0.35, saved[1], saved[2])
        try:
            flat2 = _flat(build.atech_fit_section())
        finally:
            atech_fit.FIT["stop"] = saved
        self.assertIn("a printed stop 0.35 mm off every", flat2)
        self.assertNotIn("a printed stop %s mm off every" % v["stop"], flat2)

    def test_r511_kit_calls_named_only_when_the_kit_has_them(self):
        real = build._kit_helper
        self.patch(build, "_kit_helper",
                   lambda n: True if n in ("stop_walls", "usbc_port")
                   else real(n))
        flat = _flat(build.atech_fit_section())
        self.assertIn("cad.stop_walls(fixed, board, modules)", flat)
        self.assertIn("cad.usbc_port(part, usb_module, board)", flat)
        self.patch(build, "_kit_helper", lambda n: False)
        flat = _flat(build.atech_fit_section())
        self.assertNotIn("cad.stop_walls", flat)
        self.assertNotIn("cad.usbc_port", flat)
        self.assertIn("one straight wall per board edge", flat)

    def test_r511_absent_in_only_cad_mode(self):
        os.environ[HW_ENV] = "cad_only"
        self.assertFalse(build.board_default())
        sp, _ws = self.level_prompt()
        self.assertNotIn(FIT_HEAD, sp)
        self.assertNotIn("FIT NUMBERS", sp)
        # an explicit Atech request in Only CAD mode: still no fit section
        sp = build.quality_prompt(self.ws(), True, None, None)
        self.assertNotIn(FIT_HEAD, sp)

    def test_r511_absent_in_fast_mode(self):
        os.environ["ATECH_PROMPT_MODE"] = "fast"
        sp = build.system_prompt(self.ws(), request="a toy car", atech=True)
        self.assertNotIn(FIT_HEAD, sp)

    def test_r511_sabotage_board_default_off(self):
        self.patch(build, "board_default", lambda: False)
        self.assertNotIn(FIT_HEAD, self.level_prompt()[0])

    def test_r511_length_reported(self):
        n = len(build.atech_fit_section())
        sys.stderr.write("\n  [R511] fit section %d chars; level prompt %d, "
                         "one-turn prompt %d\n"
                         % (n, len(self.level_prompt()[0]),
                            len(self.one_turn_prompt())))
        # R600: a compact checklist, not a 12-step essay
        self.assertGreater(n, 2000)
        self.assertLess(n, 3500)


class TestR510NoTimePressure(_Fit):

    def test_r510_prompts_name_no_minutes(self):
        sp, ws = self.level_prompt()
        self.assertEqual(time_hits(sp), [])
        self.assertEqual(time_hits(self.one_turn_prompt()), [])
        seeded, _ = self.level_prompt("a desk robot")
        self.assertEqual(time_hits(seeded), [])

    def test_r510_level_messages_name_no_minutes(self):
        ws = self.ws()
        ladder, seed = build.start_levels(ws, "a toy car", True)
        self.assertTrue(seed)
        seen = 0
        while True:
            msg = build.next_level(ws)
            if not msg:
                break
            seen += 1
            self.assertEqual(time_hits(msg), [], msg[:200])
        self.assertGreater(seen, 3)

    def test_r510_good_process_stays(self):
        flat = _flat(self.level_prompt()[0])
        for needle in ("End on a passing ./check",
                       "keep the last passing build",
                       "one feature per Edit"):
            self.assertIn(_flat(needle), flat)
        flat = _flat(self.one_turn_prompt())
        for needle in ("End on a passing ./check; keep the last passing build",
                       "REVIEW at least",
                       "never strip the design back to pass"):
            self.assertIn(needle, flat)

    def test_r510_sabotage_untimed_off(self):
        """With build.untimed taken out, the seeded level texts carry the
        TIME line again and the check catches it."""
        self.patch(build, "untimed", lambda text, *a, **k: text)
        sp, _ws = self.level_prompt()
        self.assertTrue(time_hits(sp))


class TestR510PanelHasNoTimeLimit(unittest.TestCase):
    """The in-app panel never ends a turn on time: its watchdogs only
    speak (a waiting line with Retry / Stop), the ladder has no time
    budget (read from the source: the panel needs Qt)."""

    def test_r510_watchdogs_never_stop_a_turn(self):
        import ast
        src = open(os.path.join(os.path.dirname(HERE), "acadagent",
                                "panel.py"), encoding="utf-8").read()
        tree = ast.parse(src)
        fns = {n.name: n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef)}
        for name in ("_check_stall", "_check_build_quiet", "_on_tick",
                     "_send_level", "_reply"):
            body = ast.get_source_segment(src, fns[name])
            # the Stop button is offered (passed), never pressed
            calls = re.findall(r"self\._on_stop\(\)|\.cancel\(\)|"
                               r"requestInterruption\(\)|_cancel_build\(\)",
                               body)
            self.assertEqual(calls, [], name)
            self.assertNotRegex(body, r"TURN_TIMEOUT|over_budget|LADDER_BUDGET")
        # Sabotage: the check sees a stop call when one is there.
        bad = "def _check_stall(self):\n    self._on_stop()\n"
        self.assertTrue(re.findall(r"self\._on_stop\(\)", bad))


if __name__ == "__main__":
    unittest.main()
