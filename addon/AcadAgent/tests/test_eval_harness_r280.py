"""R450/R451 (WS5): the eval harness keeps the best passing design level.

What is pinned:
  checkpoint  every level that ends on a clean build leaves
              <id>/model_level<N>.py, intent_level<N>.json and
              render_level<N>.png (R450)
  rollback    a level that times out with a failing model.py, or still fails
              after MAX_FIX_ATTEMPTS, restores the last passing level's
              model.py and intent.json into the workspace, rebuilds it, marks
              levels[-1]["rolled_back"] and sends the next level (its message
              names the restored level) - or, out of budget, ends
              'built_rolled_back' with built True and model.py equal to the
              checkpoint. SABOTAGE: a run_eval with the restore disabled
              fails the same test.
  budget      no level starts once the item has run ITEM_BUDGET_S
              (budget_stop); ladder turns get LEVEL_TURN_TIMEOUT_S (never
              over TURN_TIMEOUT_S, at least LEVEL_TURN_MIN_S near the budget)
              and claude_turn really kills at that time; non-ladder turns
              keep TURN_TIMEOUT_S (R451)
  report      levels reached, per-level wall times with RB marks, rollbacks
              and budget stops in the .md report
  real        (freecadcmd present) a fake CLI passes level 1 with a real
              model, then writes a broken one and hangs in level 2: the real
              fc_build rebuilds the restored level-1 model and it passes

RUN
    cd addon/AcadAgent/tests && python3 -m unittest test_eval_harness_r280 -v
"""
import json
import os
import shutil
import sys
import tempfile
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_eval_harness_r270 as T  # noqa: E402  (fakes, run_eval on the path)
R = T.R
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "acadagent", "agent_kit"))
import atech_levels as lv  # noqa: E402

_turn = T._turn
FAIL = (True, "Body: 2 solids")
OK = (True, "")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class _Ladder(T._Faked):
    """A run_prompt whose workspace runs production's design ladder."""

    def setUp(self):
        super().setUp()
        M = self.MOD
        self.saved_budget = M.over_budget
        self.budget_after = None        # jobs count from which the budget is spent
        jobs = self.jobs

        def over(t_start):
            return self.budget_after is not None and len(jobs) >= self.budget_after
        M.over_budget = over
        lv.write(self.ws, 1, "smart_speaker.py")
        self.limits = []

    def tearDown(self):
        self.MOD.over_budget = self.saved_budget
        super().tearDown()

    def script(self, turns, builds, intents=None):
        """As _Faked.script; intents[i] is written as intent.json in turn i."""
        super().script(turns, builds)
        inner = self.MOD.claude_turn
        M = self.MOD

        def turn(argv, ws, stdin_text=None):
            i = len(self.argvs)
            self.limits.append(getattr(M._TURN_LIMIT, "s", None))
            self.stdins = getattr(self, "stdins", []) + [argv[-1]]
            if intents and i < len(intents) and intents[i] is not None:
                with open(os.path.join(ws, "intent.json"), "w", encoding="utf-8") as fh:
                    fh.write(intents[i])
            return inner(argv, ws, stdin_text)
        M.claude_turn = turn

    def dest(self, *names):
        return os.path.join(self.out, "spk", *names)


def timeout_scenario(case):
    """Levels 1 and 2 build, level 3 times out on a model.py that fails;
    the budget is spent once the restored level 2 is rebuilt."""
    case.budget_after = 4
    case.script([("L1 = 1\n", _turn()), ("L2 = 2\n", _turn()),
                 ("L3 = 3\n", _turn(ok=False, timed_out=True, cost=None, tokens=None))],
                [OK, OK, FAIL, OK],
                intents=['{"l": 1}', '{"l": 2}', '{"l": 3}'])
    return case.run_item(render=True)


class Rollback(_Ladder):
    def assert_rolled_back(self, r):
        ws_model = os.path.join(self.ws, "model.py")
        self.assertEqual(_read(ws_model), "L2 = 2\n",
                         "the workspace holds level 2's passing model.py")
        self.assertEqual(_read(ws_model), _read(self.dest("model_level2.py")))
        self.assertEqual(_read(self.dest("model.py")), _read(self.dest("model_level2.py")),
                         "the item's saved model.py is level 2's checkpoint")
        self.assertEqual(_read(os.path.join(self.ws, "intent.json")), '{"l": 2}')
        self.assertEqual(r["outcome"], "built_rolled_back")
        self.assertTrue(r["built"])
        self.assertTrue(r["pass"], "scored on the restored passing build")
        self.assertTrue(r["levels"][-1]["rolled_back"])
        self.assertEqual(r["levels"][-1]["level"], 3)
        self.assertEqual(r["levels"][-1]["restored_level"], 2)
        self.assertTrue(r["builds"][-1]["rolled_back"])
        self.assertEqual(r["levels_reached"], 2)

    def test_timed_out_level_ends_on_the_last_passing_level(self):
        r = timeout_scenario(self)
        self.assert_rolled_back(r)
        self.assertEqual(len(self.jobs), 4, "L1, L2, the salvage of L3, the restore")
        self.assertEqual(len(self.argvs), 3, "no level 4: the budget is spent")
        self.assertTrue(r["budget_stop"])
        self.assertTrue(r["claude_failure"].startswith("timed_out"))
        self.assertTrue(r["salvaged"])
        for n in (1, 2):
            self.assertTrue(os.path.isfile(self.dest("model_level%d.py" % n)))
            self.assertTrue(os.path.isfile(self.dest("intent_level%d.json" % n)))
        self.assertFalse(os.path.exists(self.dest("model_level3.py")))
        self.assertEqual(_read(self.dest("model_level1.py")), "L1 = 1\n")
        self.assertEqual(_read(self.dest("intent_level1.json")), '{"l": 1}')
        self.assertEqual([l["level"] for l in r["levels"]], [1, 2, 3])
        for l in r["levels"]:
            self.assertIsNotNone(l["wall_s"])

    def test_render_checkpoint_per_level(self):
        os.makedirs(self.dest(), exist_ok=True)
        with open(self.dest("render.png"), "w") as fh:
            fh.write("png")                      # the fake build renders nothing
        self.script([("L1 = 1\n", _turn())], [OK])
        self.budget_after = 1
        self.run_item(render=True)
        self.assertTrue(os.path.isfile(self.dest("render_level1.png")))

    def test_failed_level_after_its_fixes_rolls_back_and_the_ladder_goes_on(self):
        n_fail = R.MAX_FIX_ATTEMPTS + 1
        turns = [("L1 = 1\n", _turn()), ("L2 = 2\n", _turn())]
        turns += [("L3 = %d\n" % (30 + i), _turn()) for i in range(n_fail)]
        turns += [("L4 = 4\n", _turn())]
        builds = [OK, OK] + [FAIL] * n_fail + [OK, OK]
        self.budget_after = len(builds)          # spent after level 4 built
        self.script(turns, builds)
        r = self.run_item()
        self.assertEqual(len(self.argvs), len(turns))
        lv3 = [l for l in r["levels"] if l["level"] == 3][0]
        self.assertTrue(lv3["rolled_back"])
        self.assertEqual(lv3["restored_level"], 2)
        self.assertTrue(lv3["why"].startswith("still_fails_after_"))
        # the level 4 message names the restored build, and level 4 starts
        # from level 2's model.py
        msg4 = self.stdins[-1]
        self.assertIn("restored model.py and intent.json to the passing build of LEVEL 2",
                      msg4)
        self.assertIn("LEVEL 4 of %d" % lv.COUNT, msg4)
        self.assertEqual(self.jobs[-2]["mode"], "build")
        self.assertEqual(r["outcome"], "built")
        self.assertTrue(r["built"])
        self.assertEqual(r["levels_reached"], 4)
        self.assertEqual(r["rolled_back_levels"], [3])
        self.assertEqual(_read(self.dest("model_level4.py")), "L4 = 4\n")

    def test_cli_death_without_a_rewrite_rolls_back(self):
        self.budget_after = 2
        self.script([("L1 = 1\n", _turn()),
                     (None, _turn(ok=False, timed_out=False, cost=None))],
                    [OK, OK])
        r = self.run_item()
        self.assertEqual(r["outcome"], "built_rolled_back")
        self.assertEqual(r["levels"][-1]["restored_level"], 1)
        self.assertTrue(r["claude_failure"].startswith("claude_failed"))
        self.assertEqual(len(self.jobs), 2, "no salvage build of an unchanged file")

    def test_restored_build_that_fails_is_not_built(self):
        self.budget_after = 99
        self.script([("L1 = 1\n", _turn()),
                     ("L2 = 2\n", _turn(ok=False, timed_out=True, cost=None))],
                    [OK, FAIL, FAIL])
        r = self.run_item()
        self.assertEqual(r["outcome"], "rolled_back_failed")
        self.assertFalse(r["built"])

    def test_level_one_timeout_salvaged_goes_on(self):
        """Level 1 timed out on a model that builds: it is level 1's
        checkpoint and level 2 is sent."""
        self.budget_after = 2
        self.script([("L1 = 1\n", _turn(ok=False, timed_out=True, cost=None)),
                     ("L2 = 2\n", _turn())], [OK, OK])
        r = self.run_item()
        self.assertEqual(len(self.argvs), 2)
        self.assertTrue(r["levels"][0]["salvaged"])
        self.assertEqual(r["levels_reached"], 2)
        self.assertEqual(r["outcome"], "built")

    def test_no_ladder_keeps_the_r270_salvage(self):
        lv.clear(self.ws)
        r = T.salvage_scenario(self)
        self.assertEqual(r["outcome"], "timed_out_built")
        self.assertIsNone(r.get("levels"))
        self.assertEqual(self.limits, [R.TURN_TIMEOUT_S], "no ladder: TURN_TIMEOUT_S")


class Budget(_Ladder):
    def test_budget_stops_the_ladder_after_a_passing_level(self):
        self.budget_after = 1
        self.script([("L1 = 1\n", _turn()), ("L2 = 2\n", _turn())], [OK, OK])
        r = self.run_item()
        self.assertEqual(len(self.argvs), 1, "no level is sent over budget")
        self.assertEqual(r["outcome"], "built")
        self.assertTrue(r["built"])
        self.assertTrue(r["budget_stop"])
        self.assertEqual(r["levels_reached"], 1)
        self.assertEqual(lv.read(self.ws)["level"], 1, "the marker is not advanced")

    def test_over_budget_mid_level_rolls_back_at_once(self):
        """A level still failing when the budget is spent does not use its
        remaining fixes: the item ends on the last passing level."""
        self.budget_after = 2
        self.script([("L1 = 1\n", _turn()), ("L2 = 20\n", _turn()), ("L2 = 21\n", _turn())],
                    [OK, FAIL, OK])
        r = self.run_item()
        self.assertEqual(len(self.argvs), 2)
        self.assertEqual(r["outcome"], "built_rolled_back")
        self.assertEqual(r["levels"][-1]["why"], "over_budget")
        self.assertEqual(_read(os.path.join(self.ws, "model.py")), "L1 = 1\n")

    def test_ladder_turns_get_the_level_timeout(self):
        self.budget_after = 2
        self.script([("L1 = 1\n", _turn()), ("L2 = 2\n", _turn())], [OK, OK])
        r = self.run_item()
        want = min(R.TURN_TIMEOUT_S, R.LEVEL_TURN_TIMEOUT_S)
        self.assertEqual(self.limits, [want, want])
        self.assertEqual([t["timeout_s"] for t in r["turns"]], [want, want])

    def test_turn_limit(self):
        self.assertEqual(R.LEVEL_TURN_TIMEOUT_S, 25 * 60)
        self.assertEqual(R.ITEM_BUDGET_S, 150 * 60)
        self.assertEqual(R.turn_limit(False, 0), R.TURN_TIMEOUT_S)
        self.assertEqual(R.turn_limit(True, 0), 25 * 60)
        self.assertEqual(R.turn_limit(True, R.ITEM_BUDGET_S - 600), 600)
        self.assertEqual(R.turn_limit(True, R.ITEM_BUDGET_S + 99), R.LEVEL_TURN_MIN_S)
        saved = R.TURN_TIMEOUT_S
        R.TURN_TIMEOUT_S = 4
        try:
            self.assertEqual(R.turn_limit(True, 0), 4, "never over TURN_TIMEOUT_S")
        finally:
            R.TURN_TIMEOUT_S = saved

    def test_real_over_budget(self):
        self.assertFalse(self.saved_budget(time.time()))
        self.assertTrue(self.saved_budget(time.time() - R.ITEM_BUDGET_S - 1))


class Report(_Ladder):
    def test_report_lists_levels_walls_rollbacks_and_budget(self):
        r = timeout_scenario(self)
        md = R.report([r], 1, {"date": "d"}, "t")
        self.assertIn("| design levels reached (R400; per prompt) | spk 2/%d |" % lv.COUNT, md)
        row = [ln for ln in md.splitlines() if ln.startswith("| design level wall times")][0]
        self.assertRegex(row, r"spk L1 \d+, L2 \d+, L3 \d+ RB \|$")
        self.assertIn("| levels rolled back / items ended on a rolled-back level / items "
                      "stopped by the 150 min budget (R450, R451) | 1 / 1 / 1 |", md)

    def test_no_ladder_no_level_rows(self):
        lv.clear(self.ws)
        self.script([("A = 1\n", _turn())], [OK])
        md = R.report([self.run_item()], 1, {"date": "d"}, "t")
        self.assertNotIn("design level wall times", md)


class KilledAtLevelLimit(unittest.TestCase):
    """claude_turn kills at the thread's level limit, not TURN_TIMEOUT_S."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="r280-cli-")
        self.exe = T._exe(os.path.join(self.tmp, "claude"), T.FAKE_HANG % {
            "py": sys.executable, "env_log": os.path.join(self.tmp, "env.json")})

    def tearDown(self):
        R._TURN_LIMIT.s = None
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_level_limit_kills_the_turn(self):
        R._TURN_LIMIT.s = 1.0
        t0 = time.time()
        rec = R.claude_turn([self.exe, "-p"], self.tmp, "m")
        self.assertTrue(rec["timed_out"])
        self.assertLess(time.time() - t0, 30, "killed at the level limit, not 3600 s")


class RollbackSabotage(unittest.TestCase):
    """The rollback test must FAIL on a run_eval whose restore is disabled."""

    def test_disabled_restore_fails_the_rollback_test(self):
        src = _read(R.__file__)
        gate = "    restore_checkpoint(ws, ck)\n"
        self.assertEqual(src.count(gate), 1, "the restore moved; update the sabotage")
        bad = src.replace(gate, "    pass  # SABOTAGE (R450 test)\n")
        mod = types.ModuleType("run_eval_sabotaged_r450")
        mod.__file__ = R.__file__
        exec(compile(bad, R.__file__, "exec"), mod.__dict__)     # noqa: S102

        class Case(Rollback):
            MOD = mod

            def runTest(self):
                pass
        case = Case()
        case.setUp()
        try:
            r = timeout_scenario(case)
            with self.assertRaises(AssertionError):
                case.assert_rolled_back(r)
            self.assertEqual(_read(os.path.join(case.ws, "model.py")), "L3 = 3\n",
                             "without the restore the failing level's model.py stays")
        finally:
            case.tearDown()


# ------------------------------------------------------------------ real
FAKE_LADDER = r'''#!%(py)s
import json, os, sys, time
sys.stdin.read()
def out(o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
n_path = os.path.join(%(tmp)r, "turns")
n = int(open(n_path).read()) if os.path.exists(n_path) else 0
open(n_path, "w").write(str(n + 1))
out({"type": "system", "subtype": "init", "session_id": "S1", "model": "m"})
with open("model.py", "w") as fh:
    fh.write(%(good)r if n == 0 else %(bad)r)
if n == 0:
    out({"type": "result", "subtype": "success", "is_error": False, "result": "level 1",
         "total_cost_usd": 0.01, "num_turns": 1, "session_id": "S1",
         "usage": {"input_tokens": 1, "output_tokens": 1}})
    sys.exit(0)
time.sleep(600)
'''

GOOD_SRC = T.MODEL_SRC
BAD_SRC = 'raise RuntimeError("level 2 broke the kernel")\n'


@unittest.skipUnless(T.FC, "freecadcmd not found (FREECADCMD / ATECH_FREECADCMD)")
class RealRollback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="r280-real-")
        self.out = os.path.join(self.tmp, "out")
        self.exe = T._exe(os.path.join(self.tmp, "claude"), FAKE_LADDER % {
            "py": sys.executable, "tmp": self.tmp, "good": GOOD_SRC, "bad": BAD_SRC})
        self.saved = (R.FREECADCMD, R.TURN_TIMEOUT_S, R.production_argv, R.over_budget)
        R.FREECADCMD = T.FC
        R.TURN_TIMEOUT_S = 6
        real, exe = R.production_argv, self.exe

        def argv(root, seed=None, request=None):
            p = real(root, seed, request)
            p["first"] = [exe] + p["first"][1:]
            p["resume"] = [exe] + p["resume"][1:]
            lv.write(p["workspace"], 1)            # the ladder runs
            return p
        R.production_argv = argv

    def tearDown(self):
        R.FREECADCMD, R.TURN_TIMEOUT_S, R.production_argv, R.over_budget = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_real_rollback_rebuilds_level_one(self):
        item = {"id": "box", "prompt": "a box 60 x 40 x 30",
                "expect": {"overall_z": [29, 31]}}
        spent = [0]

        def over(t):
            spent[0] += 1
            return spent[0] > 1                    # level 2 starts, then no more
        R.over_budget = over
        r = self.r = R.run_prompt(item, self.out, render=True)
        d = os.path.join(self.out, "box")
        self.assertTrue(r["turns"][1]["timed_out"])
        self.assertEqual(len(r["builds"]), 3, [b.get("error") for b in r["builds"]])
        self.assertFalse(r["builds"][1]["ok"], "level 2's broken model.py fails")
        self.assertTrue(r["builds"][2]["ok"], r["builds"][2].get("error"))
        self.assertTrue(r["builds"][2]["rolled_back"])
        self.assertEqual(r["outcome"], "built_rolled_back")
        self.assertTrue(r["built"])
        self.assertTrue(r["pass"], r.get("failed_checks"))
        self.assertEqual(_read(os.path.join(d, "model.py")), GOOD_SRC)
        self.assertEqual(_read(os.path.join(d, "model_level1.py")), GOOD_SRC)
        self.assertTrue(os.path.isfile(os.path.join(d, "render_level1.png")))
        self.assertTrue(os.path.isfile(os.path.join(d, "render.png")))
        with open(os.path.join(self.out, "box", "transcript.txt"), encoding="utf-8") as fh:
            self.assertIn("LEVEL 2 of", fh.read())


if __name__ == "__main__":
    unittest.main()
