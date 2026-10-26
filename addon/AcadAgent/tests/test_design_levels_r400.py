"""R400: the design levels, the seeded fork, the real-world quality bar and
the cad.detail guard.

    atech_levels   the 9 levels (title, studio phase, checklist, gate), the
                   level message and its tail, the workspace marker
                   (read / write / advance / clear, never through a link)
    build          start_levels: a new Atech product in quality mode seeds
                   model.py from atech_fit.fork_for and records LEVEL 1;
                   any other user turn ends the ladder; fix and level turns
                   keep it. next_level advances. quality_prompt puts THE
                   DESIGN LEVELS in place of SHIP IN STAGES / THE WORKFLOW, and
                   every change has its ATECH_PROMPT_OFF switch.
    run_eval       next_level_message / levels_reached drive the same ladder
    cad.detail     a geometry error inside the block is skipped and listed;
                   a code bug still raises (freecadcmd; skipped without it)

System Python except the freecadcmd class.

RUN
    cd addon/AcadAgent/tests && python3 -m unittest test_design_levels_r400 -v
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.dirname(HERE))      # acadagent (sandbox, panel)

from test_quality_mode import _Mode, _flat, build  # noqa: E402

KIT = os.path.join(os.path.dirname(HERE), "acadagent", "agent_kit")
sys.path.insert(0, KIT)
import atech_levels as lv  # noqa: E402

sys.path.insert(0, os.path.join(HERE, "eval"))
import run_eval  # noqa: E402


def _ws(test):
    d = tempfile.mkdtemp(prefix="r400-")
    test.addCleanup(shutil.rmtree, d, True)
    return d


class Levels(unittest.TestCase):

    def test_nine_levels_in_the_users_order(self):
        self.assertEqual(lv.COUNT, 9)
        titles = [t.lower() for t, _p, _c, _g in lv.LEVELS]
        for i, word in enumerate(("rough", "board", "smooth", "shell",
                                  "modules", "3d details", "colour",
                                  "refine", "product ready")):
            with self.subTest(level=i + 1):
                self.assertIn(word, titles[i])

    def test_every_level_formats_completely(self):
        for n in range(1, lv.COUNT + 1):
            text = lv.level_text(n)
            with self.subTest(level=n):
                self.assertTrue(text.startswith("LEVEL %d of 9 - " % n), text[:40])
                self.assertIn("\nGATE: ", text)
                self.assertNotRegex(text, r"\{[a-z_]+\}")     # nothing unfilled

    def test_level_one_carries_the_brief_and_the_numbers(self):
        t = lv.level_text(1, details=31, exterior=17, brief_lines=20)
        self.assertIn("DESIGN BRIEF", t)
        self.assertIn("at least 31 items, at least 17 on the outside", t)
        self.assertIn("at most 20 lines", t)
        self.assertIn("VOLUME MODEL", t)

    def test_detail_levels_name_the_guard(self):
        self.assertIn('cad.detail("name")', lv.level_text(6))
        self.assertIn("skipped", lv.level_text(8))

    def test_message_tail_and_turn_detection(self):
        msg = lv.level_message(4)
        self.assertTrue(msg.rstrip().endswith(lv.TURN_TAIL))
        self.assertTrue(lv.is_level_turn(msg))
        self.assertTrue(lv.is_level_turn(msg + "\n\n"))
        self.assertFalse(lv.is_level_turn("a toy car"))
        self.assertFalse(lv.is_level_turn(None))
        # a fix message is not a level message, and the reverse
        self.assertFalse(build.is_fix_turn(msg))
        self.assertFalse(lv.is_level_turn("x\n" + build.FIX_TURN_TAIL))

    def test_overview_one_line_per_level(self):
        rows = lv.overview().splitlines()
        self.assertEqual(len(rows), 9)
        self.assertTrue(rows[0].strip().startswith("1. "))
        self.assertIn("(design freeze)", rows[-1])


class Marker(unittest.TestCase):

    def test_write_read_advance_to_the_end(self):
        ws = _ws(self)
        self.assertIsNone(lv.read(ws))
        self.assertIsNone(lv.advance(ws))              # no ladder: nothing
        lv.write(ws, 1, "toy_car.py")
        self.assertEqual(lv.read(ws), {"level": 1, "count": 9, "seed": "toy_car.py"})
        self.assertEqual(os.stat(os.path.join(ws, lv.MARKER)).st_mode & 0o777, 0o444)
        for n in range(2, 10):
            msg = lv.advance(ws)
            self.assertTrue(msg.startswith("LEVEL %d of 9" % n), msg[:30])
            self.assertEqual(lv.read(ws)["level"], n)
            self.assertEqual(lv.read(ws)["seed"], "toy_car.py")
        self.assertIsNone(lv.advance(ws))              # LEVEL 9 was the last
        self.assertFalse(os.path.lexists(os.path.join(ws, lv.MARKER)))

    def test_a_planted_link_is_never_followed(self):
        ws, other = _ws(self), _ws(self)
        target = os.path.join(other, "secret.json")
        with open(target, "w") as fh:
            json.dump({"level": 3}, fh)
        os.symlink(target, os.path.join(ws, lv.MARKER))
        self.assertIsNone(lv.read(ws))
        lv.write(ws, 2)
        self.assertFalse(os.path.islink(os.path.join(ws, lv.MARKER)))
        with open(target) as fh:
            self.assertEqual(json.load(fh), {"level": 3})     # untouched
        self.assertEqual(lv.read(ws)["level"], 2)

    def test_garbage_and_out_of_range_read_as_none(self):
        ws = _ws(self)
        p = os.path.join(ws, lv.MARKER)
        for body in ("not json", json.dumps({"level": 0}),
                     json.dumps({"level": 10}), json.dumps({"lvl": 2})):
            with open(p, "w") as fh:
                fh.write(body)
            with self.subTest(body=body):
                self.assertIsNone(lv.read(ws))
            os.unlink(p)


class StartLevels(_Mode):
    MODE = "quality"

    def test_a_new_car_is_seeded_and_starts_level_one(self):
        ws = _ws(self)
        ladder, seed = build.start_levels(ws, "I want a car", True)
        self.assertEqual(seed, "toy_car.py")
        self.assertEqual(ladder["level"], 1)
        with open(os.path.join(ws, build.SCRIPT), encoding="utf-8") as fh:
            body = fh.read()
        with open(os.path.join(KIT, "examples", "toy_car.py"), encoding="utf-8") as fh:
            example = fh.read()
        self.assertTrue(body.startswith("# Seeded by Atelier from examples/toy_car.py"))
        self.assertTrue(body.endswith(example))
        compile(body, "model.py", "exec")
        # the agent can edit it
        self.assertTrue(os.stat(os.path.join(ws, build.SCRIPT)).st_mode & 0o200)

    def test_seed_follows_atech_fit(self):
        for request, want in (("a little desk robot", "desk_robot.py"),
                              ("a smart speaker", "smart_speaker.py"),
                              ("a bedside lamp", "bedside_lamp.py"),
                              ("a handheld game console", "handheld_console.py"),
                              ("a phone holder", None)):     # atech_case: never seeded
            ws = _ws(self)
            with self.subTest(request=request):
                ladder, seed = build.start_levels(ws, request, True)
                self.assertEqual(seed, want)
                self.assertEqual(ladder["level"], 1)       # the ladder runs anyway
                self.assertEqual(os.path.exists(os.path.join(ws, build.SCRIPT)),
                                 want is not None)

    def test_an_existing_design_is_never_overwritten_and_ends_the_ladder(self):
        ws = _ws(self)
        lv.write(ws, 4)
        with open(os.path.join(ws, build.SCRIPT), "w") as fh:
            fh.write("# mine\n")
        ladder, seed = build.start_levels(ws, "make it a car instead", True)
        self.assertEqual((ladder, seed), (None, None))
        with open(os.path.join(ws, build.SCRIPT)) as fh:
            self.assertEqual(fh.read(), "# mine\n")
        self.assertIsNone(lv.read(ws))                 # the user took over

    def test_fix_and_level_turns_keep_the_ladder(self):
        ws = _ws(self)
        build.start_levels(ws, "a toy car", True)
        lv.advance(ws)                                 # level 2 running
        for request in ("boom\n" + build.FIX_TURN_TAIL, lv.level_message(2)):
            with self.subTest(request=request[:20]):
                ladder, seed = build.start_levels(ws, request, True)
                self.assertEqual(ladder["level"], 2)
                self.assertIsNone(seed)

    def test_no_atech_no_ladder_no_seed(self):
        ws = _ws(self)
        self.assertEqual(build.start_levels(ws, "a toy car", False), (None, None))
        self.assertEqual(os.listdir(ws), [])

    def test_switches(self):
        os.environ["ATECH_PROMPT_OFF"] = "levels"
        ws = _ws(self)
        ladder, seed = build.start_levels(ws, "a toy car", True)
        self.assertIsNone(ladder)
        self.assertEqual(seed, "toy_car.py")           # seeding is its own switch
        os.environ["ATECH_PROMPT_OFF"] = "seed_fork"
        ws = _ws(self)
        ladder, seed = build.start_levels(ws, "a toy car", True)
        self.assertEqual((ladder["level"], seed), (1, None))
        self.assertFalse(os.path.exists(os.path.join(ws, build.SCRIPT)))

    def test_user_parts_in_the_document_block_the_seed(self):
        self.patch(build, "_has_user_parts", lambda doc: True)
        ws = _ws(self)
        ladder, seed = build.start_levels(ws, "a toy car", True, doc=object())
        self.assertIsNone(seed)
        self.assertEqual(ladder["level"], 1)

    def test_next_level(self):
        ws = _ws(self)
        self.assertIsNone(build.next_level(ws))
        build.start_levels(ws, "a toy car", True)
        msg = build.next_level(ws)
        self.assertTrue(msg.startswith("LEVEL 2 of 9 - PACKAGE THE ATECH BOARD"))
        self.assertTrue(build.is_level_turn(msg))


class FastModeUntouched(_Mode):
    MODE = "fast"

    def test_fast_mode_neither_seeds_nor_climbs(self):
        ws = _ws(self)
        self.assertEqual(build.start_levels(ws, "a toy car", True), (None, None))
        self.assertEqual(os.listdir(ws), [])
        self.assertFalse(build.levels_on())


class Prompt(_Mode):
    MODE = "quality"

    def setUp(self):
        super().setUp()
        self.atech_library()

    def _prompt(self, request="a toy car", off=None):
        if off is not None:
            os.environ["ATECH_PROMPT_OFF"] = off
        ws = _ws(self)
        ladder, seed = build.start_levels(ws, request, True)
        return build.quality_prompt(ws, True, ladder, seed)

    def test_levels_replace_the_clock_and_the_workflow(self):
        sp = self._prompt()
        self.assertIn("THE DESIGN LEVELS", sp)
        self.assertIn("LEVEL 1 of 9 - BRIEF, REFERENCES AND THE ROUGH VOLUME", sp)
        self.assertIn("Each turn does ONE level", sp)
        self.assertIn("with cad.detail(", sp)
        self.assertIn("short turn", sp)
        for gone in ("SHIP IN STAGES", "THE WORKFLOW", "STAGE A: a CHECK PASS",
                     "FORK below", "work the WORKFLOW above",
                     "START FROM THE CLOSEST", "long turn is expected"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, sp)
        self.assertNotRegex(sp, r"\{[a-z_]+\}")

    def test_seeded_prompt_says_what_model_py_is(self):
        sp = self._prompt()
        # R600: LEVEL 1's seeded checklist says it (once, not twice)
        self.assertIn("model.py already holds examples/toy_car.py, a build "
                      "that passes ./check", _flat(sp))
        self.assertIn("REDESIGN the silhouette", sp)
        self.assertNotIn("No example was seeded", sp)
        sp = self._prompt("a phone holder")
        self.assertIn("No example was seeded", sp)

    def test_real_world_bar(self):
        self.assertIn("REAL-WORLD QUALITY BAR", self._prompt())
        self.assertNotIn("REAL-WORLD QUALITY BAR", self._prompt(off="real_world"))

    def test_final_reply_only_at_the_last_level(self):
        self.assertIn("FINAL REPLY (at the last level)", self._prompt())

    def test_everything_off_is_the_one_turn_prompt(self):
        sp = self._prompt(off="levels,seed_fork,real_world")
        self.assertIn("THE WORKFLOW", sp)
        self.assertIn("START FROM THE CLOSEST PRODUCT EXAMPLE", sp)
        self.assertIn("the result is what\ncounts, not how long it takes", sp)
        self.assertIn("- FINAL REPLY: one short paragraph", sp)
        for new in ("DESIGN LEVELS", "REAL-WORLD", "SEEDED", "Each turn does ONE level"):
            with self.subTest(new=new):
                self.assertNotIn(new, sp)
        self.assertNotRegex(sp, r"\{[a-z_]+\}")

    def test_switches_are_registered(self):
        for name in ("levels", "seed_fork", "real_world"):
            self.assertIn(name, build.PROMPT_CHANGES)


class EvalLadder(unittest.TestCase):

    def test_next_level_message_advances_the_marker(self):
        ws = _ws(self)
        self.assertEqual(run_eval.next_level_message(ws), (None, None))
        lv.write(ws, 1)
        n, msg = run_eval.next_level_message(ws)
        self.assertEqual(n, 2)
        self.assertTrue(lv.is_level_turn(msg))
        lv.write(ws, 9)
        self.assertEqual(run_eval.next_level_message(ws), (None, None))

    def test_levels_reached(self):
        self.assertIsNone(run_eval.levels_reached({}))
        res = {"levels": [{"level": 1, "built_s": 10}, {"level": 2, "built_s": 50},
                          {"level": 3, "started_s": 50}]}
        self.assertEqual(run_eval.levels_reached(res), 2)
        self.assertEqual(run_eval.level_count(), 9)


class PanelTitle(unittest.TestCase):

    def test_level_title(self):
        try:
            from acadagent import panel
        except Exception as exc:                       # noqa: BLE001
            self.skipTest("panel needs Qt: %r" % (exc,))
        t = panel.AgentPanel._level_title(lv.level_message(3))
        self.assertEqual(t, "Level 3/9: Shape the surfaces and smooth the edges")
        self.assertEqual(panel.AgentPanel._level_title("a toy car"), "Designing")


# ---------------------------------------------------------------- freecadcmd
try:
    from acadagent import sandbox
    FC = sandbox.find_freecadcmd()
except Exception:                                      # noqa: BLE001
    FC = None

DETAIL_SCRIPT = r'''
import sys, json
sys.path.insert(0, %(kit)r)
import Part
import atech_cad as cad
out = {}
box = Part.makeBox(10, 10, 10)
with cad.detail("missed cut"):
    box = cad.cut(box, Part.makeBox(1, 1, 1, cad.V((50, 50, 50))))
out["volume_kept"] = round(box.Volume, 3)
with cad.detail("good cut"):
    box = cad.cut(box, Part.makeBox(2, 2, 20, cad.V((4, 4, -5))))
out["volume_cut"] = round(box.Volume, 3)
try:
    with cad.detail("a bug"):
        undefined_name + 1
    out["bug"] = "swallowed"
except NameError:
    out["bug"] = "raised"
out["skipped"] = cad.skipped_details()
cad.reset_details()
out["after_reset"] = cad.skipped_details()
out["in_all"] = "detail" in cad.__all__
print("RESULT " + json.dumps(out))
'''


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class DetailGuard(unittest.TestCase):

    def test_detail_skips_geometry_errors_only(self):
        d = _ws(self)
        script = os.path.join(d, "t.py")
        with open(script, "w") as fh:
            fh.write(DETAIL_SCRIPT % {"kit": KIT})
        p = subprocess.run([FC, script], capture_output=True, text=True, timeout=300)
        m = re.search(r"^RESULT (.+)$", p.stdout + p.stderr, re.M)
        self.assertIsNotNone(m, p.stdout[-2000:] + p.stderr[-2000:])
        out = json.loads(m.group(1))
        self.assertEqual(out["volume_kept"], 1000.0)   # the failed cut left it alone
        self.assertEqual(out["volume_cut"], 960.0)     # the good one cut
        self.assertEqual(out["bug"], "raised")
        self.assertEqual([s[0] for s in out["skipped"]], ["missed cut"])
        self.assertIn("CadError", out["skipped"][0][1])
        self.assertEqual(out["after_reset"], [])
        self.assertTrue(out["in_all"])
        self.assertIn("DETAIL SKIPPED 'missed cut'", p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
