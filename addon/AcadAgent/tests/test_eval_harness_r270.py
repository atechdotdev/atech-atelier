"""R270 (WS5): the eval harness and the runtime around a turn.

What is pinned:
  salvage   a turn killed at TURN_TIMEOUT_S (or a CLI that dies) that wrote a
            NEW model.py gets exactly one end-of-turn build WITH render
            (render.png; fc_build adds render_inside.png), recorded as
            outcome 'timed_out_built' / 'timed_out_failed' (or
            'claude_failed_built' / '_failed'), scored like any build; an
            unchanged model.py is still 'claude_failed' with no build.
            SABOTAGE: the same scenario on a copy of run_eval with the
            salvage branch reverted is scored not built, with no build.
  cost      a CLI killed before its result record: cost_usd, input and
            output tokens None, never 0; the prompt's cost is None with the
            known part kept; the report prints 'unknown'
  turn T0   ATECH_TURN_T0 (epoch s) is in the CLI child's env in
            run_eval.claude_turn and claude_cli.ClaudeRun, in ./check's
            check.py env (runtime value wins over the baked one) and in
            sandbox.Job's env when the process has it; garbage is dropped
  timeout   quality mode's build / ./check timeout is >= 120 s (the desk
            robot's model took 72 s) and ./check passes it to check.py
  contention ./check prints ATECH_CHECK_TIMING lock_wait_s / run_s and the
            eval records them per ./check; fc_job records its freecadcmd
            lock wait; --max-parallel caps --jobs (default 3)
  effort    ATECH_EVAL_EFFORT overrides --effort on every turn's argv (and
            only then); a value the CLI does not know is an error
  real      (freecadcmd present) a fake CLI that writes a real model.py and
            hangs is killed, salvaged, built and rendered by fc_build
"""
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest

os.environ.setdefault("ATECH_PROMPT_MODE", "fast")   # as test_eval_harness

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.join(HERE, "eval")
ADDON = os.path.dirname(HERE)
sys.path.insert(0, EVAL)
sys.path.insert(0, ADDON)
sys.path.insert(0, HERE)

import run_eval as R  # noqa: E402
from acadagent import sandbox  # noqa: E402

_FC_CANDS = [os.environ.get("FREECADCMD"), os.environ.get("ATECH_FREECADCMD"), R.FREECADCMD]
FC = next((c for c in _FC_CANDS if c and os.path.isfile(c)), None)


def _exe(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


# A claude that starts, writes model.py, records its env, then hangs with no
# result record (the round-1 timeout shape).
FAKE_HANG = r'''#!%(py)s
import json, os, sys, time
sys.stdin.read()
with open(%(env_log)r, "w") as fh:
    json.dump({"ATECH_TURN_T0": os.environ.get("ATECH_TURN_T0")}, fh)
def out(o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
out({"type": "system", "subtype": "init", "session_id": "S9", "model": "m"})
out({"type": "assistant", "message": {"content": [
    {"type": "tool_use", "id": "w1", "name": "Write",
     "input": {"file_path": os.path.join(os.getcwd(), "model.py")}}]}})
src = os.environ.get("FAKE_MODEL_SRC")
if src:
    with open("model.py", "w") as fh:
        fh.write(src)
out({"type": "assistant", "message": {"content": [
    {"type": "tool_use", "id": "c1", "name": "Bash", "input": {"command": "./check"}}]}})
out({"type": "user", "message": {"content": [
    {"type": "tool_result", "tool_use_id": "c1",
     "content": "ATECH_CHECK_TIMING lock_wait_s=7 run_s=41\nCHECK PASS"}]}})
time.sleep(600)
'''


def _turn(ok=True, timed_out=False, cost=0.1, tokens=10):
    return {"session": "S1", "ok": ok, "wall_s": 1.0, "cost_usd": cost,
            "num_turns": 1 if ok else None, "model": "m", "tools": [],
            "timed_out": timed_out, "exit": 0 if ok else -15, "first_write_s": 0.5,
            "init_s": 0.1, "first_text_s": 0.2, "check_calls": 0,
            "input_tokens": tokens, "output_tokens": tokens if tokens else None,
            "permission_denials": 0, "denials": [], "usage": {} if ok else None,
            "texts": [], "final": "done" if ok else "", "log": [],
            "stderr_tail": "", "result_missing": not ok}


class _FakeLive(object):
    def __init__(self, ws, job, t_ref, turn=1, **kw):
        self.skipped, self.stop_wait_s = 0, 0.0

    def start(self):
        return self

    def stop(self):
        return []


class _Faked(unittest.TestCase):
    """run_prompt with fake production argv, claude, freecadcmd (pure)."""
    MOD = R

    def setUp(self):
        M = self.MOD
        self.out = tempfile.mkdtemp(prefix="r270-out-")
        self.ws = tempfile.mkdtemp(prefix="r270-ws-")
        self.saved = (M.production_argv, M.claude_turn, M.fc_job, M.LivePreview)
        self.jobs, self.argvs = [], []
        ws = self.ws

        def argv(root, seed=None, request=None):
            return {"workspace": ws, "first": ["claude", "--effort", "xhigh", R.MSG_PH],
                    "resume": ["claude", "--resume", R.SID_PH, R.MSG_PH],
                    "document_brief": "BRIEF", "source": "fake", "private_dirs": []}
        M.production_argv = argv
        M.LivePreview = _FakeLive

        def job(j):
            self.jobs.append(dict(j))
            ok, failures = self.builds[len(self.jobs) - 1]
            return ({"ok": ok, "failures": failures, "error": "" if ok else "boom",
                     "document_brief": "B", "whole_dims_sorted_mm": [80, 50, 30],
                     "checks": [{"check": "overall_z", "pass": ok, "detail": 1}],
                     "fitness": [], "fc_lock_wait_s": 1.5}, "")
        M.fc_job = job

    def tearDown(self):
        M = self.MOD
        M.production_argv, M.claude_turn, M.fc_job, M.LivePreview = self.saved
        shutil.rmtree(self.out, ignore_errors=True)
        shutil.rmtree(self.ws, ignore_errors=True)

    def script(self, turns, builds):
        """turns: [(write or None, turn dict)]; builds: [(ok, failures)]."""
        self.builds = builds

        def turn(argv, ws, stdin_text=None):
            write, rec = turns[len(self.argvs)]
            self.argvs.append(list(argv))
            if write is not None:
                time.sleep(0.01)
                with open(os.path.join(ws, "model.py"), "w", encoding="utf-8") as fh:
                    fh.write(write)
            return dict(rec)
        self.MOD.claude_turn = turn

    def run_item(self, render=True, item=None):
        item = item or {"id": "spk", "prompt": "a smart speaker",
                        "expect": {"overall_z": [1, 100]}}
        return self.MOD.run_prompt(item, self.out, render=render)


# ------------------------------------------------------------- salvage
def salvage_scenario(case):
    """The round-1 smart speaker: the only turn times out after writing a
    model.py that builds."""
    case.script([("A = 1\n", _turn(ok=False, timed_out=True, cost=None, tokens=None))],
                [(True, "")])
    return case.run_item(render=True)


class Salvage(_Faked):
    def assert_salvaged(self, r):
        self.assertEqual(len(self.jobs), 1, "exactly one end-of-turn build")
        j = self.jobs[0]
        self.assertEqual(j["mode"], "build")
        self.assertTrue(j.get("render") and j["render"].endswith("render.png"),
                        "the salvage build renders (render.png + render_inside.png)")
        self.assertFalse(j.get("preview"))
        self.assertEqual(r["outcome"], "timed_out_built")
        self.assertTrue(r["built"])
        self.assertTrue(r["pass"], "a passing model is scored")
        self.assertTrue(r["salvaged"])
        self.assertTrue(r["builds"][0]["salvaged"])
        self.assertTrue(r["claude_failure"].startswith("timed_out: "))

    def test_timed_out_turn_with_new_model_is_built_and_rendered(self):
        r = salvage_scenario(self)
        self.assert_salvaged(r)
        self.assertEqual(len(self.argvs), 1, "no fix turn after a dead session")
        d = os.path.join(self.out, "spk")
        self.assertTrue(os.path.isfile(os.path.join(d, "model_attempt1.py")))
        self.assertTrue(os.path.isfile(os.path.join(d, "model.py")))
        self.assertIsNotNone(r["first_ok_build_s"])
        self.assertEqual(r["fc_lock_wait_s"], 1.5)

    def test_timed_out_failing_model_is_timed_out_failed(self):
        self.script([("A = 1\n", _turn(ok=False, timed_out=True, cost=None))],
                    [(True, "Body: 2 solids")])
        r = self.run_item()
        self.assertEqual(len(self.jobs), 1)
        self.assertEqual(r["outcome"], "timed_out_failed")
        self.assertFalse(r["built"])

    def test_cli_death_is_salvaged_as_claude_failed_built(self):
        self.script([("A = 1\n", _turn(ok=False, timed_out=False, cost=None))], [(True, "")])
        r = self.run_item()
        self.assertEqual(r["outcome"], "claude_failed_built")
        self.assertTrue(r["built"])

    def test_unchanged_model_is_not_built(self):
        with open(os.path.join(self.ws, "model.py"), "w", encoding="utf-8") as fh:
            fh.write("A = 1\n")                         # there before the turn
        self.script([(None, _turn(ok=False, timed_out=True, cost=None))], [])
        r = self.run_item()
        self.assertEqual(self.jobs, [])
        self.assertTrue(r["outcome"].startswith("claude_failed: "), r["outcome"])
        self.assertFalse(r["built"])

    def test_salvage_in_a_later_fix_turn(self):
        """A fix turn that times out after a rewrite: still built once more."""
        self.script([("A = 1\n", _turn()),
                     ("A = 2\n", _turn(ok=False, timed_out=True, cost=None))],
                    [(False, ""), (True, "")])
        r = self.run_item()
        self.assertEqual(len(self.jobs), 2)
        self.assertEqual(r["outcome"], "timed_out_built")
        self.assertEqual(r["cost_usd"], None)
        self.assertEqual(r["cost_usd_known"], 0.1)
        self.assertEqual(r["cost_unknown_turns"], 1)

    def test_no_render_flag_is_respected(self):
        self.script([("A = 1\n", _turn(ok=False, timed_out=True, cost=None))], [(True, "")])
        self.run_item(render=False)
        self.assertIsNone(self.jobs[0]["render"])


class SalvageSabotage(unittest.TestCase):
    """The salvage test must FAIL on a run_eval with the branch reverted
    (the pre-R270 'claude_failed -> break')."""

    def test_reverted_branch_fails_the_salvage_test(self):
        with open(R.__file__, encoding="utf-8") as fh:
            src = fh.read()
        gate = "if h_now is None or h_now == h_before:"
        self.assertEqual(src.count(gate), 1, "the salvage gate moved; update the sabotage")
        bad = src.replace(gate, "if True:  # SABOTAGE (R270 test)")
        mod = types.ModuleType("run_eval_sabotaged")
        mod.__file__ = R.__file__
        exec(compile(bad, R.__file__, "exec"), mod.__dict__)     # noqa: S102

        class Case(Salvage):
            MOD = mod

            def runTest(self):
                pass
        case = Case()
        case.setUp()
        try:
            r = salvage_scenario(case)
            with self.assertRaises(AssertionError):
                case.assert_salvaged(r)
            self.assertEqual(case.jobs, [], "the reverted branch builds nothing")
            self.assertFalse(r["built"])
        finally:
            case.tearDown()


# ---------------------------------------------------------------- cost
class CostUnknown(_Faked):
    def test_cost_record(self):
        self.assertEqual(R.cost_record([{"cost_usd": 0.5}, {"cost_usd": 0.25}]),
                         {"cost_usd": 0.75, "cost_usd_known": 0.75, "cost_unknown_turns": 0})
        self.assertEqual(R.cost_record([{"cost_usd": 0.5}, {"cost_usd": None}])["cost_usd"],
                         None)
        self.assertEqual(R.fmt_cost(None), "unknown")
        self.assertEqual(R.fmt_cost(1.234), "$1.23")

    def test_report_prints_unknown(self):
        r = salvage_scenario(self)
        self.assertIsNone(r["cost_usd"])
        self.assertIsNone(r["input_tokens"])
        self.assertIsNone(r["output_tokens"])
        md = R.report([r], 1, {"date": "d"}, "t")
        self.assertIn("| total cost | unknown (1 prompt killed before the CLI's result; "
                      "$0.00 known) |", md)
        self.assertIn("unknown for 1 prompt", md)
        row = [ln for ln in md.splitlines() if ln.startswith("| spk | a smart speaker |")][0]
        self.assertIn("| unknown | unknown | unknown |", row)
        self.assertIn("| turns killed with a new model.py, built at the end anyway (R270) | 1 |",
                      md)

    def test_known_cost_report_unchanged(self):
        self.script([("A = 1\n", _turn())], [(True, "")])
        r = self.run_item()
        self.assertEqual(r["cost_usd"], 0.1)
        md = R.report([r], 1, {"date": "d"}, "t")
        self.assertIn("| total cost | $0.10 |", md)


class KilledCli(unittest.TestCase):
    """A real claude_turn against a fake CLI that hangs with no result."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="r270-cli-")
        self.env_log = os.path.join(self.tmp, "env.json")
        self.exe = _exe(os.path.join(self.tmp, "claude"),
                        FAKE_HANG % {"py": sys.executable, "env_log": self.env_log})
        self.saved = R.TURN_TIMEOUT_S
        R.TURN_TIMEOUT_S = 1.5

    def tearDown(self):
        R.TURN_TIMEOUT_S = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_killed_cli_cost_and_tokens_are_none_and_turn_t0_is_set(self):
        t = int(time.time())
        rec = R.claude_turn([self.exe, "-p"], self.tmp, "m")
        self.assertTrue(rec["timed_out"])
        self.assertFalse(rec["ok"])
        self.assertIsNone(rec["cost_usd"], "never 0 for a killed CLI")
        self.assertIsNone(rec["input_tokens"])
        self.assertIsNone(rec["output_tokens"])
        self.assertTrue(rec["result_missing"])
        with open(self.env_log, encoding="utf-8") as fh:
            got = json.load(fh)["ATECH_TURN_T0"]
        self.assertIsNotNone(got, "ATECH_TURN_T0 not in the CLI child's env")
        self.assertTrue(re.match(r"^\d+$", got), got)
        self.assertLessEqual(abs(int(got) - t), 2)
        self.assertEqual(rec["turn_t0"], int(got))
        # R270 contention: the ./check result's timing line is recorded
        self.assertEqual(rec["check_calls"], 1)
        self.assertEqual(len(rec["check_timings"]), 1)
        self.assertEqual(rec["check_timings"][0]["lock_wait_s"], 7)
        self.assertEqual(rec["check_timings"][0]["run_s"], 41)


# -------------------------------------------------------- turn clock in app
class AppTurnClock(unittest.TestCase):
    def test_claude_cli_child_env_has_turn_t0(self):
        try:
            import test_claude_cli as TC
        except Exception as exc:                        # noqa: BLE001
            self.skipTest("test_claude_cli stub not importable: %s" % exc)
        cli = TC.cli
        env = cli.turn_env({"A": "1"}, t0=1760000000.7)
        self.assertEqual(env, {"A": "1", "ATECH_TURN_T0": "1760000000"})
        self.assertNotIn("ATECH_TURN_T0", os.environ)

        tmp = tempfile.mkdtemp(prefix="r270-app-")
        self.addCleanup(shutil.rmtree, tmp, True)
        log = os.path.join(tmp, "env.json")
        fx = os.path.join(tmp, "fx.ndjson")
        with open(fx, "w", encoding="utf-8") as fh:
            fh.write("\n".join(json.dumps(o) for o in TC.LIVE_OK) + "\n")
        exe = _exe(os.path.join(tmp, "claude"), r'''#!%s
import json, os, sys
sys.stdin.read()
if "--help" in sys.argv or "--version" in sys.argv:
    print("--effort --verbose --output-format --include-partial-messages"); sys.exit(0)
with open(%r, "w") as fh:
    json.dump({"t0": os.environ.get("ATECH_TURN_T0")}, fh)
sys.stdout.write(open(%r).read())
''' % (sys.executable, log, fx))
        saved = cli.find_claude
        cli.find_claude = lambda: exe
        try:
            t = int(time.time())
            run = cli.ClaudeRun("hello", cwd=tmp)
            th = threading.Thread(target=run.run, daemon=True)
            th.start()
            th.join(30)
            self.assertFalse(th.is_alive())
        finally:
            cli.find_claude = saved
        with open(log, encoding="utf-8") as fh:
            got = json.load(fh)["t0"]
        self.assertIsNotNone(got, "ClaudeRun did not export ATECH_TURN_T0")
        self.assertLessEqual(abs(int(got) - t), 5)


# ------------------------------------------------------ turn clock in ./check
FAKE_FC = r'''#!/bin/sh
# a stand-in freecadcmd: prints what check.py would see
echo "SEEN_T0=${ATECH_TURN_T0:-none}"
echo "SEEN_TIMEOUT=${ATECH_CHECK_TIMEOUT:-none}"
[ -n "$FAKE_FC_ENV_LOG" ] && env > "$FAKE_FC_ENV_LOG"
env > "$(dirname "$ATECH_CHECK_SCRIPT")/fc_env.txt" 2>/dev/null
echo "CHECK PASS"
'''


class CheckEnv(unittest.TestCase):
    def setUp(self):
        self.ws = os.path.realpath(tempfile.mkdtemp(prefix="r270-ws-"))
        self.addCleanup(shutil.rmtree, self.ws, True)
        self.fc = _exe(os.path.join(self.ws, "fake_fc"), FAKE_FC)
        with open(os.path.join(self.ws, "model.py"), "w", encoding="utf-8") as fh:
            fh.write("A = 1\n")
        self.saved = os.environ.pop("ATECH_TURN_T0", None)

    def tearDown(self):
        if self.saved is not None:
            os.environ["ATECH_TURN_T0"] = self.saved

    def check(self, env_t0=None, **kw):
        text = sandbox.wrapper_script(self.ws, freecadcmd=self.fc, mode="none", **kw)
        path = _exe(os.path.join(self.ws, "check"), text)
        env = dict(os.environ)
        env.pop("ATECH_TURN_T0", None)
        if env_t0 is not None:
            env["ATECH_TURN_T0"] = env_t0
        p = subprocess.run([path], cwd=self.ws, env=env, capture_output=True, text=True,
                           timeout=60)
        return text, p.stdout + p.stderr

    def test_runtime_turn_t0_reaches_check_py(self):
        _text, out = self.check(env_t0="1760000123")
        self.assertIn("SEEN_T0=1760000123", out)
        self.assertTrue(out.rstrip().endswith("CHECK PASS"), out)

    def test_baked_turn_t0_is_the_fallback(self):
        _text, out = self.check(turn_start=1760000999)
        self.assertIn("SEEN_T0=1760000999", out)
        _text, out = self.check(env_t0="1760000555", turn_start=1760000999)
        self.assertIn("SEEN_T0=1760000555", out, "the live turn's value wins")

    def test_no_turn_t0_is_empty_and_garbage_is_not_baked(self):
        text, out = self.check(turn_start="1; rm -rf /")
        self.assertIn('ATECH_TURN_T0="${ATECH_TURN_T0:-}"', text)
        self.assertIn("SEEN_T0=none", out)
        self.assertEqual(sandbox.turn_t0("abc"), "")
        self.assertEqual(sandbox.turn_t0(1760000000), "1760000000")
        self.assertEqual(sandbox.turn_t0("1760000000.25"), "1760000000.25")

    def test_check_prints_lock_wait_and_run_time(self):
        _text, out = self.check()
        t = R.check_timing(out)
        self.assertIsNotNone(t, out)
        self.assertGreaterEqual(t[0], 0)
        self.assertGreaterEqual(t[1], 0)
        self.assertTrue(out.rstrip().endswith("CHECK PASS"), "CHECK stays the last line")

    def test_job_passes_turn_t0(self):
        os.environ["ATECH_TURN_T0"] = "1760000321"
        try:
            sandbox.Job(self.ws, freecadcmd=self.fc, mode="none", timeout=30).start().wait()
        finally:
            os.environ.pop("ATECH_TURN_T0", None)
        with open(os.path.join(self.ws, "fc_env.txt"), encoding="utf-8") as fh:
            env = fh.read()
        self.assertIn("ATECH_TURN_T0=1760000321", env)
        self.assertIn("ATECH_CHECK_TIMEOUT=30.0", env)

    def test_job_without_turn_has_no_turn_t0(self):
        sandbox.Job(self.ws, freecadcmd=self.fc, mode="none", timeout=30).start().wait()
        with open(os.path.join(self.ws, "fc_env.txt"), encoding="utf-8") as fh:
            self.assertNotIn("ATECH_TURN_T0", fh.read())

    def test_quality_check_timeout_is_at_least_120(self):
        saved = os.environ.get("ATECH_PROMPT_MODE")
        os.environ["ATECH_PROMPT_MODE"] = "quality"
        try:
            self.assertGreaterEqual(sandbox.default_timeout(), 120.0)
            text = sandbox.wrapper_script(self.ws, freecadcmd=self.fc, mode="none")
            m = re.search(r"ATECH_CHECK_TIMEOUT=([0-9.]+)", text)
            self.assertGreaterEqual(float(m.group(1)), 120.0)
            _t, out = self.check()
            self.assertGreaterEqual(float(re.search(r"SEEN_TIMEOUT=([0-9.]+)", out).group(1)),
                                    120.0)
        finally:
            if saved is None:
                os.environ.pop("ATECH_PROMPT_MODE", None)
            else:
                os.environ["ATECH_PROMPT_MODE"] = saved


# ---------------------------------------------------------- contention
class Contention(unittest.TestCase):
    def test_max_parallel_caps_jobs(self):
        self.assertEqual(R.MAX_PARALLEL, 3)
        self.assertEqual(R.parallel_jobs(8), 3)
        self.assertEqual(R.parallel_jobs(2), 2)
        self.assertEqual(R.parallel_jobs(8, 5), 5)
        self.assertEqual(R.parallel_jobs(0, 0), 1)
        p = subprocess.run([sys.executable, R.__file__, "--help"], capture_output=True,
                           text=True, timeout=60)
        self.assertIn("--max-parallel", p.stdout)

    def test_fc_job_records_its_lock_wait(self):
        tmp = tempfile.mkdtemp(prefix="r270-fc-")
        self.addCleanup(shutil.rmtree, tmp, True)
        fake = _exe(os.path.join(tmp, "freecadcmd"), r'''#!%s
import json, os
job = json.load(open(os.environ["EVAL_JOB"]))
json.dump({"ok": True}, open(job["out"], "w"))
print("FC_BUILD_DONE=1")
''' % sys.executable)
        saved = R.FREECADCMD
        R.FREECADCMD = fake
        try:
            R._FC_LOCK.acquire()
            threading.Timer(0.4, R._FC_LOCK.release).start()
            b, crash = R.fc_job({"mode": "build"})
        finally:
            R.FREECADCMD = saved
        self.assertEqual(crash, "")
        self.assertTrue(b["ok"])
        self.assertGreaterEqual(b["fc_lock_wait_s"], 0.3)

    def test_lock_waits_summary(self):
        res = {"turns": [{"check_timings": [{"lock_wait_s": 3, "run_s": 40},
                                            {"lock_wait_s": None, "run_s": None}]},
                         {"check_timings": [{"lock_wait_s": 5, "run_s": 20}]}],
               "builds": [{"fc_lock_wait_s": 1.0}], "previews": [{"fc_lock_wait_s": 2.5}]}
        self.assertEqual(R.lock_waits(res), {"check_lock_wait_s": 8, "check_run_s": 60,
                                             "checks_timed": 2, "fc_lock_wait_s": 3.5})
        self.assertEqual(R.lock_waits({"turns": [{}]})["check_lock_wait_s"], None)


# --------------------------------------------------------------- effort
class Effort(_Faked):
    def setUp(self):
        super().setUp()
        self.saved_env = os.environ.pop(R.EFFORT_ENV, None)

    def tearDown(self):
        os.environ.pop(R.EFFORT_ENV, None)
        if self.saved_env is not None:
            os.environ[R.EFFORT_ENV] = self.saved_env
        super().tearDown()

    def test_helpers(self):
        self.assertEqual(R.with_effort(["c", "--effort", "xhigh", "m"], "high"),
                         ["c", "--effort", "high", "m"])
        self.assertEqual(R.with_effort(["c", "--effort=xhigh", "m"], "high"),
                         ["c", "--effort=high", "m"])
        self.assertEqual(R.with_effort(["c", "-p", "m"], "high"),
                         ["c", "--effort", "high", "-p", "m"])
        self.assertEqual(R.with_effort(["c", "m"], None), ["c", "m"])
        self.assertIsNone(R.eval_effort({}))
        self.assertEqual(R.eval_effort({R.EFFORT_ENV: " High "}), "high")
        with self.assertRaises(ValueError):
            R.eval_effort({R.EFFORT_ENV: "ultra"})

    def test_override_reaches_every_turn(self):
        os.environ[R.EFFORT_ENV] = "high"
        self.script([("A = 1\n", _turn()), ("A = 2\n", _turn())], [(False, ""), (True, "")])
        r = self.run_item()
        self.assertEqual(len(self.argvs), 2)
        for a in self.argvs:
            self.assertEqual(R.effort_of(a), "high", a)
        self.assertEqual(r["effort"], "high")
        self.assertEqual(r["effort_override"], "high")

    def test_no_override_keeps_production_argv(self):
        self.script([("A = 1\n", _turn())], [(True, "")])
        r = self.run_item()
        self.assertEqual(self.argvs[0][:3], ["claude", "--effort", "xhigh"])
        self.assertEqual(r["effort"], "xhigh")
        self.assertIsNone(r["effort_override"])


# ------------------------------------------------------------ real build
MODEL_SRC = '''import Part
b = doc.addObject("Part::Feature", "Body")
b.Shape = Part.makeBox(60, 40, 30)
'''


@unittest.skipUnless(FC, "freecadcmd not found (FREECADCMD / ATECH_FREECADCMD)")
class RealSalvage(unittest.TestCase):
    """End to end: production argv (fc_build), a fake CLI that writes a real
    model.py and hangs, the turn killed, the real fc_build build + render."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="r270-real-")
        self.out = os.path.join(self.tmp, "out")
        self.env_log = os.path.join(self.tmp, "env.json")
        self.exe = _exe(os.path.join(self.tmp, "claude"),
                        FAKE_HANG % {"py": sys.executable, "env_log": self.env_log})
        self.saved = (R.FREECADCMD, R.TURN_TIMEOUT_S, R.production_argv)
        R.FREECADCMD = FC
        R.TURN_TIMEOUT_S = 4
        real, exe = R.production_argv, self.exe

        def argv(root, seed=None, request=None):
            p = real(root, seed, request)
            p["first"] = [exe] + p["first"][1:]
            p["resume"] = [exe] + p["resume"][1:]
            return p
        R.production_argv = argv
        os.environ["FAKE_MODEL_SRC"] = MODEL_SRC

    def tearDown(self):
        R.FREECADCMD, R.TURN_TIMEOUT_S, R.production_argv = self.saved
        os.environ.pop("FAKE_MODEL_SRC", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_killed_turn_is_built_and_rendered(self):
        item = {"id": "box", "prompt": "a box 60 x 40 x 30",
                "expect": {"overall_z": [29, 31]}}
        r = R.run_prompt(item, self.out, render=True)
        self.assertTrue(r["turns"][0]["timed_out"])
        self.assertIsNone(r["cost_usd"])
        self.assertEqual(len(r["builds"]), 1)
        b = r["builds"][0]
        self.assertTrue(b["ok"], b.get("error"))
        self.assertEqual(r["outcome"], "timed_out_built", (b.get("failures"), b.get("error")))
        self.assertTrue(r["built"])
        self.assertTrue(os.path.isfile(os.path.join(self.out, "box", "render.png")),
                        (b.get("render"), b.get("render_note")))
        self.assertTrue(os.path.isfile(os.path.join(self.out, "box", "render_inside.png")),
                        b.get("render_note"))
        self.assertIsNotNone(b.get("fc_lock_wait_s"))
        with open(self.env_log, encoding="utf-8") as fh:
            self.assertTrue(json.load(fh)["ATECH_TURN_T0"])


if __name__ == "__main__":
    unittest.main()
