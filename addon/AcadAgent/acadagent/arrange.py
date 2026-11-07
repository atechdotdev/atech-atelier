"""arrange - Align, Mirror and Text for Edit shapes (R890).

The rest of what TinkerCAD's toolbar does, on FreeCAD objects:

    align(objs, axis, where)   parts lined up on x / y / z by their min
                               ("left", "front", "bottom"), centre or max,
                               within the box round all of them
    mirror(obj, axis)          a part flipped across x / y / z through its
                               own centre. An imported part keeps it as an
                               edit step (part_ops); a TinkerCAD shape
                               becomes a plain solid of the flipped shape
    add_text(doc, text)        raised letters, 10 mm high and 3 mm thick,
                               set down beside the model, ready to size

One undo step each; headless (manual_edit has the buttons).
"""
import os

from . import shape_edit as se

ALIGN = ("min", "centre", "max")
TEXT_SIZE = 10.0
TEXT_HEIGHT = 3.0
MAX_TEXT = 60


def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog("[arrange] %s\n" % msg)
    except Exception:                                  # noqa: BLE001
        pass


def align_targets(boxes, axis, where):
    """For world boxes [(min, max) on the axis], the shift each one needs:
    its min / centre / max onto the min / centre / max of all of them."""
    lo = min(b[0] for b in boxes)
    hi = max(b[1] for b in boxes)
    if where == "min":
        return [lo - b[0] for b in boxes]
    if where == "max":
        return [hi - b[1] for b in boxes]
    mid = (lo + hi) / 2.0
    return [mid - (b[0] + b[1]) / 2.0 for b in boxes]


def align(objs, axis, where):
    """Line the parts up (at least two that can move)."""
    import FreeCAD
    if axis not in ("x", "y", "z") or where not in ALIGN:
        raise se.EditRefused("Align on x, y or z, to min, centre or max.")
    objs = [o for o in objs if se.can_move(o)]
    if len(objs) < 2:
        raise se.EditRefused("Select two or more parts to align.")
    A = axis.upper()
    boxes = []
    for o in objs:
        bb = se._world_bbox(o)
        boxes.append((getattr(bb, A + "Min"), getattr(bb, A + "Max")))
    shifts = align_targets(boxes, axis, where)
    doc = objs[0].Document
    se._open(doc, "Align")
    try:
        for o, s in zip(objs, shifts):
            if abs(s) < 1e-9:
                continue
            v = FreeCAD.Vector(*[s if a == axis else 0.0 for a in "xyz"])
            p = o.Placement
            o.Placement = FreeCAD.Placement(p.Base + v, p.Rotation)
    except Exception:
        se._abort(doc)
        raise
    se._done(doc)
    return objs


def _mirror_matrix(axis, centre):
    import FreeCAD
    f = {"x": (-1, 1, 1), "y": (1, -1, 1), "z": (1, 1, -1)}[axis]
    m = FreeCAD.Matrix()
    m.move(centre * -1)
    s = FreeCAD.Matrix()
    s.scale(*f)
    m = s.multiply(m)
    back = FreeCAD.Matrix()
    back.move(centre)
    return back.multiply(m)


def mirror(obj, axis):
    """The part flipped across `axis` about its own centre (one undo step).
    Returns the object (a new one when a shape became a plain solid)."""
    if axis not in ("x", "y", "z"):
        raise se.EditRefused("Mirror across x, y or z.")
    k = se.kind(obj)
    if k in (None, "agent", "hardware"):
        raise se.EditRefused(se.why_not(obj) or "This part cannot be mirrored.")
    if k == "group":
        raise se.EditRefused("Ungroup it first, or mirror the parts in it.")
    from . import part_ops
    if k == "solid":
        return part_ops.apply(obj, {"op": "mirror", "plane": axis})
    if k == "mesh":
        doc = se._txn(obj, "Mirror %s" % obj.Label)
        try:
            m = obj.Mesh.copy()
            pl = m.Placement
            import FreeCAD
            m.Placement = FreeCAD.Placement()
            m.transform(_mirror_matrix(axis, m.BoundBox.Center))
            m.flipNormals()                 # a mirror turns the triangles inside out
            m.Placement = pl
            obj.Mesh = m
        except Exception:
            se._abort(doc)
            raise
        se._done(doc)
        return obj
    # a TinkerCAD shape: the flipped shape as a plain solid
    new = part_ops.make_editable(obj)
    return part_ops.apply(new, {"op": "mirror", "plane": axis})


def _font():
    try:
        from . import sandbox
        f = sandbox.font_path()
        if f and os.path.isfile(f):
            return f
    except Exception:                                  # noqa: BLE001
        pass
    for f in ("/System/Library/Fonts/Supplemental/Arial.ttf",
              "/Library/Fonts/Arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.isfile(f):
            return f
    return None


def text_solid(text, size=TEXT_SIZE, height=TEXT_HEIGHT, font=None):
    """Raised letters as one solid, standing on z = 0 from x = 0."""
    import FreeCAD
    import Part
    text = (text or "").strip()
    if not text:
        raise se.EditRefused("Type the text first.")
    if len(text) > MAX_TEXT:
        raise se.EditRefused("At most %d characters." % MAX_TEXT)
    font = font or _font()
    if not font:
        raise se.EditRefused("No font was found for text.")
    solids = []
    for char in Part.makeWireString(text, font, float(size)):
        if not char:
            continue
        try:
            face = Part.makeFace(char, "Part::FaceMakerBullseye")
        except Exception:                              # noqa: BLE001
            continue
        if face.isNull() or face.Area <= 0:
            continue
        solids.append(face.extrude(FreeCAD.Vector(0, 0, float(height))))
    if not solids:
        raise se.EditRefused("Those characters have no outline in the font.")
    s = solids[0] if len(solids) == 1 else Part.makeCompound(solids)
    bb = s.BoundBox
    s.translate(FreeCAD.Vector(-bb.XMin, -bb.YMin, -bb.ZMin))
    return s


def add_text(doc, text, size=TEXT_SIZE, height=TEXT_HEIGHT):
    """Raised letters beside the model (one undo step)."""
    s = text_solid(text, size, height)
    se._open(doc, "Add text")
    try:
        o = doc.addObject("Part::Feature", "Text")
        o.Shape = s
        o.Label = "Text %s" % text.strip()[:20]
        doc.recompute()
        w, _d, _h = se.size(o)
        se._shift_to(o, se._beside([x for x in doc.Objects if x is not o], w))
        doc.recompute()
    except Exception:
        se._abort(doc)
        raise
    doc.commitTransaction()
    return o
