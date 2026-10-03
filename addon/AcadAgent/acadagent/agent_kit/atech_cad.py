"""atech_cad - small, checked CAD helpers for model.py scripts.

    import atech_cad as cad

Every helper CHECKS ITS OWN RESULT and raises CadError with a message that
says what went wrong and what to change. None of them returns a shape that
merely looks fine. The FreeCAD traps each one closes:

    fuse_one        a fuse of parts that do not touch gives TWO solids while
                    isValid() still says True. fuse_one raises instead.
    fillet_safe     makeFillet on the wrong edges throws, or returns a broken
                    solid that still reports isValid(). fillet_safe returns
                    a SHAPE: the filleted one, or on failure the ORIGINAL
                    unchanged (the reason is printed and kept in
                    cad.last_reason()), never a wreck.
    hole & co.      the drilling direction is an explicit argument (`axis`
                    points INTO the material), never guessed from a bbox.
                    A hole that removes nothing raises. through="wall"
                    stops at the first exit from material: one wall of a
                    hollow case, not the wall behind it too (R181).
    shell           makeThickness + a check that the part really got hollow.
    wedge           a ramp / fin / frustum with NAMED sizes: Part.makeWedge
                    takes 10 bare numbers in an order that is easy to get
                    wrong (S60).
    measure         Shape.BoundBox is a loose BOUND on curved parts;
                    measure() uses optimalBoundingBox, which is tight.
    spur_gear       real involute teeth from FreeCAD's bundled fcgear
                    generator, checked (one valid solid, tip diameter).
    snap_fit_pair   matched hooks on a lid and catch windows through its
                    case's walls from ONE list of positions, every face
                    measured (S61): case, lid = cad.snap_fit_pair(case, lid)
    pin_hinge       alternating knuckles + one pin bore on an assembled
                    box/lid pair, the axis ON the back face, swept clear
                    before it returns; with the intent.json "motion" entry
                    (S65): box, lid, motion = cad.pin_hinge(box, lid)
    socket_opening  a plug opening through the wall in front of a seated
                    module's socket mouth - direction and size MEASURED
                    from the module (S66): lid = cad.socket_opening(lid, usb)
    bound_of        one world box around shapes AND seated Atech parts
                    (Mesh features have no .Shape).
    place_on        a lid seated ON its box (measured), not floating above
                    it - the assembled product is what intent.json sizes.

Conventions: millimetres and degrees. Points and directions may be tuples or
FreeCAD Vectors. Shapes are Part.Shape objects; add the final one to the
document yourself:  doc.addObject("Part::Feature", "Name").Shape = shape
"""
import math
import numbers

import FreeCAD as App
import Part

__all__ = [
    "CadError", "V", "measure", "fuse_one", "cut", "fillet_safe",
    "chamfer_safe", "edges_parallel", "faces_at", "rounded_box", "shell",
    "hole", "counterbore", "countersink", "linear_pattern", "polar_pattern",
    "revolve", "snap_fit_cantilever", "snap_fit_pair", "cantilever_strain",
    "last_reason",
    "spur_gear", "gear_shift_for", "bound_of", "place_on", "wedge",
    "pin_hinge", "socket_opening",
]

TOL = 1e-6          # volumes below this (mm^3) are "nothing"
BACK = 0.5          # cutters start this far OUTSIDE the entry face (mm), so
                    # no cut is ever coplanar with the face it enters


class CadError(ValueError):
    """A helper refused to return a bad shape. The message says why."""


def V(p):
    """Tuple / list / Vector -> FreeCAD.Vector."""
    if isinstance(p, App.Vector):
        return App.Vector(p)
    x, y, z = (list(p) + [0, 0, 0])[:3]
    return App.Vector(float(x), float(y), float(z))


_AXES = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}


def _dir(d, what="axis"):
    """A unit direction from a tuple, a Vector, or '+X' / '-z' / 'Y'."""
    if isinstance(d, str):
        s = d.strip().lower()
        sign = -1.0 if s.startswith("-") else 1.0
        key = s.lstrip("+-")
        if key not in _AXES:
            raise CadError("%s %r: use '+X', '-Y', 'Z' ... or a vector" % (what, d))
        v = V(_AXES[key]) * sign
    else:
        v = V(d)
    if v.Length < 1e-12:
        raise CadError("%s is a zero vector" % what)
    v.normalize()
    return v


def _check(shape, what, solids=None):
    """Raise unless `shape` is a non-null, valid shape (with `solids` solids)."""
    if shape is None or shape.isNull():
        raise CadError("%s: produced an empty shape" % what)
    if not shape.isValid():
        raise CadError("%s: produced an INVALID shape (shape.isValid() is False)"
                       % what)
    if solids is not None and len(shape.Solids) != solids:
        raise CadError("%s: expected %d solid(s), got %d"
                       % (what, solids, len(shape.Solids)))
    return shape


def _one(shape):
    """A shape holding exactly one solid -> that Solid (no compound wrapper)."""
    return shape.Solids[0] if len(shape.Solids) == 1 else shape


def _flat(shapes):
    out = []
    for s in shapes:
        if isinstance(s, (list, tuple)):
            out.extend(_flat(s))
        else:
            out.append(s)
    return out


def _tight_bbox(shape):
    try:
        return shape.optimalBoundingBox(True, False)
    except Exception:                                   # noqa: BLE001
        return shape.BoundBox


# --------------------------------------------------------------- measuring
def measure(shape):
    """Measured facts about a shape (a plain dict, tight bbox). Never raises.

    bbox is optimalBoundingBox (tight to the geometry), axis-aligned.
    """
    out = {"valid": None, "solids": None, "volume_mm3": None, "area_mm2": None,
           "bbox_min": None, "bbox_max": None, "size": None,
           "center_of_mass": None, "error": None}
    try:
        out["valid"] = bool(shape.isValid())
        out["solids"] = len(shape.Solids)
        out["volume_mm3"] = round(shape.Volume, 4)
        out["area_mm2"] = round(shape.Area, 4)
        bb = _tight_bbox(shape)
        out["bbox_min"] = [round(bb.XMin, 4), round(bb.YMin, 4), round(bb.ZMin, 4)]
        out["bbox_max"] = [round(bb.XMax, 4), round(bb.YMax, 4), round(bb.ZMax, 4)]
        out["size"] = [round(bb.XLength, 4), round(bb.YLength, 4), round(bb.ZLength, 4)]
        if shape.Solids:
            c = (shape.Solids[0].CenterOfMass if len(shape.Solids) == 1
                 else Part.makeCompound(shape.Solids).CenterOfMass)
            out["center_of_mass"] = [round(c.x, 4), round(c.y, 4), round(c.z, 4)]
    except Exception as exc:                            # noqa: BLE001
        out["error"] = "%s: %s" % (type(exc).__name__, exc)
    return out


# ---------------------------------------------------------------- booleans
def fuse_one(*shapes):
    """Fuse shapes that must become ONE body. Raises unless exactly 1 solid.

    fuse_one(a, b, c) or fuse_one([a, b, c]). Parts must overlap (share
    volume), not merely touch: give joints >= 0.1 mm of overlap.
    """
    parts = _flat(shapes)
    if not parts:
        raise CadError("fuse_one: no shapes given")
    for i, p in enumerate(parts):
        _check(p, "fuse_one: input %d" % i)
        if not p.Solids:
            raise CadError("fuse_one: input %d has no solid (a face or wire?)" % i)
    res = parts[0] if len(parts) == 1 else parts[0].fuse(parts[1:])
    try:
        res = res.removeSplitter()
    except Exception:                                   # noqa: BLE001
        pass
    if res.isNull() or not res.isValid():
        raise CadError(
            "fuse_one: the fused result is INVALID - almost always two faces "
            "that exactly touch (a fin starting exactly on a tube's radius, a "
            "block flush with a face). Overlap every joint by >= 0.5 mm: start "
            "the fin 0.5 mm inside the tube wall, sink the block 0.5 mm in.")
    n = len(res.Solids)
    if n != 1:
        raise CadError(
            "fuse_one: the result has %d separate solids, not 1 - some parts do "
            "not overlap (touching is not enough). Move or lengthen them so each "
            "joint overlaps by >= 0.1 mm, or keep them as separate objects if "
            "they really are separate parts. Cutting tools are never fused: "
            "pass the list to cad.cut(body, tools)." % n)
    return res.Solids[0]


def cut(shape, *tools):
    """shape minus tools (several, or a list: one boolean), checked valid and
    that something was actually removed.
    cut(body, t1, t2) or cut(body, [t1, t2, ...]): disjoint cutters are fine
    here (never fuse_one them first)."""
    tl = _flat(tools)
    if not tl:
        raise CadError("cut: no tools given")
    v0 = shape.Volume
    res = shape.cut(tl if len(tl) > 1 else tl[0])
    _check(res, "cut")
    if v0 - res.Volume <= TOL:
        raise CadError("cut: the tools removed nothing - they do not overlap the "
                       "shape. Check their positions.")
    if not res.Solids:
        raise CadError("cut: the tools removed the whole shape")
    stray = _stray(res, shape)
    if stray:
        raise CadError(
            "cut: the tools cut a stray %.1f mm3 sliver off the %.1f mm3 body "
            "(%d solids now, %d before) - a cutter that stops just short of a "
            "face or clips an edge. Make each cutter pass fully through, or "
            "keep it clear of the face by >= 0.5 mm." % (
                stray[0], stray[1], len(res.Solids), len(shape.Solids)))
    return _one(res)


def _parent(piece, inputs):
    """Index of the input solid a cut result solid came from: the one whose
    box holds the piece's box, and - when several do - whose volume holds
    the piece's (a cut only removes material, so each piece lies inside
    exactly one input solid). None when it cannot be told."""
    pb = piece.BoundBox
    cands = []
    for k, s in enumerate(inputs):
        sb = s.BoundBox
        if (sb.XMin - 1e-6 <= pb.XMin and pb.XMax <= sb.XMax + 1e-6
                and sb.YMin - 1e-6 <= pb.YMin and pb.YMax <= sb.YMax + 1e-6
                and sb.ZMin - 1e-6 <= pb.ZMin and pb.ZMax <= sb.ZMax + 1e-6):
            cands.append(k)
    if len(cands) == 1:
        return cands[0]
    for k in cands:
        try:
            if piece.common(inputs[k]).Volume >= 0.5 * piece.Volume:
                return k
        except Exception:                               # noqa: BLE001
            continue
    return None


def _stray(res, shape, ratio=0.10):
    """(small, big) volumes when a cut split one of `shape`'s solids and one
    of the pieces is disjoint from its siblings and under `ratio` x the
    largest of them - the stray fragment Studio fails a build for (S40: a
    toy car's wheel-arch cut left a 254 mm3 solid). A cut that splits a
    bar into two real pieces is not stray.

    Judged per INPUT solid (R135): a small disjoint solid the shape already
    held (a separate pin beside a plate) is not a sliver this cut made,
    even when the same cut splits something else. None otherwise."""
    inputs = list(shape.Solids)
    solids = list(res.Solids)
    if len(solids) <= len(inputs) or len(solids) > 50:
        return None
    groups = {}
    for piece in solids:
        k = _parent(piece, inputs) if len(inputs) > 1 else 0
        if k is None:
            return None                     # cannot tell -> do not accuse
        groups.setdefault(k, []).append(piece)
    for pieces in groups.values():
        if len(pieces) < 2:
            continue
        vols = [x.Volume for x in pieces]
        big = max(vols)
        i = min(range(len(vols)), key=lambda k: vols[k])
        if big <= 0 or vols[i] >= ratio * big:
            continue
        apart = True
        for j, other in enumerate(pieces):
            if j == i:
                continue
            try:
                if pieces[i].distToShape(other)[0] <= 1e-6:
                    apart = False           # touching: part of the body
                    break
            except Exception:                           # noqa: BLE001
                apart = False               # cannot tell -> do not accuse
                break
        if apart:
            return vols[i], big
    return None


# ----------------------------------------------------------- edge / face picks
def edges_parallel(shape, axis):
    """Straight edges of `shape` parallel to axis ('Z', '+X', (1,0,0) ...)."""
    a = _dir(axis)
    out = []
    for e in shape.Edges:
        if not isinstance(e.Curve, Part.Line):
            continue
        d = e.Vertexes[-1].Point - e.Vertexes[0].Point
        if d.Length > 1e-9 and abs(abs(d.normalize().dot(a)) - 1.0) < 1e-6:
            out.append(e)
    return out


def faces_at(shape, direction):
    """Planar faces whose outward normal is `direction` and that lie at the
    extreme of the part in that direction. faces_at(box, '+Z') -> the top."""
    d = _dir(direction, "direction")
    cands = []
    for f in shape.Faces:
        if not isinstance(f.Surface, Part.Plane):
            continue
        u0, u1, v0, v1 = f.ParameterRange
        n = f.normalAt(0.5 * (u0 + u1), 0.5 * (v0 + v1))
        if n.dot(d) > 1 - 1e-6:
            cands.append((f.CenterOfMass.dot(d), f))
    if not cands:
        return []
    top = max(c[0] for c in cands)
    return [f for h, f in cands if abs(h - top) < 1e-6]


def _pick_edges(shape, edges):
    if edges is None:
        return list(shape.Edges)
    if callable(edges):
        return [e for e in shape.Edges if edges(e)]
    out = []
    for e in edges:
        out.append(shape.Edges[e] if isinstance(e, int) else e)
    return out


# ---------------------------------------------------------- fillet / chamfer
def _round_edges(kind, shape, r, edges):
    what = "%s_safe(r=%g)" % (kind, r)
    try:
        es = _pick_edges(shape, edges)
        if not es:
            return shape, "%s: no edges selected" % what
        if r <= 0:
            return shape, "%s: radius must be > 0" % what
        res = (shape.makeFillet(r, es) if kind == "fillet"
               else shape.makeChamfer(r, es))
        if res.isNull() or not res.isValid():
            return shape, "%s: result was invalid - radius too large for the " \
                          "edges or faces it meets" % what
        if len(res.Solids) != len(shape.Solids):
            return shape, "%s: solid count changed %d -> %d" % (
                what, len(shape.Solids), len(res.Solids))
        if res.Volume <= TOL or abs(res.Volume - shape.Volume) > 0.5 * shape.Volume:
            return shape, "%s: volume went %.1f -> %.1f mm3, not a fillet" % (
                what, shape.Volume, res.Volume)
        return _one(res), None
    except Exception as exc:                            # noqa: BLE001
        return shape, "%s failed: %s" % (what, " ".join(str(exc).split()) or
                                         type(exc).__name__)


_LAST_REASON = [None]


def last_reason():
    """Why the last fillet_safe / chamfer_safe left the shape unchanged, or
    None when it succeeded."""
    return _LAST_REASON[0]


def _edge_args(kind, r, edges):
    """Accept (r, edges) and the swapped (edges, r) order: a number is the
    size, a list / function / None is the edge selection."""
    def num(x):
        # numbers.Real, not (int, float): a numpy int64 radius (a size taken
        # from an array) is a number too (R114); a bool is not a size.
        return isinstance(x, numbers.Real) and not isinstance(x, bool)
    if not num(r) and num(edges):
        r, edges = edges, r
    if not num(r):
        raise CadError("%s_safe(shape, r, edges=None): r must be a number, got "
                       "%s" % (kind, type(r).__name__))
    return float(r), edges


def _safe(kind, shape, r, edges, why):
    r, edges = _edge_args(kind, r, edges)
    res, reason = _round_edges(kind, shape, r, edges)
    _LAST_REASON[0] = reason
    if isinstance(why, list):
        why.append(reason)
    if reason:
        print("%s (the shape was kept unchanged)" % reason)
    return res


def fillet_safe(shape, r, edges=None, why=None):
    """Fillet `edges` (None = all; a list of Edges or indices; or a function
    edge -> bool) with radius r. Returns a SHAPE - never a tuple:

        body = cad.fillet_safe(body, 2, cad.edges_parallel(body, "Z"))

    On failure it returns the ORIGINAL shape unchanged, prints why, and
    keeps the reason in cad.last_reason() (None after a success); pass
    why=[] to have it appended there too."""
    return _safe("fillet", shape, r, edges, why)


def chamfer_safe(shape, d, edges=None, why=None):
    """Like fillet_safe, with an equal-distance chamfer `d`. Returns a shape."""
    return _safe("chamfer", shape, d, edges, why)


# ------------------------------------------------------------- primitives
_EDGE_AXIS = {"vertical": "z", "x": "x", "y": "y", "z": "z"}


def rounded_box(x, y, z, r, at=(0, 0, 0), edges="vertical"):
    """A box x*y*z with its CORNER at `at` (like Part.makeBox), its edges
    rounded to radius r.

    LIMIT (S56): r < half the shorter of the two sides ACROSS the rounded
    edges - r = half that side exactly gives full round ends (an obround
    slot; a cylinder when the two sides are equal). A larger r raises and
    names the side that limits it; r is never clamped for you.

    edges  'vertical' (= 'z', the 4 upright edges: limited by x and y),
           'x' / 'y' (the 4 edges along that axis: a plate standing on
           its edge, rounded on its big face, is edges='y' when y is its
           thickness), or 'all' (all 12, limited by x, y and z; r=0: a
           plain box)."""
    if min(x, y, z) <= 0:
        raise CadError("rounded_box: sizes must be > 0, got %g x %g x %g" % (x, y, z))
    key = edges.strip().lower().lstrip("+-") if isinstance(edges, str) else edges
    if key not in _EDGE_AXIS and key != "all":
        raise CadError("rounded_box: edges must be 'vertical', 'x', 'y', 'z' or 'all', "
                       "got %r (for other edges use fillet_safe)" % (edges,))
    try:
        r = float(r)
    except (TypeError, ValueError):
        raise CadError("rounded_box(x, y, z, r): r must be a number (mm), got %r"
                       % (r,))
    size = {"x": float(x), "y": float(y), "z": float(z)}
    axis = _EDGE_AXIS.get(key)
    sides = {k: v for k, v in size.items() if k != axis}
    short = min(sides, key=sides.get)
    lim = sides[short] / 2.0
    if not r >= 0:
        raise CadError("rounded_box: r=%g must be >= 0 (r=0 is a plain box). "
                       "Nothing was built" % r)
    if axis and r > 0 and abs(r - lim) <= 1e-9 * max(1.0, lim):
        # r = exactly half the short side: full round ends, which a fillet
        # cannot make (the two rounds would meet in a zero-width face) -
        # built directly instead (S56: a slot cutter SLOT_W / 2)
        return _obround(size, axis, short, r, V(at))
    if r >= lim:
        # S48: say which side limits r and the ways out - never clamp r
        # silently (a smaller radius than asked is a changed design, P1)
        ways = "use r=%g or less, or make %s longer than %g mm" % (
            math.floor(lim * 10 - 1e-9) / 10.0, short, 2 * r)
        if axis:
            ways += " (r = exactly %g gives full round ends)" % lim
        if key == "all" and short == "z" and min(x, y) / 2.0 > r:
            ways += (", or edges='vertical' (rounds only the 4 upright edges, "
                     "so z does not limit r)")
        other = [k for k in ("x", "y", "z") if k != axis and key != "all"
                 and min(v for kk, v in size.items() if kk != k) / 2.0 > r]
        if other:
            ways += ", or edges=%s (the 4 edges along %s, limited by %s)" % (
                " / ".join("'%s'" % k for k in other), " / ".join(other),
                " and ".join("%s = %g" % (kk, size[kk]) for kk in size if kk != other[0]))
        what = ("the 12 edges, limited by x, y and z" if key == "all" else
                "the 4 upright edges, limited by x and y" if key == "vertical" else
                "the 4 edges along %s, limited by %s" % (
                    axis, " and ".join(k for k in size if k != axis)))
        raise CadError(
            "rounded_box(%g, %g, %g, r=%g, edges=%r): r=%g must be < %g - half the "
            "shortest rounded side (%s = %g mm; edges=%r rounds %s). Nothing "
            "was built (r is never clamped for you): %s"
            % (x, y, z, r, edges, r, lim, short, sides[short], edges, what, ways))
    b = Part.makeBox(x, y, z, V(at))
    if r == 0:
        return b
    sel = None if key == "all" else edges_parallel(b, axis.upper())
    res, why = _round_edges("fillet", b, float(r), sel)
    if why:
        raise CadError("rounded_box: " + why)
    return _check(res, "rounded_box", solids=1)


def _obround(size, axis, short, r, at):
    """rounded_box with r = half the short side: a box between two
    cylinders along `axis` (one cylinder when the sides are equal)."""
    idx = {"x": 0, "y": 1, "z": 2}
    unit = [V((1, 0, 0)), V((0, 1, 0)), V((0, 0, 1))]
    ia, ish = idx[axis], idx[short]
    il = 3 - ia - ish
    long_ = [size["x"], size["y"], size["z"]][il]
    h = [size["x"], size["y"], size["z"]][ia]
    base = at + unit[ish] * r
    parts = [Part.makeCylinder(r, h, base + unit[il] * r, unit[ia])]
    if long_ - 2 * r > 1e-9:
        parts.append(Part.makeCylinder(r, h, base + unit[il] * (long_ - r), unit[ia]))
        dims = [0.0, 0.0, 0.0]
        dims[ia], dims[ish], dims[il] = h, 2 * r, long_ - 2 * r
        parts.append(Part.makeBox(dims[0], dims[1], dims[2], at + unit[il] * r))
        res = parts[0].fuse(parts[1:]).removeSplitter()
    else:
        res = parts[0]
    _check(res, "rounded_box (full round ends)", solids=1)
    return _one(res)


def wedge(x, y, z, top_x=0.0, top_y=None, at=(0, 0, 0), top_at=None):
    """A ramp, fin or frustum with NAMED sizes: bottom x*y (corner at `at`), top top_x*top_y at height z - not makeWedge's 10 bare numbers.

    x, y       the bottom face's size (mm), lying in the XY plane at at.z
    z          the height, along +Z
    top_x      the top face's size along X; 0 = a sharp ridge along Y
               (a ramp or a triangular fin)
    top_y      the top face's size along Y (default y: tapers in X only;
               0 = a ridge along X; top_x = top_y = 0 = a pyramid's apex)
    top_at     (dx, dy) of the top face's corner from the bottom corner;
               default centred: ((x - top_x) / 2, (y - top_y) / 2). A fin
               with a vertical back edge: top_at=(0, 0) with top_x=0.

    Rotate the result for another axis. Volume (a prismatoid):
    z / 6 * (x*y + 4 * (x+top_x)/2 * (y+top_y)/2 + top_x*top_y)."""
    try:
        x, y, z = float(x), float(y), float(z)
        tx = float(top_x)
        ty = y if top_y is None else float(top_y)
    except (TypeError, ValueError):
        raise CadError("wedge(x, y, z, top_x=0, top_y=None, at=(0, 0, 0), top_at=None): "
                       "sizes must be numbers (mm), got x=%r y=%r z=%r top_x=%r top_y=%r"
                       % (x, y, z, top_x, top_y))
    if min(x, y, z) <= 0:
        raise CadError("wedge: x, y and z must be > 0, got %g x %g x %g" % (x, y, z))
    if tx < 0 or ty < 0:
        raise CadError("wedge: top_x and top_y must be >= 0 (0 = a sharp edge), "
                       "got %g, %g" % (tx, ty))
    if top_at is None:
        dx, dy = (x - tx) / 2.0, (y - ty) / 2.0
    else:
        try:
            dx, dy = float(top_at[0]), float(top_at[1])
        except (TypeError, ValueError, IndexError):
            raise CadError("wedge: top_at must be (dx, dy), got %r" % (top_at,))
    # Part.makeWedge builds along ITS Y: xmin, ymin, zmin, z2min, x2min,
    # xmax, ymax, zmax, z2max, x2max. Its Y is our height and its Z our
    # -Y (rotated +90 deg about X below), so our Y range [a, b] is its
    # Z range [y - b, y - a].
    try:
        w = Part.makeWedge(0.0, 0.0, 0.0, y - (dy + ty), dx, x, z, y, y - dy, dx + tx)
    except Exception as exc:                            # noqa: BLE001
        raise CadError("wedge(%g, %g, %g, top_x=%g, top_y=%g): Part.makeWedge "
                       "refused it (%s)" % (x, y, z, tx, ty, exc))
    w.rotate(App.Vector(0, 0, 0), App.Vector(1, 0, 0), 90.0)
    w.translate(V(at) + App.Vector(0, y, 0))
    _check(w, "wedge", solids=1)
    want = z / 6.0 * (x * y + (x + tx) * (y + ty) + tx * ty)
    if abs(w.Volume - want) > 1e-6 * max(1.0, want):
        raise CadError("wedge: built %.4f mm3 where the sizes give %.4f mm3 - "
                       "nothing returned" % (w.Volume, want))
    return _one(w)


def revolve(points_xz, angle=360.0):
    """Revolve a closed profile about the Z axis.

    points_xz: [(radius, z), ...] in order around the outline (x = radius,
    must be >= 0; the profile is closed automatically). A lathe part.
    """
    pts = [V((p[0], 0, p[1])) for p in points_xz]
    if len(pts) < 3:
        raise CadError("revolve: need at least 3 profile points")
    if any(p.x < -1e-9 for p in pts):
        raise CadError("revolve: every x (radius) must be >= 0; the profile "
                       "may not cross the Z axis")
    if (pts[0] - pts[-1]).Length > 1e-9:
        pts.append(pts[0])
    try:
        face = Part.Face(Part.makePolygon(pts))
    except Exception as exc:                            # noqa: BLE001
        raise CadError("revolve: profile is not a simple closed outline (%s)" % exc)
    if face.Area <= TOL:
        raise CadError("revolve: profile has zero area")
    res = face.revolve(V((0, 0, 0)), V((0, 0, 1)), float(angle))
    if res.ShapeType == "Shell" or not res.Solids:
        try:
            res = Part.Solid(res)
        except Exception:                               # noqa: BLE001
            pass
    try:
        res = res.removeSplitter()
    except Exception:                                   # noqa: BLE001
        pass
    _check(res, "revolve", solids=1)
    return _one(res)


def shell(shape, t, open_faces=(), inward=True):
    """Hollow a solid to wall thickness t.

    LIMIT (S56): inward, t must be < half the part's size across each axis
    (walls from both sides would meet), or < the whole size along an axis
    that has an open face (only the floor is left there). A t at or over
    that raises and names the axis; t is never reduced for you.

    open_faces: faces to remove (the opening) - e.g. cad.faces_at(body,'+Z')
    for an open-top box. Empty = a closed hollow part (sealed cavity).
    inward=True keeps the outside size; False grows the part outward.
    """
    if t <= 0:
        raise CadError("shell: thickness must be > 0")
    _check(shape, "shell: input", solids=1)
    v0 = shape.Volume
    faces = list(open_faces)
    if inward:
        _shell_limit(shape, t, faces)
    res, why = None, None
    try:
        if faces:
            res = shape.makeThickness(faces, -t if inward else t, 1e-3,
                                      False, False, 0, 2)
        else:
            if not inward:
                raise CadError("shell: a closed shell (no open faces) is inward only")
            res = shape.cut(shape.makeOffsetShape(-t, 1e-3, False, False, 0, 2))
    except CadError:
        raise
    except Exception as exc:                            # noqa: BLE001
        why = " ".join(str(exc).split()) or type(exc).__name__
    ok = (why is None and res is not None and not res.isNull() and res.isValid()
          and len(res.Solids) == 1)
    if ok and inward and not (TOL < res.Volume < v0 - TOL):
        # MEASURED S44: makeThickness hands the input back UNCHANGED (valid,
        # same volume) when an opened face meets a rounded edge - every
        # rounded_box opened on +-X or +-Y; opened on +-Z with r == t it
        # throws. The Atech cases (open X ends) hit this 3 times in 4.
        ok, why = False, "makeThickness returned the part unchanged"
    if not ok and inward and faces:
        res = _shell_by_core(shape, t, faces, why)
    elif not ok:
        raise CadError("shell: FreeCAD could not hollow this shape at t=%g (%s). "
                       "A thinner wall, fewer fillets, or building the cavity as "
                       "a separate cut usually works." % (t, why or "invalid result"))
    _check(res, "shell(t=%g)" % t, solids=1)
    vol = res.Volume
    if inward and not (TOL < vol < v0 - TOL):
        raise CadError("shell: volume %.1f -> %.1f mm3 - the part did not get "
                       "hollow" % (v0, vol))
    if not inward and vol <= TOL:
        raise CadError("shell: empty result")
    return _one(res)


def _shell_limit(shape, t, faces):
    """Raise when an inward wall t cannot fit the part (see shell())."""
    bb = _tight_bbox(shape)
    size = (bb.XLength, bb.YLength, bb.ZLength)
    opened = set()
    for f in faces:
        try:
            n = _mid_normal(f)
        except Exception:                               # noqa: BLE001
            continue
        k = max(range(3), key=lambda i: abs((n.x, n.y, n.z)[i]))
        if abs((n.x, n.y, n.z)[k]) > 1 - 1e-6:
            opened.add(k)
    lims = [(size[k] if k in opened else size[k] / 2.0, k) for k in range(3)]
    lim, k = min(lims)
    if t >= lim - 1e-9:
        raise CadError(
            "shell(t=%g): t must be < %g - %s the part's %s size (%s = %.4g mm%s). "
            "Nothing was built (t is never reduced for you): use t=%g or less, or "
            "make the part bigger along %s" % (
                t, round(lim, 4), "all of" if k in opened else "half",
                "XYZ"[k], "xyz"[k], size[k],
                ", open on that axis: only the floor is left" if k in opened
                else ": the walls from both sides would meet",
                math.floor(lim * 10 - 1e-9) / 10.0, "XYZ"[k]))


def _shell_by_core(shape, t, faces, why):
    """The fallback when makeThickness fails: cut away an inward offset
    CORE of the part (every wall t thick) plus, for each open face, the
    core's faces toward that opening extruded out through it.

    Checked, not assumed: the cut may remove only the core and the wall
    BEHIND the open faces - at most t x their area. A part that is not
    straight-sided behind an opening (a bowl opened at its rim) would have
    its side walls cut through; that raises instead of returning a breached
    shell."""
    what = "shell(t=%g)" % t
    normals = []
    for f in faces:
        if not isinstance(f.Surface, Part.Plane):
            raise CadError("%s: FreeCAD could not hollow this shape (%s) and the "
                           "fallback needs PLANAR open faces. Build the cavity as "
                           "a separate cut." % (what, why))
        normals.append(_outward(shape, f, _mid_normal(f)))
    core, err = None, None
    # A rounded edge of radius exactly t offsets to a zero radius, which OCCT
    # refuses ("no parameter on edge", MEASURED on rounded_box r=2, t=2);
    # 1 um less wall leaves a 1 um radius it accepts.
    for tt in (t, t - 1e-3):
        try:
            core = _one(shape.makeOffsetShape(-tt, 1e-3, False, False, 0, 2))
            if not core.Solids:
                core = Part.Solid(Part.Shell(core.Faces))
            _check(core, "core", solids=1)
            break
        except Exception as exc:                        # noqa: BLE001
            core, err = None, " ".join(str(exc).split()) or type(exc).__name__
    if core is None:
        raise CadError("%s: FreeCAD could not hollow this shape (%s; the inward "
                       "offset failed too: %s). A thinner wall usually works."
                       % (what, why, err))
    span = shape.BoundBox.DiagonalLength + t + 1.0
    tools = [core]
    for n in normals:
        # only the core's flat faces looking straight out of the opening:
        # extruding a curved corner face sweeps it through the side walls
        # (MEASURED: 13 579 mm3 of wall on a rounded_box opened on +-X)
        ends = [f for f in core.Faces if isinstance(f.Surface, Part.Plane)
                and _outward(core, f, _mid_normal(f)).dot(n) > 1 - 1e-6]
        if not ends:
            raise CadError("%s: FreeCAD could not hollow this shape (%s) and the "
                           "part has no flat inside face behind an open face. Build "
                           "the cavity as a separate cut." % (what, why))
        tools.extend(f.extrude(n * span) for f in ends)
    res = shape.cut(tools)
    try:
        res = res.removeSplitter()
    except Exception:                                   # noqa: BLE001
        pass
    if res.isNull() or not res.isValid() or len(res.Solids) != 1:
        raise CadError("%s: FreeCAD could not hollow this shape (%s) and the core "
                       "cut gave %s. Build the cavity as a separate cut."
                       % (what, why, "an invalid shape" if res.isNull() or not res.isValid()
                          else "%d solids" % len(res.Solids)))
    wall = (shape.Volume - res.Volume) - core.Volume
    allowed = t * sum(f.Area for f in faces)
    if wall > 1.02 * allowed + 1e-3:
        raise CadError("%s: FreeCAD could not hollow this shape (%s); the fallback "
                       "would cut %.1f mm3 of wall where the openings allow %.1f - "
                       "the part is not straight-sided behind its open faces. "
                       "Build the cavity as a separate cut." % (what, why, wall, allowed))
    return res


def _mid_normal(f):
    u0, u1, v0, v1 = f.ParameterRange
    return f.normalAt(0.5 * (u0 + u1), 0.5 * (v0 + v1))


def _outward(shape, face, n):
    """`n` or -n: the one pointing out of `shape` at `face`."""
    try:
        if shape.isInside(face.CenterOfMass + n * 0.01, 1e-6, False):
            return n * -1
    except Exception:                                   # noqa: BLE001
        pass
    return n


# ------------------------------------------------------------------- holes
def _drill(shape, tool, what, expect=None, entry=None):
    """Cut `tool`, then prove the hole went where it was asked to.

    entry = (at, axis, r): the BACK stub of every cutter (the BACK mm before
    `at`) must be in air. Material there means `at` is buried in the part or
    `axis` points out of it - the classic wrong-direction hole, which would
    otherwise still remove a sliver and look like success."""
    if entry is not None:
        # Only a CORE of the stub (30 % of the radius) is tested: a concave
        # entry face (drilling outward from inside a bore) curls material
        # into the rim of a full-radius stub, never into its core, while a
        # buried `at` or a reversed `axis` fills the core completely.
        p, a, r = entry
        rc = 0.3 * r
        stub = Part.makeCylinder(rc, BACK, p - a * BACK, a)
        behind = shape.common(stub).Volume
        if behind > 0.25 * math.pi * rc * rc * BACK:
            raise CadError(
                "%s: there is material BEHIND `at` (%.2f mm3 in the %.1f mm "
                "before it) - `axis` points out of the part, or `at` is not on "
                "the entry face. `axis` is the drilling direction INTO the "
                "material (e.g. '-Z' from a top face)." % (what, behind, BACK))
    v0 = shape.Volume
    res = shape.cut(tool)
    _check(res, what)
    removed = v0 - res.Volume
    if removed <= 1e-3:
        raise CadError(
            "%s removed nothing: `at` is off the part or `axis` points away "
            "from it. `at` is the hole centre ON the entry face and `axis` is "
            "the drilling direction INTO the material (e.g. '-Z' from the top "
            "face)." % what)
    if expect is not None and removed < 0.25 * expect:
        raise CadError(
            "%s removed only %.2f of %.2f mm3 expected - most of it is in air. "
            "Check `at` (hole centre ON the entry face) and `axis` (INTO the "
            "material)." % (what, removed, expect))
    if len(res.Solids) != len(shape.Solids):
        raise CadError("%s split the part into %d solids" % (what, len(res.Solids)))
    return _one(res)


def _span(shape, at, axis):
    """Length from `at` along `axis` that is certain to exit the shape."""
    bb = shape.BoundBox
    return bb.DiagonalLength + (V(at) - bb.Center).Length + 1.0


WALL_RING = 8       # through='wall': lines sampled per ring, + the axis
WALL_RING_AT = (0.7, 0.98)  # ring radii / r: the rim decides a curved wall's exit


def _runs_along(shape, p, a, r):
    """The material the drill meets along the axis from `p`, per sampled
    line: [[(t_in, t_out), ...] per line], t in mm along `a` from `p`.
    Lines, not the solid under the whole tool: a hole low in a case's
    front wall that grazes the floor meets ONE solid (front wall + floor +
    back wall joined) - measured, the tool then ran through the back wall
    too. Each line is the part of the axis-parallel segment inside
    `shape` (shape x edge): the axis itself and WALL_RING lines on each
    ring of WALL_RING_AT."""
    L = _span(shape, p, a)
    u = a.cross(App.Vector(1, 0, 0))
    if u.Length < 1e-6:
        u = a.cross(App.Vector(0, 1, 0))
    u.normalize()
    w = a.cross(u)
    offs = [App.Vector(0, 0, 0)] + [
        (u * math.cos(2 * math.pi * i / WALL_RING)
         + w * math.sin(2 * math.pi * i / WALL_RING)) * (k * r)
        for k in WALL_RING_AT for i in range(WALL_RING)]
    lines = []
    for o in offs:
        s = p + o - a * BACK
        seg = Part.LineSegment(s, s + a * (L + BACK)).toShape()
        runs = []
        for e in shape.common(seg).Edges:
            if e.Length <= 1e-6:
                continue
            ts = sorted((v.Point - p).dot(a) for v in e.Vertexes)
            runs.append((ts[0], ts[-1]))
        lines.append(sorted(runs))
    return lines


def _wall_depth(shape, p, a, r, what):
    """(depth, length, wall) of a hole that stops at the FIRST exit from material
    along the axis (R181): depth is the shallowest first exit over the
    sampled lines (a line running along a floor the hole grazes never
    exits, and does not decide it); the tool runs on half-way into the air
    behind it (at most BACK), never into the next wall."""
    lines = [[(lo, hi) for lo, hi in runs if hi > 1e-6]
             for runs in _runs_along(shape, p, a, r)]
    firsts = [runs[0] for runs in lines if runs]
    if not firsts:
        raise CadError(
            "%s removed nothing: no material along `axis` from `at`. `at` is the "
            "hole centre ON the entry face and `axis` the drilling direction "
            "INTO the material (e.g. '-Y' from a +Y wall)." % what)
    first = min(firsts, key=lambda run: run[1])
    depth = first[1]
    nxt = [lo for runs in lines for lo, _hi in runs if lo > depth + 1e-6]
    nxt = min(nxt) if nxt else None
    # the deepest first exit short of the next wall: a curved inner face
    # (a tube's) is left later by the ring lines than by the axis
    deep = max(hi for _lo, hi in firsts if nxt is None or hi < nxt)
    over = BACK if nxt is None else min(BACK, 0.5 * (nxt - deep))
    return depth, deep + over, depth - max(first[0], 0.0)


def _through(through, depth, what):
    """True / 'wall' / False, checked against depth."""
    if through not in (True, False, None, "wall"):
        raise CadError("%s: through must be True (every wall on the axis) or 'wall' "
                       "(stop at the first wall), got %r" % (what, through))
    if bool(through) == (depth is not None):
        raise CadError("%s: give exactly one of depth=<mm>, through=True or "
                       "through='wall'" % what)
    return through


def hole(shape, at, axis, d, depth=None, through=False):
    """Drill a round hole of diameter d.

    at       hole centre ON the entry face, e.g. (10, 10, 5) on a 5 mm plate's top
    axis     drilling direction INTO the material: '-Z', '+X', (0, 1, 0) ...
    depth    blind hole depth (flat bottom), or
    through  True: through EVERYTHING on the axis - on a hollow case that is
             the wall you enter AND the wall behind it (and a rib between);
             'wall': through the first wall only - it stops where the drill
             first leaves material (an enclosure's front-wall hole, R181).
    """
    if d <= 0:
        raise CadError("hole: diameter must be > 0")
    _through(through, depth, "hole")
    a = _dir(axis)
    p = V(at)
    what = "hole(d=%g at %s axis %s)" % (
        d, tuple(round(c, 3) for c in p), tuple(round(c, 3) for c in a))
    if through == "wall":
        _depth, L, wall = _wall_depth(shape, p, a, d / 2.0, what)
        expect = math.pi * d * d / 4.0 * wall
    else:
        L = _span(shape, p, a) if through else float(depth)
        expect = None if through else math.pi * d * d / 4.0 * L
    if L <= 0:
        raise CadError("hole: depth must be > 0")
    tool = Part.makeCylinder(d / 2.0, L + BACK, p - a * BACK, a)
    return _drill(shape, tool, what, expect, (p, a, d / 2.0))


def counterbore(shape, at, axis, d, cb_d, cb_depth, depth=None, through=True):
    """A hole of diameter d with a flat counterbore cb_d x cb_depth at the
    entry (socket-head screws). Same `at` / `axis` / `through` rules as
    hole() (through='wall': the first wall only)."""
    if cb_d <= d:
        raise CadError("counterbore: cb_d (%g) must be larger than d (%g)" % (cb_d, d))
    if depth is not None:
        through = False
    _through(through, depth, "counterbore")
    a = _dir(axis)
    p = V(at)
    what = "counterbore(d=%g, cb_d=%g)" % (d, cb_d)
    if through == "wall":
        _depth, L, _wall = _wall_depth(shape, p, a, d / 2.0, what)
    else:
        L = _span(shape, p, a) if through else float(depth)
    if L < cb_depth:
        raise CadError("counterbore: hole depth %g is shorter than cb_depth %g" % (L, cb_depth))
    tool = Part.makeCylinder(d / 2.0, L + BACK, p - a * BACK, a).fuse(
        Part.makeCylinder(cb_d / 2.0, cb_depth + BACK, p - a * BACK, a))
    expect = math.pi / 4.0 * (cb_d * cb_d * cb_depth + d * d * (L - cb_depth)) \
        if not through else None
    return _drill(shape, tool, what, expect, (p, a, cb_d / 2.0))


def countersink(shape, at, axis, d, csk_d, angle=90.0, depth=None, through=True):
    """A hole of diameter d with a conical countersink csk_d at the entry
    (flat-head screws; ISO countersinks are 90 deg). through='wall': the
    first wall only, as in hole()."""
    if csk_d <= d:
        raise CadError("countersink: csk_d (%g) must be larger than d (%g)" % (csk_d, d))
    if not 0 < angle < 180:
        raise CadError("countersink: angle must be between 0 and 180 deg")
    if depth is not None:
        through = False
    _through(through, depth, "countersink")
    a = _dir(axis)
    p = V(at)
    what = "countersink(d=%g, csk_d=%g)" % (d, csk_d)
    if through == "wall":
        _depth, L, _wall = _wall_depth(shape, p, a, d / 2.0, what)
    else:
        L = _span(shape, p, a) if through else float(depth)
    h = (csk_d - d) / 2.0 / math.tan(math.radians(angle) / 2.0)
    if L < h:
        raise CadError("countersink: hole depth %g is shorter than the cone (%g)" % (L, h))
    tool = Part.makeCylinder(d / 2.0, L + BACK, p - a * BACK, a)
    tool = tool.fuse([Part.makeCone(csk_d / 2.0, d / 2.0, h, p, a),
                      Part.makeCylinder(csk_d / 2.0, BACK, p - a * BACK, a)])
    return _drill(shape, tool, what, None, (p, a, csk_d / 2.0))


# ---------------------------------------------------------------- patterns
def linear_pattern(shape, step, count, step2=None, count2=1):
    """A LIST of copies of `shape` at 0, step, 2*step ... (count of them);
    with step2 / count2 a grid. cut() with it, or fuse_one it into a body:
        body = cad.cut(body, cad.linear_pattern(pin, (10, 0, 0), 4))"""
    if count < 1 or count2 < 1:
        raise CadError("linear_pattern: counts must be >= 1")
    s1 = V(step)
    s2 = V(step2) if step2 is not None else V((0, 0, 0))
    out = []
    for j in range(int(count2)):
        for i in range(int(count)):
            c = shape.copy()
            c.translate(s1 * i + s2 * j)
            out.append(c)
    return out


def polar_pattern(shape, count, axis=(0, 0, 1), center=(0, 0, 0), angle=360.0):
    """A LIST of `count` copies rotated about an axis through `center`.
    angle=360 spaces them evenly round the full circle; otherwise first to
    last span `angle`."""
    if count < 1:
        raise CadError("polar_pattern: count must be >= 1")
    a = _dir(axis)
    c0 = V(center)
    full = abs(abs(angle) - 360.0) < 1e-9
    stepa = angle / count if full else (angle / (count - 1) if count > 1 else 0)
    out = []
    for i in range(int(count)):
        c = shape.copy()
        c.rotate(c0, a, stepa * i)
        out.append(c)
    return out


# --------------------------------------------------------------- snap fits
def cantilever_strain(length, thickness, deflection):
    """Peak bending strain of a constant-section cantilever deflected at its
    tip: eps = 1.5 * t * y / L^2 (beam theory: y = PL^3/3EI, sigma = PLc/I).
    Compare with the permissible strain of YOUR material - not invented here."""
    if length <= 0 or thickness <= 0:
        raise CadError("cantilever_strain: length and thickness must be > 0")
    return 1.5 * thickness * deflection / float(length) ** 2


def snap_fit_cantilever(length, thickness, width, hook_depth, lead_angle=30.0,
                        max_strain=None):
    """A snap-fit hook, a straight cantilever rising from z=0 with a hook at
    its tip on +X.

    Local frame: the beam stands on z=0 (its root - fuse it into the part
    there with some overlap), rises along +Z for `length`, spans x in
    [0, thickness] and y in [-width/2, width/2]. The hook sticks out along +X
    by `hook_depth`, with a square retaining face at z=length and a lead-in
    ramp at `lead_angle` from the beam axis. Position it with .Placement or
    .translate/.rotate.

    max_strain: if given (e.g. from the material datasheet), raises when the
    bending strain needed to clear the hook exceeds it.
    """
    for n, v in (("length", length), ("thickness", thickness), ("width", width),
                 ("hook_depth", hook_depth)):
        if v <= 0:
            raise CadError("snap_fit_cantilever: %s must be > 0" % n)
    if not 5 <= lead_angle <= 80:
        raise CadError("snap_fit_cantilever: lead_angle must be 5..80 deg")
    eps = cantilever_strain(length, thickness, hook_depth)
    if max_strain is not None and eps > max_strain:
        raise CadError(
            "snap_fit_cantilever: clearing the hook strains the beam %.2f%%, "
            "above max_strain %.2f%%. Make it longer or thinner, or the hook "
            "shallower." % (eps * 100, max_strain * 100))
    ramp = hook_depth / math.tan(math.radians(lead_angle))
    t, L, h = float(thickness), float(length), float(hook_depth)
    pts = [(0, 0), (t, 0), (t, L), (t + h, L), (t, L + ramp), (0, L + ramp)]
    wire = Part.makePolygon([V((x, -width / 2.0, z)) for x, z in pts] +
                            [V((0, -width / 2.0, 0))])
    res = Part.Face(wire).extrude(V((0, width, 0)))
    _check(res, "snap_fit_cantilever", solids=1)
    return _one(res)


def _runs_on_line(shape, p0, p1):
    """Material intervals of `shape` on the segment p0 -> p1, as distances
    from p0, sorted: [(a, b), ...] (OCCT common with the line)."""
    d = p1 - p0
    n = d.Length
    u = d * (1.0 / n)
    try:
        hit = shape.common(Part.makeLine(p0, p1))
    except Exception:                                   # noqa: BLE001
        return []
    out = []
    for e in hit.Edges:
        ts = sorted((v.Point - p0).dot(u) for v in e.Vertexes)
        if len(ts) >= 2 and ts[-1] - ts[0] > 1e-6:
            out.append((ts[0], ts[-1]))
    return sorted(out)


SNAP_LEAD_DEG = 30.0        # lead-in ramp of the hooks (snap_fit_cantilever)


def snap_fit_pair(case, lid, count=4, beam_l=10.0, beam_t=1.2, beam_w=8.0,
                  engage=None, clearance=0.2, walls="auto", direction="+Z",
                  max_strain=None):
    """Matched snap-fit hooks on the lid and catch windows through the case walls, placed in one step from one list of positions; returns (case, lid).

    case       the open box, as built; `lid` seated ON it, assembled
               (cad.place_on): its plate rests on the wall tops, a lip may
               drop inside (the lip is cut back round each hook so the beam
               can flex)
    count      hooks in all, spread evenly along two opposite walls
               (walls="auto": the two longer ones; "x" = the walls facing
               +-X, "y" = +-Y, named with the lid turned on top when
               direction is not "+Z"; the printed line names them as
               built); even, >= 2
    beam_l     beam length below the wall top (mm, shortened to fit a
               shallow case); beam_t its thickness (toward the inside);
               beam_w its width along the wall
    engage     how far the hook reaches into the wall (default: the
               smaller of 1.0 and 0.8 x the measured wall)
    clearance  gap beam-to-wall and round each hook in its window
    direction  the side the lid is on ("+Z": on top)

    Everything else is MEASURED: the wall top (the joint), each wall's
    inner and outer face at the hook, the floor. Each hook's retaining
    face sits `clearance` under its window's top edge, so the closed pair
    shares no volume and the lid cannot lift more than that. Raises
    CadError when the lid is not seated, a wall is missing at a hook, the
    case is too shallow, something inside blocks a beam's flex, or the
    bending strain to clear the hook (1.5 t y / L^2) exceeds max_strain.
    Prints one line with the positions and that strain - compare it with
    your material's permissible strain (not invented here).

        case, lid = cad.snap_fit_pair(case, lid, count=4)
    """
    count = int(count)
    if count < 2 or count % 2:
        raise CadError("snap_fit_pair: count must be even and >= 2 (hooks go in "
                       "pairs on opposite walls), got %r" % (count,))
    for n, v in (("beam_l", beam_l), ("beam_t", beam_t), ("beam_w", beam_w)):
        if v <= 0:
            raise CadError("snap_fit_pair: %s must be > 0" % n)
    if clearance < 0.05:
        raise CadError("snap_fit_pair: clearance must be >= 0.05 mm (never a "
                       "tangent fit)")
    for what, sh in (("case", case), ("lid", lid)):
        _check(sh, "snap_fit_pair: " + what)
        if not sh.Solids:
            raise CadError("snap_fit_pair: the %s has no solid" % what)
    d = _dir(direction, "direction")
    turn = abs(d.z - 1.0) > 1e-9
    rot = App.Rotation(d, V((0, 0, 1)))             # the lid's side -> +Z
    c, l = case.copy(), lid.copy()
    if turn:
        c.transformShape(App.Placement(V((0, 0, 0)), rot).toMatrix())
        l.transformShape(App.Placement(V((0, 0, 0)), rot).toMatrix())
    cb, lb = _tight_bbox(c), _tight_bbox(l)
    z0 = cb.ZMax                                    # the wall tops: the joint
    if lb.ZMax <= z0 + 0.05 or lb.ZMin > z0 + 0.05:
        raise CadError(
            "snap_fit_pair: the lid is not seated on the case (lid spans %.2f .. "
            "%.2f along %s, the case top is at %.2f): build it assembled - "
            "lid = cad.place_on(lid, case)" % (lb.ZMin, lb.ZMax, direction, z0))
    w = str(walls).strip().lower().lstrip("+-")
    if w == "auto":                                 # the two longer walls
        w = "y" if cb.XLength >= cb.YLength else "x"
    if w not in ("x", "y"):
        raise CadError("snap_fit_pair: walls must be 'auto', 'x' or 'y'")
    # each wall: o = its outward normal, a = the direction along it
    if w == "y":
        sides = [(V((0, -1, 0)), V((1, 0, 0)), -cb.YMin), (V((0, 1, 0)), V((1, 0, 0)), cb.YMax)]
        span = (cb.XMin, cb.XMax)
    else:
        sides = [(V((-1, 0, 0)), V((0, 1, 0)), -cb.XMin), (V((1, 0, 0)), V((0, 1, 0)), cb.XMax)]
        span = (cb.YMin, cb.YMax)
    along = "xy"[w == "x"]
    per = count // 2
    length = span[1] - span[0]
    bw = min(float(beam_w), 0.8 * length / (2.0 * per))
    pos = [span[0] + length * (i + 0.5) / per for i in range(per)]
    centre = V((0.5 * (cb.XMin + cb.XMax), 0.5 * (cb.YMin + cb.YMax), 0))
    # the floor under the middle: beams and windows stay above it
    runs = _runs_on_line(c, V((centre.x, centre.y, z0 + 1.0)),
                         V((centre.x, centre.y, cb.ZMin - 1.0)))
    floor = (z0 + 1.0 - runs[0][0]) if runs and runs[0][0] > 1.5 else cb.ZMin
    t, cl = float(beam_t), float(clearance)
    ramp_k = 1.0 / math.tan(math.radians(SNAP_LEAD_DEG))
    E = 0.5                                         # beam root sunk into the lid

    def wall_at(o, a, face_o, p, z):
        """(inner, outer) o-coordinates of the wall at p, height z, or None:
        the first material met coming in from 1 mm outside the case."""
        s0 = face_o + 1.0
        start = a * p + o * s0 + V((0, 0, z))
        end = a * p + o * centre.dot(o) + V((0, 0, z))
        r = _runs_on_line(c, start, end)
        if not r or r[0][0] > 1.5:
            return None
        return s0 - r[0][1], s0 - r[0][0]

    hooks, windows, reliefs, walls_mm, strains, lengths, engs = [], [], [], [], [], [], []
    for o, a, face_o in sides:
        side = "%s%s" % ("+" if o.x + o.y > 0 else "-", w.upper())
        for p in pos:
            probe = [wall_at(o, a, face_o, p, z0 - dz) for dz in (0.5, 1.5)]
            if any(x is None for x in probe):
                raise CadError(
                    "snap_fit_pair: no wall under the case top at %s = %.2f on the "
                    "%s side - is the case open there?" % (along, p, side))
            s_in = min(x[0] for x in probe)          # the innermost face
            s_out = max(x[1] for x in probe)
            wall = s_out - s_in
            walls_mm.append(wall)
            eng = float(engage) if engage is not None else min(1.0, 0.8 * wall)
            if eng < 0.3 or eng > wall:
                raise CadError(
                    "snap_fit_pair: the hook would engage %.2f mm into a %.2f mm "
                    "wall (%s side) - engage must be 0.3 .. the wall thickness"
                    % (eng, wall, side))
            hd = eng + cl                            # hook depth off the beam
            ramp = hd * ramp_k
            Lh = min(float(beam_l), z0 - floor - ramp - 2 * cl - 1.0)
            if Lh < 3.0:
                raise CadError(
                    "snap_fit_pair: the case is too shallow for a hook: %.2f mm from "
                    "the wall top to the floor, a %.2f mm hook with its lead-in needs "
                    ">= %.2f" % (z0 - floor, hd, 3.0 + ramp + 2 * cl + 1.0))
            lengths.append(Lh)
            engs.append(eng)
            strains.append(cantilever_strain(Lh, t, eng))
            beam = snap_fit_cantilever(Lh + E, t, bw, hd, SNAP_LEAD_DEG)
            beam.rotate(V((0, 0, 0)), V((0, 1, 0)), 180)     # hang it down
            beam.rotate(V((0, 0, 0)), V((0, 0, 1)),          # hook -> outward
                        math.degrees(math.atan2(o.y, o.x)) - 180.0)
            beam.translate(o * (s_in - cl - t) + a * p + V((0, 0, z0 + E)))
            hooks.append(beam)
            zr = z0 - Lh                             # its retaining face
            # the catch window through the wall, clearance round the hook
            windows.append(_frame_box(bw + 2 * cl, s_out - s_in + 1.0, ramp + 2 * cl,
                                      o, a, p, s_in - 0.5, zr - ramp - cl))
            # the lid's lip round the beam, cut back so the beam can flex
            reliefs.append(_frame_box(bw + 2.0, cl + t + hd + 0.51, Lh + ramp + 1.0,
                                      o, a, p, s_in - cl - t - hd - 0.5,
                                      z0 - Lh - ramp - 1.0))
            # the space the beam bends into must be free of the case
            flex = _frame_box(bw, hd, Lh + ramp, o, a, p, s_in - cl - t - hd,
                              z0 - Lh - ramp)
            if c.common(flex).Volume > TOL:
                raise CadError(
                    "snap_fit_pair: something inside the case blocks the hook at %s = "
                    "%.2f (%s side): the beam needs %.2f mm free behind it to flex"
                    % (along, p, side, hd))
    strain = max(strains)
    if max_strain is not None and strain > max_strain:
        raise CadError(
            "snap_fit_pair: clearing a hook strains its beam %.2f%%, above max_strain "
            "%.2f%%: a longer beam_l, a thinner beam_t or less engage" % (
                strain * 100, max_strain * 100))
    for h in hooks:                                 # a lid plate over each root
        hb = h.BoundBox
        top = V((0.5 * (hb.XMin + hb.XMax), 0.5 * (hb.YMin + hb.YMax), z0 + E / 2.0))
        if not l.isInside(top, 1e-6, True):
            raise CadError("snap_fit_pair: no lid plate over the hook root at (%.2f, "
                           "%.2f) - the lid must cover the wall tops" % (top.x, top.y))
    lip = [r for r in reliefs if l.common(r).Volume > TOL]
    if lip:
        l = cut(l, lip)
    l = fuse_one(l, *hooks)
    c = cut(c, windows)
    shared = c.common(l).Volume
    if shared > 1e-3:
        raise CadError("snap_fit_pair: the snapped lid and case share %.3f mm3 - a "
                       "hook meets a feature of the case; move the hooks (count, "
                       "walls) or clear that feature" % shared)
    wl, al, at = w.upper(), along, list(pos)
    if turn:
        inv = App.Placement(V((0, 0, 0)), rot.inverted()).toMatrix()
        c.transformShape(inv)
        l.transformShape(inv)
        # report in the caller's frame, not the internal lid-on-top one
        ri = rot.inverted()
        o0, a0 = sides[0][0], sides[0][1]
        wn, an = ri.multVec(o0), ri.multVec(a0)
        kw = max(range(3), key=lambda i: abs(wn[i]))
        ka = max(range(3), key=lambda i: abs(an[i]))
        wl, al = "XYZ"[kw], "xyz"[ka]
        mid = V((centre.x, centre.y, z0)) - a0 * centre.dot(a0)
        at = [ri.multVec(a0 * p + mid)[ka] for p in pos]
    print("snap_fit_pair: %d hooks on the +-%s walls at %s = %s; beams %.2f long x "
          "%.2f x %.2f mm, engaging %.2f .. %.2f mm into walls %.2f .. %.2f mm, "
          "clearance %.2f; bending strain to clear a hook %.2f %% (compare with your "
          "material)" % (count, wl, al, ", ".join("%.2f" % (p + 0.0) for p in sorted(at)),
                          min(lengths), t, bw, min(engs), max(engs), min(walls_mm), max(walls_mm), cl, strain * 100))
    return _one(c), _one(l)


def _frame_box(width, depth, height, o, a, p, s_lo, z_lo):
    """A box `width` along `a` (centred on p), `depth` along the outward
    normal `o` from o-coordinate s_lo, `height` up from z_lo."""
    b = Part.makeBox(width, depth, height, V((-width / 2.0, 0, 0)))
    b.rotate(V((0, 0, 0)), V((0, 0, 1)), math.degrees(math.atan2(o.y, o.x)) - 90.0)
    b.translate(o * s_lo + a * p + V((0, 0, z_lo)))
    return b


# ------------------------------------------------------------------ hinges
HINGE_STEP_DEG = 5.0        # the self-sweep's step (atech_geom.MOTION_STEP_DEG)
HINGE_HIT_MM3 = 0.01        # shared volume that counts as a hit (check.py's
                            # MIN_OVERLAP_MM3: the same bar as ./check's sweep)


def _hinge_side(axis, cb):
    """(outward normal o of the hinge side, explicit (point, dir) or None)
    from pin_hinge's `axis`: a side ('+Y' ...) or [point, dir]."""
    if isinstance(axis, str):
        o = _dir(axis, "pin_hinge: axis")
        if abs(o.z) > 1e-9 or min(abs(o.x), abs(o.y)) > 1e-9:
            raise CadError("pin_hinge: axis %r - the hinge side must be '+X', '-X', "
                           "'+Y' or '-Y' (the lid is on top)" % (axis,))
        return o, None
    try:
        p, d = V(axis[0]), _dir(axis[1], "pin_hinge: axis direction")
    except (TypeError, IndexError, KeyError):
        raise CadError("pin_hinge: axis must be a side ('+Y') or [[x, y, z], [dx, dy, dz]]")
    if abs(d.z) > 1e-6 or min(abs(d.x), abs(d.y)) > 1e-6:
        raise CadError("pin_hinge: the axis direction must run along X or Y (along a "
                       "wall's top edge), got (%.3g, %.3g, %.3g)" % (d.x, d.y, d.z))
    n = V((0, 0, 1)).cross(d)               # horizontal, across the axis
    centre = V((0.5 * (cb.XMin + cb.XMax), 0.5 * (cb.YMin + cb.YMax), p.z))
    o = n if (p - centre).dot(n) >= 0 else n * -1.0
    return o, (p, d)


def pin_hinge(box, lid, knuckles=3, pin_d=1.75, clearance=0.2, axis="+Y",
              knuckle_d=None, range_deg=(0, 90), part="Lid"):
    """A pin hinge on an assembled box/lid pair: alternating knuckles on the box and the lid with one pin bore through them all; returns (box, lid, motion).

    box        the open box, as built; `lid` seated ON it, assembled
               (cad.place_on), its plate resting on the wall tops
    knuckles   how many knuckles along the hinge edge (>= 2); the box gets
               the 1st, 3rd ..., the lid the ones between
    pin_d      the pin's diameter (1.75: a length of filament; a steel rod
               or a nail: its measured diameter). The bore is pin_d +
               2 x clearance
    clearance  the gap everywhere: knuckle to knuckle along the axis, round
               each knuckle in the other part's notch, round the pin
    axis       the hinge side: '+Y' (default: the back), '-Y', '+X', '-X' -
               the axis then runs ON that wall's outer face, at its top
               edge. Or [[x, y, z], [dx, dy, dz]]: an explicit axis along X
               or Y, ON or OUTSIDE that face (inside it raises: the lid
               would hit the wall from the first degrees, R202)
    knuckle_d  the knuckle diameter (default: bore + 2 x the measured wall,
               at least bore + 2.4)
    range_deg  the swing the motion entry declares (and this call sweeps)
    part       the lid's document label, for the motion entry

    MEASURED: the wall top (the joint), the hinge wall's outer face and
    thickness, the length of the edge. The returned `motion` is the
    intent.json "motion" entry ./check sweeps (R202):
        {"part": part, "axis": [[x, y, z], [dx, dy, dz]], "range_deg": [a, b]}
    its direction turns the lid OPEN by the right-hand rule. Before
    returning, the lid is swept through range_deg in 5 deg steps the way
    ./check does and the call raises CadError at the first angle it shares
    more than 0.01 mm3 with the box - it never returns a hinge that binds.
    The pin is not modelled (it is bought or cut: the printed line gives
    its diameter and length).

        box, lid, motion = cad.pin_hinge(box, lid, knuckles=3)
        # intent.json: "motion": [motion]
    """
    n = int(knuckles)
    if n < 2:
        raise CadError("pin_hinge: knuckles must be >= 2 (one on the box, one on "
                       "the lid at least), got %r" % (knuckles,))
    if pin_d <= 0:
        raise CadError("pin_hinge: pin_d must be > 0")
    if clearance < 0.05:
        raise CadError("pin_hinge: clearance must be >= 0.05 mm (never a tangent fit)")
    a0, a1 = (float(x) for x in range_deg)
    if a0 == a1 or abs(a1 - a0) > 360.0:
        raise CadError("pin_hinge: range_deg %r must span 0 < |b - a| <= 360"
                       % (tuple(range_deg),))
    for what, sh in (("box", box), ("lid", lid)):
        _check(sh, "pin_hinge: " + what)
        if not sh.Solids:
            raise CadError("pin_hinge: the %s has no solid" % what)
    cb, lb = _tight_bbox(box), _tight_bbox(lid)
    z0 = cb.ZMax                                    # the wall tops: the joint
    if lb.ZMax <= z0 + 0.05 or lb.ZMin > z0 + 0.05:
        raise CadError(
            "pin_hinge: the lid is not seated on the box (lid spans z %.2f .. %.2f, "
            "the box top is at %.2f): build it assembled - lid = cad.place_on(lid, "
            "box)" % (lb.ZMin, lb.ZMax, z0))
    o, explicit = _hinge_side(axis, cb)
    a = V((0, 0, 1)).cross(o)                       # along the hinge edge
    a = a * -1.0 if a.x + a.y < 0 else a            # +X or +Y
    face = max(o.dot(V(p)) for p in (
        (cb.XMin, cb.YMin, 0), (cb.XMax, cb.YMax, 0)))     # the hinge face, along o
    lo = min(a.dot(V(p)) for p in ((cb.XMin, cb.YMin, 0), (cb.XMax, cb.YMax, 0)))
    hi = max(a.dot(V(p)) for p in ((cb.XMin, cb.YMin, 0), (cb.XMax, cb.YMax, 0)))
    side = "%s%s" % ("+" if o.x + o.y > 0 else "-", "X" if abs(o.x) > 0.5 else "Y")
    mid = 0.5 * (lo + hi)
    # the hinge wall under its top edge, measured from 1 mm outside
    c_o = o.dot(V((0.5 * (cb.XMin + cb.XMax), 0.5 * (cb.YMin + cb.YMax), 0)))
    runs = _runs_on_line(box, a * mid + o * (face + 1.0) + V((0, 0, z0 - 0.5)),
                         a * mid + o * c_o + V((0, 0, z0 - 0.5)))
    if not runs or runs[0][0] > 1.5:
        raise CadError("pin_hinge: no wall under the box top on the %s side - the "
                       "hinge needs a wall to carry the box's knuckles" % side)
    wall = runs[0][1] - runs[0][0]
    if explicit is None:
        e, h = 0.0, 0.0                             # ON the face, at its top edge
    else:
        p, _d = explicit
        e, h = o.dot(p) - face, p.z - z0
        if e < -1e-6:
            raise CadError(
                "pin_hinge: the axis is %.2f mm INSIDE the %s face - the lid would "
                "hit that wall from the first degrees (R202). Put it ON the face "
                "(axis=%r) or outside it" % (-e, side, side))
    bore = float(pin_d) + 2.0 * float(clearance)
    R = 0.5 * float(knuckle_d) if knuckle_d else 0.5 * bore + max(1.2, wall)
    if R - 0.5 * bore < 0.8:
        raise CadError("pin_hinge: knuckle_d %.2f leaves under 0.8 mm round a %.2f mm "
                       "bore" % (2 * R, bore))
    if e > R - 0.5 or abs(h) > R - 0.5:
        raise CadError(
            "pin_hinge: the axis is %.2f mm outside the face and %.2f mm off the "
            "wall top - a %.2f mm knuckle would not reach both parts (keep both "
            "under %.2f)" % (e, h, 2 * R, R - 0.5))
    cl = float(clearance)
    s = ((hi - lo) - (n - 1) * cl) / n
    if s < 2.0:
        raise CadError("pin_hinge: %d knuckles on a %.2f mm edge are %.2f mm long - "
                       "fewer knuckles (>= 2 mm each)" % (n, hi - lo, s))
    origin = a * lo + o * (face + e) + V((0, 0, z0 + h))
    if explicit is not None:                        # the caller's point, on the line
        origin = explicit[0] + a * (lo - a.dot(explicit[0]))

    def cyl(r, x0, x1):
        return Part.makeCylinder(r, x1 - x0, origin + a * (x0 - lo), a)
    starts = [lo + k * (s + cl) for k in range(n)]
    box_k = [cyl(R, x, x + s) for x in starts[0::2]]
    lid_k = [cyl(R, x, x + s) for x in starts[1::2]]
    box_notch = [cyl(R + cl, x - cl, x + s + cl) for x in starts[1::2]]
    lid_notch = [cyl(R + cl, x - cl, x + s + cl) for x in starts[0::2]]
    pin = cyl(0.5 * bore, lo - 1.0, hi + 1.0)
    b, l = box, lid
    hit = [t for t in box_notch if b.common(t).Volume > TOL]
    if hit:
        b = cut(b, hit)
    hit = [t for t in lid_notch if l.common(t).Volume > TOL]
    if hit:
        l = cut(l, hit)
    b = cut(fuse_one(b, *box_k), pin)
    l = cut(fuse_one(l, *lid_k), pin)
    # opening = the lid's side away from the hinge rises: Z x o
    d = V((0, 0, 1)).cross(o)
    pt = origin + a * (mid - lo)
    shared = b.common(l).Volume
    if shared > HINGE_HIT_MM3:
        raise CadError("pin_hinge: closed, the hinged lid and box share %.3f mm3 - "
                       "a feature of the lid or box meets a knuckle" % shared)
    steps = max(1, int(math.ceil(abs(a1 - a0) / HINGE_STEP_DEG - 1e-9)))
    for i in range(steps + 1):
        deg = a0 + (a1 - a0) * i / float(steps)
        t = l.copy()
        if deg:
            t.rotate(pt, d, deg)
        v = t.common(b).Volume
        if v > HINGE_HIT_MM3:
            raise CadError(
                "pin_hinge: turned %g deg the lid hits the box (%.3f mm3 shared) - "
                "something of the lid or box reaches past the hinge line; trim it "
                "or narrow range_deg" % (deg, v))

    def r4(x):
        return round(float(x), 4) + 0.0
    motion = {"part": str(part),
              "axis": [[r4(pt.x), r4(pt.y), r4(pt.z)], [r4(d.x), r4(d.y), r4(d.z)]],
              "range_deg": [a0, a1]}
    print("pin_hinge: %d knuckles (%d on the box, %d on the lid) %.2f mm long, "
          "%.2f mm across, on the %s side; axis (%.2f, %.2f, %.2f) along %s, %.2f mm "
          "outside the face, at the wall top; bore %.2f for a %.2f x %.1f mm pin; "
          "clearance %.2f; swept %g .. %g deg clear (%d positions)" % (
              n, len(box_k), len(lid_k), s, 2 * R, side, pt.x, pt.y, pt.z,
              "XY"[abs(a.y) > 0.5], e, bore, float(pin_d), hi - lo, cl, a0, a1,
              steps + 1))
    if max(len(box_k), len(lid_k)) > 1:
        print("pin_hinge: the pin bore runs through %d knuckles of one part - ./check's "
              "WARNING that a %.2f mm hole along %s goes through %d walls is this bore, "
              "and it is meant (knuckles=2 gives one knuckle per part)" % (
                  max(len(box_k), len(lid_k)), bore, "XY"[abs(a.y) > 0.5],
                  max(len(box_k), len(lid_k))))
    return _one(b), _one(l), motion


# ---------------------------------------------------------- socket opening
def socket_opening(wall, module, margin=1.5, board=None):
    """A connector opening cut through `wall` in front of a seated Atech module's socket mouth (a USB-C module); returns the cut wall.

    wall     the part (Shape) standing in front of the socket: the case
             side or the end lid the plug comes in through
    module   the seated module (the object ap.seat returned)
    margin   clearance round the measured socket mouth on every side (mm):
             the opening is the mouth's measured size + 2 x margin. A
             cable's plug overmould is larger than its socket shell - if
             yours is, give a larger margin (its size is not invented here)
    board    the board object (default: the one in the module's document)

    MEASURED, never typed: the mouth's direction and its outline
    (atech_geom.socket_face - the same measurement ./check's OPEN line
    uses), and how far the wall is in front of it. The cut runs from the
    mouth along its direction through the FIRST wall it meets only (never a
    wall behind that). Raises CadError when the module has no socket mouth,
    or nothing of `wall` stands in front of it. Prints one line with the
    direction and the opening size.

        lid = cad.socket_opening(lid, usb)          # usb = ap.seat(doc, "usbc", 5)
    """
    import numpy as np
    import atech_geom
    mesh = getattr(module, "Mesh", None)
    if mesh is None:
        raise CadError("socket_opening: %r is not a seated module (it has no Mesh)"
                       % (getattr(module, "Label", module),))
    _check(wall, "socket_opening: wall")
    if not wall.Solids:
        raise CadError("socket_opening: the wall has no solid")
    if margin < 0.1:
        raise CadError("socket_opening: margin must be >= 0.1 mm (never a tangent fit)")
    if board is None:
        doc = getattr(module, "Document", None)
        board = next((o for o in (doc.Objects if doc else ())
                      if getattr(o, "AtechRole", None) == "board"), None)
    if board is None or getattr(board, "Mesh", None) is None:
        raise CadError("socket_opening: no Atech board found for %s - pass board="
                       % module.Label)
    _tilt, bn = atech_geom.board_tilt(board.Mesh)
    if bn is None:
        raise CadError("socket_opening: the board's plane could not be measured")
    r = module.Placement.Rotation
    axes = [[float(c) for c in r.multVec(V(e))] for e in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
    dv, P = atech_geom.socket_face(mesh, bn, axes)
    if dv is None:
        raise CadError("socket_opening: %s (%s) has no socket mouth - no part of its "
                       "mesh stands out along the board (only a connector module "
                       "such as usbc has one)" % (module.Label,
                                                  getattr(module, "AtechModule", "?")))
    d = V(dv)
    d.normalize()
    u = d.cross(V(bn))
    if u.Length < 1e-6:
        u = d.cross(V((0, 0, 1)) if abs(d.z) < 0.9 else V((1, 0, 0)))
    u.normalize()
    w = d.cross(u)
    U = np.array([u.x, u.y, u.z])
    W = np.array([w.x, w.y, w.z])
    D = np.array([d.x, d.y, d.z])
    pu, pw, pd = P @ U, P @ W, P @ D
    mouth = float(pd.max())
    cu, cw = 0.5 * (pu.min() + pu.max()), 0.5 * (pw.min() + pw.max())
    su, sw = float(pu.max() - pu.min()), float(pw.max() - pw.min())
    ou, ow = su + 2.0 * float(margin), sw + 2.0 * float(margin)
    base = u * cu + w * cw
    # the first wall in front: rays from the mouth through the opening's
    # centre and corners, the deepest exit of the first material run
    far = 200.0
    lift = 0.05
    ends = []
    for fu, fw in ((0, 0), (-1, -1), (-1, 1), (1, -1), (1, 1)):
        q = base + u * (fu * 0.45 * ou) + w * (fw * 0.45 * ow) + d * (mouth + lift)
        rr = _runs_on_line(wall, q, q + d * far)
        if rr:
            ends.append(rr[0])
    if not ends:
        raise CadError("socket_opening: nothing of the wall stands in front of %s's "
                       "socket mouth (facing %s) within %g mm - pass the part the "
                       "plug comes in through" % (module.Label, atech_geom.normal_text(dv),
                                                  far))
    first = min(e[0] for e in ends)
    # runs that start before the nearest one ends are the same wall
    exit_ = max(e[1] for e in ends if e[0] < min(x[1] for x in ends))
    depth = exit_ + BACK + lift
    tool = Part.makeBox(ou, ow, depth, V((-ou / 2.0, -ow / 2.0, 0)))
    m = App.Matrix(u.x, w.x, d.x, 0, u.y, w.y, d.y, 0, u.z, w.z, d.z, 0, 0, 0, 0, 1)
    tool.transformShape(m)                      # a rotation: (u, w, d) is right-handed
    tool.translate(base + d * (mouth + lift))
    out = cut(wall, tool)
    print("socket_opening: %s's socket mouth faces %s; opening %.2f x %.2f mm (the "
          "mouth %.2f x %.2f + %.2f a side) through %.2f mm of wall, %.2f mm in "
          "front of the mouth" % (module.Label, atech_geom.normal_text(dv), ou, ow,
                                  su, sw, margin, exit_ - first, first + lift))
    return out


# ------------------------------------------------------------------- gears
def gear_shift_for(z, pressure_angle=20.0):
    """Profile shift x that just avoids undercut on a z-tooth gear:
    x = 1 - z*sin^2(alpha)/2, and 0 from z_min = 2/sin^2(alpha) (17.1 teeth
    at 20 deg) up."""
    s2 = math.sin(math.radians(pressure_angle)) ** 2
    return max(0.0, 1.0 - z * s2 / 2.0)


def spur_gear(m, z, thickness, bore=None, backlash=0.0, shift=0.0,
              pressure_angle=20.0):
    """A spur gear with REAL involute teeth (FreeCAD's bundled fcgear
    generator), axis +Z, centred on the origin, z from 0 to `thickness`.

    m          module (mm): pitch diameter = m*z, tip = m*(z + 2 + 2*shift)
    z          tooth count (>= 6)
    bore       centre hole diameter (through), or None
    backlash   circular backlash j (mm), taken off the tooth thickness by
               an analytic profile shift - tip and root diameters unchanged
    shift      profile shift coefficient x (undercut below ~17 teeth: see
               gear_shift_for(z); a shifted pair must mate at the shifted
               centre distance)

        gear = cad.spur_gear(1.5, 24, 8, bore=8)
        doc.addObject("Part::Feature", "Gear").Shape = gear
    """
    if m <= 0 or thickness <= 0:
        raise CadError("spur_gear: module and thickness must be > 0")
    z = int(z)
    if z < 6:
        raise CadError("spur_gear: need at least 6 teeth, got %d" % z)
    if backlash < 0:
        raise CadError("spur_gear: backlash must be >= 0")
    try:
        from fcgear import involute, fcgear as fcg
    except ImportError as exc:
        raise CadError("spur_gear: FreeCAD's fcgear generator is missing (%s)" % exc)
    alpha = math.radians(pressure_angle)
    dx = -float(backlash) / (2.0 * m * math.tan(alpha)) if backlash else 0.0
    b = fcg.FCWireBuilder()
    try:
        involute.CreateExternalGear(b, float(m), z, float(pressure_angle), split=True,
                                    addCoeff=1.0 - dx, dedCoeff=1.25 + dx,
                                    shiftCoeff=float(shift) + dx)
        wire = Part.Wire([e.toShape() for e in b.wire])
        gear = Part.Face(wire).extrude(V((0, 0, float(thickness))))
    except Exception as exc:                            # noqa: BLE001
        raise CadError("spur_gear(m=%g, z=%d): the generator failed (%s)" % (m, z, exc))
    _check(gear, "spur_gear", solids=1)
    gear = _one(gear)
    tip = m * (z + 2.0 + 2.0 * shift)
    got = 2.0 * max(math.hypot(v.X, v.Y) for v in gear.Vertexes)
    if abs(got - tip) > 0.01 * m + 0.01:
        raise CadError("spur_gear: tip diameter %.3f mm, expected %.3f" % (got, tip))
    if bore:
        root = m * (z - 2.5 + 2.0 * shift)
        if bore >= root - 2.0 * m:
            raise CadError("spur_gear: bore %g leaves no rim under the %.2f mm "
                           "root circle" % (bore, root))
        gear = hole(gear, at=(0, 0, 0), axis="+Z", d=bore, through=True)
    return gear


# ---------------------------------------------------------------- placing
def place_on(shape, base, gap=0.0, direction="+Z"):
    """A copy of `shape` moved along `direction` so its lowest point (in that
    direction) sits `gap` mm beyond the highest point of `base` - a lid ON
    its box. Measured with tight boxes; only that one axis moves.

        lid = cad.place_on(lid, box)            # seated, touching
        lid = cad.place_on(lid, box, gap=-2.0)  # its 2 mm lip sunk into the box

    Model an assembly ASSEMBLED: intent.json size_mm is the assembled
    product, and a lid parked above its box doubles the height (S44: a
    snap box measured 60 mm high against its intended 40)."""
    d = _dir(direction, "direction")
    k = max(range(3), key=lambda i: abs((d.x, d.y, d.z)[i]))
    if abs(abs((d.x, d.y, d.z)[k]) - 1.0) > 1e-9:
        raise CadError("place_on: direction must be an axis ('+Z', '-X' ...)")
    sb, bb = _tight_bbox(shape), _tight_bbox(base)
    lo = (sb.XMin, sb.YMin, sb.ZMin)[k] if d[k] > 0 else -(sb.XMax, sb.YMax, sb.ZMax)[k]
    hi = (bb.XMax, bb.YMax, bb.ZMax)[k] if d[k] > 0 else -(bb.XMin, bb.YMin, bb.ZMin)[k]
    out = shape.copy()
    out.translate(d * (hi + float(gap) - lo))
    return out


# ------------------------------------------------------------ atech parts
def bound_of(*objs):
    """One world App.BoundBox (not a shape) around shapes, document objects
    and seated Atech modules / the board. Mesh features have no .Shape;
    their .Mesh is already in world coordinates.
    Shapes use the tight optimalBoundingBox.

        bb = cad.bound_of(board, button, speaker)
        case = cad.rounded_box(bb.XLength + 2*(W + C), ...,
                               at=(bb.XMin - W - C, ...))"""
    out = App.BoundBox()
    n = 0
    for o in _flat(objs):
        mesh = getattr(o, "Mesh", None)
        if mesh is not None and not isinstance(o, Part.Shape):
            out.add(App.BoundBox(mesh.BoundBox))
            n += 1
            continue
        sh = o if isinstance(o, Part.Shape) else getattr(o, "Shape", None)
        if sh is None or sh.isNull():
            raise CadError("bound_of: %r has neither a Shape nor a Mesh"
                           % (getattr(o, "Label", o),))
        out.add(_tight_bbox(sh))
        n += 1
    if not n:
        raise CadError("bound_of: nothing given")
    return out
