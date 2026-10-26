"""measure - Atech's one Measure tool and the Section tool (PRD W3, R300-R312).

Three layers, each usable without the one above it:

  core        Pure geometry on Part shapes, FreeCAD-headless (freecadcmd):
              distance, angle, radius, size, mass, wall_at, interference,
              fit_check, section_caps. Every number is in mm (deg, g).
              Raises MeasureError with a plain sentence on a bad pick.
  project     Measurements kept as document objects (record, measurements,
              refresh, remove, measurements_for_brief). A kept measurement is
              an App::FeaturePython with only plain properties: it holds the
              picked part's LABEL, the sub-element and the picked point, never
              a link. So build.py never sees it as owned (it carries no
              AtechAgentBuilt flag) and never keeps a "[previous build]" body
              alive for it (build.in_process keeps a previous-build object only
              when something links to it, via InList). After a rebuild,
              refresh() finds the part again by label and the element nearest
              the stored point, and re-measures.
  ui          make_measure_button(view_bar) / make_section_button(view_bar):
              a view-bar button that opens a floating card over the 3D view
              (MeasurePanel / SectionPanel). Qt and FreeCADGui are imported
              lazily, so the core imports with neither.

The selection is turned into picks (Pick: object, sub-element name, picked
point in world mm); a pick on a mesh (an Atech board or module) becomes its
picked point.
"""
import json
import math
import os
import sys

# ------------------------------------------------------------------ data
#: R304: densities in g/cm3 (the common FDM filaments; PLA is the default)
MATERIALS = (("PLA", 1.24), ("PETG", 1.27), ("ABS", 1.04), ("TPU", 1.21))
DENSITY = dict(MATERIALS)
DEFAULT_MATERIAL = "PLA"
#: R303: a wall under this is shown red (the printability floor the PRD sets)
THIN_WALL_MM = 0.8

#: kind -> (button label, hint, picks needed: an int, or None = optional)
KINDS = (
    ("distance", "Distance", "Click two things: points, edges, faces or parts.", 2),
    ("angle", "Angle", "Click two straight edges or flat faces.", 2),
    ("radius", "Radius", "Click a round edge or a round face.", 1),
    ("size", "Size", "Click parts, or press Measure for the whole model.", None),
    ("wall", "Wall", "Click a face to measure the wall behind it.", 1),
    ("interference", "Overlaps", "Click parts, or press Measure to check every part.", None),
    ("mass", "Mass", "Click parts, or press Measure for the whole model.", None),
    ("fit", "Fit", "Press Measure to check how the board and modules fit.", None),
)
KIND_LABEL = {k: lab for k, lab, _h, _n in KINDS}
KIND_HINT = {k: h for k, _l, h, _n in KINDS}
KIND_PICKS = {k: n for k, _l, _h, n in KINDS}
#: what refresh() re-measures (fast); overlaps and fit are kept as measured
CHEAP = ("distance", "angle", "radius", "size", "wall", "mass")

GROUP_LABEL = "Measurements"
PROP_GROUP = "Measurement"
REMATCH_MM = 10.0         # after a rebuild, the same-facing element this close
REMATCH_DEG = 10.0        # ...whose normal / direction turned at most this much
REMATCH_VERTEX_MM = 1.0   # a corner must stay this close
_EPS = 1e-6

KIT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_kit")


class MeasureError(Exception):
    """A pick the tool cannot measure; str() is a sentence for the user."""


class Pick(object):
    """One picked thing: a document object, a sub-element name ("Face3",
    "Edge1", "Vertex2", "" for the whole object; may carry a container path
    such as "Pad.Face3") and the picked point (world mm) or None."""

    __slots__ = ("obj", "sub", "point")

    def __init__(self, obj, sub="", point=None):
        self.obj = obj
        self.sub = sub or ""
        self.point = None if point is None else tuple(float(c) for c in point)

    def __repr__(self):
        return "Pick(%s, %r, %r)" % (getattr(self.obj, "Label", "?"), self.sub, self.point)


def _geom():
    """agent_kit/atech_geom (tight boxes, overlaps, margins, face_open), or
    None. Appended to sys.path like build._kit_on_path (never shadows)."""
    if KIT_DIR not in sys.path:
        sys.path.append(KIT_DIR)
    try:
        import atech_geom
        return atech_geom
    except Exception:                                   # noqa: BLE001
        return None


def _vec(p):
    import FreeCAD as App
    return p if isinstance(p, App.Vector) else App.Vector(*p)


def _r(x, n=3):
    return round(float(x), n) + 0.0


# ================================================================== core
def distance(a, b):
    """R300: minimum distance between two shapes, with the axis components
    of the closest-points vector. Returns {"kind", "mm", "dx", "dy", "dz",
    "p1", "p2"} (dx.. are absolute, mm)."""
    try:
        d, pairs, _info = a.distToShape(b)
    except Exception as exc:                            # noqa: BLE001
        raise MeasureError("Could not measure the distance between these two (%s)." % exc)
    if not pairs:
        raise MeasureError("Could not measure the distance between these two.")
    p1, p2 = pairs[0]
    return {"kind": "distance", "mm": _r(d), "dx": _r(abs(p2.x - p1.x)),
            "dy": _r(abs(p2.y - p1.y)), "dz": _r(abs(p2.z - p1.z)),
            "p1": [_r(c) for c in p1], "p2": [_r(c) for c in p2]}


def direction(s):
    """The direction a shape stands for when measuring an angle: a straight
    edge's direction, a flat face's normal, a round edge's or a cylinder's
    axis. None when it has none."""
    import Part
    try:
        if s.ShapeType == "Edge":
            c = s.Curve
            if isinstance(c, (Part.Line, Part.LineSegment)):
                v = s.Vertexes[-1].Point - s.Vertexes[0].Point
                return v.normalize() if v.Length > _EPS else c.Direction
            if isinstance(c, (Part.Circle, Part.ArcOfCircle)):
                return c.Axis
            return None
        if s.ShapeType == "Face":
            srf = s.Surface
            if isinstance(srf, Part.Plane) or srf.__class__.__name__ == "Plane":
                u, v = srf.parameter(s.CenterOfMass)
                return s.normalAt(u, v)
            if hasattr(srf, "Axis") and srf.__class__.__name__ in ("Cylinder", "Cone"):
                return srf.Axis
    except Exception:                                   # noqa: BLE001
        return None
    return None


def angle(a, b):
    """R301: the angle between two straight edges / flat faces (normals) /
    round edges or cylinders (axes). Returns {"kind", "deg" (0-90, the angle
    between the lines or planes), "between" (0-180, between the directions
    as found)}."""
    da, db = direction(a), direction(b)
    if da is None or db is None:
        raise MeasureError("Pick two straight edges or flat faces to measure an angle.")
    c = max(-1.0, min(1.0, da.dot(db) / (da.Length * db.Length)))
    between = math.degrees(math.acos(c))
    return {"kind": "angle", "deg": _r(min(between, 180.0 - between), 4),
            "between": _r(between, 4)}


def radius(s):
    """R302: the radius and diameter of a round edge (circle or arc), a
    cylindrical or spherical face, or of the first round edge of a part
    picked whole. Returns {"kind", "radius", "diameter", "center"}."""
    import Part
    cands = [s]
    if s.ShapeType not in ("Edge", "Face"):
        cands = list(s.Faces) + list(s.Edges)
    for c in cands:
        try:
            if c.ShapeType == "Edge" and isinstance(c.Curve, (Part.Circle, Part.ArcOfCircle)):
                r, ctr = c.Curve.Radius, c.Curve.Center
            elif c.ShapeType == "Face" and c.Surface.__class__.__name__ in ("Cylinder", "Sphere"):
                srf = c.Surface
                r = srf.Radius
                ctr = srf.Center if hasattr(srf, "Center") else srf.Location
            else:
                continue
        except Exception:                               # noqa: BLE001
            continue
        return {"kind": "radius", "radius": _r(r), "diameter": _r(2 * r),
                "center": [_r(v) for v in ctr]}
    raise MeasureError("Pick a round edge or a round face to measure a radius.")


def _box(shape):
    g = _geom()
    if g is not None:
        try:
            return g.tight(shape)
        except Exception:                               # noqa: BLE001
            pass
    try:
        return shape.optimalBoundingBox()
    except Exception:                                   # noqa: BLE001
        return shape.BoundBox


def size(shapes):
    """R303: the tight axis-aligned size of one or more shapes together
    (atech_geom.tight). Returns {"kind", "x", "y", "z", "box"}."""
    shapes = [s for s in shapes if s is not None and not s.isNull()]
    if not shapes:
        raise MeasureError("There is nothing to measure.")
    bb = None
    for s in shapes:
        b = _box(s)
        if bb is None:
            bb = b
        else:
            bb.add(b)
    return {"kind": "size", "x": _r(bb.XLength), "y": _r(bb.YLength),
            "z": _r(bb.ZLength),
            "box": [_r(v) for v in (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)]}


def mass(shapes, material=DEFAULT_MATERIAL):
    """R304: volume and printed mass (solid, 100 % infill) for `material`
    (MATERIALS, g/cm3). Returns {"kind", "volume_mm3", "volume_cm3",
    "grams", "material", "density"}."""
    if material not in DENSITY:
        raise MeasureError("Unknown material %r (choose %s)."
                           % (material, ", ".join(DENSITY)))
    vol = 0.0
    for s in shapes:
        try:
            for so in (s.Solids if s.Solids else []):
                vol += abs(so.Volume)
        except Exception:                               # noqa: BLE001
            continue
    if vol <= 0:
        raise MeasureError("Pick solid parts to weigh (a face or an edge has no volume).")
    rho = DENSITY[material]
    return {"kind": "mass", "volume_mm3": _r(vol), "volume_cm3": _r(vol / 1000.0, 4),
            "grams": _r(vol / 1000.0 * rho, 3), "material": material, "density": rho}


def _solid_of(shape, point):
    sols = list(shape.Solids) if shape.ShapeType != "Solid" else [shape]
    if not sols:
        raise MeasureError("That part is not a solid, so it has no wall to measure.")
    if len(sols) == 1:
        return sols[0]
    v = _vec(point)
    import Part
    vx = Part.Vertex(v)
    return min(sols, key=lambda s: s.distToShape(vx)[0])


def wall_at(shape, point, face=None):
    """R305: the wall thickness at `point` on a face of `shape`: the length
    of the run of material along the inward normal, starting at the point
    (an exact OCCT ray/solid common, not a sampled probe). `face` defaults to
    the face nearest the point. Returns {"kind", "mm", "at", "dir", "thin"};
    thin is True under THIN_WALL_MM."""
    import Part
    p = _vec(point)
    solid = _solid_of(shape, p)
    vx = Part.Vertex(p)
    if face is None:
        face = min(solid.Faces, key=lambda f: f.distToShape(vx)[0])
    try:
        d0, pr, _i = face.distToShape(vx)
        p = pr[0][0] if d0 > _EPS else p
        u, v = face.Surface.parameter(p)
        n = face.normalAt(u, v)
    except Exception as exc:                            # noqa: BLE001
        raise MeasureError("Could not find which way this face points (%s)." % exc)
    if n.Length < _EPS:
        raise MeasureError("Could not find which way this face points.")
    n = n.normalize()
    probe = 0.01
    inward = n * -1
    try:
        if not solid.isInside(p + inward * probe, 1e-5, False):
            if solid.isInside(p + n * probe, 1e-5, False):
                inward = n
    except Exception:                                   # noqa: BLE001
        pass
    reach = solid.BoundBox.DiagonalLength + 1.0
    seg = Part.LineSegment(p - inward * 1e-3, p + inward * reach).toShape()
    try:
        common = solid.common(seg)
    except Exception as exc:                            # noqa: BLE001
        raise MeasureError("Could not measure the wall here (%s)." % exc)
    best = None
    for e in common.Edges:
        near = min((vt.Point - p).Length for vt in e.Vertexes)
        if near < 0.01 and (best is None or near < best[0]):
            best = (near, e.Length)
    if best is None:
        raise MeasureError("There is no material behind this point.")
    mm = _r(best[1])
    return {"kind": "wall", "mm": mm, "at": [_r(c) for c in p],
            "dir": [_r(c, 6) for c in inward], "thin": mm < THIN_WALL_MM}


def interference(items, min_volume=None):
    """R306: which parts overlap and by how much. items: [{"label", "shape"}
    (optionally "name", "role", or "mesh" for an Atech part)]. Uses
    atech_geom.overlaps (the agent's own check), else a plain boolean
    common. Returns {"kind", "pairs": [{"a", "b", "volume_mm3"}], "note"}."""
    items = [dict(it, name=it.get("name") or it["label"], role=it.get("role"))
             for it in items]
    g = _geom()
    pairs, note = [], None
    if g is not None:
        kw = {} if min_volume is None else {"min_volume": min_volume}
        try:
            hits, note = g.overlaps(items, **kw)
            label = {it["name"]: it["label"] for it in items}
            for h in hits:
                vol = h.get("volume_mm3")       # None: judged on sampled points
                pairs.append({"a": label.get(h["a"], h["a"]), "b": label.get(h["b"], h["b"]),
                              "volume_mm3": None if vol is None else _r(vol, 2),
                              "points": h.get("mesh_points_inside")})
            return {"kind": "interference", "pairs": pairs, "note": note}
        except Exception as exc:                        # noqa: BLE001
            note = "agent check unavailable (%s); plain boolean used" % exc
    floor = 0.001 if min_volume is None else min_volume
    shp = [it for it in items if it.get("shape") is not None]
    for i in range(len(shp)):
        for j in range(i + 1, len(shp)):
            a, b = shp[i], shp[j]
            if not a["shape"].BoundBox.intersect(b["shape"].BoundBox):
                continue
            try:
                v = a["shape"].common(b["shape"]).Volume
            except Exception:                           # noqa: BLE001
                continue
            if v > floor:
                pairs.append({"a": a["label"], "b": b["label"], "volume_mm3": _r(v, 2)})
    return {"kind": "interference", "pairs": pairs, "note": note}


def fit_check(parts, board, modules):
    """R307: how the Atech board and its modules fit the product's parts:
    per item, its outline margin to the enclosing part per side
    (atech_geom.margins; negative = sticks out), and per module how open its
    working face is (atech_geom.face_open). parts [{"label", "shape"}],
    board {"label", "mesh"} or None, modules [{"label", "name", "mesh",
    "module", "axes"}]. Returns {"kind", "margins", "groups", "faces",
    "faces_note"}."""
    g = _geom()
    if g is None:
        raise MeasureError("The fit check is not available in this build.")
    if board is None and not modules:
        raise MeasureError("There is no Atech board or module in this project.")
    if not parts:
        raise MeasureError("There are no parts around the board to check.")
    atech = ([(board["label"], g._mesh_box(board["mesh"]))] if board else []) + \
        [(m["label"], g._mesh_box(m["mesh"])) for m in modules]
    rows, groups = g.margins(parts, atech)
    faces, note = [], None
    if board is not None and modules:
        try:
            faces = [{"label": r.get("label"), "open_pct": r.get("open_pct"),
                      "blocked_by": r.get("blocked_by"), "face": r.get("face")}
                     for r in g.face_open(parts, board, modules, covers={})]
        except Exception as exc:                        # noqa: BLE001
            note = "the face check could not run (%s)" % exc
    return {"kind": "fit", "margins": rows, "groups": groups, "faces": faces,
            "faces_note": note}


# ----------------------------------------------------------- describing
def _f(x, n=2):
    return ("%%.%df" % n) % (round(float(x), n) + 0.0)


def describe(res):
    """(headline, detail) for a result, in plain words, mm."""
    k = res.get("kind")
    if k == "distance":
        return ("%s mm" % _f(res["mm"]),
                "dX %s  dY %s  dZ %s mm" % (_f(res["dx"]), _f(res["dy"]), _f(res["dz"])))
    if k == "angle":
        return ("%s°" % _f(res["deg"]),
                "%s° between the directions" % _f(res["between"]))
    if k == "radius":
        return ("R %s mm" % _f(res["radius"]), "⌀ %s mm" % _f(res["diameter"]))
    if k == "size":
        return ("%s × %s × %s mm" % (_f(res["x"], 1), _f(res["y"], 1), _f(res["z"], 1)),
                "X %s  Y %s  Z %s mm" % (_f(res["x"]), _f(res["y"]), _f(res["z"])))
    if k == "wall":
        return ("%s mm" % _f(res["mm"]),
                ("Thinner than %s mm: too thin to print reliably" % _f(THIN_WALL_MM, 1))
                if res.get("thin") else "Wall thickness at the point you picked")
    if k == "mass":
        return ("%s g" % _f(res["grams"], 1),
                "%s cm³ of %s (%s g/cm³), solid" % (
                    _f(res["volume_cm3"], 2), res["material"], _f(res["density"], 2)))
    if k == "interference":
        pairs = res.get("pairs") or []
        if not pairs:
            return ("No overlaps", "No two parts run into each other")
        lines = []
        for p in pairs:
            v = p.get("volume_mm3")
            lines.append("%s and %s: %s" % (p["a"], p["b"], ("%s mm³" % _f(v, 1))
                                            if v is not None else "they touch inside"))
        return ("%d overlap%s" % (len(pairs), "" if len(pairs) == 1 else "s"),
                "\n".join(lines))
    if k == "fit":
        lines, worst = [], None
        for r in res.get("margins") or []:
            mm = r["mm"]
            low = min(mm.values())
            worst = low if worst is None else min(worst, low)
            lines.append("%s in %s: %s" % (r["label"], r["part"], "  ".join(
                "%s %s" % (s.upper(), _f(mm[s], 1)) for s in ("-x", "+x", "-y", "+y", "-z", "+z")
                if s in mm)))
        for f in res.get("faces") or []:
            if f.get("open_pct") is None:
                continue
            lines.append("%s face: %s%% open%s" % (
                f["label"], _f(f["open_pct"], 0),
                (" (blocked by %s)" % f["blocked_by"]) if f.get("blocked_by")
                and f["open_pct"] < 100 else ""))
        if res.get("faces_note"):
            lines.append("Note: " + res["faces_note"])
        if worst is None:
            head = "Nothing to fit"
        elif worst < 0:
            head = "Sticks out by %s mm" % _f(-worst, 1)
        else:
            head = "Fits, %s mm to spare" % _f(worst, 1)
        return head, "\n".join(lines)
    return ("", "")


# ================================================================== picks
def pick_shape(pick):
    """The Part shape a pick stands for, in world coordinates: the picked
    sub-element, else the whole object's shape; a pick on a mesh (no Part
    shape) is its picked point as a vertex."""
    import Part
    obj = pick.obj
    if getattr(obj, "Shape", None) is not None and not obj.TypeId.startswith("Mesh::"):
        try:
            s = Part.getShape(obj, pick.sub, needSubElement=True) if pick.sub \
                else Part.getShape(obj)
            if s is not None and not s.isNull():
                return s
        except Exception:                               # noqa: BLE001
            pass
        try:
            s = obj.Shape.getElement(pick.sub.split(".")[-1]) if pick.sub else obj.Shape
            if not s.isNull():
                return s
        except Exception:                               # noqa: BLE001
            pass
    if pick.point is not None:
        return Part.Vertex(_vec(pick.point))
    raise MeasureError("%s has no shape to measure." % getattr(obj, "Label", "That"))


def _whole(pick):
    import Part
    obj = pick.obj
    try:
        return Part.getShape(obj)
    except Exception:                                   # noqa: BLE001
        return getattr(obj, "Shape", None)


def product_parts(doc):
    """The parts a whole-model measurement covers: visible solid objects
    that are not consumed by another shape object (a Cut's inputs), not an
    Atech mesh, not a previous-build leftover. [obj]."""
    out = []
    for o in doc.Objects:
        if getattr(o, "AtechRole", None) or o.TypeId.startswith(("Mesh::", "App::")):
            continue
        if getattr(o, "AtechCableModule", None):
            continue        # R515: a module's ribbon cable is Atech hardware, not a part
        if o.Label.endswith("[previous build]") or getattr(o, "Visibility", True) is False:
            continue
        sh = getattr(o, "Shape", None)
        try:
            if sh is None or sh.isNull() or not sh.Solids:
                continue
        except Exception:                               # noqa: BLE001
            continue
        if any(getattr(u, "Shape", None) is not None and not u.TypeId.startswith("App::")
               for u in o.InList):
            continue
        out.append(o)
    return out


def atech_items(doc):
    """(board, modules) in the shapes fit_check / face_open take."""
    import FreeCAD as App
    board, mods = None, []
    for o in doc.Objects:
        role = getattr(o, "AtechRole", None)
        if o.TypeId != "Mesh::Feature" or not role:
            continue
        if role == "board" and board is None:
            board = {"label": o.Label, "mesh": o.Mesh}
        elif role == "module":
            try:
                r = o.Placement.Rotation
                axes = [[_r(c, 6) for c in r.multVec(App.Vector(*e))]
                        for e in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
            except Exception:                           # noqa: BLE001
                axes = None
            mods.append({"label": o.Label, "name": o.Name, "mesh": o.Mesh,
                         "module": str(getattr(o, "AtechModule", "") or "") or None,
                         "axes": axes})
    return board, mods


def measure(kind, picks, doc=None, material=DEFAULT_MATERIAL):
    """Run one kind of measurement on picks (whole-model kinds use the
    product's parts when picks is empty). Returns the core result dict."""
    picks = list(picks or [])
    need = KIND_PICKS.get(kind, 0)
    if kind not in KIND_LABEL:
        raise MeasureError("Unknown measurement %r." % kind)
    if need and len(picks) < need:
        raise MeasureError(KIND_HINT[kind])
    if kind == "distance":
        return distance(pick_shape(picks[0]), pick_shape(picks[1]))
    if kind == "angle":
        return angle(pick_shape(picks[0]), pick_shape(picks[1]))
    if kind == "radius":
        return radius(pick_shape(picks[0]))
    if kind == "wall":
        p = picks[0]
        sub = pick_shape(p)
        whole = _whole(p)
        face = sub if sub.ShapeType == "Face" else None
        point = p.point
        if point is None:
            if face is None:
                raise MeasureError("Click a face to measure the wall behind it.")
            point = tuple(face.CenterOfMass)
        return wall_at(whole, point, face)
    objs = [p.obj for p in picks] if picks else (product_parts(doc) if doc else [])
    if kind == "fit":
        if doc is None:
            raise MeasureError("Open a project first.")
        board, mods = atech_items(doc)
        parts = [{"label": o.Label, "shape": o.Shape} for o in product_parts(doc)]
        return fit_check(parts, board, mods)
    if not objs:
        raise MeasureError("There are no parts to measure.")
    if kind == "size":
        return size([_whole(Pick(o)) for o in objs])
    if kind == "mass":
        return mass([_whole(Pick(o)) for o in objs], material)
    if kind == "interference":
        items = []
        for o in objs:
            if o.TypeId == "Mesh::Feature":
                items.append({"name": o.Name, "label": o.Label, "mesh": o.Mesh,
                              "role": getattr(o, "AtechRole", None)})
            else:
                items.append({"name": o.Name, "label": o.Label, "shape": _whole(Pick(o)),
                              "role": None})
        if len(items) < 2:
            raise MeasureError("Pick at least two parts to check for overlaps.")
        return interference(items)
    raise MeasureError("Unknown measurement %r." % kind)


# ================================================================ project
def _element_dir(shape, point):
    """The direction that identifies a picked element again after a
    rebuild: a face's outward normal at the point, an edge's direction (or
    a round edge's axis). None for a vertex or a whole part."""
    try:
        if shape.ShapeType == "Face" and point is not None:
            u, v = shape.Surface.parameter(_vec(point))
            n = shape.normalAt(u, v)
            return n.normalize() if n.Length > _EPS else None
        if shape.ShapeType == "Edge":
            d = direction(shape)
            return d.normalize() if d is not None and d.Length > _EPS else None
    except Exception:                                   # noqa: BLE001
        return None
    return None


def _refs(picks):
    """One string per pick: label, sub-element, point, direction (tab
    separated; the last two may be empty)."""
    out = []
    for p in picks:
        pt = "" if p.point is None else ",".join("%.6f" % c for c in p.point)
        nd = ""
        if p.sub:
            try:
                d = _element_dir(pick_shape(p), p.point)
                nd = "" if d is None else ",".join("%.6f" % c for c in d)
            except Exception:                           # noqa: BLE001
                nd = ""
        out.append("%s\t%s\t%s\t%s" % (getattr(p.obj, "Label", ""), p.sub, pt, nd))
    return out


def _parse_ref(s):
    """(label, sub, point or None, direction or None)."""
    label, sub, pt, nd = (s.split("\t") + ["", "", "", ""])[:4]
    point = tuple(float(c) for c in pt.split(",")) if pt else None
    dirn = tuple(float(c) for c in nd.split(",")) if nd else None
    return label, sub, point, dirn


def _title(kind, res, refs):
    head, _d = describe(res)
    labels = []
    for r in refs:
        lab = _parse_ref(r)[0]
        if lab and lab not in labels:
            labels.append(lab)
    on = (" " + " to ".join(labels[:2])) if labels and kind in ("distance", "angle") \
        else ((" " + ", ".join(labels[:2])) if labels else "")
    return "%s%s: %s" % (KIND_LABEL.get(kind, kind), on, head)


def _value(res):
    k = res.get("kind")
    return float({"distance": res.get("mm"), "angle": res.get("deg"),
                  "radius": res.get("radius"), "size": max(res.get("x", 0), res.get("y", 0),
                                                           res.get("z", 0)),
                  "wall": res.get("mm"), "mass": res.get("grams"),
                  "interference": len(res.get("pairs") or []),
                  "fit": 0.0}.get(k) or 0.0)


def _group(doc, create=True):
    for o in doc.Objects:
        if getattr(o, "AtechMeasureGroup", False):
            return o
    if not create:
        return None
    g = doc.addObject("App::DocumentObjectGroup", "AtechMeasurements")
    g.addProperty("App::PropertyBool", "AtechMeasureGroup", PROP_GROUP,
                  "Atech: holds the measurements the user kept")
    g.AtechMeasureGroup = True
    g.setEditorMode("AtechMeasureGroup", 2)
    g.Label = GROUP_LABEL
    return g


_PROPS = (
    ("App::PropertyString", "AtechMeasure", "what was measured"),
    ("App::PropertyStringList", "AtechMeasureRefs", "picked part label, element, point"),
    ("App::PropertyFloat", "AtechMeasureValue", "the main number (mm, deg or g)"),
    ("App::PropertyString", "AtechMeasureText", "the measurement in words"),
    ("App::PropertyString", "AtechMeasureMaterial", "material for a mass"),
    ("App::PropertyBool", "AtechMeasureStale", "a picked part is gone"),
    ("App::PropertyString", "AtechMeasureData", "the full result (JSON)"),
)


def _write(o, kind, res, refs, material):
    head, detail = describe(res)
    o.AtechMeasure = kind
    o.AtechMeasureRefs = list(refs)
    o.AtechMeasureValue = _value(res)
    o.AtechMeasureText = head + ((" (" + detail.replace("\n", "; ") + ")") if detail else "")
    o.AtechMeasureMaterial = material or ""
    o.AtechMeasureStale = False
    o.AtechMeasureData = json.dumps(res, sort_keys=True, default=str)
    o.Label = _title(kind, res, refs)


def record(doc, res, picks=(), material=None):
    """R308: keep a measurement in the project. One undo step. Returns the
    new object. It never links to the measured parts (see the module doc)."""
    kind = res["kind"]
    refs = _refs(picks)
    txn = False
    try:
        doc.openTransaction("Keep measurement")
        txn = True
    except Exception:                                   # noqa: BLE001
        pass
    try:
        g = _group(doc)
        o = doc.addObject("App::FeaturePython", "AtechMeasurement")
        for typ, name, tip in _PROPS:
            o.addProperty(typ, name, PROP_GROUP, "Atech: " + tip)
            o.setEditorMode(name, 1)                    # read-only in the editor
        _write(o, kind, res, refs, material if kind == "mass" else "")
        g.addObject(o)
    finally:
        if txn:
            doc.commitTransaction()
    return o


def measurements(doc):
    """The kept measurements, in document order."""
    return [o for o in doc.Objects if getattr(o, "AtechMeasure", "")]


def remove(doc, obj):
    name = obj.Name
    doc.removeObject(name)
    g = _group(doc, create=False)
    if g is not None and not measurements(doc):
        doc.removeObject(g.Name)


def _find_label(doc, label):
    objs = [o for o in doc.getObjectsByLabel(label)] if label else []
    return objs[0] if objs else None


def _rematch(obj, sub, point, dirn=None):
    """After a rebuild: (sub, point) of the element of obj that stands for
    the one picked before. Same type as sub; for a face or an edge, one
    whose normal / direction is within REMATCH_DEG of the stored one; the
    nearest such to the stored point, within REMATCH_MM. The point moves to
    the nearest point on the new element. (None, None) when nothing
    matches (the face is gone)."""
    import Part
    if not sub:
        return sub, point
    if point is None:
        try:
            s = Part.getShape(obj, sub, needSubElement=True)
            return (sub, None) if s is not None and not s.isNull() else (None, None)
        except Exception:                               # noqa: BLE001
            return None, None
    leaf = sub.split(".")[-1]
    prefix = "".join(ch for ch in leaf if ch.isalpha())
    path = sub[:len(sub) - len(leaf)]
    vx = Part.Vertex(_vec(point))
    try:
        whole = Part.getShape(obj, path.rstrip("."), needSubElement=True) if path \
            else Part.getShape(obj)
    except Exception:                                   # noqa: BLE001
        return None, None
    elems = {"Face": whole.Faces, "Edge": whole.Edges, "Vertex": whole.Vertexes}.get(prefix)
    if not elems:
        return None, None
    want = None if dirn is None else _vec(dirn)
    limit = REMATCH_MM if prefix != "Vertex" else REMATCH_VERTEX_MM
    best = None
    for i, e in enumerate(elems):
        try:
            d, pr, _info = e.distToShape(vx)
        except Exception:                               # noqa: BLE001
            continue
        if d > limit or (best is not None and d >= best[0]):
            continue
        q = pr[0][0]
        if want is not None:
            got = _element_dir(e, q)
            if got is None:
                continue
            c = abs(got.dot(want)) if prefix == "Edge" else got.dot(want)
            if c < math.cos(math.radians(REMATCH_DEG)):
                continue
        best = (d, i, q)
    if best is None:
        return None, None
    return "%s%s%d" % (path, prefix, best[1] + 1), tuple(best[2])


def refresh(doc, kinds=CHEAP):
    """R309: re-measure every kept measurement of `kinds` on the model as
    it is now (after an agent rebuild the parts are new objects with the
    same labels). A part or element that is gone marks it stale (the old
    numbers stay). Only changed values are written. Returns how many
    changed."""
    changed = 0
    for o in measurements(doc):
        kind = o.AtechMeasure
        if kind not in kinds:
            continue
        picks, gone = [], False
        refs = list(o.AtechMeasureRefs)
        for ref in refs:
            label, sub, point, dirn = _parse_ref(ref)
            obj = _find_label(doc, label)
            if obj is None:
                gone = True
                break
            new_sub, new_point = _rematch(obj, sub, point, dirn)
            if new_sub is None:
                gone = True
                break
            picks.append(Pick(obj, new_sub, new_point))
        try:
            res = None if gone else measure(kind, picks, doc,
                                            o.AtechMeasureMaterial or DEFAULT_MATERIAL)
        except MeasureError:
            res = None
        if res is None:
            if not o.AtechMeasureStale:
                o.AtechMeasureStale = True
                changed += 1
            continue
        new_refs = _refs(picks)
        if (o.AtechMeasureStale or abs(o.AtechMeasureValue - _value(res)) > 1e-6
                or o.AtechMeasureData != json.dumps(res, sort_keys=True, default=str)
                or new_refs != refs):
            _write(o, kind, res, new_refs, o.AtechMeasureMaterial)
            changed += 1
    return changed


def measurements_for_brief(doc, refresh_first=True):
    """R310: text lines for the agent's document brief (W6 adds them to
    vision.document_brief): every kept measurement with its value. Empty
    when there are none."""
    ms = measurements(doc)
    if not ms:
        return []
    if refresh_first:
        try:
            refresh(doc)
        except Exception:                               # noqa: BLE001
            pass
    lines = ["Measurements the user kept (mm, re-measured on the current model; "
             "keep these numbers true when you change the model):"]
    for o in ms:
        refs = [_parse_ref(r) for r in o.AtechMeasureRefs]
        what = ", ".join("%s%s" % (lab, (" " + sub.split(".")[-1]) if sub else "")
                         for lab, sub, _p, _d in refs) or "the whole model"
        txt = "- %s of %s: %s" % (KIND_LABEL.get(o.AtechMeasure, o.AtechMeasure), what,
                                  o.AtechMeasureText)
        if o.AtechMeasureStale:
            txt += " [as kept earlier: a picked part or face is no longer in the model]"
        lines.append(txt)
    return lines


# ================================================================ section
AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}


def section_range(shapes, axis):
    """(lo, hi) of the shapes along axis "X" / "Y" / "Z"."""
    k = "XYZ".index(axis)
    lo, hi = None, None
    for s in shapes:
        bb = s.BoundBox
        a, b = (bb.XMin, bb.YMin, bb.ZMin)[k], (bb.XMax, bb.YMax, bb.ZMax)[k]
        lo = a if lo is None else min(lo, a)
        hi = b if hi is None else max(hi, b)
    if lo is None:
        return (0.0, 0.0)
    return (lo, hi)


def section_caps(shapes, axis, offset):
    """R311: the cut faces of each shape on the plane axis = offset (the
    caps a capped section shows). shapes [(label, shape)]. Returns
    [(label, face)] with face a Part.Face (possibly a compound)."""
    shapes = list(shapes)
    if not shapes:
        return []
    import FreeCAD as App
    import Part
    n = App.Vector(*AXES[axis])
    out = []
    for label, s in shapes:
        try:
            wires = s.slice(n, float(offset))
        except Exception:                               # noqa: BLE001
            continue
        wires = [w for w in wires if w.isClosed()]
        if not wires:
            continue
        try:
            face = Part.makeFace(wires, "Part::FaceMakerBullseye")
        except Exception:                               # noqa: BLE001
            try:
                face = Part.makeCompound([Part.Face(w) for w in wires])
            except Exception:                           # noqa: BLE001
                continue
        out.append((label, face))
    return out


def clip_plane(axis, offset, flip=False):
    """(normal, distance) of the clip plane that keeps the side BELOW
    `offset` along the axis (the side above is cut away); flip keeps the
    other side. Coin keeps the half-space the normal points into."""
    n = [-c for c in AXES[axis]]
    d = -float(offset)
    if flip:
        n, d = [-c for c in n], -d
    return n, d


def cut_solid(shape, axis, offset, flip=False):
    """The part of `shape` a section keeps (a real cut solid, for a check
    or an export of the section). Used by the tests to prove the caps."""
    import FreeCAD as App
    import Part
    bb = shape.BoundBox
    big = bb.DiagonalLength * 2 + 10
    k = "XYZ".index(axis)
    lo = [bb.XMin - 1, bb.YMin - 1, bb.ZMin - 1]
    size_ = [bb.XLength + 2, bb.YLength + 2, bb.ZLength + 2]
    if not flip:
        lo[k] = offset - big
    else:
        lo[k] = offset
    size_[k] = big
    box = Part.makeBox(size_[0], size_[1], size_[2], App.Vector(*lo))
    return shape.common(box)


# ===================================================================== ui
MEASURE_QSS = """
#MeasureCard {{ background: {panel}; border: 1px solid {line}; border-radius: 16px; }}
#MTitle {{ color: {text}; font-family: {UI}; font-size: 13px; font-weight: 600; }}
#MHint {{ color: {muted}; font-family: {UI}; font-size: 12px; }}
#MSub {{ color: {muted}; font-family: {UI}; font-size: 11px; font-weight: 600; }}
#MChip {{
    background: transparent; border: 1px solid {line}; border-radius: 13px;
    padding: 0 10px; min-height: 26px; max-height: 26px;
    color: {muted}; font-family: {UI}; font-size: 12px; font-weight: 500;
}}
#MChip:hover {{ background: {hover}; color: {text}; }}
#MChip:checked {{ background: {btn_bg}; color: {btn_text}; border-color: {btn_bg}; }}
#MValue {{ color: {text}; font-family: {MONO}; font-size: 20px; font-weight: 600; }}
#MDetail {{ color: {muted}; font-family: {MONO}; font-size: 11px; }}
#MError {{ color: {fail}; font-family: {UI}; font-size: 12px; }}
#MPrimary {{
    background: {btn_bg}; color: {btn_text}; border: none; border-radius: 14px;
    padding: 0 14px; min-height: 28px; max-height: 28px;
    font-family: {UI}; font-size: 12px; font-weight: 600;
}}
#MPrimary:hover {{ background: {btn_bg_hover}; }}
#MPrimary:disabled {{ background: {line}; color: {dim}; }}
#MGhost {{
    background: transparent; color: {text}; border: 1px solid {line}; border-radius: 14px;
    padding: 0 12px; min-height: 28px; max-height: 28px;
    font-family: {UI}; font-size: 12px; font-weight: 500;
}}
#MGhost:hover {{ background: {hover}; }}
#MGhost:disabled {{ color: {dim}; }}
#MClose {{ background: transparent; border: none; border-radius: 12px;
    min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px; }}
#MClose:hover {{ background: {hover}; }}
QComboBox#MCombo {{
    background: {input_bg}; color: {text}; border: 1px solid {input_border};
    border-radius: 8px; padding: 2px 8px; font-family: {UI}; font-size: 12px;
}}
QListWidget#MKept {{
    background: {sunken}; color: {text}; border: 1px solid {line}; border-radius: 10px;
    font-family: {UI}; font-size: 12px; padding: 2px;
}}
QListWidget#MKept::item {{ padding: 4px 6px; border-radius: 6px; }}
QListWidget#MKept::item:selected {{ background: {hover}; color: {text}; }}
QSlider#MSlider::groove:horizontal {{ height: 4px; background: {track}; border-radius: 2px; }}
QSlider#MSlider::handle:horizontal {{
    background: {btn_bg}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
"""


class MeasureSession(object):
    """The Measure tool's state without Qt: the mode, the picks so far, the
    material and the last result. doc_fn() returns the active document."""

    def __init__(self, doc_fn=None):
        self.doc_fn = doc_fn or _active_doc
        self.mode = "distance"
        self.material = DEFAULT_MATERIAL
        self.picks = []
        self.result = None
        self.error = None

    def set_mode(self, kind):
        if kind not in KIND_LABEL:
            raise ValueError(kind)
        self.mode = kind
        self.picks = []
        self.result = None
        self.error = None

    def needs(self):
        return KIND_PICKS[self.mode]

    def add_pick(self, pick):
        """A click in the model. Returns the result once enough is picked
        (distance / angle: the 2nd click; radius / wall: each click);
        a 3rd click starts over from that click."""
        need = self.needs()
        if need is None:
            self.picks.append(pick)
            return None
        if len(self.picks) >= need:
            self.picks = []
        self.picks.append(pick)
        if len(self.picks) == need:
            return self.run()
        self.result, self.error = None, None
        return None

    def clear(self):
        self.picks = []
        self.result = None
        self.error = None

    def run(self):
        try:
            self.result = measure(self.mode, self.picks, self.doc_fn(), self.material)
            self.error = None
        except MeasureError as exc:
            self.result, self.error = None, str(exc)
        except Exception as exc:                        # noqa: BLE001
            self.result, self.error = None, "Could not measure that (%s)." % exc
        return self.result

    def keep(self):
        doc = self.doc_fn()
        if self.result is None or doc is None:
            return None
        return record(doc, self.result, self.picks, self.material)


def _active_doc():
    try:
        import FreeCAD
        return FreeCAD.ActiveDocument
    except Exception:                                   # noqa: BLE001
        return None


def _qt():
    from PySide6 import QtCore, QtGui, QtWidgets
    return QtCore, QtGui, QtWidgets


def _style():
    from . import style
    return style


class _Marks(object):
    """Temporary 3D marks (a dimension line, dots) in the active view's
    scene graph. Display only: nothing goes into the document."""

    def __init__(self):
        self.node = None
        self.view = None

    def show(self, segments, color=(0.03, 0.5, 0.37), view=None):
        self.clear()
        if not segments:
            return
        try:
            from pivy import coin
            if view is None:
                import FreeCADGui
                view = FreeCADGui.ActiveDocument.ActiveView
            root = view.getSceneGraph()
        except Exception:                               # noqa: BLE001
            return
        sep = coin.SoSeparator()
        st = coin.SoDrawStyle()
        st.lineWidth = 2.5
        st.pointSize = 7
        mat = coin.SoBaseColor()
        mat.rgb = color
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        sep.addChild(pick)
        sep.addChild(st)
        sep.addChild(mat)
        for a, b in segments:
            co = coin.SoCoordinate3()
            co.point.setValues(0, 2, [list(a), list(b)])
            sep.addChild(co)
            ln = coin.SoLineSet()
            ln.numVertices.setValue(2)
            sep.addChild(ln)
            sep.addChild(coin.SoPointSet())
        root.addChild(sep)
        self.node, self.view = sep, view

    def clear(self):
        if self.node is not None:
            try:
                self.view.getSceneGraph().removeChild(self.node)
            except Exception:                           # noqa: BLE001
                pass
        self.node = self.view = None


class _SelObserver(object):
    """FreeCAD selection observer feeding clicks to the panel."""

    def __init__(self, panel):
        self.panel = panel

    def clearSelection(self, doc):                      # noqa: N802
        self.panel.on_clear_selection()

    def removeSelection(self, doc, obj, sub):           # noqa: N802
        self.panel.on_clear_selection()

    def addSelection(self, doc, obj, sub, pnt):         # noqa: N802
        try:
            import FreeCAD
            d = FreeCAD.getDocument(doc)
            o = d.getObject(obj)
        except Exception:                               # noqa: BLE001
            return
        if o is None or getattr(o, "AtechMeasure", ""):
            return
        pt = tuple(pnt) if pnt is not None and any(abs(c) > 0 for c in pnt) else None
        self.panel.on_pick(Pick(o, sub, pt))


def _make_card_class():
    QtCore, QtGui, QtWidgets = _qt()

    class _Card(QtWidgets.QFrame):
        """A floating card over the 3D view, kept at the top left of its
        parent (the MDI area), closed with the X or Escape."""

        closed = QtCore.Signal()

        def __init__(self, title, parent=None):
            super().__init__(parent)
            self.setObjectName("MeasureCard")
            self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
            self.setFocusPolicy(QtCore.Qt.StrongFocus)
            self.lay = QtWidgets.QVBoxLayout(self)
            self.lay.setContentsMargins(14, 12, 14, 14)
            self.lay.setSpacing(8)
            head = QtWidgets.QHBoxLayout()
            self.title = QtWidgets.QLabel(title)
            self.title.setObjectName("MTitle")
            head.addWidget(self.title)
            head.addStretch(1)
            self.btn_close = QtWidgets.QPushButton()
            self.btn_close.setObjectName("MClose")
            self.btn_close.setAccessibleName("Close %s" % title.lower())
            self.btn_close.setToolTip("Close")
            self.btn_close.setCursor(QtCore.Qt.PointingHandCursor)
            self.btn_close.clicked.connect(self.close_card)
            head.addWidget(self.btn_close)
            self.lay.addLayout(head)
            self.setAccessibleName(title)
            self.setFixedWidth(300)
            if parent is not None:
                parent.installEventFilter(self)
            sh = QtWidgets.QGraphicsDropShadowEffect(self)
            sh.setBlurRadius(24)
            sh.setOffset(0, 4)
            sh.setColor(QtGui.QColor(0, 0, 0, 40))
            self.setGraphicsEffect(sh)

        def eventFilter(self, obj, ev):                 # noqa: N802
            if obj is self.parent() and ev.type() == QtCore.QEvent.Resize:
                self.place()
            return False

        def place(self):
            p = self.parentWidget()
            if p is None:
                return
            self.adjustSize()
            h = min(self.sizeHint().height(), max(120, p.height() - 32))
            self.setGeometry(16, 16, self.width(), h)
            self.raise_()

        def keyPressEvent(self, ev):                    # noqa: N802
            if ev.key() == QtCore.Qt.Key_Escape:
                self.close_card()
                return
            super().keyPressEvent(ev)

        def restyle(self):
            st = _style()
            self.setStyleSheet(st.qss(MEASURE_QSS))
            self.btn_close.setIcon(st.icon("x", st.tokens()["muted"], 14))

        def open_card(self):
            self.is_open = True
            self.restyle()
            self.show()
            self.place()

        def close_card(self):
            self.hide()
            if getattr(self, "is_open", False):
                self.is_open = False
                self.closed.emit()

    return _Card


_CARD = []


def _card_class():
    if not _CARD:
        _CARD.append(_make_card_class())
    return _CARD[0]


def MeasurePanel(parent=None, session=None, gui=True):     # noqa: N802
    """The Measure card. session: a MeasureSession (tests pass one with a
    stub doc_fn). gui=False leaves out the FreeCAD selection observer and
    the 3D marks (plain Qt tests)."""
    QtCore, QtGui, QtWidgets = _qt()
    Card = _card_class()

    class _MeasurePanel(Card):
        def __init__(self):
            super().__init__("Measure", parent)
            self.session = session or MeasureSession()
            self.gui = gui
            self.marks = _Marks()
            self._obs = None
            grid = QtWidgets.QGridLayout()
            grid.setSpacing(6)
            self.chips = {}
            self.group = QtWidgets.QButtonGroup(self)
            self.group.setExclusive(True)
            for i, (kind, label, hint, _n) in enumerate(KINDS):
                b = QtWidgets.QPushButton(label)
                b.setObjectName("MChip")
                b.setCheckable(True)
                b.setCursor(QtCore.Qt.PointingHandCursor)
                b.setAccessibleName("Measure %s" % label.lower())
                b.setToolTip(hint)
                b.clicked.connect(lambda _=False, k=kind: self.set_mode(k))
                self.group.addButton(b)
                self.chips[kind] = b
                grid.addWidget(b, i // 4, i % 4)
            self.lay.addLayout(grid)
            self.hint = QtWidgets.QLabel()
            self.hint.setObjectName("MHint")
            self.hint.setWordWrap(True)
            self.lay.addWidget(self.hint)
            mrow = QtWidgets.QHBoxLayout()
            self.mat_label = QtWidgets.QLabel("Material")
            self.mat_label.setObjectName("MHint")
            self.material = QtWidgets.QComboBox()
            self.material.setObjectName("MCombo")
            self.material.setAccessibleName("Material")
            for name, rho in MATERIALS:
                self.material.addItem("%s  %.2f g/cm³" % (name, rho), name)
            self.material.currentIndexChanged.connect(self._on_material)
            self.mat_label.setBuddy(self.material)
            mrow.addWidget(self.mat_label)
            mrow.addWidget(self.material, 1)
            self.mat_row = QtWidgets.QWidget()
            self.mat_row.setLayout(mrow)
            mrow.setContentsMargins(0, 0, 0, 0)
            self.lay.addWidget(self.mat_row)
            self.value = QtWidgets.QLabel("–")
            self.value.setObjectName("MValue")
            self.value.setAccessibleName("Result")
            self.value.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            self.lay.addWidget(self.value)
            self.detail = QtWidgets.QLabel("")
            self.detail.setObjectName("MDetail")
            self.detail.setWordWrap(True)
            self.detail.setAccessibleName("Result details")
            self.detail.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            self.lay.addWidget(self.detail)
            self.error = QtWidgets.QLabel("")
            self.error.setObjectName("MError")
            self.error.setWordWrap(True)
            self.error.setVisible(False)
            self.lay.addWidget(self.error)
            brow = QtWidgets.QHBoxLayout()
            self.btn_run = QtWidgets.QPushButton("Measure")
            self.btn_run.setObjectName("MPrimary")
            self.btn_run.setAccessibleName("Measure now")
            self.btn_run.setCursor(QtCore.Qt.PointingHandCursor)
            self.btn_run.clicked.connect(self.run)
            self.btn_keep = QtWidgets.QPushButton("Keep")
            self.btn_keep.setObjectName("MGhost")
            self.btn_keep.setAccessibleName("Keep this measurement in the project")
            self.btn_keep.setToolTip("Save this measurement with the project; "
                                     "the agent sees it and it is re-measured after each build")
            self.btn_keep.setCursor(QtCore.Qt.PointingHandCursor)
            self.btn_keep.clicked.connect(self.keep)
            self.btn_clear = QtWidgets.QPushButton("Clear")
            self.btn_clear.setObjectName("MGhost")
            self.btn_clear.setAccessibleName("Clear the picks")
            self.btn_clear.setCursor(QtCore.Qt.PointingHandCursor)
            self.btn_clear.clicked.connect(self.clear)
            brow.addWidget(self.btn_run)
            brow.addWidget(self.btn_keep)
            brow.addStretch(1)
            brow.addWidget(self.btn_clear)
            self.lay.addLayout(brow)
            self.kept_label = QtWidgets.QLabel("KEPT IN THIS PROJECT")
            self.kept_label.setObjectName("MSub")
            self.lay.addWidget(self.kept_label)
            self.kept = QtWidgets.QListWidget()
            self.kept.setObjectName("MKept")
            self.kept.setAccessibleName("Kept measurements")
            self.kept.setMaximumHeight(120)
            self.kept_label.setBuddy(self.kept)
            self.lay.addWidget(self.kept)
            self.btn_remove = QtWidgets.QPushButton("Remove")
            self.btn_remove.setObjectName("MGhost")
            self.btn_remove.setAccessibleName("Remove the chosen measurement")
            self.btn_remove.clicked.connect(self.remove_chosen)
            rrow = QtWidgets.QHBoxLayout()
            rrow.addStretch(1)
            rrow.addWidget(self.btn_remove)
            self.lay.addLayout(rrow)
            self.closed.connect(self._on_closed)
            self.set_mode(self.session.mode)

        # -- state
        def set_mode(self, kind):
            self.session.set_mode(kind)
            self.chips[kind].setChecked(True)
            self.hint.setText(KIND_HINT[kind])
            self.mat_row.setVisible(kind == "mass")
            self.btn_run.setVisible(KIND_PICKS[kind] is None)
            self.marks.clear()
            self.show_result()
            if KIND_PICKS[kind] is None and self.gui:
                try:
                    import FreeCADGui
                    for o in FreeCADGui.Selection.getSelection():
                        self.session.picks.append(Pick(o))
                except Exception:                       # noqa: BLE001
                    pass
            if self.isVisible():
                self.place()

        def _on_material(self, _i):
            self.session.material = self.material.currentData()
            if self.session.mode == "mass" and self.session.result is not None:
                self.run()

        def on_pick(self, pick):
            res = self.session.add_pick(pick)
            if res is None and self.session.error is None:
                need = self.session.needs()
                if need:
                    self.value.setText("–")
                    self.detail.setText("%d of %d picked: %s" % (
                        len(self.session.picks), need,
                        getattr(pick.obj, "Label", "")))
                else:
                    self.detail.setText("%d part%s picked" % (
                        len(self.session.picks), "" if len(self.session.picks) == 1 else "s"))
                self.error.setVisible(False)
                self.btn_keep.setEnabled(False)
                return
            self.show_result()

        def run(self):
            self.session.run()
            self.show_result()

        def on_clear_selection(self):
            """Clicking empty space: whole-model kinds forget their picks
            (Measure then covers the whole model again)."""
            if self.session.needs() is None and self.session.picks:
                self.session.picks = []
                self.detail.setText("Whole model")

        def clear(self):
            self.session.clear()
            self.marks.clear()
            if self.gui:
                try:
                    import FreeCADGui
                    FreeCADGui.Selection.clearSelection()
                except Exception:                       # noqa: BLE001
                    pass
            self.show_result()

        def show_result(self):
            st = _style()
            t = st.tokens()
            res, err = self.session.result, self.session.error
            if err:
                self.value.setText("–")
                self.detail.setText("")
                self.error.setText(err)
                self.error.setVisible(True)
            elif res is None:
                self.value.setText("–")
                self.detail.setText("")
                self.error.setVisible(False)
            else:
                head, detail = describe(res)
                self.value.setText(head)
                self.detail.setText(detail)
                self.error.setVisible(False)
            thin = bool(res and res.get("kind") == "wall" and res.get("thin"))
            bad = bool(res and ((res.get("kind") == "interference" and res.get("pairs"))
                                or (res.get("kind") == "fit"
                                    and describe(res)[0].startswith("Sticks"))))
            self.value.setProperty("thin", thin)
            self.value.setStyleSheet("color: %s;" % t["fail"] if (thin or bad) else "")
            self.btn_keep.setEnabled(res is not None)
            if self.gui and res is not None:
                self._mark(res)
            self.refresh_kept()
            if self.isVisible():
                self.place()

        def _mark(self, res):
            k = res.get("kind")
            if k == "distance":
                self.marks.show([(res["p1"], res["p2"])])
            elif k == "wall":
                a = res["at"]
                b = [a[i] + res["dir"][i] * res["mm"] for i in range(3)]
                self.marks.show([(a, b)], (0.8, 0.24, 0.16) if res.get("thin")
                                else (0.03, 0.5, 0.37))
            elif k == "interference" and res.get("pairs"):
                try:
                    import FreeCADGui
                    doc = self.session.doc_fn()
                    FreeCADGui.Selection.clearSelection()
                    for p in res["pairs"]:
                        for lab in (p["a"], p["b"]):
                            for o in doc.getObjectsByLabel(lab):
                                FreeCADGui.Selection.addSelection(o)
                except Exception:                       # noqa: BLE001
                    pass

        def keep(self):
            try:
                o = self.session.keep()
            except Exception as exc:                    # noqa: BLE001
                self.error.setText("Could not keep it (%s)." % exc)
                self.error.setVisible(True)
                return None
            self.refresh_kept()
            return o

        def refresh_kept(self):
            doc = self.session.doc_fn()
            self.kept.clear()
            ms = measurements(doc) if doc is not None else []
            for o in ms:
                text = o.Label + (" (part gone)" if o.AtechMeasureStale else "")
                it = QtWidgets.QListWidgetItem(text)
                it.setData(QtCore.Qt.UserRole, o.Name)
                it.setToolTip(o.AtechMeasureText)
                self.kept.addItem(it)
            self.kept_label.setVisible(bool(ms))
            self.kept.setVisible(bool(ms))
            self.btn_remove.setVisible(bool(ms))

        def remove_chosen(self):
            it = self.kept.currentItem()
            doc = self.session.doc_fn()
            if it is None or doc is None:
                return
            o = doc.getObject(it.data(QtCore.Qt.UserRole))
            if o is not None:
                doc.openTransaction("Remove measurement")
                remove(doc, o)
                doc.commitTransaction()
            self.refresh_kept()

        # -- lifecycle
        def open_card(self):
            doc = self.session.doc_fn()
            if doc is not None:
                try:
                    if refresh(doc):
                        doc.recompute()
                except Exception:                       # noqa: BLE001
                    pass
            super().open_card()
            self.refresh_kept()
            if self.gui and self._obs is None:
                try:
                    import FreeCADGui
                    self._obs = _SelObserver(self)
                    FreeCADGui.Selection.addObserver(self._obs)
                except Exception:                       # noqa: BLE001
                    self._obs = None

        def _on_closed(self):
            self.marks.clear()
            if self._obs is not None:
                try:
                    import FreeCADGui
                    FreeCADGui.Selection.removeObserver(self._obs)
                except Exception:                       # noqa: BLE001
                    pass
                self._obs = None

    return _MeasurePanel()


# ----------------------------------------------------------- section ui
class _SectionView(object):
    """The live capped section in the active 3D view: a Coin clip plane at
    the scene root, and the cut faces (caps) drawn before it so they are not
    clipped. Display only: the document is not touched."""

    def __init__(self):
        self.view = None
        self.clip = None
        self.caps = None

    def apply(self, axis, offset, flip, caps, colors, view=None):
        try:
            from pivy import coin
            if view is None:
                import FreeCADGui
                view = FreeCADGui.ActiveDocument.ActiveView
            root = view.getSceneGraph()
        except Exception:                               # noqa: BLE001
            return False
        if self.view is not view:
            self.remove()
        n, d = clip_plane(axis, offset, flip)
        if self.clip is None:
            self.clip = coin.SoClipPlane()
            self.caps = coin.SoSeparator()
            root.insertChild(self.caps, 0)
            root.insertChild(self.clip, 1)
            self.view = view
        self.clip.plane.setValue(coin.SbPlane(coin.SbVec3f(*n), d))
        self.caps.removeAllChildren()
        for (label, face) in caps:
            try:
                pts, tris = face.tessellate(0.05)
            except Exception:                           # noqa: BLE001
                continue
            if not tris:
                continue
            sep = coin.SoSeparator()
            col = coin.SoBaseColor()
            col.rgb = colors.get(label, (0.8, 0.24, 0.16))
            hints = coin.SoShapeHints()
            hints.vertexOrdering = coin.SoShapeHints.UNKNOWN_ORDERING
            hints.shapeType = coin.SoShapeHints.UNKNOWN_SHAPE_TYPE
            co = coin.SoCoordinate3()
            co.point.setValues(0, len(pts), [[p.x, p.y, p.z] for p in pts])
            fs = coin.SoIndexedFaceSet()
            idx = []
            for t in tris:
                idx += [t[0], t[1], t[2], -1]
            fs.coordIndex.setValues(0, len(idx), idx)
            for c in (hints, col, co, fs):
                sep.addChild(c)
            self.caps.addChild(sep)
        return True

    def remove(self):
        if self.view is not None:
            try:
                root = self.view.getSceneGraph()
                root.removeChild(self.clip)
                root.removeChild(self.caps)
            except Exception:                           # noqa: BLE001
                pass
        self.view = self.clip = self.caps = None


def SectionPanel(parent=None, doc_fn=None, gui=True):     # noqa: N802
    """The Section card: X / Y / Z (PillTabs), an offset slider in 0.1 mm
    steps across the model, Flip, Close. Each change re-cuts the caps after
    a short pause (60 ms) so dragging stays smooth."""
    QtCore, QtGui, QtWidgets = _qt()
    Card = _card_class()
    from .navbar import PillTabs

    class _SectionPanel(Card):
        STEP = 0.1

        def __init__(self):
            super().__init__("Section", parent)
            self.doc_fn = doc_fn or _active_doc
            self.gui = gui
            self.view = _SectionView()
            self.axis = "Z"
            self.flip = False
            self.lo, self.hi = 0.0, 0.0
            self.caps = []
            self.tabs = PillTabs(["X", "Y", "Z"])
            self.tabs.setAccessibleName("Cut across")
            self.tabs.set_index(2, animate=False)
            self.tabs.changed.connect(lambda i: self.set_axis("XYZ"[i]))
            self.lay.addWidget(self.tabs)
            row = QtWidgets.QHBoxLayout()
            self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            self.slider.setObjectName("MSlider")
            self.slider.setAccessibleName("Cut position")
            self.slider.valueChanged.connect(self._on_slider)
            row.addWidget(self.slider, 1)
            self.pos = QtWidgets.QLabel("")
            self.pos.setObjectName("MDetail")
            self.pos.setMinimumWidth(72)
            self.pos.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            row.addWidget(self.pos)
            self.lay.addLayout(row)
            brow = QtWidgets.QHBoxLayout()
            self.btn_flip = QtWidgets.QPushButton("Flip")
            self.btn_flip.setObjectName("MGhost")
            self.btn_flip.setAccessibleName("Show the other side of the cut")
            self.btn_flip.clicked.connect(self.toggle_flip)
            brow.addWidget(self.btn_flip)
            brow.addStretch(1)
            self.lay.addLayout(brow)
            self._timer = QtCore.QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.setInterval(60)
            self._timer.timeout.connect(self.update_cut)
            self.closed.connect(self.view.remove)

        def _shapes(self):
            doc = self.doc_fn()
            if doc is None:
                return []
            return [(o.Label, o.Shape) for o in product_parts(doc)]

        def set_axis(self, axis):
            self.axis = axis
            self.tabs.set_index("XYZ".index(axis))
            self.reset_range()

        def reset_range(self):
            shapes = [s for _l, s in self._shapes()]
            self.lo, self.hi = section_range(shapes, self.axis)
            n = max(1, int(round((self.hi - self.lo) / self.STEP)))
            self.slider.blockSignals(True)
            self.slider.setRange(0, n)
            self.slider.setValue(n // 2)
            self.slider.blockSignals(False)
            self._on_slider(self.slider.value())

        def offset(self):
            return self.lo + self.slider.value() * self.STEP

        def _on_slider(self, _v):
            self.pos.setText("%s %.1f mm" % (self.axis, self.offset()))
            self._timer.start()

        def toggle_flip(self):
            self.flip = not self.flip
            self.update_cut()

        def update_cut(self):
            self.caps = section_caps(self._shapes(), self.axis, self.offset())
            if self.gui:
                self.view.apply(self.axis, self.offset(), self.flip, self.caps,
                                self._colors())

        def _colors(self):
            out = {}
            doc = self.doc_fn()
            for o in (product_parts(doc) if doc is not None else []):
                try:
                    c = o.ViewObject.ShapeColor
                    out[o.Label] = tuple(max(0.0, x * 0.75) for x in c[:3])
                except Exception:                       # noqa: BLE001
                    pass
            return out

        def open_card(self):
            super().open_card()
            self.reset_range()
            self.update_cut()

    return _SectionPanel()


def _view_button(view_bar, icon_name, tip, accessible):
    QtCore, _QtGui, QtWidgets = _qt()
    st = _style()
    b = QtWidgets.QPushButton("")
    b.setObjectName("VBtn")
    b.setCursor(QtCore.Qt.PointingHandCursor)
    b.setToolTip(tip)
    b.setAccessibleName(accessible)
    b.setIconSize(QtCore.QSize(16, 16))
    b.setFixedWidth(34)
    b.setCheckable(True)
    b.setIcon(st.icon(icon_name, st.tokens()["muted"], 16))
    icons = getattr(view_bar, "_icons", None)
    if isinstance(icons, list):
        icons.append((b, icon_name))      # ViewBar.restyle() recolours it
    return b


def _host(view_bar):
    """The widget the cards float over: the view bar's parent (the MDI
    area), else the view bar's window."""
    p = view_bar.parentWidget() if view_bar is not None else None
    return p if p is not None else (view_bar.window() if view_bar is not None else None)


def _attach(button, make_panel):
    def toggled(on):
        if on:
            if getattr(button, "panel", None) is None:
                button.panel = make_panel()
                button.panel.closed.connect(lambda: button.setChecked(False))
            button.panel.open_card()
        elif getattr(button, "panel", None) is not None:
            button.panel.close_card()
    button.panel = None
    button.toggled.connect(toggled)
    return button


#: Lucide "square-split-horizontal": the section tool's view-bar icon.
SECTION_ICON = ('<path d="M8 19H5c-1.1 0-2-.9-2-2V7c0-1.1.9-2 2-2h3"/>'
                '<path d="M16 5h3c1.1 0 2 .9 2 2v10c0 1.1-.9 2-2 2h-3"/>'
                '<line x1="12" x2="12" y1="4" y2="20"/>')


def make_measure_button(view_bar_parent, gui=True, session=None):
    """R312: the view bar's Measure button (ruler icon, checkable): opens
    the Measure card over the 3D view; unchecks when the card closes."""
    b = _view_button(view_bar_parent, "ruler", "Measure (M)", "Measure")
    host = _host(view_bar_parent)
    return _attach(b, lambda: MeasurePanel(host, session=session, gui=gui))


def make_section_button(view_bar_parent, gui=True, doc_fn=None):
    """R312: the view bar's Section button: opens the Section card."""
    # R380: its own icon (a box cut in two); "layers" is the Parts button's.
    _style().PATHS.setdefault("section", SECTION_ICON)
    b = _view_button(view_bar_parent, "section", "Section view (Shift+S)", "Section view")
    host = _host(view_bar_parent)
    return _attach(b, lambda: SectionPanel(host, doc_fn=doc_fn, gui=gui))
