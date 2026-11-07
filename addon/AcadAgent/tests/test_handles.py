"""R890 handles in the 3D view, Align, Mirror and Text.

  TestGeometry   fc_arrange.py under freecadcmd (align, mirror, text, the
                 pivy overlay); skips without ATECH_FREECADCMD
  TestMath       the drag math, no FreeCAD: snapping, handle places, a
                 resize keeps the opposite side, proportions, moves, turns,
                 ray / plane, picking the nearest handle
  TestWindow     Edit shapes has Text, Grid, Mirror and Align, offscreen Qt

    QT_QPA_PLATFORM=offscreen python -m unittest -v test_handles
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
if ADDON not in sys.path:
    sys.path.insert(0, ADDON)

from acadagent import arrange                             # noqa: E402
from acadagent import handles as h                        # noqa: E402

try:
    from PySide6 import QtWidgets
    APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
except ImportError:
    QtWidgets = None


def _fc():
    try:
        from acadagent import sandbox
        return sandbox.find_freecadcmd()
    except Exception:                                      # noqa: BLE001
        return os.environ.get("ATECH_FREECADCMD")


FC = _fc()


@unittest.skipIf(FC is None, "freecadcmd not found (set ATECH_FREECADCMD)")
class TestGeometry(unittest.TestCase):
    def test_fc_arrange(self):
        home = tempfile.mkdtemp(prefix="atech-ar-")
        env = {"HOME": home, "FREECAD_USER_HOME": home, "PATH": "/usr/bin:/bin"}
        p = subprocess.run([FC, os.path.join(HERE, "fc_arrange.py")], env=env,
                           cwd=home, capture_output=True, text=True, timeout=300)
        line = [ln for ln in (p.stdout + p.stderr).splitlines()
                if ln.startswith("ARRANGE_RESULT=")]
        self.assertTrue(line, (p.stdout + p.stderr)[-2000:])
        r = json.loads(line[-1].split("=", 1)[1])
        failed = [k for k, v in r["checks"].items() if not v]
        self.assertTrue(r["ok"], (failed, r["errors"]))
        self.assertGreaterEqual(len(r["checks"]), 18)


class TestMath(unittest.TestCase):
    def close(self, a, b):
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, places=6)

    def test_snap(self):
        self.assertEqual(h.snap(12.4, 1.0), 12.0)
        self.assertEqual(h.snap(12.6, 0.5), 12.5)
        self.assertEqual(h.snap(3.3, 0), 3.3)
        self.assertEqual(h.snap(-2.6, 1.0), -3.0)

    def test_handle_points(self):
        pts = h.handle_points((0, 0, 0, 40, 20, 10))
        self.assertEqual(pts["x+"], (40, 10, 0))
        self.assertEqual(pts["y-"], (20, 0, 0))
        self.assertEqual(pts["z+"], (20, 10, 10))
        self.assertGreater(pts["lift"][2], 10)
        self.assertEqual(set(pts), set(h.HANDLES))

    def test_resize_keeps_opposite_side(self):
        size, pos = h.resize_from_drag((40, 20, 10), (20, 10, 0), "x+", (5.2, 3, 0))
        self.close(size, (45, 20, 10))
        self.close(pos, (22.5, 10, 0))       # left side stays at x = 0
        size, pos = h.resize_from_drag((40, 20, 10), (20, 10, 0), "x-", (5, 0, 0))
        self.close(size, (35, 20, 10))
        self.close(pos, (22.5, 10, 0))       # right side stays at x = 40
        size, pos = h.resize_from_drag((40, 20, 10), (20, 10, 0), "x+y+", (2, 4, 0))
        self.close(size, (42, 24, 10))
        size, pos = h.resize_from_drag((40, 20, 10), (20, 10, 0), "z+", (0, 0, 7.6))
        self.close(size, (40, 20, 18))
        self.close(pos, (20, 10, 0))         # the bottom stays

    def test_resize_never_below_minimum(self):
        size, _p = h.resize_from_drag((10, 10, 10), (0, 0, 0), "x+", (-50, 0, 0))
        self.assertGreater(size[0], 0)

    def test_resize_keep_proportions(self):
        size, _p = h.resize_from_drag((40, 20, 10), (20, 10, 0), "x+", (40, 0, 0),
                                      keep=True)
        self.close(size, (80, 40, 20))

    def test_move_lift_turn(self):
        self.close(h.move_from_drag((0, 0, 5), (3.4, -1.6, 9)), (3, -2, 5))
        self.close(h.lift_from_drag((1, 2, 0), 4.7), (1, 2, 5))
        self.assertEqual(h.angle_from_drag((0, 0, 0), "z", (10, 0, 0), (0, 10, 0)), 90)
        self.assertEqual(h.angle_from_drag((0, 0, 0), "z", (10, 0, 0), (10, -3, 0)), -15)
        self.assertEqual(h.angle_from_drag((0, 0, 0), "z", (0, 0, 5), (1, 0, 0)), 0.0)
        self.assertEqual(h.angle_from_drag((0, 0, 0), "x", (0, 10, 0), (0, 7, 7), 45), 45)

    def test_ray_plane_and_planes(self):
        p = h.ray_plane((0, 0, 10), (0, 0, -1), (0, 0, 0), (0, 0, 1))
        self.close(p, (0, 0, 0))
        self.assertIsNone(h.ray_plane((0, 0, 10), (1, 0, 0), (0, 0, 0), (0, 0, 1)))
        pt, n = h.drag_plane("z+", (1, 2, 3), (0.5, 0.5, -0.7))
        self.assertEqual(n[2], 0.0)          # vertical plane for height
        pt, n = h.drag_plane("x+", (1, 2, 3), (0, 0, -1))
        self.assertEqual(n, (0.0, 0.0, 1.0))
        pt, n = h.drag_plane("z+", (1, 2, 3), (0, 0, -1))   # looking straight down
        self.assertNotEqual(n, (0.0, 0.0, 0.0))

    def test_nearest(self):
        pts = {"x+": (100, 100), "z+": (108, 100), "lift": (300, 300)}
        self.assertEqual(h.nearest(pts, (106, 101)), "z+")
        self.assertIsNone(h.nearest(pts, (200, 200)))

    def test_labels(self):
        self.assertEqual(h.label_for("x+", (40, 20, 10), (0, 0, 0)), "40 mm")
        self.assertEqual(h.label_for("x+y-", (40, 20.5, 10), (0, 0, 0)), "40 x 20.5 mm")
        self.assertEqual(h.label_for("lift", (1, 1, 1), (0, 0, 7)), "elevation 7 mm")

    def test_align_targets(self):
        boxes = [(0, 10), (20, 40), (5, 6)]
        self.assertEqual(arrange.align_targets(boxes, "x", "min"), [0, -20, -5])
        self.assertEqual(arrange.align_targets(boxes, "x", "max"), [30, 0, 34])
        self.assertEqual(arrange.align_targets(boxes, "x", "centre"), [15, -10, 14.5])


@unittest.skipIf(QtWidgets is None, "PySide6 not installed")
class TestWindow(unittest.TestCase):
    def test_edit_shapes_has_new_tools(self):
        from acadagent import manual_edit
        d = manual_edit.ShapeEditor(None)
        try:
            self.assertEqual(d.btn_text.text(), "Text")
            self.assertEqual(d.grid.currentData(), h.DEFAULT_SNAP)
            self.assertEqual(set(d.btn_mirror), {"x", "y", "z"})
            self.assertEqual(set(d.btn_align), {"min", "centre", "max"})
            for b in list(d.btn_align.values()) + list(d.btn_mirror.values()):
                self.assertFalse(b.isEnabled(), b.text())   # nothing selected
        finally:
            d.close()


if __name__ == "__main__":
    unittest.main()
