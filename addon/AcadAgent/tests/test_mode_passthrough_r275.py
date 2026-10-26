"""R275: the agent mode reaches check.py through the sandbox.

check.py's R270 quality gates (sealed modules, thin walls, board retention)
read $ATECH_PROMPT_MODE. ./check runs under `env -i` and Studio's build
child gets a fixed env, so the mode must be passed explicitly - otherwise a
user in fast mode (settings "agent_quality" off) is judged by quality gates.

RUN: cd addon/AcadAgent/tests && python3 -m unittest test_mode_passthrough_r275
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from acadagent import sandbox  # noqa: E402


class ModePassthrough(unittest.TestCase):

    def setUp(self):
        self.saved = os.environ.get("ATECH_PROMPT_MODE")
        self.addCleanup(self._restore)

    def _restore(self):
        if self.saved is None:
            os.environ.pop("ATECH_PROMPT_MODE", None)
        else:
            os.environ["ATECH_PROMPT_MODE"] = self.saved

    def _mode(self, value):
        orig = sandbox._quality_mode
        sandbox._quality_mode = lambda: value
        self.addCleanup(setattr, sandbox, "_quality_mode", orig)

    def test_fast_mode_is_passed(self):
        self._mode(False)
        self.assertEqual(sandbox._passthrough_env()["ATECH_PROMPT_MODE"], "fast")

    def test_quality_mode_is_passed(self):
        self._mode(True)
        self.assertEqual(sandbox._passthrough_env()["ATECH_PROMPT_MODE"], "quality")

    def test_env_decides_without_settings(self):
        os.environ["ATECH_PROMPT_MODE"] = "fast"
        self.assertFalse(sandbox._quality_mode())
        os.environ["ATECH_PROMPT_MODE"] = "quality"
        self.assertTrue(sandbox._quality_mode())

    def test_wrapper_script_carries_the_mode(self):
        # sabotage: dropping the passthrough line fails this
        self._mode(False)
        text = sandbox.wrapper_script("/tmp", freecadcmd="/bin/true", mode="none")
        self.assertIn("ATECH_PROMPT_MODE=fast", text)
        self._mode(True)
        text = sandbox.wrapper_script("/tmp", freecadcmd="/bin/true", mode="none")
        self.assertIn("ATECH_PROMPT_MODE=quality", text)


if __name__ == "__main__":
    unittest.main()
