"""R890 drag handles end to end under freecadcmd (no GUI, no OpenGL).

The 3D view is a stand-in (FakeView) with the calls handles.Handles makes
on a FreeCAD view - getPoint, getPointOnScreen, getViewDirection,
getObjectInfo, getCameraNode, the scene graph and the pivy event callbacks -
and a real Coin camera (orthographic or perspective) doing the projection.
Mouse presses, moves and releases go in as real Coin events through the
registered callbacks, so hit testing, drag planes, snapping, the resize /
move / turn on release and the undo steps all run as in Atelier.

Prints HANDLES_RESULT=<json>.

    freecadcmd tests/fc_handles.py
"""
import json
import math
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import FreeCAD  # noqa: E402
from pivy import coin  # noqa: E402

from acadagent import handles as H  # noqa: E402
from acadagent import shape_edit as se  # noqa: E402

CHECKS = {}
ERRORS = []


def check(name, cond, detail=None):
    CHECKS[name] = bool(cond)
    if not cond:
        ERRORS.append("%s: %r" % (name, detail))


def _n(v):
    m = math.sqrt(sum(c * c for c in v))
    return tuple(c / m for c in v)


class FakeView(object):
    """A W x H pixel view looking along `direction` at `centre`, `mm_px`
    millimetres per pixel at the focal plane. Screen points are device
    pixels with y up, as Coin's."""

    def __init__(self, direction=(-1, 1, -1), centre=(0, 0, 10), mm_px=0.1,
                 w=1200, h=800, perspective=False, doc=None):
        self.d = _n(direction)
        up0 = (0.0, 0.0, 1.0)
        r = H._cross(self.d, up0)
        self.r = _n(r)
        self.u = _n(H._cross(self.r, self.d))
        self.c = centre
        self.k = mm_px
        self.w, self.h = w, h
        self.dist = 300.0
        self.eye = tuple(centre[i] - self.d[i] * self.dist for i in range(3))
        self.persp = perspective
        if perspective:
            self.cam = coin.SoPerspectiveCamera()
        else:
            self.cam = coin.SoOrthographicCamera()
        self.cam.position.setValue(*self.eye)
        self.root = coin.SoSeparator()
        self.cbs = []
        self.doc = doc

    # -- what Handles calls
    def getCameraNode(self):
        return self.cam

    def getSceneGraph(self):
        return self.root

    def getViewDirection(self):
        return FreeCAD.Vector(*self.d)

    def addEventCallbackPivy(self, t, fn):
        self.cbs.append((t, fn))
        return fn

    def removeEventCallbackPivy(self, t, fn):
        self.cbs = [(a, b) for a, b in self.cbs if b is not fn]

    def getPointOnScreen(self, p):
        v = (p.x - self.eye[0], p.y - self.eye[1], p.z - self.eye[2])
        f = 1.0
        if self.persp:
            depth = H._dot(v, self.d)
            f = self.dist / depth
        x = H._dot(v, self.r) * f / self.k + self.w / 2.0
        y = H._dot(v, self.u) * f / self.k + self.h / 2.0
        return (int(round(x)), int(round(y)))

    def getPoint(self, pos):
        """The point on the focal plane under the screen point."""
        a = (pos[0] - self.w / 2.0) * self.k
        b = (pos[1] - self.h / 2.0) * self.k
        return FreeCAD.Vector(*[self.c[i] + self.r[i] * a + self.u[i] * b
                                for i in range(3)])

    def ray(self, pos):
        p = self.getPoint(pos)
        p = (p.x, p.y, p.z)
        d = _n(H._sub(p, self.eye)) if self.persp else self.d
        return p, d

    def getObjectInfo(self, pos):
        """The first part whose box the ray hits (slab test)."""
        o, d = self.ray(pos)
        if self.persp:
            o = self.eye
        best = None
        for obj in (self.doc.Objects if self.doc else []):
            sh = getattr(obj, "Shape", None)
            if sh is None or sh.isNull():
                continue
            bb = sh.BoundBox
            lo, hi = (bb.XMin, bb.YMin, bb.ZMin), (bb.XMax, bb.YMax, bb.ZMax)
            t0, t1 = -1e18, 1e18
            for i in range(3):
                if abs(d[i]) < 1e-12:
                    if not lo[i] <= o[i] <= hi[i]:
                        t0, t1 = 1, 0
                    continue
                a, b = (lo[i] - o[i]) / d[i], (hi[i] - o[i]) / d[i]
                t0, t1 = max(t0, min(a, b)), min(t1, max(a, b))
            if t0 <= t1 and (best is None or t0 < best[0]):
                best = (t0, obj)
        if best is None:
            return None
        t, obj = best
        return {"Object": obj.Name, "x": o[0] + d[0] * t, "y": o[1] + d[1] * t,
                "z": o[2] + d[2] * t}

    # -- the hand
    def _send(self, ev):
        handled = [False]

        class CB(object):
            def getEvent(self_):
                return ev

            def setHandled(self_):
                handled[0] = True
        for t, fn in list(self.cbs):
            if ev.isOfType(t):
                fn(CB())
        return handled[0]

    def press(self, pos, shift=False, down=True):
        ev = coin.SoMouseButtonEvent()
        ev.setButton(coin.SoMouseButtonEvent.BUTTON1)
        ev.setState(coin.SoMouseButtonEvent.DOWN if down else coin.SoMouseButtonEvent.UP)
        ev.setPosition(coin.SbVec2s(int(pos[0]), int(pos[1])))
        ev.setShiftDown(shift)
        return self._send(ev)

    def move(self, pos, shift=False):
        ev = coin.SoLocation2Event()
        ev.setPosition(coin.SbVec2s(int(pos[0]), int(pos[1])))
        ev.setShiftDown(shift)
        return self._send(ev)

    def drag(self, a, b, steps=8, shift=False):
        took = self.press(a, shift)
        for i in range(1, steps + 1):
            self.move((a[0] + (b[0] - a[0]) * i / steps,
                       a[1] + (b[1] - a[1]) * i / steps), shift)
        self.press(b, shift, down=False)
        return took

    def screen_of_world(self, p):
        return self.getPointOnScreen(FreeCAD.Vector(*p))

    def screen_for_floor(self, p0, dp):
        """Screen point where the floor point p0 + dp shows."""
        return self.screen_of_world(tuple(p0[i] + dp[i] for i in range(3)))


def r3(t):
    return tuple(round(x, 3) for x in t)


def run(perspective):
    tag = "persp_" if perspective else "ortho_"
    doc = FreeCAD.newDocument("Handles" + tag.strip("_"))
    doc.UndoMode = 1
    box = se.add_shape(doc, "box")              # 20 mm cube on the floor
    doc.recompute()
    view = FakeView(perspective=perspective, doc=doc,
                    centre=se.position(box)[:2] + (10.0,))
    h = H.Handles(view, snap_step=lambda: 1.0).attach()
    h.show(box)
    check(tag + "overlay", h.node is not None and view.root.getNumChildren() == 1)
    check(tag + "callbacks", len(view.cbs) == 2)

    def handle_px(k):
        return view.screen_of_world(H.handle_points(H._box(h.obj))[k])

    # hit test: every handle's own point, a turn arrow on its arc
    pts = H.handle_points(H._box(box))
    for k in ("x+", "y-", "x-y+", "z+", "lift"):
        check(tag + "hit_" + k, h.hit(handle_px(k)) == k, h.hit(handle_px(k)))
    r = H.handle_size(H._box(box)) * 2.2
    c = pts["rot_z"]
    on_arc = view.screen_of_world((c[0], c[1] + r, c[2]))     # a quarter round
    check(tag + "hit_turn_on_arc", h.hit(on_arc) == "rot_z", h.hit(on_arc))
    far = (5, 5)
    check(tag + "miss_empty", h.hit(far) is None, h.hit(far))

    # side x+: drag 7.3 mm along +x on the floor -> 27 mm wide, x- side kept
    s0, p0 = se.size(h.obj), se.position(h.obj)
    xmin0 = H._box(h.obj)[0]
    u0 = doc.UndoCount
    a = handle_px("x+")
    took = view.drag(a, view.screen_for_floor(pts["x+"], (7.3, 0, 0)))
    s1, p1 = se.size(h.obj), se.position(h.obj)
    check(tag + "side_took_press", took)
    check(tag + "side_width_snapped", abs(s1[0] - 27.0) < 0.05, (s0, s1))
    check(tag + "side_depth_kept", abs(s1[1] - s0[1]) < 1e-6, s1)
    check(tag + "side_far_edge_kept", abs(H._box(h.obj)[0] - xmin0) < 0.05,
          (xmin0, H._box(h.obj)[0]))
    check(tag + "side_one_undo", doc.UndoCount - u0 == 1, doc.UndoCount - u0)
    check(tag + "drag_ended", h.drag is None)

    # top: up by 5 mm -> 25 mm tall
    pts = H.handle_points(H._box(h.obj))
    a = handle_px("z+")
    b = view.screen_of_world((pts["z+"][0], pts["z+"][1], pts["z+"][2] + 5.0))
    view.drag(a, b)
    check(tag + "top_height", abs(se.size(h.obj)[2] - 25.0) < 0.05, se.size(h.obj))
    check(tag + "top_on_floor", abs(se.position(h.obj)[2]) < 1e-6, se.position(h.obj))

    # corner with Shift keeps proportions
    s0 = se.size(h.obj)
    pts = H.handle_points(H._box(h.obj))
    a = handle_px("x+y+")
    view.drag(a, view.screen_for_floor(pts["x+y+"], (5.4, 0, 0)), shift=True)
    s1 = se.size(h.obj)
    check(tag + "corner_shift_ratio",
          abs(s1[0] / s0[0] - s1[2] / s0[2]) < 0.01 and s1[0] > s0[0], (s0, s1))

    # lift: 4 mm up
    z0 = se.position(h.obj)[2]
    pts = H.handle_points(H._box(h.obj))
    a = handle_px("lift")
    view.drag(a, view.screen_of_world((pts["lift"][0], pts["lift"][1],
                                       pts["lift"][2] + 4.0)))
    check(tag + "lift_raised", abs(se.position(h.obj)[2] - z0 - 4.0) < 0.05,
          (z0, se.position(h.obj)[2]))

    # body: grab the top face off its middle (the middle is the height
    # handle), slide 12 mm -x, 6 mm +y
    bb = H._box(h.obj)
    top = (bb[0] + 0.3 * (bb[3] - bb[0]), bb[1] + 0.3 * (bb[4] - bb[1]), bb[5])
    p0 = se.position(h.obj)
    a = view.screen_of_world(top)
    check(tag + "body_hit", h.hit(a) == H.BODY, h.hit(a))
    view.drag(a, view.screen_for_floor(top, (-12.0, 6.0, 0)))
    p1 = se.position(h.obj)
    check(tag + "body_moved", abs(p1[0] - p0[0] + 12) < 0.6 and abs(p1[1] - p0[1] - 6) < 0.6,
          (r3(p0), r3(p1)))
    check(tag + "body_height_kept", abs(p1[2] - p0[2]) < 1e-6, (p0, p1))
    check(tag + "body_snapped", abs((p1[0] - p0[0]) - round(p1[0] - p0[0])) < 1e-6,
          p1[0] - p0[0])

    # turn about z by a quarter: on the arc's start (angle 0) to its 90 deg
    pts = H.handle_points(H._box(h.obj))
    c = pts["rot_z"]
    r = H.handle_size(H._box(h.obj)) * 2.2
    a = view.screen_of_world((c[0] + r, c[1], c[2]))
    bb = H._box(h.obj)
    centre = ((bb[0] + bb[3]) / 2, (bb[1] + bb[4]) / 2, (bb[2] + bb[5]) / 2)
    # end where the start point lands after turning it 90 deg about the centre
    sx, sy = c[0] + r - centre[0], c[1] - centre[1]
    end = (centre[0] - sy, centre[1] + sx, c[2])
    u0 = doc.UndoCount
    rot0 = h.obj.Placement.Rotation
    view.drag(a, view.screen_of_world(end), steps=12)
    rot1 = h.obj.Placement.Rotation
    rel = rot1.multiply(rot0.inverted())
    ang = math.degrees(rel.Angle) * (1 if rel.Axis.z >= 0 else -1)
    check(tag + "turned_90", abs(ang - 90) < 0.5, ang)
    check(tag + "turn_one_undo", doc.UndoCount - u0 == 1, doc.UndoCount - u0)

    # a press-release without moving changes nothing and leaves no undo step
    u0 = doc.UndoCount
    p0 = se.position(h.obj)
    a = handle_px("x+")
    view.press(a)
    view.press(a, down=False)
    check(tag + "click_no_change", doc.UndoCount == u0 and r3(se.position(h.obj)) == r3(p0),
          (doc.UndoCount - u0,))

    # a press on empty space is not taken (FreeCAD navigates / deselects)
    check(tag + "empty_not_taken", not view.press(far))
    view.press(far, down=False)

    # undo walks back the last drag
    n = doc.UndoCount
    doc.undo()
    doc.recompute()
    check(tag + "undo_one", n - doc.UndoCount == 1)

    # hardware has no handles; an agent part only lift / turn / body
    hw = doc.addObject("Part::Feature", "Board")
    hw.Shape = __import__("Part").makeBox(10, 10, 2)
    hw.addProperty("App::PropertyString", "AtechRole", "Atech")
    hw.AtechRole = next(iter(se.HARDWARE_ROLES))
    h.show(hw)
    check(tag + "hardware_none", h.node is None)

    h.detach()
    check(tag + "detached", not view.cbs and view.root.getNumChildren() == 0)
    FreeCAD.closeDocument(doc.Name)


try:
    run(False)
    run(True)
except Exception:                                          # noqa: BLE001
    ERRORS.append(traceback.format_exc())

print("HANDLES_RESULT=" + json.dumps({"ok": not ERRORS and all(CHECKS.values()),
                                      "checks": CHECKS, "errors": ERRORS}))
