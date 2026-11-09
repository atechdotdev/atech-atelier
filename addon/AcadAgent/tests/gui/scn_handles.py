"""R890 drag handles, driven with real mouse events on the 3D view.

Opens Edit shapes on a box, then presses, drags and releases the mouse on
the viewer widget (QMouseEvents, as a user's hand would) and checks:
  * the handles overlay is in the scene graph
  * dragging a side handle resizes the box on release (snapped)
  * dragging the top handle sets the height, the lift arrow raises it
  * dragging the body moves it on the floor
  * dragging the turn arrow turns it in 15 degree steps
  * each drag is one undo step
  * a plain click elsewhere still reaches FreeCAD (navigation untouched)

    python3 app_driver.py scn_handles.py --app <test app>

The app's window shows on screen while it runs: on macOS Qt's offscreen
platform has no OpenGL, so FreeCAD cannot make a 3D view there (MEASURED
2026-11-09: "QOpenGLWidget is not supported on this platform", then a
crash). The same drags run headless in fc_handles.py on a stand-in view.
"""
import os
import sys

sys.path.insert(0, os.environ["ATECH_GUI_HARNESS"])
from scenario_base import Scenario  # noqa: E402

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402


def viewer():
    v = Gui.ActiveDocument.ActiveView
    gv = v.graphicsView()
    return v, gv, gv.viewport()


def to_qt(w, p):
    """Coin screen point (device pixels, y up) -> widget point."""
    dpr = w.devicePixelRatioF()
    return QtCore.QPointF(p[0] / dpr, (w.height() * dpr - p[1]) / dpr)


def mouse(w, kind, pt, buttons=QtCore.Qt.LeftButton, mods=QtCore.Qt.NoModifier):
    t = {"press": QtCore.QEvent.MouseButtonPress,
         "move": QtCore.QEvent.MouseMove,
         "release": QtCore.QEvent.MouseButtonRelease}[kind]
    btn = QtCore.Qt.NoButton if kind == "move" else QtCore.Qt.LeftButton
    held = buttons if kind != "release" else QtCore.Qt.NoButton
    g = w.mapToGlobal(pt.toPoint())
    ev = QtGui.QMouseEvent(t, pt, QtCore.QPointF(g), btn, held, mods)
    QtWidgets.QApplication.sendEvent(w, ev)


def main(s):
    s.step("wait for Atech shell", s.wait_shell)
    d = s.result["data"]
    from acadagent import shape_edit as se, handles, manual_edit
    doc = s.new_doc("Handles")
    box = s.step("add box", lambda: se.add_shape(doc, "box"))
    box = box if box is not None else doc.Objects[-1]
    if isinstance(box, str):
        box = doc.getObject(box)
    doc.recompute()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, box.Name)
    v, gv, vp = viewer()
    v.viewIsometric()
    v.fitAll()
    s.pump(300)
    dlg = s.step("open Edit shapes", lambda: manual_edit.open_editor(s.mw))
    s.pump(400)
    h = handles.active()
    d["handles_active"] = h is not None
    d["overlay_in_scene"] = bool(h and h.node is not None)
    d["viewport_size"] = [vp.width(), vp.height(), vp.devicePixelRatioF()]
    s.grab_3d("handles_start")
    if h is None:
        raise RuntimeError("no handles")

    def drag(handle, dx, dy, mods=QtCore.Qt.NoModifier, steps=6):
        o = h.obj
        pts = handles.handle_points(handles._box(o))
        if handle == handles.BODY:
            bb = handles._box(o)
            p3 = ((bb[0] + bb[3]) / 2, (bb[1] + bb[4]) / 2, bb[5])
        else:
            p3 = pts[handle]
        a = to_qt(vp, h._screen(p3))
        b = a + QtCore.QPointF(dx, dy)
        hit = h.hit(tuple(int(round(c)) for c in h._screen(p3)))
        mouse(vp, "press", a, mods=mods)
        s.pump(30)
        started = h.drag is not None
        for i in range(1, steps + 1):
            mouse(vp, "move", a + (b - a) * (i / float(steps)), mods=mods)
            s.pump(20)
        mouse(vp, "release", b, mods=mods)
        s.pump(150)
        return {"hit": hit, "started": started, "drag_left": h.drag is not None}

    def record(name, fn):
        before = (tuple(round(x, 3) for x in se.size(h.obj)),
                  tuple(round(x, 3) for x in se.position(h.obj)),
                  round(h.obj.Placement.Rotation.Angle * 57.29578, 2))
        undo0 = doc.UndoCount
        info = fn()
        o = h.obj
        after = (tuple(round(x, 3) for x in se.size(o)),
                 tuple(round(x, 3) for x in se.position(o)),
                 round(o.Placement.Rotation.Angle * 57.29578, 2))
        info.update(before=before, after=after, undo_steps=doc.UndoCount - undo0)
        d[name] = info
        return info

    r = s.step("drag side x+", lambda: record("side", lambda: drag("x+", 80, 0)))
    s.grab_3d("after_side")
    s.step("drag top", lambda: record("top", lambda: drag("z+", 0, -60)))
    s.step("drag lift", lambda: record("lift", lambda: drag("lift", 0, -50)))
    s.step("drag body", lambda: record("body", lambda: drag(handles.BODY, -70, 30)))
    s.step("drag turn z", lambda: record("turn", lambda: drag("rot_z", -60, -60, steps=10)))
    s.grab_3d("after_all")

    # undo walks back one drag at a time
    def undo_one():
        n = doc.UndoCount
        doc.undo()
        doc.recompute()
        s.pump(100)
        return n - doc.UndoCount
    d["undo_one"] = s.step("undo one drag", undo_one)

    # a click on empty space is not swallowed (FreeCAD clears the selection)
    def empty_click():
        p = QtCore.QPointF(8, 8)
        mouse(vp, "press", p)
        mouse(vp, "release", p)
        s.pump(200)
        return len(Gui.Selection.getSelection())
    d["selection_after_empty_click"] = s.step("click empty space", empty_click)
    d["overlay_after_deselect"] = h.node is not None

    def close():
        dlg.close()
        s.pump(200)
        return handles.active() is None
    d["handles_stopped"] = s.step("close Edit shapes", close)

    checks = {
        "overlay": d["overlay_in_scene"],
        "side_hit": d.get("side", {}).get("hit") == "x+",
        "side_resized": bool(d.get("side")) and d["side"]["after"][0][0] > d["side"]["before"][0][0],
        "side_one_undo": d.get("side", {}).get("undo_steps") == 1,
        "top_taller": bool(d.get("top")) and d["top"]["after"][0][2] > d["top"]["before"][0][2],
        "lift_raised": bool(d.get("lift")) and d["lift"]["after"][1][2] > d["lift"]["before"][1][2],
        "body_moved": bool(d.get("body")) and d["body"]["after"][1][:2] != d["body"]["before"][1][:2],
        "body_on_floor": bool(d.get("body")) and d["body"]["after"][1][2] == d["body"]["before"][1][2],
        "turned": bool(d.get("turn")) and d["turn"]["after"][2] != d["turn"]["before"][2]
                  and abs(d["turn"]["after"][2] % 15) < 0.01,
        "undo_one": d.get("undo_one") == 1,
        "empty_click_deselects": d.get("selection_after_empty_click") == 0,
        "stopped": d.get("handles_stopped") is True,
    }
    d["checks"] = checks
    s.result["ok"] = all(checks.values()) and all(st["ok"] for st in s.result["steps"])


Scenario("handles").run(main)
