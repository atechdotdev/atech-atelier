"""R280/R281: the sidebar's "Only CAD | CAD + electronics" switch.

hw_mode stores the choice; build.board_default() follows it (CAD only =
plain CAD prompt, no board by default); the panel puts the 14-port board in
the document before an electronics-mode turn starts. Runs under system
python (no Qt, no FreeCAD needed for these).
"""
import ast
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
sys.path.insert(0, ADDON)

from acadagent import hw_mode  # noqa: E402
from acadagent import build as pbuild  # noqa: E402


class HwMode(unittest.TestCase):

    def setUp(self):
        self._env = os.environ.pop(hw_mode.ENV, None)
        self.addCleanup(self._restore)

    def _restore(self):
        os.environ.pop(hw_mode.ENV, None)
        if self._env is not None:
            os.environ[hw_mode.ENV] = self._env

    def test_default_is_electronics(self):
        self.assertEqual(hw_mode.get({}), hw_mode.ELECTRONICS)
        self.assertEqual(hw_mode.get({hw_mode.KEY: "nonsense"}), hw_mode.ELECTRONICS)
        self.assertTrue(hw_mode.electronics({}))

    def test_setting_and_env_override(self):
        self.assertEqual(hw_mode.get({hw_mode.KEY: "cad_only"}), hw_mode.CAD_ONLY)
        os.environ[hw_mode.ENV] = "electronics"
        self.assertEqual(hw_mode.get({hw_mode.KEY: "cad_only"}), hw_mode.ELECTRONICS)

    def test_switch_order_and_labels(self):
        self.assertEqual(hw_mode.MODES, ("cad_only", "electronics"))
        self.assertEqual([hw_mode.LABELS[m] for m in hw_mode.MODES],
                         ["Only CAD", "CAD + electronics"])

    def test_set_stores_through_settings_update(self):
        try:
            from acadagent import settings
        except ImportError:
            self.skipTest("settings needs PySide6 (run with the app's python)")
        d = tempfile.mkdtemp(prefix="hwmode_")
        with mock.patch.object(settings, "CONFIG_DIR", d), \
                mock.patch.object(settings, "CONFIG_PATH", os.path.join(d, "settings.json")):
            self.assertTrue(hw_mode.set("cad_only"))
            self.assertEqual(hw_mode.get(), "cad_only")
            self.assertTrue(hw_mode.set("electronics"))
            self.assertEqual(hw_mode.get(), "electronics")
        with self.assertRaises(ValueError):
            hw_mode.set("both")

    def test_board_default_follows_the_switch(self):
        with mock.patch.object(pbuild, "library_available", lambda refresh=False: True):
            os.environ[hw_mode.ENV] = "electronics"
            self.assertTrue(pbuild.board_default())
            os.environ[hw_mode.ENV] = "cad_only"
            self.assertFalse(pbuild.board_default())

    def test_cad_only_prompt_has_no_board_default(self):
        with mock.patch.object(pbuild, "library_available", lambda refresh=False: True), \
                mock.patch.object(pbuild, "_atech_note", lambda *a, **kw: "\nATECH SECTION\n"), \
                mock.patch.object(pbuild, "_atech_pointer", lambda *a, **kw: "\nATECH POINTER\n"):
            os.environ[hw_mode.ENV] = "cad_only"
            sp = pbuild.system_prompt("/nonexistent/ws", request="a car")
            self.assertNotIn("ATECH SECTION", sp)
            os.environ[hw_mode.ENV] = "electronics"
            sp = pbuild.system_prompt("/nonexistent/ws", request="a car")
            self.assertIn("ATECH SECTION", sp)


def _panel_src():
    with open(os.path.join(ADDON, "acadagent", "panel.py"), encoding="utf-8") as fh:
        return fh.read()


class PanelShowsBoardFirst(unittest.TestCase):
    """The panel side is Qt; checked from its source so CI without Qt runs it."""

    def test_user_turn_shows_the_board_before_the_agent(self):
        src = _panel_src()
        tree = ast.parse(src)
        send = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == "_send_claude")
        body = ast.get_source_segment(src, send)
        # only on a user turn (state is None), before the state and prompt
        self.assertLess(body.index("self._show_board_first(doc)"),
                        body.index("state = self._state_for(doc)"))
        self.assertLess(body.index("self._show_board_first(doc)"),
                        body.index("self._turn_args("))

    def test_show_board_first_gates(self):
        src = _panel_src()
        fn = src[src.index("def _show_board_first"):src.index("def _involves_atech")]
        for gate in ("hw_mode.electronics()", "build.library_available()",
                     "AtechRole", "openTransaction", "ap.board_object(doc)"):
            self.assertIn(gate, fn)


class TopBarSwitch(unittest.TestCase):

    def test_switch_in_the_sidebar_head_not_the_menu_bar(self):
        with open(os.path.join(ADDON, "acadagent", "shell.py"), encoding="utf-8") as fh:
            src = fh.read()
        side = src[src.index("class Sidebar"):src.index("self.stack = QtWidgets.QStackedWidget()")]
        self.assertIn("_hardware_switch()", side)
        # the macOS native menu bar draws no corner widgets: never put it there
        top = src[src.index("def _build_topbar"):src.index("def _hardware_switch")]
        self.assertNotIn("_hardware_switch()", top)
        sw = src[src.index("def _hardware_switch"):]
        self.assertIn("hw_mode.set(hw_mode.MODES[i])", sw)
        self.assertIn("hw_mode.MODES.index(hw_mode.get())", sw)


if __name__ == "__main__":
    unittest.main()
