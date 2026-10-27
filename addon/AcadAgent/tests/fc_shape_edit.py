"""shape_edit under freecadcmd (R800): real FreeCAD geometry, no GUI.

    ATECH_FREECADCMD=<freecadcmd> python3 -m unittest -v test_shape_edit
    (or directly: <freecadcmd> fc_shape_edit.py; the last line is
    SHAPE_EDIT_RESULT=<json>)

Covers: adding each shape beside what is there; typed resize of a box
(parametric), a cylinder (round: parametric; oval: becomes a plain solid of
exactly that size), a STEP-imported solid (scaled geometry, volume follows)
and keeping the footprint centre + bottom; move_to / nudge; turn about the
centre, a tilt staying on the floor; hole + combine = the hole is cut;
ungroup; duplicate; undo of a resize; refusing agent-built and hardware
parts.
"""
import json
import os
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import FreeCAD                                          # noqa: E402
import Part                                             # noqa: E402
from acadagent import shape_edit as se                  # noqa: E402

R = {"checks": {}, "errors": []}


def check(name, ok, detail=None):
    R["checks"][name] = bool(ok)
    if not ok:
        R["errors"].append("%s: %r" % (name, detail))


def close(a, b, tol=0.01):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


try:
    doc = FreeCAD.newDocument("ShapeEdit")
    doc.UndoMode = 1
    box = se.add_shape(doc, "box")
    check("box 20", close(se.size(box), (20, 20, 20)), se.size(box))
    check("box on floor at origin", close(se.position(box), (0, 0, 0)), se.position(box))
    cyl = se.add_shape(doc, "cylinder")
    check("cylinder beside box", se.position(cyl)[0] > 20, se.position(cyl))
    for k in se.SHAPE_ORDER:
        o = se.add_shape(doc, k)
        check("add %s valid" % k, o.Shape.isValid() and o.Shape.Volume > 0, k)

    # box: parametric resize, footprint centre and bottom kept
    p0 = se.position(box)
    se.resize(box, 40, 10, 5)
    check("box resized", close(se.size(box), (40, 10, 5)), se.size(box))
    check("box still parametric", box.TypeId == "Part::Box")
    check("box kept centre+bottom", close(se.position(box), p0), se.position(box))

    # cylinder round -> parametric; oval -> plain solid of that size
    se.resize(cyl, 30, 30, 12)
    check("cyl round parametric", cyl.TypeId == "Part::Cylinder"
          and abs(cyl.Radius.Value - 15) < 1e-6 and abs(cyl.Height.Value - 12) < 1e-6)
    pc = se.position(cyl)
    oval = se.resize(cyl, 30, 15, 12)
    check("oval became solid", oval.TypeId == "Part::Feature", oval.TypeId)
    check("oval size", close(se.size(oval), (30, 15, 12)), se.size(oval))
    check("oval kept place", close(se.position(oval), pc), se.position(oval))

    # imported STEP: a shape written and read back as STEP
    tmp = tempfile.mkdtemp()
    step = os.path.join(tmp, "part.step")
    Part.makeBox(10, 20, 30).exportStep(step)
    import Import
    Import.insert(step, doc.Name)
    doc.recompute()
    imp = [o for o in doc.Objects if o.TypeId == "Part::Feature"
           and o not in (oval,)][-1]
    check("step kind solid", se.kind(imp) == "solid", se.kind(imp))
    v0 = imp.Shape.Volume
    se.resize(imp, 20, 20, 30)                 # x doubled
    check("step resized", close(se.size(imp), (20, 20, 30)), se.size(imp))
    check("step volume doubled", abs(imp.Shape.Volume - 2 * v0) < 1.0,
          (v0, imp.Shape.Volume))
    check("step valid", imp.Shape.isValid())

    # undo the last resize
    doc.undo()
    doc.recompute()
    check("undo resize", close(se.size(imp), (10, 20, 30)), se.size(imp))

    # move, nudge, turn
    se.move_to(box, 100, 50, 0)
    check("move_to", close(se.position(box), (100, 50, 0)), se.position(box))
    se.nudge(box, dx=5)
    check("nudge", close(se.position(box), (105, 50, 0)), se.position(box))
    se.turn(box, "z", 90)
    check("turn z keeps size", close(sorted(se.size(box)), sorted((40, 10, 5))))
    check("turn z keeps centre", close(se.position(box)[:2], (105, 50)), se.position(box))
    se.turn(box, "x", 90)
    check("tilt stays on floor", abs(se.position(box)[2]) < 1e-6, se.position(box))

    # hole + combine: a 10 mm hole through a 30 mm block
    blk = se.add_shape(doc, "box")
    se.resize(blk, 30, 30, 10)
    hole = se.add_shape(doc, "cylinder")
    se.resize(hole, 10, 10, 20)
    bx, by, _bz = se.position(blk)
    se.move_to(hole, bx, by, -5)
    se.set_hole(hole, True)
    check("is hole", se.is_hole(hole))
    grp = se.combine(doc, [blk, hole])
    want = 30 * 30 * 10 - 3.141592653589793 * 5 * 5 * 10
    check("hole cut", abs(grp.Shape.Volume - want) < 1.0, (grp.Shape.Volume, want))
    check("group kind", se.kind(grp) == "group")
    grp_name = grp.Name
    parts = se.ungroup(grp)
    check("ungroup gives inputs back", sorted(p.Name for p in parts)
          == sorted((blk.Name, hole.Name)))
    check("group gone", doc.getObject(grp_name) is None)

    # duplicate
    cp = se.duplicate(blk)
    check("duplicate same size", close(se.size(cp), se.size(blk)))
    check("duplicate beside", se.position(cp)[0] > se.position(blk)[0])

    # refusals
    agent = doc.addObject("Part::Feature", "AgentPart")
    agent.Shape = Part.makeBox(5, 5, 5)
    agent.addProperty("App::PropertyBool", "AtechAgentBuilt", "Atech", "")
    agent.AtechAgentBuilt = True
    try:
        se.resize(agent, 10, 10, 10)
        check("agent refused", False, "resized")
    except se.EditRefused as exc:
        check("agent refused", "Dimensions" in str(exc), str(exc))
    hw = doc.addObject("Part::Feature", "Mod")
    hw.Shape = Part.makeBox(5, 5, 5)
    hw.addProperty("App::PropertyString", "AtechRole", "Atech", "")
    hw.AtechRole = "module"
    try:
        se.move_to(hw, 1, 1, 1)
        check("hardware refused", False, "moved")
    except se.EditRefused:
        check("hardware refused", True)
    try:
        se.resize(box, 0, 5, 5)
        check("zero refused", False)
    except se.EditRefused:
        check("zero refused", True)
    check("same_ratio", close(se.same_ratio((10, 20, 30), 0, 20), (20, 40, 60)))
    check("fmt_mm", se.fmt_mm(12.0) == "12" and se.fmt_mm(12.25) == "12.25")
except Exception:                                       # noqa: BLE001
    R["errors"].append(traceback.format_exc())

R["ok"] = not R["errors"] and all(R["checks"].values())
print("SHAPE_EDIT_RESULT=" + json.dumps(R))
