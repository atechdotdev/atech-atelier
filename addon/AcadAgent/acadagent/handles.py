"""handles - TinkerCAD-style handles in the 3D view (R890).

While the Edit shapes window (manual_edit, R) is open, the selected part
gets handles drawn round it in the 3D view, and they are dragged with the
mouse:

    white squares   on the sides and corners of its footprint: drag to
                    change the width / depth (the opposite side stays put);
                    Shift keeps the proportions
    white square    on top: drag to change the height
    black cone      above it: drag to raise or lower it (its elevation)
    curved arrows   turn it about Z, X or Y, in snap steps (Shift: 45 deg)
    the part itself drag it across the floor (the workplane)

Sizes and moves snap to the grid step chosen in Edit shapes (1 mm by
default, as TinkerCAD); the size being dragged is shown beside the
handle. Each drag is one undo step. A part the agent built moves and turns
(the hand edit is kept across builds, export_tools R340) but is not
resized; Atech hardware has no handles.

The math is pure (handle_points, resize_from_drag, ...) and tested
without a GUI; Handles puts it on a FreeCAD 3D view with pivy (Coin3D).
"""
import math

from . import shape_edit as se

#: Grid steps offered (mm); TinkerCAD's default is 1 mm.
SNAP_STEPS = (0.1, 0.5, 1.0, 2.0, 5.0, 10.0)
DEFAULT_SNAP = 1.0
#: A turn snaps to this (degrees); Shift: TURN_SNAP_SHIFT.
TURN_SNAP = 15.0
TURN_SNAP_SHIFT = 45.0
#: A handle is grabbed within this many pixels of it.
GRAB_PX = 12.0
SIDES = ("x+", "x-", "y+", "y-")
CORNERS = ("x+y+", "x+y-", "x-y+", "x-y-")
TOP = "z+"
LIFT = "lift"
TURNS = ("rot_z", "rot_x", "rot_y")
BODY = "body"
HANDLES = SIDES + CORNERS + (TOP, LIFT) + TURNS


def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog("[handles] %s\n" % msg)
    except Exception:                                  # noqa: BLE001
        pass


# ------------------------------------------------------------------ pure math
def snap(v, step):
    """v to the nearest multiple of step (step <= 0: unchanged)."""
    if not step or step <= 0:
        return v
    return round(v / step) * step


def offset(box):
    """How far handles sit out from the part: grows with it, never tiny."""
    xmin, ymin, zmin, xmax, ymax, zmax = box
    diag = math.sqrt((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2)
    return max(3.0, 0.12 * diag)


def handle_points(box):
    """{handle: (x, y, z)} round a world box (xmin, ymin, zmin, xmax, ymax,
    zmax): sides and corners on the footprint, the top in the middle of
    the top, the lift cone above it, the turn arrows outside a corner."""
    xmin, ymin, zmin, xmax, ymax, zmax = box
    cx, cy = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0
    off = offset(box)
    pts = {"x+": (xmax, cy, zmin), "x-": (xmin, cy, zmin),
           "y+": (cx, ymax, zmin), "y-": (cx, ymin, zmin),
           "x+y+": (xmax, ymax, zmin), "x+y-": (xmax, ymin, zmin),
           "x-y+": (xmin, ymax, zmin), "x-y-": (xmin, ymin, zmin),
           TOP: (cx, cy, zmax), LIFT: (cx, cy, zmax + 2.0 * off),
           "rot_z": (xmax + off, ymin - off, zmin),
           "rot_x": (cx, ymin - off, zmax + off),
           "rot_y": (xmax + off, cy, zmax + off)}
    return pts


def handle_size(box):
    """Edge of a square handle (mm); the cone and arrows scale from it."""
    return max(1.2, offset(box) * 0.35)


def arc_points(which, r, n=18):
    """Offsets of a turn arrow's arc (three quarters of a circle of radius
    r about its axis) from the arrow's handle point."""
    pts = []
    for i in range(n + 1):
        a = 1.5 * math.pi * i / n
        u, v = r * math.cos(a), r * math.sin(a)
        pts.append({"rot_z": (u, v, 0.0), "rot_x": (0.0, u, v),
                    "rot_y": (u, 0.0, v)}[which])
    return pts


def resize_from_drag(size, pos, handle, delta, step=DEFAULT_SNAP,
                     keep=False):
    """((w, d, h), (x, y, z)) after dragging a size handle by `delta` (a
    world vector): the side across from the handle stays where it is;
    `keep` scales all three by the dragged axis's factor. pos is the
    footprint centre and the bottom (shape_edit.position)."""
    w, d, h = size
    x, y, z = pos
    dx, dy, dz = delta
    sx = 1 if "x+" in handle else (-1 if "x-" in handle else 0)
    sy = 1 if "y+" in handle else (-1 if "y-" in handle else 0)
    nw = max(se.MIN_MM, snap(w + sx * dx, step)) if sx else w
    nd = max(se.MIN_MM, snap(d + sy * dy, step)) if sy else d
    nh = max(se.MIN_MM, snap(h + dz, step)) if handle == TOP else h
    if keep:
        if sx and (not sy or abs(nw - w) * d >= abs(nd - d) * w):
            f = nw / w
        elif sy:
            f = nd / d
        else:
            f = nh / h
        f = max(f, se.MIN_MM / min(w, d, h))
        nw, nd, nh = w * f, d * f, h * f
    # the opposite side stays put: the centre moves half the change
    nx = x + sx * (nw - w) / 2.0
    ny = y + sy * (nd - d) / 2.0
    return (nw, nd, nh), (nx, ny, z)


def move_from_drag(pos, delta, step=DEFAULT_SNAP):
    """The footprint centre after dragging the part over the floor: the
    move snaps, the height stays."""
    return (pos[0] + snap(delta[0], step), pos[1] + snap(delta[1], step), pos[2])


def lift_from_drag(pos, dz, step=DEFAULT_SNAP):
    return (pos[0], pos[1], pos[2] + snap(dz, step))


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def angle_from_drag(centre, axis, p0, p1, step=TURN_SNAP):
    """Degrees turned about `axis` through `centre` from point p0 to p1
    (both projected onto the plane across the axis), snapped; 0 when a
    point is on the axis."""
    ax = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[axis]
    a = _sub(p0, centre)
    b = _sub(p1, centre)
    a = _sub(a, tuple(_dot(a, ax) * c for c in ax))
    b = _sub(b, tuple(_dot(b, ax) * c for c in ax))
    if _dot(a, a) < 1e-9 or _dot(b, b) < 1e-9:
        return 0.0
    ang = math.degrees(math.atan2(_dot(_cross(a, b), ax), _dot(a, b)))
    return snap(ang, step)


def ray_plane(origin, direction, point, normal):
    """Where the ray meets the plane, or None (parallel / behind)."""
    den = _dot(direction, normal)
    if abs(den) < 1e-9:
        return None
    t = _dot(_sub(point, origin), normal) / den
    return (origin[0] + direction[0] * t, origin[1] + direction[1] * t,
            origin[2] + direction[2] * t)


def drag_plane(handle, grab, view_dir):
    """(point, normal) of the plane a handle is dragged in: the floor-level
    plane for sides, corners and the body; for the top and the lift, the
    vertical plane through the grab point that faces the camera most."""
    if handle in (TOP, LIFT):
        vx, vy = view_dir[0], view_dir[1]
        n = (vx, vy, 0.0) if abs(vx) + abs(vy) > 1e-6 else (0.0, 1.0, 0.0)
        return grab, n
    if handle in TURNS:
        ax = {"rot_z": (0, 0, 1), "rot_x": (1, 0, 0), "rot_y": (0, 1, 0)}[handle]
        return grab, ax
    return grab, (0.0, 0.0, 1.0)


def nearest(points, cursor, px=GRAB_PX):
    """The handle whose screen point is within px of the cursor (closest
    first), or None. points: {handle: (sx, sy)}."""
    best = None
    for k, (sx, sy) in points.items():
        dd = math.hypot(sx - cursor[0], sy - cursor[1])
        if dd <= px and (best is None or dd < best[1]):
            best = (k, dd)
    return best[0] if best else None


def label_for(handle, size, pos):
    """The number shown beside a handle while it is dragged."""
    w, d, h = size
    if handle in ("x+", "x-"):
        return "%s mm" % se.fmt_mm(w)
    if handle in ("y+", "y-"):
        return "%s mm" % se.fmt_mm(d)
    if handle in CORNERS:
        return "%s x %s mm" % (se.fmt_mm(w), se.fmt_mm(d))
    if handle == TOP:
        return "%s mm" % se.fmt_mm(h)
    if handle == LIFT:
        return "elevation %s mm" % se.fmt_mm(pos[2])
    return ""


def allowed(obj):
    """The handles a part gets: every one for a part sized by hand, move
    and turn only for one the agent built, none for hardware."""
    k = se.kind(obj)
    if k in (None, "hardware"):
        return ()
    if se.can_resize(obj) and k != "group":
        return HANDLES + (BODY,)
    return (LIFT,) + TURNS + (BODY,)


def _box(obj):
    bb = se._world_bbox(obj)
    return (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)


# ------------------------------------------------------------------ on a view
class Handles(object):
    """The handles of the selected part on one 3D view."""

    WHITE = (1.0, 1.0, 1.0)
    INK = (0.07, 0.09, 0.15)
    ACCENT = (0.03, 0.5, 0.37)

    def __init__(self, view, snap_step=lambda: DEFAULT_SNAP, on_change=None):
        self.view = view
        self.snap_step = snap_step
        self.on_change = on_change
        self.node = None
        self.obj = None
        self.drag = None
        self._cbs = []

    # -- life
    def attach(self):
        from pivy import coin
        for t, fn in ((coin.SoMouseButtonEvent.getClassTypeId(), self._button),
                      (coin.SoLocation2Event.getClassTypeId(), self._move)):
            self._cbs.append((t, self.view.addEventCallbackPivy(t, fn)))
        return self

    def detach(self):
        for t, cb in self._cbs:
            try:
                self.view.removeEventCallbackPivy(t, cb)
            except Exception:                          # noqa: BLE001
                pass
        self._cbs = []
        if self.drag is not None:
            self._end(commit=False)
        self.clear()

    def clear(self):
        if self.node is not None:
            try:
                self.view.getSceneGraph().removeChild(self.node)
            except Exception:                          # noqa: BLE001
                pass
        self.node = None

    # -- drawing
    def show(self, obj, label=None, label_at=None):
        self.clear()
        self.obj = obj
        if obj is None or not allowed(obj):
            return
        try:
            self.node = self.build(_box(obj), allowed(obj), label, label_at)
            self.view.getSceneGraph().addChild(self.node)
        except Exception as exc:                       # noqa: BLE001
            _log("show: %r" % (exc,))
            self.node = None

    @classmethod
    def build(cls, box, which, label=None, label_at=None):
        """The overlay: an outline of the box's footprint and handles (an
        SoSeparator, unpickable, drawn on top)."""
        from pivy import coin
        root = coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        root.addChild(pick)
        # drawn over the model, so handles inside it stay visible
        depth = coin.SoDepthBuffer()
        depth.function = coin.SoDepthBuffer.ALWAYS
        root.addChild(depth)
        xmin, ymin, zmin, xmax, ymax, zmax = box
        sz = handle_size(box)
        line = coin.SoSeparator()
        st = coin.SoDrawStyle()
        st.lineWidth = 1.5
        st.linePattern = 0xF0F0
        line.addChild(st)
        col = coin.SoBaseColor()
        col.rgb = cls.ACCENT
        line.addChild(col)
        co = coin.SoCoordinate3()
        co.point.setValues(0, 5, [[xmin, ymin, zmin], [xmax, ymin, zmin],
                                  [xmax, ymax, zmin], [xmin, ymax, zmin],
                                  [xmin, ymin, zmin]])
        line.addChild(co)
        ls = coin.SoLineSet()
        ls.numVertices.setValue(5)
        line.addChild(ls)
        root.addChild(line)
        pts = handle_points(box)
        for k in which:
            if k == BODY:
                continue
            p = pts[k]
            sep = coin.SoSeparator()
            sep.setName("handle_" + k.replace("+", "p").replace("-", "m"))
            tr = coin.SoTranslation()
            tr.translation = p
            sep.addChild(tr)
            if k == LIFT:
                c = coin.SoBaseColor()
                c.rgb = cls.INK
                sep.addChild(c)
                cone = coin.SoCone()
                cone.bottomRadius = sz * 0.8
                cone.height = sz * 2.2
                rot = coin.SoRotationXYZ()
                rot.axis = coin.SoRotationXYZ.X
                rot.angle = math.pi / 2
                sep.addChild(rot)
                sep.addChild(cone)
            elif k in TURNS:
                sep.addChild(cls._arc(k, sz * 2.2))
            else:
                c = coin.SoBaseColor()
                c.rgb = cls.WHITE
                sep.addChild(c)
                cube = coin.SoCube()
                cube.width = cube.height = cube.depth = sz
                sep.addChild(cube)
                ink = coin.SoBaseColor()
                ink.rgb = cls.INK
                sep.addChild(ink)
                ds = coin.SoDrawStyle()
                ds.style = coin.SoDrawStyle.LINES
                ds.lineWidth = 1.5
                sep.addChild(ds)
                rim = coin.SoCube()
                rim.width = rim.height = rim.depth = sz
                sep.addChild(rim)
            root.addChild(sep)
        if label:
            t = coin.SoSeparator()
            tr = coin.SoTranslation()
            tr.translation = label_at or pts[TOP]
            t.addChild(tr)
            c = coin.SoBaseColor()
            c.rgb = cls.INK
            t.addChild(c)
            f = coin.SoFont()
            f.size = 14
            t.addChild(f)
            txt = coin.SoText2()
            txt.string.setValue(label)
            t.addChild(txt)
            root.addChild(t)
        return root

    @classmethod
    def _arc(cls, which, r):
        """A curved arrow (three quarters of a circle) about the axis."""
        from pivy import coin
        sep = coin.SoSeparator()
        c = coin.SoBaseColor()
        c.rgb = cls.ACCENT
        sep.addChild(c)
        st = coin.SoDrawStyle()
        st.lineWidth = 3
        sep.addChild(st)
        pts = [list(p) for p in arc_points(which, r)]
        co = coin.SoCoordinate3()
        co.point.setValues(0, len(pts), pts)
        sep.addChild(co)
        ls = coin.SoLineSet()
        ls.numVertices.setValue(len(pts))
        sep.addChild(ls)
        return sep

    # -- picking
    def _screen(self, p):
        import FreeCAD
        x, y = self.view.getPointOnScreen(FreeCAD.Vector(*p))
        return float(x), float(y)

    def _cursor(self, pos):
        """The cursor in the same screen frame as _screen(): through the
        point under it, so the two always agree."""
        p = self.view.getPoint(pos)
        return self._screen((p.x, p.y, p.z))

    def _ray(self, pos):
        """(point under the cursor, direction into the scene). A perspective
        camera's rays fan out from the eye, so the view direction alone would
        drag a part away from the cursor towards the edges of the view."""
        p = self.view.getPoint(pos)
        d = self.view.getViewDirection()
        p, d = (p.x, p.y, p.z), (d.x, d.y, d.z)
        try:
            from pivy import coin
            cam = self.view.getCameraNode()
            if cam.isOfType(coin.SoPerspectiveCamera.getClassTypeId()):
                e = tuple(cam.position.getValue().getValue())
                v = _sub(p, e)
                n = math.sqrt(_dot(v, v))
                if n > 1e-9:
                    d = (v[0] / n, v[1] / n, v[2] / n)
        except Exception:                              # noqa: BLE001
            pass
        return p, d

    def hit(self, pos):
        """The handle under the cursor, BODY when it is on the part, or None."""
        if self.obj is None:
            return None
        which = allowed(self.obj)
        box = _box(self.obj)
        pts = handle_points(box)
        cur = self._cursor(pos)
        scr = {k: self._screen(pts[k]) for k in which if k != BODY}
        k = nearest(scr, cur)
        if k:
            return k
        # a turn arrow is grabbed anywhere on its arc, not at its centre
        r = handle_size(box) * 2.2
        for k in which:
            if k in TURNS:
                c = pts[k]
                arc = {i: self._screen((c[0] + u, c[1] + v, c[2] + w))
                       for i, (u, v, w) in enumerate(arc_points(k, r))}
                if nearest(arc, cur) is not None:
                    return k
        if BODY in which:
            try:
                info = self.view.getObjectInfo(tuple(pos))
            except Exception:                          # noqa: BLE001
                info = None
            if info and info.get("Object") == self.obj.Name:
                return BODY
        return None

    # -- dragging
    def _button(self, cb):
        from pivy import coin
        ev = cb.getEvent()
        if ev.getButton() != coin.SoMouseButtonEvent.BUTTON1:
            return
        pos = tuple(ev.getPosition().getValue())
        if ev.getState() == coin.SoMouseButtonEvent.DOWN:
            k = self.hit(pos)
            if k is None or (k == BODY and self.drag is None and ev.wasCtrlDown()):
                return
            self._start(k, pos)
            cb.setHandled()
        elif self.drag is not None:
            self._end(commit=True)
            cb.setHandled()

    def _start(self, handle, pos):
        o = self.obj
        origin, d = self._ray(pos)
        box = _box(o)
        grab = handle_points(box).get(handle)
        if handle == BODY:
            info = self.view.getObjectInfo(pos) or {}
            grab = (info.get("x", origin[0]), info.get("y", origin[1]),
                    info.get("z", origin[2]))
        # a turn is dragged in the plane its arrow is drawn in (through the
        # arrow, across the axis) and measured about the part's centre
        pt, n = drag_plane(handle, grab, d)
        centre = ((box[0] + box[3]) / 2.0, (box[1] + box[4]) / 2.0,
                  (box[2] + box[5]) / 2.0)
        start = ray_plane(origin, d, pt, n) or grab
        doc = o.Document
        se._open(doc, "Drag %s" % o.Label)
        self.drag = {"handle": handle, "plane": (pt, n), "start": start,
                     "centre": centre,
                     "size": se.size(o), "pos": se.position(o),
                     "placement": o.Placement.copy(), "doc": doc,
                     "result": None}

    def _move(self, cb):
        if self.drag is None:
            return
        ev = cb.getEvent()
        pos = tuple(ev.getPosition().getValue())
        dr = self.drag
        origin, d = self._ray(pos)
        p = ray_plane(origin, d, dr["plane"][0], dr["plane"][1])
        if p is None:
            return
        delta = _sub(p, dr["start"])
        k = dr["handle"]
        step = self.snap_step() or DEFAULT_SNAP
        o = self.obj
        o.Placement = dr["placement"].copy()
        try:
            if k == BODY:
                se._shift_to(o, move_from_drag(dr["pos"], delta, step))
                dr["result"] = ("move",)
                self.show(o)
            elif k == LIFT:
                newpos = lift_from_drag(dr["pos"], delta[2], step)
                se._shift_to(o, newpos)
                dr["result"] = ("move",)
                self.show(o, label_for(k, dr["size"], newpos))
            elif k in TURNS:
                axis = k[-1]
                ang = angle_from_drag(dr["centre"], axis, dr["start"], p,
                                      TURN_SNAP_SHIFT if ev.wasShiftDown()
                                      else TURN_SNAP)
                dr["result"] = ("turn", axis, ang)
                if ang:
                    self._turn_preview(o, axis, ang)
                self.show(o, "%s°" % se.fmt_mm(ang))
            else:
                size, newpos = resize_from_drag(dr["size"], dr["pos"], k, delta,
                                                step, keep=ev.wasShiftDown())
                dr["result"] = ("resize", size, newpos)
                self._ghost(size, newpos, label_for(k, size, newpos))
        except Exception as exc:                       # noqa: BLE001
            _log("drag: %r" % (exc,))
        cb.setHandled()

    def _turn_preview(self, o, axis, ang):
        import FreeCAD
        bb = se._world_bbox(o)
        c = bb.Center
        ax = FreeCAD.Vector(*{"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[axis])
        rot = FreeCAD.Placement(FreeCAD.Vector(), FreeCAD.Rotation(ax, ang), c)
        o.Placement = rot.multiply(o.Placement)

    def _ghost(self, size, pos, label):
        """The new size as an outline (the part is resized on release)."""
        w, d, h = size
        x, y, z = pos
        box = (x - w / 2.0, y - d / 2.0, z, x + w / 2.0, y + d / 2.0, z + h)
        self.clear()
        try:
            self.node = self.build(box, allowed(self.obj), label)
            self.view.getSceneGraph().addChild(self.node)
        except Exception as exc:                       # noqa: BLE001
            _log("ghost: %r" % (exc,))

    def _end(self, commit=True):
        dr, self.drag = self.drag, None
        o, doc = self.obj, dr["doc"]
        res = dr["result"]
        try:
            if not commit or res is None:
                o.Placement = dr["placement"]
                se._abort(doc)
            elif res[0] == "resize":
                se._abort(doc)                  # resize opens its own step
                o.Placement = dr["placement"]
                se.resize(o, *res[1], at=res[2])     # one undo step
            elif res[0] == "turn":
                o.Placement = dr["placement"]
                se._abort(doc)
                if res[2]:
                    se.turn(o, res[1], res[2])
            else:
                se._done(doc)
        except se.EditRefused as exc:
            _log("drag refused: %s" % exc)
            o.Placement = dr["placement"]
        except Exception as exc:                       # noqa: BLE001
            _log("drag end: %r" % (exc,))
        # resize may replace the object (an oval cylinder becomes a solid)
        try:
            import FreeCADGui
            sel = FreeCADGui.Selection.getSelection()
            o = sel[0] if sel else o
        except Exception:                              # noqa: BLE001
            pass
        self.show(o)
        if self.on_change:
            self.on_change()


_ACTIVE = {}


def _active_view():
    try:
        import FreeCADGui
        return FreeCADGui.ActiveDocument.ActiveView
    except Exception:                                  # noqa: BLE001
        return None


def _same_view(a, b):
    """FreeCAD may wrap one view in a new Python object per call; its Qt
    widget (shiboken keeps one wrapper per QObject) tells them apart."""
    if a is b:
        return True
    try:
        return a.graphicsView() is b.graphicsView()
    except Exception:                                  # noqa: BLE001
        return False


def start(snap_step=lambda: DEFAULT_SNAP, on_change=None):
    """Handles on the active 3D view, following the selection (and the
    active view: refresh() moves them to another project's view). Returns
    the Handles, or None while no 3D view is open (stop() takes them off)."""
    stop()
    _ACTIVE["args"] = (snap_step, on_change)
    return _attach()


def _attach():
    view = _active_view()
    if view is None or not hasattr(view, "addEventCallbackPivy"):
        return None
    snap_step, on_change = _ACTIVE["args"]
    try:
        h = Handles(view, snap_step, on_change).attach()
    except Exception as exc:                           # noqa: BLE001
        _log("start: %r" % (exc,))
        return None
    _ACTIVE["h"] = h
    refresh()
    return h


def refresh():
    if "args" not in _ACTIVE:
        return
    h = _ACTIVE.get("h")
    if h is not None and h.drag is not None:
        return
    view = _active_view()
    if h is None or view is None or not _same_view(h.view, view):
        if h is not None:
            _ACTIVE.pop("h", None)
            h.detach()
        if view is None or _attach() is None:
            return
        return                                         # _attach refreshed
    try:
        import FreeCADGui
        sel = FreeCADGui.Selection.getSelection()
    except Exception:                                  # noqa: BLE001
        sel = []
    h.show(sel[0] if len(sel) == 1 else None)


def stop():
    _ACTIVE.pop("args", None)
    h = _ACTIVE.pop("h", None)
    if h is not None:
        h.detach()


def active():
    return _ACTIVE.get("h")
