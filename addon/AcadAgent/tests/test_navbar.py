"""The sidebar's top (navbar.py) and the Studio board (modules_page.BoardMap).

Pure parts need nothing; the widget parts need PySide6 (offscreen) and skip
without it. No FreeCAD.

    QT_QPA_PLATFORM=offscreen python -m unittest -v test_navbar
"""
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ADDON))
if ADDON not in sys.path:
    sys.path.insert(0, ADDON)

try:
    from PySide6 import QtCore, QtWidgets
    _APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from acadagent import modules_page as mp
    from acadagent import navbar
except ImportError:                                    # no Qt here
    navbar = mp = None


@unittest.skipIf(navbar is None, "PySide6 not installed")
class TestProjectEntries(unittest.TestCase):
    def test_open_recent_and_actions(self):
        docs = [("Bracket", "Bracket", "/p/Bracket.FCStd"), ("Hub", "Desk hub", "")]
        rec = ["/p/Bracket.FCStd", "/q/Lamp.FCStd"]
        out = navbar.project_entries(docs, "Hub", rec, [("motion-rig", "Motion Rig")])
        kinds = [k for k, *_ in out]
        # R456: starters passed in are ignored - no starter submenu any more
        self.assertEqual(kinds, ["header", "open", "open", "sep", "header", "recent",
                                 "sep", "new", "file"])
        opens = [(p, t, c) for k, p, t, c in out if k == "open"]
        self.assertEqual(opens, [("Bracket", "Bracket", False), ("Hub", "Desk hub", True)])
        # an open file is not listed again under Recent
        self.assertEqual([p for k, p, *_ in out if k == "recent"], ["/q/Lamp.FCStd"])

    def test_same_name_recent_files_are_told_apart(self):
        out = navbar.project_entries([], None, ["/a/hub.FCStd", "/b/hub.FCStd"], [])
        texts = [t for k, _p, t, _c in out if k == "recent"]
        self.assertEqual(texts, ["hub  (a)", "hub  (b)"])

    def test_nothing_open(self):
        out = navbar.project_entries([], None, [], [])
        self.assertEqual([k for k, *_ in out], ["sep", "new", "file"])
        self.assertEqual(navbar.current_title([], None), "No project open")


@unittest.skipIf(navbar is None, "PySide6 not installed")
class TestPillTabs(unittest.TestCase):
    def test_two_tabs_click_and_keys(self):
        w = navbar.PillTabs(["3D CAD", "Atech modules"])
        w.resize(300, w.HEIGHT)
        got = []
        w.changed.connect(got.append)
        self.assertEqual(w.index(), 0)
        w.set_index(1, animate=False, emit=True)
        self.assertEqual((w.index(), got), (1, [1]))
        w.set_index(1, animate=False, emit=True)          # no change, no signal
        self.assertEqual(got, [1])
        # the thumb sits on the chosen tab: the right half
        r = w._tab_rect(0, w._pos)
        self.assertGreater(r.left(), w.width() / 2 - w.PAD - 1)

    def test_studio_easing(self):
        # cubic-bezier(0.34, 1.56, 0.64, 1) overshoots past 1 and settles.
        vals = [navbar._EASE.valueForProgress(t / 20.0) for t in range(21)]
        self.assertGreater(max(vals), 1.0)
        self.assertAlmostEqual(vals[-1], 1.0, places=6)


@unittest.skipIf(mp is None, "PySide6 not installed")
class TestStudioBoard(unittest.TestCase):
    def test_every_library_module_has_a_picture_or_is_known(self):
        presets = os.path.join(REPO, "models", "presets.yaml")
        if not os.path.isfile(presets):
            self.skipTest("module library not in this checkout")
        with open(presets, encoding="utf-8") as fh:
            keys = re.findall(r"^([a-z0-9_]+):\s*$", fh.read(), re.M)
        modules = [k for k in keys if k != "motherboard_14_port"]
        # Off-board parts (the wheel, the NEMA 17) are never seated on the
        # board, so they need no board picture. Modules with no Atech CAD yet
        # (derived placeholder meshes, projects/import_simready.py) have no
        # studio picture either; the board map draws them as labelled cells.
        off_board = ("n20_wheel", "nema17_stepper")
        no_cad = ("pir", "scd40_air_quality", "robot_arm", "stepper_motor")
        missing = [k for k in modules
                   if k not in mp.SPRITE_FOR and k not in off_board + no_cad]
        self.assertEqual(missing, [])
        for k, name in mp.SPRITE_FOR.items():
            self.assertIsNotNone(mp.sprite(name), "%s -> %s.png" % (k, name))
        self.assertIsNotNone(mp.sprite(mp.BOARD_SPRITE))

    def test_sprites_match_their_manifest(self):
        import hashlib
        with open(os.path.join(mp.SPRITE_DIR, "MANIFEST.json"), encoding="utf-8") as fh:
            sprites = json.load(fh)["sprites"]
        for name, rec in sprites.items():
            with open(os.path.join(mp.SPRITE_DIR, rec["file"]), "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), rec["sha256"], name)

    def test_cells_are_studios_layout(self):
        self.assertEqual(sorted(mp.CELLS), list(range(1, 15)))
        for n in range(1, 7):
            self.assertEqual(mp.CELLS[n][1], (-1, 0))     # left column faces left
        for n in range(9, 15):
            self.assertEqual(mp.CELLS[n][1], (1, 0))
        self.assertEqual(mp.CELLS[7][1], (0, -1))         # top edge
        self.assertEqual(mp.CELLS[8][1], (0, 1))          # USB-C, bottom

    def test_pose_and_turn(self):
        (x, z), out = mp.module_pose((1, 2))               # two-port: the mean
        self.assertAlmostEqual(x, -19.5)
        self.assertAlmostEqual(z, -39.995)
        self.assertEqual(out, (-1, 0))
        self.assertIsNone(mp.module_pose((99,)))
        self.assertAlmostEqual(mp.outward_angle((0, -1)), 0.0)    # up stays up
        self.assertAlmostEqual(mp.outward_angle((1, 0)), 90.0)
        self.assertAlmostEqual(mp.outward_angle((-1, 0)), -90.0)
        self.assertAlmostEqual(abs(mp.outward_angle((0, 1))), 180.0)

    def test_board_paints_and_picks(self):
        w = mp.BoardMap()
        w.resize(340, 420)
        ports = {n: object() for n in range(1, 15)}
        w.set_state(ports, {1: "Screen", 2: "Screen"}, 4,
                    {"Screen": ("screen", (1, 2)), "W": ("n20_wheel", (5,))})
        img = w.grab().toImage()
        self.assertFalse(img.isNull())
        # the board's charcoal is drawn at the centre
        c = img.pixelColor(img.width() // 2, img.height() // 2)
        self.assertLess(c.lightness(), 110)
        got = []
        w.picked.connect(got.append)
        r = w._cell(4)
        ev_pos = r.center()
        self.assertEqual(w._hit(ev_pos), 4)
        self.assertIsNone(w._hit(QtCore.QPointF(2, 2)))


if __name__ == "__main__":
    unittest.main()
