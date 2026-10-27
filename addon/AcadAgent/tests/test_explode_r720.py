"""R720: the exploded view is display only, whatever else happens.

  TestExplodeFreeCAD  under freecadcmd: a hand move made while the parts are
                      apart is kept; a second Exploder never stores pulled-
                      apart values; Undo while apart lands assembled; a part
                      deleted while apart; a closed document is forgotten.
                      Each has a sabotage run (Exploder.absorb removed).
  TestWidgets         offscreen Qt: the Show and hide popover opens above a
                      button at the bottom of the screen and stays on it;
                      Enter in an Edit shapes box clicks no button.

    QT_QPA_PLATFORM=offscreen python -m unittest -v test_explode_r720
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

try:
    from PySide6 import QtCore, QtWidgets
    APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
except ImportError:
    QtWidgets = None


def _fc():
    try:
        from acadagent import sandbox
        return sandbox.find_freecadcmd()
    except Exception:                                      # noqa: BLE001
        return os.environ.get("ATECH_FREECADCMD")


FC_SCRIPT = r'''
import sys, json, os
sys.path.insert(0, os.environ["R720_ADDON"])
import FreeCAD as App, Part
from acadagent import export_tools as et
if os.environ.get("R720_SABOTAGE"):
    et.Exploder.absorb = lambda self, assembled_space=False: None
out, calls = {}, []
class Obs:
    def slotUndoDocument(self, doc):
        calls.append("undo"); et.explode_after_undo(doc)
App.addDocumentObserver(Obs())
doc = App.newDocument("T"); doc.UndoMode = 1
for i, x in enumerate((-50, 0, 50)):
    o = doc.addObject("Part::Feature", "P%d" % i)
    o.Shape = Part.makeBox(10, 10, 10, App.Vector(x, 0, 0))
doc.recompute()
P = lambda n: tuple(round(v, 6) for v in doc.getObject(n).Placement.Base)
base = {n: P(n) for n in ("P0", "P1", "P2")}
et.set_explode(doc, 0.6)
pl = doc.getObject("P0").Placement.copy(); pl.Base.z += 5; doc.getObject("P0").Placement = pl
et.set_explode(doc, 0.0)
out["hand_move_kept"] = P("P0") == (base["P0"][0], base["P0"][1], base["P0"][2] + 5)
out["others_back"] = P("P2") == base["P2"]
et.set_explode(doc, 0.6)
et.Exploder(doc).set_factor(0.3)
et.restore_exploded(doc)
out["no_stale_after_two"] = P("P2") == base["P2"] and et.explode_amount(doc) == 0.0
doc.openTransaction("move")
pl = doc.getObject("P2").Placement.copy(); pl.Base.y += 7; doc.getObject("P2").Placement = pl
doc.commitTransaction()
et.set_explode(doc, 0.6)
doc.undo()
out["undo_signal"] = calls[:]
out["undo_still_apart"] = et.explode_amount(doc) > 0
et.set_explode(doc, 0.0)
out["undo_lands_assembled"] = P("P2") == base["P2"]
et.set_explode(doc, 0.6); doc.removeObject("P1"); et.set_explode(doc, 0.0)
out["delete_ok"] = P("P2") == base["P2"]
et.set_explode(doc, 0.6); et.forget_exploded(doc)
out["forgotten"] = et.explode_amount(doc) == 0.0
sys.stdout.write("\nR720=" + json.dumps(out) + "\n"); sys.stdout.flush()
os._exit(0)
'''


def run_fc(sabotage=False):
    dst = tempfile.mkdtemp(prefix="atech-r720-")
    script = os.path.join(dst, "r720_fc.py")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(FC_SCRIPT)
    env = dict(os.environ, R720_ADDON=ADDON)
    if sabotage:
        env["R720_SABOTAGE"] = "1"
    p = subprocess.run([_fc(), script], env=env, capture_output=True, text=True, timeout=300)
    text = p.stdout + p.stderr
    k = text.rfind("R720=")
    if k < 0:
        raise AssertionError("no result line:\n" + text[-3000:])
    return json.loads(text[k + len("R720="):].split("\n", 1)[0])


@unittest.skipIf(not _fc(), "bundled freecadcmd not found (set ATECH_FREECADCMD)")
class TestExplodeFreeCAD(unittest.TestCase):
    def test_display_only(self):
        r = run_fc()
        self.assertEqual(r["undo_signal"], ["undo"], "FreeCAD sends slotUndoDocument")
        for k in ("hand_move_kept", "others_back", "no_stale_after_two", "undo_still_apart",
                  "undo_lands_assembled", "delete_ok", "forgotten"):
            self.assertTrue(r[k], k)

    def test_sabotage_without_absorb_moves_are_lost(self):
        r = run_fc(sabotage=True)
        self.assertFalse(r["hand_move_kept"])
        self.assertFalse(r["undo_lands_assembled"])


@unittest.skipIf(QtWidgets is None, "PySide6 not available (run with the bundled python)")
class TestWidgets(unittest.TestCase):
    def test_popover_opens_above_a_button_at_the_bottom(self):
        from acadagent import visibility
        area = APP.primaryScreen().availableGeometry()
        w = QtWidgets.QWidget()
        w.setGeometry(area.left() + 100, area.bottom() - 30, 34, 24)
        w.show()
        size = QtCore.QSize(340, 380)
        pos = visibility.popover_pos(w, size)
        self.assertLessEqual(pos.y() + size.height(), area.bottom() + 1)
        self.assertLess(pos.y(), w.mapToGlobal(QtCore.QPoint(0, 0)).y())
        w.move(area.left() + 100, area.top() + 10)        # room below: under it
        pos = visibility.popover_pos(w, size)
        self.assertGreater(pos.y(), w.mapToGlobal(QtCore.QPoint(0, 0)).y())
        w.close()

    def test_enter_in_a_box_clicks_no_button(self):
        from acadagent import manual_edit
        d = manual_edit.ShapeEditor(None)
        btns = d.findChildren(QtWidgets.QPushButton)
        self.assertTrue(btns)
        self.assertFalse([b.text() for b in btns if b.autoDefault() or b.isDefault()])
        d.close()


if __name__ == "__main__":
    unittest.main()
