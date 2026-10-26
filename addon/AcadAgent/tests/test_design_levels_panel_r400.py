"""R400: the panel drives the design ladder - a clean level sends the next
one (its own fix budget, its title on the turn card), a failed level sends a
fix instead, and no ladder means no extra turn.

Needs PySide6 (offscreen), like the other test_ws_chat_* files.

RUN
    cd addon/AcadAgent/tests && QT_QPA_PLATFORM=offscreen \
        python3 -m unittest test_design_levels_panel_r400 -v
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    import test_ws_chat_panel as twp   # noqa: E402  (HOME, Qt, FreeCAD stub)
    from acadagent import build, panel  # noqa: E402
except ImportError as exc:              # no PySide6 here
    twp = None
    _WHY = repr(exc)

sys.path.insert(0, os.path.join(os.path.dirname(HERE), "acadagent", "agent_kit"))
import atech_levels as lv  # noqa: E402

Base = twp.Case if twp is not None else unittest.TestCase


@unittest.skipIf(twp is None, "PySide6 missing")
class PanelLadder(Base):

    def setUp(self):
        super().setUp()
        self.sent, self.fixes = [], []
        self.patch(self.p, "_send_claude",
                   lambda text, state=None, fix=False, title=None:
                   self.sent.append((text, state, fix, title)) or True)
        self.patch(self.p, "_send_fix", self.fixes.append)

    def test_a_clean_level_sends_the_next(self):
        st = self.turn_state(key="uid-l1")
        lv.write(st.ws, 1, "toy_car.py")
        self.p._attempt = 3
        self.p._reply("Level 1 done.", None, None)
        self.assertEqual(len(self.sent), 1)
        text, state, fix, title = self.sent[0]
        self.assertTrue(text.startswith("LEVEL 2 of 9 - PACKAGE THE ATECH BOARD"))
        self.assertTrue(build.is_level_turn(text))
        self.assertIs(state, st)
        self.assertFalse(fix)
        self.assertEqual(title, "Level 2/9: Package the Atech board inside")
        self.assertEqual(self.p._attempt, 0)      # each level has its own fixes
        self.assertEqual(lv.read(st.ws)["level"], 2)

    def test_a_failed_level_is_fixed_not_advanced(self):
        st = self.turn_state(key="uid-l2")
        lv.write(st.ws, 3)
        self.p._reply("", None, "boom")
        self.assertEqual(self.fixes, ["boom"])
        self.assertEqual(self.sent, [])
        self.assertEqual(lv.read(st.ws)["level"], 3)

    def test_a_failed_turn_without_a_fix_does_not_advance(self):
        st = self.turn_state(key="uid-l3")
        lv.write(st.ws, 3)
        self.p._turn_failed = True
        self.p._reply("", None, None)
        self.assertEqual(self.sent, [])
        self.assertEqual(lv.read(st.ws)["level"], 3)

    def test_no_ladder_no_extra_turn(self):
        self.turn_state(key="uid-l4")
        self.p._reply("Done.", None, None)
        self.assertEqual(self.sent, [])

    def test_the_last_level_ends_the_ladder(self):
        st = self.turn_state(key="uid-l5")
        lv.write(st.ws, 9)
        self.p._reply("Ready for tooling.", None, None)
        self.assertEqual(self.sent, [])
        self.assertIsNone(lv.read(st.ws))


if __name__ == "__main__":
    unittest.main()
