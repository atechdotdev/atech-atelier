"""The build-quality benchmark harness itself (release PRD S15).

Runs under SYSTEM python (CI included). The FreeCAD half (fc_build.py) runs
in the bundled freecadcmd as a child, one at a time; those classes skip when
freecadcmd is missing (ATECH_REQUIRE_FREECADCMD=1 makes that a failure).

What is pinned:
  argv     the harness has no hand-typed claude flags; the command comes from
           production code (fc_build mode "argv") with exactly ONE --add-dir,
           the workspace production's build.new_workspace() made (R14), and
           the message delivered exactly once (argv or stdin, R35)
  metrics  init_s, first_text_s, ./check count, input tokens and
           permission denials parsed from a fake claude's stream
  fitness  the logged desk stand (fixtures/desk_stand_overlap.py) FAILS
           no_overlap (~20,046 mm3) and not_below_desk (z ~ -30 mm); a clean
           part passes; teeth counted on real involute gears; seed objects
           count for overlap
  rescore  first-apply / built come from model_attempt1.py / model.py, and
           the core prompt set is still the 12 of baseline_1
  S32      transcript.txt carries every tool result next to its call; output
           tokens are parsed per turn, summed per prompt (older runs: from
           the saved usage) and reported
  S35      three Atech prompts in the extra set, each with atech_check and
           machine-checked Atech keys; plain and Atech pass rates reported
           separately; atech_modules / board_upright / modules_inside FAIL a
           flat board, a speaker outside the case and a missing module
  R111     the argv job gives _turn_args the request text and the seeded
           document: a plain request gets no ATECH_ASSEMBLY.md copy and the
           plain prompt, an Atech request the copy and the Atech section
  S41      each run records its addon revision (commit, sha256, addon.diff,
           untracked files); materialize_addon rebuilds exactly that tree
           (sha256 equal); --rescore builds against it and the report names
           both the run's revision and the one rescored against
  R150     the materialized tree carries <repo>/projects/ (atech_ports) at
           the same revision, where acadagent.projects looks for it; a run's
           uncommitted projects/ changes are recorded and rebuilt; a pre-R150
           run and a commit with no projects/ say so; the child build gets
           ATECH_ARTIFACTS (the live meshes) unless the user set one
  S46      the live preview: every model.py change (any writer) is built on a
           COPY of the workspace after the panel's debounce, only when its
           bytes changed and it compiles, one build at a time, none after the
           turn ends; first clean preview time (harness and production
           estimate) and permission denials per command are reported; a run
           saved before S46 says "not measured"; fc_build's preview job runs
           build.apply + failures only
  R173     the shift-4 prompts: overall_z FAILS a proud lid (32 vs 30),
           channels_open FAILS end collars and closed bores, open_from_above
           FAILS a capped pot, open_along FAILS a USB-C slot over the cover
           (receptacle axis found in the mesh, left and right edge) and a
           box with no window, closed_around_board FAILS open ends and not a
           plug slot; the edit turn goes on the same session after the
           request builds, is scored on its own expectations (report +
           --rescore), has its own fix loop, and is not sent when the
           request never built
  S57      each turn records a stream timeline; every gap of >= 120 s with
           no tool call or result is split into retries, slow first event,
           stream stall, model, tool, startup and unattributed seconds
           (pure timelines + a fake claude that goes quiet); the report has
           a stall section, a headline row and a per-prompt column; a run
           without timelines says "not measured", never "none"
  R191/R192 the S6-3 toothbrush holder and S6-2 phone tripod mount are in
           the extra set (core prompts.json unchanged): volume_mm3 and
           notches_open pass the right holder and FAIL shallow or blind
           notches; insertion_path FAILS the lipped cradle (mouth 5.0 mm, as
           the dogfood measured) and passes the open one (9.0);
           no_failed_verdict follows production's build.failures()
  R213     the S7 c2n3 pegboard hook is in the extra set with 'mates': a
           1/4-inch board (5 mm, 6.35 holes, 25.4 pitch) modelled where the
           measured pegs put it FAILS the c2n3 hook (8 x 8 arm root 4.9 mm
           into the board: 313.6 mm3 = 8 x 8 x 4.9, its place named) also
           when the hook lies flat, passes the hook whose arm starts at the
           board face, and FAILS pegs 24 mm apart, a curl bent inside the
           board, too few pegs and a part with no peg
  R212     the S7 c1n4 desk clock is in the extra set with 'parts_engage':
           a flat 2 mm end cap that only touches the case FAILS, named,
           held only from one side; a lipped cap and the kit's own
           snap_fit_pair lid pass; a lip with 1.5 mm clearance and the lid
           without its snaps FAIL
"""
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.join(HERE, "eval")
ADDON = os.path.dirname(HERE)
sys.path.insert(0, EVAL)
sys.path.insert(0, ADDON)

import run_eval as R  # noqa: E402

FC = R.FREECADCMD if os.path.isfile(R.FREECADCMD) else None
if FC is None and os.environ.get("ATECH_REQUIRE_FREECADCMD") == "1":
    raise RuntimeError("ATECH_REQUIRE_FREECADCMD=1 but %s is missing" % R.FREECADCMD)

BASELINE_12 = ["l_bracket", "phone_stand", "snap_box", "spur_gear", "desk_organizer",
               "toy_car", "rocket", "hex_planter", "cable_clip", "rpi4_case", "mug",
               "headphone_hook"]


# ------------------------------------------------------------------ pure
class ArgvTemplates(unittest.TestCase):
    def test_render_fills_placeholders(self):
        t = ["claude", "-p", "--resume", R.SID_PH, "--x", R.MSG_PH]
        self.assertEqual(R.render_argv(t, "hello", "s1"),
                         ["claude", "-p", "--resume", "s1", "--x", "hello"])
        with self.assertRaises(ValueError):
            R.render_argv(t, "hello", None)
        self.assertIsNone(R.render_stdin(None, "hello"))
        self.assertEqual(R.render_stdin(R.MSG_PH, "hello"), "hello")

    def test_flags_elide_free_text(self):
        f = R.flags_of(["c", "-p", "--append-system-prompt", "x" * 50, R.MSG_PH])
        self.assertEqual(f, ["c", "-p", "--append-system-prompt", "<50 chars>", "<message>"])

    def test_harness_has_no_hand_copied_claude_flags(self):
        """The argv must come from production (P2): none of the flags the
        old hand-copied list carried may appear as a literal in run_eval."""
        with open(os.path.join(EVAL, "run_eval.py"), encoding="utf-8") as fh:
            src = fh.read()
        code = re.sub(r'"""[\s\S]*?"""', "", src)          # docstrings describe them
        code = "\n".join(l.split("#")[0] for l in code.splitlines())
        for flag in ("--permission-mode", "--add-dir", "--output-format", "--resume",
                     "--verbose", "--strict-mcp-config", "--allowedTools", "acceptEdits"):
            self.assertNotIn('"%s"' % flag, code, "hand-typed claude flag %s" % flag)


FAKE = r'''#!%(py)s
import json, sys, time
data = sys.stdin.read()
open(%(stdin_log)r, "w").write(data)
def out(o):
    print(json.dumps(o), flush=True)
time.sleep(0.05)
out({"type": "system", "subtype": "init", "session_id": "S1", "model": "m"})
time.sleep(0.05)
out({"type": "stream_event", "event": {"type": "content_block_delta",
     "delta": {"type": "text_delta", "text": "Plan"}}})
out({"type": "assistant", "message": {"content": [{"type": "text", "text": "Plan"}]}})
out({"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Write", "input": {"file_path": "/w/model.py"}},
    {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "./check"}},
    {"type": "tool_use", "id": "t3", "name": "Bash", "input": {"command": "./check --full"}},
    {"type": "tool_use", "name": "Bash", "input": {"command": "ls ./checker"}}]}})
out({"type": "user", "message": {"content": [
    {"type": "tool_result", "tool_use_id": "t2", "content": "CHECK PASS 3 bodies"},
    {"type": "tool_result", "tool_use_id": "t3", "is_error": True,
     "content": [{"type": "text", "text": "check: wall 0.4 mm"}, {"type": "image"}]}]}})
out({"type": "result", "result": "done", "is_error": False, "total_cost_usd": 0.5,
     "num_turns": 3, "permission_denials": [{"tool_name": "Bash"}],
     "usage": {"input_tokens": 10, "cache_creation_input_tokens": 200,
               "cache_read_input_tokens": 3000, "output_tokens": 50}})
'''


class TurnMetrics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="eval-harness-")
        self.stdin_log = os.path.join(self.tmp, "stdin.txt")
        self.exe = os.path.join(self.tmp, "claude")
        with open(self.exe, "w", encoding="utf-8") as fh:
            fh.write(FAKE % {"py": sys.executable, "stdin_log": self.stdin_log})
        os.chmod(self.exe, os.stat(self.exe).st_mode | stat.S_IEXEC)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stream_metrics(self):
        rec = R.claude_turn([self.exe, "-p"], self.tmp, "the message")
        with open(self.stdin_log, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "the message", "prompt not delivered on stdin")
        self.assertTrue(rec["ok"])
        self.assertEqual(rec["session"], "S1")
        self.assertEqual(rec["check_calls"], 2)          # not `ls ./checker`
        self.assertEqual(rec["input_tokens"], 3210)
        self.assertEqual(rec["permission_denials"], 1)
        self.assertEqual(rec["cost_usd"], 0.5)
        self.assertIsNotNone(rec["init_s"])
        self.assertIsNotNone(rec["first_text_s"])
        self.assertGreaterEqual(rec["first_text_s"], rec["init_s"])
        self.assertIsNotNone(rec["first_write_s"])
        self.assertEqual(rec["output_tokens"], 50)

    def test_transcript_has_tool_results(self):
        """S32: each tool call is followed by its result, errors marked."""
        rec = R.claude_turn([self.exe, "-p"], self.tmp, "the message")
        text = R.transcript_turn("the message", rec)
        self.assertIn("-> [t2] Bash ./check", text)
        self.assertIn("<- [t2] CHECK PASS 3 bodies", text)
        self.assertIn("<- [t3] ERROR check: wall 0.4 mm\n<image block>", text)
        self.assertLess(text.index("-> [t2]"), text.index("<- [t2]"))
        self.assertLess(text.index("<- [t2]"), text.index("<- [t3]"))

    def test_long_tool_result_is_clipped_not_dropped(self):
        t = R._clip("x" * (R.TOOL_RESULT_CHARS + 7))
        self.assertTrue(t.startswith("x" * R.TOOL_RESULT_CHARS))
        self.assertIn("[7 more chars]", t)
        self.assertEqual(R.tool_result_text([{"type": "text", "text": "a"},
                                             {"type": "text", "text": "b"}]), "a\nb")

    def test_input_tokens_missing_stays_missing(self):
        self.assertIsNone(R.input_tokens(None))
        self.assertIsNone(R.input_tokens({"output_tokens": 5}))

    def test_output_tokens(self):
        self.assertEqual(R.output_tokens({"output_tokens": 5}), 5)
        self.assertIsNone(R.output_tokens({"input_tokens": 5}))
        self.assertIsNone(R.output_tokens(None))
        # a run saved before S32 carries only each turn's usage
        old = [{"usage": {"output_tokens": 7}}, {"usage": {"output_tokens": 3}}]
        self.assertEqual(R.turns_output_tokens(old), 10)
        self.assertEqual(R.turns_output_tokens([{"output_tokens": 4}, {"usage": {}}]), None)
        self.assertIsNone(R.turns_output_tokens([]))


class Rescore(unittest.TestCase):
    def setUp(self):
        self.run = tempfile.mkdtemp(prefix="eval-rescore-")

    def tearDown(self):
        shutil.rmtree(self.run, ignore_errors=True)

    def _saved(self, pid, files):
        d = os.path.join(self.run, pid)
        os.makedirs(d)
        for f in files:
            with open(os.path.join(d, f), "w", encoding="utf-8") as fh:
                fh.write("# %s\n" % f)

    @staticmethod
    def fake_build(verdicts):
        def build(job):
            with open(os.path.join(job["workspace"], "model.py"), encoding="utf-8") as fh:
                tag = fh.read().strip()[2:]
            ok = verdicts[tag]
            return ({"ok": ok, "failures": "", "error": "" if ok else "boom",
                     "checks": [{"check": "x", "pass": ok, "detail": 1}],
                     "fitness": [{"check": "no_overlap", "pass": True, "detail": {}}]}, "")
        return build

    def test_first_attempt_and_built_from_saved_files(self):
        self._saved("a", ["model_attempt1.py", "model_attempt2.py", "model.py"])
        r = {"id": "a", "prompt": "p", "built": True, "builds": [{}, {}], "final_build": {}}
        R.rescore_result(r, self.run, {}, self.fake_build(
            {"model_attempt1.py": False, "model.py": True}))
        self.assertFalse(r["first_apply_pass"])
        self.assertTrue(r["built"])
        self.assertEqual(len(r["builds"]), 2)            # not "first attempt" in report()
        self.assertTrue(r["pass"])
        self.assertTrue(r["fit_pass"])

    def test_first_time_build_counts_once(self):
        self._saved("b", ["model_attempt1.py", "model.py"])
        r = {"id": "b", "prompt": "p", "built": True, "builds": [{}], "final_build": {}}
        R.rescore_result(r, self.run, {}, self.fake_build(
            {"model_attempt1.py": True, "model.py": True}))
        self.assertTrue(r["first_apply_pass"] and r["built"])
        self.assertEqual(len(r["builds"]), 1)

    def test_nothing_saved_is_not_built(self):
        r = {"id": "c", "prompt": "p", "built": False, "builds": [], "final_build": {}}
        R.rescore_result(r, self.run, {}, self.fake_build({}))
        self.assertFalse(r["built"])
        self.assertFalse(r["first_apply_pass"])

    def test_run_names(self):
        self.assertEqual(R.resolve_run("baseline_1"), ("baseline_1", "baseline", 1))
        self.assertEqual(R.resolve_run("round_3"), ("round_3", "round", 3))
        self.assertEqual(R.resolve_run("baseline_extra_2"),
                         ("baseline_extra_2", "baseline_extra", 2))
        self.assertEqual(R.resolve_run("4", "round"), ("round_4", "round", 4))
        with self.assertRaises(ValueError):
            R.resolve_run("../etc")


class AddonRevision(unittest.TestCase):
    """S41, pure: a throwaway git repo stands in for this one (git only)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="eval-addon-rev-")
        self.repo = os.path.join(self.tmp, "repo")
        self.addon = os.path.join(self.repo, "addon", "AcadAgent")
        os.makedirs(os.path.join(self.addon, "acadagent"))
        self.write("acadagent/kit.py", "def fillet_safe(s):\n    return s, 'ok'\n")
        self.write("acadagent/build.py", "X = 1\n")
        self.git("init", "-q")
        self.git("add", "addon")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "r1")
        self.c1 = self.git("rev-parse", "HEAD").strip()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *a):
        return subprocess.run(["git", "-C", self.repo] + list(a), check=True,
                              capture_output=True, text=True).stdout

    def write(self, rel, text):
        path = os.path.join(self.addon, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def read(self, root, rel):
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            return fh.read()

    def test_clean_tree_records_the_commit_and_rebuilds_it(self):
        info = R.addon_revision(os.path.join(self.tmp, "run"), self.repo, self.addon)
        self.assertEqual(info["commit"], self.c1)
        self.assertIs(info["dirty"], False)
        self.assertIsNone(info["diff"])
        self.assertEqual(info["path"], "addon/AcadAgent")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "run", "addon.diff")))
        # bytecode caches and git-ignored tool caches do not change the hash
        # (measured on this repo: .pytest_cache / .ruff_cache made the live
        # tree's hash differ from its own rebuild)
        self.write("acadagent/__pycache__/kit.cpython-311.pyc", "junk")
        self.write(".gitignore", ".pytest_cache/\n")
        self.git("add", "addon")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "r2")
        self.write(".pytest_cache/v/cache/nodeids", "[]")
        info = R.addon_revision(os.path.join(self.tmp, "run"), self.repo, self.addon)
        self.assertIs(info["dirty"], False)
        out, ok = R.materialize_addon(info, os.path.join(self.tmp, "m"), None, self.repo)
        self.assertTrue(ok)
        self.assertIn("return s, 'ok'", self.read(out, "acadagent/kit.py"))

    def test_dirty_tree_is_rebuilt_from_commit_diff_and_untracked(self):
        run = os.path.join(self.tmp, "run")
        # the S28 change, uncommitted, plus a new untracked module
        self.write("acadagent/kit.py", "def fillet_safe(s):\n    return s\n")
        self.write("acadagent/new_mod.py", "Y = 2\n")
        info = R.addon_revision(run, self.repo, self.addon)
        self.assertIs(info["dirty"], True)
        self.assertEqual(info["diff"], "addon.diff")
        self.assertEqual(info["untracked"], ["addon/AcadAgent/acadagent/new_mod.py"])
        self.assertTrue(os.path.isfile(os.path.join(
            run, "addon_untracked", "addon", "AcadAgent", "acadagent", "new_mod.py")))
        # the live tree moves on after the run
        self.write("acadagent/kit.py", "raise SystemExit('later tree')\n")
        self.assertNotEqual(R.addon_tree_sha256(self.addon), info["sha256"])
        out, ok = R.materialize_addon(info, os.path.join(self.tmp, "m"), run, self.repo)
        self.assertTrue(ok, "rebuilt addon differs from the run's")
        self.assertEqual(self.read(out, "acadagent/kit.py"),
                         "def fillet_safe(s):\n    return s\n")
        self.assertEqual(self.read(out, "acadagent/new_mod.py"), "Y = 2\n")
        # the repo itself was only read
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.c1)
        self.assertIn("later tree", self.read(self.addon, "acadagent/kit.py"))

    def test_user_diff_config_does_not_break_the_saved_diff(self):
        # diff.noprefix / color.diff=always in the user's git config would
        # write a patch `git apply` rejects; the recorded diff pins them.
        self.git("config", "diff.noprefix", "true")
        self.git("config", "color.diff", "always")
        run = os.path.join(self.tmp, "run")
        self.write("acadagent/kit.py", "def fillet_safe(s):\n    return s\n")
        info = R.addon_revision(run, self.repo, self.addon)
        out, ok = R.materialize_addon(info, os.path.join(self.tmp, "m"), run, self.repo)
        self.assertTrue(ok)
        self.assertEqual(self.read(out, "acadagent/kit.py"),
                         "def fillet_safe(s):\n    return s\n")

    def test_sabotage_a_wrong_record_is_caught(self):
        info = R.addon_revision(None, self.repo, self.addon)
        info["sha256"] = "0" * 64
        _, ok = R.materialize_addon(info, os.path.join(self.tmp, "m"), None, self.repo)
        self.assertIs(ok, False)

    def test_no_git_leaves_the_commit_missing(self):
        plain = os.path.join(self.tmp, "nogit", "addon", "AcadAgent")
        os.makedirs(plain)
        info = R.addon_revision(None, os.path.join(self.tmp, "nogit"), plain)
        self.assertIsNone(info["commit"])
        self.assertIn("git", info["error"])
        self.assertTrue(R.describe_addon(info).startswith("not recorded"))

    def test_rescore_passes_the_addon_to_every_build(self):
        d = os.path.join(self.tmp, "run", "a")
        os.makedirs(d)
        for f in ("model_attempt1.py", "model.py"):
            with open(os.path.join(d, f), "w", encoding="utf-8") as fh:
                fh.write("# x\n")
        seen = []

        def build(job):
            seen.append(job.get("addon"))
            return {"ok": True, "failures": "", "checks": [], "fitness": []}, ""
        r = {"id": "a", "prompt": "p", "built": True, "builds": [{}], "final_build": {}}
        R.rescore_result(r, os.path.join(self.tmp, "run"), {}, build, addon="/old/addon")
        self.assertEqual(seen, ["/old/addon", "/old/addon"])
        seen[:] = []
        R.rescore_result(r, os.path.join(self.tmp, "run"), {}, build)
        self.assertEqual(seen, [None, None])

    def write_projects(self, rel, text):
        path = os.path.join(self.repo, "projects", rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_r150_projects_come_with_the_tree_at_the_same_revision(self):
        # R150: rescoring round_extra_5 at its own revision rebuilt an addon
        # tree with no projects/, so every Atech file raised
        # ModuleNotFoundError: No module named 'atech_ports'.
        self.write_projects("atech_ports.py", "REV = 1\n")
        self.git("add", "projects")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "p1")
        run = os.path.join(self.tmp, "run")
        # uncommitted projects/ change + an untracked projects/ file at run time
        self.write_projects("atech_ports.py", "REV = 2\n")
        self.write_projects("atech_modules.py", "M = 1\n")
        addon_sha = R.addon_tree_sha256(self.addon)
        info = R.addon_revision(run, self.repo, self.addon)
        self.assertIs(info["dirty"], True)
        self.assertEqual(info["sha256"], addon_sha, "sha256 stays the addon's own")
        self.assertIn("projects/atech_modules.py", info["untracked"])
        self.assertTrue(info.get("projects_sha256"))
        # the live projects/ moves on after the run
        self.write_projects("atech_ports.py", "raise SystemExit('later')\n")
        dest = os.path.join(self.tmp, "m")
        out, ok = R.materialize_addon(info, dest, run, self.repo)
        self.assertTrue(ok)
        # where acadagent.projects._builder_candidates looks from the addon
        pdir = os.path.normpath(os.path.join(out, "acadagent", "..", "..", "..", "projects"))
        self.assertEqual(pdir, os.path.join(dest, "projects"))
        self.assertEqual(self.read(pdir, "atech_ports.py"), "REV = 2\n")
        self.assertEqual(self.read(pdir, "atech_modules.py"), "M = 1\n")
        rec = R._projects_record(dest, info)
        self.assertEqual(rec["projects"], "projects")
        self.assertIs(rec["projects_verified"], True)
        # sabotage: a wrong projects record is caught
        rec = R._projects_record(dest, dict(info, projects_sha256="0" * 64))
        self.assertIs(rec["projects_verified"], False)

    def test_r150_run_before_r150_says_projects_came_from_the_commit(self):
        self.write_projects("atech_ports.py", "REV = 1\n")
        self.git("add", "projects")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "p1")
        c2 = self.git("rev-parse", "HEAD").strip()
        old = {"path": "addon/AcadAgent", "commit": c2}   # an S41-era record
        dest = os.path.join(self.tmp, "m")
        R.materialize_addon(old, dest, None, self.repo)
        self.assertEqual(self.read(os.path.join(dest, "projects"), "atech_ports.py"),
                         "REV = 1\n")
        rec = R._projects_record(dest, old)
        self.assertNotIn("projects_verified", rec)
        self.assertIn("predates R150", rec["note"])
        if rec.get("library"):
            self.assertIn("not revisioned", rec["note"])

    def test_r150_commit_without_projects_still_materializes_and_says_so(self):
        info = R.addon_revision(None, self.repo, self.addon)     # c1: no projects/
        dest = os.path.join(self.tmp, "m")
        out, ok = R.materialize_addon(info, dest, None, self.repo)
        self.assertTrue(ok)
        self.assertFalse(os.path.exists(os.path.join(dest, "projects")))
        rec = R._projects_record(dest, info)
        self.assertIsNone(rec["projects"])
        self.assertIn("cannot import atech_ports", rec["note"])

    def test_r150_materialized_build_is_pointed_at_the_mesh_library(self):
        seen = []

        class P(object):
            stdout, stderr = "no marker", ""

        def fake_run(argv, env=None, **kw):
            seen.append(env)
            return P()
        saved = (R.subprocess.run, R.live_library, os.environ.pop(R.LIBRARY_ENV, None))
        R.subprocess.run, R.live_library = fake_run, lambda repo=R.REPO: "/lib/models"
        try:
            R.fc_job({"mode": "build", "addon": "/old/addon"})
            R.fc_job({"mode": "build"})
            os.environ[R.LIBRARY_ENV] = "/mine"
            R.fc_job({"mode": "build", "addon": "/old/addon"})
        finally:
            R.subprocess.run, R.live_library = saved[0], saved[1]
            os.environ.pop(R.LIBRARY_ENV, None)
            if saved[2] is not None:
                os.environ[R.LIBRARY_ENV] = saved[2]
        self.assertEqual(seen[0][R.LIBRARY_ENV], "/lib/models")
        self.assertEqual(seen[0]["EVAL_ADDON"], "/old/addon")
        self.assertNotIn(R.LIBRARY_ENV, seen[1])      # this tree finds its own
        self.assertEqual(seen[2][R.LIBRARY_ENV], "/mine")   # the user's wins

    def test_unrecorded_run_says_it_used_the_current_tree(self):
        addon, rec = R.resolve_addon("run", {"date": "d"}, self.tmp, self.tmp)
        self.assertIsNone(addon)
        self.assertEqual(rec["source"], "current tree")
        self.assertIn("predates S41", rec["note"])

    def test_report_names_both_revisions(self):
        run_rev = {"commit": "a" * 40, "dirty": True, "sha256": "b" * 64,
                   "untracked": ["x.py"], "diff": "addon.diff"}
        again = dict(run_rev, source="run's recorded revision", verified=True)
        md = R.report([_result("a", True, True, True)], 2,
                      {"date": "d", "addon": run_rev, "rescore_of": "round_2",
                       "rescored": "now", "rescore_addon": again}, "round")
        self.assertIn("| addon revision of the run | aaaaaaaaaaaa + uncommitted changes "
                      "(addon.diff, 1 untracked), addon sha256 bbbbbbbbbbbb |", md)
        self.assertIn("| addon rescored against (run's recorded revision) | aaaaaaaaaaaa",
                      md)
        self.assertIn("sha256 matches the run's", md)
        md = R.report([_result("a", True, True, True)], 1, {"date": "d"}, "t")
        self.assertIn("| addon revision of the run | not recorded (run predates S41) |", md)


def _result(pid, built, passed, fit, atech=None, fit_total=1):
    r = {"id": pid, "prompt": pid, "outcome": "built" if built else "x", "built": built,
         "pass": passed, "fit_pass": fit, "fitness_total": fit_total,
         "fitness_passed": fit_total if fit else 0, "first_apply_pass": built,
         "builds": [{}], "turns": [{"usage": {"output_tokens": 100}}],
         "final_build": {"checks": [], "fitness": []}, "checks_passed": 1,
         "checks_total": 1, "wall_s": 10.0, "cost_usd": 0.1, "fix_rounds": 0}
    if atech is not None:
        r["atech"] = atech
    return r


class Report(unittest.TestCase):
    """S35 / S32 in the report (pure: no files, no freecadcmd)."""

    def test_plain_and_atech_pass_rates_are_separate(self):
        rs = [_result("a", True, True, True, atech=False),
              _result("b", True, False, True, atech=False),
              _result("c", True, True, False, atech=True),    # Atech check failed
              _result("d", True, True, True, atech=True)]
        rows = {g[0]: g[1:] for g in R.group_rows(rs, {})}
        # (n, built, first, expectations, fitness, all)
        self.assertEqual(rows["plain"], (2, 2, 2, 1, 2, 1))
        self.assertEqual(rows["Atech"], (2, 2, 2, 2, 1, 1))
        md = R.report(rs, 1, {"date": "d"}, "t")
        self.assertIn("## Plain vs Atech prompts", md)
        self.assertIn("| plain | 2 | 2/2 | 2/2 | 1/2 | 2/2 | 1/2 |", md)
        self.assertIn("| Atech | 2 | 2/2 | 2/2 | 2/2 | 1/2 | 1/2 |", md)

    def test_group_of_an_old_run_comes_from_the_prompt_files(self):
        items = R.load_expectations()
        self.assertTrue(R.is_atech_result({"id": "atech_clock_enclosure"}, items))
        self.assertFalse(R.is_atech_result({"id": "l_bracket"}, items))
        self.assertFalse(R.is_atech_result({"id": "no_such_prompt"}, items))

    def test_output_tokens_in_report_from_saved_usage(self):
        rs = [_result("a", True, True, True, atech=False),
              _result("b", True, True, True, atech=False)]
        md = R.report(rs, 1, {"date": "d"}, "t")
        self.assertIn("| output tokens (total / median per prompt) | 200 / 100 (n=2) |", md)
        rs[0]["turns"] = [{"usage": {}}]
        rs[0]["output_tokens"] = None
        rs[1]["turns"] = [{}]
        rs[1]["output_tokens"] = None
        md = R.report(rs, 1, {"date": "d"}, "t")
        self.assertIn("| output tokens (total / median per prompt) | not measured |", md)


# ------------------------------------------------------------- S57 (pure)
def _nightlight_timeline():
    """The shape of r8's atech_nightlight_closed stall: a ./check result at
    50 s, two API retries, a first event at 400 s, a reply that goes silent
    for 290 s mid-stream, and the 900 s timeout."""
    return [[1.0, "init", None], [3.0, "msg_start", None], [40.0, "msg_stop", 900],
            [40.0, "tool_use", "t1"], [50.0, "tool_result", "t1"],
            [100.0, "retry", 30.0], [200.0, "retry", 60.0],
            [400.0, "msg_start", None], [700.0, "quiet", 410.0],
            [800.0, "msg_stop", 3000]]


class StallAttribution(unittest.TestCase):
    def test_nightlight_gap_is_split_and_numbered(self):
        turn = {"wall_s": 900.0, "timed_out": True, "timeline": _nightlight_timeline()}
        gaps = R.turn_gaps(turn)
        self.assertEqual(len(gaps), 1)
        g = gaps[0]
        self.assertEqual((g["from_s"], g["to_s"], g["gap_s"]), (50.0, 900.0, 850.0))
        self.assertEqual(g["after"], "tool_result t1")
        self.assertEqual(g["until"], "timeout")
        # failed attempts 50-100 and 130-200, backoffs 100-130 and 200-260
        self.assertEqual(g["retries_s"], 210.0)
        # 260-400 before the first event, 800-900 after the last message
        self.assertEqual(g["first_event_s"], 240.0)
        self.assertEqual(g["stream_stall_s"], 290.0)          # 410-700
        self.assertEqual(g["model_s"], 110.0)                 # 400-410, 700-800
        self.assertEqual(g["tool_s"] + g["startup_s"] + g["unattributed_s"], 0.0)
        total = sum(g[c + "_s"] for c in R.STALL_CATEGORIES)
        self.assertAlmostEqual(total, g["gap_s"], places=1)   # every second attributed
        self.assertEqual((g["requests"], g["retries"], g["output_tokens"]), (1, 2, 3000))
        self.assertEqual(g["cause"], "stream_stall")

    def test_slow_first_event_and_short_gaps(self):
        tl = [[0.5, "init", None], [216.0, "msg_start", None], [230.0, "msg_stop", 1772],
              [230.0, "tool_use", "w"], [230.2, "tool_result", "w"],
              [231.0, "msg_start", None], [240.0, "msg_stop", 50]]
        gaps = R.turn_gaps({"wall_s": 249.4, "timeline": tl})
        self.assertEqual(len(gaps), 1, gaps)                  # 230 -> 249 is short
        g = gaps[0]
        self.assertEqual(g["after"], "request")
        self.assertEqual(g["cause"], "first_event")
        self.assertEqual(g["first_event_s"], 215.5)
        self.assertEqual(g["startup_s"], 0.5)
        self.assertEqual(g["model_s"], 14.0)

    def test_tool_time_is_tool(self):
        tl = [[0.1, "init", None], [1.0, "msg_start", None], [2.0, "tool_use", "c"],
              [3.0, "msg_stop", 10], [200.0, "tool_result", "c"]]
        g = R.turn_gaps({"wall_s": 201.0, "timeline": tl})[0]
        self.assertEqual(g["cause"], "tool")
        self.assertEqual(g["tool_s"], 197.0)

    def test_no_stream_events_is_unattributed_not_guessed(self):
        tl = [[0.2, "init", None], [300.0, "tool_use", "a"], [301.0, "tool_result", "a"]]
        g = R.turn_gaps({"wall_s": 310.0, "timeline": tl})[0]
        self.assertEqual(g["cause"], "unattributed")
        self.assertEqual(g["first_event_s"] + g["model_s"], 0.0)
        self.assertIsNone(g["output_tokens"])

    def test_old_turns_are_not_measured(self):
        self.assertIsNone(R.turn_gaps({"wall_s": 900.0}))
        self.assertIsNone(R.request_stalls({"turns": [{"wall_s": 900.0}]}))
        r = _result("old", True, True, True)
        self.assertEqual(R.stall_cell(r), "not measured")
        md = R.report([r], 1, {"date": "d"}, "t")
        self.assertIn("## Stalls over 120 s (S57)", md)
        self.assertIn("Not measured: the run predates S57", md)
        self.assertIn("| gaps >= 120 s with no tool activity (S57; causes below) | "
                      "not measured (run predates S57) |", md)

    def test_report_section_column_and_headline(self):
        slow = _result("atech_nightlight_closed", False, False, False)
        slow["turns"] = [{"wall_s": 900.0, "timed_out": True, "started_s": 0.0,
                          "timeline": _nightlight_timeline()}]
        quick = _result("mug", True, True, True)
        quick["turns"] = [{"wall_s": 20.0, "timeline": [[0.1, "init", None]]}]
        slow["stalls"] = R.request_stalls(slow)
        self.assertEqual(slow["stalls"][0]["turn"], 1)
        self.assertEqual(R.stall_cell(slow), "1 (850 s stream_stall)")
        self.assertEqual(R.stall_cell(quick), "0")          # recomputed from turns
        md = R.report([slow, quick], 1, {"date": "d"}, "t")
        self.assertIn("| atech_nightlight_closed | 1 | 50 | 900 | 850 | tool_result t1 | "
                      "210 | 240 | 290 | 110 | 0 | 0 | 0 | 1 | 2 | 3000 | "
                      "**stream_stall** |", md)
        self.assertIn("| gaps >= 120 s with no tool activity (S57; causes below) | "
                      "1 in 1 of 2 prompts, 850 s total; cause: stream_stall 1 |", md)
        self.assertIn("| stalls >120 s | render |", md)
        self.assertIn("| 1 (850 s stream_stall) | - |", md)


FAKE_STALL = r'''#!%(py)s
import json, sys, time
sys.stdin.read()
def out(o):
    print(json.dumps(o), flush=True)
out({"type": "system", "subtype": "init", "session_id": "S1", "model": "m"})
out({"type": "system", "subtype": "api_retry", "attempt": 1, "error_status": 529,
     "retry_delay_ms": 300})
time.sleep(0.6)
out({"type": "stream_event", "event": {"type": "message_start"}})
out({"type": "stream_event", "event": {"type": "content_block_delta",
     "delta": {"type": "text_delta", "text": "Pl"}}})
time.sleep(0.6)
out({"type": "stream_event", "event": {"type": "content_block_delta",
     "delta": {"type": "text_delta", "text": "an"}}})
out({"type": "stream_event", "event": {"type": "message_delta",
     "usage": {"output_tokens": 42}}})
out({"type": "stream_event", "event": {"type": "message_stop"}})
out({"type": "assistant", "message": {"content": [
    {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "./check"}}]}})
out({"type": "user", "message": {"content": [
    {"type": "tool_result", "tool_use_id": "t1", "content": "CHECK PASS"}]}})
out({"type": "result", "result": "done", "is_error": False, "duration_api_ms": 1234,
     "usage": {"output_tokens": 42}})
'''


FAKE_DIES_MID_STREAM = r'''#!%(py)s
import json, sys, time
sys.stdin.read()
def out(o):
    print(json.dumps(o), flush=True)
out({"type": "system", "subtype": "init", "session_id": "S1", "model": "m"})
out({"type": "stream_event", "event": {"type": "message_start"}})
out({"type": "stream_event", "event": {"type": "content_block_delta",
     "delta": {"type": "text_delta", "text": "Pl"}}})
time.sleep(0.8)
'''


class StallStream(unittest.TestCase):
    """S57 end to end: the timeline comes from a real stream parse."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="eval-stall-")
        self.exe = os.path.join(self.tmp, "claude")
        with open(self.exe, "w", encoding="utf-8") as fh:
            fh.write(FAKE_STALL % {"py": sys.executable})
        os.chmod(self.exe, os.stat(self.exe).st_mode | stat.S_IEXEC)
        self.saved = R.STREAM_QUIET_S
        R.STREAM_QUIET_S = 0.3

    def tearDown(self):
        R.STREAM_QUIET_S = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_timeline_attributes_a_quiet_stream(self):
        rec = R.claude_turn([self.exe, "-p"], self.tmp, "m")
        self.assertTrue(rec["ok"])
        kinds = [k for _t, k, _i in rec["timeline"]]
        for k in ("init", "retry", "msg_start", "quiet", "msg_stop", "tool_use",
                  "tool_result", "result"):
            self.assertIn(k, kinds)
        self.assertEqual(rec["duration_api_ms"], 1234)
        self.assertEqual(rec["stalls"], [], "no gap reaches 120 s")
        g = R.turn_gaps(rec, threshold=0.5)[0]
        self.assertEqual(g["after"], "request")
        self.assertEqual(g["until"], "tool_use t1")
        self.assertEqual(g["retries"], 1)
        self.assertGreaterEqual(g["retries_s"], 0.25)          # the 0.3 s backoff
        self.assertGreaterEqual(g["retries_s"] + g["first_event_s"], 0.5)
        self.assertGreaterEqual(g["stream_stall_s"], 0.5)      # the 0.6 s silence
        self.assertEqual(g["output_tokens"], 42)
        self.assertEqual(g["requests"], 1)

    def test_silence_until_the_end_is_a_stream_stall(self):
        """The r8 shape: a reply goes silent mid-message and the turn ends
        (timeout / crash) with no later stream event. The trailing silence
        is a stream stall, not model time."""
        with open(self.exe, "w", encoding="utf-8") as fh:
            fh.write(FAKE_DIES_MID_STREAM % {"py": sys.executable})
        rec = R.claude_turn([self.exe, "-p"], self.tmp, "m")
        self.assertFalse(rec["ok"])
        self.assertEqual(rec["timeline"][-1][1], "quiet", rec["timeline"])
        g = R.turn_gaps(rec, threshold=0.5)[0]
        self.assertEqual(g["cause"], "stream_stall", g)
        self.assertGreaterEqual(g["stream_stall_s"], 0.5)
        self.assertLess(g["model_s"], 0.3)


# ------------------------------------------------------------- S46 (pure)
class _FakePreviewBuild(object):
    """A preview build_fn: records what it was handed, sleeps `secs`,
    counts concurrent calls, and scribbles on the model.py it was given
    (as fc_build's headless patch does) to prove it is a copy."""

    def __init__(self, secs=0.0, ok=True, failures=""):
        self.secs, self.ok, self.failures = secs, ok, failures
        self.jobs, self.codes = [], []
        self.active = self.max_active = 0
        self.lock = __import__("threading").Lock()

    def __call__(self, job):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            path = os.path.join(job["workspace"], "model.py")
            with open(path, encoding="utf-8") as fh:
                self.codes.append(fh.read())
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# patched by the build\n")
            self.jobs.append(dict(job))
            __import__("time").sleep(self.secs)
            return {"ok": self.ok, "failures": self.failures, "error": "",
                    "build_seconds": 0.25}, ""
        finally:
            with self.lock:
                self.active -= 1


def _wait_for(pred, timeout=5.0):
    import time as _t
    end = _t.time() + timeout
    while _t.time() < end:
        if pred():
            return True
        _t.sleep(0.02)
    return False


class LivePreview(unittest.TestCase):
    """S46: every model.py write is built as it happens, as the panel's
    live preview does (content gate, compile gate, one at a time)."""

    DEB, POLL = 0.1, 0.01

    def setUp(self):
        self.ws = tempfile.mkdtemp(prefix="eval-preview-")
        self.script = os.path.join(self.ws, "model.py")

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def write(self, text):
        with open(self.script, "w", encoding="utf-8") as fh:
            fh.write(text)

    def live(self, fake, t_ref=None):
        import time as _t
        return R.LivePreview(self.ws, {"mode": "build", "expect": {"x": 1}, "prompt": "p",
                                       "seed": None}, _t.time() if t_ref is None else t_ref,
                             turn=2, build_fn=fake, debounce=self.DEB, poll=self.POLL).start()

    def test_each_write_is_built_on_a_copy(self):
        fake = _FakePreviewBuild()
        lp = self.live(fake)
        self.write("A = 1\n")                                   # a Write
        self.assertTrue(_wait_for(lambda: len(fake.jobs) == 1))
        self.write("A = 1\nB = (\n")                            # half-written: not built
        _wait_for(lambda: lp.skipped >= 1)
        self.write("A = 2\n")                                   # e.g. a Bash `sed -i`
        self.assertTrue(_wait_for(lambda: len(fake.jobs) == 2))
        recs = lp.stop()
        self.assertEqual(fake.codes, ["A = 1\n", "A = 2\n"])
        self.assertEqual(lp.skipped, 1, "the non-compiling file was skipped, not built")
        with open(self.script, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "A = 2\n", "the agent's model.py was touched")
        for job in fake.jobs:
            self.assertNotEqual(os.path.realpath(job["workspace"]), os.path.realpath(self.ws))
            self.assertFalse(os.path.exists(job["workspace"]), "preview copy left behind")
            self.assertTrue(job["preview"])
            self.assertIsNone(job["render"])
            self.assertEqual((job["mode"], job["expect"]), ("build", {"x": 1}))
        self.assertEqual([r["turn"] for r in recs], [2, 2])
        r = recs[0]
        self.assertLessEqual(r["settled_s"], r["start_s"])
        self.assertLessEqual(r["start_s"], r["done_s"])
        self.assertAlmostEqual(r["prod_s"], r["settled_s"] + self.DEB + 0.25, places=2)
        self.assertGreaterEqual(r["start_s"] - r["settled_s"], self.DEB - 0.005,
                                "built before the debounce")

    def test_same_bytes_and_starting_file_are_not_rebuilt(self):
        self.write("A = 1\n")                                  # there before the turn
        fake = _FakePreviewBuild()
        lp = self.live(fake)
        self.write("A = 1\n")                                  # identical rewrite
        import time as _t
        _t.sleep(self.DEB * 3)
        self.write("A = 3\n")
        self.assertTrue(_wait_for(lambda: len(fake.jobs) == 1))
        self.write("A = 3\n")
        _t.sleep(self.DEB * 3)
        lp.stop()
        self.assertEqual(fake.codes, ["A = 3\n"])

    def test_one_build_at_a_time_and_a_change_meanwhile_is_built_after(self):
        fake = _FakePreviewBuild(secs=0.4)
        lp = self.live(fake)
        self.write("A = 1\n")
        self.assertTrue(_wait_for(lambda: fake.active == 1))
        self.write("A = 2\n")                                  # during the build
        self.assertTrue(_wait_for(lambda: len(fake.jobs) == 2, 5))
        lp.stop()
        self.assertEqual(fake.max_active, 1)
        self.assertEqual(fake.codes, ["A = 1\n", "A = 2\n"])

    def test_stop_finishes_the_build_in_flight_and_starts_none(self):
        fake = _FakePreviewBuild(secs=0.4)
        lp = self.live(fake)
        self.write("A = 1\n")
        self.assertTrue(_wait_for(lambda: fake.active == 1))
        self.write("A = 2\n")                                  # would be next
        recs = lp.stop()
        self.assertEqual(len(recs), 1, "the build in flight is recorded")
        self.assertEqual(fake.codes, ["A = 1\n"], "no preview after the turn ended")
        self.assertGreater(lp.stop_wait_s, 0.0, "the wait on the build in flight is recorded")

    def test_a_raising_build_does_not_kill_the_watch(self):
        calls = []

        def boom(job):
            calls.append(job)
            if len(calls) == 1:
                raise ValueError("bad json from the child")
            return {"ok": True, "failures": "", "error": "", "build_seconds": 0.1}, ""
        lp = self.live(boom)
        self.write("A = 1\n")
        self.assertTrue(_wait_for(lambda: len(calls) == 1))
        self.write("A = 2\n")
        self.assertTrue(_wait_for(lambda: len(calls) == 2), "the watch died with the build")
        recs = lp.stop()
        self.assertEqual([r["ok"] for r in recs], [False, True])
        self.assertIn("preview build raised", recs[0]["error"])
        self.assertTrue(recs[0]["harness_crash"])

    def test_first_good_preview(self):
        recs = [{"ok": False, "failures": ""}, {"ok": True, "failures": "Box: 2 solids"},
                {"ok": True, "failures": "", "done_s": 12.0}, {"ok": True, "failures": ""}]
        self.assertEqual(R.first_good_preview(recs)["done_s"], 12.0)
        self.assertIsNone(R.first_good_preview(recs[:2]))
        self.assertIsNone(R.first_good_preview(None))

    def test_source_compiles_is_build_compiles(self):
        self.assertTrue(R.source_compiles(b"\xef\xbb\xbfA = 1\n"))    # BOM, as utf-8-sig
        self.assertFalse(R.source_compiles(b"A = (\n"))
        self.assertFalse(R.source_compiles(b"\xff\xfe"))


class Denials(unittest.TestCase):
    """S46: permission denials per command."""

    def test_commands_from_input_or_stream(self):
        res = {"permission_denials": [
            {"tool_name": "Bash", "tool_use_id": "t1", "tool_input": {
                "command": "sed -i 's/^A = 1/A = 2/' model.py && ./check"}},
            {"tool_name": "Bash", "tool_use_id": "t2"},
            {"tool_name": "Write", "tool_use_id": "t3"},
            {"tool_name": "Bash"}]}
        calls = {"t2": {"command": "ls ./checker"}, "t3": {"file_path": "/etc/x"}}
        d = R.denial_records(res, calls)
        self.assertEqual([x["tool"] for x in d], ["Bash", "Bash", "Write", "Bash"])
        self.assertEqual(d[0]["command"], "sed -i 's/^A = 1/A = 2/' model.py && ./check")
        self.assertEqual([x["runs_check"] for x in d], [True, False, False, False])
        self.assertEqual(d[1]["command"], "ls ./checker")
        self.assertEqual(d[2]["command"], "/etc/x")
        self.assertIsNone(d[3]["command"], "a missing command stays missing")
        self.assertTrue(R.denial_records({"permission_denials": [
            {"tool_input": {"command": "./check --full"}}]}, {})[0]["runs_check"])
        self.assertEqual(R.denial_records({}, {}), [])

    def test_report_lists_denials_per_command(self):
        a = _result("rocket", True, True, True, atech=False)
        a["permission_denials"] = 1
        a["denials"] = [{"tool": "Bash", "command": "sed -i 's/a|b/c/' model.py && ./check",
                         "runs_check": True}]
        b = _result("mug", True, True, True, atech=False)
        md = R.report([a, b], 1, {"date": "d"}, "t")
        self.assertIn("## Permission denials by command", md)
        self.assertIn("| rocket | Bash | `sed -i 's/a\\|b/c/' model.py && ./check` | yes |", md)
        self.assertIn("| permission denials (total) | 1 |", md)
        old = _result("old", True, True, True, atech=False)
        old["permission_denials"] = 2
        md = R.report([old], 1, {"date": "d"}, "t")
        self.assertIn("2 denial(s); the run predates S46", md)


class PreviewReport(unittest.TestCase):
    def test_old_run_says_not_measured(self):
        md = R.report([_result("a", True, True, True, atech=False)], 1, {"date": "d"}, "t")
        self.assertIn("| live preview (S46) | not measured (run predates S46) |", md)

    def test_preview_times_reported(self):
        rs = []
        for pid, done, prod in (("a", 20.0, 12.5), ("b", 30.0, 16.5), ("c", None, None)):
            r = _result(pid, True, True, True, atech=False)
            r["previews"] = [{"ok": done is not None, "failures": "", "done_s": done,
                              "prod_s": prod}]
            r["preview_skipped"] = 1
            r["first_preview_s"], r["first_preview_prod_s"] = done, prod
            rs.append(r)
        md = R.report(rs, 1, {"date": "d"}, "t")
        self.assertIn("freecadcmd child, lock wait) | 25 s (n=2 of 3) |", md)
        self.assertIn("build.apply) | 14 s (n=2 of 3) |", md)
        self.assertIn("| 3 / 1 / 3 |", md)
        self.assertIn("| 20 (12) |", md)
        self.assertIn("| none (1 built) |", md)


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class PreviewBuildMode(unittest.TestCase):
    def test_preview_job_is_apply_and_failures_only(self):
        ws = tempfile.mkdtemp(prefix="eval-harness-fc-")
        try:
            with open(os.path.join(ws, "model.py"), "w", encoding="utf-8") as fh:
                fh.write(BOX_ON_DESK)
            b, crash = R.fc_job({"mode": "build", "workspace": ws, "expect": {},
                                 "prompt": "a block on a desk", "seed": None,
                                 "render": None, "preview": True})
        finally:
            shutil.rmtree(ws, ignore_errors=True)
        self.assertIsNotNone(b, crash)
        self.assertTrue(b["ok"], b.get("error"))
        self.assertEqual(b["failures"], "")
        self.assertIsInstance(b["build_seconds"], float)
        for k in ("checks", "fitness", "render"):
            self.assertNotIn(k, b, "a preview build ran %s" % k)


class PromptSets(unittest.TestCase):
    def _ids(self, fname):
        with open(os.path.join(EVAL, fname), encoding="utf-8") as fh:
            return [p["id"] for p in json.load(fh)["prompts"]], fh.name

    def test_core_set_is_still_the_baseline_12(self):
        ids, _ = self._ids(R.PROMPT_SETS["core"])
        self.assertEqual(ids, BASELINE_12)

    def test_extra_set_is_separate_and_seeds_exist(self):
        extra, _ = self._ids(R.PROMPT_SETS["extra"])
        self.assertIn("stand_for_existing_part", extra)
        self.assertIn("atech_clock_enclosure", extra)
        self.assertFalse(set(extra) & set(BASELINE_12))
        items = R.load_expectations()
        for pid in extra:
            seed = R._seed_path(items[pid])
            if seed:
                self.assertTrue(os.path.isfile(seed), seed)

    def test_atech_prompts_are_machine_checked(self):
        """S35: doorbell remote, upright weather station, alarm clock."""
        items = R.load_expectations()
        want = {"atech_doorbell_remote": ["button", "speaker"],
                "atech_weather_station": ["temp_humidity", "screen"],
                "atech_alarm_clock": ["screen", "button", "speaker"]}
        extra, _ = self._ids(R.PROMPT_SETS["extra"])
        for pid, mods in want.items():
            with self.subTest(pid):
                self.assertIn(pid, extra)
                e = items[pid]["expect"]
                self.assertTrue(R.is_atech_item(items[pid]))
                self.assertEqual(e["atech_modules"], mods)
        self.assertTrue(items["atech_weather_station"]["expect"]["board_upright"])
        self.assertIn("upright", items["atech_weather_station"]["prompt"])
        self.assertEqual(items["atech_doorbell_remote"]["expect"]["modules_inside"], ["speaker"])
        # the core 12 stay plain, so the comparable score is not diluted
        core, _ = self._ids(R.PROMPT_SETS["core"])
        self.assertFalse(any(R.is_atech_item(items[p]) for p in core))

    def test_r173_shift4_prompts_are_machine_checked(self):
        """The four shift-4 failures (D64-D67), each with the key that
        measures it, and a size-changing edit turn (D57)."""
        items = R.load_expectations()
        extra, _ = self._ids(R.PROMPT_SETS["extra"])
        for pid in ("enclosure_80x50x30", "atech_nightlight_closed",
                    "cable_clip_push_in", "self_watering_planter"):
            self.assertIn(pid, extra)
        e = items["enclosure_80x50x30"]["expect"]
        self.assertEqual(e["overall_z"], [29.5, 30.5])
        self.assertIn("80 x 50 x 30 mm outside", items["enclosure_80x50x30"]["prompt"])
        edit = items["enclosure_80x50x30"]["edit"]
        self.assertEqual(edit["expect"]["overall_z"], [39.5, 40.5])
        self.assertIn("40 mm", edit["prompt"])
        n = items["atech_nightlight_closed"]["expect"]
        self.assertTrue(R.is_atech_item(items["atech_nightlight_closed"]))
        self.assertTrue(n["closed_around_board"])
        self.assertIn({"module": "usbc", "toward": "socket", "min_open_pct": 80},
                      n["open_along"])
        self.assertEqual(items["cable_clip_push_in"]["expect"]["channels_open"],
                         {"count": 3, "d": [5.5, 7.0]})
        self.assertIn("open_from_above", items["self_watering_planter"]["expect"])

    def test_round9_dogfood_regressions_are_machine_checked(self):
        """R191/R192: the S6-3 toothbrush holder and the S6-2 phone tripod
        mount, prompts verbatim from the dogfood driver, each with the key
        that measures its defect; the core set is not touched."""
        items = R.load_expectations()
        extra, _ = self._ids(R.PROMPT_SETS["extra"])
        core, _ = self._ids(R.PROMPT_SETS["core"])
        for pid in ("toothbrush_holder_slots", "phone_tripod_mount"):
            self.assertIn(pid, extra)
            self.assertNotIn(pid, core)
            self.assertFalse(R.is_atech_item(items[pid]))
        tb = items["toothbrush_holder_slots"]
        self.assertIn("80 x 30 x 20 mm with four 14 mm wide slots cut 15 mm deep from the "
                      "front edge", tb["prompt"])
        e = tb["expect"]
        lo, hi = e["volume_mm3"]
        self.assertTrue(lo <= 80 * 30 * 20 - 4 * 14 * 15 * 20 <= hi)   # 31200
        self.assertEqual(e["notches_open"], {"count": 4, "w": [13.5, 14.5], "min_depth": 14.5,
                                             "through": True, "exact": True})
        self.assertTrue(e["no_failed_verdict"])
        ph = items["phone_tripod_mount"]
        self.assertIn("9 mm thick and 75 mm wide, 30 mm deep, with 2 mm lips", ph["prompt"])
        self.assertEqual(ph["expect"]["insertion_path"],
                         {"section_mm": [75, 9], "min_depth_mm": 20, "min_mouth_mm": 9})

    def test_round10_hinged_box_is_machine_checked(self):
        """R202 / D77: the S6-5 c5n prompt verbatim, with the hinge sweep;
        the core set is not touched."""
        items = R.load_expectations()
        extra, _ = self._ids(R.PROMPT_SETS["extra"])
        core, _ = self._ids(R.PROMPT_SETS["core"])
        self.assertIn("hinged_box_lid", extra)
        self.assertNotIn("hinged_box_lid", core)
        hb = items["hinged_box_lid"]
        self.assertFalse(R.is_atech_item(hb))
        self.assertEqual(hb["prompt"], HINGE_PROMPT)
        self.assertEqual(hb["expect"]["hinge_opens"],
                         {"bore_d": [1.8, 2.6], "range_deg": [0, 90]})
        self.assertGreaterEqual(hb["expect"]["min_objects"], 2)

    def test_round11_pegboard_hook_and_desk_clock_are_machine_checked(self):
        """R213 / D79 and R212 / D78: the S7 c2n3 and c1n4 prompts verbatim,
        each with the key that measures its defect; the core set is not
        touched."""
        items = R.load_expectations()
        extra, _ = self._ids(R.PROMPT_SETS["extra"])
        core, _ = self._ids(R.PROMPT_SETS["core"])
        for pid in ("pegboard_hook", "atech_desk_clock_leaning"):
            self.assertIn(pid, extra)
            self.assertNotIn(pid, core)
        hook = items["pegboard_hook"]
        self.assertFalse(R.is_atech_item(hook))
        self.assertEqual(hook["prompt"], PEGBOARD_PROMPT)
        self.assertEqual(hook["expect"]["mates"],
                         {"board": "pegboard", "thick_mm": 5.0, "hole_d": 6.35, "pitch": 25.4,
                          "peg_d": [4.0, 6.35], "min_pegs": 1})
        clock = items["atech_desk_clock_leaning"]
        self.assertTrue(R.is_atech_item(clock))
        self.assertEqual(clock["prompt"], DESK_CLOCK_PROMPT)
        self.assertEqual(clock["expect"]["atech_modules"], ["screen", "speaker", "button"])
        self.assertEqual(clock["expect"]["parts_engage"], {"min_parts": 0, "slide_mm": 1.0})


# dogfood S7 c2n3 and c1n4, the driver's prompt file word for word
PEGBOARD_PROMPT = ("A pegboard hook for standard 1/4-inch pegboard (6.35 mm holes on 25.4 mm "
                   "centres, 5 mm thick board): two pegs that go through two vertically adjacent "
                   "holes, the top one curling down behind the board, and a 60 mm straight arm "
                   "sticking out from the front, angled 15 degrees up.")
DESK_CLOCK_PROMPT = ("Build a desk clock on the Atech board: a screen module, a speaker module for "
                     "the alarm and a button module to snooze, in a stand-up case that leans the "
                     "screen back about 15 degrees, with openings over the screen and the button "
                     "and a grille over the speaker.")
# dogfood S6-5 c5n, the driver's prompt file word for word
HINGE_PROMPT = ("A small box with a hinged lid: box 60 x 40 x 25 mm outside with 2 mm walls, "
                "and a separate 2 mm lid joined to it by a pin hinge along the back edge - three "
                "knuckles, alternating between box and lid, with a 2 mm hole through all of them "
                "for a 1.75 mm filament pin, and 0.3 mm clearance between the knuckles.")


# ------------------------------------------------------ R173 edit turn (pure)
class _FakeLive(object):
    def __init__(self, ws, job, t_ref, turn=1, **kw):
        self.skipped, self.stop_wait_s, self.job = 0, 0.0, job

    def start(self):
        return self

    def stop(self):
        return []


class EditTurn(unittest.TestCase):
    """R173: an item's "edit" is a second user request on the same
    session, sent once the first request built; it has its own fix loop
    and is scored on its own expectations. Pure: claude, freecadcmd and
    the production argv are fakes."""

    FIRST = {"overall_z": [29.5, 30.5]}
    SECOND = {"overall_z": [39.5, 40.5]}

    def setUp(self):
        self.out = tempfile.mkdtemp(prefix="eval-edit-")
        self.ws = tempfile.mkdtemp(prefix="eval-edit-ws-")
        self.saved = (R.production_argv, R.claude_turn, R.fc_job, R.LivePreview)
        self.messages, self.jobs = [], []
        ws = self.ws

        def argv(root, seed=None, request=None):
            return {"workspace": ws, "first": ["claude", R.MSG_PH],
                    "resume": ["claude", "--resume", R.SID_PH, R.MSG_PH],
                    "document_brief": "BRIEF0", "source": "fake", "private_dirs": []}
        R.production_argv = argv
        R.LivePreview = _FakeLive

    def tearDown(self):
        R.production_argv, R.claude_turn, R.fc_job, R.LivePreview = self.saved
        shutil.rmtree(self.out, ignore_errors=True)
        shutil.rmtree(self.ws, ignore_errors=True)

    def script(self, writes, builds):
        """claude writes writes[i] (None = nothing) on turn i; fc_job
        returns builds[j] (ok, failures, pass) for build j."""
        import time as _t

        def turn(argv, ws, stdin_text=None):
            i = len(self.messages)
            self.messages.append((argv[-1], "--resume" in argv))
            if writes[i] is not None:
                _t.sleep(0.01)                         # a new mtime
                with open(os.path.join(ws, "model.py"), "w", encoding="utf-8") as fh:
                    fh.write(writes[i])
            return {"session": "S1", "ok": True, "wall_s": 1.0, "cost_usd": 0.1,
                    "num_turns": 1, "model": "m", "tools": [], "timed_out": False,
                    "exit": 0, "first_write_s": 0.5, "init_s": 0.1, "first_text_s": 0.2,
                    "check_calls": 0, "input_tokens": 10, "output_tokens": 5,
                    "permission_denials": 0, "denials": [], "usage": {}, "texts": [],
                    "final": "done", "log": [], "stderr_tail": ""}

        def job(j):
            k = len(self.jobs)
            self.jobs.append(dict(j))
            ok, failures, passed = builds[k]
            return ({"ok": ok, "failures": failures, "error": "" if ok else "boom",
                     "document_brief": "BRIEF%d" % (k + 1),
                     "whole_dims_sorted_mm": [80, 50, 30 + 10 * (k > 0)],
                     "checks": [{"check": "overall_z", "pass": passed, "detail": 1}],
                     "fitness": [{"check": "no_overlap", "pass": True, "detail": {}}]}, "")
        R.claude_turn, R.fc_job = turn, job

    def run_item(self):
        item = {"id": "enc", "prompt": "enclosure 30 tall",
                "expect": self.FIRST,
                "edit": {"prompt": "make it 40 tall", "expect": self.SECOND}}
        return R.run_prompt(item, self.out, render=False)

    def test_edit_is_sent_after_the_request_builds_and_scored_on_its_own(self):
        self.script(["A = 30\n", "A = 40\n"], [(True, "", True), (True, "", True)])
        r = self.run_item()
        self.assertEqual(len(self.messages), 2)
        first, second = self.messages
        self.assertFalse(first[1])
        self.assertTrue(second[1], "the edit goes on the same session (--resume)")
        self.assertTrue(second[0].startswith("make it 40 tall\n\n---\nBRIEF1"),
                        "the edit carries the brief of the build it edits")
        self.assertEqual([j["expect"] for j in self.jobs], [self.FIRST, self.SECOND])
        self.assertEqual(r["outcome"], "edit_built")
        self.assertTrue(r["built"] and r["pass"])
        self.assertTrue(r["first_request"]["built"] and r["first_request"]["pass"])
        self.assertEqual(r["edit_prompt"], "make it 40 tall")
        d = os.path.join(self.out, "enc")
        with open(os.path.join(d, R.REQUEST1_FILE), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "A = 30\n")
        with open(os.path.join(d, "model.py"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "A = 40\n")
        self.assertTrue(os.path.isfile(os.path.join(d, "edit_attempt1.py")))
        md = R.report([r], 1, {"date": "d"}, "t")
        self.assertIn("## Edit turns (R173)", md)
        self.assertIn("| enc | make it 40 tall | yes | 1/1 | PASS | edit_built | PASS | 1/1 |", md)

    def test_edit_gets_its_own_fix_loop(self):
        self.script(["A = 30\n", "A = 41\n", "A = 40\n"],
                    [(True, "", True), (False, "", False), (True, "", True)])
        r = self.run_item()
        self.assertEqual(len(self.messages), 3)
        self.assertTrue(self.messages[2][0].startswith(
            "The script failed when Atech Atelier ran it:\nboom\nFix model.py"))
        self.assertEqual(r["outcome"], "edit_built")
        self.assertEqual(r["fix_rounds"], 1)
        self.assertEqual([j["expect"] for j in self.jobs],
                         [self.FIRST, self.SECOND, self.SECOND])

    def test_an_edit_that_misses_the_size_fails_the_prompt(self):
        self.script(["A = 30\n", "A = 30.5\n"], [(True, "", True), (True, "", False)])
        r = self.run_item()
        self.assertTrue(r["first_request"]["pass"])
        self.assertTrue(r["built"])
        self.assertFalse(r["pass"], "the final score is the edit's")

    def test_edit_not_rewritten_is_its_own_outcome(self):
        self.script(["A = 30\n", None], [(True, "", True)])
        r = self.run_item()
        self.assertEqual(r["outcome"], "edit_not_rewritten")
        self.assertFalse(r["built"])

    def test_no_edit_when_the_request_never_builds(self):
        self.script(["A\n", "B\n", "C\n"], [(False, "", False)] * 3)
        r = self.run_item()
        self.assertEqual(len(self.messages), 3)            # 1 + MAX_FIX_ATTEMPTS
        self.assertEqual(r["outcome"], "still_fails_after_2_fixes")
        self.assertFalse(r["first_request"]["built"])
        self.assertTrue(all(j["expect"] == self.FIRST for j in self.jobs))
        self.assertIn("not sent (the request did not build)",
                      R.report([r], 1, {"date": "d"}, "t"))

    def rescore_run(self, files):
        run = tempfile.mkdtemp(prefix="eval-edit-rescore-")
        self.addCleanup(shutil.rmtree, run, True)
        d = os.path.join(run, "enc")
        os.makedirs(d)
        for f in files:
            with open(os.path.join(d, f), "w", encoding="utf-8") as fh:
                fh.write("# %s\n" % f)
        seen = {}

        def build(job):
            with open(os.path.join(job["workspace"], "model.py"), encoding="utf-8") as fh:
                seen[fh.read().strip()[2:]] = job["expect"]
            return ({"ok": True, "failures": "", "checks": [
                {"check": "z", "pass": True, "detail": 1}], "fitness": []}, "")
        items = {"enc": {"id": "enc", "prompt": "p", "expect": self.FIRST,
                         "edit": {"prompt": "e", "expect": self.SECOND}}}
        r = {"id": "enc", "prompt": "p", "built": True, "builds": [{}], "final_build": {}}
        R.rescore_result(r, run, items, build)
        return r, seen

    def test_rescore_scores_final_on_the_edit_and_request1_on_the_item(self):
        r, seen = self.rescore_run(("model_attempt1.py", R.REQUEST1_FILE,
                                    "edit_attempt1.py", "model.py"))
        self.assertEqual(seen, {"model_attempt1.py": self.FIRST,
                                R.REQUEST1_FILE: self.FIRST, "model.py": self.SECOND})
        self.assertTrue(r["first_request"]["pass"])
        self.assertTrue(r["built"] and r["pass"])

    def test_rescore_of_an_edit_never_written_is_not_built(self):
        # review: the edit turn wrote nothing (edit_not_rewritten), so
        # model.py is still the request's file; rescore must not score it
        # as the edit and call the prompt built
        r, seen = self.rescore_run(("model_attempt1.py", R.REQUEST1_FILE, "model.py"))
        self.assertNotIn("model.py", seen)
        self.assertTrue(r["first_request"]["pass"])
        self.assertFalse(r["built"])
        self.assertFalse(r["pass"])


# ------------------------------------------------------------ freecadcmd
def build_job(code, expect=None, prompt="", seed=None):
    ws = tempfile.mkdtemp(prefix="eval-harness-fc-")
    try:
        with open(os.path.join(ws, "model.py"), "w", encoding="utf-8") as fh:
            fh.write(code)
        b, crash = R.fc_job({"mode": "build", "workspace": ws, "expect": expect,
                             "prompt": prompt, "seed": seed, "render": None})
        if b is None:
            raise AssertionError("fc_build crashed: %s" % crash)
        return b
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def fit(b, name):
    for c in b.get("fitness") or []:
        if c["check"] == name:
            return c
    return None


GEAR = """import Part
from FreeCAD import Vector
from fcgear import involute, fcgear as fcg
b = fcg.FCWireBuilder()
involute.CreateExternalGear(b, %(m)s, %(z)d, 20.0, split=True)
w = Part.Wire([e.toShape() for e in b.wire])
g = Part.Face(w).extrude(Vector(0, 0, 6)).cut(Part.makeCylinder(4, 6))
doc.addObject("Part::Feature", "Gear").Shape = g
"""
BOX_ON_DESK = ("import Part\n"
               "doc.addObject('Part::Feature', 'Block').Shape = Part.makeBox(40, 30, 20)\n")


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class ProductionArgv(unittest.TestCase):
    def test_argv_is_productions(self):
        root = tempfile.mkdtemp(prefix="eval-harness-argv-")
        prod = None
        try:
            prod = R.production_argv(root)
            ws = prod["workspace"]
            self.assertTrue(ws.startswith(root), "workspace not made under the harness root")
            for key in ("first", "resume"):
                argv = prod[key]
                dirs = [argv[i + 1] for i, a in enumerate(argv) if a == "--add-dir"]
                self.assertEqual(dirs, [ws], "R14: exactly one --add-dir, the workspace")
                n = argv.count(R.MSG_PH) + (prod.get("stdin_" + key) or "").count(R.MSG_PH)
                self.assertEqual(n, 1, "message not delivered exactly once")
            self.assertIn(R.SID_PH, prod["resume"])
            self.assertNotIn(R.SID_PH, prod["first"])
            sp = R.system_prompt_of(prod["first"])
            self.assertIn(os.path.join(ws, "model.py"), sp)
            if "ATECH_ASSEMBLY.md" in prod["workspace_files"]:
                self.assertIn(os.path.join(ws, "ATECH_ASSEMBLY.md"), sp,
                              "system prompt points outside the workspace")
            print("\n  [S15] argv source: %s\n  [S15] flags: %s" % (
                prod["source"], " ".join(R.flags_of(prod["first"])).replace(ws, "<ws>")))
        finally:
            shutil.rmtree(root, ignore_errors=True)
            for d in (prod or {}).get("private_dirs") or []:
                shutil.rmtree(d, ignore_errors=True)

    def _argv(self, request, seed=None):
        root = tempfile.mkdtemp(prefix="eval-harness-argv-")
        self.addCleanup(shutil.rmtree, root, True)
        prod = R.production_argv(root, seed, request)
        for d in prod.get("private_dirs") or []:
            self.addCleanup(shutil.rmtree, d, True)
        return prod, R.system_prompt_of(prod["first"])

    def test_r111_request_reaches_turn_args(self):
        # Production (panel._send_claude) calls _turn_args(ws, text=, doc=):
        # a plain request gets no ATECH_ASSEMBLY.md copy, an Atech one gets
        # the copy and the full Atech section. The eval must send the same.
        plain, sp_plain = self._argv("An L bracket, 40 x 40 mm, 4 mm thick, two M4 holes.")
        atech, sp_atech = self._argv(
            "Smart desk clock on the Atech 14-port board with a screen and a "
            "button module, in a case that sits on a desk.")
        self.assertNotIn("ATECH_ASSEMBLY.md", plain["workspace_files"])
        self.assertIn("ATECH_ASSEMBLY.md", atech["workspace_files"])
        self.assertIn(os.path.join(atech["workspace"], "ATECH_ASSEMBLY.md"), sp_atech)
        self.assertNotIn(os.path.join(plain["workspace"], "ATECH_ASSEMBLY.md"), sp_plain)
        self.assertGreater(len(sp_atech), len(sp_plain))
        for prod in (plain, atech):              # still a placeholder on argv/stdin
            n = prod["first"].count(R.MSG_PH) + (prod.get("stdin_first") or "").count(R.MSG_PH)
            self.assertEqual(n, 1)
        print("\n  [R111] system prompt: plain %d chars, Atech %d chars"
              % (len(sp_plain), len(sp_atech)))

    def test_seed_is_in_the_brief(self):
        root = tempfile.mkdtemp(prefix="eval-harness-argv-")
        prod = None
        try:
            prod = R.production_argv(root, os.path.join(EVAL, "seeds", "clock_enclosure.py"))
            self.assertIn("Clock_Enclosure", prod["document_brief"])
            self.assertNotIn("already in your workspace", prod["document_brief"])
        finally:
            shutil.rmtree(root, ignore_errors=True)
            for d in (prod or {}).get("private_dirs") or []:
                shutil.rmtree(d, ignore_errors=True)


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class Fitness(unittest.TestCase):
    def test_logged_desk_stand_fails_overlap_and_desk(self):
        with open(os.path.join(EVAL, "fixtures", "desk_stand_overlap.py"), encoding="utf-8") as fh:
            b = build_job(fh.read(), prompt="clock stand that sits on a desk")
        self.assertTrue(b["ok"], b.get("error"))
        ov = fit(b, "no_overlap")
        self.assertFalse(ov["pass"])
        v = ov["detail"]["over_tol"][0]["common_mm3"]
        self.assertAlmostEqual(v, 20046.0, delta=5.0)     # the logged 20,046 mm3
        desk = fit(b, "not_below_desk")
        self.assertFalse(desk["pass"])
        self.assertAlmostEqual(desk["detail"]["lowest_z_mm"], -30.0, delta=0.5)
        # the expectation checks alone call it fine: that is the defect
        self.assertTrue(all(c["pass"] for c in b["checks"]))

    def test_clean_part_passes_and_desk_check_only_when_asked(self):
        b = build_job(BOX_ON_DESK, prompt="a block on a desk")
        self.assertTrue(fit(b, "no_overlap")["pass"])
        self.assertTrue(fit(b, "not_below_desk")["pass"])
        b = build_job(BOX_ON_DESK, prompt="a block")
        self.assertIsNone(fit(b, "not_below_desk"))

    def test_seed_objects_count_for_overlap(self):
        code = ("import Part\nfrom FreeCAD import Vector\n"
                "doc.addObject('Part::Feature', 'Stand').Shape = "
                "Part.makeBox(60, 60, 20, Vector(-30, -30, -10))\n")
        b = build_job(code, seed=os.path.join(EVAL, "seeds", "clock_enclosure.py"))
        self.assertTrue(b["ok"], b.get("error"))
        self.assertEqual(b["seed_objects"], ["Clock_Enclosure"])
        ov = fit(b, "no_overlap")
        self.assertFalse(ov["pass"])
        self.assertEqual(sorted(ov["detail"]["over_tol"][0]["pair"]),
                         ["Clock_Enclosure", "Stand"])
        # expectation checks measure the agent's objects only
        self.assertEqual([o["label"] for o in b["objects"]], ["Stand"])

    def test_allowed_overlap_is_not_reported(self):
        code = ("import Part\n"
                "doc.addObject('Part::Feature', 'A').Shape = Part.makeBox(10, 10, 10)\n"
                "doc.addObject('Part::Feature', 'B').Shape = Part.makeBox(10, 10, 10)\n")
        self.assertFalse(fit(build_job(code), "no_overlap")["pass"])
        self.assertTrue(fit(build_job(code, {"allow_overlap": [["A", "B"]]}),
                            "no_overlap")["pass"])

    def test_tooth_count(self):
        for m, z in ((1.5, 24), (1.0, 17), (2.0, 40)):
            with self.subTest(z=z):
                b = build_job(GEAR % {"m": m, "z": z}, {"gear_teeth": z})
                self.assertTrue(b["ok"], b.get("error"))
                c = fit(b, "gear_teeth==%d" % z)
                self.assertEqual(c["detail"]["counted"], z, c)
                self.assertTrue(c["pass"])
        b = build_job("import Part\ndoc.addObject('Part::Feature', 'Disc').Shape = "
                      "Part.makeCylinder(20, 6)\n", {"gear_teeth": 24})
        c = fit(b, "gear_teeth==24")
        self.assertFalse(c["pass"])
        self.assertEqual(c["detail"]["counted"], 0)


ATECH_CASE = """import atech_ports as ap
import Part
import FreeCAD as App
from FreeCAD import Vector
b = ap.board_object(doc)
if %(flat)s:
    b.Placement = App.Placement(Vector(0, 0, 0), App.Rotation(Vector(1, 0, 0), 90))
mods = [ap.seat(doc, "button", 3)]
if %(speaker)s:
    mods.append(ap.seat(doc, "speaker", ap.pair_for(doc, "speaker", 9)))
bb = App.BoundBox(ap.bbox(b))
if %(around)s:
    for m in mods:
        bb.add(ap.bbox(m))
def box(bb, g):
    return Part.makeBox(bb.XLength + 2 * g, bb.YLength + 2 * g, bb.ZLength + 2 * g,
                        Vector(bb.XMin - g, bb.YMin - g, bb.ZMin - g))
doc.addObject("Part::Feature", "Case").Shape = box(bb, 3.0).cut(box(bb, 1.0))
"""
ATECH_EXPECT = {"atech_modules": ["button", "speaker"], "board_upright": True,
                "modules_inside": ["speaker"]}


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class AtechFitness(unittest.TestCase):
    """S35: the Atech keys pass a correct product and FAIL each defect the
    dogfood logged (D20: board flat, speaker outside the case)."""

    def build(self, flat=False, speaker=True, around=True):
        b = build_job(ATECH_CASE % {"flat": flat, "speaker": speaker, "around": around},
                      ATECH_EXPECT)
        if not b["ok"] and ("LibraryMissing" in (b.get("error") or "")
                            or "modules are missing" in (b.get("error") or "")):
            self.skipTest("Atech module library not installed here")
        self.assertTrue(b["ok"], b.get("error"))
        return b

    def test_correct_product_passes(self):
        b = self.build()
        self.assertTrue(fit(b, "atech_modules button+speaker")["pass"])
        up = fit(b, "board_upright")
        self.assertTrue(up["pass"], up)
        self.assertLess(up["detail"]["tilt_from_vertical_deg"], 1.0)
        self.assertTrue(fit(b, "modules_inside speaker")["pass"])

    def test_flat_board_fails_upright(self):
        up = fit(self.build(flat=True), "board_upright")
        self.assertFalse(up["pass"])
        self.assertGreater(up["detail"]["tilt_from_vertical_deg"], 89.0)

    def test_speaker_outside_the_case_fails(self):
        c = fit(self.build(around=False), "modules_inside speaker")
        self.assertFalse(c["pass"], c)
        worst = [v for k, v in c["detail"].items() if k.startswith("speaker")]
        self.assertTrue(worst, c)
        self.assertGreater(worst[0]["worst_outside_mm"], 1.0, c)

    def test_missing_module_fails(self):
        b = self.build(speaker=False)
        c = fit(b, "atech_modules button+speaker")
        self.assertFalse(c["pass"])
        self.assertEqual(c["detail"]["missing"], ["speaker"])
        self.assertFalse(fit(b, "modules_inside speaker")["pass"])

    def test_no_board_fails_not_passes(self):
        b = build_job(BOX_ON_DESK, ATECH_EXPECT)
        self.assertFalse(fit(b, "board_upright")["pass"])
        self.assertFalse(fit(b, "atech_modules button+speaker")["pass"])


# ------------------------------------------------ R173 probes (freecadcmd)
def check(b, prefix):
    for c in b.get("checks") or []:
        if c["check"].startswith(prefix):
            return c
    return None


ENCLOSURE = """import Part
from FreeCAD import Vector
body = Part.makeBox(80, 50, 28).cut(Part.makeBox(76, 46, 28, Vector(2, 2, 2)))
doc.addObject("Part::Feature", "Body").Shape = body
doc.addObject("Part::Feature", "Lid").Shape = Part.makeBox(80, 50, %(lid)s, Vector(0, 0, 28))
"""
CLIP = """import Part
from FreeCAD import Vector
L = 40.0
blk = Part.makeBox(34, L, 12)
for x in (8.0, 17.0, 26.0):
    blk = blk.cut(Part.makeCylinder(3.0, L, Vector(x, 0, 7), Vector(0, 1, 0)))
    if %(slots)s:
        y0 = %(collar)s
        blk = blk.cut(Part.makeBox(4.5, L - 2 * y0, 6, Vector(x - 2.25, y0, 7)))
doc.addObject("Part::Feature", "Clip").Shape = blk
"""
PLANTER = """import Part
from FreeCAD import Vector
res = Part.makeCylinder(55, 90).cut(Part.makeCylinder(52, 87, Vector(0, 0, 3)))
pot = Part.makeCylinder(48, 60, Vector(0, 0, 30)).cut(
    Part.makeCylinder(45, 57, Vector(0, 0, 33)))
pot = pot.cut(Part.makeCylinder(4, 3, Vector(0, 0, 30)))          # wick hole
if %(cap)s:
    pot = pot.fuse(Part.makeCylinder(48, 4, Vector(0, 0, 86))).removeSplitter()
doc.addObject("Part::Feature", "Reservoir").Shape = res
doc.addObject("Part::Feature", "Inner_Pot").Shape = pot
"""


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class ShiftFourProbes(unittest.TestCase):
    """R173: each shift-4 failure shape FAILS its key, the right product
    passes it (the dogfood's own model.py files scored the same way:
    docs/verification/eval notes in the round log)."""

    def test_overall_z_sees_the_proud_lid(self):            # D65
        e = {"overall_z": [29.5, 30.5]}
        ok = check(build_job(ENCLOSURE % {"lid": 2}, e), "overall_z")
        self.assertTrue(ok["pass"], ok)
        self.assertEqual(ok["detail"]["overall_xyz_mm"], [80.0, 50.0, 30.0])
        bad = check(build_job(ENCLOSURE % {"lid": 4}, e), "overall_z")
        self.assertFalse(bad["pass"], bad)
        self.assertEqual(bad["detail"]["overall_xyz_mm"][2], 32.0)

    def test_push_in_channels_open_along_their_length(self):  # D67
        e = {"channels_open": {"count": 3, "d": [5.5, 7.0]}}
        ok = check(build_job(CLIP % {"slots": True, "collar": 0.0}, e), "channels_open")
        self.assertTrue(ok["pass"], ok)
        self.assertEqual(ok["detail"]["open_channels"], 3)
        collared = check(build_job(CLIP % {"slots": True, "collar": 4.0}, e), "channels_open")
        self.assertFalse(collared["pass"], collared)
        self.assertEqual(len(collared["detail"]["channels"]), 3)
        for ch in collared["detail"]["channels"]:
            self.assertTrue(ch["closed_at_t"], ch)        # the end collars
            self.assertGreater(ch["open_stations"], 0)     # the slotted middle
        bores = check(build_job(CLIP % {"slots": False, "collar": 0.0}, e), "channels_open")
        self.assertFalse(bores["pass"], bores)
        self.assertEqual(bores["detail"]["open_channels"], 0)

    def test_planter_pot_open_from_above(self):             # D66
        e = {"open_from_above": {"min_depth_frac": 0.3}}
        ok = check(build_job(PLANTER % {"cap": False}, e), "open_from_above")
        self.assertTrue(ok["pass"], ok)
        capped = check(build_job(PLANTER % {"cap": True}, e), "open_from_above")
        self.assertFalse(capped["pass"], capped)
        self.assertTrue(all(r["depth_mm"] < 1.0 for r in capped["detail"]["rays"]), capped)

    def test_missing_objects_fail_not_pass(self):
        e = {"overall_z": [29.5, 30.5], "channels_open": {"count": 1, "d": [5.5, 7.0]},
             "open_from_above": {}}
        b = build_job(BOX_ON_DESK, e)
        self.assertFalse(check(b, "overall_z")["pass"])
        self.assertFalse(check(b, "channels_open")["pass"])


TOOTHBRUSH = """import Part
from FreeCAD import Vector
b = Part.makeBox(80, 30, 20)
for i in range(%(n)d):
    b = b.cut(Part.makeBox(14, %(depth)s, %(h)s, Vector(4.8 + i * 18.8, 0, 20 - %(h)s)))
doc.addObject("Part::Feature", "Holder").Shape = b.removeSplitter()
"""
# The S6-2 cradle as the dogfood measured it: a 75 x 9 x 30 pocket walled on
# all four sides (z 8-38), the 2 mm lips at z 35-38 leaving a 5.0 mm mouth,
# a 6.5 mm tripod hole underneath.
CRADLE = """import Part
from FreeCAD import Vector
b = Part.makeBox(83, 17, 38).cut(Part.makeBox(75, 9, 30, Vector(4, 4, 8)))
if %(lips)s:
    b = b.fuse(Part.makeBox(75, 2, 3, Vector(4, 4, 35))).fuse(
        Part.makeBox(75, 2, 3, Vector(4, 11, 35)))
b = b.cut(Part.makeCylinder(3.25, 8, Vector(41.5, 8.5, 0)))
doc.addObject("Part::Feature", "Cradle").Shape = b.removeSplitter()
"""


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class RoundNineProbes(unittest.TestCase):
    """R191 / R192 regressions: the eval's own OCCT probes, measured on the
    parts (never ./check or intent.json)."""

    @classmethod
    def setUpClass(cls):
        cls.items = R.load_expectations()

    def tb(self, n=4, depth=15, h=20):
        return build_job(TOOTHBRUSH % {"n": n, "depth": depth, "h": h},
                         self.items["toothbrush_holder_slots"]["expect"])

    def test_toothbrush_holder_passes(self):              # D74 geometry, vol 31200
        b = self.tb()
        self.assertTrue(b["ok"], b.get("error"))
        self.assertEqual(check(b, "volume_mm3")["detail"]["volume_mm3"], 31200.0)
        n = check(b, "notches_open")
        self.assertTrue(n["pass"], n)
        o = n["detail"]["objects"][0]
        self.assertEqual((o["across"], o["open_face"]), ("X", "-Y"))
        self.assertEqual([r["w_mm"] for r in o["notches"]], [14.0] * 4)
        self.assertEqual({r["depth_mm"] for r in o["notches"]}, {15.0})
        self.assertTrue(all(r["through"] for r in o["notches"]))
        self.assertTrue(all(c["pass"] for c in b["checks"]), b["checks"])

    def test_shallow_blind_or_missing_notches_fail(self):
        shallow = check(self.tb(depth=10), "notches_open")
        self.assertFalse(shallow["pass"])
        self.assertEqual({r["depth_mm"] for r in shallow["detail"]["objects"][0]["notches"]},
                         {10.0})
        blind = check(self.tb(h=15), "notches_open")       # closed 5 mm floor
        self.assertFalse(blind["pass"])
        self.assertFalse(any(r["through"] for r in blind["detail"]["objects"][0]["notches"]))
        three = self.tb(n=3)
        self.assertFalse(check(three, "notches_open")["pass"])
        self.assertFalse(check(three, "volume_mm3")["pass"])

    def test_lipped_cradle_has_no_way_in(self):           # D73
        e = self.items["phone_tripod_mount"]["expect"]
        bad = check(build_job(CRADLE % {"lips": True}, e), "insertion_path")
        self.assertFalse(bad["pass"], bad)
        self.assertEqual(bad["detail"]["mouth_mm"], 5.0)    # the dogfood's 5.0 mm
        self.assertEqual(bad["detail"]["enter"], "+Z")
        good = build_job(CRADLE % {"lips": False}, e)
        ok = check(good, "insertion_path")
        self.assertTrue(ok["pass"], ok)
        self.assertEqual(ok["detail"]["mouth_mm"], 9.0)
        self.assertTrue(check(good, "holes")["pass"])

    def test_no_failed_verdict_is_productions_failures(self):
        e = {"no_failed_verdict": True}
        clean = check(build_job(BOX_ON_DESK, e), "no_failed_verdict")
        self.assertTrue(clean["pass"], clean)
        overlap = ("import Part\nfrom FreeCAD import Vector\n"
                   "doc.addObject('Part::Feature', 'A').Shape = Part.makeBox(10, 10, 10)\n"
                   "doc.addObject('Part::Feature', 'B').Shape = "
                   "Part.makeBox(10, 10, 10, Vector(5, 0, 0))\n")
        bad = check(build_job(overlap, e), "no_failed_verdict")
        self.assertFalse(bad["pass"])
        self.assertIn("overlap", bad["detail"])


# The S6-5 c5n model.py as the agent wrote it (atech_cad.cut / fuse_one as
# plain Part calls). %(py)s is the pin axis's y: W - KR = 37 is the dogfood's
# (3 mm inside the 40 mm back face); 40 puts it on the face, 41 outside.
HINGED_BOX = """import Part
from FreeCAD import Vector
L, W, H = 60.0, 40.0, 25.0
T = 2.0
LID_T = 2.0
RIM = H - LID_T
KR, KW, CL, PIN_D = 3.0, 10.0, 0.3, 2.0
PY, PZ = %(py)s, H - KR
X0 = L / 2.0 - 1.5 * KW
box = Part.makeBox(L, W, RIM)
box = box.cut(Part.makeBox(L - 2 * T, W - 2 * T, RIM - T, Vector(T, T, T)))
box = box.fuse([Part.makeCylinder(KR, KW, Vector(X0, PY, PZ), Vector(1, 0, 0)),
                Part.makeCylinder(KR, KW, Vector(X0 + 2 * KW, PY, PZ), Vector(1, 0, 0))])
box = box.removeSplitter()
box = box.cut(Part.makeBox(KW, 2 * KR, KR + LID_T, Vector(X0 + KW, PY - KR, PZ - KR)))
lid = Part.makeBox(L, W, LID_T, Vector(0, 0, RIM))
lid = lid.cut(Part.makeBox(3 * KW + 2 * CL, 2 * KR + CL, LID_T,
                           Vector(X0 - CL, PY - KR - CL, RIM)))
lid = lid.fuse([Part.makeCylinder(KR, KW - 2 * CL, Vector(X0 + KW + CL, PY, PZ), Vector(1, 0, 0)),
                Part.makeBox(KW - 2 * CL, KR + 4.0, LID_T, Vector(X0 + KW + CL, PY - KR - 4.0, RIM))])
lid = lid.removeSplitter()
pin = Part.makeCylinder(PIN_D / 2.0, 3 * KW + 2 * T, Vector(X0 - T, PY, PZ), Vector(1, 0, 0))
doc.addObject("Part::Feature", "Box").Shape = box.cut(pin)
doc.addObject("Part::Feature", "Lid").Shape = lid.cut(pin)
if %(pin)s:
    doc.addObject("Part::Feature", "Pin").Shape = Part.makeCylinder(
        0.875, 3 * KW, Vector(X0, PY, PZ), Vector(1, 0, 0))
"""


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class HingeProbe(unittest.TestCase):
    """R202 / D77: the hinged-box prompt's sweep, measured on the parts."""

    @classmethod
    def setUpClass(cls):
        cls.e = R.load_expectations()["hinged_box_lid"]["expect"]

    def hinge(self, py, pin=False, expect=None):
        b = build_job(HINGED_BOX % {"py": py, "pin": pin}, expect or self.e, HINGE_PROMPT)
        self.assertTrue(b["ok"], b.get("error"))
        return b, check(b, "hinge_opens")

    def test_s6_5_hinge_is_blocked_from_5_deg(self):
        b, c = self.hinge(37.0)
        self.assertFalse(c["pass"], c)
        d = c["detail"]
        self.assertEqual(d["axis"]["point"][1:], [37.0, 22.0])        # measured, not declared
        self.assertEqual(d["axis"]["dir"], [1.0, 0.0, 0.0])
        self.assertEqual((d["fixed"], d["moving"]), ("Box", ["Lid"]))
        self.assertEqual(d["first_blocked_deg"], 5.0)
        self.assertEqual(d["sweep"][0][:2], [0.0, 0.0])               # closed lid is clear
        at = {r[0]: r[1] for r in d["sweep"]}
        self.assertAlmostEqual(at[5.0], 10.2, delta=0.1)              # the dogfood's numbers
        self.assertAlmostEqual(at[90.0], 235.2, delta=0.5)
        # every static check passes: only the sweep sees it
        self.assertTrue(all(x["pass"] for x in b["checks"] if x is not c), b["checks"])
        self.assertTrue(fit(b, "no_overlap")["pass"])

    def test_axis_on_or_outside_the_back_face_opens(self):
        for py in (40.0, 41.0):
            with self.subTest(py=py):
                _b, c = self.hinge(py)
                self.assertTrue(c["pass"], c)
                self.assertEqual(c["detail"]["axis"]["point"][1], py)
                self.assertIsNone(c["detail"]["first_blocked_deg"])
                self.assertEqual(len(c["detail"]["sweep"]), 19)       # 0..90 in 5 deg
                self.assertEqual(c["detail"]["max_common_mm3"], 0.0)

    def test_a_modelled_pin_stays_an_obstacle_not_the_leaf(self):
        _b, c = self.hinge(40.0, pin=True)
        self.assertTrue(c["pass"], c)
        self.assertEqual(c["detail"]["moving"], ["Lid"])
        _b, c = self.hinge(37.0, pin=True)
        self.assertFalse(c["pass"])

    def test_the_sweep_is_what_fails_it(self):
        """Sabotage: a 0..0 range (no motion) passes the S6-5 hinge, so the
        failure above comes from the sweep, not from the closed lid."""
        e = dict(self.e, hinge_opens={"bore_d": [1.8, 2.6], "range_deg": [0, 0]})
        _b, c = self.hinge(37.0, expect=e)
        self.assertTrue(c["pass"], c)

    def test_no_shared_bore_fails_not_passes(self):
        c = check(build_job(BOX_ON_DESK, self.e), "hinge_opens")
        self.assertFalse(c["pass"])
        self.assertIn("no pin axis", c["detail"]["error"])


# The S7 c2n3 hook as the tester measured it: Ø6.0 pegs 25.4 apart standing
# out of a backplate whose back face is the board's front (y 0, board to
# y 5), the top peg curling down behind the board (tail axis at y 10), and an
# 8 x 8 arm. %(root)s is how far the arm's root runs past the backplate into
# the board: 4.9 is the dogfood's, 0 starts the arm at the board face. The
# root sits beside the lower hole (z 14..22), so the overlap is the closed
# form 8 x 8 x root. %(y1)s is where the curl starts (5 = the board's back).
PEGBOARD_HOOK = """import Part
from FreeCAD import Vector
R, PIT = 3.0, %(pitch)s
Z1 = 10.0
Z2 = Z1 + PIT
RB = 5.0
plate = Part.makeBox(20, 4, Z2 + 10, Vector(-10, -4, 0))
low = Part.makeCylinder(R, 8, Vector(0, 0, Z1), Vector(0, 1, 0))
top = Part.makeCylinder(R, %(y1)s, Vector(0, 0, Z2), Vector(0, 1, 0))
disk = Part.Face(Part.Wire(Part.makeCircle(R, Vector(0, %(y1)s, Z2), Vector(0, 1, 0))))
bend = disk.revolve(Vector(0, %(y1)s, Z2 - RB), Vector(-1, 0, 0), 90)
tail = Part.makeCylinder(R, 10, Vector(0, %(y1)s + RB, Z2 - RB), Vector(0, 0, -1))
root = Part.makeBox(8, 4 + %(root)s, 8, Vector(-4, -4, Z1 + 4.0))
arm = Part.makeBox(8, 60, 8, Vector(-4, -64, Z1 + 4.0))
arm.rotate(Vector(0, -4, Z1 + 8.0), Vector(1, 0, 0), -15)
hook = plate.fuse([low, top, bend, tail, root, arm]).removeSplitter()
if %(fillet)s:    # a fillet round each peg's root, on the board-facing face
    hook = hook.makeFillet(%(fillet)s, [ed for ed in hook.Edges
                                        if isinstance(ed.Curve, Part.Circle)
                                        and abs(ed.Curve.Radius - R) < 1e-6
                                        and abs(ed.Curve.Center.y) < 1e-6])
if %(flat)s:      # lying on its back as printed: pegs up, turned 30 deg
    hook.rotate(Vector(0, 0, 0), Vector(1, 0, 0), -90)
    hook.rotate(Vector(0, 0, 0), Vector(0, 0, 1), 30)
doc.addObject("Part::Feature", "Hook").Shape = hook
"""


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class MatesProbe(unittest.TestCase):
    """R213 / D79: the pegboard the prompt fully specifies is modelled where
    the measured pegs put it; measured on the parts, never ./check or
    intent.json (P2)."""

    @classmethod
    def setUpClass(cls):
        cls.e = R.load_expectations()["pegboard_hook"]["expect"]

    def hook(self, root=4.9, pitch=25.4, y1=5.0, flat=False, expect=None, fillet=0):
        b = build_job(PEGBOARD_HOOK % {"root": root, "pitch": pitch, "y1": y1, "flat": flat,
                                       "fillet": fillet},
                      expect or self.e, PEGBOARD_PROMPT)
        self.assertTrue(b["ok"], b.get("error"))
        return b, check(b, "mates")

    def test_c2n3_arm_root_in_the_board_fails_with_volume_and_place(self):
        b, c = self.hook()
        self.assertFalse(c["pass"], c)
        d = c["detail"]
        self.assertAlmostEqual(d["common_mm3"], 8 * 8 * 4.9, delta=0.05)     # 313.6
        w = d["worst"]
        self.assertEqual(w["object"], "Hook")
        self.assertEqual(w["into_board_mm"], 4.9)
        self.assertEqual(w["box_mm"], [[-4.0, 0.0, 14.0], [4.0, 4.9, 22.0]])
        self.assertEqual(d["pegs"], 2)                                      # both found
        self.assertEqual(d["board"]["normal"], [0.0, 1.0, 0.0])
        self.assertEqual(d["board"]["front_point"][1], 0.0)
        # every other check passes: only the modelled board sees it
        self.assertTrue(all(x["pass"] for x in b["checks"] if x is not c), b["checks"])

    def test_arm_starting_at_the_board_face_passes(self):
        _b, c = self.hook(root=0.0)
        self.assertTrue(c["pass"], c)
        self.assertEqual(c["detail"]["common_mm3"], 0.0)
        self.assertEqual(sorted(p["root"][2] for p in c["detail"]["peg_list"]), [10.0, 35.4])

    def test_placement_is_measured_not_world_axes(self):
        """The same hooks lying flat and turned: same verdicts, same volume."""
        _b, bad = self.hook(flat=True)
        self.assertFalse(bad["pass"])
        self.assertAlmostEqual(bad["detail"]["common_mm3"], 313.6, delta=0.05)
        self.assertAlmostEqual(bad["detail"]["worst"]["into_board_mm"], 4.9, delta=0.01)
        self.assertAlmostEqual(abs(bad["detail"]["board"]["normal"][2]), 1.0, delta=1e-4)
        _b, good = self.hook(root=0.0, flat=True)
        self.assertTrue(good["pass"], good)

    def test_sabotage_the_board_is_really_modelled(self):
        """Pegs 24 mm apart miss the 25.4 grid; a curl bent inside the 5 mm
        board hits it: both FAIL with no arm overlap at all."""
        _b, pitch = self.hook(root=0.0, pitch=24.0)
        self.assertFalse(pitch["pass"])
        self.assertGreater(pitch["detail"]["common_mm3"], 30.0)            # 34.7 measured
        self.assertEqual(pitch["detail"]["worst"]["into_board_mm"], 5.0)   # through the board
        _b, curl = self.hook(root=0.0, y1=3.0)
        self.assertFalse(curl["pass"])
        self.assertGreater(curl["detail"]["common_mm3"], 1.0)              # 2.05 measured

    def test_filleted_peg_roots_still_place_the_board(self):
        """A 0.8 mm fillet round each peg's root leaves the cylinder short of
        the backplate; the board sits where the fillet meets the 6.35 hole's
        edge: lift = 0.8 - sqrt(0.8^2 - (3.8 - 3.175)^2) = 0.3006 (closed
        form). The good hook passes; the c2n3 root FAILS by 8 x 8 x (4.9 -
        lift) = 294.36 mm3."""
        lift = 0.8 - math.sqrt(0.8 ** 2 - (3.8 - 3.175) ** 2)
        _b, good = self.hook(root=0.0, fillet=0.8)
        self.assertTrue(good["pass"], good)
        self.assertEqual(good["detail"]["pegs"], 2)
        for p in good["detail"]["peg_list"]:
            self.assertAlmostEqual(p["lift_mm"], lift, delta=0.002)
        _b, bad = self.hook(fillet=0.8)
        self.assertFalse(bad["pass"])
        self.assertAlmostEqual(bad["detail"]["common_mm3"], 64 * (4.9 - lift), delta=0.2)

    def test_too_few_pegs_or_none_fail(self):
        e = dict(self.e, mates=dict(self.e["mates"], min_pegs=3))
        _b, c = self.hook(root=0.0, expect=e)
        self.assertFalse(c["pass"])
        self.assertEqual((c["detail"]["pegs"], c["detail"]["common_mm3"]), (2, 0.0))
        c = check(build_job(BOX_ON_DESK, self.e), "mates")
        self.assertFalse(c["pass"])
        self.assertIn("no peg", c["detail"]["error"])


class _Vec(object):
    """Just enough of FreeCAD.Vector for fc_build.in_open_hemisphere."""

    def __init__(self, x=0.0, y=0.0, z=0.0):
        if isinstance(x, _Vec):
            x, y, z = x.x, x.y, x.z
        self.x, self.y, self.z = float(x), float(y), float(z)

    def __add__(self, o):
        return _Vec(self.x + o.x, self.y + o.y, self.z + o.z)

    def dot(self, o):
        return self.x * o.x + self.y * o.y + self.z * o.z

    @property
    def Length(self):
        return math.sqrt(self.dot(self))

    def normalize(self):
        n = self.Length
        self.x, self.y, self.z = self.x / n, self.y / n, self.z / n
        return self


def _fc_build_function(name):
    """fc_build.py runs main() on import (it is a freecadcmd script), so one
    of its pure-math functions is lifted out by its AST, with the module's
    constants, and run here against a stand-in Vector."""
    import ast
    with open(os.path.join(EVAL, "fc_build.py"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    keep = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name == name) or
            (isinstance(n, ast.Assign) and all(isinstance(t, ast.Name) and t.id.isupper()
                                                for t in n.targets)
             and isinstance(n.value, ast.Constant))]
    ns = {"App": type("App", (), {"Vector": _Vec}), "math": math}
    exec(compile(ast.Module(body=keep, type_ignores=[]), "fc_build.py", "exec"), ns)
    return ns[name]


class HemisphereMath(unittest.TestCase):
    """R212: parts_engage's verdict rests on in_open_hemisphere. Every subset
    of a set of the 26 slide directions that lies in an open hemisphere lies
    in it too, so the function must find an m for each (a renormalising
    perceptron missed ~15 % of them, calling a face touch 'engaged')."""

    def test_every_subset_of_a_hemisphere_set_is_found(self):
        import random
        f = _fc_build_function("in_open_hemisphere")
        raw = [(i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1) for k in (-1, 0, 1)
               if i or j or k]
        dirs = [_Vec(*r).normalize() for r in raw]
        rnd = random.Random(7)
        misses = n = 0
        for _ in range(3000):
            m = _Vec(rnd.gauss(0, 1), rnd.gauss(0, 1), rnd.gauss(0, 1)).normalize()
            sub = [d for d in dirs if d.dot(m) > 1e-3 and rnd.random() < 0.5]
            if not sub:
                continue
            n += 1
            got = f(sub)
            if got is None:
                misses += 1
            else:
                self.assertTrue(all(d.dot(got) > 0 for d in sub))
        self.assertGreater(n, 2500)
        self.assertEqual(misses, 0)

    def test_sets_that_surround_are_not_in_a_hemisphere(self):
        f = _fc_build_function("in_open_hemisphere")
        x, y, z = _Vec(1, 0, 0), _Vec(0, 1, 0), _Vec(0, 0, 1)
        self.assertIsNone(f([]))
        self.assertIsNone(f([x, _Vec(-1, 0, 0)]))
        self.assertIsNone(f([x, y, _Vec(-1, -1, 0).normalize()]))
        self.assertIsNotNone(f([x, y, z]))
        # a cap held from -X and -Y: the slide along (-1, 1, 0) and its
        # opposite are both blocked, so no hemisphere holds them
        raw = [(i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1) for k in (-1, 0, 1)
               if (i or j or k) and (i < 0 or j < 0)]
        self.assertIsNone(f([_Vec(*r).normalize() for r in raw]))


# A case open at both X ends (60 x 40 x 30, 2 mm walls) and end caps: a cap
# is a 2 mm plate on the end face (the S7 c1n4 / c2n4 "push fit"), with an
# optional 3 mm lip inside the opening at `cl` clearance to the walls.
END_CAPS = """import Part
from FreeCAD import Vector
L, W, H, T = 60.0, 40.0, 30.0, 2.0
case = Part.makeBox(L, W, H).cut(Part.makeBox(L + 2, W - 2 * T, H - 2 * T, Vector(-1, T, T)))
doc.addObject("Part::Feature", "Case").Shape = case
def cap(x0, sign, lip, cl):
    c = Part.makeBox(T, W, H, Vector(x0 if sign > 0 else x0 - T, 0, 0))
    if lip:
        c = c.fuse(Part.makeBox(3.0, W - 2 * T - 2 * cl, H - 2 * T - 2 * cl,
                                Vector(x0 - 3.0 if sign > 0 else x0, T + cl, T + cl)))
        c = c.removeSplitter()
    return c
for name, x0, sign, lip, cl in %(caps)r:
    doc.addObject("Part::Feature", name).Shape = cap(x0, sign, lip, cl)
"""
# An open box and a flat 2 mm lid on it, joined by the kit's own snap_fit_pair
SNAP_LID = """import sys
try:
    import atech_cad as cad
except ImportError:
    sys.path.insert(0, %(kit)r)
    import atech_cad as cad
import Part
from FreeCAD import Vector
case = Part.makeBox(60, 40, 30).cut(Part.makeBox(56, 36, 28, Vector(2, 2, 2)))
lid = Part.makeBox(60, 40, 2, Vector(0, 0, 30))
if %(snap)s:
    case, lid = cad.snap_fit_pair(case, lid, count=4)
doc.addObject("Part::Feature", "Case").Shape = case
doc.addObject("Part::Feature", "Lid").Shape = lid
"""
FLAT_R = ("Cap_R", 60.0, 1, False, 0.2)
LIPPED_R = ("Cap_R", 60.0, 1, True, 0.2)


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class EngageProbe(unittest.TestCase):
    """R212 / D78: a part that only touches the rest is held from one side;
    measured by trial slides on the parts, never ./check or intent.json."""

    @classmethod
    def setUpClass(cls):
        cls.e = R.load_expectations()["atech_desk_clock_leaning"]["expect"]
        # the plain fixtures carry only the key under test (no Atech board)
        cls.pe = {"parts_engage": cls.e["parts_engage"]}

    def caps(self, caps, expect=None):
        b = build_job(END_CAPS % {"caps": list(caps)}, expect or self.pe)
        self.assertTrue(b["ok"], b.get("error"))
        return check(b, "parts_engage")

    def rows(self, c):
        return {r["object"]: r for r in c["detail"]["parts"]}

    def test_flat_touching_cap_fails_named(self):
        c = self.caps([FLAT_R])
        self.assertFalse(c["pass"], c)
        self.assertEqual(c["detail"]["only_touch"], ["Cap_R"])
        r = self.rows(c)["Cap_R"]
        self.assertEqual((r["gap_mm"], r["common_mm3"]), (0.0, 0.0))      # D78: touch only
        self.assertTrue(r["only_touches"])
        self.assertEqual(r["held_only_from"], [-1.0, 0.0, 0.0])
        self.assertEqual(r["blocked"], 9)          # only slides with a -X component
        self.assertIn("+Y", r["free"])

    def test_lipped_cap_passes(self):
        c = self.caps([LIPPED_R])
        self.assertTrue(c["pass"], c)
        r = self.rows(c)["Cap_R"]
        self.assertTrue(r["engaged"])
        self.assertEqual(r["blocked"], 25)         # only +X (pulling it off) is free

    def test_one_flat_cap_of_two_is_the_one_named(self):
        c = self.caps([("Cap_L", 0.0, -1, False, 0.2), LIPPED_R])
        self.assertFalse(c["pass"])
        self.assertEqual(c["detail"]["only_touch"], ["Cap_L"])
        self.assertEqual(self.rows(c)["Cap_L"]["held_only_from"], [1.0, 0.0, 0.0])
        self.assertTrue(self.rows(c)["Cap_R"]["engaged"])

    def test_a_cap_sunk_into_the_case_is_still_only_touching(self):
        """A flat cap modelled 0.5 mm INTO the case end (132 mm3 = the 264 mm2
        wall ring x 0.5) is still held from one side: a slide is blocked only
        when it drives the cap further in, not because it overlaps at rest."""
        c = self.caps([("Cap_R", 59.5, 1, False, 0.2)])
        self.assertFalse(c["pass"], c)
        r = self.rows(c)["Cap_R"]
        self.assertAlmostEqual(r["common_mm3"], 132.0, delta=0.05)
        self.assertEqual((r["blocked"], r["held_only_from"]), (9, [-1.0, 0.0, 0.0]))

    def test_sabotage_a_loose_lip_does_not_engage(self):
        """A lip with 1.5 mm clearance never meets a wall in a 1 mm slide:
        the check reads the walls, not the lip's presence."""
        c = self.caps([("Cap_R", 60.0, 1, True, 1.5)])
        self.assertFalse(c["pass"], c)
        self.assertEqual(self.rows(c)["Cap_R"]["blocked"], 9)

    def test_kit_snap_fit_pair_lid_passes_and_without_it_fails(self):
        kit = os.path.join(ADDON, "acadagent", "agent_kit")
        e = {"parts_engage": {"min_parts": 1, "slide_mm": 1.0}}
        snap = build_job(SNAP_LID % {"kit": kit, "snap": True}, e)
        self.assertTrue(snap["ok"], snap.get("error"))
        c = check(snap, "parts_engage")
        self.assertTrue(c["pass"], c)
        self.assertEqual(self.rows(c)["Lid"]["blocked"], 26)
        flat = check(build_job(SNAP_LID % {"kit": kit, "snap": False}, e), "parts_engage")
        self.assertFalse(flat["pass"])
        self.assertEqual(flat["detail"]["only_touch"], ["Lid"])
        self.assertEqual(self.rows(flat)["Lid"]["held_only_from"], [0.0, 0.0, -1.0])

    def test_nothing_to_judge(self):
        """min_parts 0 (the desk clock): a one-part design and a cap 3 mm
        clear of the case are not judged and say so; min_parts 1 fails both."""
        apart = self.caps([("Cap_R", 63.0, 1, False, 0.2)])
        self.assertTrue(apart["pass"], apart)
        self.assertEqual((apart["detail"]["judged"], apart["detail"]["separate"]), (0, ["Cap_R"]))
        one = self.caps([])
        self.assertTrue(one["pass"], one)
        self.assertEqual(one["detail"]["judged"], 0)
        strict = {"parts_engage": {"min_parts": 1, "slide_mm": 1.0}}
        self.assertFalse(self.caps([("Cap_R", 63.0, 1, False, 0.2)], strict)["pass"])
        self.assertFalse(self.caps([], strict)["pass"])


NIGHTLIGHT = """import atech_ports as ap
import Part
import FreeCAD as App
from FreeCAD import Vector
b = ap.board_object(doc)
light = ap.seat(doc, "light", 2)
usbc = ap.seat(doc, "usbc", %(port)d)
bb = App.BoundBox(ap.bbox(b))
for m in (light, usbc):
    bb.add(ap.bbox(m))
def box(bb, g, open_z=0.0):
    return Part.makeBox(bb.XLength + 2 * g, bb.YLength + 2 * g, bb.ZLength + 2 * g + 2 * open_z,
                        Vector(bb.XMin - g, bb.YMin - g, bb.ZMin - g - open_z))
case = box(bb, 3.0).cut(box(bb, 1.0, %(open_z)s))
lb, ub = App.BoundBox(ap.bbox(light)), App.BoundBox(ap.bbox(usbc))
if %(window)s:          # a window in front of the light's face (+Y)
    case = case.cut(Part.makeBox(lb.XLength - 4, 10, lb.ZLength - 4,
                                 Vector(lb.XMin + 2, lb.YMax - 1, lb.ZMin + 2)))
if "%(slot)s" == "socket":   # through the wall the receptacle faces (the board edge)
    x = ub.XMin - 6 if ub.XMin < bb.XMin + 1 else ub.XMax - 1
    case = case.cut(Part.makeBox(7, ub.YLength, ub.ZLength, Vector(x, ub.YMin, ub.ZMin)))
elif "%(slot)s" == "cover":  # D64: over the module's cover instead
    case = case.cut(Part.makeBox(ub.XLength - 4, 10, ub.ZLength - 4,
                                 Vector(ub.XMin + 2, ub.YMax - 1, ub.ZMin + 2)))
doc.addObject("Part::Feature", "Case").Shape = case
"""
NIGHT_EXPECT = {"closed_around_board": True,
                "open_along": [{"module": "usbc", "toward": "socket", "min_open_pct": 80},
                               {"module": "light", "toward": "face", "min_open_pct": 20}]}


@unittest.skipIf(FC is None, "bundled freecadcmd not found")
class NightlightProbes(unittest.TestCase):
    """R173 / D64: the USB-C opening is judged along the receptacle's own
    axis, found in the module mesh - not along the board normal."""

    def build(self, port=1, window=True, slot="socket", open_z=0.0):
        b = build_job(NIGHTLIGHT % {"port": port, "window": window, "slot": slot,
                                    "open_z": open_z}, NIGHT_EXPECT)
        if not b["ok"] and ("LibraryMissing" in (b.get("error") or "")
                            or "modules are missing" in (b.get("error") or "")):
            self.skipTest("Atech module library not installed here")
        self.assertTrue(b["ok"], b.get("error"))
        return b

    def rows(self, b):
        c = fit(b, "open_along usbc:socket+light:face")
        return c, {r["module"]: r for r in c["detail"]}

    def test_closed_box_with_socket_slot_and_window_passes(self):
        for port, side in ((1, "-X"), (12, "+X")):          # left and right edge
            with self.subTest(port=port):
                b = self.build(port=port)
                c, rows = self.rows(b)
                self.assertTrue(c["pass"], c)
                self.assertEqual(rows["usbc"]["dir"], side)
                self.assertEqual(rows["usbc"]["open_pct"], 100.0)
                self.assertEqual(rows["light"]["dir"], "+Y")
                closed = fit(b, "closed_around_board")
                self.assertTrue(closed["pass"], closed)
                side_row = [r for r in closed["detail"] if r["dir"] == side][0]
                self.assertGreater(side_row["open"], 0, "the slot lets rays out")

    def test_slot_over_the_cover_fails_the_socket(self):   # the c2a2/c3a2/c4a2 shape
        c, rows = self.rows(self.build(slot="cover"))
        self.assertFalse(c["pass"], c)
        self.assertEqual(rows["usbc"]["dir"], "-X")
        self.assertEqual(rows["usbc"]["open"], 0)
        self.assertEqual(rows["usbc"]["blocked_by"], {"Case": rows["usbc"]["rays"]})

    def test_no_window_fails_the_light(self):
        c, rows = self.rows(self.build(window=False))
        self.assertFalse(c["pass"])
        self.assertTrue(rows["usbc"]["pass"])
        self.assertEqual(rows["light"]["open"], 0)

    def test_open_ends_fail_closed(self):
        b = self.build(open_z=20.0)
        c = fit(b, "closed_around_board")
        self.assertFalse(c["pass"], c)
        self.assertEqual(sorted(r["dir"] for r in c["detail"] if not r["closed"]),
                         ["+Z", "-Z"])
        for r in c["detail"]:
            if not r["closed"]:
                self.assertEqual(r["open"], r["rays"], r)   # the whole end is gone


if __name__ == "__main__":
    unittest.main(verbosity=2)
