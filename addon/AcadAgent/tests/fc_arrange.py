"""arrange + handles under freecadcmd (R890): real geometry, no GUI.

    ATECH_FREECADCMD=<freecadcmd> python3 -m unittest -v test_handles
    (or directly: <freecadcmd> fc_arrange.py; the last line is
    ARRANGE_RESULT=<json>)

Covers: align min / centre / max on x and z, in one undo step; mirror of an
imported solid (kept as an edit step), a mesh (normals flipped, still a
solid mesh) and a wedge (becomes a plain solid, flipped); raised text set
down beside the model; the handles overlay built with pivy for a part
sized by hand and one the agent built.
"""
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import FreeCAD                                          # noqa: E402
import Mesh                                             # noqa: E402
from acadagent import arrange                           # noqa: E402
from acadagent import handles                           # noqa: E402
from acadagent import part_ops as po                    # noqa: E402
from acadagent import shape_edit as se                  # noqa: E402

R = {"checks": {}, "errors": []}


def check(name, ok, detail=None):
    R["checks"][name] = bool(ok)
    if not ok:
        R["errors"].append("%s: %r" % (name, detail))


def near(a, b, tol=0.01):
    return abs(a - b) <= tol


try:
    doc = FreeCAD.newDocument("Arrange")
    doc.UndoMode = 1
    a = se.add_shape(doc, "box")
    b = se.add_shape(doc, "cylinder")
    se.resize(b, 10, 10, 40)
    se.move_to(b, 60, 15, 5)
    undo0 = doc.UndoCount
    arrange.align([a, b], "x", "min")
    check("align x min", near(se._world_bbox(a).XMin, se._world_bbox(b).XMin))
    check("align one undo step", doc.UndoCount == undo0 + 1, (undo0, doc.UndoCount))
    arrange.align([a, b], "z", "max")
    check("align z max", near(se._world_bbox(a).ZMax, se._world_bbox(b).ZMax))
    arrange.align([a, b], "y", "centre")
    ca = se._world_bbox(a).Center.y
    check("align y centre", near(ca, se._world_bbox(b).Center.y))
    try:
        arrange.align([a], "x", "min")
        check("align needs two", False)
    except se.EditRefused:
        check("align needs two", True)

    # mirror: an imported-style solid keeps it as a step
    w = se.add_shape(doc, "wedge")
    bb0 = se._world_bbox(w)
    vol = w.Shape.Volume
    w2 = arrange.mirror(w, "x")
    check("wedge became solid", se.kind(w2) == "solid", se.kind(w2))
    check("wedge kept volume", near(w2.Shape.Volume, vol, 1e-3))
    check("wedge stays put", near(se._world_bbox(w2).XMin, bb0.XMin, 1e-3))
    check("mirror is a step", po.steps(w2) and po.steps(w2)[-1]["op"] == "mirror")
    m = doc.addObject("Mesh::Feature", "M")
    m.Mesh = Mesh.createCone(5, 0, 10, True, 1.0, 24)
    m.Placement.Base = FreeCAD.Vector(200, 0, 0)
    mb = m.Mesh.BoundBox
    arrange.mirror(m, "z")
    check("mesh mirrored in place", near(m.Mesh.BoundBox.ZMin, mb.ZMin, 1e-3)
          and near(m.Mesh.BoundBox.ZMax, mb.ZMax, 1e-3))
    check("mesh still solid", m.Mesh.isSolid() and m.Mesh.Volume > 0, m.Mesh.Volume)

    # text
    t = arrange.add_text(doc, "Atech")
    check("text solid", se.kind(t) == "solid" and t.Shape.Volume > 0)
    sz = se.size(t)
    check("text 3 mm thick", near(sz[2], 3.0, 1e-3), sz)
    check("text beside", se._world_bbox(t).XMin > se._world_bbox(m).XMin - 1e6)
    check("text on floor", near(se.position(t)[2], 0.0, 1e-6))
    try:
        arrange.add_text(doc, "   ")
        check("empty text refused", False)
    except se.EditRefused:
        check("empty text refused", True)

    # the overlay
    node = handles.Handles.build(handles._box(a), handles.allowed(a), "20 mm")
    check("overlay built", node.getNumChildren() >= 10, node.getNumChildren())
    a.addProperty("App::PropertyBool", "AtechAgentBuilt", "Atech")
    a.AtechAgentBuilt = True
    check("agent part: move and turn only",
          set(handles.allowed(a)) == {handles.LIFT, handles.BODY} | set(handles.TURNS))
    node2 = handles.Handles.build(handles._box(a), handles.allowed(a))
    check("agent overlay smaller", node2.getNumChildren() < node.getNumChildren())
except Exception:                                       # noqa: BLE001
    R["errors"].append(traceback.format_exc())

R["ok"] = not R["errors"] and all(R["checks"].values())
print("ARRANGE_RESULT=" + json.dumps(R))
