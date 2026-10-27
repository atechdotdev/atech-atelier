"""shape_edit - hand editing of parts, TinkerCAD style (R800).

What a person does in TinkerCAD, on FreeCAD objects:

    add_shape(doc, kind)         a box, cylinder, sphere, cone, torus or roof
                                 (wedge), 20 mm, set down beside what is there
    size(obj) / resize(obj, w, d, h)
                                 the part's own width x depth x height (its
                                 bounding box before its placement), typed.
                                 It keeps its footprint centre and its bottom:
                                 it grows up and out, never into the floor.
    position(obj) / move_to(obj, x, y, z)
                                 x, y = the centre of its footprint, z = its
                                 bottom ("elevation"), in the document frame
    nudge(obj, dx, dy, dz)       arrow-key moves
    turn(obj, axis, degrees)     about its own centre
    set_hole(obj, on)            a hole is cut from the solids it is
                                 combined with (shown see-through, grey)
    combine(doc, objs)           solids fused, holes cut from them: FreeCAD's
                                 own Part::MultiFuse / Part::Cut, so the
                                 inputs stay editable under it in the tree
    ungroup(obj)                 back to the parts it was made of
    duplicate(obj)               a copy, set down beside it

How a resize is done depends on what the part is (kind()):

    box, cylinder, sphere, cone, torus, wedge
        FreeCAD's parametric primitives: their own numbers change (a box's
        Length/Width/Height, a cylinder's Radius/Height, ...). A size the
        shape cannot have (an oval cylinder, a stretched sphere) turns it
        into a plain solid scaled to that size, and says so.
    solid
        any other Part shape, imported STEP / IGES / BREP included: the
        shape itself is scaled (non-uniform scaling via transformGeometry).
    mesh
        STL / 3MF / OBJ: the mesh is scaled.
    agent
        a part the design agent built (AtechAgentBuilt). It is rebuilt from
        its script on the next turn, so a hand resize would silently come
        undone: its sizes are changed with Dimensions or in the chat.
        Moving, turning and colour are allowed (R340 keeps those).
    hardware
        the Atech board, a module, a cable or a library part: real
        hardware with real sizes. Not resized; modules are placed on the
        Atech modules page.

Every change is one undo step (one transaction). Nothing here touches the
GUI, so it runs (and is tested) under freecadcmd: tests/fc_shape_edit.py.
"""
import json
import math

GAP_MM = 10.0                 # space between a new shape and what is there
DEFAULT_MM = 20.0             # TinkerCAD's 20 mm shapes
MIN_MM = 0.1
HOLE_RGB = (0.62, 0.64, 0.70)
HOLE_TRANSPARENCY = 65

#: kind -> (FreeCAD type, label, default size settings)
SHAPES = {
    "box": ("Part::Box", "Box", {"Length": 20.0, "Width": 20.0, "Height": 20.0}),
    "cylinder": ("Part::Cylinder", "Cylinder", {"Radius": 10.0, "Height": 20.0}),
    "sphere": ("Part::Sphere", "Sphere", {"Radius": 10.0}),
    "cone": ("Part::Cone", "Cone", {"Radius1": 10.0, "Radius2": 0.0, "Height": 20.0}),
    "torus": ("Part::Torus", "Torus", {"Radius1": 8.0, "Radius2": 2.0}),
    "wedge": ("Part::Wedge", "Roof", {"Xmin": 0.0, "Ymin": 0.0, "Zmin": 0.0,
                                      "X2min": 0.0, "Z2min": 0.0,
                                      "Xmax": 20.0, "Ymax": 20.0, "Zmax": 20.0,
                                      "X2max": 20.0, "Z2max": 0.0}),
}
SHAPE_ORDER = ("box", "cylinder", "sphere", "cone", "torus", "wedge")
_TYPE_KIND = {t: k for k, (t, _l, _d) in SHAPES.items()}
HARDWARE_ROLES = ("board", "module", "part", "cable")
GROUP_TAG = "AtechHandGroup"


class EditRefused(ValueError):
    """A change this part does not take (why, in words for the user)."""


# ------------------------------------------------------------------ what it is
def kind(obj):
    """box / cylinder / sphere / cone / torus / wedge / solid / mesh /
    agent / hardware / group, or None for something with no shape."""
    if obj is None:
        return None
    if getattr(obj, "AtechRole", None) in HARDWARE_ROLES:
        return "hardware"
    if getattr(obj, "AtechAgentBuilt", False):
        return "agent"
    if getattr(obj, GROUP_TAG, False):
        return "group"
    k = _TYPE_KIND.get(getattr(obj, "TypeId", ""))
    if k:
        return k
    if hasattr(obj, "Mesh") and getattr(obj, "TypeId", "").startswith("Mesh::"):
        return "mesh"
    sh = getattr(obj, "Shape", None)
    if sh is not None and not sh.isNull():
        return "solid"
    return None


def can_resize(obj):
    return kind(obj) not in (None, "agent", "hardware")


def can_move(obj):
    return kind(obj) not in (None, "hardware")


def why_not(obj):
    """One sentence for the user when a part cannot be resized, else ""."""
    k = kind(obj)
    if k == "agent":
        return ("The design agent builds this part from its script, so a "
                "size typed here would come undone on its next build. Change "
                "it with Dimensions (D), or ask in the chat.")
    if k == "hardware":
        return ("This is real Atech hardware with fixed sizes. Place modules "
                "on the Atech modules page.")
    if k is None:
        return "This has no shape to edit."
    return ""


# ------------------------------------------------------------------ geometry
def _local(obj):
    """(shape-or-mesh copy at the identity placement, is_mesh)."""
    import FreeCAD
    if kind(obj) == "mesh":
        m = obj.Mesh.copy()
        m.Placement = FreeCAD.Placement()
        return m, True
    s = obj.Shape.copy()
    s.Placement = FreeCAD.Placement()
    return s, False


def _bbox(s):
    """The TIGHT bounding box. A shape scaled non-uniformly is a B-spline
    whose quick BoundBox follows its control points, not its surface
    (MEASURED: a 30 x 15 oval cylinder read 45 x 26), so a Part shape is
    measured with optimalBoundingBox(); a mesh's box is already its points."""
    f = getattr(s, "optimalBoundingBox", None)
    if f is not None:
        try:
            return f(True, False)
        except Exception:                              # noqa: BLE001
            pass
    return s.BoundBox


def size(obj):
    """(width x, depth y, height z) in mm: the part's own bounding box."""
    s, _m = _local(obj)
    bb = _bbox(s)
    return (bb.XLength, bb.YLength, bb.ZLength)


def _world_bbox(obj):
    if kind(obj) == "mesh":
        return obj.Mesh.BoundBox
    return _bbox(obj.Shape)


def position(obj):
    """(x, y, z): the centre of its footprint and its bottom, in the
    document frame."""
    bb = _world_bbox(obj)
    return ((bb.XMin + bb.XMax) / 2.0, (bb.YMin + bb.YMax) / 2.0, bb.ZMin)


def _txn(obj, name):
    doc = obj.Document
    doc.openTransaction(name)
    return doc


def _done(doc):
    doc.commitTransaction()
    doc.recompute()


def _abort(doc):
    try:
        doc.abortTransaction()
    except Exception:                                  # noqa: BLE001
        pass


def scale_matrix(fx, fy, fz, anchor):
    """FreeCAD Matrix scaling by (fx, fy, fz) about the point `anchor`."""
    import FreeCAD
    m = FreeCAD.Matrix()
    m.move(FreeCAD.Vector(-anchor[0], -anchor[1], -anchor[2]))
    s = FreeCAD.Matrix()
    s.scale(FreeCAD.Vector(fx, fy, fz))
    m = s.multiply(m)
    back = FreeCAD.Matrix()
    back.move(FreeCAD.Vector(*anchor))
    return back.multiply(m)


def factors(cur, want):
    """Per-axis scale factors from size `cur` to size `want` (an axis with
    no extent, a flat face, keeps factor 1)."""
    out = []
    for c, w in zip(cur, want):
        if w < MIN_MM:
            raise EditRefused("A size must be at least %.1f mm." % MIN_MM)
        out.append(1.0 if c < 1e-9 else float(w) / float(c))
    return tuple(out)


def _scaled_local(obj, want):
    """The part's local shape (or mesh) scaled to `want`, its footprint
    centre and bottom where they were."""
    s, is_mesh = _local(obj)
    bb = _bbox(s)
    f = factors((bb.XLength, bb.YLength, bb.ZLength), want)
    anchor = ((bb.XMin + bb.XMax) / 2.0, (bb.YMin + bb.YMax) / 2.0, bb.ZMin)
    m = scale_matrix(f[0], f[1], f[2], anchor)
    if is_mesh:
        s.transform(m)
        return s, True
    if abs(f[0] - f[1]) < 1e-12 and abs(f[1] - f[2]) < 1e-12:
        return s.transformShape(m, True) or s, False      # uniform: exact
    return s.transformGeometry(m), False                  # non-uniform


def _as_solid(obj, want, doc):
    """Replace parametric primitive `obj` by a plain Part::Feature of size
    `want` (the shape it cannot have parametrically). Returns the new
    object; the old one is removed."""
    import FreeCAD
    shape, _m = _scaled_local(obj, want)
    new = doc.addObject("Part::Feature", obj.Name + "_shape")
    new.Shape = shape
    new.Placement = FreeCAD.Placement(obj.Placement)
    new.Label = obj.Label
    _copy_view(obj, new)
    if getattr(obj, "AtechHole", False):
        _set_hole_prop(new, True)
    doc.removeObject(obj.Name)
    return new


def _copy_view(src, dst):
    for p in ("ShapeColor", "Transparency", "Visibility", "LineColor"):
        try:
            setattr(dst.ViewObject, p, getattr(src.ViewObject, p))
        except Exception:                              # noqa: BLE001
            pass


def resize(obj, w, d, h):
    """Set the part's width, depth and height (mm). Returns the object that
    now has that size (a new one when a primitive had to become a plain
    solid; see the module docstring). Raises EditRefused."""
    msg = why_not(obj)
    if msg:
        raise EditRefused(msg)
    want = (float(w), float(d), float(h))
    factors(size(obj), want)                      # validates the numbers
    k = kind(obj)
    doc = _txn(obj, "Resize %s" % obj.Label)
    try:
        base_before = position(obj)
        out = obj
        if k == "box":
            obj.Length, obj.Width, obj.Height = want
        elif k == "cylinder" and abs(want[0] - want[1]) < 1e-6:
            obj.Radius, obj.Height = want[0] / 2.0, want[2]
        elif k == "sphere" and abs(want[0] - want[1]) < 1e-6 \
                and abs(want[1] - want[2]) < 1e-6:
            obj.Radius = want[0] / 2.0
        elif k == "cone" and abs(want[0] - want[1]) < 1e-6:
            r1, r2 = float(obj.Radius1), float(obj.Radius2)
            big = max(r1, r2) or 1.0
            f = (want[0] / 2.0) / big
            obj.Radius1, obj.Radius2, obj.Height = r1 * f, r2 * f, want[2]
        elif k in ("solid", "group") or k == "mesh":
            shape, is_mesh = _scaled_local(obj, want)
            if is_mesh:
                pl = obj.Placement
                obj.Mesh = shape
                obj.Placement = pl
            elif k == "group":
                raise EditRefused("A combined group is resized by resizing "
                                  "its parts: ungroup it first.")
            else:
                pl = obj.Placement
                obj.Shape = shape
                obj.Placement = pl
        else:
            out = _as_solid(obj, want, doc)
        doc.recompute()
        # Keep its footprint centre and bottom where they were (a box grows
        # from its corner, a sphere from its centre).
        _shift_to(out, base_before)
    except Exception:
        _abort(doc)
        raise
    _done(doc)
    return out


def _shift_to(obj, target):
    import FreeCAD
    cur = position(obj)
    delta = FreeCAD.Vector(target[0] - cur[0], target[1] - cur[1], target[2] - cur[2])
    if delta.Length > 1e-9:
        obj.Placement.Base = obj.Placement.Base + delta


def move_to(obj, x, y, z):
    """Put the part's footprint centre at (x, y) and its bottom at z."""
    if not can_move(obj):
        raise EditRefused(why_not(obj))
    doc = _txn(obj, "Move %s" % obj.Label)
    try:
        _shift_to(obj, (float(x), float(y), float(z)))
    except Exception:
        _abort(doc)
        raise
    _done(doc)
    return obj


def nudge(obj, dx=0.0, dy=0.0, dz=0.0):
    x, y, z = position(obj)
    return move_to(obj, x + dx, y + dy, z + dz)


def turn(obj, axis, degrees):
    """Turn the part about its own centre. axis: "x", "y" or "z"."""
    import FreeCAD
    if not can_move(obj):
        raise EditRefused(why_not(obj))
    vec = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[axis.lower()]
    bb = _world_bbox(obj)
    bottom_before = bb.ZMin
    doc = _txn(obj, "Turn %s" % obj.Label)
    try:
        rot = FreeCAD.Placement(FreeCAD.Vector(), FreeCAD.Rotation(FreeCAD.Vector(*vec),
                                                                    float(degrees)),
                                bb.Center)
        obj.Placement = rot.multiply(obj.Placement)
        doc.recompute()
        if axis.lower() != "z":                 # a tilt keeps it on the floor
            x, y, _z = position(obj)
            _shift_to(obj, (x, y, bottom_before))
    except Exception:
        _abort(doc)
        raise
    _done(doc)
    return obj


# ------------------------------------------------------------------ holes
def is_hole(obj):
    return bool(getattr(obj, "AtechHole", False))


def _set_hole_prop(obj, on):
    if "AtechHole" not in obj.PropertiesList:
        obj.addProperty("App::PropertyBool", "AtechHole", "Atech",
                        "Cut from the solids it is combined with")
    obj.AtechHole = bool(on)
    vo = getattr(obj, "ViewObject", None)
    if vo is None:
        return
    try:
        if on:
            if "AtechSolidColor" not in obj.PropertiesList:
                obj.addProperty("App::PropertyString", "AtechSolidColor", "Atech",
                                "Colour before it became a hole")
            obj.AtechSolidColor = json.dumps(list(tuple(vo.ShapeColor)[:3])
                                             + [int(vo.Transparency)])
            vo.ShapeColor = HOLE_RGB
            vo.Transparency = HOLE_TRANSPARENCY
        else:
            saved = getattr(obj, "AtechSolidColor", "")
            if saved:
                r, g, b, t = json.loads(saved)
                vo.ShapeColor = (r, g, b)
                vo.Transparency = int(t)
            else:
                vo.Transparency = 0
    except Exception:                                  # noqa: BLE001
        pass


def set_hole(obj, on=True):
    if not can_resize(obj) and kind(obj) != "group":
        raise EditRefused(why_not(obj) or "This part cannot be a hole.")
    doc = _txn(obj, "%s %s" % ("Hole" if on else "Solid", obj.Label))
    try:
        _set_hole_prop(obj, on)
    except Exception:
        _abort(doc)
        raise
    _done(doc)
    return obj


# ------------------------------------------------------------------ groups
def combine(doc, objs):
    """Fuse the solids among `objs` and cut the holes from them. Returns the
    new group object (a Part::Cut or Part::MultiFuse, tagged)."""
    objs = [o for o in objs if o is not None]
    for o in objs:
        if kind(o) in (None, "hardware"):
            raise EditRefused("%s cannot be combined: %s" % (o.Label, why_not(o)))
    solids = [o for o in objs if not is_hole(o)]
    holes = [o for o in objs if is_hole(o)]
    if len(objs) < 2:
        raise EditRefused("Select two or more parts to combine.")
    if not solids:
        raise EditRefused("Combine needs at least one solid: these are all holes.")
    doc.openTransaction("Combine %d parts" % len(objs))
    try:
        if len(solids) == 1:
            base = solids[0]
        else:
            base = doc.addObject("Part::MultiFuse", "Combined")
            base.Shapes = solids
            base.Refine = True
        result = base
        if holes:
            if len(holes) == 1:
                tool = holes[0]
            else:
                tool = doc.addObject("Part::MultiFuse", "Holes")
                tool.Shapes = holes
            result = doc.addObject("Part::Cut", "Combined")
            result.Base = base
            result.Tool = tool
            result.Refine = True
        result.addProperty("App::PropertyBool", GROUP_TAG, "Atech",
                           "Made with Combine; Ungroup takes it apart")
        setattr(result, GROUP_TAG, True)
        result.Label = "Group"
        doc.recompute()
        for o in objs:
            try:
                o.ViewObject.Visibility = False
            except Exception:                          # noqa: BLE001
                pass
        if result.Shape.isNull() or not result.Shape.isValid():
            raise EditRefused("The parts could not be combined into a valid solid.")
    except Exception:
        _abort(doc)
        raise
    doc.commitTransaction()
    return result


def _inputs(obj):
    out = []
    for p in ("Base", "Tool"):
        v = getattr(obj, p, None)
        if v is not None:
            out.append(v)
    out += list(getattr(obj, "Shapes", []) or [])
    return out


def ungroup(obj):
    """Undo combine(): the inputs come back, the group goes. Returns them."""
    if not getattr(obj, GROUP_TAG, False):
        raise EditRefused("This is not a combined group.")
    doc = obj.Document
    doc.openTransaction("Ungroup %s" % obj.Label)
    try:
        parts, todo, helpers = [], [obj], []
        while todo:
            o = todo.pop()
            for i in _inputs(o):
                if i.TypeId == "Part::MultiFuse" and not getattr(i, GROUP_TAG, False) \
                        and i.Name.startswith(("Combined", "Holes")):
                    helpers.append(i)
                    todo.append(i)
                else:
                    parts.append(i)
        names = [obj.Name] + [h.Name for h in helpers]
        for n in names:
            doc.removeObject(n)
        for p in parts:
            try:
                p.ViewObject.Visibility = True
            except Exception:                          # noqa: BLE001
                pass
        doc.recompute()
    except Exception:
        _abort(doc)
        raise
    doc.commitTransaction()
    return parts


# ------------------------------------------------------------------ new parts
def _beside(objs, width):
    """Where a new part goes: right of everything visible, on the floor."""
    xmax = None
    for o in objs:
        try:
            if not getattr(o.ViewObject, "Visibility", True):
                continue
        except Exception:                              # noqa: BLE001
            pass
        sh = getattr(o, "Shape", None)
        if sh is None or sh.isNull():
            continue
        bb = sh.BoundBox
        if bb.isValid():
            xmax = bb.XMax if xmax is None else max(xmax, bb.XMax)
    x = 0.0 if xmax is None else xmax + GAP_MM + width / 2.0
    return (x, 0.0, 0.0)


def add_shape(doc, shape_kind):
    """A new 20 mm shape beside what is there, standing on the floor."""
    if shape_kind not in SHAPES:
        raise EditRefused("Unknown shape %r." % shape_kind)
    type_id, label, props = SHAPES[shape_kind]
    doc.openTransaction("Add %s" % label)
    try:
        o = doc.addObject(type_id, label)
        for k, v in props.items():
            setattr(o, k, v)
        o.Label = label
        doc.recompute()
        w, _d, _h = size(o)
        _shift_to(o, _beside([x for x in doc.Objects if x is not o], w))
        doc.recompute()
    except Exception:
        _abort(doc)
        raise
    doc.commitTransaction()
    return o


def duplicate(obj):
    """A copy of the part, set down to its right."""
    if not can_move(obj) or kind(obj) == "agent":
        raise EditRefused(why_not(obj) or "This part cannot be copied.")
    doc = obj.Document
    doc.openTransaction("Duplicate %s" % obj.Label)
    try:
        new = doc.copyObject(obj, False)
        new.Label = obj.Label + " copy"
        _copy_view(obj, new)
        if is_hole(obj):
            _set_hole_prop(new, True)
        doc.recompute()
        w, _d, _h = size(obj)
        x, y, z = position(obj)
        _shift_to(new, (x + w + GAP_MM / 2.0, y, z))
    except Exception:
        _abort(doc)
        raise
    doc.commitTransaction()
    doc.recompute()
    return new


def remove(obj):
    if kind(obj) in ("hardware",):
        raise EditRefused(why_not(obj))
    doc = obj.Document
    doc.openTransaction("Delete %s" % obj.Label)
    try:
        doc.removeObject(obj.Name)
    except Exception:
        _abort(doc)
        raise
    doc.commitTransaction()


def fmt_mm(v):
    """12.0 -> "12", 12.25 -> "12.25" (no trailing zeros)."""
    s = "%.2f" % float(v)
    return s.rstrip("0").rstrip(".") if "." in s else s


def same_ratio(old, new_axis, new_value):
    """Lock proportions: the full size when axis `new_axis` (0/1/2) becomes
    `new_value` and the other two follow."""
    base = old[new_axis] or 1.0
    f = float(new_value) / float(base)
    return tuple(v * f if i != new_axis else float(new_value)
                 for i, v in enumerate(old))


def angle_ok(deg):
    return math.isfinite(float(deg))
