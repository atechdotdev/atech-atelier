"""R452: production's design ladder keeps its best passing level.

What is pinned:
  checkpoint  a design level that ends on a clean build is saved in the
              chat workspace as .atech_level<N>_model.py (+ _intent.json),
              read-only, before the next level is sent
  rollback    a level still failing after its fix rounds, or whose CLI dies,
              restores the newest checkpoint below it (model.py and
              intent.json), rebuilds it, says so in one line, and sends the
              next level with a note naming the restored level
  stop        SABOTAGE: with no checkpoint file the panel reports in one
              line, shows its usual notice and sends nothing (the ladder
              stops cleanly); a restored build that fails stops with a
              notice; Stop / sign-in / offline never roll back; a planted
              link is never followed

Needs PySide6 (offscreen), like the other test_ws_chat_* files.

RUN
    cd addon/AcadAgent/tests && QT_QPA_PLATFORM=offscreen \
        python3 -m unittest test_levels_panel_r280 -v
"""
import os
import stat
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    import test_ws_chat_panel as twp   # noqa: E402  (HOME, Qt, FreeCAD stub)
    from acadagent import build, claude_cli, engine, panel  # noqa: E402
except ImportError as exc:              # no PySide6 here
    twp = None
    _WHY = repr(exc)

sys.path.insert(0, os.path.join(os.path.dirname(HERE), "acadagent", "agent_kit"))
import atech_levels as lv  # noqa: E402

Base = twp.Case if twp is not None else unittest.TestCase


def _w(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _r(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


@unittest.skipIf(twp is None, "PySide6 missing")
class LevelRollback(Base):

    def setUp(self):
        super().setUp()
        self.sent, self.builds = [], []
        self.patch(self.p, "_send_claude",
                   lambda text, state=None, fix=False, title=None:
                   self.sent.append((text, state, fix, title)) or True)
        self.build_ok = True
        test = self

        def start(*a, **k):
            test.builds.append(_r(os.path.join(test.st.ws, "model.py")))
            if test.build_ok:
                return build.PendingBuild(twp._ok_result())
            return build.PendingBuild(build.Result(False, "model.py",
                                                   error="RuntimeError: boom"))
        self.patch(build, "start", start)
        self.patch(build, "failures", lambda res: "")
        self.st = self.turn_state(key="uid-r452")
        self.ws = self.st.ws

    def lines(self):
        """Every transcript bubble (the stub's document switch on a build
        hides the transcript it was not keyed to)."""
        return [b.label.text() for b in self.p.findChildren(panel.Bubble)]

    def model(self, text, intent=None):
        _w(os.path.join(self.ws, "model.py"), text)
        if intent is not None:
            _w(os.path.join(self.ws, "intent.json"), intent)

    def ckpt(self, n):
        return os.path.join(self.ws, panel.LEVEL_CKPT_MODEL % n)

    def pass_level(self, n, text, intent=None):
        """LEVEL n ends on a clean build (the panel saves its checkpoint)."""
        self.model(text, intent)
        lv.write(self.ws, n, "toy_car.py")
        self.p._turn_failed = False
        self.p._reply("Level %d done." % n, None, None)

    def fail_level(self):
        """The running level is out of fix rounds."""
        self.p._attempt = self.p.MAX_FIX_ATTEMPTS
        self.p._busy = False
        self.p._reply("", None, "RuntimeError: kernel failure")

    # --------------------------------------------------------- checkpoint
    def test_a_clean_level_is_checkpointed_before_the_next(self):
        self.pass_level(2, "L2 = 2\n", '{"l": 2}')
        self.assertEqual(_r(self.ckpt(2)), "L2 = 2\n")
        self.assertEqual(_r(os.path.join(self.ws, panel.LEVEL_CKPT_INTENT % 2)), '{"l": 2}')
        self.assertFalse(os.stat(self.ckpt(2)).st_mode & stat.S_IWUSR, "read-only")
        self.assertEqual(lv.read(self.ws)["level"], 3)
        self.assertTrue(self.sent[-1][0].startswith("LEVEL 3 of"))
        # not a build input: Studio's snapshot never sees it
        self.assertNotIn(panel.LEVEL_CKPT_MODEL % 2, build.snapshot(self.ws))

    def test_no_ladder_no_checkpoint(self):
        self.model("A = 1\n")
        self.p._reply("Done.", None, None)
        self.assertFalse([f for f in os.listdir(self.ws) if f.startswith(".atech_level")])

    # ------------------------------------------------------------ rollback
    def test_failed_level_restores_the_checkpoint_and_advances(self):
        self.pass_level(2, "L2 = 2\n", '{"l": 2}')
        self.sent.clear()
        self.model("L3 = 'broken'\n", '{"l": 3}')       # level 3, failing
        self.fail_level()
        self.assertEqual(_r(os.path.join(self.ws, "model.py")), "L2 = 2\n")
        self.assertEqual(_r(os.path.join(self.ws, "intent.json")), '{"l": 2}')
        self.assertEqual(self.builds[-1], "L2 = 2\n", "the restored model is rebuilt")
        self.assertEqual(len(self.sent), 1, "the next level is sent")
        text, state, fix, title = self.sent[0]
        self.assertIs(state, self.st)
        self.assertFalse(fix)
        self.assertTrue(text.startswith(panel.rollback_note(2, 3, "still failing after %d "
                                                            "fixes" % self.p.MAX_FIX_ATTEMPTS)))
        self.assertIn("LEVEL 4 of %d" % lv.COUNT, text)
        self.assertTrue(build.is_level_turn(text))
        self.assertTrue(title.startswith("Level 4/"))
        self.assertEqual(lv.read(self.ws)["level"], 4)
        self.assertEqual(self.p._attempt, 0)
        line = [b for b in self.lines() if b.startswith("Level 3 did not pass")]
        self.assertEqual(len(line), 1, self.lines())
        self.assertIn("level 2's passing build", line[0])
        self.assertNotIn("The build still fails", self.titles())

    def test_intent_added_by_the_failed_level_goes(self):
        self.pass_level(1, "L1 = 1\n")
        self.model("L2 = 'broken'\n", '{"l": 2}')
        self.fail_level()
        self.assertFalse(os.path.exists(os.path.join(self.ws, "intent.json")))

    def test_cli_death_rolls_back(self):
        self.pass_level(2, "L2 = 2\n")
        self.sent.clear()
        self.model("L3 = 'half'\n")
        self.patch(claude_cli, "classify_failure", lambda msg: "other")
        self.patch(engine, "available", lambda name: (True, ""))
        self.p._on_claude_failed("claude exited 1: Segmentation fault")
        self.assertEqual(_r(os.path.join(self.ws, "model.py")), "L2 = 2\n")
        self.assertEqual(len(self.sent), 1)
        self.assertIn("LEVEL 4 of", self.sent[0][0])
        self.assertNotIn("The agent stopped before finishing", self.titles())

    def test_stop_and_offline_do_not_roll_back(self):
        self.pass_level(2, "L2 = 2\n")
        self.sent.clear()
        self.model("L3 = 'half'\n")
        self.patch(engine, "available", lambda name: (True, ""))
        for kind in (claude_cli.CANCELLED, claude_cli.OFFLINE):
            self.patch(claude_cli, "classify_failure", lambda msg, k=kind: k)
            self.p._on_claude_failed("x")
        self.assertEqual(_r(os.path.join(self.ws, "model.py")), "L3 = 'half'\n")
        self.assertEqual(self.sent, [])

    def test_the_last_level_failing_ends_on_the_checkpoint(self):
        self.pass_level(lv.COUNT - 1, "L8 = 8\n")
        self.sent.clear()
        self.model("L9 = 'broken'\n")
        self.fail_level()
        self.assertEqual(_r(os.path.join(self.ws, "model.py")), "L8 = 8\n")
        self.assertEqual(self.sent, [], "no level after the last")
        self.assertIsNone(lv.read(self.ws), "the ladder ended")

    def test_restored_build_that_fails_stops_with_a_notice(self):
        self.pass_level(2, "L2 = 2\n")
        self.sent.clear()
        self.model("L3 = 'broken'\n")
        self.build_ok = False
        self.fail_level()
        self.assertEqual(self.sent, [])
        self.assertIn("The design levels stopped", self.titles())

    def test_user_took_over_during_the_rebuild(self):
        self.pass_level(2, "L2 = 2\n")
        self.sent.clear()
        self.model("L3 = 'broken'\n")
        self.p._attempt = self.p.MAX_FIX_ATTEMPTS
        self.p._busy = True             # a user turn started meanwhile
        self.p._level_rollback("x")
        self.assertEqual(self.sent, [])

    def test_planted_link_is_not_followed(self):
        secret = os.path.join(self.tmp, "secret.txt")
        _w(secret, "TOKEN")
        os.symlink(secret, self.ckpt(2))
        self.assertIsNone(panel.last_level_checkpoint(self.ws, 3))
        self.assertFalse(panel.restore_level_checkpoint(self.ws, 2))
        self.pass_level(2, "L2 = 2\n")             # the link is replaced
        self.assertFalse(os.path.islink(self.ckpt(2)))
        self.assertEqual(_r(secret), "TOKEN")

    # ------------------------------------------------------------ sabotage
    def test_no_checkpoint_reports_and_stops_cleanly(self):
        """SABOTAGE: the same failed level with no checkpoint file."""
        self.pass_level(2, "L2 = 2\n")
        os.chmod(self.ckpt(2), 0o644)
        os.unlink(self.ckpt(2))                    # the checkpoint is gone
        self.sent.clear()
        n_builds = len(self.builds)
        self.model("L3 = 'broken'\n")
        self.fail_level()
        self.assertEqual(self.sent, [], "nothing is sent")
        self.assertEqual(len(self.builds), n_builds, "nothing is rebuilt")
        self.assertEqual(_r(os.path.join(self.ws, "model.py")), "L3 = 'broken'\n")
        self.assertEqual(lv.read(self.ws)["level"], 3, "the ladder does not advance")
        self.assertIn("The build still fails", self.titles())
        line = [b for b in self.lines() if b.startswith("Level 3 did not pass")]
        self.assertEqual(len(line), 1, self.lines())
        self.assertIn("no earlier passing level", line[0])


@unittest.skipIf(twp is None, "PySide6 missing")
class RestoreSabotage(unittest.TestCase):
    """SABOTAGE: with the restore disabled the rollback test fails."""

    def test_disabled_restore_fails_the_rollback_test(self):
        saved = panel.restore_level_checkpoint
        panel.restore_level_checkpoint = lambda ws, level: True
        try:
            res = unittest.TestResult()
            LevelRollback(
                "test_failed_level_restores_the_checkpoint_and_advances").run(res)
            self.assertEqual(len(res.failures), 1, res.errors)
        finally:
            panel.restore_level_checkpoint = saved


if __name__ == "__main__":
    unittest.main()
