"""part_ops - granular edits on imported parts, kept as steps (R885).

An imported part (design_import.add_file) keeps its original shape in the
property AtechBase and the edits made to it in AtechEditSteps (JSON). Its
Shape is always replay(AtechBase, steps): an edit appends a step and
replays; Undo step drops the last one; Back to original drops them all.
Nothing is ever lost from the file the user brought in.

A step is a dict. Points and directions are in the part's own frame (its
Shape without its Placement), so moving or turning the part never breaks
its steps; a step given in the document frame (the agent's, or a picked
point) is stored with "m", the matrix from that frame to the part's.

    push_pull  face, distance      a flat face moved out (adds) or in (cuts)
    hole       face, diameter, depth (None = through), at (optional point)
    fillet     edges, radius
    chamfer    edges, size
    hollow     thickness, open (faces left open; none = a closed shell)
    mirror     plane x|y|z         flipped about its own centre
    split      plane x|y|z, at, keep above|below
    add / cut  shape box (min, max) | cylinder (center, axis, radius,
               height): material added or cut away

Faces are 1-based numbers (FreeCAD's Face3) or a direction: top, bottom,
+x, -x, +y, -y, +z, -z (the largest flat face that looks that way).
Edges are numbers, "all", "vertical", "face:<face>" (the edges of a face,
e.g. "face:top") . A number names the face or edge as the part is just
before that step, the way the user (or the agent's brief) saw it.

A mesh (STL, 3MF, OBJ) has no faces to pick: mesh_to_solid turns it into
a solid first, its flat areas merged into real faces.

The agent edits a part only when the user ticked "Let the agent edit
it" (AtechAgentEditable): it writes part_edits.json beside model.py and
apply_agent_edits() runs it here, in Atelier, never in its sandbox.
Headless: no Qt (the Edit part window is part_edit.py).
"""
import json
import math

from . import shape_edit as se

EditRefused = se.EditRefused

BASE = "AtechBase"
STEPS = "AtechEditSteps"
EDITABLE = "AtechAgentEditable"
#: The file the agent writes beside model.py.
AGENT_FILE = "part_edits.json"
OPS = ("push_pull", "hole", "fillet", "chamfer", "hollow", "mirror", "split",
       "add", "cut")
DIRECTIONS = {"top": (0, 0, 1), "bottom": (0, 0, -1),
              "+x": (1, 0, 0), "-x": (-1, 0, 0), "+y": (0, 1, 0),
              "-y": (0, -1, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}
#: A face looks "that way" within this angle (degrees).
DIRECTION_TOL = 15.0
#: A mesh with more triangles is simplified to about this many first:
#: sewing and merging take seconds per 10 000 and pickable faces get lost
#: in the noise above it.
MAX_FACETS = 40000
#: Steps an agent turn may add to one part, and parts per turn.
AGENT_MAX_STEPS = 12
AGENT_MAX_PARTS = 8
MAX_MM = 10000.0


def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog("[part_ops] %s\n" % msg)
    except Exception:                                  # noqa: BLE001
        pass


# ------------------------------------------------------------------ what it is
def can_edit(obj):
    """True for a part whose faces and edges can be edited here: a plain
    solid (imported STEP / IGES / BREP, or one of the user's own)."""
    return se.kind(obj) == "solid"


def why_not(obj):
    """One sentence for the user when the part cannot be edited here, else ""."""
    k = se.kind(obj)
    if k == "solid":
        return ""
    if k == "mesh":
        return ("This is a mesh (STL, 3MF or OBJ): triangles, no faces to "
                "pick. Convert it to a solid first.")
    if k in ("box", "cylinder", "sphere", "cone", "torus", "wedge", "group"):
        return ("Make it a plain solid first (Make editable): then its faces "
                "and edges can be edited.")
    return se.why_not(obj) or "This part cannot be edited here."


def steps(obj):
    try:
        out = json.loads(getattr(obj, STEPS, "") or "[]")
        return out if isinstance(out, list) else []
    except ValueError:
        return []


def has_base(obj):
    sh = getattr(obj, BASE, None)
    return sh is not None and not sh.isNull()


def agent_editable(obj):
    return bool(getattr(obj, EDITABLE, False)) and can_edit(obj)


def _local_shape(obj):
    import FreeCAD
    s = obj.Shape.copy()
    s.Placement = FreeCAD.Placement()
    return s


def ensure_props(obj):
    """Give a solid its AtechBase (the shape as it is now) and an empty step
    list, once. Safe to call again."""
    if not hasattr(obj, BASE):
        obj.addProperty("Part::PropertyPartShape", BASE, "Atech",
                        "The part as it was brought in; edits replay on it")
        try:
            obj.setEditorMode(BASE, 2)                 # hidden in the editor
        except Exception:                              # noqa: BLE001
            pass
    if not hasattr(obj, STEPS):
        obj.addProperty("App::PropertyString", STEPS, "Atech",
                        "Edits made to the part, in order (JSON)")
        try:
            obj.setEditorMode(STEPS, 2)
        except Exception:                              # noqa: BLE001
            pass
    if not hasattr(obj, EDITABLE):
        obj.addProperty("App::PropertyBool", EDITABLE, "Atech",
                        "The design agent may edit this part")
    if not has_base(obj):
        setattr(obj, BASE, _local_shape(obj))
        setattr(obj, STEPS, "[]")


def set_agent_editable(obj, on=True):
    ensure_props(obj)
    setattr(obj, EDITABLE, bool(on))


# ------------------------------------------------------------------ helpers
def _vec(v):
    import FreeCAD
    if isinstance(v, FreeCAD.Vector):
        return FreeCAD.Vector(v)
    if isinstance(v, str):
        d = DIRECTIONS.get(v.lower()) or {"x": (1, 0, 0), "y": (0, 1, 0),
                                          "z": (0, 0, 1)}.get(v.lower())
        if d is None:
            raise EditRefused("Unknown direction %r." % v)
        return FreeCAD.Vector(*d)
    try:
        x, y, z = (float(a) for a in v)
    except (TypeError, ValueError):
        raise EditRefused("A point is three numbers in mm, not %r." % (v,))
    for a in (x, y, z):
        if not math.isfinite(a) or abs(a) > 1e6:
            raise EditRefused("%r is not a usable coordinate." % (v,))
    return FreeCAD.Vector(x, y, z)


def _mm(step, key, lo=0.0, hi=MAX_MM, default=None, allow_none=False):
    v = step.get(key, default)
    if v is None and allow_none:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise EditRefused("%s needs a number in mm for %s." % (step.get("op"), key))
    if not math.isfinite(v) or v < lo or v > hi:
        raise EditRefused("%s: %s must be between %g and %g mm."
                          % (step.get("op"), key, lo, hi))
    return v


def _matrix(step):
    import FreeCAD
    m = step.get("m")
    if not m:
        return None
    try:
        mat = FreeCAD.Matrix(*[float(a) for a in m])
    except (TypeError, ValueError):
        raise EditRefused("A step carries a broken frame.")
    return mat


def _pt(step, key, mat):
    p = _vec(step[key])
    return mat.multVec(p) if mat is not None else p


def _dir(v, mat):
    import FreeCAD
    d = _vec(v)
    if mat is not None:
        d = mat.multVec(d) - mat.multVec(FreeCAD.Vector())
    if d.Length < 1e-9:
        raise EditRefused("A direction cannot be zero.")
    return d.normalize()


def _is_flat(face):
    import Part
    return isinstance(face.Surface, Part.Plane)


def _normal(face):
    u0, u1, v0, v1 = face.ParameterRange
    n = face.normalAt((u0 + u1) / 2.0, (v0 + v1) / 2.0)
    return n.normalize()


def _face(shape, ref, mat=None):
    """(index, Face) for a face number or a direction word."""
    faces = shape.Faces
    if isinstance(ref, bool):
        ref = None
    if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()) or \
            (isinstance(ref, str) and ref.lower().startswith("face")
             and ref[4:].isdigit()):
        i = int(ref[4:] if isinstance(ref, str) and ref.lower().startswith("face")
                else ref)
        if i < 1 or i > len(faces):
            raise EditRefused("The part has faces 1 to %d, not %d." % (len(faces), i))
        return i, faces[i - 1]
    if isinstance(ref, str) and ref.lower() in DIRECTIONS:
        want = _dir(ref.lower(), mat)
        best = None
        for i, f in enumerate(faces, 1):
            if not _is_flat(f):
                continue
            ang = math.degrees(_normal(f).getAngle(want))
            if ang <= DIRECTION_TOL and (best is None or f.Area > best[1].Area):
                best = (i, f)
        if best is None:
            raise EditRefused("The part has no flat face looking %s." % ref)
        return best
    raise EditRefused("Name a face by its number or a direction (top, -x, ...), "
                      "not %r." % (ref,))


def _edges(shape, ref, mat=None):
    """A list of Edges for numbers, "all", "vertical" or "face:<face>"."""
    edges = shape.Edges
    if isinstance(ref, str):
        r = ref.lower().strip()
        if r == "all":
            return list(edges)
        if r == "vertical":
            up = _dir("z", mat)
            out = [e for e in edges if hasattr(e.Curve, "Direction")
                   and abs(abs(e.Curve.Direction.normalize().dot(up)) - 1) < 1e-6]
            if not out:
                raise EditRefused("The part has no vertical straight edges.")
            return out
        if r.startswith("face:"):
            _i, f = _face(shape, r[5:], mat)
            return list(f.Edges)
        ref = [ref]
    if isinstance(ref, int):
        ref = [ref]
    if not isinstance(ref, (list, tuple)) or not ref:
        raise EditRefused("Name the edges: numbers, \"all\", \"vertical\" or "
                          "\"face:top\".")
    out = []
    for r in ref:
        if isinstance(r, str) and not r.isdigit():
            out += _edges(shape, r, mat)
            continue
        try:
            i = int(r)
        except (TypeError, ValueError):
            raise EditRefused("%r is not an edge number." % (r,))
        if i < 1 or i > len(edges):
            raise EditRefused("The part has edges 1 to %d, not %d." % (len(edges), i))
        out.append(edges[i - 1])
    # the same edge named twice makes fillets fail
    seen, uniq = [], []
    for e in out:
        if not any(e.isSame(s) for s in seen):
            seen.append(e)
            uniq.append(e)
    return uniq


def _faces(shape, refs, mat=None):
    if refs in (None, "", []):
        return []
    if not isinstance(refs, (list, tuple)):
        refs = [refs]
    return [_face(shape, r, mat)[1] for r in refs]


def _big(shape):
    return max(shape.BoundBox.DiagonalLength, 1.0) * 2.0


def _solid(result, what):
    """The edit's result as one clean shape, or a refusal."""
    try:
        result = result.removeSplitter()
    except Exception:                                  # noqa: BLE001
        pass
    if result.isNull() or not result.Solids:
        raise EditRefused("%s left no solid." % what)
    if len(result.Solids) == 1:
        result = result.Solids[0]
    if not result.isValid():
        try:
            result.fix(1e-4, 1e-4, 1e-4)
        except Exception:                              # noqa: BLE001
            pass
    if not result.isValid() or result.Volume <= 1e-6:
        raise EditRefused("%s did not give a valid solid." % what)
    return result


def _plane_axis(name):
    import FreeCAD
    k = str(name or "").lower().lstrip("+-")
    if k not in ("x", "y", "z"):
        raise EditRefused("A plane is x, y or z, not %r." % (name,))
    return k, FreeCAD.Vector(*{"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[k])


# ------------------------------------------------------------------ the ops
def run_step(shape, step):
    """The shape after one step. Raises EditRefused with words for the user."""
    import FreeCAD
    import Part
    if not isinstance(step, dict):
        raise EditRefused("A step is a dict like {\"op\": \"fillet\", ...}.")
    op = step.get("op")
    mat = _matrix(step)
    if op == "push_pull":
        _i, f = _face(shape, step.get("face"), mat)
        if not _is_flat(f):
            raise EditRefused("Push/pull takes a flat face.")
        d = _mm(step, "distance", -MAX_MM, MAX_MM)
        if abs(d) < 1e-4:
            raise EditRefused("Push/pull by 0 mm changes nothing.")
        prism = f.extrude(_normal(f) * d)
        return _solid(shape.fuse(prism) if d > 0 else shape.cut(prism),
                      "Push/pull")
    if op == "hole":
        _i, f = _face(shape, step.get("face"), mat)
        if not _is_flat(f):
            raise EditRefused("A hole is drilled into a flat face.")
        r = _mm(step, "diameter", 0.1, MAX_MM) / 2.0
        depth = _mm(step, "depth", 0.01, MAX_MM, allow_none=True)
        n = _normal(f)
        c = _pt(step, "at", mat) if step.get("at") is not None else f.CenterOfMass
        # onto the face's plane
        c = c - n * (c - f.CenterOfMass).dot(n)
        h = _big(shape) if depth is None else depth
        lead = 0.5
        cyl = Part.makeCylinder(r, h + lead, c + n * lead, n * -1)
        return _solid(shape.cut(cyl), "The hole")
    if op in ("fillet", "chamfer"):
        edges = _edges(shape, step.get("edges"), mat)
        key = "radius" if op == "fillet" else "size"
        v = _mm(step, key, 0.01, MAX_MM)
        try:
            out = (shape.makeFillet(v, edges) if op == "fillet"
                   else shape.makeChamfer(v, edges))
        except Exception as exc:                       # noqa: BLE001
            raise EditRefused("A %g mm %s does not fit those edges (%s). Try "
                              "a smaller one or fewer edges."
                              % (v, op, str(exc) or type(exc).__name__))
        return _solid(out, "The %s" % op)
    if op == "hollow":
        t = _mm(step, "thickness", 0.1, MAX_MM)
        open_faces = _faces(shape, step.get("open"), mat)
        try:
            if open_faces:
                out = shape.makeThickness(open_faces, -t, 1e-3)
            else:
                inner = shape.makeOffsetShape(-t, 1e-3)
                out = shape.cut(inner)
        except Exception as exc:                       # noqa: BLE001
            raise EditRefused("Could not hollow it with %g mm walls (%s). Try "
                              "thinner walls." % (t, str(exc) or type(exc).__name__))
        return _solid(out, "Hollowing")
    if op == "mirror":
        _k, n = _plane_axis(step.get("plane"))
        bb = shape.BoundBox
        return _solid(shape.mirror(bb.Center, n), "The mirror")
    if op == "split":
        k, n = _plane_axis(step.get("plane"))
        bb = shape.BoundBox
        lo, hi = getattr(bb, k.upper() + "Min"), getattr(bb, k.upper() + "Max")
        at = _mm(step, "at", lo, hi, default=(lo + hi) / 2.0)
        keep = str(step.get("keep", "below")).lower()
        if keep not in ("above", "below"):
            raise EditRefused("split keeps \"above\" or \"below\".")
        big = _big(shape)
        corner = FreeCAD.Vector(bb.Center.x - big / 2, bb.Center.y - big / 2,
                                bb.Center.z - big / 2)
        setattr(corner, k, at if keep == "above" else at - big)
        half = Part.makeBox(big, big, big, corner)
        if not (lo < at < hi):
            raise EditRefused("The split plane misses the part.")
        return _solid(shape.common(half), "The split")
    if op in ("add", "cut"):
        kind = step.get("shape")
        if kind == "box":
            a, b = _vec(step.get("min")), _vec(step.get("max"))
            lo = FreeCAD.Vector(min(a.x, b.x), min(a.y, b.y), min(a.z, b.z))
            size = FreeCAD.Vector(abs(a.x - b.x), abs(a.y - b.y), abs(a.z - b.z))
            if min(size.x, size.y, size.z) < 0.01:
                raise EditRefused("The box has no size.")
            tool = Part.makeBox(size.x, size.y, size.z, lo)
            if mat is not None:
                tool = tool.transformGeometry(mat)
        elif kind == "cylinder":
            r = _mm(step, "radius", 0.01, MAX_MM)
            h = _mm(step, "height", 0.01, MAX_MM)
            c = _pt(step, "center", mat)
            ax = _dir(step.get("axis", "z"), mat)
            tool = Part.makeCylinder(r, h, c, ax)
        else:
            raise EditRefused("%s takes shape \"box\" or \"cylinder\"." % op)
        out = shape.fuse(tool) if op == "add" else shape.cut(tool)
        res = _solid(out, "Adding" if op == "add" else "Cutting")
        if op == "cut" and abs(res.Volume - shape.Volume) < 1e-6:
            raise EditRefused("That cut misses the part.")
        return res
    raise EditRefused("Unknown edit %r (one of: %s)." % (op, ", ".join(OPS)))


def replay(base, step_list):
    """base with every step applied; EditRefused names the step that broke."""
    s = base.copy()
    for i, st in enumerate(step_list, 1):
        try:
            s = run_step(s, st)
        except EditRefused as exc:
            raise EditRefused("Step %d (%s): %s" % (i, describe_step(st), exc))
    return s


def _set_local(obj, shape):
    s = shape.copy()
    s.Placement = obj.Placement
    obj.Shape = s


def _commit(obj, new_steps, name):
    """Replay `new_steps` on the base and store both, in one undo step."""
    ensure_props(obj)
    shape = replay(getattr(obj, BASE), new_steps)
    doc = se._txn(obj, name)
    try:
        setattr(obj, STEPS, json.dumps(new_steps))
        _set_local(obj, shape)
    except Exception:
        se._abort(doc)
        raise
    se._done(doc)
    return obj


def frame_matrix(obj):
    """Document frame -> the part's own frame, as a step's "m"."""
    m = obj.Placement.inverse().toMatrix()
    return [float(a) for a in m.A]


def _in_frame(obj, step, frame):
    st = dict(step)
    if frame == "world":
        import FreeCAD
        if not obj.Placement.isSame(FreeCAD.Placement(), 1e-9):
            st["m"] = frame_matrix(obj)
    return st


# ------------------------------------------------------------------ edits
def apply(obj, step, frame="local"):
    """Add one step to the part and show the result (one undo step)."""
    if not can_edit(obj):
        raise EditRefused(why_not(obj))
    ensure_props(obj)
    st = _in_frame(obj, step, frame)
    return _commit(obj, steps(obj) + [st], describe_step(st).capitalize())


def apply_many(obj, step_list, frame="local", name="Edit part"):
    if not can_edit(obj):
        raise EditRefused(why_not(obj))
    ensure_props(obj)
    new = [_in_frame(obj, s, frame) for s in step_list]
    return _commit(obj, steps(obj) + new, name)


def undo_step(obj):
    cur = steps(obj)
    if not cur:
        raise EditRefused("The part has no edits to undo.")
    return _commit(obj, cur[:-1], "Undo %s" % describe_step(cur[-1]))


def remove_step(obj, index):
    """Drop step `index` (0-based); the later steps are replayed after it."""
    cur = steps(obj)
    if not 0 <= index < len(cur):
        raise EditRefused("No such edit.")
    return _commit(obj, cur[:index] + cur[index + 1:],
                   "Remove %s" % describe_step(cur[index]))


def reset(obj):
    if not steps(obj):
        raise EditRefused("The part is already as it was brought in.")
    return _commit(obj, [], "Back to original")


def describe_step(st):
    """A step in a few words: "fillet 2 mm", "hole 5 mm through"."""
    if not isinstance(st, dict):
        return "edit"
    op = st.get("op", "edit")
    f = lambda k: se.fmt_mm(float(st.get(k) or 0))      # noqa: E731
    try:
        if op == "push_pull":
            d = float(st.get("distance") or 0)
            return "%s face %s by %s mm" % ("pull" if d > 0 else "push",
                                            st.get("face"), se.fmt_mm(abs(d)))
        if op == "hole":
            dep = st.get("depth")
            return "hole %s mm %s" % (f("diameter"), "through" if dep is None
                                      else "%s mm deep" % se.fmt_mm(float(dep)))
        if op == "fillet":
            return "fillet %s mm" % f("radius")
        if op == "chamfer":
            return "chamfer %s mm" % f("size")
        if op == "hollow":
            return "hollow, %s mm walls" % f("thickness")
        if op == "mirror":
            return "mirror %s" % st.get("plane")
        if op == "split":
            return "split %s, keep %s" % (st.get("plane"), st.get("keep", "below"))
        if op in ("add", "cut"):
            return "%s %s" % (op, st.get("shape", "shape"))
    except (TypeError, ValueError):
        pass
    return str(op)


# ------------------------------------------------------------------ meshes
def mesh_to_solid(obj, max_facets=MAX_FACETS, tolerance=0.05, notes=None):
    """A mesh part replaced by a solid of the same shape (one undo step):
    its triangles sewn, flat areas merged into faces. Keeps the label,
    placement, colour and the import's source and licence. Returns the
    new object; what the user should know (it was simplified) is appended
    to `notes`."""
    import FreeCAD
    import Part
    if se.kind(obj) != "mesh":
        raise EditRefused("Only a mesh is converted to a solid.")
    m = obj.Mesh.copy()
    m.Placement = FreeCAD.Placement()
    note = ""
    if m.CountFacets > max_facets:
        n0 = m.CountFacets
        try:
            m.decimate(tolerance * 10, 1.0 - float(max_facets) / n0)
        except Exception as exc:                       # noqa: BLE001
            raise EditRefused("The mesh has %d triangles, too many to turn into "
                              "a solid (%s)." % (n0, exc))
        note = "simplified from %d to %d triangles" % (n0, m.CountFacets)
    if not m.isSolid():
        try:
            m.fillupHoles(1000)
            m.harmonizeNormals()
        except Exception:                              # noqa: BLE001
            pass
    sh = Part.Shape()
    sh.makeShapeFromMesh(m.Topology, tolerance, True)
    try:
        solid = Part.makeSolid(sh)
    except Exception:                                  # noqa: BLE001
        solid = sh
    try:
        solid = solid.removeSplitter()
    except Exception:                                  # noqa: BLE001
        pass
    if not solid.Solids or not solid.isValid():
        raise EditRefused("The mesh is not closed (it has holes or loose "
                          "triangles), so it does not make a solid. Repair it "
                          "in your slicer or mesh tool first.")
    if solid.Volume < 0:
        solid.reverse()
    doc = se._txn(obj, "Convert %s to a solid" % obj.Label)
    try:
        new = doc.addObject("Part::Feature", obj.Name + "_solid")
        s = solid.copy()
        s.Placement = obj.Placement
        new.Shape = s
        new.Label = obj.Label
        se._copy_view(obj, new)
        _copy_import_props(obj, new)
        ensure_props(new)
        label = obj.Label
        doc.removeObject(obj.Name)
        new.Label = label
    except Exception:
        se._abort(doc)
        raise
    se._done(doc)
    if note and notes is not None:
        notes.append(note)
    return new


def _copy_import_props(src, dst):
    for p in src.PropertiesList:
        if not p.startswith("Atech") or p in (BASE, STEPS):
            continue
        try:
            t = src.getTypeIdOfProperty(p)
            if not hasattr(dst, p):
                dst.addProperty(t, p, "Atech", src.getDocumentationOfProperty(p) or "")
            setattr(dst, p, getattr(src, p))
        except Exception as exc:                       # noqa: BLE001
            _log("copy %s: %r" % (p, exc))


def make_editable(obj, notes=None):
    """A primitive (Box, Cylinder, ...) or a hand group replaced by a plain
    solid of the same shape, ready for face and edge edits."""
    k = se.kind(obj)
    if k == "solid":
        ensure_props(obj)
        return obj
    if k == "mesh":
        return mesh_to_solid(obj, notes=notes)
    if k not in ("box", "cylinder", "sphere", "cone", "torus", "wedge", "group"):
        raise EditRefused(why_not(obj))
    if se.is_hole(obj):
        raise EditRefused("A hole shape cuts other parts; edit those instead.")
    doc = se._txn(obj, "Make %s editable" % obj.Label)
    try:
        new = doc.addObject("Part::Feature", "Solid")
        new.Shape = obj.Shape.copy()
        label = obj.Label
        se._copy_view(obj, new)
        for o in [obj] + list(getattr(obj, "OutList", []) if k == "group" else []):
            try:
                doc.removeObject(o.Name)
            except Exception:                          # noqa: BLE001
                pass
        new.Label = label
        ensure_props(new)
    except Exception:
        se._abort(doc)
        raise
    se._done(doc)
    return new


# ------------------------------------------------------------------ the agent
def _fmt(v):
    return "(%s)" % ", ".join("%g" % round(a, 2) for a in (v.x, v.y, v.z))


def _look(n):
    """top / bottom / +x ... when a normal looks that way, else None."""
    import FreeCAD
    for word, d in DIRECTIONS.items():
        if word in ("+z", "-z"):
            continue
        if math.degrees(n.getAngle(FreeCAD.Vector(*d))) <= DIRECTION_TOL:
            return word
    return None


def describe(obj, max_faces=14):
    """Lines for the agent's brief: the part, its edits and its biggest
    faces in the DOCUMENT frame (numbers as of now)."""
    sh = obj.Shape
    bb = sh.BoundBox
    lines = ["%s: %d faces, %d edges, box %s to %s mm%s" % (
        obj.Label, len(sh.Faces), len(sh.Edges),
        _fmt(_bbmin(bb)), _fmt(_bbmax(bb)),
        ("; edits so far: " + "; ".join(describe_step(s) for s in steps(obj)))
        if steps(obj) else "")]
    faces = sorted(enumerate(sh.Faces, 1), key=lambda t: -t[1].Area)[:max_faces]
    for i, f in faces:
        if _is_flat(f):
            n = _normal(f)
            word = _look(n)
            lines.append("  face %d flat%s, normal %s, centre %s, %g mm2" % (
                i, (" " + word) if word else "", _fmt(n), _fmt(f.CenterOfMass),
                round(f.Area, 1)))
        else:
            r = getattr(f.Surface, "Radius", None)
            kind = type(f.Surface).__name__.lower()
            lines.append("  face %d %s%s, centre %s, %g mm2" % (
                i, kind, (" r %g" % round(r, 2)) if r else "",
                _fmt(f.CenterOfMass), round(f.Area, 1)))
    return lines


def _bbmin(bb):
    import FreeCAD
    return FreeCAD.Vector(bb.XMin, bb.YMin, bb.ZMin)


def _bbmax(bb):
    import FreeCAD
    return FreeCAD.Vector(bb.XMax, bb.YMax, bb.ZMax)


def editable_parts(doc):
    return [o for o in getattr(doc, "Objects", []) if agent_editable(o)]


def brief_lines(doc):
    """R885: the EDITABLE PARTS section of the agent's brief, or []."""
    parts = editable_parts(doc)
    if not parts:
        return []
    out = []
    for o in parts[:AGENT_MAX_PARTS]:
        try:
            out += describe(o, max_faces=10)
        except Exception as exc:                       # noqa: BLE001
            _log("describe %s: %r" % (o.Label, exc))
    return out


AGENT_RULE = """EDITABLE PARTS: the user let you edit the imported parts listed under
EDITABLE PARTS in <document_data>. Never rebuild them in model.py. To change
one, write {file} beside model.py (it is applied when your turn ends):
  {{"edits": [{{"part": "<label>", "steps": [{{"op": "fillet", "edges":
  "face:top", "radius": 2}}]}}]}}
Ops: push_pull(face, distance: + adds, - cuts), hole(face, diameter, depth
or null = through, at [x,y,z]), fillet(edges, radius), chamfer(edges, size),
hollow(thickness, open [faces]), mirror(plane x|y|z), split(plane, at, keep
above|below), add|cut(shape "box", min, max | shape "cylinder", center,
axis, radius, height). Coordinates are document mm. A face is its number
from the brief or top|bottom|+x|-x|+y|-y; edges are numbers, "all",
"vertical" or "face:<face>". Numbers change after each step: after the first
step use directions and coordinates. Steps are kept on the part (the user
can undo each); write only the NEW steps, never the old ones."""


def agent_rule():
    return AGENT_RULE.format(file=AGENT_FILE)


def _find(doc, label):
    for o in doc.Objects:
        if o.Label == label:
            return o
    for o in doc.Objects:
        if o.Name == label:
            return o
    return None


def parse_agent_file(text):
    """The {"edits": [...]} the agent wrote, validated in shape; raises
    EditRefused with what is wrong."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise EditRefused("%s is not valid JSON: %s" % (AGENT_FILE, exc))
    edits = data.get("edits") if isinstance(data, dict) else data
    if not isinstance(edits, list) or not edits:
        raise EditRefused("%s needs {\"edits\": [{\"part\": ..., \"steps\": "
                          "[...]}]}." % AGENT_FILE)
    if len(edits) > AGENT_MAX_PARTS:
        raise EditRefused("At most %d parts per turn." % AGENT_MAX_PARTS)
    out = []
    for e in edits:
        if not isinstance(e, dict) or not isinstance(e.get("part"), str):
            raise EditRefused("Each edit names its \"part\" by label.")
        st = e.get("steps")
        if isinstance(st, dict):
            st = [st]
        if not isinstance(st, list) or not st:
            raise EditRefused("%s: \"steps\" is a list of steps." % e["part"])
        if len(st) > AGENT_MAX_STEPS:
            raise EditRefused("%s: at most %d steps per turn."
                              % (e["part"], AGENT_MAX_STEPS))
        for s in st:
            if not isinstance(s, dict) or s.get("op") not in OPS:
                raise EditRefused("%s: unknown step %r." % (e["part"], s))
            s.pop("m", None)              # the frame is Atelier's to set
        out.append((e["part"], st))
    return out


def apply_agent_edits(doc, text):
    """Run the agent's part_edits.json on the parts the user let it edit.
    Each part's steps go in together or not at all. Returns (done, errors):
    lines for the user (and the agent's next turn)."""
    done, errors = [], []
    try:
        edits = parse_agent_file(text)
    except EditRefused as exc:
        return done, [str(exc)]
    for label, st in edits:
        o = _find(doc, label)
        if o is None:
            errors.append("%s: no part with that label." % label)
            continue
        if not agent_editable(o):
            errors.append("%s: the user has not let you edit this part; "
                          "leave it as it is." % label)
            continue
        try:
            apply_many(o, st, frame="world", name="Agent edits to %s" % o.Label)
            done.append("%s: %s" % (o.Label, "; ".join(describe_step(s) for s in st)))
        except EditRefused as exc:
            errors.append("%s: %s" % (label, exc))
        except Exception as exc:                       # noqa: BLE001
            errors.append("%s: %s" % (label, exc))
    return done, errors
