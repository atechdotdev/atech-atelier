"""R300-R306: Atech hardware tools on the Modules page (PRD "Atech hardware
tools" 1-5).

  R300  move a module to another port, or swap two modules
  R301  board-moved detector + "Re-seat all" (atech_ports.stale_modules,
        reseat_all: seated modules follow the board, cables are remade)
  R302  cables in the UI: icon, length, "Connected by cable", Remake cable
  R303  power rule: Check all warns when the board has no USB-C module
  R304  port hover info (board map tooltips, keyboard) and an Undo-add row
  R305  knob, N20 wheel, NEMA 17 placeable by hand as free parts
  R306  starter projects built with real, tagged hardware (projects.py)

Pure parts need PySide6 only (offscreen):

    QT_QPA_PLATFORM=offscreen <bundled python> -m unittest -v test_modules_page_r300

The FreeCAD parts run fc_modules_r300.py under freecadcmd (found through
ATECH_FREECADCMD or the dist build) once clean and once per sabotage, in
parallel, and skip without freecadcmd or the module library.
"""
import os
import re
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ADDON))
if ADDON not in sys.path:
    sys.path.insert(0, ADDON)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    _APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from acadagent import modules_page as mp
except ImportError:                                    # no Qt here
    mp = None


def _freecadcmd():
    env = os.environ.get("ATECH_FREECADCMD")
    if env and os.path.isfile(env):
        return env
    for arch in ("arm64", "x86_64"):
        p = os.path.join(REPO, "dist", "build-macos-%s" % arch, "Atech Atelier.app",
                         "Contents", "Resources", "bin", "freecadcmd")
        if os.path.isfile(p):
            return p
    return shutil.which("freecadcmd")


FC = _freecadcmd()
MODELS = os.environ.get("ATECH_ARTIFACTS") or os.path.join(REPO, "models")
LIB = os.path.isfile(os.path.join(REPO, "projects", "atech_ports.py")) and \
    os.path.isfile(os.path.join(MODELS, "presets.yaml"))


# ------------------------------------------------------------------ pure
@unittest.skipIf(mp is None, "PySide6 not installed")
class TestWords(unittest.TestCase):

    def test_r303_power_warning(self):
        self.assertIsNone(mp.power_warning([]))                  # nothing to power
        self.assertIsNone(mp.power_warning(["button", "usbc"]))
        w = mp.power_warning(["button", "light"])
        self.assertIn("No USB-C module", w)
        self.assertIn("port 8", w)

    def test_r304_port_tooltip(self):
        self.assertEqual(mp.port_tooltip(3, "left"),
                         "Port 3 · left edge · empty · a module slides in from the left")
        self.assertEqual(mp.port_tooltip(9, "right", "Screen", [10]),
                         "Port 9 · right edge · Screen, seated · also on port 10")
        self.assertEqual(mp.port_tooltip(11, "right", "Button", cable_mm=182.4),
                         "Port 11 · right edge · Button on a 182 mm cable")
        self.assertEqual(mp.port_tooltip(8, "bottom", reserved="USB-C"),
                         "Port 8 · bottom edge · reserved for USB-C")
        # the pin order is OPEN in the library: never named
        self.assertNotIn("pin", mp.port_tooltip(3, "left").lower())

    def test_r302_cable_words(self):
        self.assertEqual(mp.cable_words([182.4]), "Connected by cable · 182 mm")
        self.assertEqual(mp.cable_words([100, 120]), "Connected by 2 cables · 220 mm in all")
        self.assertEqual(mp.cable_words([]), "Connected by cable")

    def test_r302_cabled_verdicts_never_say_seated_or_slides(self):
        ok = {"verdict": "PASS"}
        self.assertEqual(mp.verdict_words("seated", ok, cabled=True),
                         ("Connected by cable", "ok"))
        self.assertEqual(mp.verdict_words("seated", ok), ("Fully seated", "ok"))
        self.assertEqual(mp.CABLED_ORDER, ("seated", "interference"))
        moved = {"verdict": "FAIL", "why": "the board or the module moved after its "
                 "cable was made (b_cable_p11): make the cable again", "ports": []}
        self.assertEqual(mp.fail_why("seated", moved), mp.CABLE_REMADE_WHY)
        self.assertEqual(mp.verdict_words("seated", moved, cabled=True)[0],
                         "Cable not connected")

    def test_r301_stale_sentence(self):
        self.assertIsNone(mp.stale_sentence(0, 0))
        self.assertEqual(mp.stale_sentence(1, 0), "The board has moved: 1 module is no "
                         "longer in its port. Re-seat all puts them back.")
        self.assertEqual(mp.stale_sentence(2, 2), "The board has moved: 2 modules are no "
                         "longer in their ports and 2 cables no longer reach their "
                         "modules. Re-seat all puts them back.")
        self.assertTrue(mp.stale_sentence(0, 1).startswith(
            "A cabled module or the board has moved: 1 cable no longer reaches its module"))

    def test_r300_move_action(self):
        self.assertEqual(mp.move_action([3], 5), ("move", 5))
        self.assertEqual(mp.move_action([3], 3), ("cancel", None))
        self.assertEqual(mp.move_action([3], 4, ("light_p4", [4])), ("swap", "light_p4"))
        self.assertEqual(mp.move_action([9, 10], 4, ("light_p4", [4]))[0], "refuse")
        self.assertEqual(mp.move_action([9, 10], 10), ("cancel", None))

    def test_r302_cable_icon(self):
        ic = mp.cable_icon("#6b7280")
        self.assertFalse(ic.isNull())
        img = ic.pixmap(16, 16).toImage()
        painted = sum(1 for x in range(img.width()) for y in range(img.height())
                      if img.pixelColor(x, y).alpha() > 0)
        self.assertGreater(painted, 10)


@unittest.skipIf(mp is None, "PySide6 not installed")
class TestBoardMap(unittest.TestCase):

    def _map(self):
        w = mp.BoardMap()
        w.resize(340, 420)
        ports = {n: object() for n in range(1, 15)}
        tips = {n: mp.port_tooltip(n, "left") for n in range(1, 15)}
        tips[11] = mp.port_tooltip(11, "right", "Button", cable_mm=150)
        w.set_state(ports, {3: "Light", 11: "Button"}, None,
                    {"L": ("light", (3,)), "B": ("button", (11,), "cable")},
                    tips=tips, moving=(3,))
        return w

    def test_r302_cabled_module_drawn_as_plug_not_sprite(self):
        w = self._map()
        img = w.grab().toImage()
        self.assertFalse(img.isNull())
        # same board, the button seated instead: the cell looks different
        w2 = self._map()
        w2.modules["B"] = ("button", (11,))
        img2 = w2.grab().toImage()
        r = w._cell(11).toRect()
        diff = sum(1 for x in range(r.left(), r.right(), 2)
                   for y in range(r.top(), r.bottom(), 2)
                   if img.pixelColor(x, y) != img2.pixelColor(x, y))
        self.assertGreater(diff, 20)

    def test_r304_hover_and_keyboard(self):
        w = self._map()
        self.assertEqual(w.accessibleName(), "Atech board map")
        self.assertEqual(w.tip_for(11), "Port 11 · right edge · Button on a 150 mm cable")
        self.assertEqual(w.tip_for(None), "")
        w.tips = {}
        self.assertEqual(w.tip_for(3), "Port 3 · Light")     # the short form
        w = self._map()
        got = []
        w.picked.connect(got.append)
        w.grab()
        w.keyPressEvent(QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Down,
                                        QtCore.Qt.NoModifier))
        self.assertEqual(w.hover, 1)
        self.assertIn("Port 1", w.accessibleDescription())
        w.keyPressEvent(QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Down,
                                        QtCore.Qt.NoModifier))
        w.keyPressEvent(QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Return,
                                        QtCore.Qt.NoModifier))
        self.assertEqual(got, [2])

    def test_old_two_tuple_modules_still_paint(self):
        w = mp.BoardMap()
        w.resize(340, 420)
        w.set_state({n: object() for n in range(1, 15)}, {}, 4,
                    {"S": ("screen", (1, 2))})
        self.assertFalse(w.grab().toImage().isNull())


@unittest.skipIf(mp is None, "PySide6 not installed")
class TestPageWidgets(unittest.TestCase):

    def test_new_controls_exist_hidden_and_named(self):
        page = mp.ModulesPage()
        for w, name in ((page.btn_reseat, "Re-seat all modules"),
                        (page.btn_move, "Move this module to another port"),
                        (page.btn_recable, "Remake this module's cable"),
                        (page.btn_move_cancel, "Cancel moving")):
            self.assertEqual(w.accessibleName(), name)
        self.assertEqual(page.btn_reseat.text(), "Re-seat all")
        self.assertEqual(page.btn_recable.text(), "Remake cable")
        for w in (page.stale_row, page.move_row, page.undo_row, page.free_label):
            self.assertFalse(w.isVisibleTo(page))

    def test_undo_row_says_what_it_undoes(self):
        page = mp.ModulesPage()

        class _Doc(object):
            Name = "D"
        page._offer_undo(_Doc(), "Add button", "Button", "Added Button")
        self.assertEqual(page.undo_text.text(), "Added Button  ·")
        self.assertEqual(page.btn_undo.accessibleName(), "Undo: Added Button")
        page._offer_undo(_Doc(), "Remove light_p2", "Light")
        self.assertEqual(page.undo_text.text(), "Removed Light  ·")


# --------------------------------------------------------- FreeCAD-backed
SABOTAGES = {
    # feature: the checks its sabotage must fail
    "reseat": {"reseat.banner_gone", "reseat.all_pass"},
    "power": {"power.warns"},
    "cabled": {"cable.words"},
    "undo_add": {"undo_add.row"},
    "starter": {"starter.desk-sensor-hub"},
    "move": {"move.moved"},
    "hover": {"hover.empty", "hover.cable"},
    "free": {"free.placed"},
    "by_cable": {"bycable.added"},
}
_RUNS = {}


def _launch(sabotage=""):
    env = dict(os.environ, ATECH_ARTIFACTS=MODELS, QT_QPA_PLATFORM="offscreen",
               ATECH_R300_SABOTAGE=sabotage)
    return subprocess.Popen([FC, os.path.join(HERE, "fc_modules_r300.py")], env=env,
                            cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _parse(out):
    checks = dict(re.findall(r"^CHECK (\S+) (PASS|FAIL)", out, re.M))
    m = re.search(r"^R300_TESTS=(\d+)", out, re.M)
    return checks, (int(m.group(1)) if m else None)


@unittest.skipIf(FC is None, "freecadcmd not found (set ATECH_FREECADCMD)")
@unittest.skipUnless(LIB, "the Atech module library is not in this checkout")
class TestInFreeCAD(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if _RUNS:
            return
        procs = {"": _launch("")}
        procs.update({k: _launch(k) for k in SABOTAGES})
        for k, p in procs.items():
            out, _ = p.communicate(timeout=600)
            _RUNS[k] = out.decode("utf-8", "replace")

    def _clean(self):
        checks, n = _parse(_RUNS[""])
        return checks, n

    def assert_checks(self, prefix, minimum):
        checks, _ = self._clean()
        mine = {k: v for k, v in checks.items() if k.startswith(prefix)}
        self.assertGreaterEqual(len(mine), minimum, _RUNS[""][-3000:])
        bad = [k for k, v in mine.items() if v != "PASS"]
        self.assertEqual(bad, [], _RUNS[""][-3000:])

    def test_clean_run_has_no_failures(self):
        checks, n = self._clean()
        self.assertEqual(n, 0, _RUNS[""][-3000:])
        self.assertGreater(len(checks), 40)

    def test_r300_move_and_swap(self):
        self.assert_checks("move.", 7)
        self.assert_checks("swap.", 3)

    def test_r301_reseat_all(self):
        self.assert_checks("reseat.", 5)

    def test_r302_cables(self):
        self.assert_checks("cable.", 8)

    def test_r303_power(self):
        self.assert_checks("power.", 2)

    def test_r304_hover_and_undo_add(self):
        self.assert_checks("hover.", 4)
        self.assert_checks("undo_add.", 3)

    def test_r305_free_parts(self):
        self.assert_checks("free.", 8)

    def test_by_cable_off_the_board(self):
        self.assert_checks("bycable.", 8)

    def test_r306_starters_tagged(self):
        self.assert_checks("starter.", 8)

    def test_sabotage_each_feature_is_caught(self):
        for feature, must_fail in sorted(SABOTAGES.items()):
            checks, n = _parse(_RUNS[feature])
            failed = {k for k, v in checks.items() if v == "FAIL"}
            self.assertTrue(n, "sabotage %r went unnoticed" % feature)
            self.assertTrue(must_fail <= failed,
                            "sabotage %r: expected %s to fail, failed: %s"
                            % (feature, sorted(must_fail), sorted(failed)))


if __name__ == "__main__":
    unittest.main()
